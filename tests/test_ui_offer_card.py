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
from offers.storage.database import connect, hide, save_source_result, save_tracking_details
from offers.ui import offer_card
from offers.ui.offer_table import PageSettings
from tests.factories import make_stored
from tests.test_ui_offers import (
    TIMEOUT,
    button,
    by_reference,
    counters,
    list_data,
    offer,
    titles,
)

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
    assert "**2** non lues" in counters(at)


def test_card_of_an_unknown_offer_is_closed(start):
    at = start(999)
    assert not at.exception
    assert CARD not in at.session_state


# --- Follow-up ----------------------------------------------------------------


def test_each_change_of_the_follow_up_is_saved(start, db_path, ids):
    at = start(ids["VIE1"])
    at.selectbox(key=field(ids, "VIE1", "status")).select("applied").run()

    assert by_reference(db_path)["VIE1"].status == "applied"
    # The card stays open beside the list, which shows the change.
    assert at.session_state[CARD] == ids["VIE1"]
    assert "Suivi enregistré." in texts(at.toast)

    at.selectbox(key=field(ids, "VIE1", "letter")).select("written").run()
    at.date_input(key=field(ids, "VIE1", "applied_on")).set_value(date(2026, 10, 21)).run()
    at.text_area(key=field(ids, "VIE1", "notes")).set_value("Relancer lundi").run()

    first = by_reference(db_path)["VIE1"]
    assert (first.status, first.letter_status) == ("applied", "written")
    assert (first.applied_on, first.notes) == ("2026-10-21", "Relancer lundi")


def test_no_save_button_nor_favorite_in_the_follow_up(start, ids):
    at = start(ids["VIE1"])
    assert not [b for b in at.button if b.label == "Enregistrer"]
    assert not at.checkbox


def test_form_shows_the_current_follow_up(start, db_path, ids):
    conn = connect(db_path)
    save_tracking_details(conn, ids["VIE2"], date(2026, 10, 20), "Vu au salon", NOW)
    conn.close()

    at = start(ids["VIE2"])

    assert at.date_input(key=field(ids, "VIE2", "applied_on")).value == date(2026, 10, 20)
    assert at.text_area(key=field(ids, "VIE2", "notes")).value == "Vu au salon"
    assert at.selectbox(key=field(ids, "VIE2", "status")).value == ""


def test_trash_from_the_card_opens_the_next_offer(start, db_path, ids):
    at = start(ids["VIE1"])
    at.button(key="offers_card_action").click().run()

    assert by_reference(db_path)["VIE1"].hidden
    # The card shows the offer below in the table, now read.
    assert at.session_state[CARD] == ids["VIE2"]
    assert by_reference(db_path)["VIE2"].read_at is not None
    assert at.success[0].value == "1 offres mises à la corbeille"

    button(at, "Annuler").click().run()
    assert not by_reference(db_path)["VIE1"].hidden


def test_trash_of_the_last_offer_opens_the_one_above(start, ids):
    at = start(ids["VIE3"])
    at.button(key="offers_card_action").click().run()
    assert at.session_state[CARD] == ids["VIE2"]


@pytest.mark.parametrize(
    "navigation, expected",
    [
        (offer_card.Navigation(previous=10, next=30, position=2, total=3), 30),
        (offer_card.Navigation(previous=20, next=None, position=3, total=3), 20),
        (offer_card.Navigation(previous=None, next=None, position=1, total=1), None),
        (None, None),
    ],
)
def test_following_offer(navigation, expected):
    assert offer_card.following_offer(navigation) == expected


# --- Without Streamlit --------------------------------------------------------


