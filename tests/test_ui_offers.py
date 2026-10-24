"""Tests of the « Offres » page and of its shared list module.

AppTest cannot run the list component (JavaScript): the tests read the
lines it is given, and set the checked offers and the open card in the
session state, as the component's callbacks do.
"""

import json
import sys
from datetime import date, datetime

import pytest
from streamlit.elements.lib import policies
from streamlit.testing.v1 import AppTest

from offers import browsing
from offers.__main__ import UI_APP
from offers.sources.base import FoundOffer
from offers.storage.database import connect, list_offers, save_source_result, set_status
from offers.ui import labels, offer_card, offer_list, offer_table
from offers.ui.offer_table import PageSettings, make_filter
from tests.factories import make_offer, make_stored

NOW = datetime(2026, 10, 22, 9, 30)
TIMEOUT = 30
PAGE = PageSettings(key="offers", title="Offres")
SELECTED = "offers_selected"


def offer(number, **changes):
    values = {
        "source": "business_france",
        "source_id": str(number),
        "reference": f"VIE{number}",
        "title": f"Poste {number}",
        "company": f"Entreprise {number}",
        "url": f"https://example.com/{number}",
    }
    return make_offer(**{**values, **changes})


def by_reference(db_path):
    conn = connect(db_path)
    try:
        return {s.offer.reference: s for s in list_offers(conn)}
    finally:
        conn.close()


@pytest.fixture
def db_path(tmp_path):
    """Database with 4 online offers; VIE4 is offline, VIE1 has a score."""
    path = tmp_path / "offers.db"
    conn = connect(path)
    offers = [offer(1, title="Data analyst"), offer(2), offer(3), offer(4)]
    found = [FoundOffer(o, "A") for o in offers]

    def score(o):
        return (2, "data") if o.reference == "VIE1" else (0, "")

    save_source_result(conn, "business_france", found, offers, score, NOW)
    save_source_result(conn, "business_france", found[:3], offers[:3], score, NOW)
    conn.close()
    return path


@pytest.fixture
def ids(db_path):
    return {reference: s.id for reference, s in by_reference(db_path).items()}


@pytest.fixture
def at(monkeypatch, db_path):
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(db_path)])
    return AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT).run()


def list_data(at):
    """Return the data given to the list component, or None without a list."""
    lists = at.get("bidi_component")
    return json.loads(lists[0].proto.json) if lists else None


def titles(at):
    data = list_data(at)
    return [row["title"] for row in data["rows"]] if data else []


def counters(at):
    """Return the line of the counters."""
    return next(c.value for c in at.caption if " offres · " in c.value)


def button(at, label):
    """Return the button of this name: shown as its label, or on hovering an icon."""
    return next(b for b in at.button if label in (b.label, b.help))


# --- Page ---------------------------------------------------------------------


def test_page_shows_counters_and_list(at):
    assert not at.exception
    # Default filter: online offers only.
    assert titles(at) == ["Data analyst", "Poste 2", "Poste 3"]
    assert counters(at) == (
        "**3** offres · **3** non lues · **0** postulées · **0** lettres à rédiger"
    )


def test_no_sidebar_and_no_title(at):
    # Search, filters and counters stay on top of the list.
    assert not at.sidebar.children
    assert not at.title


def test_filters_change_the_table(at):
    at.text_input(key="offers_text").set_value("data").run()
    assert titles(at) == ["Data analyst"]

    at.text_input(key="offers_text").set_value("").run()
    at.segmented_control(key="offers_online").set_value(browsing.ALL).run()
    assert len(titles(at)) == 4

    at.number_input(key="offers_min_score").set_value(1).run()
    assert titles(at) == ["Data analyst"]
    assert "**1** offres" in counters(at)


def test_search_by_reference_finds_an_offline_offer(at):
    # VIE4 is offline, hidden by the default filter.
    at.text_input(key="offers_text").set_value("vie4").run()
    assert titles(at) == ["Poste 4"]


def test_search_bar_is_above_the_list(at):
    assert at.text_input(key="offers_text").placeholder == offer_table.SEARCH_PLACEHOLDER


def test_no_offer_left(at):
    at.text_input(key="offers_text").set_value("introuvable").run()
    assert list_data(at) is None
    assert "Aucune offre" in at.info[0].value


