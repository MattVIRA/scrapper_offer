"""Tests of the Business France source, without network."""

import copy
from datetime import date

import pytest
import requests

from offers.config import Search, SourceConfig
from offers.model import Offer
from offers.sources import business_france as bf
from offers.sources.base import FoundOffer
from tests.sources_contract import (
    check_found_offers,
    check_online_offers,
    check_only_active_searches,
)

# URL of config.yaml, copied here so the test does not depend on the
# current settings.
CONFIG_URL = (
    "https://mon-vie-via.businessfrance.fr/offres/recherche?query=&specializationsIds=243"
    "&specializationsIds=210&specializationsIds=212&specializationsIds=59"
    "&specializationsIds=255&specializationsIds=24&geographicZones=2&geographicZones=3"
    "&geographicZones=4&geographicZones=6&geographicZones=5&studiesLevelId=4"
    "&teletravail=0&porteEnv=0"
)


class FakeResponse:
    """Minimal HTTP response, like those of requests."""

    def __init__(self, status_code=200, text="", data=None):
        self.status_code = status_code
        self.text = text
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"code {self.status_code}")


class FakeSession:
    """Session that returns prepared responses and records the requests.

    responses: FakeResponse objects or exceptions, returned in order.
    """

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def _answer(self):
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, url, **options):
        self.requests.append(("GET", url, options))
        return self._answer()

    def post(self, url, **options):
        self.requests.append(("POST", url, options))
        return self._answer()


@pytest.fixture(autouse=True)
def no_pause(monkeypatch):
    """Tests do not wait between two pages."""
    monkeypatch.setattr(bf, "PAUSE_SECONDS", 0)


@pytest.fixture
def raw_offers(business_france_search):
    """The 5 raw offers of the fixture."""
    return business_france_search["result"]


def make_raw_offers(model, count):
    """Return `count` copies of the model offer, with different ids."""
    offers = []
    for number in range(count):
        offer = copy.deepcopy(model)
        offer["id"] = 900000 + number
        offer["reference"] = f"VIE{900000 + number}"
        offers.append(offer)
    return offers


def api_pages(pages, total):
    """One API response per page, with the announced total."""
    return [FakeResponse(data={"result": page, "count": total}) for page in pages]


def make_source(session, searches=()):
    config = SourceConfig(bf.BusinessFranceSource.name, True, list(searches))
    return bf.BusinessFranceSource(config, session=session)


# --- read_api_key -------------------------------------------------------------


def test_read_api_key_reads_and_decodes_the_key(business_france_page):
    session = FakeSession([FakeResponse(text=business_france_page)])
    assert bf.read_api_key(session) == "fausse/cle+test="
    method, url, _ = session.requests[0]
    assert (method, url) == ("GET", bf.SEARCH_PAGE_URL)


def test_read_api_key_error_if_key_missing():
    session = FakeSession([FakeResponse(text="<html>rien ici</html>")])
    with pytest.raises(bf.ApiError, match="introuvable"):
        bf.read_api_key(session)


def test_read_api_key_error_if_page_fails():
    session = FakeSession([FakeResponse(status_code=503)])
    with pytest.raises(bf.ApiError, match="Impossible d'ouvrir") as error:
        bf.read_api_key(session)
    assert isinstance(error.value.__cause__, requests.HTTPError)


def test_read_api_key_error_if_site_unreachable():
    session = FakeSession([requests.ConnectionError("pas de réseau")])
    with pytest.raises(bf.ApiError, match="Impossible d'ouvrir"):
        bf.read_api_key(session)


# --- filters_from_url ---------------------------------------------------------


def test_filters_from_url_with_the_config_url():
    assert bf.filters_from_url(CONFIG_URL) == {
        "query": "",
        "specializationsIds": ["243", "210", "212", "59", "255", "24"],
        "geographicZones": ["2", "3", "4", "6", "5"],
        "studiesLevelId": ["4"],
        "teletravail": ["0"],
        "porteEnv": ["0"],
    }


def test_filters_from_url_accepts_comma_separated_values():
    filters = bf.filters_from_url(f"{bf.SEARCH_PAGE_URL}?countriesIds=1,2&countriesIds=3")
    assert filters["countriesIds"] == ["1", "2", "3"]


def test_filters_from_url_ignores_unknown_and_empty_parameters():
    filters = bf.filters_from_url(f"{bf.SEARCH_PAGE_URL}?query=data&tri=date&page=2&countriesIds=")
    assert filters == {"query": "data", "countriesIds": []}


