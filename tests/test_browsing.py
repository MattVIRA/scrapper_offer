"""Tests of the filters, counters, markers and duplicates of the offer lists."""

from dataclasses import replace
from datetime import date, datetime

import pytest

from offers import browsing
from offers.browsing import OfferFilter, counters, duplicate_tags, filter_offers, marker
from tests.factories import make_offer, make_stored

ALL_STATUSES = frozenset({None, *browsing.STATUSES})
# Shows every offer: a starting point for testing one filter at a time.
SHOW_ALL = OfferFilter(statuses=ALL_STATUSES, online=browsing.ALL)


def stored(id, **changes):
    # Neutral title: only offer 1 is about data.
    offer_fields = {"title": "Poste"}
    offer_fields.update(
        {
            key: changes.pop(key)
            for key in ("source", "country", "title", "company")
            if key in changes
        }
    )
    offer = make_offer(source_id=str(id), reference=f"REF{id}", **offer_fields)
    return make_stored(id, offer, **changes)


def ids(offers):
    return [s.id for s in offers]


@pytest.fixture
def offers():
    return [
        stored(1, source="business_france", country="ALLEMAGNE", title="Data Analyst", score=3),
        stored(2, source="business_france", country="ESPAGNE", title="Comptable",
               status="rejected"),
        stored(3, source="other", country="ALLEMAGNE", company="Société Générale", score=1,
               online=False),
        stored(4, status="not_for_me", score=5, favorite=True),
        stored(5, hidden=True, letter_status="to_write"),
        stored(6, status="applied", letter_status="written", favorite=True,
               first_seen=datetime(2026, 10, 22, 8, 0), read_at=datetime(2026, 10, 22, 9, 0)),
    ]  # fmt: skip


# --- Filters ------------------------------------------------------------------


def test_default_filter(offers):
    # Online, not "Pas pour moi", not in the trash.
    assert ids(filter_offers(offers, OfferFilter())) == [1, 2, 6]


def test_show_all_keeps_the_trash_apart(offers):
    assert ids(filter_offers(offers, SHOW_ALL)) == [1, 2, 3, 4, 6]


def test_trash(offers):
    assert ids(filter_offers(offers, replace(SHOW_ALL, in_trash=True))) == [5]


def test_sources(offers):
    assert ids(filter_offers(offers, replace(SHOW_ALL, sources=frozenset({"other"})))) == [3]


def test_countries(offers):
    chosen = replace(SHOW_ALL, countries=frozenset({"ALLEMAGNE"}))
    assert ids(filter_offers(offers, chosen)) == [1, 3]


@pytest.mark.parametrize(
    "statuses, expected",
    [
        (frozenset({None}), [1, 3]),
        (frozenset({"applied", "rejected"}), [2, 6]),
        (frozenset(), []),
    ],
)
def test_statuses(offers, statuses, expected):
    assert ids(filter_offers(offers, replace(SHOW_ALL, statuses=statuses))) == expected


@pytest.mark.parametrize(
    "letters, expected",
    [
        (frozenset({None}), [1, 2, 3, 4]),
        (frozenset({"written"}), [6]),
        (frozenset({"to_write"}), []),
    ],
)
def test_letters(offers, letters, expected):
    assert ids(filter_offers(offers, replace(SHOW_ALL, letter_statuses=letters))) == expected


def test_min_score_counts_no_score_as_zero(offers):
    assert ids(filter_offers(offers, replace(SHOW_ALL, min_score=2))) == [1, 4]
    assert ids(filter_offers(offers, replace(SHOW_ALL, min_score=0))) == [1, 2, 3, 4, 6]


@pytest.mark.parametrize(
    "online, expected",
    [(browsing.ONLINE, [1, 2, 4, 6]), (browsing.OFFLINE, [3]), (browsing.ALL, [1, 2, 3, 4, 6])],
)
def test_online(offers, online, expected):
    assert ids(filter_offers(offers, replace(SHOW_ALL, online=online))) == expected


