"""Offer list shared by the Offres, Favoris and Corbeille pages.

Search and filters on top, then the list with the card beside it, as in
a mailbox. The checked offers live in the session state, not in the
list: the list only shows them, so the page always knows what is checked.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

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
from offers.tracking import STATUSES, status_label
from offers.ui import offer_card, offer_list
from offers.ui.labels import (
    LETTER_CHOICES,
    STATUS_CHOICES,
    letter_choice_label,
    status_choice_label,
    to_database_code,
    to_widget_code,
)
from offers.ui.offer_list import ListEvents, ListKeys
from offers.ui.session import open_database

ONLINE_LABELS = {
    browsing.ONLINE: "En ligne",
    browsing.OFFLINE: "Hors ligne",
    browsing.ALL: "Toutes",
}
TRASH_ICON = ":material/delete:"
RESTORE_ICON = ":material/restore_from_trash:"
SEARCH_PLACEHOLDER = "Titre, entreprise, ville, pays ou réf. (VIE243542)"
# Pause in the typing before the list is filtered.
SEARCH_DELAY = "300ms"
# Icons of the icon-only buttons, above the list and in the card.
ICON_SIZE = "1.4rem"
MORE_FILTERS = "Plus de filtres"
# Filters of the « Plus de filtres » menu, with their value when unused.
MORE_FILTER_DEFAULTS = {
    "letters": [],
    "sources": [],
    "countries": [],
    "min_score": 0,
    "added_since": None,
}


@dataclass(frozen=True)
class PageSettings:
    """What changes from one list page to another."""

    # Prefix of the widget and session state keys of the page.
    key: str
    title: str
    favorites_only: bool = False
    # The trash page: hidden offers, which can only be restored.
    in_trash: bool = False

    def state_key(self, name):
        return f"{self.key}_{name}"

    def default_statuses(self):
        # The trash is often made of offers the user did not want.
        return frozenset({None, *STATUSES}) if self.in_trash else browsing.DEFAULT_STATUSES

    def default_online(self):
        return browsing.ALL if self.in_trash else browsing.ONLINE

    def list_keys(self):
        return ListKeys(
            split=self.state_key("split"),
            list_pane=self.state_key("list_pane"),
            card_pane=self.state_key("card_pane"),
        )


def show_offer_page(settings):
    """Show the whole list page: search, filters, list, actions and card."""
    st.session_state.setdefault(settings.state_key("selected"), set())
    with open_database(st.session_state.db_path) as conn:
        offers = list_offers(conn)
        if mark_card_read(conn, settings, offers):
            # Read again, for the counters and the list.
            offers = list_offers(conn)
        tags = browsing.duplicate_tags(probable_duplicates(conn))
    text = search_bar(settings)
    offer_filter, counters_slot = filter_bar(offers, settings, text)
    shown = browsing.filter_offers(offers, offer_filter)
    counters_slot.caption(counters_text(browsing.counters(shown)))
    show_undo(settings)
    card = opened_offer(settings, offers)
    open_id = card.id if card else None
    keys = settings.list_keys()
    st.html(offer_list.split_style(keys, card_open=card is not None))
    st.html(icon_style(settings))
    # The same containers with or without card, so that the list keeps
    # its scroll position on opening one.
    with st.container(horizontal=True, gap="medium", key=keys.split):
        with st.container(key=keys.list_pane, gap="small"):
            show_actions(settings, shown, open_id)
            show_offers(settings, shown, open_id)
        if card:
            with st.container(key=keys.card_pane):
                show_card(settings, card, shown, tags)


def icon_style(settings):
    """Return the CSS that enlarges the icons of the action bar and of the card's bar.

    The icons are in the labels (Markdown), drawn as span role="img".
    """
    bars = [settings.state_key("actions"), settings.state_key("card_toolbar")]
    selectors = ", ".join(f'.st-key-{bar} [kind="tertiary"] span[role="img"]' for bar in bars)
    return f"<style>{selectors} {{font-size: {ICON_SIZE};}}</style>"


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


def filter_bar(offers, settings, text):
    """Show the filters on one line; return the chosen OfferFilter and the
    place of the counters, at the end of the line.

    The status and online state are always visible, the others in a menu.
    text: typed in the search bar. The filters are not kept from one opening of the app to
    the next.
    """
    choices = browsing.filter_choices(offers)
    key = settings.state_key
    with st.container(horizontal=True, vertical_alignment="center", gap="small"):
        statuses = st.pills(
            "Statut",
            STATUS_CHOICES,
            selection_mode="multi",
            default=sorted(map(to_widget_code, settings.default_statuses()), key=status_order),
            format_func=status_choice_label,
            label_visibility="collapsed",
            key=key("statuses"),
        )
        online = st.segmented_control(
            "En ligne",
            list(ONLINE_LABELS),
            default=settings.default_online(),
            format_func=ONLINE_LABELS.get,
            label_visibility="collapsed",
            key=key("online"),
        )
        with st.popover(more_filters_label(settings), icon=":material/filter_list:"):
            letters = st.multiselect(
                "Lettre",
                LETTER_CHOICES,
                format_func=letter_choice_label,
                placeholder="Toutes",
                key=key("letters"),
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
        offer_filter = make_filter(
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
        st.space("stretch")
        # Filled once the offers are filtered.
        counters_slot = st.empty()
    return offer_filter, counters_slot


def more_filters_label(settings):
    """Label of the filters menu, with the number of filters in use."""
    used = sum(
        st.session_state.get(settings.state_key(name), unused) not in (unused, None)
        for name, unused in MORE_FILTER_DEFAULTS.items()
    )
    return f"{MORE_FILTERS} ({used})" if used else MORE_FILTERS


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


def counters_text(numbers):
    """Return the counters of the offers shown, on one line."""
    parts = [
        f"**{numbers.total}** offres",
        f"**{numbers.unread}** non lues",
        f"**{numbers.by_status.get('applied', 0)}** postulées",
        f"**{numbers.letters_to_write}** lettres à rédiger",
    ]
    return " · ".join(parts)


# --- List ---------------------------------------------------------------------


def show_offers(settings, shown, open_id):
    """Show the lines of the offers shown, or why there is none."""
    if not shown:
        st.info("Aucune offre ne correspond aux filtres.", icon=":material/filter_alt_off:")
        return
    favorites = {stored.id: stored.favorite for stored in shown}
    offer_list.show_list(
        settings.state_key("list"),
        offer_list.list_rows(shown, on_favorites_page=settings.favorites_only),
        st.session_state[settings.state_key("selected")],
        open_id,
        settings.list_keys(),
        ListEvents(
            checked=state_setter(settings.state_key("selected")),
            opened=lambda offer_id: offer_card.open_card(settings, offer_id),
            starred=lambda offer_id: offer_card.switch_favorite(offer_id, not favorites[offer_id]),
        ),
        stars=not settings.in_trash,
    )


def state_setter(state_key) -> Callable:
    """Return a function that keeps its argument under state_key."""

    def setter(value):
        st.session_state[state_key] = value

    return setter


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
    with st.container(horizontal=True, vertical_alignment="center", key=key("actions")):
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
        show_group_favorite(settings, shown, targets)
        action_button(settings, "Marquer comme lu", ":material/done:", targets, mark_read)
        action_button(settings, "Corbeille", TRASH_ICON, targets, hide, trashed=True, **leaving)
        st.button(
            ":material/done_all:",
            help="Tout marquer comme lu",
            type="tertiary",
            disabled=not shown,
            key=key("read_all"),
            on_click=act,
            args=(settings, mark_read, sorted(shown_ids)),
        )


def show_group_favorite(settings, shown, targets):
    """One star for the favorites: yellow when all the targets are favorites.

    A click removes them from the favorites then; else all become favorites.
    """
    write = favorite_write(targets, {stored.id for stored in shown if stored.favorite})
    key = settings.state_key("group_favorite")
    if write is remove_favorite:
        st.html(offer_card.favorite_style(key))
    st.button(
        ":material/star:" if write is remove_favorite else ":material/star_border:",
        help="Retirer des favoris" if write is remove_favorite else "Favori",
        type="tertiary",
        disabled=not targets,
        key=key,
        on_click=act,
        args=(settings, write, targets),
    )


def favorite_write(targets, favorite_ids):
    """Return the write of the star: remove_favorite if all the targets are
    favorites, else add_favorite (a mix becomes all favorites).
    """
    if targets and set(targets) <= favorite_ids:
        return remove_favorite
    return add_favorite


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
    """Icon button that applies write(conn, ids, now) to the target offers.

    label: shown on hovering it. options: those of act.
    """
    st.button(
        icon,
        help=label,
        type="tertiary",
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

    A callback, so that the list drawn after it shows the change.

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
    if move_card and next_card is None:
        offer_card.close_card(settings)
    elif move_card:
        offer_card.open_card(settings, next_card)


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
