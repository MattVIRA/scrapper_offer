"""Card of one offer: everything about it, and its follow-up to edit.

Shown in a side drawer (st.dialog) over the list, so that the list stays
as it was. Opening the card marks the offer as read (offer_table).
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime
from functools import partial

import streamlit as st

from offers.sources import source_label
from offers.storage.database import save_follow_up
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
ONLINE_LABEL = "Oui"
OFFLINE_LABEL = "Plus en ligne"


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
    """Open the card of a StoredOffer.

    duplicates: references of its probable duplicates.
    action: CardAction of the button at the bottom; it closes the card.
    editable: False shows the follow-up without the form (trash).
    navigation: Navigation for the arrows; None hides them (offer no
        longer shown, after a change of its status for example).
    """
    dialog = st.dialog(
        stored.offer.title,
        width="large",
        position="right",
        on_dismiss=partial(close_card, settings),
    )
    dialog(card_body)(settings, stored, duplicates, action, editable, navigation)


def card_body(settings, stored, duplicates, action, editable, navigation):
    if navigation:
        show_arrows(settings, navigation)
    show_summary(stored, duplicates)
    if editable:
        show_follow_up_form(settings, stored)
    else:
        show_follow_up(stored)
    st.button(
        action.label,
        icon=action.icon,
        key=settings.state_key("card_action"),
        on_click=run_action,
        args=(settings, action, stored.id),
    )


def run_action(settings, action, offer_id):
    """Callback of the button at the bottom of the card.

    A callback, because the action also unchecks the table, which can only
    be changed before it is drawn.
    """
    action.run([offer_id])
    close_card(settings)
    # The whole page, not only the card, runs again.
    st.rerun()


def go_to(settings, offer_id):
    """Callback of an arrow: the whole page runs again with the other offer."""
    open_card(settings, offer_id)
    st.rerun()


def show_arrows(settings, navigation):
    """Buttons to the previous and next offers shown, and the position."""
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button(
            "Précédente",
            icon=":material/chevron_left:",
            disabled=navigation.previous is None,
            key=settings.state_key("card_previous"),
            on_click=go_to,
            args=(settings, navigation.previous),
        )
        st.caption(f"{navigation.position} / {navigation.total}")
        st.button(
            "Suivante",
            icon=":material/chevron_right:",
            disabled=navigation.next is None,
            key=settings.state_key("card_next"),
            on_click=go_to,
            args=(settings, navigation.next),
        )


def show_summary(stored, duplicates):
    """Show what is known about the offer."""
    offer = stored.offer
    st.caption(" · ".join(part for part in (offer.company, place(offer)) if part))
    if duplicates:
        st.warning(f"Doublon probable de {', '.join(duplicates)}", icon=":material/content_copy:")
    st.link_button("Voir l'offre sur le site", offer.url, icon=":material/open_in_new:")
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
    st.subheader("Suivi")
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
    """Form of the follow-up: nothing is written before « Enregistrer »."""
    key = partial(field_key, settings, stored.id)
    with st.form(key("form")):
        st.subheader("Suivi")
        status = st.selectbox(
            "Statut",
            STATUS_CHOICES,
            index=STATUS_CHOICES.index(to_widget_code(stored.status)),
            format_func=status_choice_label,
            key=key("status"),
        )
        letter = st.selectbox(
            "Lettre",
            LETTER_CHOICES,
            index=LETTER_CHOICES.index(to_widget_code(stored.letter_status)),
            format_func=letter_choice_label,
            key=key("letter"),
        )
        favorite = st.checkbox("Favori", value=stored.favorite, key=key("favorite"))
        applied_on = st.date_input(
            "Postulé le",
            value=as_date(stored.applied_on),
            format=DATE_INPUT_FORMAT,
            key=key("applied_on"),
        )
        if stored.applied_on and as_date(stored.applied_on) is None:
            st.caption(
                f"Date tapée dans l'ancien Excel : « {stored.applied_on} ». "
                "Elle est gardée tant qu'aucune date n'est choisie."
            )
        notes = st.text_area("Notes", value=stored.notes or "", key=key("notes"))
        if st.form_submit_button("Enregistrer", icon=":material/save:", type="primary"):
            with open_database(st.session_state.db_path) as conn:
                save_follow_up(
                    conn,
                    stored.id,
                    to_database_code(status),
                    to_database_code(letter),
                    favorite,
                    applied_on_to_save(applied_on, stored.applied_on),
                    notes,
                    datetime.now(),
                )
            close_card(settings)
            st.rerun()


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
