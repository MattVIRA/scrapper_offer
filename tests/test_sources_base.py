"""Tests of the source contract and registry."""

import pytest

from offers import sources
from offers.config import Search, SourceConfig
from offers.sources.base import FoundOffer, Source
from tests import factories
from tests.sources_contract import check_found_offers, check_online_offers


def make_offer(source_id, title="Titre"):
    return factories.make_offer(
        source="fake",
        source_id=source_id,
        reference=f"F{source_id}",
        title=title,
        url=f"https://example.com/{source_id}",
    )


class FakeSource(Source):
    """Minimal source: one offer per search."""

    name = "fake"
    label = "Fausse source"

    def collect(self):
        return [FoundOffer(make_offer("1"), search.name) for search in self.config.searches]

    def online_offers(self):
        return [make_offer("1"), make_offer("2")]


CONFIG = SourceConfig("fake", True, [Search("A", "u"), Search("B", "u")])


def test_source_cannot_be_created_without_its_methods():
    class Incomplete(Source):
        name = "incomplete"

        def collect(self):
            return []

    with pytest.raises(TypeError):
        Incomplete(CONFIG)


def test_fake_source_passes_the_contract():
    source = FakeSource(CONFIG)
    found = source.collect()
    assert [item.search_name for item in found] == ["A", "B"]
    check_found_offers(found, FakeSource.name)
    check_online_offers(source.online_offers(), found, FakeSource.name)
    check_online_offers(None, found, FakeSource.name)


@pytest.mark.parametrize(
    "found",
    [
        [make_offer("1")],
        [FoundOffer(make_offer("1"), "")],
        [FoundOffer(make_offer(""), "A")],
        [FoundOffer(make_offer("1", title=""), "A")],
        [FoundOffer(make_offer("1"), "A"), FoundOffer(make_offer("1", title="Autre"), "B")],
    ],
)
def test_contract_rejects_bad_offers(found):
    with pytest.raises(AssertionError):
        check_found_offers(found, FakeSource.name)


def test_contract_rejects_wrong_source_name():
    with pytest.raises(AssertionError):
        check_found_offers([FoundOffer(make_offer("1"), "A")], "other")


def test_contract_rejects_incomplete_online_offers():
    found = [FoundOffer(make_offer("1"), "A"), FoundOffer(make_offer("3"), "A")]
    with pytest.raises(AssertionError):
        check_online_offers([make_offer("1")], found, FakeSource.name)


def test_registry_creates_the_right_class(monkeypatch):
    monkeypatch.setitem(sources.SOURCES, "fake", FakeSource)
    source = sources.create_source(CONFIG)
    assert isinstance(source, FakeSource) and source.config is CONFIG


def test_registry_rejects_an_unknown_name():
    with pytest.raises(ValueError, match="Unknown source: nope"):
        sources.create_source(SourceConfig("nope", True, []))


def test_source_label(monkeypatch):
    monkeypatch.setitem(sources.SOURCES, "fake", FakeSource)
    assert sources.source_label("fake") == "Fausse source"
    assert sources.source_label("business_france") == "Business France"
    # An unknown name is shown as is.
    assert sources.source_label("nope") == "nope"
