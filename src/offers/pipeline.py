"""Orchestrate a collection: sources, database, Excel export."""

from dataclasses import dataclass
from datetime import datetime

from offers.errors import OffersError
from offers.exports.excel import ExcelError, ExcelReport, write_workbook
from offers.scoring.keywords import KeywordScorer
from offers.sources import create_source
from offers.storage.database import (
    SaveReport,
    backup_database,
    connect,
    list_offers,
    probable_duplicates,
    record_run,
    save_source_result,
)


@dataclass(frozen=True)
class SourceReport:
    """Result of one source: what was saved, or its error."""

    name: str
    saved: SaveReport | None = None
    error: str | None = None


@dataclass(frozen=True)
class CollectReport:
    """Summary of a collection, shown to the user."""

    sources: list[SourceReport]
    # None if the export failed, for example because the file is open.
    excel: ExcelReport | None
    excel_error: str | None = None
    # Number of groups of probable duplicates.
    duplicates: int = 0


def run_collect(
    config, db_path, excel_path, now, sources=None, clock=datetime.now, on_source_done=None
):
    """Collect the offers of all sources into the database, then export the Excel file.

    sources: Source objects to use; by default, the enabled sources of the
        config. A failing source does not stop the others.
    clock: returns the current time, for the run log.
    on_source_done: called with the SourceReport of each source, once read.
    Raise OffersError if no source could be read: only the run log is
    written, the Excel file is not modified. A failed export (Excel file
    open, for example) does not undo the collection: it is in the report.
    """
    if sources is None:
        sources = [create_source(source) for source in config.enabled_sources()]
    if not sources:
        raise OffersError("Aucune source activée dans config.yaml.")

    backup_database(db_path, now)
    conn = connect(db_path)
    try:
        score = KeywordScorer(config.keywords_include, config.keywords_exclude).score
        reports = []
        for source in sources:
            reports.append(collect_source(conn, source, score, now, clock))
            if on_source_done:
                on_source_done(reports[-1])
        if all(report.error for report in reports):
            details = "\n".join(f"- {report.name} : {report.error}" for report in reports)
            raise OffersError(
                f"Aucune source n'a pu être lue. L'Excel n'est pas modifié.\n{details}"
            )
        try:
            excel_report, excel_error = export_workbook(conn, excel_path, now.date()), None
        except ExcelError as err:
            excel_report, excel_error = None, str(err)
        duplicates = len(probable_duplicates(conn))
    finally:
        conn.close()
    return CollectReport(
        sources=reports, excel=excel_report, excel_error=excel_error, duplicates=duplicates
    )


def export_workbook(conn, excel_path, today):
    """Write the Excel file again from the database; return its ExcelReport."""
    return write_workbook(str(excel_path), list_offers(conn), today)


def collect_source(conn, source, score, now, clock):
    """Read a source and save its offers; keep its error instead of stopping."""
    started_at = clock()
    try:
        online = source.online_offers()
        found = source.collect()
        saved = save_source_result(conn, source.name, found, online, score, now)
    except OffersError as err:
        record_run(conn, source.name, started_at, clock(), error=str(err))
        return SourceReport(source.name, error=str(err))
    record_run(conn, source.name, started_at, clock(), report=saved)
    return SourceReport(source.name, saved=saved)
