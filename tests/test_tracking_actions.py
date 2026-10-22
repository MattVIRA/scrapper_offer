"""Tests of the follow-up written by the interface: status, letter, favorite, read, trash."""

from datetime import date, datetime

import pytest

from offers.storage import database
from offers.storage.database import (
    StorageError,
    connect,
    hide,
    mark_read,
    restore,
    save_tracking_details,
    set_favorite,
    set_letter_status,
    set_status,
)
from tests.test_storage_offers import DAY_2, offer, save, stored

NOW = datetime(2026, 10, 22, 9, 30)
LATER = datetime(2026, 10, 23, 18, 0)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "offers.db")
    save(conn, [offer(1), offer(2), offer(3)])
    return conn


def ids(conn, *references):
    offers = stored(conn)
    return [offers[reference].id for reference in references]


def tracking_row(conn, reference):
    return database.load_tracking(conn, ids(conn, reference)[0])


def test_new_offer_has_no_follow_up(conn):
    first = stored(conn)["fake-1"]
    assert first.status is None and first.letter_status is None
    assert not first.favorite and not first.hidden
    assert first.read_at is None


def test_set_status_on_several_offers(conn):
    set_status(conn, ids(conn, "fake-1", "fake-2"), "applied", NOW)

    offers = stored(conn)
    assert [offers[r].status for r in ("fake-1", "fake-2", "fake-3")] == [
        "applied",
        "applied",
        None,
    ]
    assert tracking_row(conn, "fake-1")["updated_at"] == "2026-10-22T09:30:00"


def test_set_status_keeps_the_rest_of_the_follow_up(conn):
    first = ids(conn, "fake-1")
    save_tracking_details(conn, first[0], date(2026, 10, 21), "Relancer", NOW)
    set_favorite(conn, first, True, NOW)

    set_status(conn, first, "rejected", LATER)
    set_status(conn, first, None, LATER)

    result = stored(conn)["fake-1"]
    assert result.status is None
    assert (result.applied_on, result.notes, result.favorite) == ("2026-10-21", "Relancer", True)


def test_unknown_status_is_refused(conn):
    with pytest.raises(ValueError, match="to_write"):
        set_status(conn, ids(conn, "fake-1"), "to_write", NOW)
    assert tracking_row(conn, "fake-1") is None


def test_set_letter_status(conn):
    set_letter_status(conn, ids(conn, "fake-1", "fake-3"), "to_write", NOW)
    set_letter_status(conn, ids(conn, "fake-3"), "written", NOW)

    offers = stored(conn)
    assert [offers[r].letter_status for r in ("fake-1", "fake-2", "fake-3")] == [
        "to_write",
        None,
        "written",
    ]
    set_letter_status(conn, ids(conn, "fake-1"), None, NOW)
    assert stored(conn)["fake-1"].letter_status is None


def test_unknown_letter_status_is_refused(conn):
    with pytest.raises(ValueError):
        set_letter_status(conn, ids(conn, "fake-1"), "letter_ready", NOW)


def test_set_favorite(conn):
    set_favorite(conn, ids(conn, "fake-1", "fake-2"), True, NOW)
    set_favorite(conn, ids(conn, "fake-2"), False, NOW)

    offers = stored(conn)
    assert [offers[r].favorite for r in ("fake-1", "fake-2", "fake-3")] == [True, False, False]


def test_mark_read_keeps_the_first_reading(conn):
    mark_read(conn, ids(conn, "fake-1"), NOW)
    mark_read(conn, ids(conn, "fake-1", "fake-2"), LATER)

    offers = stored(conn)
    assert offers["fake-1"].read_at == NOW
    assert offers["fake-2"].read_at == LATER
    assert offers["fake-3"].read_at is None
    # Nothing changed for the offer already read.
    assert tracking_row(conn, "fake-1")["updated_at"] == "2026-10-22T09:30:00"


def test_hide_and_restore(conn):
    hide(conn, ids(conn, "fake-1", "fake-2"), NOW)
    assert [s.hidden for s in stored(conn).values()] == [True, True, False]

    restore(conn, ids(conn, "fake-2"), LATER)
    assert [s.hidden for s in stored(conn).values()] == [True, False, False]
    # Hidden, never deleted.
    assert database.count_offers(conn) == 3


def test_save_tracking_details(conn):
    first = ids(conn, "fake-1")[0]
    save_tracking_details(conn, first, date(2026, 10, 21), "Entretien jeudi", NOW)
    result = stored(conn)["fake-1"]
    assert (result.applied_on, result.notes) == ("2026-10-21", "Entretien jeudi")

    save_tracking_details(conn, first, None, "", LATER)
    result = stored(conn)["fake-1"]
    assert (result.applied_on, result.notes) == (None, None)


def test_group_action_writes_all_offers_or_none(conn):
    with pytest.raises(StorageError, match="rien n'a été modifié"):
        set_favorite(conn, [*ids(conn, "fake-1"), 999], True, NOW)
    assert tracking_row(conn, "fake-1") is None


def test_collect_does_not_touch_the_follow_up(conn):
    first, second = ids(conn, "fake-1", "fake-2")
    set_favorite(conn, [first], True, NOW)
    mark_read(conn, [first], NOW)
    set_letter_status(conn, [first], "to_write", NOW)
    hide(conn, [second], NOW)
    before = [dict(tracking_row(conn, r)) for r in ("fake-1", "fake-2")]

    # The source still returns both offers.
    save(conn, [offer(1), offer(2), offer(3)], day=DAY_2)

    assert [dict(tracking_row(conn, r)) for r in ("fake-1", "fake-2")] == before
    offers = stored(conn)
    assert offers["fake-2"].hidden
    assert offers["fake-1"].favorite and offers["fake-1"].read_at == NOW
    assert offers["fake-1"].last_seen == DAY_2
