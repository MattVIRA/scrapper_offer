"""Card of one offer: its follow-up to edit, then everything about it.

Shown beside the list, not in a st.dialog (which greys the page behind
it): the list stays visible and clickable, with the line of the card
highlighted. Opening the card marks the offer as read (offer_table). Each
change of the follow-up is saved at once: the user is alone, no
« Enregistrer ».
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial

import streamlit as st

from offers.sources import source_label
from offers.storage.database import save_follow_up, set_favorite
from offers.ui.labels import (
    LETTER_CHOICES,
    STATUS_CHOICES,
    letter_choice_label,
    status_choice_label,
    to_database_code,
    to_widget_code,
)
from offers.ui.session import open_database

DATE_FORMAT = "%d/%m/%Y"
DATE_INPUT_FORMAT = "DD/MM/YYYY"
MISSING = "—"
# Height of the « Notes » field, in pixels: about three lines.
NOTES_HEIGHT = 90
ONLINE_LABEL = "Oui"
OFFLINE_LABEL = "Plus en ligne"
# Background of the favorites, in the card and in the list.
FAVORITE_COLOR = "#FDE68A"
FAVORITE_BORDER = "#F59E0B"
FAVORITE_TEXT = "#1F2937"


@dataclass(frozen=True)
class CardAction:
    """Button at the bottom of the card, such as « Mettre à la corbeille »."""

    label: str
    icon: str
    # Called with [offer id].
    run: Callable


@dataclass(frozen=True)
class Navigation:
    """Place of the card's offer among the offers shown, for the arrows."""

    previous: int | None
    next: int | None
    # From 1.
    position: int
    total: int


def navigation(shown_ids, offer_id):
    """Return the Navigation of an offer in the list shown; None if not in it."""
    if offer_id not in shown_ids:
        return None
    index = shown_ids.index(offer_id)
    return Navigation(
        previous=shown_ids[index - 1] if index > 0 else None,
        next=shown_ids[index + 1] if index + 1 < len(shown_ids) else None,
        position=index + 1,
        total=len(shown_ids),
    )


def card_key(settings):
    """Session state key holding the id of the offer whose card is open."""
    return settings.state_key("card")


def open_card(settings, offer_id):
    st.session_state[card_key(settings)] = offer_id


def close_card(settings):
    st.session_state.pop(card_key(settings), None)


def show_card(settings, stored, duplicates, action, editable=True, navigation=None):
    """Show the card of a StoredOffer, in the current container.

    duplicates: references of its probable duplicates.
    action: CardAction of the button at the top (« Mettre à la corbeille »,
        « Restaurer »); the card then goes to the next offer shown.
    editable: False shows the follow-up without fields, and no favorite
        button (trash).
    navigation: Navigation for the arrows; None hides them (offer no
        longer shown, after a change of its status for example).
    """
    show_toolbar(settings, stored, navigation, editable, action)
    st.subheader(stored.offer.title)
    st.caption(" · ".join(part for part in (stored.offer.company, place(stored.offer)) if part))
    show_follow_up_panel(settings, stored, editable)
    show_summary(stored, duplicates)


def show_follow_up_panel(settings, stored, editable=True):
    """Follow-up of the open offer: the form, or only its values (trash)."""
    with st.container(border=True):
        if st.session_state.pop(settings.state_key("card_saved"), False):
            st.toast("Suivi enregistré.", icon=":material/check_circle:")
        if editable:
            show_follow_up_form(settings, stored)
        else:
            show_follow_up(stored)


def show_toolbar(settings, stored, navigation, editable, action):
    """Arrows on the left; favorite, action, website and « Fermer » on the right.

    Icons only, their name shown on hovering them.
    """
    with st.container(
        horizontal=True,
        vertical_alignment="center",
        gap="xsmall",
        key=settings.state_key("card_toolbar"),
    ):
        if navigation:
            show_arrows(settings, navigation)
        st.space("stretch")
        if editable:
            show_favorite_button(settings, stored)
        show_action(settings, stored, action, following_offer(navigation))
        st.link_button(
            ":material/open_in_new:",
            stored.offer.url,
            help="Voir l'offre sur le site",
            type="tertiary",
        )
        st.button(
            ":material/close:",
            help="Fermer",
            type="tertiary",
            key=settings.state_key("card_close"),
            on_click=close_card,
            args=(settings,),
        )


