"""Access to the SQLite database: the only module that talks to it."""

import json
import os
import re
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from importlib.resources import files
from pathlib import Path

from offers.errors import OffersError
from offers.model import Offer
from offers.scoring.keywords import normalize
from offers.tracking import LETTER_STATUSES, STATUSES

STORAGE_FILES = files("offers.storage")
# Schema changes, applied in order. The schema version stored in
# PRAGMA user_version is the number of migrations already applied: never
# change or remove one, add a new one at the end.
MIGRATIONS = [
    STORAGE_FILES.joinpath("schema.sql").read_text(encoding="utf-8"),
    STORAGE_FILES.joinpath("migrations", "002_tracking_ui.sql").read_text(encoding="utf-8"),
]


KEYWORDS_METHOD = "keywords"
BACKUP_DIR = "backup"
BACKUP_PREFIX = "offers_"
BACKUPS_KEPT = 30
# Spaces and punctuation, ignored when comparing titles and companies.
SEPARATORS = re.compile(r"[\W_]+")
# Offer fields stored in their own column of the offers table.
OFFER_COLUMNS = [
    "source", "source_id", "reference", "title", "company", "country", "city",
    "contract_type", "duration_months", "published_on", "url", "description",
    "candidate_profile",
]  # fmt: skip


class StorageError(OffersError):
    """Problem with the database."""


@dataclass(frozen=True)
class SaveReport:
    """What saving the result of a source changed."""

    found: int
    added: int
    # Added offers with a keyword score above 0.
    relevant: int
    # Offers that went from online to offline.
    removed: int


@dataclass(frozen=True)
class StoredOffer:
    """An offer as stored, with its follow-up and its keyword score."""

    id: int
    offer: Offer
    search_name: str | None
    first_seen: datetime
    last_seen: datetime
    online: bool
    score: int | None
    words: str | None
    status: str | None
    applied_on: str | None
    notes: str | None
    letter_status: str | None
    favorite: bool
    # None: the offer was never opened.
    read_at: datetime | None
    # In the trash.
    hidden: bool


@dataclass(frozen=True)
class Run:
    """The run of one source."""

    started_at: datetime
    finished_at: datetime
    source: str
    status: str
    found: int | None
    added: int | None
    removed: int | None
    error: str | None


@contextmanager
def transaction(conn, error_message):
    """Run the block in a transaction: all of it is written, or nothing.

    A SQLite error becomes a StorageError: "<error_message> : <error>".
    """
    try:
        conn.execute("BEGIN")
        try:
            yield conn
        except BaseException:
            conn.rollback()
            raise
        conn.commit()
    except sqlite3.Error as err:
        raise StorageError(f"{error_message} : {err}") from err


def connect(path, migrations=MIGRATIONS):
    """Open the database, creating it and applying the migrations if needed."""
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # Transactions are opened explicitly, with transaction().
        conn = sqlite3.connect(path, isolation_level=None)
    except (OSError, sqlite3.Error) as err:
        raise StorageError(f"Impossible d'ouvrir la base {path} : {err}") from err
    conn.row_factory = sqlite3.Row
    try:
        # WAL: the interface can read while a collection writes.
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA foreign_keys = ON")
        apply_migrations(conn, migrations)
    except sqlite3.Error as err:
        conn.close()
        raise StorageError(
            f"Impossible d'utiliser la base {path} : {err}. "
            "Vérifie que c'est bien la base des offres, ou restaure une sauvegarde."
        ) from err
    return conn


