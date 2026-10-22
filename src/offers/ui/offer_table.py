"""Offer list shared by the Offres, Favoris and Corbeille pages.

Filters in the sidebar, counters, actions on the checked offers and the
table. The checked offers live in the session state, not in the table:
the table only shows them, so the page always knows what is checked.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

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
OPEN_LABEL = ":material/open_in_new: Ouvrir"
DATE_FORMAT = "DD/MM/YYYY"

# Table columns.
CHOOSE = "Choisir"
MARKER = "Repère"
UNREAD = "Non lu"
DUPLICATE = "Doublon de"
STATUS = "Statut"
OPEN = "Ouvrir"
# fmt: off
COLUMNS = [
    CHOOSE, MARKER, UNREAD, DUPLICATE, "Score", "Titre", "Entreprise", "Pays", "Ville",
    "Durée", "Publiée le", "Ajoutée le", STATUS, "Lettre", "Favori", "En ligne", OPEN,
]
# fmt: on
# The only columns the user can change in the table.
EDITABLE = {CHOOSE, STATUS}


@dataclass(frozen=True)
class PageSettings:
    """What changes from one list page to another."""

    # Prefix of the widget and session state keys of the page.
    key: str
    favorites_only: bool = False
    in_trash: bool = False

    def state_key(self, name):
        return f"{self.key}_{name}"


def show_offer_page(settings):
    """Show the whole list page: filters, counters, actions and table."""
    st.session_state.setdefault(settings.state_key("selected"), set())
    with open_database(st.session_state.db_path) as conn:
        offers = list_offers(conn)
        if mark_card_read(conn, settings, offers):
            # Read again, for the counters and the table.
            offers = list_offers(conn)
        tags = browsing.duplicate_tags(probable_duplicates(conn))
    offer_filter = filter_sidebar(offers, settings)
    shown = browsing.filter_offers(offers, offer_filter)
    show_counters(shown)
    show_undo(settings)
    show_actions(settings, shown)
    show_table(settings, shown, tags)
    show_open_card(settings, offers, tags)


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


def show_open_card(settings, offers, tags):
    """Show the card of the opened offer, if any."""
    stored = opened_offer(settings, offers)
    if stored is None:
        return
    offer_card.show_card(
        settings,
        stored,
        tags.get(stored.id, []),
        on_trash=lambda offer_ids: act(settings, hide, offer_ids, trashed=True),
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
            default=sorted(map(to_widget_code, browsing.DEFAULT_STATUSES), key=status_order),
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
            default=browsing.ONLINE,
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
        "À voir": numbers.by_status.get("to_review", 0),
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
        action_button(settings, "Corbeille", ":material/delete:", checked, hide, trashed=True)
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


def show_undo(settings):
    """After a move to the trash, offer to undo it, until the next action."""
    trashed = st.session_state.get(settings.state_key("trashed"))
    if not trashed:
        return
    with st.container(horizontal=True, vertical_alignment="center"):
        st.success(f"{len(trashed)} offres mises à la corbeille", icon=":material/delete:")
        st.button(
            "Annuler",
            icon=":material/undo:",
            key=settings.state_key("undo"),
            on_click=act,
            args=(settings, restore, trashed),
        )


# --- Table --------------------------------------------------------------------


def show_table(settings, shown, tags):
    """Show the table; a status changed in it is saved at once."""
    if not shown:
        st.info("Aucune offre ne correspond aux filtres.", icon=":material/filter_alt_off:")
        return
    selected = st.session_state[settings.state_key("selected")]
    # The table callbacks find the offers from the row numbers.
    st.session_state[settings.state_key("rows")] = [stored.id for stored in shown]
    st.data_editor(
        table_frame(shown, tags, selected, on_favorites_page=settings.favorites_only),
        key=settings.state_key("table"),
        on_change=save_table_changes,
        args=(settings,),
        hide_index=True,
        disabled=[column for column in COLUMNS if column not in EDITABLE],
        column_config=column_config(settings),
        alt="Offres filtrées, avec leur suivi",
    )


def column_config(settings):
    return {
        CHOOSE: st.column_config.CheckboxColumn(CHOOSE, width="small", pinned=True),
        MARKER: st.column_config.TextColumn(MARKER, width="small", pinned=True),
        UNREAD: st.column_config.CheckboxColumn(UNREAD, width="small"),
        DUPLICATE: st.column_config.TextColumn(DUPLICATE, help="Doublons probables"),
        "Score": st.column_config.NumberColumn("Score", width="small"),
        "Titre": st.column_config.TextColumn("Titre", width="large"),
        "Publiée le": st.column_config.DateColumn("Publiée le", format=DATE_FORMAT),
        "Ajoutée le": st.column_config.DateColumn("Ajoutée le", format=DATE_FORMAT),
        STATUS: st.column_config.SelectboxColumn(
            STATUS, options=list(STATUSES), format_func=status_label, required=False
        ),
        "Favori": st.column_config.TextColumn("Favori", width="small"),
        "En ligne": st.column_config.CheckboxColumn("En ligne", width="small"),
        OPEN: st.column_config.ButtonColumn(
            OPEN,
            type="tertiary",
            key=settings.state_key("open"),
            on_click=open_offer,
            args=(settings,),
        ),
    }


def table_frame(shown, tags, selected, on_favorites_page=False):
    """Return the table of the offers shown, one row per offer, in their order.

    tags: {offer id: references of its probable duplicates}.
    selected: ids of the checked offers.
    """
    rows = [table_row(stored, tags, selected, on_favorites_page) for stored in shown]
    return pd.DataFrame(rows, columns=COLUMNS)


def table_row(stored, tags, selected, on_favorites_page):
    offer = stored.offer
    return {
        CHOOSE: stored.id in selected,
        MARKER: browsing.marker(stored, on_favorites_page),
        UNREAD: browsing.is_unread(stored),
        DUPLICATE: ", ".join(tags.get(stored.id, [])),
        "Score": stored.score,
        "Titre": offer.title,
        "Entreprise": offer.company,
        "Pays": offer.country,
        "Ville": offer.city,
        "Durée": offer.duration_months,
        "Publiée le": offer.published_on,
        "Ajoutée le": stored.first_seen.date(),
        STATUS: stored.status,
        "Lettre": letter_label(stored.letter_status) if stored.letter_status else None,
        "Favori": FAVORITE_MARK if stored.favorite else "",
        "En ligne": stored.online,
        OPEN: OPEN_LABEL,
    }


def save_table_changes(settings):
    """Callback of the table: save the statuses, keep the checked offers."""
    edited_rows = st.session_state[settings.state_key("table")]["edited_rows"]
    selected_key = settings.state_key("selected")
    with open_database(st.session_state.db_path) as conn:
        st.session_state[selected_key] = apply_table_changes(
            conn,
            st.session_state[settings.state_key("rows")],
            edited_rows,
            st.session_state[selected_key],
            datetime.now(),
        )
    if any(STATUS in changes for changes in edited_rows.values()):
        st.session_state[settings.state_key("trashed")] = None


def apply_table_changes(conn, row_ids, edited_rows, selected, now):
    """Apply the cells changed in the table; return the checked offers.

    row_ids: offer id of each row of the table.
    edited_rows: {row number: {column: new value}}, as given by st.data_editor.
    """
    selected = set(selected)
    for row, changes in edited_rows.items():
        offer_id = row_ids[int(row)]
        if CHOOSE in changes:
            if changes[CHOOSE]:
                selected.add(offer_id)
            else:
                selected.discard(offer_id)
        if STATUS in changes:
            set_status(conn, [offer_id], changes[STATUS] or None, now)
    return selected


def open_offer(settings):
    """Callback of the "Ouvrir" button: open the card of the offer of that row."""
    row = st.session_state[settings.state_key("open")]["row"]
    offer_card.open_card(settings, st.session_state[settings.state_key("rows")][row])