def test_filters_from_url_without_parameters():
    assert bf.filters_from_url(bf.SEARCH_PAGE_URL) == {"query": ""}


# --- search_offers ------------------------------------------------------------


def test_search_offers_reads_all_pages(monkeypatch, raw_offers):
    monkeypatch.setattr(bf, "PAGE_SIZE", 2)
    session = FakeSession(api_pages([raw_offers[0:2], raw_offers[2:4], raw_offers[4:5]], total=5))

    result = bf.search_offers(session, "cle", {"query": "data", "countriesIds": ["1"]})

    assert [o["id"] for o in result] == [o["id"] for o in raw_offers]
    bodies = [options["json"] for _, _, options in session.requests]
    assert [b["skip"] for b in bodies] == [0, 2, 4]
    assert all(b["limit"] == 2 for b in bodies)
    assert all(b["query"] == "data" and b["countriesIds"] == ["1"] for b in bodies)
    assert all(options["headers"] == {"X-API-KEY": "cle"} for _, _, options in session.requests)
    assert all(url == bf.API_URL for _, url, _ in session.requests)


def test_search_offers_without_filters(raw_offers):
    session = FakeSession(api_pages([raw_offers], total=len(raw_offers)))
    assert len(bf.search_offers(session, "cle")) == len(raw_offers)
    assert session.requests[0][2]["json"] == {"limit": bf.PAGE_SIZE, "skip": 0, "query": ""}


def test_search_offers_removes_duplicates_between_pages(monkeypatch, raw_offers):
    # An offer moved from one page to the next during the reading: it is
    # read twice, and another is never read (19 out of 20, within 95 %).
    monkeypatch.setattr(bf, "PAGE_SIZE", 10)
    offers = make_raw_offers(raw_offers[0], 20)
    session = FakeSession(api_pages([offers[0:10], offers[9:19]], total=20))

    ids = [o["id"] for o in bf.search_offers(session, "cle")]
    assert len(ids) == len(set(ids)) == 19


def test_search_offers_stops_on_an_empty_page(monkeypatch, raw_offers):
    monkeypatch.setattr(bf, "PAGE_SIZE", 5)
    # The site announces 6 offers but the 2nd page is empty: 5/6 < 95 %.
    session = FakeSession(api_pages([raw_offers, []], total=6))

    with pytest.raises(bf.ApiError, match="5 offres lues sur 6"):
        bf.search_offers(session, "cle")
    assert len(session.requests) == 2


def test_search_offers_no_offer():
    session = FakeSession(api_pages([[]], total=0))
    assert bf.search_offers(session, "cle") == []


def test_search_offers_error_if_reading_incomplete(monkeypatch, raw_offers):
    monkeypatch.setattr(bf, "PAGE_SIZE", 10)
    offers = make_raw_offers(raw_offers[0], 20)
    # 18 different offers out of 20 announced: below 95 %.
    session = FakeSession(api_pages([offers[0:10], offers[8:18]], total=20))
    with pytest.raises(bf.ApiError, match="Lecture incomplète : 18 offres lues sur 20"):
        bf.search_offers(session, "cle")


def test_search_offers_error_if_http_code_is_not_200():
    session = FakeSession([FakeResponse(status_code=401, text="clé refusée")])
    with pytest.raises(bf.ApiError, match=r"code 401.*clé refusée"):
        bf.search_offers(session, "cle")


def test_search_offers_error_if_site_unreachable():
    session = FakeSession([requests.Timeout("trop long")])
    with pytest.raises(bf.ApiError, match="ne répond pas") as error:
        bf.search_offers(session, "cle")
    assert isinstance(error.value.__cause__, requests.Timeout)


# --- reference and offer_url --------------------------------------------------


def test_reference_read_from_the_offer(raw_offers):
    for offer in raw_offers:
        assert bf.reference(offer) == offer["reference"]


def test_reference_built_if_missing():
    assert bf.reference({"id": 246803}) == "VIE246803"
    assert bf.reference({"id": 246803, "reference": ""}) == "VIE246803"


def test_offer_url(raw_offers):
    offer = raw_offers[0]
    assert bf.offer_url(offer) == f"https://mon-vie-via.businessfrance.fr/offres/{offer['id']}"


# --- to_offer -----------------------------------------------------------------


