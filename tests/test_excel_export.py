"""Tests of the Excel export (offers.exports.excel), from a database filled
by save_source_result.

To regenerate the snapshot after a wanted change:
    UPDATE_SNAPSHOT=1 pytest tests/test_excel_export.py
"""

import json
import os
from datetime import date, datetime, time

import pytest
from openpyxl import load_workbook

from offers.exports import excel
from offers.scoring.keywords import KeywordScorer
from offers.sources.base import FoundOffer
from offers.sources.business_france import to_offer
from offers.storage.database import (
    connect,
    hide,
    list_offers,
    save_source_result,
    save_tracking_details,
    set_favorite,
    set_letter_status,
    set_status,
)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SNAPSHOT_PATH = os.path.join(FIXTURES, "excel_expected.json")
DAY_1 = date(2026, 10, 20)
DAY_2 = date(2026, 10, 21)
DAY_3 = date(2026, 10, 22)
SEARCH = "Recherche principale"
WORDS_DAY_1 = ["python", "data", "ia", "sql", "food"]
WORDS_DAY_2 = ["python", "data", "ia", "sql", "food", "marketing"]


# --- Helpers ------------------------------------------------------------------


def scorer(include, exclude=()):
    return KeywordScorer(include, exclude).score


def moment(day):
    return datetime.combine(day, time(8))


def save(conn, day, found, online, words=WORDS_DAY_1):
    """Save in the database what a source returned on that day."""
    save_source_result(conn, "business_france", found, online, scorer(words), moment(day))


def run(conn, path, day, offers, words=WORDS_DAY_1, online=True):
    """Save these offers, online, then export, as the pipeline does."""
    found = [FoundOffer(o, SEARCH) for o in offers]
    save(conn, day, found, offers if online else None, words)
    return excel.write_workbook(path, list_offers(conn), day)


def ids(conn, offers):
    by_reference = {s.offer.reference: s.id for s in list_offers(conn)}
    return [by_reference[o.reference] for o in offers]


def rows_by_reference(path):
    """Return {reference: {column title: value}} for each row."""
    sheet = load_workbook(path).active
    titles = [c.value for c in sheet[1]]
    rows = {}
    for row in sheet.iter_rows(min_row=2, values_only=True):
        values = dict(zip(titles, row))
        rows[values["Réf."]] = values
    return rows


def green_rows(path):
    """Return the references of the rows with the "new" green background."""
    sheet = load_workbook(path).active
    ref_column = [c.value for c in sheet[1]].index("Réf.")
    return [
        row[ref_column].value
        for row in sheet.iter_rows(min_row=2)
        if any(c.fill.fgColor.rgb == excel.NEW_COLOR for c in row)
    ]


def as_text(value):
    """Make a cell value storable in JSON."""
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return value


def content(path):
    """Return everything important in the file, for the snapshot."""
    sheet = load_workbook(path).active
    return {
        "titre_feuille": sheet.title,
        "volets_figes": sheet.freeze_panes,
        "filtre": sheet.auto_filter.ref,
        "listes": [
            {"formule": v.formula1, "plage": str(v.sqref)}
            for v in sheet.data_validations.dataValidation
        ],
        "cellules": [[as_text(c.value) for c in row] for row in sheet.iter_rows()],
        "formats": [
            [c.coordinate, c.number_format]
            for row in sheet.iter_rows()
            for c in row
            if c.number_format != "General"
        ],
        "largeurs": {
            letter: dimension.width for letter, dimension in sheet.column_dimensions.items()
        },
        "liens": [
            [c.coordinate, c.hyperlink.target]
            for row in sheet.iter_rows()
            for c in row
            if c.hyperlink
        ],
        # Color written as is: the snapshot must see a color change.
        "fonds": [
            [c.coordinate, c.fill.fgColor.rgb]
            for row in sheet.iter_rows()
            for c in row
            if c.fill.fill_type == "solid"
        ],
    }


def follow_up(conn, offers):
    """Enter a follow-up on offers 2 and 3 and put offer 4 in the trash."""
    second, third, fourth = ids(conn, offers[1:4])
    now = moment(DAY_2)
    set_status(conn, [second], "applied", now)
    save_tracking_details(conn, second, date(2026, 10, 20), "Relancer lundi", now)
    set_status(conn, [third], "interesting", now)
    set_letter_status(conn, [third], "to_write", now)
    set_favorite(conn, [third], True, now)
    hide(conn, [fourth], now)


