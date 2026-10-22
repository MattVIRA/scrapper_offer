"""Tests of saving and reading offers in the database."""

from datetime import datetime

import pytest

from offers.scoring.keywords import KeywordScorer
from offers.sources.base import FoundOffer
from offers.storage.database import StorageError, connect, list_offers, save_source_result
from tests.factories import make_offer

DAY_1 = datetime(2026, 10, 20, 8, 0)
DAY_2 = datetime(2026, 10, 21, 8, 0)
DAY_3 = datetime(2026, 10, 22, 8, 0)
SCORE = KeywordScorer(["data", "python"], []).score


def offer(number, source="fake", **changes):
    values = {
        "source": source,
        "source_id": str(number),
        "reference": f"{source}-{number}",
        "title": f"Data {number}",
        "url": f"https://example.com/{number}",
    }
    return make_offer(**{**values, **changes})


def save(conn, offers, online="same", day=DAY_1, source="fake", score=SCORE, search="A"):
    """Save offers found by one search; online defaults to the same offers."""
    found = [FoundOffer(o, search) for o in offers]
    online = offers if online == "same" else online
    return save_source_result(conn, source, found, online, score, day)


def stored(conn):
    """Return {reference: StoredOffer}."""
    return {s.offer.reference: s for s in list_offers(conn)}


def count(conn, table):
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "offers.db")


def test_new_offers_are_added(conn):
    report = save(conn, [offer(1), offer(2, title="Comptable")])

    offers = stored(conn)
    assert list(offers) == ["fake-1", "fake-2"]
    first = offers["fake-1"]
    assert first.offer == offer(1)
    assert first.first_seen == first.last_seen == DAY_1
    assert first.online and first.search_name == "A"
    assert (first.score, first.words) == (1, "data")
    assert first.status is None and first.notes is None
    assert report.found == 2 and report.added == 2
    assert report.relevant == 1 and report.removed == 0


def test_second_run_adds_no_duplicate(conn):
    save(conn, [offer(1), offer(2)])
    report = save(conn, [offer(1), offer(2, title="Data 2 bis")], day=DAY_2)

    offers = stored(conn)
    assert count(conn, "offers") == 2
    assert count(conn, "evaluations") == 2
    assert offers["fake-2"].offer.title == "Data 2 bis"
    assert offers["fake-2"].first_seen == DAY_1
    assert offers["fake-2"].last_seen == DAY_2
    assert report.added == 0 and report.found == 2


def test_offer_found_by_two_searches_keeps_the_first(conn):
    found = [FoundOffer(offer(1), "A"), FoundOffer(offer(1), "B")]
    report = save_source_result(conn, "fake", found, None, SCORE, DAY_1)
    save(conn, [offer(1)], day=DAY_2, search="B")

    assert stored(conn)["fake-1"].search_name == "A"
    assert report.found == 1 and report.added == 1


def test_offer_gone_then_back(conn):
    save(conn, [offer(1), offer(2)])

    report = save(conn, [offer(2)], day=DAY_2)
    assert not stored(conn)["fake-1"].online
    assert report.removed == 1

    # Already offline: not counted again.
    assert save(conn, [offer(2)], day=DAY_3).removed == 0

    save(conn, [offer(1), offer(2)], day=DAY_3)
    back = stored(conn)["fake-1"]
    assert back.online and back.first_seen == DAY_1 and back.last_seen == DAY_3


def test_online_offer_not_found_by_a_search(conn):
    """An online offer updates a stored offer, but is never added."""
    save(conn, [offer(1)])
    save(conn, [], online=[offer(1, title="Data 1 bis"), offer(2)], day=DAY_2)

    offers = stored(conn)
    assert list(offers) == ["fake-1"]
    assert offers["fake-1"].offer.title == "Data 1 bis"
    assert offers["fake-1"].online and offers["fake-1"].last_seen == DAY_2


def test_unknown_online_offers(conn):
    save(conn, [offer(1), offer(2)])
    report = save(conn, [offer(2)], online=None, day=DAY_2)

    offers = stored(conn)
    assert offers["fake-1"].online and offers["fake-1"].last_seen == DAY_1
    assert report.removed == 0


def test_two_sources_only_one_complete(conn):
    save(conn, [offer(1, "a")], source="a")
    save(conn, [offer(1, "b")], source="b")

    # Source "a" cannot tell, source "b" gives its complete list.
    save(conn, [], online=None, day=DAY_2, source="a")
    report = save(conn, [offer(2, "b")], day=DAY_2, source="b")

    offers = stored(conn)
    assert offers["a-1"].online
    assert not offers["b-1"].online
    assert report.removed == 1


def test_score_updated_when_keywords_change(conn):
    save(conn, [offer(1, title="Data Python")])
    save(conn, [offer(1, title="Data Python")], day=DAY_2, score=KeywordScorer(["sql"], []).score)

    first = stored(conn)["fake-1"]
    assert (first.score, first.words) == (0, "")
    assert count(conn, "evaluations") == 1


def test_score_of_an_offline_offer_is_kept(conn):
    save(conn, [offer(1), offer(2)])
    save(conn, [offer(2)], day=DAY_2, score=KeywordScorer(["sql"], []).score)
    assert stored(conn)["fake-1"].score == 1


def test_raw_read_back_identical(conn):
    raw = {"id": 1, "missionTitle": "Data é", "nested": {"list": [1, 2.5, None, True]}}
    save(conn, [offer(1, raw=raw, published_on=None, company=None)])

    first = stored(conn)["fake-1"].offer
    assert first.raw == raw
    assert first.published_on is None and first.company is None


def test_error_rolls_back_everything(conn):
    save(conn, [offer(1)])
    before = list_offers(conn)

    # Two offers with the same reference break UNIQUE (source, reference).
    clash = [offer(2), offer(3, reference="fake-2")]
    with pytest.raises(StorageError, match="Rien n'a été enregistré pour fake.*UNIQUE"):
        save(conn, clash, day=DAY_2)
    assert list_offers(conn) == before
    assert count(conn, "evaluations") == 1
