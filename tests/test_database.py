"""Tests of the database creation and migrations."""

import pytest

from offers.storage import database
from offers.storage.database import StorageError, connect

TABLES = {"offers", "tracking", "evaluations", "runs"}


def tables(conn):
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    return {row["name"] for row in rows}


def version(conn):
    return conn.execute("PRAGMA user_version").fetchone()[0]


@pytest.fixture
def path(tmp_path):
    return tmp_path / "data" / "offers.db"


def test_creation(path):
    conn = connect(path)
    assert path.exists()
    assert tables(conn) == TABLES
    assert version(conn) == len(database.MIGRATIONS)


def test_wal_and_foreign_keys(path):
    conn = connect(path)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(database.sqlite3.IntegrityError):
        conn.execute("INSERT INTO tracking (offer_id, updated_at) VALUES (42, 'now')")


def test_reopening_keeps_the_data(path):
    conn = connect(path)
    conn.execute(
        "INSERT INTO runs (started_at, finished_at, source, status) VALUES ('a', 'b', 's', 'ok')"
    )
    conn.close()

    conn = connect(path)
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert version(conn) == len(database.MIGRATIONS)


def test_added_migration_is_applied_once(path):
    connect(path).close()
    migrations = [*database.MIGRATIONS, "CREATE TABLE letters (id INTEGER PRIMARY KEY);"]

    conn = connect(path, migrations)
    assert tables(conn) == TABLES | {"letters"}
    assert version(conn) == len(migrations)
    conn.close()

    # Applied a second time, CREATE TABLE would fail.
    conn = connect(path, migrations)
    assert version(conn) == len(migrations)


def test_failing_migration_is_rolled_back(path):
    connect(path).close()
    migrations = [*database.MIGRATIONS, "CREATE TABLE letters (id INTEGER);\nNOT SQL;"]

    with pytest.raises(StorageError, match="Impossible d'utiliser la base"):
        connect(path, migrations)
    conn = connect(path)
    assert "letters" not in tables(conn)
    assert version(conn) == len(database.MIGRATIONS)


def test_version_1_database_moves_to_version_2_without_loss(path):
    conn = connect(path, database.MIGRATIONS[:1])
    for number, status in enumerate(["to_write", "letter_ready", "applied", None], 1):
        conn.execute(
            "INSERT INTO offers (source, source_id, reference, title, url, first_seen, "
            "last_seen) VALUES ('fake', ?, ?, 'Data', 'https://example.com', 'a', 'b')",
            (str(number), f"F{number}"),
        )
        conn.execute(
            "INSERT INTO tracking (offer_id, status, applied_on, notes, updated_at) "
            "VALUES (?, ?, '2026-10-21', ?, 'avant')",
            (number, status, f"Note {number}"),
        )
    conn.close()

    conn = connect(path)
    assert version(conn) == 2
    assert conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 4
    rows = conn.execute(
        "SELECT offer_id, status, letter_status, applied_on, notes, updated_at, favorite, "
        "read_at, hidden FROM tracking ORDER BY offer_id"
    ).fetchall()
    assert [tuple(row) for row in rows] == [
        (1, "interesting", "to_write", "2026-10-21", "Note 1", "avant", 0, None, 0),
        (2, "interesting", "written", "2026-10-21", "Note 2", "avant", 0, None, 0),
        (3, "applied", None, "2026-10-21", "Note 3", "avant", 0, None, 0),
        (4, None, None, "2026-10-21", "Note 4", "avant", 0, None, 0),
    ]


def test_unreadable_file(path):
    path.parent.mkdir()
    path.write_text("pas une base de données " * 100)
    with pytest.raises(StorageError, match="Impossible d'utiliser la base") as info:
        connect(path)
    assert isinstance(info.value.__cause__, database.sqlite3.DatabaseError)


def test_transaction_rolls_back_on_error(path):
    conn = connect(path)
    with pytest.raises(ValueError):
        with database.transaction(conn, "Erreur"):
            conn.execute(
                "INSERT INTO runs (started_at, finished_at, source, status) "
                "VALUES ('a', 'b', 's', 'ok')"
            )
            raise ValueError("boom")
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 0


def test_transaction_translates_sqlite_errors(path):
    conn = connect(path)
    with pytest.raises(StorageError, match="Écriture impossible : no such table") as info:
        with database.transaction(conn, "Écriture impossible"):
            conn.execute("INSERT INTO missing_table VALUES (1)")
    assert isinstance(info.value.__cause__, database.sqlite3.OperationalError)
    assert not conn.in_transaction
