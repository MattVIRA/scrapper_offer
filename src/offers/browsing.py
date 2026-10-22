"""What the offer lists show: filters, counters, markers and duplicates.

Plain Python, without Streamlit: the pages only call these functions.
"""

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from offers.scoring.keywords import normalize
from offers.tracking import STATUSES

# "online" filter values.
ONLINE = "online"
OFFLINE = "offline"
ALL = "all"
# Hidden by the default filter: the user already said no.
DEFAULT_STATUSES = frozenset({None, *STATUSES} - {"not_for_me"})

# Marker of an offer, by priority: red, blue and orange are never hidden
# by yellow, and an offline offer keeps its color.
# Emojis: a table cell cannot show Material icons.
MARKER_REJECTED = "🔴"
MARKER_APPLIED = "🔵"
MARKER_NOT_FOR_ME = "🟠"
MARKER_FAVORITE = "🟡"
MARKER_OFFLINE = "⚪"
NO_MARKER = ""


@dataclass(frozen=True)
class OfferFilter:
    """What the user wants to see.

    For sources, countries and letter_statuses, None means no filter. In
    statuses and letter_statuses, None stands for "no status" / "no letter".
    An empty set matches no offer.
    """

    sources: frozenset[str] | None = None
    countries: frozenset[str] | None = None
    statuses: frozenset[str | None] = DEFAULT_STATUSES
    letter_statuses: frozenset[str | None] | None = None
    # Offers without a score count as 0.
    min_score: int | None = None
    online: str = ONLINE
    added_since: date | None = None
    # Searched in the title and the company, without case or accents.
    text: str = ""
    favorites_only: bool = False
    # True: only the offers in the trash; False: only the others.
    in_trash: bool = False


@dataclass(frozen=True)
class Counters:
    """Numbers shown above a list of offers."""

    total: int
    unread: int
    # Status code (None: no status) -> number of offers.
    by_status: dict[str | None, int] = field(default_factory=dict)
    letters_to_write: int = 0


@dataclass(frozen=True)
class FilterChoices:
    """Values offered by the filters: the ones present in the offers."""

    sources: list[str]
    countries: list[str]


def filter_offers(offers, offer_filter):
    """Return the StoredOffer that match the filter, in the same order."""
    return [stored for stored in offers if matches(stored, offer_filter)]


def matches(stored, offer_filter):
    """Tell whether a StoredOffer matches every part of the filter."""
    return (
        stored.hidden == offer_filter.in_trash
        and is_in(stored.offer.source, offer_filter.sources)
        and is_in(stored.offer.country, offer_filter.countries)
        and stored.status in offer_filter.statuses
        and is_in(stored.letter_status, offer_filter.letter_statuses)
        and has_score(stored, offer_filter.min_score)
        and has_online_state(stored, offer_filter.online)
        and added_since(stored, offer_filter.added_since)
        and contains_text(stored, offer_filter.text)
        and (stored.favorite or not offer_filter.favorites_only)
    )


def is_in(value, accepted):
    """Tell whether value is accepted; None accepts everything."""
    return accepted is None or value in accepted


def has_score(stored, min_score):
    return min_score is None or (stored.score or 0) >= min_score


def has_online_state(stored, online):
    if online == ONLINE:
        return stored.online
    if online == OFFLINE:
        return not stored.online
    return True


def added_since(stored, day):
    return day is None or stored.first_seen.date() >= day


def contains_text(stored, text):
    """Tell whether the title or the company contains text, without case or accents."""
    searched = normalize(text.strip())
    if not searched:
        return True
    offer = stored.offer
    return searched in normalize(f"{offer.title} {offer.company or ''}")


def is_unread(stored):
    """Tell whether the offer was never opened."""
    return stored.read_at is None


def counters(offers):
    """Return the Counters of a list of StoredOffer."""
    return Counters(
        total=len(offers),
        unread=sum(is_unread(stored) for stored in offers),
        by_status=dict(Counter(stored.status for stored in offers)),
        letters_to_write=sum(stored.letter_status == "to_write" for stored in offers),
    )


def marker(stored, on_favorites_page=False):
    """Return the marker of an offer; no yellow on the Favorites page."""
    if stored.status == "rejected":
        return MARKER_REJECTED
    if stored.status == "applied":
        return MARKER_APPLIED
    if stored.status == "not_for_me":
        return MARKER_NOT_FOR_ME
    if stored.favorite and not on_favorites_page:
        return MARKER_FAVORITE
    if not stored.online:
        return MARKER_OFFLINE
    return NO_MARKER


def duplicate_tags(groups):
    """Return {offer id: references of its probable duplicates}.

    groups: lists of StoredOffer, as given by database.probable_duplicates.
    """
    tags = {}
    for group in groups:
        for stored in group:
            tags[stored.id] = [other.offer.reference for other in group if other.id != stored.id]
    return tags


def filter_choices(offers):
    """Return the sources and countries present in the offers, sorted."""
    return FilterChoices(
        sources=sorted({stored.offer.source for stored in offers}),
        countries=sorted({stored.offer.country for stored in offers if stored.offer.country}),
    )
