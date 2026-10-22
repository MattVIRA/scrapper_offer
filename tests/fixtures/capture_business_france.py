"""Record real Business France responses for the tests.

Run by hand, never by pytest:
    python tests/fixtures/capture_business_france.py

Writes next to this file:
- business_france_search.json: one API page (a few offers);
- business_france_page.html: an excerpt of the search page, with a fake
  API key instead of the real one.
"""

import json
import os
import re

from offers.sources import business_france as bf

FIXTURES_DIR = os.path.dirname(os.path.abspath(__file__))
OFFER_COUNT = 5
# Text kept on each side of the key in the page excerpt.
EXCERPT_MARGIN = 60
# Fake key, escaped in the page like the real one.
FAKE_KEY = "fausse/cle+test="
# Offer fields that can identify a person: replaced.
CONTACT_FIELDS = {
    "contactCivility": "",
    "contactFirstName": "",
    "contactLastName": "",
    "contactName": "Contact Test",
    "contactEmail": "contact@example.com",
    "contactURL": "",
}


def escape(text):
    """Escape special characters as unicode codes, like the site's page."""
    return "".join(c if c.isalnum() or c == "=" else "\\u%04X" % ord(c) for c in text)


def anonymize(offer):
    """Replace the contact details with fake values."""
    for name, value in CONTACT_FIELDS.items():
        if name in offer:
            offer[name] = value
    return offer


def capture_page(session):
    """Save the page excerpt around the key, with the fake key; return the real key."""
    response = session.get(bf.SEARCH_PAGE_URL, timeout=bf.TIMEOUT_SECONDS)
    response.raise_for_status()
    match = re.search(r'API_KEY:"((?:[^"\\]|\\.)*)"', response.text)
    if not match:
        raise bf.ApiError("Clé d'API introuvable dans la page du site.")

    start = max(match.start() - EXCERPT_MARGIN, 0)
    end = match.end() + EXCERPT_MARGIN
    excerpt = (
        response.text[start : match.start(1)] + escape(FAKE_KEY) + response.text[match.end(1) : end]
    )
    with open(
        os.path.join(FIXTURES_DIR, "business_france_page.html"), "w", encoding="utf-8"
    ) as file:
        file.write(excerpt + "\n")
    return json.loads('"' + match.group(1) + '"')


def capture_search(session, api_key):
    """Save one API page, reduced to a few offers."""
    data = bf.post_search(session, api_key, {"limit": OFFER_COUNT, "skip": 0, "query": ""})
    data["result"] = [anonymize(offer) for offer in data["result"]]
    with open(
        os.path.join(FIXTURES_DIR, "business_france_search.json"), "w", encoding="utf-8"
    ) as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def main():
    session = bf.create_session()
    api_key = capture_page(session)
    capture_search(session, api_key)
    print(f"Fixtures écrites dans {FIXTURES_DIR}")


if __name__ == "__main__":
    main()
