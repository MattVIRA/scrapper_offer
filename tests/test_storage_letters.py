"""Tests of the letters table and of the letter field of the follow-up."""

from datetime import datetime
from pathlib import Path

import pytest

from offers.storage import database
from offers.storage.database import (
    StorageError,
    StoredLetter,
    connect,
    hide,
    list_letters,
    load_letter,
    offers_to_write,
    record_letter,
    save_follow_up,
    set_favorite,
    set_letter_status,
)
from tests.test_storage_offers import DAY_2, offer, save, stored

NOW = datetime(2026, 10, 23, 9, 30)
LATER = datetime(2026, 10, 23, 18, 0)


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "offers.db")
    save(conn, [offer(1), offer(2), offer(3)])
    return conn


def offer_id(conn, reference):
    return stored(conn)[reference].id


def letter_rows(conn):
    return conn.execute("SELECT offer_id, path, prompt_version FROM letters").fetchall()


def test_version_3_database_moves_to_version_4_without_loss(tmp_path):
    path = tmp_path / "offers.db"
    conn = connect(path, database.MIGRATIONS[:3])
    save(conn, [offer(1), offer(2)])
    save_follow_up(conn, 1, "applied", "to_write", "2026-10-21", "Note", NOW)
    set_favorite(conn, [2], True, NOW)
    before = {
        table: [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")]
        for table in ("offers", "tracking", "evaluations")
    }
    conn.close()

    conn = connect(path)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 4
    for table, rows in before.items():
        assert [tuple(row) for row in conn.execute(f"SELECT * FROM {table} ORDER BY 1")] == rows
    assert letter_rows(conn) == []
    assert all(s.letter is None for s in stored(conn).values())


def test_record_letter_of_an_offer_without_tracking(conn):
    record_letter(conn, offer_id(conn, "fake-1"), Path("/l/a.docx"), "abcd1234", NOW)

    offer_1 = stored(conn)["fake-1"]
    assert offer_1.letter_status == "written"
    assert offer_1.letter == StoredLetter(offer_1.id, Path("/l/a.docx"), "abcd1234", NOW)
    assert database.load_tracking(conn, offer_1.id)["updated_at"] == NOW.isoformat()


def test_record_letter_keeps_the_rest_of_the_tracking(conn):
    number = offer_id(conn, "fake-1")
    save_follow_up(conn, number, "applied", "to_write", "2026-10-21", "Note", NOW)
    set_favorite(conn, [number], True, NOW)

    record_letter(conn, number, Path("/l/a.docx"), "abcd1234", LATER)

    offer_1 = stored(conn)["fake-1"]
    assert (offer_1.status, offer_1.letter_status, offer_1.applied_on, offer_1.notes) == (
        "applied",
        "written",
        "2026-10-21",
        "Note",
    )
    assert offer_1.favorite


def test_a_new_letter_replaces_the_old_one(conn):
    number = offer_id(conn, "fake-1")
    record_letter(conn, number, Path("/l/a.docx"), "v1", NOW)
    set_letter_status(conn, [number], "to_write", NOW)

    record_letter(conn, number, Path("/l/b.docx"), "v2", LATER)

    assert [tuple(row) for row in letter_rows(conn)] == [(number, "/l/b.docx", "v2")]
    assert load_letter(conn, number) == StoredLetter(number, Path("/l/b.docx"), "v2", LATER)
    assert stored(conn)["fake-1"].letter_status == "written"


def test_record_letter_writes_nothing_on_error(conn):
    with pytest.raises(StorageError, match="Impossible d'enregistrer la lettre"):
        record_letter(conn, 99, Path("/l/a.docx"), "v1", NOW)
    assert letter_rows(conn) == []
    assert conn.execute("SELECT COUNT(*) FROM tracking").fetchone()[0] == 0


def test_offers_to_write_skips_the_trash_and_shows_existing_letters(conn):
    one, two, three = (offer_id(conn, f"fake-{n}") for n in (1, 2, 3))
    set_letter_status(conn, [one, two, three], "to_write", NOW)
    hide(conn, [two], NOW)
    record_letter(conn, three, Path("/l/c.docx"), "v1", NOW)
    set_letter_status(conn, [three], "to_write", LATER)

    to_write = offers_to_write(conn)

    assert [s.offer.reference for s in to_write] == ["fake-1", "fake-3"]
    assert to_write[0].letter is None
    assert to_write[1].letter.path == Path("/l/c.docx")


def test_list_letters_most_recent_first(conn):
    one, two = offer_id(conn, "fake-1"), offer_id(conn, "fake-2")
    record_letter(conn, one, Path("/l/a.docx"), "v1", NOW)
    record_letter(conn, two, Path("/l/b.docx"), "v1", LATER)

    assert [s.offer.reference for s in list_letters(conn)] == ["fake-2", "fake-1"]
    assert load_letter(conn, offer_id(conn, "fake-3")) is None


def test_a_collection_does_not_touch_the_letters(conn):
    number = offer_id(conn, "fake-1")
    record_letter(conn, number, Path("/l/a.docx"), "v1", NOW)

    # fake-1 goes offline, fake-2 is seen again.
    save(conn, [offer(2), offer(4)], day=DAY_2)

    offer_1 = stored(conn)["fake-1"]
    assert not offer_1.online
    assert offer_1.letter == StoredLetter(number, Path("/l/a.docx"), "v1", NOW)
    assert offer_1.letter_status == "written"
