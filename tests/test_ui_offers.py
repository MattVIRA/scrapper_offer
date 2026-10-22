"""Tests of the « Offres » page and of its shared table module.

AppTest cannot check a row nor click a cell of st.dataframe: the checked
offers and the open card are set in the session state, and the decoding
of a click is tested through read_selection.
"""

import sys
from datetime import date, datetime

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from offers import browsing
from offers.__main__ import UI_APP
from offers.sources.base import FoundOffer
from offers.storage.database import connect, list_offers, save_source_result, set_status
from offers.ui import labels, offer_card, offer_table
from offers.ui.offer_table import PageSettings, make_filter, read_selection, table_frame
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


def table(at):
    return at.dataframe[0].value


def metrics(at):
    return {m.label: m.value for m in at.metric}


def button(at, label):
    return next(b for b in at.button if b.label == label)


# --- Page ---------------------------------------------------------------------


def test_page_shows_counters_and_table(at):
    assert not at.exception
    # Default filter: online offers only.
    assert list(table(at)["Titre"]) == ["Data analyst", "Poste 2", "Poste 3"]
    assert metrics(at) == {
        "Offres": "3",
        "Non lues": "3",
        "Postulées": "0",
        "Lettres à rédiger": "0",
    }


def test_filters_change_the_table(at):
    at.text_input(key="offers_text").set_value("data").run()
    assert list(table(at)["Titre"]) == ["Data analyst"]

    at.text_input(key="offers_text").set_value("").run()
    at.segmented_control(key="offers_online").set_value(browsing.ALL).run()
    assert len(table(at)) == 4

    at.number_input(key="offers_min_score").set_value(1).run()
    assert list(table(at)["Titre"]) == ["Data analyst"]
    assert metrics(at)["Offres"] == "1"


def test_search_by_reference_finds_an_offline_offer(at):
    # VIE4 is offline, hidden by the default filter.
    at.text_input(key="offers_text").set_value("vie4").run()
    assert list(table(at)["Titre"]) == ["Poste 4"]


def test_search_bar_is_above_the_list(at):
    assert "offers_text" not in [w.key for w in at.sidebar.text_input]
    assert at.text_input(key="offers_text").placeholder == offer_table.SEARCH_PLACEHOLDER


def test_no_offer_left(at):
    at.text_input(key="offers_text").set_value("introuvable").run()
    assert not at.dataframe
    assert "Aucune offre" in at.info[0].value


def test_status_saved_in_the_database_is_shown(at, db_path, ids):
    conn = connect(db_path)
    set_status(conn, [ids["VIE1"]], "applied", NOW)
    conn.close()

    at.run()
    assert metrics(at)["Postulées"] == "1"


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
    # Everything is unchecked after an action.
    assert at.session_state[SELECTED] == set()
    # The boxes of the table are unchecked too.
    assert at.session_state["offers_table"]["selection"]["rows"] == []


def test_group_letter_and_favorite(at, db_path, ids):
    at.session_state[SELECTED] = {ids["VIE2"]}
    at.run()
    at.menu_button(key="offers_letter_menu").click("to_write").run()
    at.session_state[SELECTED] = {ids["VIE2"]}
    at.run()
    button(at, "Favori").click().run()

    second = by_reference(db_path)["VIE2"]
    assert (second.letter_status, second.favorite) == ("to_write", True)
    assert metrics(at)["Lettres à rédiger"] == "1"


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
    assert list(table(at)["Titre"]) == ["Data analyst", "Poste 3"]
    assert at.success[0].value == "1 offres mises à la corbeille"

    button(at, "Annuler").click().run()

    assert not by_reference(db_path)["VIE2"].hidden
    assert len(table(at)) == 3
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
    assert metrics(at)["Non lues"] == "0"


# --- Table and filters, without Streamlit -------------------------------------


def test_table_frame():
    first = make_stored(
        1,
        status="rejected",
        letter_status="written",
        favorite=True,
        read_at=NOW,
        score=3,
    )
    second = make_stored(2, online=False)

    frame = table_frame([first, second])

    # Read-only lines: the rest (status, favorite, online, reference) is
    # in the card and in the color of the line.
    assert list(frame.columns) == offer_table.COLUMNS
    assert frame.to_dict("records")[0] == {
        "Score": 3,
        "Titre": "Data Analyst",
        "Entreprise": "ACME",
        "Source": "test",
        "Ville": "PARIS",
        "Ajoutée le": date(2026, 10, 20),
        "Lettre": "Rédigée",
    }
    assert pd.isna(frame.to_dict("records")[1]["Lettre"])


def test_table_markers():
    shown = [make_stored(1, favorite=True), make_stored(2, status="applied", favorite=True)]
    assert offer_table.table_markers(shown) == [browsing.MARKER_FAVORITE, browsing.MARKER_APPLIED]
    # No yellow on the Favorites page; blue stays.
    assert offer_table.table_markers(shown, on_favorites_page=True) == [
        browsing.NO_MARKER,
        browsing.MARKER_APPLIED,
    ]