def test_status_saved_in_the_database_is_shown(at, db_path, ids):
    conn = connect(db_path)
    set_status(conn, [ids["VIE1"]], "applied", NOW)
    conn.close()

    at.run()
    assert "**1** postulées" in counters(at)


# --- Actions on the checked offers --------------------------------------------


def test_group_status_only_changes_the_checked_offers(at, db_path, ids):
    at.session_state[SELECTED] = {ids["VIE1"], ids["VIE3"]}
    at.run()
    at.menu_button(key="offers_status_menu").click("rejected").run()

    assert not at.exception
    stored = by_reference(db_path)
    assert {r: s.status for r, s in stored.items()} == {
        "VIE1": "rejected",
        "VIE2": None,
        "VIE3": "rejected",
        "VIE4": None,
    }
    # Everything is unchecked after an action, the boxes of the list too.
    assert at.session_state[SELECTED] == set()
    assert list_data(at)["checked"] == []


def test_group_letter_and_favorite(at, db_path, ids):
    at.session_state[SELECTED] = {ids["VIE2"]}
    at.run()
    at.menu_button(key="offers_letter_menu").click("to_write").run()
    at.session_state[SELECTED] = {ids["VIE2"]}
    at.run()
    button(at, "Favori").click().run()

    second = by_reference(db_path)["VIE2"]
    assert (second.letter_status, second.favorite) == ("to_write", True)
    assert "**1** lettres à rédiger" in counters(at)


def test_checked_offer_hidden_by_a_filter_is_not_changed(at, db_path, ids):
    at.session_state[SELECTED] = {ids["VIE1"], ids["VIE2"]}
    at.text_input(key="offers_text").set_value("data").run()
    button(at, "Marquer comme lu").click().run()

    stored = by_reference(db_path)
    assert stored["VIE1"].read_at is not None
    assert stored["VIE2"].read_at is None


def test_actions_need_a_checked_offer(at):
    assert button(at, "Corbeille").disabled
    assert at.menu_button(key="offers_status_menu").disabled
    assert not button(at, "Tout marquer comme lu").disabled


def test_actions_apply_to_the_open_line_when_nothing_is_checked(at, db_path, ids):
    at.session_state["offers_card"] = ids["VIE2"]
    at.run()
    assert "Ligne ouverte" in [c.value for c in at.caption]
    assert not at.menu_button(key="offers_status_menu").disabled

    at.menu_button(key="offers_status_menu").click("interesting").run()

    stored = by_reference(db_path)
    assert {r: s.status for r, s in stored.items()} == {
        "VIE1": None,
        "VIE2": "interesting",
        "VIE3": None,
        "VIE4": None,
    }
    # The card stays open.
    assert at.session_state["offers_card"] == ids["VIE2"]


def test_checked_offers_win_over_the_open_line(at, db_path, ids):
    at.session_state["offers_card"] = ids["VIE2"]
    at.session_state[SELECTED] = {ids["VIE1"]}
    at.run()
    assert "1 cochées" in [c.value for c in at.caption]
    button(at, "Favori").click().run()

    stored = by_reference(db_path)
    assert stored["VIE1"].favorite and not stored["VIE2"].favorite


def test_trash_of_the_open_line_opens_the_next_offer(at, db_path, ids):
    at.session_state["offers_card"] = ids["VIE2"]
    at.run()
    button(at, "Corbeille").click().run()

    assert by_reference(db_path)["VIE2"].hidden
    assert at.session_state["offers_card"] == ids["VIE3"]


@pytest.mark.parametrize(
    "checked, open_id, expected",
    [
        ({30, 10}, 20, [10, 30]),
        (set(), 20, [20]),
        (set(), 99, []),  # open offer hidden by a filter
        (set(), None, []),
        ({99}, 20, [20]),  # checked offer hidden by a filter
    ],
)
def test_action_targets(checked, open_id, expected):
    assert offer_table.action_targets(checked, open_id, [10, 20, 30]) == expected


@pytest.mark.parametrize(
    "targets, open_id, expected",
    [
        ([20], 20, 30),  # the open offer leaves: the next one
        ([30], 30, 20),  # the last one: the one above
        ([10], 20, 20),  # the open offer stays
        ([10, 20, 30], None, None),
    ],
)
def test_next_card(targets, open_id, expected):
    assert offer_table.next_card(targets, open_id, [10, 20, 30]) == expected