def test_to_offer_on_the_fixture(raw_offers):
    for raw in raw_offers:
        offer = bf.to_offer(raw)
        assert offer == Offer(
            source="business_france",
            source_id=str(raw["id"]),
            reference=raw["reference"],
            title=raw["missionTitle"],
            company=raw["organizationName"],
            country=raw["countryName"],
            city=raw["cityName"],
            contract_type="VIE",
            duration_months=raw["missionDuration"],
            published_on=date.fromisoformat(raw["startBroadcastDate"][:10]),
            url=bf.offer_url(raw),
            description=raw["missionDescription"],
            candidate_profile=raw["missionProfile"],
        )
        assert offer.raw is raw


def test_to_offer_with_missing_fields():
    offer = bf.to_offer(
        {
            "id": 5,
            "creationDate": "2026-10-07T15:03:30Z",
            "missionDuration": "6 mois",
            "missionDescription": None,
        }
    )
    assert offer.reference == "VIE5"
    assert offer.title == "" and offer.company is None
    assert offer.published_on == date(2026, 10, 7)
    # A duration that is not a number is left empty.
    assert offer.duration_months is None
    assert offer.description == "" and offer.candidate_profile == ""


def test_to_offer_numeric_text_and_no_date():
    assert bf.to_offer({"id": 5, "missionDuration": "12"}).duration_months == 12
    assert bf.to_offer({"id": 5}).published_on is None


# --- BusinessFranceSource -----------------------------------------------------


def test_collect_reads_each_search(business_france_page, raw_offers):
    session = FakeSession(
        [FakeResponse(text=business_france_page)]
        + api_pages([raw_offers[:2]], total=2)
        + api_pages([raw_offers[1:3]], total=2)
    )
    source = make_source(session, [Search("A", CONFIG_URL), Search("B", bf.SEARCH_PAGE_URL)])

    found = source.collect()

    assert found == [
        FoundOffer(bf.to_offer(raw_offers[0]), "A"),
        FoundOffer(bf.to_offer(raw_offers[1]), "A"),
        FoundOffer(bf.to_offer(raw_offers[1]), "B"),
        FoundOffer(bf.to_offer(raw_offers[2]), "B"),
    ]
    # The key is read once, then used for every search.
    assert [method for method, _, _ in session.requests] == ["GET", "POST", "POST"]
    first_body = session.requests[1][2]["json"]
    assert first_body["specializationsIds"] == ["243", "210", "212", "59", "255", "24"]
    assert session.requests[2][2]["json"] == {"limit": bf.PAGE_SIZE, "skip": 0, "query": ""}
    check_found_offers(found, bf.BusinessFranceSource.name)


def test_collect_skips_the_searches_switched_off(business_france_page, raw_offers):
    session = FakeSession(
        [FakeResponse(text=business_france_page)] + api_pages([raw_offers[:2]], total=2)
    )
    searches = [Search("A", CONFIG_URL, enabled=False), Search("B", bf.SEARCH_PAGE_URL)]
    source = make_source(session, searches)

    found = source.collect()

    assert {item.search_name for item in found} == {"B"}
    # One page read and one search: "A" is not queried.
    assert [method for method, _, _ in session.requests] == ["GET", "POST"]
    check_only_active_searches(found, source.config)


def test_online_offers_reads_without_filters(business_france_page, raw_offers):
    session = FakeSession(
        [FakeResponse(text=business_france_page)]
        + api_pages([raw_offers], total=5)
        + api_pages([raw_offers[:2]], total=2)
    )
    source = make_source(session, [Search("A", CONFIG_URL)])

    online = source.online_offers()
    found = source.collect()

    assert online == [bf.to_offer(raw) for raw in raw_offers]
    assert session.requests[1][2]["json"] == {"limit": bf.PAGE_SIZE, "skip": 0, "query": ""}
    check_online_offers(online, found, bf.BusinessFranceSource.name)


def test_online_offers_error_if_site_returns_nothing(business_france_page):
    session = FakeSession([FakeResponse(text=business_france_page)] + api_pages([[]], total=0))
    with pytest.raises(bf.ApiError, match="aucune offre"):
        make_source(session).online_offers()


def test_source_errors_are_api_errors():
    session = FakeSession([requests.ConnectionError("pas de réseau")])
    with pytest.raises(bf.ApiError):
        make_source(session, [Search("A", CONFIG_URL)]).collect()
