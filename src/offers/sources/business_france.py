"""Business France source (VIE offers)."""

import json
import re
import time
from datetime import date
from urllib.parse import parse_qs, urlparse

import requests

from offers.errors import OffersError
from offers.model import Offer
from offers.sources.base import FoundOffer, Source

SITE_URL = "https://mon-vie-via.businessfrance.fr"
SEARCH_PAGE_URL = SITE_URL + "/offres/recherche"
API_URL = "https://civiweb-api-prd.azurewebsites.net/api/Offers/search"

# Offers per request. The API refuses values that are too large.
PAGE_SIZE = 100
# Short pause between two requests, not to load the site.
PAUSE_SECONDS = 0.3
TIMEOUT_SECONDS = 30
# An offer can move to another page during the reading, so a small gap
# is tolerated. A large gap means the reading failed.
MIN_READ_RATIO = 0.95

# Search URL parameters that the API understands. Others are ignored.
KNOWN_FILTERS = [
    "specializationsIds",
    "geographicZones",
    "countriesIds",
    "studiesLevelId",
    "activitySectorId",
    "companiesSizes",
    "missionsTypesIds",
    "missionsDurations",
    "entreprisesIds",
    "teletravail",
    "porteEnv",
]


class ApiError(OffersError):
    """Problem while talking to a source's site."""


class BusinessFranceSource(Source):
    """VIE offers from mon-vie-via.businessfrance.fr."""

    name = "business_france"
    label = "Business France"

    def __init__(self, config, session=None):
        super().__init__(config)
        self.session = session or create_session()
        self._api_key = None

    def api_key(self):
        """Return the API key, read from the site on first use."""
        if self._api_key is None:
            self._api_key = read_api_key(self.session)
        return self._api_key

    def collect(self):
        found = []
        for search in self.config.searches:
            print(f"Recherche « {search.name} »...")
            filters = filters_from_url(search.url)
            for raw in search_offers(self.session, self.api_key(), filters):
                found.append(FoundOffer(to_offer(raw), search.name))
        return found

    def online_offers(self):
        # All offers, without filters: tells whether the offers of the file
        # are still online, even if the searches of config.yaml changed.
        print("Lecture de toutes les offres du site...")
        offers = search_offers(self.session, self.api_key())
        if not offers:
            raise ApiError("Le site ne renvoie aucune offre. Rien n'est modifié.")
        return [to_offer(raw) for raw in offers]


def create_session():
    """Return an HTTP session reused for all requests."""
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"
    return session


def read_api_key(session):
    """Read the API key from the site's search page.

    The key is public: it is written in the page's HTML. It is read on
    each run, in case it changes.
    """
    try:
        response = session.get(SEARCH_PAGE_URL, timeout=TIMEOUT_SECONDS)
        response.raise_for_status()
    except requests.RequestException as err:
        raise ApiError(f"Impossible d'ouvrir la page du site : {err}") from err

    match = re.search(r'API_KEY:"((?:[^"\\]|\\.)*)"', response.text)
    if not match:
        raise ApiError("Clé d'API introuvable dans la page du site. Le site a peut-être changé.")
    # The key is written as a JavaScript string, with escaped characters.
    return json.loads('"' + match.group(1) + '"')


def filters_from_url(url):
    """Turn the URL of a search on the site into API filters.

    Values stay text: the API refuses numbers.
    """
    params = parse_qs(urlparse(url).query, keep_blank_values=True)
    filters = {"query": params.get("query", [""])[0]}
    for name in KNOWN_FILTERS:
        if name in params:
            # Accept "a=1&a=2" as well as "a=1,2".
            values = ",".join(params[name]).split(",")
            filters[name] = [v for v in values if v != ""]
    return filters


def search_offers(session, api_key, filters=None):
    """Return all raw offers matching the filters, read page by page.

    Without filters, return all offers of the site.
    """
    offers = {}
    position = 0
    while True:
        body = {"limit": PAGE_SIZE, "skip": position, "query": ""}
        body.update(filters or {})
        data = post_search(session, api_key, body)
        page = data.get("result", [])
        total = data.get("count", 0)
        for offer in page:
            # Keyed by id: removes duplicates between two pages.
            offers[str(offer["id"])] = offer

        position += PAGE_SIZE
        if not page or position >= total:
            break
        time.sleep(PAUSE_SECONDS)

    if len(offers) < total * MIN_READ_RATIO:
        raise ApiError(f"Lecture incomplète : {len(offers)} offres lues sur {total}.")
    return list(offers.values())


def post_search(session, api_key, body):
    """Send one search request and return its JSON content."""
    try:
        response = session.post(
            API_URL, json=body, headers={"X-API-KEY": api_key}, timeout=TIMEOUT_SECONDS
        )
    except requests.RequestException as err:
        raise ApiError(f"Le site ne répond pas : {err}") from err
    if response.status_code != 200:
        raise ApiError(
            f"Le site a refusé la requête (code {response.status_code}) : {response.text[:200]}"
        )
    return response.json()


def reference(raw):
    """Return the offer's reference, for example "VIE246803"."""
    return raw.get("reference") or f"VIE{raw['id']}"


def offer_url(raw):
    """Return the URL of the offer's page on the site."""
    return f"{SITE_URL}/offres/{raw['id']}"


def to_offer(raw):
    """Convert an offer of the API into an Offer."""
    return Offer(
        source=BusinessFranceSource.name,
        source_id=str(raw["id"]),
        reference=reference(raw),
        title=raw.get("missionTitle") or "",
        company=raw.get("organizationName"),
        country=raw.get("countryName"),
        city=raw.get("cityName"),
        contract_type=raw.get("missionType"),
        duration_months=to_int(raw.get("missionDuration")),
        published_on=to_date(raw.get("startBroadcastDate") or raw.get("creationDate")),
        url=offer_url(raw),
        description=raw.get("missionDescription") or "",
        candidate_profile=raw.get("missionProfile") or "",
        raw=raw,
    )


def to_int(value):
    """Turn "12" into 12; None if it is not a number."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_date(text):
    """Turn "2026-10-07T15:03:30Z" into a date; None if empty."""
    if not text:
        return None
    return date.fromisoformat(text[:10])
