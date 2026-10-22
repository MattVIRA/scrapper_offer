"""Offer list shared by the Offres, Favoris and Corbeille pages.

Filters in the sidebar, counters, actions on the checked offers and the
table. The checked offers live in the session state, not in the table:
the table only shows them, so the page always knows what is checked.
"""

import zlib
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
FAVORITE_MARK = "★"
TRASH_ICON = ":material/delete:"
RESTORE_ICON = ":material/restore_from_trash:"
DATE_FORMAT = "DD/MM/YYYY"

# Table columns.
UNREAD = "Non lu"
DUPLICATE = "Doublon de"
STATUS = "Statut"
# fmt: off
COLUMNS = [
    UNREAD, DUPLICATE, "Score", "Titre", "Entreprise", "Source", "Pays", "Ville",
    "Durée", "Publiée le", "Ajoutée le", STATUS, "Lettre", "Favori", "En ligne",
]
# fmt: on
# Background of a whole line, by marker: light colors with dark text, so
# that the lines stay readable with the dark theme too.
TEXT_COLOR = "#1F2937"
# fmt: off
ROW_STYLES = {
    browsing.MARKER_REJECTED: f"background-color: #FDE2E1; color: {TEXT_COLOR}",
    browsing.MARKER_APPLIED:    f"background-color: #DBEAFE; color: {TEXT_COLOR}",
    browsing.MARKER_NOT_FOR_ME: f"background-color: #FFEDD5; color: {TEXT_COLOR}",
    browsing.MARKER_FAVORITE:   f"background-color: #FEF3C7; color: {TEXT_COLOR}",
    browsing.MARKER_OFFLINE:    "background-color: #E5E7EB; color: #6B7280",
}
# fmt: on
# The line whose card is open, above the color of its follow-up.
OPEN_ROW_STYLE = "background-color: #4F46E5; color: #FFFFFF; font-weight: bold"
# Widths of the list and of the card beside it.
LIST_AND_CARD = [3, 2]


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
    offer_filter = filter_sidebar(offers, settings)
    shown = browsing.filter_offers(offers, offer_filter)
    show_counters(shown)
    show_undo(settings)
    show_actions(settings, shown)
    card = opened_offer(settings, offers)
    if card is None:
        show_table(settings, shown, tags)
        return
    # The description beside the list, the follow-up under it: the list
    # stays visible and clickable.
    list_column, card_column = st.columns(LIST_AND_CARD, gap="medium")
    with list_column:
        show_table(settings, shown, tags, open_id=card.id)
        offer_card.show_follow_up_panel(settings, card, editable=not settings.in_trash)
    with card_column:
        show_card(settings, card, shown, tags)


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


def filter_sidebar(offers, settings):
    """Show the filters in the sidebar and return the chosen OfferFilter.

    The filters are not kept from one opening of the app to the next.
    """
    choices = browsing.filter_choices(offers)
    key = settings.state_key
    with st.sidebar:
        st.header("Filtres")
        text = st.text_input("Titre ou entreprise", key=key("text"))
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


def show_actions(settings, shown):
    """Show the actions on the checked offers, and "Tout marquer comme lu"."""
    shown_ids = {stored.id for stored in shown}
    # A checked offer hidden by a filter is not changed.
    checked = sorted(st.session_state[settings.state_key("selected")] & shown_ids)
    nothing_checked = not checked
    key = settings.state_key
    with st.container(horizontal=True, vertical_alignment="center"):
        st.caption(f"{len(checked)} cochées")
        if settings.in_trash:
            action_button(settings, "Restaurer", RESTORE_ICON, checked, restore)
            return
        st.menu_button(
            "Statut",
            list(STATUSES),
            format_func=status_label,
            icon=":material/label:",
            disabled=nothing_checked,
            key=key("status_menu"),
            on_click=act_from_menu,
            args=(settings, key("status_menu"), checked, write_status),
        )
        st.menu_button(
            "Lettre",
            LETTER_CHOICES,
            format_func=letter_choice_label,
            icon=":material/edit_note:",
            disabled=nothing_checked,
            key=key("letter_menu"),
            on_click=act_from_menu,
            args=(settings, key("letter_menu"), checked, write_letter_status),
        )
        action_button(settings, "Favori", ":material/star:", checked, add_favorite)
        action_button(settings, "Retirer des favoris", ":material/star_border:", checked,
                      remove_favorite)  # fmt: skip
        action_button(settings, "Marquer comme lu", ":material/done:", checked, mark_read)
        action_button(settings, "Corbeille", TRASH_ICON, checked, hide, trashed=True)
        st.button(
            "Tout marquer comme lu",
            icon=":material/done_all:",
            disabled=not shown,
            key=key("read_all"),
            on_click=act,
            args=(settings, mark_read, sorted(shown_ids)),
        )