def test_trash_then_undo(at, db_path, ids):
    at.session_state[SELECTED] = {ids["VIE2"]}
    at.run()
    button(at, "Corbeille").click().run()

    assert by_reference(db_path)["VIE2"].hidden
    assert titles(at) == ["Data analyst", "Poste 3"]
    assert at.success[0].value == "1 offres mises à la corbeille"

    button(at, "Annuler").click().run()

    assert not by_reference(db_path)["VIE2"].hidden
    assert len(titles(at)) == 3
    assert not at.success


def test_undo_disappears_after_the_next_action(at, ids):
    at.session_state[SELECTED] = {ids["VIE2"]}
    at.run()
    button(at, "Corbeille").click().run()
    button(at, "Tout marquer comme lu").click().run()
    assert not at.success


def test_mark_all_shown_as_read(at, db_path):
    at.text_input(key="offers_text").set_value("poste").run()
    button(at, "Tout marquer comme lu").click().run()

    stored = by_reference(db_path)
    assert [stored[r].read_at is None for r in ("VIE1", "VIE2", "VIE3")] == [True, False, False]
    assert "**0** non lues" in counters(at)


# --- List ---------------------------------------------------------------------


def test_list_shows_the_checked_and_open_offers(at, ids):
    at.session_state[SELECTED] = {ids["VIE3"], ids["VIE1"]}
    at.session_state["offers_card"] = ids["VIE2"]
    at.run()
    data = list_data(at)
    assert data["checked"] == sorted([ids["VIE1"], ids["VIE3"]])
    assert data["open"] == ids["VIE2"]
    assert data["cardOpen"] and data["stars"]


def test_list_without_card(at):
    data = list_data(at)
    assert data["open"] is None and not data["cardOpen"]
    assert "card_pane" not in offer_list.split_style(PAGE.list_keys(), card_open=False)


def test_list_row():
    stored = make_stored(
        1, status="rejected", letter_status="written", favorite=True, read_at=NOW, score=3
    )
    assert offer_list.list_row(stored) == {
        "id": 1,
        "title": "Data Analyst",
        "subtitle": "ACME · PARIS, FRANCE",
        "source": "test",
        "score": "3",
        "date": "20/10",
        "letter": "Rédigée",
        "marker": "rejected",
        "unread": False,
        "favorite": True,
    }
    unread = offer_list.list_row(make_stored(2, online=False))
    assert (unread["score"], unread["letter"], unread["marker"]) == ("", "", "offline")
    assert unread["unread"]


def test_list_rows_markers():
    shown = [make_stored(1, favorite=True), make_stored(2, status="applied", favorite=True)]
    assert [row["marker"] for row in offer_list.list_rows(shown)] == ["favorite", "applied"]
    # No yellow on the Favorites page; blue stays.
    on_favorites = offer_list.list_rows(shown, on_favorites_page=True)
    assert [row["marker"] for row in on_favorites] == ["", "applied"]


def test_every_marker_has_its_class():
    markers = {*browsing.STATUS_MARKERS.values(), browsing.MARKER_FAVORITE, browsing.MARKER_OFFLINE}
    assert set(offer_list.MARKER_CLASSES) == markers | {browsing.NO_MARKER}
    css = (offer_list.ASSETS / "offer_list.css").read_text()
    for name in filter(None, offer_list.MARKER_CLASSES.values()):
        assert f".{name} " in css


def test_split_style_with_a_card():
    css = offer_list.split_style(PAGE.list_keys(), card_open=True)
    assert ".st-key-offers_split > :has(> .st-key-offers_list_pane)" in css
    assert "var(--offer-list-width" in css
    assert ".st-key-offers_card_pane {max-height" in css


def test_source_shows_the_label(at):
    assert {row["source"] for row in list_data(at)["rows"]} == {"Business France"}


def more_filters_label(at):
    return at.get("popover")[0].proto.popover.label