def apply_migrations(conn, migrations):
    """Apply the migrations not applied yet, each in its own transaction."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for number, script in enumerate(migrations[version:], version + 1):
        # executescript() cannot run inside transaction(): the script opens
        # and commits its own.
        try:
            conn.executescript(f"BEGIN;\n{script}\nPRAGMA user_version = {number};\nCOMMIT;")
        except sqlite3.Error:
            if conn.in_transaction:
                conn.rollback()
            raise


def save_source_result(conn, source_name, found, online, score, now):
    """Save what a source returned, in a single transaction.

    found: FoundOffer list; only these offers can be added.
    online: all offers online on the source, or None if it cannot tell.
        If given, the offers of this source missing from it go offline.
    score: function that returns (score, found words) for an Offer.
    """
    found_offers = first_search_of_each_offer(found)
    seen = {offer.source_id: offer for offer in online or []}
    seen.update({offer.source_id: offer for offer, _ in found_offers.values()})
    error_message = f"Rien n'a été enregistré pour {source_name} : impossible d'écrire dans la base"
    with transaction(conn, error_message):
        known = known_offer_ids(conn, source_name)
        added = relevant = 0
        for source_id, offer in seen.items():
            if source_id in known:
                offer_id = update_offer(conn, known[source_id], offer, now)
            elif source_id in found_offers:
                offer_id = insert_offer(conn, offer, found_offers[source_id][1], now)
                added += 1
            else:
                # Only the offers of the searches enter the database.
                continue
            offer_score, words = score(offer)
            save_keyword_score(conn, offer_id, offer_score, words, now)
            if source_id not in known and offer_score > 0:
                relevant += 1
        removed = 0 if online is None else mark_offline(conn, source_name, set(seen))
    return SaveReport(found=len(found_offers), added=added, relevant=relevant, removed=removed)


def first_search_of_each_offer(found):
    """Return {source_id: (offer, name of the first search that found it)}."""
    result = {}
    for item in found:
        result.setdefault(item.offer.source_id, (item.offer, item.search_name))
    return result


def known_offer_ids(conn, source_name):
    """Return {source_id: id} of the offers of a source already stored."""
    rows = conn.execute("SELECT id, source_id FROM offers WHERE source = ?", (source_name,))
    return {row["source_id"]: row["id"] for row in rows}


def offer_values(offer):
    """Return the values of the OFFER_COLUMNS, then raw, ready for SQLite."""
    values = [getattr(offer, column) for column in OFFER_COLUMNS]
    published_on = OFFER_COLUMNS.index("published_on")
    values[published_on] = to_text(values[published_on])
    return [*values, json.dumps(offer.raw, ensure_ascii=False)]


def insert_offer(conn, offer, search_name, now):
    """Add an offer, seen online now; return its id."""
    columns = [*OFFER_COLUMNS, "raw", "search_name", "first_seen", "last_seen", "online"]
    values = [*offer_values(offer), search_name, to_text(now), to_text(now), 1]
    cursor = conn.execute(
        f"INSERT INTO offers ({', '.join(columns)}) VALUES ({', '.join('?' * len(columns))})",
        values,
    )
    return cursor.lastrowid


def update_offer(conn, offer_id, offer, now):
    """Refresh an offer seen online; first_seen and search_name do not change."""
    columns = [*OFFER_COLUMNS, "raw", "last_seen", "online"]
    assignments = ", ".join(f"{column} = ?" for column in columns)
    conn.execute(
        f"UPDATE offers SET {assignments} WHERE id = ?",
        [*offer_values(offer), to_text(now), 1, offer_id],
    )
    return offer_id


def save_keyword_score(conn, offer_id, score, words, now):
    """Write the keyword score of an offer, replacing the previous one."""
    conn.execute(
        "INSERT INTO evaluations (offer_id, method, score, justification, created_at) "
        "VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (offer_id, method) DO UPDATE SET "
        "score = excluded.score, justification = excluded.justification, "
        "created_at = excluded.created_at",
        (offer_id, KEYWORDS_METHOD, score, words, to_text(now)),
    )


def mark_offline(conn, source_name, online_ids):
    """Mark offline the online offers of a source missing from online_ids.

    Return how many went offline.
    """
    removed = 0
    for source_id, offer_id in known_offer_ids(conn, source_name).items():
        if source_id in online_ids:
            continue
        cursor = conn.execute(
            "UPDATE offers SET online = 0 WHERE id = ? AND online = 1", (offer_id,)
        )
        removed += cursor.rowcount
    return removed


def load_tracking(conn, offer_id):
    """Return the tracking row of an offer, or None."""
    return conn.execute("SELECT * FROM tracking WHERE offer_id = ?", (offer_id,)).fetchone()


def set_status(conn, offer_ids, status, now):
    """Set the status of the offers; None removes it."""
    check_code(status, STATUSES)
    update_tracking(conn, offer_ids, {"status": status}, now)


def set_letter_status(conn, offer_ids, letter_status, now):
    """Set the letter status of the offers; None means no letter."""
    check_code(letter_status, LETTER_STATUSES)
    update_tracking(conn, offer_ids, {"letter_status": letter_status}, now)


def set_favorite(conn, offer_ids, favorite, now):
    """Add the offers to the favorites, or remove them."""
    update_tracking(conn, offer_ids, {"favorite": int(favorite)}, now)


def mark_read(conn, offer_ids, now):
    """Mark the offers as read; an offer already read keeps its read_at."""
    update_tracking(conn, offer_ids, {"read_at": to_text(now)}, now, only_if="read_at IS NULL")


def hide(conn, offer_ids, now):
    """Put the offers in the trash; they are never deleted."""
    update_tracking(conn, offer_ids, {"hidden": 1}, now)


def restore(conn, offer_ids, now):
    """Take the offers out of the trash."""
    update_tracking(conn, offer_ids, {"hidden": 0}, now)


def save_tracking_details(conn, offer_id, applied_on, notes, now):
    """Write the application date and the notes of an offer.

    applied_on: date, or None. Empty notes are stored as None.
    """
    update_tracking(
        conn, [offer_id], {"applied_on": to_text(applied_on), "notes": notes or None}, now
    )


def check_code(code, codes):
    """Refuse a code that is neither None nor one of codes."""
    if code is not None and code not in codes:
        raise ValueError(f"Code inconnu : {code!r} (attendu : {', '.join(codes)} ou None)")


def update_tracking(conn, offer_ids, fields, now, only_if=None):
    """Write fields ({column: value}) in the tracking of the offers.

    Create the missing tracking rows; all offers are written, or none.
    only_if: SQL condition; rows that do not meet it are left unchanged.
    """
    values = {**fields, "updated_at": to_text(now)}
    assignments = ", ".join(f"{column} = ?" for column in values)
    condition = f" AND {only_if}" if only_if else ""
    with transaction(conn, "Impossible d'enregistrer le suivi, rien n'a été modifié"):
        for offer_id in offer_ids:
            conn.execute(
                "INSERT INTO tracking (offer_id, updated_at) VALUES (?, ?) "
                "ON CONFLICT (offer_id) DO NOTHING",
                (offer_id, to_text(now)),
            )
            conn.execute(
                f"UPDATE tracking SET {assignments} WHERE offer_id = ?{condition}",
                [*values.values(), offer_id],
            )


def count_offers(conn):
    """Return the number of stored offers."""
    try:
        return conn.execute("SELECT COUNT(*) FROM offers").fetchone()[0]
    except sqlite3.Error as err:
        raise StorageError(f"Impossible de lire les offres de la base : {err}") from err


def load_offer(row):
    """Return the Offer of a row of the offers table."""
    values = {column: row[column] for column in OFFER_COLUMNS}
    if values["published_on"]:
        values["published_on"] = date.fromisoformat(values["published_on"])
    return Offer(**values, raw=json.loads(row["raw"]))


def list_offers(conn):
    """Return all offers as StoredOffer, by first_seen then id."""
    try:
        rows = conn.execute(
            "SELECT o.*, t.status, t.applied_on, t.notes, t.letter_status, t.favorite, "
            "t.read_at, t.hidden, "
            "e.score, e.justification AS words "
            "FROM offers o "
            "LEFT JOIN tracking t ON t.offer_id = o.id "
            "LEFT JOIN evaluations e ON e.offer_id = o.id AND e.method = ? "
            "ORDER BY o.first_seen, o.id",
            (KEYWORDS_METHOD,),
        ).fetchall()
    except sqlite3.Error as err:
        raise StorageError(f"Impossible de lire les offres de la base : {err}") from err
    return [stored_offer(row) for row in rows]


def stored_offer(row):
    """Return the StoredOffer of a row of list_offers."""
    return StoredOffer(
        id=row["id"],
        offer=load_offer(row),
        search_name=row["search_name"],
        first_seen=datetime.fromisoformat(row["first_seen"]),
        last_seen=datetime.fromisoformat(row["last_seen"]),
        online=bool(row["online"]),
        score=row["score"],
        words=row["words"],
        status=row["status"],
        applied_on=row["applied_on"],
        notes=row["notes"],
        letter_status=row["letter_status"],
        # No tracking row: not a favorite, not read, not hidden.
        favorite=bool(row["favorite"]),
        read_at=datetime.fromisoformat(row["read_at"]) if row["read_at"] else None,
        hidden=bool(row["hidden"]),
    )


def to_text(value):
    """Return a date or datetime as ISO text, as stored in the database."""
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    return value


def record_run(conn, source, started_at, finished_at, report=None, error=None):
    """Log the run of a source: its SaveReport if it worked, else its error."""
    values = (
        to_text(started_at),
        to_text(finished_at),
        source,
        "error" if error else "ok",
        report.found if report else None,
        report.added if report else None,
        report.removed if report else None,
        error,
    )
    try:
        conn.execute(
            "INSERT INTO runs (started_at, finished_at, source, status, found, added, "
            "removed, error) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            values,
        )
    except sqlite3.Error as err:
        raise StorageError(f"Impossible d'enregistrer le lancement de {source} : {err}") from err


def last_runs(conn, limit):
    """Return the last runs, most recent first."""
    try:
        rows = conn.execute(
            "SELECT * FROM runs ORDER BY started_at DESC, id DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.Error as err:
        raise StorageError(f"Impossible de lire le journal des lancements : {err}") from err
    return [
        Run(
            started_at=datetime.fromisoformat(row["started_at"]),
            finished_at=datetime.fromisoformat(row["finished_at"]),
            source=row["source"],
            status=row["status"],
            found=row["found"],
            added=row["added"],
            removed=row["removed"],
            error=row["error"],
        )
        for row in rows
    ]


def backup_database(path, now):
    """Copy the database into the "backup" folder next to it; keep the last ones.

    Use the SQLite backup API: a plain file copy can miss what is still in
    the WAL file. Do nothing if the database does not exist yet.
    Return the path of the backup, or None.
    """
    path = Path(path)
    if not path.exists():
        return None
    backup_dir = path.parent / BACKUP_DIR
    target = backup_dir / f"{BACKUP_PREFIX}{now.strftime('%Y-%m-%d_%H%M')}.db"
    temporary = target.with_name(target.name + ".tmp")
    try:
        backup_dir.mkdir(exist_ok=True)
        copy_database(path, temporary)
        os.replace(temporary, target)
        remove_old_backups(backup_dir)
    except (OSError, sqlite3.Error) as err:
        temporary.unlink(missing_ok=True)
        raise StorageError(
            f"Impossible de sauvegarder la base {path} dans {backup_dir} : {err}. "
            "Rien n'a été modifié."
        ) from err
    return target


def copy_database(source_path, target_path):
    """Copy a database with the SQLite backup API."""
    source = sqlite3.connect(source_path)
    try:
        target = sqlite3.connect(target_path)
        try:
            source.backup(target)
        finally:
            target.close()
    finally:
        source.close()


def remove_old_backups(backup_dir):
    """Delete the oldest backups, keeping BACKUPS_KEPT."""
    # The date in the name sorts the backups from the oldest.
    backups = sorted(backup_dir.glob(f"{BACKUP_PREFIX}*.db"))
    for old in backups[:-BACKUPS_KEPT]:
        old.unlink()


def probable_duplicates(conn):
    """Return the groups of online offers with the same company and title.

    Company and title are compared without case, accents, punctuation or
    extra spaces. Offers without a company are ignored. Nothing is merged:
    the groups are only shown to the user. Groups are sorted by company.
    """
    groups = {}
    for stored in list_offers(conn):
        company = duplicate_key(stored.offer.company)
        if stored.online and company:
            groups.setdefault((company, duplicate_key(stored.offer.title)), []).append(stored)
    return [group for key, group in sorted(groups.items()) if len(group) > 1]


def duplicate_key(text):
    """Return a text reduced for comparison: "Data-Analyst  (H/F)" -> "data analyst h f"."""
    return SEPARATORS.sub(" ", normalize(text or "")).strip()