def following_offer(navigation):
    """Return the offer to show once the card's offer leaves the list.

    The next one below in the table, else the one above; None if alone.
    """
    if navigation is None:
        return None
    return navigation.next if navigation.next is not None else navigation.previous


def show_favorite_button(settings, stored):
    """The star switches the favorite at once; yellow when it is one."""
    key = settings.state_key("card_favorite")
    if stored.favorite:
        st.html(favorite_style(key))
    st.button(
        ":material/star:" if stored.favorite else ":material/star_border:",
        help="Retirer des favoris" if stored.favorite else "Favori",
        type="tertiary",
        key=key,
        on_click=switch_favorite,
        args=(stored.id, not stored.favorite),
    )


def favorite_style(key):
    """Return the CSS that colors the button of this key as a favorite."""
    return (
        f"<style>.st-key-{key} button {{background-color: {FAVORITE_COLOR}; "
        f"border-color: {FAVORITE_BORDER}; color: {FAVORITE_TEXT};}}</style>"
    )


def switch_favorite(offer_id, favorite):
    with open_database(st.session_state.db_path) as conn:
        set_favorite(conn, [offer_id], favorite, datetime.now())


def show_action(settings, stored, action, following_id):
    st.button(
        action.icon,
        help=action.label,
        type="tertiary",
        key=settings.state_key("card_action"),
        on_click=run_action,
        args=(settings, action, stored.id, following_id),
    )


def run_action(settings, action, offer_id, following_id):
    """Callback of the action button: the offer leaves the list, the card
    goes to following_id (or closes if None).

    A callback, because the action also unchecks the table, which can only
    be changed before it is drawn.
    """
    action.run([offer_id])
    if following_id is None:
        close_card(settings)
    else:
        open_card(settings, following_id)


def go_to(settings, offer_id):
    """Callback of an arrow: the card shows the other offer, read."""
    open_card(settings, offer_id)


def show_arrows(settings, navigation):
    """Buttons to the previous and next offers shown, and the position."""
    st.button(
        ":material/chevron_left:",
        help="Précédente",
        type="tertiary",
        disabled=navigation.previous is None,
        key=settings.state_key("card_previous"),
        on_click=go_to,
        args=(settings, navigation.previous),
    )
    st.caption(f"{navigation.position} / {navigation.total}", width="content")
    st.button(
        ":material/chevron_right:",
        help="Suivante",
        type="tertiary",
        disabled=navigation.next is None,
        key=settings.state_key("card_next"),
        on_click=go_to,
        args=(settings, navigation.next),
    )


def show_summary(stored, duplicates):
    """Show what is known about the offer."""
    offer = stored.offer
    if duplicates:
        st.warning(f"Doublon probable de {', '.join(duplicates)}", icon=":material/content_copy:")
    st.table(details(stored), border="horizontal", width="content")
    score = MISSING if stored.score is None else stored.score
    st.metric("Score par mots-clés", score)
    st.caption(f"Mots trouvés : {stored.words or MISSING}")
    st.subheader("Description")
    st.text(offer.description or MISSING)
    st.subheader("Profil recherché")
    st.text(offer.candidate_profile or MISSING)
    # Lot 5: the link to the letter goes here, once it exists.


def place(offer):
    return ", ".join(part for part in (offer.city, offer.country) if part)


def details(stored):
    """Return {label: text} of the facts about the offer."""
    offer = stored.offer
    return {
        "Réf.": offer.reference,
        "Pays et ville": place(offer) or MISSING,
        "Durée": f"{offer.duration_months} mois" if offer.duration_months else MISSING,
        "Type de contrat": offer.contract_type or MISSING,
        "Publiée le": format_date(offer.published_on),
        "Ajoutée le": format_date(stored.first_seen),
        "Vue pour la dernière fois": format_date(stored.last_seen),
        "En ligne": ONLINE_LABEL if stored.online else OFFLINE_LABEL,
        "Source": source_label(offer.source),
        "Recherche": stored.search_name or MISSING,
    }


