"""Tests of the run log and of the database backup."""

import sqlite3
from datetime import datetime, timedelta

import pytest

from offers.backups import BACKUPS_KEPT
from offers.storage import database
from offers.storage.database import (
    SaveReport,
    StorageError,
    backup_database,
    connect,
    last_runs,
    list_offers,
    record_run,
)
from tests.factories import make_offer
from tests.test_storage_offers import save

START = datetime(2026, 10, 21, 8, 0)
END = datetime(2026, 10, 21, 8, 2)


@pytest.fixture
def path(tmp_path):
    return tmp_path / "data" / "offers.db"


@pytest.fixture
def conn(path):
    return connect(path)


def test_one_row_per_source(conn):
    record_run(conn, "a", START, END, report=SaveReport(found=5, added=2, relevant=1, removed=1))
    record_run(conn, "b", START, END, error="site en panne")

    runs = last_runs(conn, 10)
    assert [(r.source, r.status) for r in runs] == [("b", "error"), ("a", "ok")]
    assert (runs[1].found, runs[1].added, runs[1].removed) == (5, 2, 1)
    assert runs[1].started_at == START and runs[1].finished_at == END
    assert runs[0].error == "site en panne" and runs[0].found is None


def test_last_runs_most_recent_first(conn):
    for hour in range(5):
        start = START + timedelta(hours=hour)
        record_run(conn, f"s{hour}", start, start, error="x")
    assert [r.source for r in last_runs(conn, 3)] == ["s4", "s3", "s2"]


def test_backup_contains_the_same_offers(conn, path):
    save(conn, [make_offer(), make_offer(source_id="2", reference="REF2")], source="test")

    backup = backup_database(path, START)

    assert backup == path.parent / "backup" / "offers_2026-10-21_0800.db"
    copy = connect(backup)
    assert list_offers(copy) == list_offers(conn)
    assert copy.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_backup_sees_the_wal_content(conn, path):
    """Rows still in the WAL file, not yet in the database file, are in the backup."""
    save(conn, [make_offer()], source="test")
    assert (path.parent / "offers.db-wal").exists()

    backup = backup_database(path, START)
    assert len(list_offers(connect(backup))) == 1


def test_only_the_last_backups_are_kept(conn, path):
    for day in range(BACKUPS_KEPT + 5):
        backup_database(path, START + timedelta(days=day))

    backups = sorted((path.parent / "backup").iterdir())
    assert len(backups) == BACKUPS_KEPT
    assert backups[0].name == "offers_2026-10-26_0800.db"
    assert backups[-1].name == "offers_2026-11-24_0800.db"


def test_no_backup_of_a_missing_database(path):
    assert backup_database(path, START) is None
    assert not path.parent.exists()


def test_backup_error(conn, path, monkeypatch):
    def failing_backup(source, target):
        raise sqlite3.OperationalError("disque plein")

    monkeypatch.setattr(database, "copy_database", failing_backup)
    with pytest.raises(StorageError, match="Impossible de sauvegarder.*disque plein"):
        backup_database(path, START)
    assert list((path.parent / "backup").iterdir()) == []