def action_button(settings, label, icon, checked, write, trashed=False):
    """Button that applies write(conn, ids, now) to the checked offers."""
    st.button(
        label,
        icon=icon,
        disabled=not checked,
        key=settings.state_key(label),
        on_click=act,
        args=(settings, write, checked),
        kwargs={"trashed": trashed},
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


def act(settings, write: Callable, offer_ids, trashed=False):
    """Write an action, uncheck everything, and keep the trash to undo it."""
    with open_database(st.session_state.db_path) as conn:
        write(conn, offer_ids, datetime.now())
    st.session_state[settings.state_key("selected")] = set()
    st.session_state[settings.state_key("trashed")] = list(offer_ids) if trashed else None
    uncheck_table(settings)


def uncheck_table(settings):
    """Uncheck the boxes of the table shown, to match the empty selection."""
    key = st.session_state.get(settings.state_key("table_key"))
    if key is not None:
        st.session_state[key] = {"selection": {"rows": [], "cells": []}}


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


def show_table(settings, shown, tags, open_id=None):
    """Show the offers as read-only lines, colored by their follow-up.

    The boxes on the left check offers for the actions; a click on a cell
    opens the card of its line. open_id: offer whose card is open, its
    line is highlighted.
    """
    if not shown:
        st.info("Aucune offre ne correspond aux filtres.", icon=":material/filter_alt_off:")
        return
    row_ids = [stored.id for stored in shown]
    # The callback finds the offers from the row numbers.
    st.session_state[settings.state_key("rows")] = row_ids
    key = table_key(settings, row_ids)
    st.session_state[settings.state_key("table_key")] = key
    frame = table_frame(shown, tags)
    checked = st.session_state[settings.state_key("selected")]
    open_row = row_ids.index(open_id) if open_id in row_ids else None
    markers = table_markers(shown, on_favorites_page=settings.favorites_only)
    st.dataframe(
        frame.style.apply(row_styles, axis=1, markers=markers, open_row=open_row),
        key=key,
        # st.dataframe takes no args for its callback.
        on_select=partial(on_table_select, settings, key),
        selection_mode=["multi-row", "single-cell"],
        selection_default={
            "selection": {"rows": [n for n, i in enumerate(row_ids) if i in checked]}
        },
        hide_index=True,
        column_config=column_config(),
        alt="Offres filtrées, avec leur suivi",
    )


def table_key(settings, row_ids):
    """Key of the table: a new table, with the checked boxes, when the lines change.

    The table selects rows by their number: after a filter, the same
    numbers would point to other offers.
    """
    return settings.state_key(f"table_{zlib.crc32(repr(row_ids).encode())}")


def column_config():
    return {
        UNREAD: st.column_config.CheckboxColumn(UNREAD, width="small"),
        DUPLICATE: st.column_config.TextColumn(DUPLICATE, help="Doublons probables"),
        "Score": st.column_config.NumberColumn("Score", width="small"),
        "Titre": st.column_config.TextColumn("Titre", width="large", pinned=True),
        "Publiée le": st.column_config.DateColumn("Publiée le", format=DATE_FORMAT),
        "Ajoutée le": st.column_config.DateColumn("Ajoutée le", format=DATE_FORMAT),
        "Favori": st.column_config.TextColumn("Favori", width="small"),
        "En ligne": st.column_config.CheckboxColumn("En ligne", width="small"),
    }


def table_markers(shown, on_favorites_page=False):
    """Return the marker of each offer shown, which gives the color of its line."""
    return [browsing.marker(stored, on_favorites_page) for stored in shown]


def table_frame(shown, tags):
    """Return the table of the offers shown, one row per offer, in their order.

    tags: {offer id: references of its probable duplicates}.
    """
    rows = [table_row(stored, tags) for stored in shown]
    return pd.DataFrame(rows, columns=COLUMNS)


def table_row(stored, tags):
    offer = stored.offer
    return {
        UNREAD: browsing.is_unread(stored),
        DUPLICATE: ", ".join(tags.get(stored.id, [])),
        "Score": stored.score,
        "Titre": offer.title,
        "Entreprise": offer.company,
        "Source": source_label(offer.source),
        "Pays": offer.country,
        "Ville": offer.city,
        "Durée": offer.duration_months,
        "Publiée le": offer.published_on,
        "Ajoutée le": stored.first_seen.date(),
        STATUS: status_label(stored.status) if stored.status else None,
        "Lettre": letter_label(stored.letter_status) if stored.letter_status else None,
        "Favori": FAVORITE_MARK if stored.favorite else "",
        "En ligne": stored.online,
    }


def row_styles(row, markers, open_row=None):
    """Return the CSS of each cell of a table row: the color of its marker.

    markers: marker of each row (table_markers); row.name is its number.
    open_row: number of the row whose card is open, highlighted instead.
    """
    if row.name == open_row:
        return [OPEN_ROW_STYLE] * len(row)
    return [ROW_STYLES.get(markers[row.name], "")] * len(row)


def on_table_select(settings, key):
    """Callback of the table: keep the checked offers, open the clicked one."""
    selection = st.session_state[key].selection
    row_ids = st.session_state[settings.state_key("rows")]
    checked, opened = read_selection(row_ids, selection.rows, selection.cells)
    st.session_state[settings.state_key("selected")] = checked
    if opened is not None:
        offer_card.open_card(settings, opened)
        # Unselect the cell, so that the same offer can be opened again.
        st.session_state[key] = {"selection": {"rows": list(selection.rows), "cells": []}}


def read_selection(row_ids, rows, cells):
    """Return (checked offer ids, id of the clicked offer or None).

    row_ids: offer id of each row of the table.
    rows: numbers of the checked rows; cells: (row number, column) clicked.
    """
    checked = {row_ids[row] for row in rows}
    opened = row_ids[cells[0][0]] if cells else None
    return checked, opened
