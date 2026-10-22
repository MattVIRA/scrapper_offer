"""Tests of the common Offer model."""

import dataclasses

import pytest

from offers.model import Offer
from tests.factories import make_offer


def test_creation_with_defaults():
    offer = Offer(
        source="test",
        source_id="1",
        reference="REF1",
        title="Titre",
        company=None,
        country=None,
        city=None,
        contract_type=None,
        duration_months=None,
        published_on=None,
        url="https://example.com/1",
    )
    assert offer.description == ""
    assert offer.candidate_profile == ""
    assert offer.raw == {}


def test_key():
    assert make_offer(source="a", source_id="42").key == ("a", "42")


def test_offer_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        make_offer().title = "Autre"


def test_raw_is_ignored_in_equality():
    assert make_offer(raw={"id": 1}) == make_offer(raw={"id": 2, "extra": True})
    assert make_offer(title="A") != make_offer(title="B")


def test_raw_is_not_in_repr():
    assert "raw" not in repr(make_offer())
