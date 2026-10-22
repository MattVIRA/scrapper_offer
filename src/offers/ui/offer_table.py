"""Offer list shared by the Offres, Favoris and Corbeille pages.

Filters in the sidebar, counters, actions on the checked offers and the
table. The checked offers live in the session state, not in the table:
the table only shows them, so the page always knows what is checked.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import partial

import pandas as pd
import streamlit as st

from offers import browsing
from offers.browsing import OfferFilter
from offers.sources import source_label
from offers.storage.database import (
    hide,
    list_offers,
    mark_read,
    probable_duplicates,
    restore,
    set_favorite,
    set_letter_status,
    set_status,
)
from offers.tracking import STATUSES, letter_label, status_label
from offers.ui import offer_card
from offers.ui.labels import (
    LETTER_CHOICES,
    STATUS_CHOICES,
    letter_choice_label,
    status_choice_label,
    to_database_code,
    to_widget_code,
)
from offers.ui.session import open_database

ONLINE_LABELS = {
    browsing.ONLINE: "En ligne",
    browsing.OFFLINE: "Hors ligne",
    browsing.ALL: "Toutes",
}
TRASH_ICON = ":material/delete:"
RESTORE_ICON = ":material/restore_from_trash:"
DATE_FORMAT = "DD/MM/YYYY"
SEARCH_PLACEHOLDER = "Titre, entreprise, ville, pays ou réf. (VIE243542)"
# Pause in the typing before the list is filtered.
SEARCH_DELAY = "300ms"

# Table columns: the rest is in the card. The status, favorite and
# online state are given by the color of the line.
TITLE = "Titre"
COLUMNS = ["Score", TITLE, "Entreprise", "Source", "Ville", "Ajoutée le", "Lettre"]
# Title of an offer never opened.
UNREAD_STYLE = "font-weight: bold"
# Background of a whole line, by marker: light colors with dark text, so
# that the lines stay readable with the dark theme too.
TEXT_COLOR = "#1F2937"
# Same yellow as the « Favori » button of the card.
FAVORITE_COLOR = offer_card.FAVORITE_COLOR
# fmt: off
ROW_STYLES = {
    browsing.MARKER_REJECTED:    f"background-color: #FDE2E1; color: {TEXT_COLOR}",
    browsing.MARKER_APPLIED:     f"background-color: #DBEAFE; color: {TEXT_COLOR}",
    browsing.MARKER_NOT_FOR_ME:  f"background-color: #FFEDD5; color: {TEXT_COLOR}",
    browsing.MARKER_INTERESTING: f"background-color: #DCFCE7; color: {TEXT_COLOR}",
    browsing.MARKER_FAVORITE:    f"background-color: {FAVORITE_COLOR}; color: {TEXT_COLOR}",
    browsing.MARKER_OFFLINE:     "background-color: #E5E7EB; color: #6B7280",
}
# fmt: on
# The line whose card is open, above the color of its follow-up.
OPEN_ROW_STYLE = "background-color: #4F46E5; color: #FFFFFF; font-weight: bold"
# Widths of the list and of the card beside it.
LIST_AND_CARD = [3, 2]
NO_CARD_HINT = "Cliquer sur une ligne pour ouvrir sa fiche."


@dataclass(frozen=True)
class PageSettings:
    """What changes from one list page to another."""

    # Prefix of the widget and session state keys of the page.
    key: str
    title: str
    favorites_only: bool = False
    # The trash page: hidden offers, which can only be restored.
    in_trash: bool = False
    # Number of offers of the page in its title (Favoris, Corbeille).
    count_in_title: bool = False

    def state_key(self, name):
        return f"{self.key}_{name}"

    def default_statuses(self):
        # The trash is often made of offers the user did not want.
        return frozenset({None, *STATUSES}) if self.in_trash else browsing.DEFAULT_STATUSES

    def default_online(self):
        return browsing.ALL if self.in_trash else browsing.ONLINE


def show_offer_page(settings):
    """Show the whole list page: filters, counters, actions and table."""
    st.session_state.setdefault(settings.state_key("selected"), set())
    with open_database(st.session_state.db_path) as conn:
        offers = list_offers(conn)
        if mark_card_read(conn, settings, offers):
            # Read again, for the counters and the table.
            offers = list_offers(conn)
        tags = browsing.duplicate_tags(probable_duplicates(conn))
    st.title(page_title(settings, offers))
    text = search_bar(settings)
    offer_filter = filter_sidebar(offers, settings, text)
    shown = browsing.filter_offers(offers, offer_filter)
    show_counters(shown)
    show_undo(settings)
    card = opened_offer(settings, offers)
    show_actions(settings, shown, card.id if card else None)
    # The description beside the list, the follow-up under it: the list
    # stays visible and clickable. The same columns with or without card,
    # so that the table is not drawn again from its top on opening one.
    list_column, card_column = st.columns(LIST_AND_CARD, gap="medium")
    with list_column:
        show_table(settings, shown, open_id=card.id if card else None)
        if card:
            offer_card.show_follow_up_panel(settings, card, editable=not settings.in_trash)
    with card_column:
        if card:
            show_card(settings, card, shown, tags)
        else:
            st.caption(NO_CARD_HINT)


def page_title(settings, offers):
    """Return the title of the page, with its number of offers if wanted."""
    if not settings.count_in_title:
        return settings.title
    whole_page = OfferFilter(
        statuses=frozenset({None, *STATUSES}),
        online=browsing.ALL,
        favorites_only=settings.favorites_only,
        in_trash=settings.in_trash,
    )
    return f"{settings.title} ({len(browsing.filter_offers(offers, whole_page))})"


def opened_offer(settings, offers):
    """Return the StoredOffer whose card is open, or None."""
    card_id = st.session_state.get(offer_card.card_key(settings))
    return next((stored for stored in offers if stored.id == card_id), None)


def mark_card_read(conn, settings, offers):
    """Mark as read the offer whose card is open; tell whether it changed.

    A card whose offer is no longer in the database is closed.
    """
    stored = opened_offer(settings, offers)
    if stored is None:
        offer_card.close_card(settings)
        return False
    if not browsing.is_unread(stored):
        return False
    mark_read(conn, [stored.id], datetime.now())
    return True


def show_card(settings, stored, shown, tags):
    """Show the card of an offer, with arrows to the offers shown."""
    offer_card.show_card(
        settings,
        stored,
        tags.get(stored.id, []),
        card_action(settings),
        editable=not settings.in_trash,
        navigation=offer_card.navigation([s.id for s in shown], stored.id),
    )


def card_action(settings):
    """Button of the card: restore in the trash, move to the trash elsewhere."""
    if settings.in_trash:
        return offer_card.CardAction(
            "Restaurer",
            RESTORE_ICON,
            lambda offer_ids: act(settings, restore, offer_ids),
        )
    return offer_card.CardAction(
        "Mettre à la corbeille",
        TRASH_ICON,
        lambda offer_ids: act(settings, hide, offer_ids, trashed=True),
    )


# --- Filters ------------------------------------------------------------------


def search_bar(settings):
    """Show the search bar above the list and return the text typed."""
    return st.text_input(
        "Rechercher",
        type="search",
        placeholder=SEARCH_PLACEHOLDER,
        live=SEARCH_DELAY,
        label_visibility="collapsed",
        key=settings.state_key("text"),
    )


def filter_sidebar(offers, settings, text):
    """Show the filters in the sidebar and return the chosen OfferFilter.

    text: typed in the search bar. The filters are not kept from one
    opening of the app to the next.
    """
    choices = browsing.filter_choices(offers)
    key = settings.state_key
    with st.sidebar:
        st.header("Filtres")
        statuses = st.multiselect(
            "Statut",
            STATUS_CHOICES,
            default=sorted(map(to_widget_code, settings.default_statuses()), key=status_order),
            format_func=status_choice_label,
            placeholder="Tous",
            key=key("statuses"),
        )
        letters = st.multiselect(
            "Lettre",
            LETTER_CHOICES,
            format_func=letter_choice_label,
            placeholder="Toutes",
            key=key("letters"),
        )
        online = st.segmented_control(
            "En ligne",
            list(ONLINE_LABELS),
            default=settings.default_online(),
            format_func=ONLINE_LABELS.get,
            key=key("online"),
        )
        sources = st.multiselect(
            "Source",
            choices.sources,
            format_func=source_label,
            placeholder="Toutes",
            key=key("sources"),
        )
        countries = st.multiselect(
            "Pays", choices.countries, placeholder="Tous", key=key("countries")
        )
        min_score = st.number_input("Score minimum", min_value=0, step=1, key=key("min_score"))
        added_since = st.date_input(
            "Ajoutée depuis le", value=None, format="DD/MM/YYYY", key=key("added_since")
        )
    return make_filter(
        settings,
        text=text,
        statuses=statuses,
        letters=letters,
        online=online,
        sources=sources,
        countries=countries,
        min_score=min_score,
        added_since=added_since,
    )


def make_filter(
    settings,
    text="",
    statuses=(),
    letters=(),
    online=browsing.ONLINE,
    sources=(),
    countries=(),
    min_score=0,
    added_since=None,
):
    """Return the OfferFilter of the values of the filter widgets.

    An empty choice means no filter; NONE_CODE stands for "no status" or
    "no letter"; a score of 0 and a cleared "online" choice filter nothing.
    """
    return OfferFilter(
        sources=frozenset(sources) or None,
        countries=frozenset(countries) or None,
        statuses=frozenset(map(to_database_code, statuses)) or frozenset({None, *STATUSES}),
        letter_statuses=frozenset(map(to_database_code, letters)) or None,
        min_score=min_score or None,
        online=online or browsing.ALL,
        added_since=added_since,
        text=text,
        favorites_only=settings.favorites_only,
        in_trash=settings.in_trash,
    )


def status_order(code):
    """Sort the status choices as in STATUSES, "no status" first."""
    return STATUS_CHOICES.index(code)


# --- Counters -----------------------------------------------------------------


def show_counters(shown):
    """Show the counters of the offers shown."""
    numbers = browsing.counters(shown)
    metrics = {
        "Offres": numbers.total,
        "Non lues": numbers.unread,
        "Postulées": numbers.by_status.get("applied", 0),
        "Lettres à rédiger": numbers.letters_to_write,
    }
    for column, (label, value) in zip(st.columns(len(metrics)), metrics.items()):
        column.metric(label, value, border=True)


# --- Actions ------------------------------------------------------------------


def show_actions(settings, shown, open_id=None):
    """Show the actions on the checked offers, and "Tout marquer comme lu".

    With no offer checked, the actions apply to the open one (open_id).
    """
    shown_ids = [stored.id for stored in shown]
    checked = st.session_state[settings.state_key("selected")]
    targets = action_targets(checked, open_id, shown_ids)
    nothing_checked = not targets
    # Once the open offer leaves the list, the card goes to the next one.
    leaving = {"move_card": True, "next_card": next_card(targets, open_id, shown_ids)}
    key = settings.state_key
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(targets_caption(checked & set(shown_ids), targets))
        if settings.in_trash:
            action_button(settings, "Restaurer", RESTORE_ICON, targets, restore, **leaving)
            return
        st.menu_button(
            "Statut",
            list(STATUSES),
            format_func=status_label,
            icon=":material/label:",
            disabled=nothing_checked,
            key=key("status_menu"),
            on_click=act_from_menu,
            args=(settings, key("status_menu"), targets, write_status),
        )
        st.menu_button(
            "Lettre",
            LETTER_CHOICES,
            format_func=letter_choice_label,
            icon=":material/edit_note:",
            disabled=nothing_checked,
            key=key("letter_menu"),
            on_click=act_from_menu,
            args=(settings, key("letter_menu"), targets, write_letter_status),
        )
        action_button(settings, "Favori", ":material/star:", targets, add_favorite)
        action_button(settings, "Retirer des favoris", ":material/star_border:", targets,
                      remove_favorite)  # fmt: skip
        action_button(settings, "Marquer comme lu", ":material/done:", targets, mark_read)
        action_button(settings, "Corbeille", TRASH_ICON, targets, hide, trashed=True, **leaving)
        st.button(
            "Tout marquer comme lu",
            icon=":material/done_all:",
            disabled=not shown,
            key=key("read_all"),
            on_click=act,
            args=(settings, mark_read, sorted(shown_ids)),
        )


def action_targets(checked, open_id, shown_ids):
    """Return the ids of the offers the actions apply to, sorted.

    The checked offers shown (a checked offer hidden by a filter is not
    changed); with none checked, the open offer if shown.
    """
    targets = sorted(set(checked) & set(shown_ids))
    if not targets and open_id in shown_ids:
        return [open_id]
    return targets


def targets_caption(checked_shown, targets):
    """Return the text before the actions: what they apply to."""
    if targets and not checked_shown:
        return "Ligne ouverte"
    return f"{len(checked_shown)} cochées"


def next_card(targets, open_id, shown_ids):
    """Return the offer to open if the open one leaves the list by an action.

    open_id when it is not among the targets; None closes the card.
    """
    if open_id not in targets:
        return open_id
    return offer_card.following_offer(offer_card.navigation(shown_ids, open_id))


def action_button(settings, label, icon, targets, write, **options):
    """Button that applies write(conn, ids, now) to the target offers.

    options: those of act.
    """
    st.button(
        label,
        icon=icon,
        disabled=not targets,
        key=settings.state_key(label),
        on_click=act,
        args=(settings, write, targets),
        kwargs=options,
    )


def write_status(conn, offer_ids, code, now):
    set_status(conn, offer_ids, code, now)


def write_letter_status(conn, offer_ids, code, now):
    set_letter_status(conn, offer_ids, to_database_code(code), now)


def add_favorite(conn, offer_ids, now):
    set_favorite(conn, offer_ids, True, now)


def remove_favorite(conn, offer_ids, now):
    set_favorite(conn, offer_ids, False, now)


def act_from_menu(settings, menu_key, offer_ids, write):
    """Apply the option chosen in a menu: write(conn, ids, option, now)."""
    option = st.session_state[menu_key]
    act(settings, lambda conn, ids, now: write(conn, ids, option, now), offer_ids)


def act(settings, write: Callable, offer_ids, trashed=False, move_card=False, next_card=None):
    """Write an action, uncheck everything, and keep the trash to undo it.

    move_card: the offers leave the list; the card then shows next_card,
    or closes if None.
    """
    with open_database(st.session_state.db_path) as conn:
        write(conn, offer_ids, datetime.now())
        changed = [stored for stored in list_offers(conn) if stored.id in offer_ids]
    # The follow-up fields of the card show the new values.
    offer_card.refresh_fields(settings, changed)
    st.session_state[settings.state_key("selected")] = set()
    st.session_state[settings.state_key("trashed")] = list(offer_ids) if trashed else None
    uncheck_table(settings)
    if move_card and next_card is None:
        offer_card.close_card(settings)
    elif move_card:
        offer_card.open_card(settings, next_card)


def uncheck_table(settings):
    """Uncheck the boxes of the table shown, to match the empty selection."""
    reset_table(settings, [])


def reset_table(settings, rows):
    """Set the selection of the table: rows checked, no cell clicked.

    The browser ignores a selection equal to the last one sent, so the
    clicked cell is kept between clicks, and only cleared when needed.
    """
    st.session_state[table_key(settings)] = {"selection": {"rows": rows, "cells": []}}
    st.session_state[settings.state_key("clicked")] = None


def show_undo(settings):
    """After a move to the trash, offer to undo it, until the next action."""
    trashed = st.session_state.get(settings.state_key("trashed"))
    if not trashed:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.success(f"{len(trashed)} offres mises à la corbeille", icon=TRASH_ICON)
        st.button(
            "Annuler",
            icon=":material/undo:",
            key=settings.state_key("undo"),
            on_click=act,
            args=(settings, restore, trashed),
        )


# --- Table --------------------------------------------------------------------


def show_table(settings, shown, open_id=None):
    """Show the offers as read-only lines, colored by their follow-up, the
    titles of the unread ones in bold.

    The boxes on the left check offers for the actions; a click on a cell
    opens the card of its line. open_id: offer whose card is open, its
    line is highlighted.
    """
    if not shown:
        st.info("Aucune offre ne correspond aux filtres.", icon=":material/filter_alt_off:")
        return
    row_ids = [stored.id for stored in shown]
    key = table_key(settings)
    checked = st.session_state[settings.state_key("selected")]
    previous_ids = st.session_state.get(settings.state_key("rows"))
    clicked = st.session_state.get(settings.state_key("clicked"))
    # The table selects rows by their number: after a change of the lines,
    # the same numbers would point to other offers. A cell clicked on
    # another line than the open one (card closed, arrows) is cleared, so
    # that it can open its offer again.
    if (
        key not in st.session_state
        or previous_ids != row_ids
        or (clicked is not None and row_ids[clicked[0]] != open_id)
    ):
        reset_table(settings, checked_rows(row_ids, checked))
    # The callback finds the offers from the row numbers.
    st.session_state[settings.state_key("rows")] = row_ids
    frame = table_frame(shown)
    open_row = row_ids.index(open_id) if open_id in row_ids else None
    markers = table_markers(shown, on_favorites_page=settings.favorites_only)
    unread = [browsing.is_unread(stored) for stored in shown]
    st.dataframe(
        frame.style.apply(row_styles, axis=1, markers=markers, unread=unread, open_row=open_row),
        key=key,
        # st.dataframe takes no args for its callback.
        on_select=partial(on_table_select, settings, key),
        selection_mode=["multi-row", "single-cell"],
        hide_index=True,
        column_config=column_config(),
        alt="Offres filtrées, avec leur suivi",
    )


def table_key(settings):
    """Key of the table: always the same, so that it keeps its scroll position."""
    return settings.state_key("table")


def checked_rows(row_ids, checked):
    """Return the numbers of the rows whose offer is checked."""
    return [number for number, offer_id in enumerate(row_ids) if offer_id in checked]


def column_config():
    return {
        "Score": st.column_config.NumberColumn("Score", width="small"),
        TITLE: st.column_config.TextColumn(TITLE, width="large", pinned=True),
        "Ajoutée le": st.column_config.DateColumn("Ajoutée le", format=DATE_FORMAT),
    }


def table_markers(shown, on_favorites_page=False):
    """Return the marker of each offer shown, which gives the color of its line."""
    return [browsing.marker(stored, on_favorites_page) for stored in shown]


def table_frame(shown):
    """Return the table of the offers shown, one row per offer, in their order."""
    return pd.DataFrame([table_row(stored) for stored in shown], columns=COLUMNS)


def table_row(stored):
    offer = stored.offer
    return {
        "Score": stored.score,
        TITLE: offer.title,
        "Entreprise": offer.company,
        "Source": source_label(offer.source),
        "Ville": offer.city,
        "Ajoutée le": stored.first_seen.date(),
        "Lettre": letter_label(stored.letter_status) if stored.letter_status else None,
    }


def row_styles(row, markers, unread, open_row=None):
    """Return the CSS of each cell of a table row: the color of its marker,
    and the title in bold if unread.

    markers, unread: marker and unread state of each row; row.name is its number.
    open_row: number of the row whose card is open, highlighted instead.
    """
    if row.name == open_row:
        return [OPEN_ROW_STYLE] * len(row)
    styles = [ROW_STYLES.get(markers[row.name], "")] * len(row)
    if unread[row.name]:
        title = COLUMNS.index(TITLE)
        styles[title] = "; ".join(part for part in (styles[title], UNREAD_STYLE) if part)
    return styles


def on_table_select(settings, key):
    """Callback of the table: keep the checked offers, open the clicked one."""
    selection = st.session_state[key].selection
    row_ids = st.session_state[settings.state_key("rows")]
    checked, opened = read_selection(row_ids, selection.rows, selection.cells)
    st.session_state[settings.state_key("selected")] = checked
    cell = tuple(selection.cells[0]) if selection.cells else None
    if is_new_click(cell, st.session_state.get(settings.state_key("clicked"))):
        offer_card.open_card(settings, opened)
    st.session_state[settings.state_key("clicked")] = cell


def is_new_click(cell, clicked):
    """Tell whether cell (row number, column) was just clicked.

    clicked: the cell already selected. It stays selected after its click,
    and a change of the checked boxes sends it again.
    """
    return cell is not None and cell != clicked


def read_selection(row_ids, rows, cells):
    """Return (checked offer ids, id of the clicked offer or None).

    row_ids: offer id of each row of the table.
    rows: numbers of the checked rows; cells: (row number, column) clicked.
    """
    checked = {row_ids[row] for row in rows}
    opened = row_ids[cells[0][0]] if cells else None
    return checked, opened
