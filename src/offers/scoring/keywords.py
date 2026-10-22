"""Score offers by keywords found in their text."""

import re
import unicodedata

EXCLUDED_PREFIX = "exclu : "


def normalize(text):
    """Lowercase the text and remove accents."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


def contains(normalized_text, keyword):
    """Tell whether the keyword is in the text, as a whole word.

    "ia" is found in "projet IA", but not in "media".
    """
    pattern = r"(?<!\w)" + re.escape(normalize(keyword)) + r"(?!\w)"
    return re.search(pattern, normalized_text) is not None


class KeywordScorer:
    """Score = number of keywords found; 0 if an excluded word is found."""

    def __init__(self, include, exclude):
        self.include = list(include)
        self.exclude = list(exclude)

    def score(self, offer):
        """Return (score, text of the "Mots trouvés" column)."""
        text = normalize(" ".join([offer.title, offer.description, offer.candidate_profile]))

        excluded = [word for word in self.exclude if contains(text, word)]
        if excluded:
            return 0, EXCLUDED_PREFIX + ", ".join(excluded)

        found = [word for word in self.include if contains(text, word)]
        return len(found), ", ".join(found)
