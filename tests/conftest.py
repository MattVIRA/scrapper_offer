"""Data shared by the tests."""

import json
import os

import pytest

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def read_fixture(name):
    """Return the text of a file of tests/fixtures."""
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as file:
        return file.read()


@pytest.fixture
def business_france_search():
    """Real Business France API response: {"result": [...], "count": ...}."""
    return json.loads(read_fixture("business_france_search.json"))


@pytest.fixture
def business_france_page():
    """Excerpt of the site's search page, with a fake API key."""
    return read_fixture("business_france_page.html")
