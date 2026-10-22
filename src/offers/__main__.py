"""Command line: python -m offers collect | export | duplicates | ui."""

import argparse
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from offers.config import load_config
from offers.errors import OffersError
from offers.exports.excel import write_workbook
from offers.pipeline import run_collect
from offers.sources import SOURCES, source_label
from offers.storage.database import (
    connect,
    list_offers,
    probable_duplicates,
)

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.yaml"
DEFAULT_EXCEL = ROOT / "output" / "offres_vie.xlsx"
DEFAULT_DB = ROOT / "data" / "offers.db"
UI_APP = Path(__file__).resolve().parent / "ui" / "app.py"
# The interface never listens on the local network.
STREAMLIT_OPTIONS = ["--server.address=localhost", "--browser.gatherUsageStats=false"]


def build_parser():
    """Return the command line parser."""
    parser = argparse.ArgumentParser(prog="offers", description="Collecte des offres d'emploi.")
    commands = parser.add_subparsers(dest="command", required=True)
    collect = commands.add_parser(
        "collect",
        help="récupère les offres, met à jour la base et régénère l'Excel",
        description="Interroge les sources activées dans config.yaml, met à jour la base "
        "et régénère l'Excel.",
    )
    add_config_option(collect)
    add_excel_option(collect)
    add_db_option(collect)
    export = commands.add_parser(
        "export",
        help="régénère l'Excel à partir de la base, sans interroger les sites",
        description="Réécrit l'Excel avec les offres de la base et leur suivi, hors corbeille.",
    )
    add_db_option(export)
    add_excel_option(export)
    duplicates = commands.add_parser(
        "duplicates",
        help="affiche les doublons probables (même entreprise, même titre)",
        description="Affiche les offres en ligne de même entreprise et de même titre.",
    )
    add_db_option(duplicates)
    ui = commands.add_parser(
        "ui",
        help="ouvre l'interface dans le navigateur",
        description="Ouvre l'interface sur http://localhost:8501, visible seulement depuis ce Mac.",
    )
    add_db_option(ui)
    add_config_option(ui)
    return parser


def add_config_option(parser):
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help=f"fichier de réglages (défaut : {DEFAULT_CONFIG})",
    )


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
    report = run_collect(config, str(args.db), str(args.excel), datetime.now())
    for source in report.sources:
        print(source_summary(source))
    print(excel_summary(report.excel, args.excel))
    if report.duplicates:
        print(
            f"{report.duplicates} doublons probables : python -m offers duplicates pour les voir."
        )


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


def excel_summary(report, path):
    """Return the summary line of the Excel export."""
    return f"Excel régénéré : {report.rows} offres (hors corbeille). Fichier : {path}"


def export(args):
    """Write the Excel file again from the database and print the summary."""
    conn = open_existing_database(args.db)
    report = write_workbook(str(args.excel), list_offers(conn), date.today())
    print(excel_summary(report, args.excel))


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
        raise OffersError(f"Base introuvable : {path}. Lance d'abord python -m offers collect.")
    return connect(path)


def ui(args):
    """Run the Streamlit interface until Ctrl+C."""
    if not args.db.exists():
        raise OffersError(f"Base introuvable : {args.db}. Lance d'abord python -m offers collect.")
    print("Ouverture de l'interface dans le navigateur. Ctrl+C pour l'arrêter.")
    try:
        subprocess.run(streamlit_command(args.db, args.config), check=False)
    except KeyboardInterrupt:
        # Streamlit receives the Ctrl+C too and stops on its own.
        pass
    print("Interface arrêtée.")


def streamlit_command(db_path, config_path):
    """Return the command that runs the interface on db_path and config_path."""
    return [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        str(UI_APP),
        *STREAMLIT_OPTIONS,
        "--",
        "--db",
        str(db_path),
        "--config",
        str(config_path),
    ]


COMMANDS = {
    "collect": collect,
    "export": export,
    "duplicates": duplicates,
    "ui": ui,
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
