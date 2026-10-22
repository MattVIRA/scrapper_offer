"""Contract that every source follows."""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from offers.config import SourceConfig
from offers.model import Offer


@dataclass(frozen=True)
class FoundOffer:
    """An offer and the search that found it.

    The same offer can be found by several searches.
    """

    offer: Offer
    search_name: str


class Source(ABC):
    """A site or service that provides offers.

    On failure, a source raises a subclass of OffersError, never a raw
    library exception.
    """

    # Name used in config.yaml and in Offer.source.
    name: str
    # Name shown to the user, in the "Source" column.
    label: str

    def __init__(self, config: SourceConfig):
        self.config = config

    @abstractmethod
    def collect(self) -> list[FoundOffer]:
        """Return the offers of all configured searches, in search order."""

    @abstractmethod
    def online_offers(self) -> list[Offer] | None:
        """Return all offers online on the source, not only the searched ones.

        Used to update the rows already in the file. None means the source
        cannot tell: none of its offers will then be marked as no longer
        online.
        """
