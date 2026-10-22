"""Common format of an offer, shared by all sources."""

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Offer:
    """A job offer, whatever its source."""

    source: str
    source_id: str
    # Shown in the "Réf." column; unique within a source.
    reference: str
    title: str
    company: str | None
    country: str | None
    city: str | None
    contract_type: str | None
    duration_months: int | None
    published_on: date | None
    url: str
    description: str = ""
    candidate_profile: str = ""
    # Original data, kept to reprocess an offer without downloading it again.
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @property
    def key(self):
        """Global identifier: (source, source_id)."""
        return (self.source, self.source_id)
