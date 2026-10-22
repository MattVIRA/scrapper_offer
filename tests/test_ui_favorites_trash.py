"""Tests of the « Favoris » and « Corbeille » pages."""

import sys
from datetime import date, datetime

import pytest
from streamlit.testing.v1 import AppTest

from offers import browsing
from offers.__main__ import UI_APP
from offers.sources.base import FoundOffer
from offers.storage.database import (
    connect,
    hide,
    list_offers,
    save_follow_up,
    save_source_result,
    set_favorite,
)
from offers.ui import offer_card
from offers.ui.offer_table import PageSettings
from tests.factories import make_stored
from tests.test_ui_offers import TIMEOUT, button, by_reference, offer, table

NOW = datetime(2026, 10, 22, 9, 30)
OFFERS = "app_pages/offers.py"
FAVORITES = "app_pages/favorites.py"
TRASH = "app_pages/trash.py"


@pytest.fixture
def db_path(tmp_path):
    """VIE1 favorite and followed; VIE2 favorite and applied; VIE3 not for me, offline."""
    path = tmp_path / "offers.db"
    conn = connect(path)
    offers = [offer(1), offer(2), offer(3)]
    found = [FoundOffer(o, "A") for o in offers]
    save_source_result(conn, "business_france", found, offers[:2], lambda o: (1, "data"), NOW)
    ids = {s.offer.reference: s.id for s in list_offers(conn)}
    save_follow_up(conn, ids["VIE1"], "rejected", "to_write", date(2026, 10, 21), "Relancer", NOW)
    save_follow_up(conn, ids["VIE2"], "applied", None, None, None, NOW)
    save_follow_up(conn, ids["VIE3"], "not_for_me", None, None, None, NOW)
    set_favorite(conn, [ids["VIE1"], ids["VIE2"]], True, NOW)
    conn.close()
    return path


@pytest.fixture
def ids(db_path):
    return {reference: s.id for reference, s in by_reference(db_path).items()}


@pytest.fixture
def open_page(monkeypatch, db_path):
    """Return a function that opens one page of the app."""
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(db_path)])

    def open_page(page, state=None):
        at = AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT).run()
        for key, value in (state or {}).items():
            at.session_state[key] = value
        return at.switch_page(page).run()

    return open_page


def titles(at):
    return list(table(at)["Titre"]) if at.dataframe else []


def write(db_path, action, offer_ids):
    conn = connect(db_path)
    action(conn, offer_ids, NOW)
    conn.close()


# --- Favoris ------------------------------------------------------------------


def test_favorites_page(open_page):
    at = open_page(FAVORITES)

    assert not at.exception
    assert at.title[0].value == "Favoris (2)"
    assert titles(at) == ["Poste 1", "Poste 2"]


def test_favorites_has_the_columns_and_actions_of_offers(open_page):
    favorites = open_page(FAVORITES)
    offers = open_page(OFFERS)

    assert list(table(favorites).columns) == list(table(offers).columns)
    assert [b.label for b in favorites.button] == [b.label for b in offers.button]
    assert [m.label for m in favorites.menu_button] == ["Statut", "Lettre"]


def test_removing_a_favorite_takes_it_out_of_favorites(open_page, db_path, ids):
    at = open_page(FAVORITES, {"favorites_selected": {ids["VIE1"]}})
    button(at, "Retirer des favoris").click().run()

    assert titles(at) == ["Poste 2"]
    assert at.title[0].value == "Favoris (1)"
    assert not by_reference(db_path)["VIE1"].favorite


# --- Corbeille ----------------------------------------------------------------


def test_trashed_offer_leaves_offers_and_favorites(open_page, db_path, ids):
    write(db_path, hide, [ids["VIE1"], ids["VIE3"]])

    assert titles(open_page(OFFERS)) == ["Poste 2"]
    assert titles(open_page(FAVORITES)) == ["Poste 2"]
    trash = open_page(TRASH)
    assert trash.title[0].value == "Corbeille (2)"
    # In the trash, every status and offline offers are shown by default.
    assert titles(trash) == ["Poste 1", "Poste 3"]


def test_trash_only_offers_to_restore(open_page, db_path, ids):
    write(db_path, hide, [ids["VIE1"]])
    at = open_page(TRASH)

    assert [b.label for b in at.button] == ["Restaurer"]
    assert not at.menu_button


def test_restored_offer_comes_back_with_its_follow_up(open_page, db_path, ids):
    write(db_path, hide, [ids["VIE1"], ids["VIE2"]])
    at = open_page(TRASH, {"trash_selected": {ids["VIE1"]}})

    button(at, "Restaurer").click().run()

    assert titles(at) == ["Poste 2"]
    first = by_reference(db_path)["VIE1"]
    assert not first.hidden
    assert (first.status, first.letter_status, first.favorite) == ("rejected", "to_write", True)
    assert (first.applied_on, first.notes) == ("2026-10-21", "Relancer")
    assert "Poste 1" in titles(open_page(OFFERS))
    assert titles(open_page(FAVORITES)) == ["Poste 1"]


def test_card_in_the_trash_is_read_only_and_restores(open_page, db_path, ids):
    write(db_path, hide, [ids["VIE1"]])
    at = open_page(TRASH, {"trash_card": ids["VIE1"]})

    assert not at.exception
    assert not at.text_area and not at.selectbox
    # The follow-up shown under the list, without form.
    follow_up = next(table.value for table in at.table if "Notes" in table.value.index)
    assert follow_up.loc["Notes"].iloc[0] == "Relancer"

    at.button(key="trash_card_action").click().run()
    assert not by_reference(db_path)["VIE1"].hidden
    assert "trash_card" not in at.session_state


def test_empty_trash(open_page):
    at = open_page(TRASH)
    assert at.title[0].value == "Corbeille (0)"
    assert "Aucune offre" in at.info[0].value


# --- Without Streamlit --------------------------------------------------------


def test_page_settings():
    trash = PageSettings(key="trash", title="Corbeille", in_trash=True)
    offers = PageSettings(key="offers", title="Offres")

    assert trash.default_online() == browsing.ALL
    assert offers.default_statuses() == browsing.DEFAULT_STATUSES
    assert "not_for_me" in trash.default_statuses()


def test_read_only_follow_up():
    stored = make_stored(status="applied", favorite=True, applied_on="mi-oct")
    assert offer_card.follow_up(stored) == {
        "Statut": "Postulé",
        "Lettre": "Aucune",
        "Favori": "Oui",
        "Postulé le": "mi-oct",
        "Notes": "—",
    }
    dated = make_stored(applied_on="2026-10-21")
    assert offer_card.follow_up(dated)["Postulé le"] == "21/10/2026"
    assert offer_card.follow_up(make_stored())["Statut"] == "Sans statut"
