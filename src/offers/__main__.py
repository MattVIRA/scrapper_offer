"""Command line: python -m offers collect | import-excel | export | duplicates."""

import argparse
import sys
from datetime import date, datetime
from pathlib import Path

from offers.config import load_config
from offers.errors import OffersError
from offers.exports.excel import update_workbook
from offers.pipeline import run_collect
from offers.sources import SOURCES, source_label
from offers.storage.database import (
    backup_database,
    connect,
    count_offers,
    list_offers,
    probable_duplicates,
)
from offers.storage.excel_import import import_workbook

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.yaml"
DEFAULT_EXCEL = ROOT / "output" / "offres_vie.xlsx"
DEFAULT_DB = ROOT / "data" / "offers.db"


def build_parser():
    """Return the command line parser."""
    parser = argparse.ArgumentParser(prog="offers", description="Collecte des offres d'emploi.")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser(
        "collect",
        help="récupère les offres et met à jour l'Excel",
        description="Interroge les sources activées dans config.yaml et met à jour l'Excel.",
    )
    collect.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"fichier de réglages (défaut : {DEFAULT_CONFIG})",
    )
    add_excel_option(collect)
    add_db_option(collect)
    import_excel = commands.add_parser(
        "import-excel",
        help="importe une seule fois les offres et le suivi de l'Excel dans la base",
        description="Ajoute à la base les offres et le suivi de l'Excel, sans modifier l'Excel.",
    )
    add_excel_option(import_excel)
    add_db_option(import_excel)
    export = commands.add_parser(
        "export",
        help="met à jour l'Excel à partir de la base, sans interroger les sites",
        description="Ajoute à l'Excel les offres de la base, met à jour « En ligne » et le score.",
    )
    add_db_option(export)
    add_excel_option(export)
    duplicates = commands.add_parser(
        "duplicates",
        help="affiche les doublons probables (même entreprise, même titre)",
        description="Affiche les offres en ligne de même entreprise et de même titre.",
    )
    add_db_option(duplicates)
    return parser


def add_excel_option(parser):
    parser.add_argument(
        "--excel",
        type=Path,
        default=DEFAULT_EXCEL,
        help=f"fichier Excel (défaut : {DEFAULT_EXCEL})",
    )


def add_db_option(parser):
    parser.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_DB,
        help=f"base des offres (défaut : {DEFAULT_DB})",
    )


def collect(args):
    """Run a collection and print its summary."""
    config = load_config(str(args.config), set(SOURCES))
    check_excel_imported(args.db, args.excel)
    report = run_collect(config, str(args.db), str(args.excel), datetime.now())
    for source in report.sources:
        print(source_summary(source))
    print_sync_summary(report.sync)
    print(
        f"Excel : {report.excel.added} lignes ajoutées, "
        f"{report.excel.removed} passées « plus en ligne »."
    )
    print(f"Fichier : {args.excel}")
    if report.duplicates:
        print(
            f"{report.duplicates} doublons probables : python -m offers duplicates pour les voir."
        )


def check_excel_imported(db_path, excel_path):
    """Stop if the Excel file exists but the database is still empty.

    Collecting would then add the offers of the Excel file a second time,
    without their follow-up.
    """
    if not excel_path.exists() or (db_path.exists() and has_offers(db_path)):
        return
    raise OffersError(
        f"La base {db_path} est vide alors que l'Excel {excel_path} existe. "
        "Lance d'abord python -m offers import-excel, pour y reprendre ses offres et son suivi."
    )


def has_offers(db_path):
    """Tell whether the database contains offers."""
    conn = connect(db_path)
    try:
        return count_offers(conn) > 0
    finally:
        conn.close()


def source_summary(source):
    """Return the summary line of one source."""
    label = source_label(source.name)
    if source.error:
        return f"{label} : en erreur, ses offres ne changent pas. {source.error}"
    saved = source.saved
    return (
        f"{label} : {saved.found} offres trouvées, "
        f"{saved.added} nouvelles ajoutées ({saved.relevant} pertinentes), "
        f"{saved.removed} passées « plus en ligne »."
    )


def print_sync_summary(sync):
    """Print what the copy of the follow-up from the Excel file changed."""
    if sync.updated:
        print(f"Suivi recopié depuis l'Excel : {sync.updated} offres mises à jour.")
    print_unknown_statuses(sync.unknown_statuses)
    if sync.unknown_references:
        print(
            f"{sync.unknown_references} lignes de l'Excel ne sont pas dans la base : "
            "leur suivi n'est pas recopié."
        )


def print_unknown_statuses(unknown_statuses):
    for label, count in unknown_statuses.items():
        print(f"Statut inconnu « {label} » ({count} lignes) : gardé au début des notes.")


def import_excel(args):
    """Import the Excel file into the database and print the summary."""
    if not args.excel.exists():
        raise OffersError(f"Fichier Excel introuvable : {args.excel}")
    now = datetime.now()
    backup_database(args.db, now)
    report = import_workbook(connect(args.db), args.excel, now)
    print(
        f"{report.offers_added} offres importées, "
        f"{report.tracking_added} suivis importés (statut, date ou notes)."
    )
    if report.skipped:
        print(
            f"{len(report.skipped)} lignes ignorées, sans lien ni référence VIE : "
            + ", ".join(report.skipped)
        )
    print_unknown_statuses(report.unknown_statuses)
    print(f"Base : {args.db}")


def export(args):
    """Update the Excel file from the database and print the summary."""
    conn = open_existing_database(args.db)
    report = update_workbook(str(args.excel), list_offers(conn), date.today())
    print(f"{report.added} offres ajoutées, {report.removed} passées « plus en ligne ».")
    print(f"Fichier : {args.excel}")


def duplicates(args):
    """Print the groups of probable duplicates."""
    groups = probable_duplicates(open_existing_database(args.db))
    if not groups:
        print("Aucun doublon probable.")
    for group in groups:
        print(f"{group[0].offer.company} — {group[0].offer.title} ({len(group)} offres)")
        for stored in group:
            offer = stored.offer
            print(
                f"  {offer.reference} | {source_label(offer.source)} | {offer.title} | "
                f"{offer.company} | vue le {stored.first_seen:%d/%m/%Y}"
            )


def open_existing_database(path):
    """Open the database; stop if it does not exist yet."""
    if not path.exists():
        raise OffersError(
            f"Base introuvable : {path}. Lance d'abord python -m offers import-excel, "
            "ou python -m offers collect."
        )
    return connect(path)


COMMANDS = {
    "collect": collect,
    "import-excel": import_excel,
    "export": export,
    "duplicates": duplicates,
}


def main(argv=None):
    """Run the command and return the exit code."""
    args = build_parser().parse_args(argv)
    try:
        COMMANDS[args.command](args)
    except OffersError as err:
        print(f"Erreur : {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
