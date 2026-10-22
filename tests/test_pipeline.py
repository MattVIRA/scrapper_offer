"""Tests of the collection pipeline, with fake sources."""

import os
from datetime import date

import pytest
from openpyxl import load_workbook

from offers.config import Config
from offers.errors import OffersError
from offers.exports import excel
from offers.pipeline import run_collect
from offers.scoring.keywords import KeywordScorer
from offers.sources.base import FoundOffer
from tests.factories import FakeSource, make_offer

DAY_1 = date(2026, 10, 20)
DAY_2 = date(2026, 10, 21)
CONFIG = Config(sources=[], keywords_include=["python", "data"], keywords_exclude=[])


def offer(number, source="fake"):
    return make_offer(
        source=source,
        source_id=str(number),
        reference=f"{source}-{number}",
        title=f"Data {number}",
        url=f"https://example.com/{number}",
    )


def rows(path):
    """Return {reference: "En ligne" value}."""
    sheet = load_workbook(path).active
    columns = excel.read_columns(sheet)
    return {
        row[columns["Réf."] - 1]: row[columns["En ligne"] - 1]
        for row in sheet.iter_rows(min_row=2, values_only=True)
    }


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "offres_vie.xlsx")


def test_nominal_case_same_as_the_export(tmp_path, path):
    offers = [offer(1), offer(2), offer(3)]
    source = FakeSource(found=offers[:2], online=offers)

    report = run_collect(CONFIG, path, DAY_1, sources=[source])

    direct_path = str(tmp_path / "direct.xlsx")
    scorer = KeywordScorer(CONFIG.keywords_include, CONFIG.keywords_exclude)
    expected = excel.update_workbook(
        direct_path,
        [FoundOffer(o, "A") for o in offers[:2]],
        {o.reference: o for o in offers},
        scorer.score,
        DAY_1,
    )
    assert [list(r) for r in load_workbook(path).active.values] == [
        list(r) for r in load_workbook(direct_path).active.values
    ]
    assert (report.added, report.relevant, report.removed) == (
        expected.added,
        expected.relevant,
        expected.removed,
    )
    assert report.online == 2 and report.errors == {}


def test_a_failing_source_does_not_stop_the_others(path):
    run_collect(CONFIG, path, DAY_1, sources=[FakeSource(found=[offer(1)], online=[offer(1)])])

    good = FakeSource(found=[offer(2, "good")], online=[offer(2, "good")], name="good")
    bad = FakeSource(error=OffersError("site en panne"), name="bad")
    report = run_collect(CONFIG, path, DAY_2, sources=[bad, good])

    # offer 1 is not in the online list of "good", but since "bad" failed
    # nobody knows: it stays online.
    assert rows(path) == {"fake-1": excel.ONLINE, "good-2": excel.ONLINE}
    assert report.errors == {"bad": "site en panne"}
    assert report.added == 1 and report.removed == 0


def test_a_source_that_cannot_tell_what_is_online(path):
    run_collect(CONFIG, path, DAY_1, sources=[FakeSource(found=[offer(1)], online=[offer(1)])])
    report = run_collect(
        CONFIG,
        path,
        DAY_2,
        sources=[
            FakeSource(found=[offer(2)], online=[offer(2)]),
            FakeSource(found=[offer(3, "other")], online=None, name="other"),
        ],
    )
    assert rows(path)["fake-1"] == excel.ONLINE
    assert report.removed == 0 and report.errors == {}


def test_offline_offers_are_marked_when_all_sources_tell(path):
    run_collect(CONFIG, path, DAY_1, sources=[FakeSource(found=[offer(1)], online=[offer(1)])])
    report = run_collect(
        CONFIG, path, DAY_2, sources=[FakeSource(found=[offer(2)], online=[offer(2)])]
    )
    assert rows(path)["fake-1"] == excel.NO_LONGER_ONLINE
    assert report.removed == 1


def test_all_sources_failing(path):
    run_collect(CONFIG, path, DAY_1, sources=[FakeSource(found=[offer(1)], online=[offer(1)])])
    with open(path, "rb") as file:
        before = file.read()

    sources = [
        FakeSource(error=OffersError("panne A"), name="a"),
        FakeSource(error=OffersError("panne B"), name="b"),
    ]
    with pytest.raises(OffersError, match=r"Aucune source(.|\n)*- a : panne A\n- b : panne B"):
        run_collect(CONFIG, path, DAY_2, sources=sources)
    with open(path, "rb") as file:
        assert file.read() == before
    assert not os.path.exists(os.path.join(os.path.dirname(path), "backup"))


def test_no_enabled_source(path):
    with pytest.raises(OffersError, match="Aucune source activée"):
        run_collect(CONFIG, path, DAY_1)


def test_open_excel_stops_before_any_source_call(path):
    run_collect(CONFIG, path, DAY_1, sources=[FakeSource(found=[offer(1)], online=[offer(1)])])
    open(os.path.join(os.path.dirname(path), "~$offres_vie.xlsx"), "w").close()
    source = FakeSource(found=[offer(2)], online=[offer(2)])

    with pytest.raises(excel.ExcelError, match="est ouvert"):
        run_collect(CONFIG, path, DAY_2, sources=[source])
    assert source.calls == 0


def test_sources_created_from_the_config(monkeypatch, path):
    from offers import sources as registry
    from offers.config import SourceConfig

    class ConfiguredSource(FakeSource):
        def __init__(self, config):
            super().__init__(config, found=[offer(1)], online=[offer(1)])

    monkeypatch.setitem(registry.SOURCES, "fake", ConfiguredSource)
    config = Config(
        sources=[SourceConfig("fake", True, []), SourceConfig("off", False, [])],
        keywords_include=[],
        keywords_exclude=[],
    )
    report = run_collect(config, path, DAY_1)
    assert report.added == 1
