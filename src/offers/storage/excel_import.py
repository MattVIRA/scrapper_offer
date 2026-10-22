"""Read the offers and the user's follow-up from the Excel file.

The Excel file is only read, never modified.
"""

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from offers.exports.excel import (
    ONLINE,
    check_reference_column,
    last_row,
    read_columns,
    read_workbook,
)
from offers.model import Offer
from offers.sources import source_name
from offers.sources.business_france import BusinessFranceSource
from offers.storage.database import (
    find_offer_id,
    find_offer_id_by_reference,
    insert_offer,
    load_tracking,
    save_tracking,
    transaction,
)
from offers.tracking import status_code

# Rows without "Source" come from the time when it was the only source.
DEFAULT_SOURCE = BusinessFranceSource.name
# Offer id in a Business France link (".../offres/247348") or reference
# ("VIE247348").
ID_IN_URL = re.compile(r"/offres/(\d+)")
ID_IN_REFERENCE = re.compile(r"^VIE(\d+)$")
ORIGINAL_STATUS_NOTE = "Statut d'origine : {}"


@dataclass(frozen=True)
class ExcelRow:
    """A row of the Excel file that has a reference."""

    source: str
    reference: str
    # Cell values by column title.
    values: dict
    link: str | None


@dataclass(frozen=True)
class TrackingEntry:
    """The follow-up entered in a row, as stored in the tracking table."""

    status: str | None
    applied_on: str | None
    notes: str | None
    # Status label not in offers.tracking, kept in the notes.
    unknown_status: str | None = None

    def is_empty(self):
        return self.status is None and self.applied_on is None and self.notes is None


@dataclass
class ImportReport:
    """What the import added to the database."""

    offers_added: int = 0
    tracking_added: int = 0
    # References of the rows without an offer id.
    skipped: list[str] = field(default_factory=list)
    # Number of rows by unknown status label.
    unknown_statuses: dict[str, int] = field(default_factory=dict)


@dataclass
class SyncReport:
    """What the synchronization of the follow-up changed in the database."""

    updated: int = 0
    # Number of rows by unknown status label.
    unknown_statuses: dict[str, int] = field(default_factory=dict)
    # Rows whose reference is not in the database.
    unknown_references: int = 0


def read_rows(path):
    """Return the rows of the Excel file that have a reference."""
    sheet = read_workbook(path).active
    columns = read_columns(sheet)
    check_reference_column(columns)
    rows = []
    for number in range(2, last_row(sheet) + 1):
        values = {
            title: sheet.cell(row=number, column=column).value for title, column in columns.items()
        }
        reference = text(values["Réf."])
        if reference is None:
            continue
        rows.append(
            ExcelRow(
                source=source_name(text(values.get("Source")) or DEFAULT_SOURCE),
                reference=reference,
                values=values,
                link=row_link(sheet, number, columns),
            )
        )
    return rows


def row_link(sheet, number, columns):
    """Return the target of the "Lien" cell of a row, or None."""
    if "Lien" not in columns:
        return None
    cell = sheet.cell(row=number, column=columns["Lien"])
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    value = text(cell.value)
    return value if value and value.startswith("http") else None


def source_id(row):
    """Return the offer id on its source, from the link or the reference."""
    match = ID_IN_URL.search(row.link or "") or ID_IN_REFERENCE.match(row.reference)
    return match.group(1) if match else None


def row_offer(row, offer_id):
    """Return the Offer described by a row; the Excel has no description."""
    values = row.values
    return Offer(
        source=row.source,
        source_id=offer_id,
        reference=row.reference,
        title=text(values.get("Titre")) or "",
        company=text(values.get("Entreprise")),
        country=text(values.get("Pays")),
        city=text(values.get("Ville")),
        contract_type=None,
        duration_months=to_int(values.get("Durée")),
        published_on=to_date(values.get("Publiée le")),
        url=row.link or "",
    )


def row_tracking(row):
    """Return the follow-up entered in a row.

    An unknown status is kept at the start of the notes, not to lose it.
    """
    label = text(row.values.get("Statut"))
    notes = text(row.values.get("Notes"))
    status = status_code(label) if label else None
    unknown = label if label and status is None else None
    if unknown:
        notes = "\n".join(filter(None, [ORIGINAL_STATUS_NOTE.format(unknown), notes]))
    applied_on = row.values.get("Postulé le")
    if isinstance(applied_on, (date, datetime)):
        applied_on = to_date(applied_on).isoformat()
    else:
        applied_on = text(applied_on)
    return TrackingEntry(status, applied_on, notes, unknown)


def import_workbook(conn, path, now):
    """Add the offers and the follow-up of the Excel file to the database.

    Offers already stored are not modified, and their follow-up is only
    imported if they have none: importing twice changes nothing.
    """
    rows = read_rows(path)
    report = ImportReport()
    with transaction(conn, "Rien n'a été importé : impossible d'écrire dans la base"):
        for row in rows:
            offer_id = source_id(row)
            if offer_id is None:
                report.skipped.append(row.reference)
                continue
            stored_id = find_offer_id(conn, row.source, offer_id)
            if stored_id is None:
                stored_id = insert_row_offer(conn, row, offer_id, now)
                report.offers_added += 1
            entry = row_tracking(row)
            count_unknown_status(report.unknown_statuses, entry)
            if not entry.is_empty() and load_tracking(conn, stored_id) is None:
                save_tracking(conn, stored_id, entry.status, entry.applied_on, entry.notes, now)
                report.tracking_added += 1
    return report


def sync_tracking(conn, path, now):
    """Copy the follow-up entered in the Excel file into the database.

    Until the interface takes over (lot 3), the Excel file is where the
    user enters the follow-up, so it wins over the database. Only the rows
    that changed are written. Nothing to do if the file does not exist.
    """
    report = SyncReport()
    if not os.path.exists(path):
        return report
    rows = read_rows(path)
    with transaction(conn, "Suivi non recopié : impossible d'écrire dans la base"):
        for row in rows:
            offer_id = find_offer_id_by_reference(conn, row.source, row.reference)
            if offer_id is None:
                report.unknown_references += 1
                continue
            entry = row_tracking(row)
            count_unknown_status(report.unknown_statuses, entry)
            if tracking_changed(load_tracking(conn, offer_id), entry):
                save_tracking(conn, offer_id, entry.status, entry.applied_on, entry.notes, now)
                report.updated += 1
    return report


def tracking_changed(stored, entry):
    """Tell whether the entry differs from the stored tracking row (or None)."""
    if stored is None:
        return not entry.is_empty()
    return (stored["status"], stored["applied_on"], stored["notes"]) != (
        entry.status,
        entry.applied_on,
        entry.notes,
    )


def insert_row_offer(conn, row, offer_id, now):
    """Add the offer of a row; its keyword score comes at the next collection."""
    added_on = row.values.get("Ajoutée le")
    return insert_offer(
        conn,
        row_offer(row, offer_id),
        text(row.values.get("Recherche")),
        now,
        first_seen=added_on if isinstance(added_on, datetime) else None,
        online=text(row.values.get("En ligne")) == ONLINE,
    )


def count_unknown_status(counts, entry):
    """Count the unknown status of an entry, if any."""
    if entry.unknown_status:
        counts[entry.unknown_status] = counts.get(entry.unknown_status, 0) + 1


def text(value):
    """Return a cell value as stripped text; None if empty."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def to_int(value):
    """Return a cell value as an integer; None if it is not one."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_date(value):
    """Return a date cell as a date; None if it is not a date."""
    if isinstance(value, datetime):
        return value.date()
    return value if isinstance(value, date) else None
