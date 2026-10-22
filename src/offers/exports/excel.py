"""Excel file of the offers, exported from the database.

The file is only for reading: it is written again from scratch at each
export, and nothing is read from it. The follow-up is entered in the
interface.
"""

import os
import shutil
from dataclasses import dataclass
from datetime import date, datetime

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

from offers.errors import OffersError
from offers.sources import source_label
from offers.tracking import letter_label, status_label

# Columns of the offer.
# fmt: off
SCRIPT_COLUMNS = [
    "Réf.", "Titre", "Entreprise", "Pays", "Ville", "Durée", "Publiée le",
    "Ajoutée le", "En ligne", "Score", "Mots trouvés", "Lien", "Recherche", "Source",
]
# fmt: on
# Columns of the user's follow-up, filled from the database.
TRACKING_COLUMNS = ["Statut", "Lettre", "Favori", "Postulé le", "Notes"]
COLUMNS = SCRIPT_COLUMNS + TRACKING_COLUMNS

ONLINE = "Oui"
NO_LONGER_ONLINE = "Plus en ligne"
FAVORITE = "Oui"
LINK_TEXT = "Ouvrir l'offre"
SHEET_TITLE = "Offres"

# fmt: off
WIDTHS = {
    "Réf.": 12, "Titre": 55, "Entreprise": 28, "Pays": 22, "Ville": 18,
    "Durée": 8, "Publiée le": 12, "Ajoutée le": 12, "En ligne": 14,
    "Score": 7, "Mots trouvés": 28, "Lien": 16, "Recherche": 22, "Source": 16,
    "Statut": 14, "Lettre": 12, "Favori": 8, "Postulé le": 12, "Notes": 40,
}
# fmt: on
DATE_FORMAT = "DD/MM/YYYY"
DATE_COLUMNS = ("Publiée le", "Ajoutée le", "Postulé le")
# Light green background of the offers first seen today.
NEW_COLOR = "FFE2F0D9"
NEW_FILL = PatternFill("solid", fgColor=NEW_COLOR)
BACKUP_DIR = "backup"
LOCK_PREFIX = "~$"


class ExcelError(OffersError):
    """Problem with the Excel file."""


@dataclass(frozen=True)
class ExcelReport:
    """What an export wrote."""

    # Offers written, one per row.
    rows: int


def check_file_closed(path):
    """Stop if the file is open in Excel.

    When Excel opens a file, it creates a "~$name.xlsx" file next to it.
    """
    folder, name = os.path.split(path)
    if os.path.exists(os.path.join(folder, LOCK_PREFIX + name)):
        raise ExcelError(f"{name} est ouvert : ferme l'Excel puis relance.")


def save_backup(path):
    """Copy the current file into the "backup" folder."""
    backup_dir = os.path.join(os.path.dirname(path), BACKUP_DIR)
    name, extension = os.path.splitext(os.path.basename(path))
    moment = datetime.now().strftime("%Y-%m-%d_%H%M")
    try:
        os.makedirs(backup_dir, exist_ok=True)
        shutil.copy2(path, os.path.join(backup_dir, f"{name}_{moment}{extension}"))
    except OSError as err:
        raise ExcelError(f"Impossible de sauvegarder {path} dans {backup_dir} : {err}") from err


def save_workbook(workbook, path):
    """Save atomically: a temporary file first, then it replaces the old one.

    If saving fails, the old file stays intact.
    """
    temporary_path = path + ".tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        workbook.save(temporary_path)
        os.replace(temporary_path, path)
    except OSError as err:
        if os.path.exists(temporary_path):
            os.remove(temporary_path)
        raise ExcelError(f"Impossible d'écrire {path} : {err}") from err


def new_sheet(workbook):
    """Set up the sheet: title, bold column titles, widths, frozen first row."""
    sheet = workbook.active
    sheet.title = SHEET_TITLE
    sheet.freeze_panes = "A2"
    for number, title in enumerate(COLUMNS, 1):
        sheet.cell(row=1, column=number, value=title).font = Font(bold=True)
        sheet.column_dimensions[get_column_letter(number)].width = WIDTHS[title]
    return sheet


def row_values(stored):
    """Return {column title: value} for a StoredOffer."""
    offer = stored.offer
    return {
        "Réf.": offer.reference,
        "Titre": offer.title,
        "Entreprise": offer.company,
        "Pays": offer.country,
        "Ville": offer.city,
        "Durée": offer.duration_months,
        "Publiée le": offer.published_on,
        "Ajoutée le": stored.first_seen.date(),
        "En ligne": ONLINE if stored.online else NO_LONGER_ONLINE,
        "Score": stored.score,
        "Mots trouvés": stored.words,
        "Lien": LINK_TEXT,
        "Recherche": stored.search_name,
        "Source": source_label(offer.source),
        "Statut": status_label(stored.status) if stored.status else None,
        "Lettre": letter_label(stored.letter_status) if stored.letter_status else None,
        "Favori": FAVORITE if stored.favorite else None,
        "Postulé le": as_date(stored.applied_on),
        "Notes": stored.notes,
    }


def as_date(text):
    """Return an ISO date text as a date; other texts are kept as they are.

    The import of the old Excel file (lot 2) kept dates typed as text.
    """
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return text


def write_row(sheet, row, stored, highlight):
    """Write a StoredOffer on the given row."""
    for number, (title, value) in enumerate(row_values(stored).items(), 1):
        cell = sheet.cell(row=row, column=number, value=value)
        if title in DATE_COLUMNS:
            cell.number_format = DATE_FORMAT
        if title == "Lien":
            cell.hyperlink = stored.offer.url
            cell.style = "Hyperlink"
        if highlight:
            cell.fill = NEW_FILL


def write_workbook(path, stored_offers, today):
    """Write a new Excel file with the offers that are not in the trash.

    stored_offers: StoredOffer list (database.list_offers); written in the
        order of first_seen, then id.
    today: offers first seen on that day get a green background, except
        when the file did not exist yet: everything would be green.
    """
    check_file_closed(path)
    file_exists = os.path.exists(path)
    workbook = Workbook()
    sheet = new_sheet(workbook)
    shown = sorted(
        (stored for stored in stored_offers if not stored.hidden),
        key=lambda stored: (stored.first_seen, stored.id),
    )
    for row, stored in enumerate(shown, 2):
        highlight = file_exists and stored.first_seen.date() == today
        write_row(sheet, row, stored, highlight)
    sheet.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(shown) + 1}"

    # Backup last: nothing is written while an error is still possible.
    if file_exists:
        save_backup(path)
    save_workbook(workbook, path)
    return ExcelReport(rows=len(shown))