def test_more_filters_shows_how_many_are_used(at):
    assert more_filters_label(at) == offer_table.MORE_FILTERS
    at.number_input(key="offers_min_score").set_value(1).run()
    at.multiselect(key="offers_letters").select("").run()
    assert more_filters_label(at) == f"{offer_table.MORE_FILTERS} (2)"


def test_checked_box_hidden_by_a_filter_stays_checked(at, ids):
    at.session_state[SELECTED] = {ids["VIE3"]}
    at.text_input(key="offers_text").set_value("poste 2").run()
    assert at.session_state[SELECTED] == {ids["VIE3"]}
    at.text_input(key="offers_text").set_value("").run()
    assert list_data(at)["checked"] == [ids["VIE3"]]


def test_action_bar_updates_the_follow_up_of_the_card(at, db_path, ids):
    at.session_state["offers_card"] = ids["VIE2"]
    at.run()
    at.menu_button(key="offers_status_menu").click("not_for_me").run()
    assert at.selectbox(key=f"offers_card_{ids['VIE2']}_status").value == "not_for_me"
    # The old value of the field is not saved back on the next run.
    at.run()
    assert by_reference(db_path)["VIE2"].status == "not_for_me"


def test_card_fields_get_no_default_and_state_warning(at, ids, monkeypatch):
    # Streamlit only logs this misuse; its logger does not reach caplog.
    warnings = []
    monkeypatch.setattr(policies._LOGGER, "warning", lambda *args, **kw: warnings.append(args))
    at.session_state["offers_card"] = ids["VIE2"]
    at.run()
    at.menu_button(key="offers_status_menu").click("not_for_me").run()
    at.run()
    assert warnings == []


def test_make_filter_without_choice_filters_nothing():
    result = make_filter(PAGE, online=None)
    assert result == browsing.OfferFilter(
        statuses=frozenset({None, *browsing.STATUSES}), online=browsing.ALL
    )


def test_make_filter_with_choices():
    result = make_filter(
        PageSettings(key="favorites", title="Favoris", favorites_only=True),
        text="data",
        statuses=[labels.NONE_CODE, "applied"],
        letters=[labels.NONE_CODE],
        sources=["business_france"],
        countries=["ESPAGNE"],
        min_score=2,
        added_since=date(2026, 10, 1),
    )
    assert result == browsing.OfferFilter(
        sources=frozenset({"business_france"}),
        countries=frozenset({"ESPAGNE"}),
        statuses=frozenset({None, "applied"}),
        letter_statuses=frozenset({None}),
        min_score=2,
        added_since=date(2026, 10, 1),
        text="data",
        favorites_only=True,
    )


def test_default_status_choices_match_the_default_filter(at):
    statuses = at.pills(key="offers_statuses").value
    assert make_filter(PAGE, statuses=statuses) == browsing.OfferFilter()


@pytest.mark.parametrize(
    "targets, favorites, expected",
    [
        ([10, 20], {10, 20, 30}, offer_table.remove_favorite),
        ([10, 20], {10}, offer_table.add_favorite),  # a mix: all become favorites
        ([10], set(), offer_table.add_favorite),
        ([], {10}, offer_table.add_favorite),
    ],
)
def test_favorite_write(targets, favorites, expected):
    assert offer_table.favorite_write(targets, favorites) is expected


def test_one_star_for_the_checked_offers(at, db_path, ids):
    star = "offers_group_favorite"
    style = offer_card.favorite_style(star)
    at.session_state[SELECTED] = {ids["VIE1"], ids["VIE2"]}
    at.run()
    assert not [b for b in at.button if b.help == "Retirer des favoris"]
    at.button(key=star).click().run()
    stored = by_reference(db_path)
    assert stored["VIE1"].favorite and stored["VIE2"].favorite

    # All favorites: the star is yellow and removes them.
    at.session_state[SELECTED] = {ids["VIE1"], ids["VIE2"]}
    at.run()
    assert at.button(key=star).help == "Retirer des favoris"
    assert style in [h.value for h in at.get("html")]
    at.button(key=star).click().run()
    assert not by_reference(db_path)["VIE1"].favorite


def test_icon_style_covers_both_bars():
    css = offer_table.icon_style(PAGE)
    assert ".st-key-offers_actions" in css and ".st-key-offers_card_toolbar" in css
    assert offer_table.ICON_SIZE in css