def format_date(value):
    return value.strftime(DATE_FORMAT) if value else MISSING


def show_follow_up(stored):
    """Show the follow-up without changing it."""
    st.table(follow_up(stored), border="horizontal", width="content")


def follow_up(stored):
    """Return {label: text} of the user's follow-up of the offer."""
    return {
        "Statut": status_choice_label(to_widget_code(stored.status)),
        "Lettre": letter_choice_label(to_widget_code(stored.letter_status)),
        "Favori": "Oui" if stored.favorite else "Non",
        "Postulé le": format_applied_on(stored.applied_on),
        "Notes": stored.notes or MISSING,
    }


def format_applied_on(text):
    """Return the application date as shown: a date, or the text typed in the old Excel."""
    if as_date(text):
        return format_date(as_date(text))
    return text or MISSING


def show_follow_up_form(settings, stored):
    """Fields of the follow-up, each saved as soon as it changes.

    The notes are saved when the field is left (or Ctrl+Entrée).
    """
    key = partial(field_key, settings, stored.id)
    init_fields(settings, stored)
    save = {"on_change": save_fields, "args": (settings, stored)}
    # Statut, Lettre and Postulé le on one line; then Notes.
    status_column, letter_column, date_column = st.columns(3)
    status_column.selectbox(
        "Statut",
        STATUS_CHOICES,
        format_func=status_choice_label,
        key=key("status"),
        **save,
    )
    letter_column.selectbox(
        "Lettre",
        LETTER_CHOICES,
        format_func=letter_choice_label,
        key=key("letter"),
        **save,
    )
    date_column.date_input(
        "Postulé le",
        format=DATE_INPUT_FORMAT,
        key=key("applied_on"),
        **save,
    )
    if stored.applied_on and as_date(stored.applied_on) is None:
        st.caption(
            f"Date tapée dans l'ancien Excel : « {stored.applied_on} ». "
            "Elle est gardée tant qu'aucune date n'est choisie."
        )
    st.text_area("Notes", height=NOTES_HEIGHT, key=key("notes"), **save)


def init_fields(settings, stored):
    """Fill the fields from the database the first time the card is shown.

    Through the session state only, not the widgets' defaults:
    refresh_fields also sets these keys, and Streamlit warns when a widget
    gets both.
    """
    values = {
        "status": to_widget_code(stored.status),
        "letter": to_widget_code(stored.letter_status),
        "applied_on": as_date(stored.applied_on),
        "notes": stored.notes or "",
    }
    for name, value in values.items():
        st.session_state.setdefault(field_key(settings, stored.id, name), value)


def save_fields(settings, stored):
    """Callback of the follow-up fields: write all of them, as shown."""
    value = partial(field_value, settings, stored.id)
    with open_database(st.session_state.db_path) as conn:
        save_follow_up(
            conn,
            stored.id,
            to_database_code(value("status")),
            to_database_code(value("letter")),
            applied_on_to_save(value("applied_on"), stored.applied_on),
            value("notes"),
            datetime.now(),
        )
    st.session_state[settings.state_key("card_saved")] = True


def field_value(settings, offer_id, name):
    return st.session_state[field_key(settings, offer_id, name)]


def refresh_fields(settings, offers):
    """Show in the card the status and letter of offers changed elsewhere
    (action bar). offers: StoredOffer as now in the database.

    Set, not dropped: a dropped widget value would come back from the
    browser, and be saved again over the change.
    """
    for stored in offers:
        values = {
            "status": to_widget_code(stored.status),
            "letter": to_widget_code(stored.letter_status),
        }
        for name, value in values.items():
            key = field_key(settings, stored.id, name)
            if key in st.session_state:
                st.session_state[key] = value


def field_key(settings, offer_id, name):
    """Widget key of the card: one per offer, so that no value leaks to another."""
    return settings.state_key(f"card_{offer_id}_{name}")


def as_date(text):
    """Return an ISO date text as a date, or None."""
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def applied_on_to_save(chosen, stored_text):
    """Return the application date to save.

    A date typed as text in the old Excel file is kept while no date is
    chosen; a real date can be cleared.
    """
    if chosen is not None:
        return chosen
    if stored_text and as_date(stored_text) is None:
        return stored_text
    return None