@pytest.mark.parametrize(
    "changes, color",
    [
        ({"status": "rejected"}, "#FDE2E1"),
        ({"status": "applied"}, "#DBEAFE"),
        ({"status": "interesting"}, "#DCFCE7"),
        ({"favorite": True}, offer_card.FAVORITE_COLOR),
        ({"online": False}, "#E5E7EB"),
        ({"status": "not_for_me"}, "#FFEDD5"),
        ({"status": "rejected", "favorite": True}, "#FDE2E1"),
    ],
)
def test_whole_line_takes_the_color_of_its_marker(changes, color):
    shown = [make_stored(1, **changes)]
    frame = table_frame(shown)
    styles = offer_table.row_styles(frame.iloc[0], offer_table.table_markers(shown), [False])
    assert len(styles) == len(offer_table.COLUMNS)
    assert all(f"background-color: {color}" in style for style in styles)


def test_every_marker_has_its_color():
    markers = {*browsing.STATUS_MARKERS.values(), browsing.MARKER_FAVORITE, browsing.MARKER_OFFLINE}
    assert set(offer_table.ROW_STYLES) == markers


def test_open_line_is_highlighted_above_its_color():
    shown = [make_stored(1), make_stored(2, status="rejected")]
    frame = table_frame(shown)
    markers = offer_table.table_markers(shown)
    width = len(offer_table.COLUMNS)
    styles = offer_table.row_styles(frame.iloc[1], markers, [True, True], open_row=1)
    assert styles == [offer_table.OPEN_ROW_STYLE] * width
    assert (
        offer_table.row_styles(frame.iloc[0], markers, [False, False], open_row=1) == [""] * width
    )


def test_source_column_shows_the_label(at):
    assert set(table(at)["Source"]) == {"Business France"}


def test_line_without_marker_keeps_the_default_color():
    shown = [make_stored(1)]
    frame = table_frame(shown)
    styles = offer_table.row_styles(frame.iloc[0], offer_table.table_markers(shown), [False])
    assert set(styles) == {""}


def test_title_of_an_unread_offer_is_bold():
    shown = [make_stored(1, favorite=True)]
    frame = table_frame(shown)
    styles = offer_table.row_styles(frame.iloc[0], offer_table.table_markers(shown), [True])
    title = offer_table.COLUMNS.index(offer_table.TITLE)
    assert offer_table.UNREAD_STYLE in styles[title]
    # The color of the line is kept.
    assert offer_card.FAVORITE_COLOR in styles[title]
    others = styles[:title] + styles[title + 1 :]
    assert not any(offer_table.UNREAD_STYLE in style for style in others)


@pytest.mark.parametrize(
    "cell, clicked, expected",
    [
        ((2, "Titre"), None, True),
        ((2, "Titre"), (1, "Titre"), True),
        ((2, "Titre"), (2, "Titre"), False),  # sent again with a checked box
        (None, (2, "Titre"), False),
    ],
)
def test_is_new_click(cell, clicked, expected):
    assert offer_table.is_new_click(cell, clicked) == expected


def test_clicked_cell_is_cleared_once_its_card_is_closed(at, ids):
    at.session_state["offers_card"] = ids["VIE2"]
    at.session_state["offers_clicked"] = (1, "Titre")
    at.run()
    assert at.session_state["offers_clicked"] == (1, "Titre")

    at.button(key="offers_card_close").click().run()
    # Cleared, so that a new click on it opens the card again.
    assert at.session_state["offers_clicked"] is None
    assert at.session_state["offers_table"]["selection"]["cells"] == []


def test_read_selection():
    rows = [30, 10, 20]
    assert read_selection(rows, [0, 2], []) == ({30, 20}, None)
    # A click on a cell opens the offer of its line.
    assert read_selection(rows, [1], [(2, "Titre")]) == ({10}, 20)
    assert read_selection(rows, [], []) == (set(), None)


def test_checked_rows():
    assert offer_table.checked_rows([30, 10, 20], {20, 30, 99}) == [0, 2]


def test_checked_boxes_follow_their_offers_when_the_lines_change(at, ids):
    # Checked in the third line.
    at.session_state[SELECTED] = {ids["VIE3"]}
    # VIE3 is now the first line.
    at.text_input(key="offers_text").set_value("poste 3").run()
    assert at.session_state["offers_table"]["selection"]["rows"] == [0]


def test_action_bar_updates_the_follow_up_of_the_card(at, db_path, ids):
    at.session_state["offers_card"] = ids["VIE2"]
    at.run()
    at.menu_button(key="offers_status_menu").click("not_for_me").run()
    assert at.selectbox(key=f"offers_card_{ids['VIE2']}_status").value == "not_for_me"
    # The old value of the field is not saved back on the next run.
    at.run()
    assert by_reference(db_path)["VIE2"].status == "not_for_me"


def test_hint_without_card(at):
    assert offer_table.NO_CARD_HINT in [c.value for c in at.caption]


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
    statuses = at.multiselect(key="offers_statuses").value
    assert make_filter(PAGE, statuses=statuses) == browsing.OfferFilter()