def test_details():
    stored = make_stored(last_seen=datetime(2026, 10, 22, 8, 0), online=False, search_name=None)
    assert offer_card.details(stored) == {
        "Réf.": "REF1",
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


# --- Arrows -------------------------------------------------------------------


def test_arrows_go_to_the_next_and_previous_offers(start, db_path, ids):
    at = start(ids["VIE1"])
    assert "1 / 3" in texts(at.caption)
    assert at.button(key="offers_card_previous").disabled

    at.button(key="offers_card_next").click().run()

    assert at.session_state[CARD] == ids["VIE2"]
    assert "2 / 3" in texts(at.caption)
    # The offer reached is read.
    assert by_reference(db_path)["VIE2"].read_at is not None

    at.button(key="offers_card_previous").click().run()
    assert at.session_state[CARD] == ids["VIE1"]


def test_last_offer_has_no_next(start, ids):
    at = start(ids["VIE3"])
    assert "3 / 3" in texts(at.caption)
    assert at.button(key="offers_card_next").disabled
    assert not at.button(key="offers_card_previous").disabled


def test_arrows_follow_the_filters(start, ids):
    at = start(ids["VIE2"])
    at.text_input(key="offers_text").set_value("comptable").run()
    assert "1 / 2" in texts(at.caption)
    at.button(key="offers_card_next").click().run()
    assert at.session_state[CARD] == ids["VIE3"]


@pytest.mark.parametrize(
    "offer_id, expected",
    [
        (20, offer_card.Navigation(previous=10, next=30, position=2, total=3)),
        (10, offer_card.Navigation(previous=None, next=20, position=1, total=3)),
        (30, offer_card.Navigation(previous=20, next=None, position=3, total=3)),
        (99, None),
    ],
)
def test_navigation(offer_id, expected):
    assert offer_card.navigation([10, 20, 30], offer_id) == expected


def texts(elements):
    return [element.value for element in elements]


# --- Card beside the list -----------------------------------------------------


def test_card_is_beside_the_list(start, ids):
    at = start(ids["VIE2"])

    # The list stays shown with the card, its line highlighted.
    assert titles(at) == ["Data analyst", "Comptable", "Comptable"]
    assert list_data(at)["open"] == ids["VIE2"]
    # The follow-up at the top of the card, under its title.
    assert at.subheader[0].value == "Comptable"
    assert at.selectbox(key=field(ids, "VIE2", "status"))


def test_card_toolbar_has_only_icons(start, ids):
    at = start(ids["VIE2"])
    names = {
        "offers_card_previous": "Précédente",
        "offers_card_next": "Suivante",
        "offers_card_favorite": "Favori",
        "offers_card_action": "Mettre à la corbeille",
        "offers_card_close": "Fermer",
    }
    for key, help_text in names.items():
        assert at.button(key=key).label.startswith(":material/")
        assert at.button(key=key).help == help_text
    assert at.link_button[0].help == "Voir l'offre sur le site"


def test_close_button(start, ids):
    at = start(ids["VIE1"])
    at.button(key="offers_card_close").click().run()
    assert CARD not in at.session_state
    assert not at.link_button


def test_favorite_button_writes_at_once(start, db_path, ids):
    at = start(ids["VIE1"])
    favorite_style = offer_card.favorite_style("offers_card_favorite")
    assert at.button(key="offers_card_favorite").help == "Favori"
    assert favorite_style not in texts(at.get("html"))

    at.button(key="offers_card_favorite").click().run()

    assert by_reference(db_path)["VIE1"].favorite
    assert at.button(key="offers_card_favorite").help == "Retirer des favoris"
    # Yellow, as the line of a favorite in the list.
    assert favorite_style in texts(at.get("html"))
    assert offer_card.FAVORITE_COLOR in favorite_style

    at.button(key="offers_card_favorite").click().run()
    assert not by_reference(db_path)["VIE1"].favorite


def test_no_favorite_button_in_the_trash(open_trash_card):
    assert not [b for b in open_trash_card.button if b.key == "trash_card_favorite"]


@pytest.fixture
def open_trash_card(monkeypatch, db_path, ids):
    conn = connect(db_path)
    hide(conn, [ids["VIE1"]], NOW)
    conn.close()
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(db_path)])
    at = AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT).run()
    at.session_state["trash_card"] = ids["VIE1"]
    return at.switch_page("app_pages/trash.py").run()
