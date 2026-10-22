"""Tests of the detection of probable duplicates."""

from datetime import datetime

import pytest

from offers import __main__ as cli
from offers.storage.database import connect, list_offers, probable_duplicates
from tests.test_storage_offers import offer, save


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "offers.db")


def references(groups):
    return [[s.offer.reference for s in group] for group in groups]


def test_same_title_apart_from_case_accents_and_punctuation(conn):
    save(
        conn,
        [
            offer(1, title="Ingénieur Data (H/F)", company="ACME France"),
            offer(2, title="INGENIEUR  DATA - H/F", company="Acme  france"),
            offer(3, title="Comptable", company="ACME France"),
        ],
    )
    save(conn, [offer(1, "other", title="ingenieur data h f", company="acme-france")],
         source="other")  # fmt: skip

    assert references(probable_duplicates(conn)) == [["fake-1", "fake-2", "other-1"]]


def test_same_title_other_company_is_not_a_duplicate(conn):
    save(conn, [offer(1, title="Data", company="ACME"), offer(2, title="Data", company="Globex")])
    assert probable_duplicates(conn) == []


def test_offline_offer_is_ignored(conn):
    same = [offer(1, title="Data"), offer(2, title="Data")]
    save(conn, same)
    assert len(probable_duplicates(conn)) == 1
    save(conn, same[1:], day=datetime(2026, 10, 21))
    assert probable_duplicates(conn) == []


def test_empty_company_is_ignored(conn):
    save(conn, [offer(1, title="Data", company=None), offer(2, title="Data", company=" ")])
    assert probable_duplicates(conn) == []


def test_groups_sorted_by_company_and_nothing_modified(conn):
    save(
        conn,
        [
            offer(1, title="Data", company="Zeta"),
            offer(2, title="Data", company="Zeta"),
            offer(3, title="Data", company="Alpha"),
            offer(4, title="Data", company="alpha"),
        ],
    )
    before = list_offers(conn)
    assert references(probable_duplicates(conn)) == [["fake-3", "fake-4"], ["fake-1", "fake-2"]]
    assert list_offers(conn) == before


def test_duplicates_command(capsys, tmp_path):
    db = tmp_path / "offers.db"
    conn = connect(db)
    save(conn, [offer(1, title="Data", company="ACME"), offer(2, title="Data", company="ACME")])
    conn.close()

    assert cli.main(["duplicates", "--db", str(db)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "ACME — Data (2 offres)",
        "  fake-1 | fake | Data | ACME | vue le 20/10/2026",
        "  fake-2 | fake | Data | ACME | vue le 20/10/2026",
    ]


def test_duplicates_command_without_duplicates(capsys, tmp_path):
    db = tmp_path / "offers.db"
    connect(db).close()
    assert cli.main(["duplicates", "--db", str(db)]) == 0
    assert capsys.readouterr().out == "Aucun doublon probable.\n"
