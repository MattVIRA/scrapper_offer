"""Tests of the card of an offer.

The « Ouvrir » button of the table cannot be clicked in AppTest: the card
is opened by setting its session state key, as the button callback does.
"""

import sys
from datetime import date, datetime

import pytest
from streamlit.testing.v1 import AppTest

from offers.__main__ import UI_APP
from offers.sources.base import FoundOffer
from offers.storage.database import connect, save_source_result, save_tracking_details
from offers.ui import offer_card, offer_table
from offers.ui.offer_table import PageSettings
from tests.factories import make_stored
from tests.test_ui_offers import TIMEOUT, button, by_reference, metrics, offer, table

NOW = datetime(2026, 10, 22, 9, 30)
CARD = "offers_card"
DESCRIPTION = "Analyse des ventes.\n• Tableaux de bord\n• SQL et *Python*"


@pytest.fixture
def db_path(tmp_path):
    """VIE1 with a description; VIE2 and VIE3: same company and title."""
    path = tmp_path / "offers.db"
    conn = connect(path)
    offers = [
        offer(1, title="Data analyst", description=DESCRIPTION, candidate_profile="Bac+5"),
        offer(2, title="Comptable", company="ACME"),
        offer(3, title="Comptable", company="ACME"),
    ]
    found = [FoundOffer(o, "Recherche data") for o in offers]
    save_source_result(conn, "business_france", found, offers, lambda o: (2, "data, sql"), NOW)
    conn.close()
    return path


@pytest.fixture
def ids(db_path):
    return {reference: s.id for reference, s in by_reference(db_path).items()}


@pytest.fixture
def start(monkeypatch, db_path):
    """Return a function that opens the app with the card of an offer open."""
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(db_path)])

    def start(offer_id):
        at = AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT)
        at.session_state[CARD] = offer_id
        return at.run()

    return start


def field(ids, reference, name):
    return f"offers_card_{ids[reference]}_{name}"


# --- Content ------------------------------------------------------------------


def test_card_shows_the_whole_offer(start, ids):
    at = start(ids["VIE1"])

    assert not at.exception
    texts = [t.value for t in at.text]
    assert DESCRIPTION in texts and "Bac+5" in texts
    assert at.link_button[0].url == "https://example.com/1"
    details = at.table[0].value
    assert details.loc["Recherche"].iloc[0] == "Recherche data"
    assert details.loc["Ajoutée le"].iloc[0] == "22/10/2026"
    assert {m.label: m.value for m in at.metric}["Score par mots-clés"] == "2"
    assert "Mots trouvés : data, sql" in [c.value for c in at.caption]
    assert not at.warning


def test_card_shows_the_probable_duplicates(start, ids):
    at = start(ids["VIE2"])
    assert at.warning[0].value == "Doublon probable de VIE3"


def test_opening_the_card_marks_the_offer_as_read(start, db_path, ids):
    at = start(ids["VIE1"])

    assert by_reference(db_path)["VIE1"].read_at is not None
    assert by_reference(db_path)["VIE2"].read_at is None
    assert metrics(at)["Non lues"] == "2"
    assert list(table(at)[offer_table.UNREAD]) == [False, True, True]


def test_card_of_an_unknown_offer_is_closed(start):
    at = start(999)
    assert not at.exception
    assert CARD not in at.session_state


# --- Follow-up ----------------------------------------------------------------


def test_follow_up_is_saved_by_the_form(start, db_path, ids):
    at = start(ids["VIE1"])
    at.selectbox(key=field(ids, "VIE1", "status")).select("applied")
    at.selectbox(key=field(ids, "VIE1", "letter")).select("written")
    at.checkbox(key=field(ids, "VIE1", "favorite")).check()
    at.date_input(key=field(ids, "VIE1", "applied_on")).set_value(date(2026, 10, 21))
    at.text_area(key=field(ids, "VIE1", "notes")).set_value("Relancer lundi")
    button(at, "Enregistrer").click().run()

    first = by_reference(db_path)["VIE1"]
    assert (first.status, first.letter_status, first.favorite) == ("applied", "written", True)
    assert (first.applied_on, first.notes) == ("2026-10-21", "Relancer lundi")
    assert CARD not in at.session_state
    assert table(at)[offer_table.STATUS][0] == "applied"


def test_nothing_is_written_before_saving(start, db_path, ids):
    at = start(ids["VIE1"])
    at.selectbox(key=field(ids, "VIE1", "status")).select("applied")
    at.text_area(key=field(ids, "VIE1", "notes")).set_value("Brouillon")
    at.button(key="offers_card_action").click().run()

    first = by_reference(db_path)["VIE1"]
    assert (first.status, first.notes) == (None, None)


def test_form_shows_the_current_follow_up(start, db_path, ids):
    conn = connect(db_path)
    save_tracking_details(conn, ids["VIE2"], date(2026, 10, 20), "Vu au salon", NOW)
    conn.close()

    at = start(ids["VIE2"])

    assert at.date_input(key=field(ids, "VIE2", "applied_on")).value == date(2026, 10, 20)
    assert at.text_area(key=field(ids, "VIE2", "notes")).value == "Vu au salon"
    assert at.selectbox(key=field(ids, "VIE2", "status")).value == ""


def test_trash_from_the_card_can_be_undone(start, db_path, ids):
    at = start(ids["VIE1"])
    at.button(key="offers_card_action").click().run()

    assert by_reference(db_path)["VIE1"].hidden
    assert CARD not in at.session_state
    assert at.success[0].value == "1 offres mises à la corbeille"

    button(at, "Annuler").click().run()
    assert not by_reference(db_path)["VIE1"].hidden


# --- Without Streamlit --------------------------------------------------------


def test_details():
    stored = make_stored(last_seen=datetime(2026, 10, 22, 8, 0), online=False, search_name=None)
    assert offer_card.details(stored) == {
        "Pays et ville": "PARIS, FRANCE",
        "Durée": "12 mois",
        "Type de contrat": "VIE",
        "Publiée le": "21/10/2026",
        "Ajoutée le": "20/10/2026",
        "Vue pour la dernière fois": "22/10/2026",
        "En ligne": "Plus en ligne",
        "Source": "test",
        "Recherche": "—",
    }


@pytest.mark.parametrize(
    "chosen, stored_text, expected",
    [
        (date(2026, 10, 21), None, date(2026, 10, 21)),
        (date(2026, 10, 21), "mi-oct", date(2026, 10, 21)),
        (None, "mi-oct", "mi-oct"),  # typed in the old Excel file: kept
        (None, "2026-10-20", None),  # a real date can be cleared
        (None, None, None),
    ],
)
def test_applied_on_to_save(chosen, stored_text, expected):
    assert offer_card.applied_on_to_save(chosen, stored_text) == expected


def test_card_key_belongs_to_the_page():
    assert offer_card.card_key(PageSettings(key="favorites", title="Favoris")) == "favorites_card"
