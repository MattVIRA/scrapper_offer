"""List of the offers, one line each as in a mailbox, beside the card.

A custom component (offer_list.js, offer_list.css): st.dataframe can
neither color a whole line nor open it on a click without selecting a
cell. It also draws the bar that changes the width of the list; that
width is kept by the browser, not by the app.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import streamlit as st

from offers import browsing
from offers.sources import source_label
from offers.tracking import letter_label

ASSETS = Path(__file__).parent
DATE_FORMAT = "%d/%m"
# CSS class of the line of each marker (offer_list.css).
# fmt: off
MARKER_CLASSES = {
    browsing.MARKER_REJECTED:    "rejected",
    browsing.MARKER_APPLIED:     "applied",
    browsing.MARKER_NOT_FOR_ME:  "not_for_me",
    browsing.MARKER_INTERESTING: "interesting",
    browsing.MARKER_FAVORITE:    "favorite",
    browsing.MARKER_OFFLINE:     "offline",
    browsing.NO_MARKER:          "",
}
# fmt: on
# Width of the list beside an open card, until the user drags the bar.
DEFAULT_LIST_WIDTH = "50%"
# The bar between the list and the card: the page itself has no theme variables.
SPLITTER_COLOR = "rgba(128, 128, 128, 0.2)"
SPLITTER_HOVER_COLOR = "rgba(79, 70, 229, 0.8)"

_COMPONENT = st.components.v2.component(
    "offer_list",
    html="<div class='offer-list'></div>",
    css=(ASSETS / "offer_list.css").read_text(encoding="utf-8"),
    js=(ASSETS / "offer_list.js").read_text(encoding="utf-8"),
)


@dataclass(frozen=True)
class ListKeys:
    """Keys of the containers around the list, found by the component."""

    split: str
    list_pane: str
    card_pane: str


@dataclass(frozen=True)
class ListEvents:
    """What to do on a gesture in the list; each gets the event's value."""

    checked: Callable
    opened: Callable
    starred: Callable


def show_list(key, rows, checked, open_id, keys, events, stars=True):
    """Show the lines of the offers.

    key: widget key of the list; rows: list_rows of the offers shown;
    checked: ids of the checked offers; open_id: offer whose card is open.
    stars: show the stars that switch the favorites (not in the trash).
    """
    _COMPONENT(
        data={
            "rows": rows,
            "checked": sorted(checked),
            "open": open_id,
            "splitKey": keys.split,
            "listPaneKey": keys.list_pane,
            "cardOpen": open_id is not None,
            "stars": stars,
        },
        key=key,
        on_checked_change=lambda: events.checked(set(event_value(key, "checked") or ())),
        on_opened_change=lambda: events.opened(event_value(key, "opened")),
        on_starred_change=lambda: events.starred(event_value(key, "starred")),
    )


def event_value(key, name):
    return getattr(st.session_state[key], name, None)


def split_style(keys, card_open):
    """Return the CSS that puts the list and the card side by side.

    Without a card, the list takes the whole width. Streamlit wraps each
    container in an element of its own: the widths are set on those.
    """
    split = f".st-key-{keys.split}"
    rules = [
        f"{split} {{position: relative; flex-wrap: nowrap;}}",
        f"{split} > * {{min-width: 0;}}",
        ".offer-splitter::after {content: ''; position: absolute; left: 4px; top: 0;"
        f" bottom: 0; width: 2px; border-radius: 1px; background: {SPLITTER_COLOR};}}",
        f".offer-splitter:hover::after {{background: {SPLITTER_HOVER_COLOR};}}",
    ]
    if card_open:
        rules += [
            f"{split} > :has(> .st-key-{keys.list_pane})"
            f" {{flex: 0 0 var(--offer-list-width, {DEFAULT_LIST_WIDTH});}}",
            f"{split} > :has(> .st-key-{keys.card_pane}) {{flex: 1 1 0;}}",
            f".st-key-{keys.card_pane} {{max-height: var(--offer-pane-height, 80vh);"
            " overflow-y: auto; overscroll-behavior: contain; padding-right: 0.5rem;}",
        ]
    return "<style>" + "\n".join(rules) + "</style>"


def list_rows(shown, on_favorites_page=False):
    """Return what the list shows of each offer, in their order."""
    return [list_row(stored, on_favorites_page) for stored in shown]


def list_row(stored, on_favorites_page=False):
    offer = stored.offer
    place = ", ".join(part for part in (offer.city, offer.country) if part)
    return {
        "id": stored.id,
        "title": offer.title,
        "subtitle": " · ".join(part for part in (offer.company, place) if part),
        "source": source_label(offer.source),
        "score": "" if stored.score is None else f"{stored.score:g}",
        "date": stored.first_seen.strftime(DATE_FORMAT),
        "letter": letter_label(stored.letter_status) if stored.letter_status else "",
        "marker": MARKER_CLASSES[browsing.marker(stored, on_favorites_page)],
        "unread": browsing.is_unread(stored),
        "favorite": stored.favorite,
    }
