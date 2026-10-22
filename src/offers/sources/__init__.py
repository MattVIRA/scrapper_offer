"""Offer sources and their registry."""

from offers.config import SourceConfig
from offers.sources.base import Source
from offers.sources.business_france import BusinessFranceSource

# Source classes by name, as written in config.yaml.
SOURCES: dict[str, type[Source]] = {
    BusinessFranceSource.name: BusinessFranceSource,
}


def create_source(config: SourceConfig) -> Source:
    """Return the source described by this config section."""
    try:
        source_class = SOURCES[config.name]
    except KeyError as err:
        raise ValueError(f"Unknown source: {config.name}") from err
    return source_class(config)


def source_label(name):
    """Return the name of a source as shown to the user."""
    source_class = SOURCES.get(name)
    return source_class.label if source_class else name
