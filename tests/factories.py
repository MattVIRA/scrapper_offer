"""Builders of test objects."""

from datetime import date

from offers.config import SourceConfig
from offers.model import Offer
from offers.sources.base import FoundOffer, Source


def make_offer(**changes):
    """Return a valid offer, with the given fields changed."""
    values = {
        "source": "test",
        "source_id": "1",
        "reference": "REF1",
        "title": "Data Analyst",
        "company": "ACME",
        "country": "FRANCE",
        "city": "PARIS",
        "contract_type": "VIE",
        "duration_months": 12,
        "published_on": date(2026, 10, 21),
        "url": "https://example.com/1",
        "description": "",
        "candidate_profile": "",
        "raw": {},
    }
    values.update(changes)
    return Offer(**values)


class FakeSource(Source):
    """Source with prepared results, for pipeline tests.

    found: Offer list returned by collect(), all from search "A".
    online: Offer list returned by online_offers(); None if unknown.
    error: OffersError raised by both methods instead.
    """

    name = "fake"
    label = "Fausse source"

    def __init__(self, config=None, found=(), online=(), error=None, name=None):
        super().__init__(config or SourceConfig(name or self.name, True, []))
        # Named after its config section, as real sources are.
        self.name = self.config.name
        self.found = list(found)
        self.online = None if online is None else list(online)
        self.error = error
        self.calls = 0

    def collect(self):
        self.calls += 1
        if self.error:
            raise self.error
        return [FoundOffer(offer, "A") for offer in self.found]

    def online_offers(self):
        self.calls += 1
        if self.error:
            raise self.error
        return self.online
