"""Command line: python -m offers collect."""

import argparse
import sys
from datetime import date
from pathlib import Path

from offers.config import load_config
from offers.errors import OffersError
from offers.pipeline import run_collect
from offers.sources import SOURCES

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config.yaml"
DEFAULT_EXCEL = ROOT / "output" / "offres_vie.xlsx"


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
    collect.add_argument(
        "--excel",
        type=Path,
        default=DEFAULT_EXCEL,
        help=f"fichier Excel (défaut : {DEFAULT_EXCEL})",
    )
    return parser


def collect(config_path, excel_path):
    """Run a collection and print its summary."""
    config = load_config(str(config_path), set(SOURCES))
    report = run_collect(config, str(excel_path), date.today())
    print(
        f"{report.online} offres en ligne, "
        f"{report.added} nouvelles ajoutées ({report.relevant} pertinentes), "
        f"{report.removed} passées « plus en ligne »."
    )
    for name, error in report.errors.items():
        print(f"Source « {name} » en erreur : {error}")
    if report.errors:
        print("Aucune offre n'est passée « plus en ligne » : une source n'a pas pu être lue.")
    print(f"Fichier : {excel_path}")


def main(argv=None):
    """Run the command and return the exit code."""
    args = build_parser().parse_args(argv)
    try:
        collect(args.config, args.excel)
    except OffersError as err:
        print(f"Erreur : {err}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
