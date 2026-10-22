"""Orchestrate a collection: sources, scoring, export."""

from dataclasses import dataclass, field

from offers.errors import OffersError
from offers.exports.excel import check_file_closed, update_workbook
from offers.scoring.keywords import KeywordScorer
from offers.sources import create_source


@dataclass(frozen=True)
class CollectReport:
    """Summary of a collection, shown to the user."""

    online: int
    added: int
    relevant: int
    removed: int
    # Error message by source name, for the sources that failed.
    errors: dict[str, str] = field(default_factory=dict)


@dataclass
class Collected:
    """What the sources returned."""

    found: list = field(default_factory=list)
    online: dict = field(default_factory=dict)
    # False if a source failed or cannot tell which offers are online.
    online_complete: bool = True
    errors: dict[str, str] = field(default_factory=dict)


def run_collect(config, excel_path, today, sources=None):
    """Collect the offers of all sources and update the Excel file.

    sources: Source objects to use; by default, the enabled sources of the
        config. A failing source does not stop the others.
    Raise OffersError if no source could be read: nothing is modified.
    """
    # No need to query the sites if the file cannot be modified.
    check_file_closed(excel_path)
    if sources is None:
        sources = [create_source(source) for source in config.enabled_sources()]
    if not sources:
        raise OffersError("Aucune source activée dans config.yaml.")

    collected = collect_all(sources)
    if len(collected.errors) == len(sources):
        details = "\n".join(f"- {name} : {error}" for name, error in collected.errors.items())
        raise OffersError(f"Aucune source n'a pu être lue. Rien n'est modifié.\n{details}")

    scorer = KeywordScorer(config.keywords_include, config.keywords_exclude)
    online = collected.online if collected.online_complete else None
    excel_report = update_workbook(excel_path, collected.found, online, scorer.score, today)
    return CollectReport(
        online=len({found.offer.reference for found in collected.found}),
        added=excel_report.added,
        relevant=excel_report.relevant,
        removed=excel_report.removed,
        errors=collected.errors,
    )


def collect_all(sources):
    """Read every source, keeping the errors instead of stopping."""
    collected = Collected()
    for source in sources:
        try:
            online = source.online_offers()
            found = source.collect()
        except OffersError as err:
            collected.errors[source.name] = str(err)
            collected.online_complete = False
            continue
        collected.found.extend(found)
        if online is None:
            collected.online_complete = False
        else:
            collected.online.update({offer.reference: offer for offer in online})
    return collected