def two_days(conn, path, offers):
    """Day 1 on a new file; day 2 after a follow-up entered in the interface."""
    result = {}
    run(conn, path, DAY_1, offers[:4])
    result["jour_1"] = content(path)
    follow_up(conn, offers)
    run(conn, path, DAY_2, offers[1:], words=WORDS_DAY_2)
    result["jour_2"] = content(path)
    return result


@pytest.fixture
def offers(business_france_search):
    """The 5 offers of the fixture."""
    return [to_offer(raw) for raw in business_france_search["result"]]


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "offres_vie.xlsx")


@pytest.fixture
def conn(tmp_path):
    return connect(tmp_path / "offers.db")


# --- 1. Creation --------------------------------------------------------------


def test_file_creation(conn, path, offers):
    report = run(conn, path, DAY_1, offers)

    sheet = load_workbook(path).active
    assert [c.value for c in sheet[1]] == excel.SCRIPT_COLUMNS + [
        "Statut",
        "Lettre",
        "Favori",
        "Postulé le",
        "Notes",
    ]
    assert sheet.title == "Offres"
    assert sheet.freeze_panes == "A2"
    assert sheet.auto_filter.ref == "A1:S6"

    rows = rows_by_reference(path)
    assert list(rows) == [o.reference for o in offers]
    first = rows[offers[0].reference]
    assert first["Titre"] == offers[0].title
    assert first["Entreprise"] == offers[0].company
    assert first["Ajoutée le"].date() == DAY_1
    assert first["En ligne"] == excel.ONLINE
    assert first["Recherche"] == SEARCH
    assert first["Source"] == "Business France"
    assert all(first[title] is None for title in excel.TRACKING_COLUMNS)

    # No green background on the first export: everything would be green.
    assert green_rows(path) == []
    # The file is no longer filled in by hand: no drop-down list.
    assert not sheet.data_validations.dataValidation

    assert sheet.cell(row=2, column=12).hyperlink.target == offers[0].url
    # No backup: there was nothing to save.
    assert not os.path.exists(os.path.join(os.path.dirname(path), "backup"))
    assert report.rows == 5


# --- 2. Follow-up and trash ---------------------------------------------------


def test_follow_up_comes_from_the_database(conn, path, offers):
    run(conn, path, DAY_1, offers[:4])
    follow_up(conn, offers)

    report = run(conn, path, DAY_2, offers[1:])

    rows = rows_by_reference(path)
    second, third = rows[offers[1].reference], rows[offers[2].reference]
    assert (second["Statut"], second["Postulé le"], second["Notes"]) == (
        "Postulé",
        datetime(2026, 10, 20),
        "Relancer lundi",
    )
    assert (second["Lettre"], second["Favori"]) == (None, None)
    assert (third["Statut"], third["Lettre"], third["Favori"]) == (
        "Intéressant",
        "À rédiger",
        "Oui",
    )
    # Offer 4 is in the trash.
    assert offers[3].reference not in rows
    assert report.rows == 4


def test_application_date_typed_as_text_is_kept(conn, path, offers):
    run(conn, path, DAY_1, offers[:1])
    (first,) = ids(conn, offers[:1])
    conn.execute(
        "INSERT INTO tracking (offer_id, applied_on, updated_at) VALUES (?, 'mi-oct', 'x')",
        (first,),
    )

    excel.write_workbook(path, list_offers(conn), DAY_2)
    assert rows_by_reference(path)[offers[0].reference]["Postulé le"] == "mi-oct"


def test_offline_offers_are_kept(conn, path, offers):
    run(conn, path, DAY_1, offers)
    run(conn, path, DAY_2, offers[1:])
    rows = rows_by_reference(path)
    assert rows[offers[0].reference]["En ligne"] == excel.NO_LONGER_ONLINE
    run(conn, path, DAY_3, offers)
    assert rows_by_reference(path)[offers[0].reference]["En ligne"] == excel.ONLINE


# --- 3. Regeneration ----------------------------------------------------------