def test_added_since(offers):
    chosen = replace(SHOW_ALL, added_since=date(2026, 10, 22))
    assert ids(filter_offers(offers, chosen)) == [6]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("data", [1]),
        ("  ANALYST ", [1]),
        ("societe generale", [3]),  # company, without accents
        ("générale", [3]),
        ("acme", [1, 2, 4, 6]),  # default company of make_offer
        ("", [1, 2, 3, 4, 6]),
        ("introuvable", []),
    ],
)
def test_text(offers, text, expected):
    assert ids(filter_offers(offers, replace(SHOW_ALL, text=text))) == expected


def test_favorites_only(offers):
    assert ids(filter_offers(offers, replace(SHOW_ALL, favorites_only=True))) == [4, 6]


def test_combined_filters(offers):
    chosen = OfferFilter(
        countries=frozenset({"ALLEMAGNE"}),
        online=browsing.ALL,
        min_score=1,
        text="data",
    )
    assert ids(filter_offers(offers, chosen)) == [1]
    assert ids(filter_offers(offers, replace(chosen, text=""))) == [1, 3]


def test_order_is_kept(offers):
    assert ids(filter_offers(list(reversed(offers)), OfferFilter())) == [6, 2, 1]


# --- Counters -----------------------------------------------------------------


def test_counters(offers):
    result = counters(offers)
    assert result.total == 6
    assert result.unread == 5
    assert result.by_status == {None: 3, "rejected": 1, "not_for_me": 1, "applied": 1}
    assert result.letters_to_write == 1


def test_counters_of_no_offer():
    assert counters([]) == browsing.Counters(total=0, unread=0, by_status={}, letters_to_write=0)


# --- Markers ------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({}, browsing.NO_MARKER),
        ({"status": "rejected"}, browsing.MARKER_REJECTED),
        ({"status": "applied"}, browsing.MARKER_APPLIED),
        ({"favorite": True}, browsing.MARKER_FAVORITE),
        ({"online": False}, browsing.MARKER_OFFLINE),
        # Yellow never before red or blue.
        ({"status": "rejected", "favorite": True}, browsing.MARKER_REJECTED),
        ({"status": "applied", "favorite": True}, browsing.MARKER_APPLIED),
        # An offline offer keeps its color.
        ({"status": "rejected", "online": False}, browsing.MARKER_REJECTED),
        ({"favorite": True, "online": False}, browsing.MARKER_FAVORITE),
        ({"status": "interesting"}, browsing.NO_MARKER),
    ],
)
def test_marker(changes, expected):
    assert marker(make_stored(**changes)) == expected


@pytest.mark.parametrize(
    "changes, expected",
    [
        ({"favorite": True}, browsing.NO_MARKER),
        ({"favorite": True, "online": False}, browsing.MARKER_OFFLINE),
        ({"favorite": True, "status": "applied"}, browsing.MARKER_APPLIED),
    ],
)
def test_no_yellow_on_the_favorites_page(changes, expected):
    assert marker(make_stored(**changes), on_favorites_page=True) == expected


def test_markers_are_distinct():
    markers = [
        browsing.MARKER_REJECTED,
        browsing.MARKER_APPLIED,
        browsing.MARKER_FAVORITE,
        browsing.MARKER_OFFLINE,
        browsing.NO_MARKER,
    ]
    assert len(set(markers)) == len(markers)


def test_unread():
    assert browsing.is_unread(make_stored())
    assert not browsing.is_unread(make_stored(read_at=datetime(2026, 10, 22, 9, 0)))


# --- Duplicates and choices ---------------------------------------------------


def test_duplicate_tags():
    first, second, third = make_stored(1), make_stored(2), make_stored(3)
    other_pair = [make_stored(7), make_stored(8)]

    tags = duplicate_tags([[first, second, third], other_pair])

    assert tags == {
        1: ["REF2", "REF3"],
        2: ["REF1", "REF3"],
        3: ["REF1", "REF2"],
        7: ["REF8"],
        8: ["REF7"],
    }
    assert duplicate_tags([]) == {}


def test_filter_choices(offers):
    offers.append(stored(9, country=None))
    choices = browsing.filter_choices(offers)
    assert choices.sources == ["business_france", "other", "test"]
    assert choices.countries == ["ALLEMAGNE", "ESPAGNE", "FRANCE"]
