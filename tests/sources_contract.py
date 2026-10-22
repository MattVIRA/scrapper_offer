"""Checks that every source must pass, reused by each source's tests."""

from offers.model import Offer
from offers.sources.base import FoundOffer

REQUIRED_TEXT_FIELDS = ("source_id", "reference", "title", "url")


def check_found_offers(found, source_name):
    """Check the result of Source.collect()."""
    assert isinstance(found, list)
    by_key = {}
    for item in found:
        assert isinstance(item, FoundOffer), item
        assert isinstance(item.search_name, str) and item.search_name
        offer = item.offer
        assert isinstance(offer, Offer), offer
        assert offer.source == source_name
        for name in REQUIRED_TEXT_FIELDS:
            value = getattr(offer, name)
            assert isinstance(value, str) and value, (name, offer)
        assert isinstance(offer.description, str)
        assert isinstance(offer.candidate_profile, str)
        # Two searches may find the same offer, but it must be the same.
        assert by_key.setdefault(offer.key, offer) == offer, offer.key


def check_online_offers(online, found, source_name):
    """Check the result of Source.online_offers()."""
    if online is None:
        return
    check_found_offers([FoundOffer(offer, "online") for offer in online], source_name)
    missing = {item.offer.reference for item in found} - {offer.reference for offer in online}
    assert not missing, missing


def check_only_active_searches(found, source_config):
    """Check that Source.collect() queried only the active searches."""
    active = {search.name for search in source_config.active_searches()}
    assert {item.search_name for item in found} <= active