def test_file_is_written_again_from_scratch(conn, path, offers):
    run(conn, path, DAY_1, offers[:2])
    workbook = load_workbook(path)
    sheet = workbook.active
    sheet.cell(row=1, column=20, value="Ma colonne")
    sheet.cell(row=2, column=20, value="perso")
    sheet.cell(row=2, column=15, value="Postulé")  # "Statut", typed in the file
    sheet.append(["MANUEL-1", "Offre notée à la main"])
    workbook.save(path)

    report = run(conn, path, DAY_2, offers)

    sheet = load_workbook(path).active
    assert [c.value for c in sheet[1]] == excel.COLUMNS
    rows = rows_by_reference(path)
    assert list(rows) == [o.reference for o in offers]
    assert rows[offers[0].reference]["Statut"] is None
    backups = os.listdir(os.path.join(os.path.dirname(path), "backup"))
    assert len(backups) == 1 and backups[0].startswith("offres_vie_")
    assert report.rows == 5


def test_rows_follow_first_seen_then_id(conn, tmp_path, path, offers):
    run(conn, path, DAY_1, offers[2:4])
    run(conn, path, DAY_2, offers)

    other = str(tmp_path / "autre.xlsx")
    excel.write_workbook(other, list(reversed(list_offers(conn))), DAY_3)

    rows = rows_by_reference(other)
    assert list(rows) == [o.reference for o in offers[2:4] + offers[:2] + offers[4:]]
    assert rows[offers[0].reference]["Ajoutée le"].date() == DAY_2


def test_green_background_only_for_offers_first_seen_today(conn, path, offers):
    run(conn, path, DAY_1, offers[:2])
    # Offer 3 saved on day 2, but exported only on day 3.
    save(conn, DAY_2, [FoundOffer(offers[2], SEARCH)], offers[:3])
    run(conn, path, DAY_3, offers[:4])
    assert green_rows(path) == [offers[3].reference]

    run(conn, path, date(2026, 10, 23), offers[:4])
    assert green_rows(path) == []


def test_no_duplicate_between_searches(conn, path, offers):
    # The same offer found by two searches is written once, with the name of
    # the first search.
    found = [FoundOffer(offers[0], "A"), FoundOffer(offers[0], "B"), FoundOffer(offers[1], "B")]
    save(conn, DAY_1, found, offers)
    report = excel.write_workbook(path, list_offers(conn), DAY_1)

    rows = rows_by_reference(path)
    assert len(rows) == 2
    assert rows[offers[0].reference]["Recherche"] == "A"
    assert report.rows == 2


def test_empty_database(conn, path):
    report = excel.write_workbook(path, list_offers(conn), DAY_1)
    assert report.rows == 0
    assert load_workbook(path).active.auto_filter.ref == "A1:S1"


# --- 4. Errors ----------------------------------------------------------------


def test_error_if_the_file_is_open(conn, path, offers):
    run(conn, path, DAY_1, offers[:2])
    before = content(path)
    lock = os.path.join(os.path.dirname(path), "~$offres_vie.xlsx")
    open(lock, "w").close()

    with pytest.raises(excel.ExcelError, match="est ouvert"):
        run(conn, path, DAY_2, offers)
    assert content(path) == before


def test_file_that_is_not_an_excel_file_is_saved_then_replaced(conn, path, offers):
    """Nothing is read from the existing file."""
    with open(path, "w") as file:
        file.write("pas un classeur")

    run(conn, path, DAY_1, offers)

    assert len(rows_by_reference(path)) == 5
    (backup,) = os.listdir(os.path.join(os.path.dirname(path), "backup"))
    with open(os.path.join(os.path.dirname(path), "backup", backup)) as file:
        assert file.read() == "pas un classeur"


def test_error_on_save_keeps_the_old_file(conn, monkeypatch, path, offers):
    run(conn, path, DAY_1, offers[:2])
    before = content(path)

    def failing_replace(source, target):
        raise PermissionError("disque protégé")

    monkeypatch.setattr(excel.os, "replace", failing_replace)
    with pytest.raises(excel.ExcelError, match="Impossible d'écrire.*disque protégé"):
        run(conn, path, DAY_2, offers)
    assert content(path) == before
    assert not os.path.exists(path + ".tmp")


def test_new_file_without_folder(conn, tmp_path, offers):
    path = str(tmp_path / "output" / "offres.xlsx")
    run(conn, path, DAY_1, offers[:1])
    assert os.path.exists(path)


# --- 5. Snapshot --------------------------------------------------------------


def test_snapshot(conn, path, offers):
    """Compare the file with the recorded snapshot, after two exports."""
    result = two_days(conn, path, offers)

    if os.environ.get("UPDATE_SNAPSHOT"):
        with open(SNAPSHOT_PATH, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=1)
            file.write("\n")

    with open(SNAPSHOT_PATH, encoding="utf-8") as file:
        assert result == json.load(file)
