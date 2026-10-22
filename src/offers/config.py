"""Read and check config.yaml."""

from dataclasses import dataclass, field

import yaml

from offers.errors import OffersError

# Keys of a source section that are not source-specific options.
COMMON_SOURCE_KEYS = {"enabled", "searches"}


class ConfigError(OffersError):
    """config.yaml is missing or badly filled."""


@dataclass(frozen=True)
class Search:
    """A saved search on a source."""

    name: str
    url: str


@dataclass(frozen=True)
class SourceConfig:
    """Settings of one source."""

    name: str
    enabled: bool
    searches: list[Search]
    options: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Config:
    """Whole configuration."""

    sources: list[SourceConfig]
    keywords_include: list[str]
    keywords_exclude: list[str]

    def enabled_sources(self):
        """Return the sources to collect."""
        return [source for source in self.sources if source.enabled]


def load_config(path, known_sources):
    """Read and check the configuration file.

    known_sources: names of the sources the program can use.
    """
    data = read_yaml(path)
    if not isinstance(data, dict):
        raise ConfigError(f"{path} doit contenir des réglages (clé: valeur).")

    sections = data.get("sources")
    if not isinstance(sections, dict) or not sections:
        raise ConfigError(
            f"{path} : la rubrique « sources » est vide ou absente. "
            "Ajoute au moins une source, par exemple business_france."
        )
    sources = [parse_source(name, section, known_sources) for name, section in sections.items()]
    return Config(
        sources=sources,
        keywords_include=parse_keywords(data, "keywords_include"),
        keywords_exclude=parse_keywords(data, "keywords_exclude"),
    )


def read_yaml(path):
    """Return the content of a YAML file."""
    try:
        with open(path, encoding="utf-8") as file:
            return yaml.safe_load(file)
    except FileNotFoundError as err:
        raise ConfigError(f"Fichier de réglages introuvable : {path}") from err
    except OSError as err:
        raise ConfigError(f"Impossible de lire {path} : {err}") from err
    except yaml.YAMLError as err:
        raise ConfigError(f"{path} n'est pas un YAML valide : {err}") from err


def parse_source(name, section, known_sources):
    """Return the settings of one source."""
    if name not in known_sources:
        raise ConfigError(
            f"Source inconnue dans « sources » : {name}. "
            f"Sources possibles : {', '.join(sorted(known_sources))}."
        )
    if not isinstance(section, dict):
        raise ConfigError(f"La source « {name} » doit contenir enabled et searches.")

    enabled = section.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"sources.{name}.enabled doit valoir true ou false.")

    searches = section.get("searches") or []
    if not isinstance(searches, list):
        raise ConfigError(f"sources.{name}.searches doit être une liste de recherches.")

    options = {key: value for key, value in section.items() if key not in COMMON_SOURCE_KEYS}
    return SourceConfig(
        name=name,
        enabled=enabled,
        searches=[parse_search(name, number, s) for number, s in enumerate(searches, 1)],
        options=options,
    )


def parse_search(source_name, number, search):
    """Return one search; number starts at 1, for the error message."""
    place = f"sources.{source_name}.searches, recherche n°{number}"
    if not isinstance(search, dict):
        raise ConfigError(f"{place} : attendu « name » et « url ».")
    for key in ("name", "url"):
        if not isinstance(search.get(key), str) or not search[key].strip():
            raise ConfigError(f"{place} : le champ « {key} » est absent ou vide.")
    return Search(name=search["name"], url=search["url"])


def parse_keywords(data, key):
    """Return a list of keywords; empty if the key is absent."""
    keywords = data.get(key) or []
    if not isinstance(keywords, list):
        raise ConfigError(f"« {key} » doit être une liste de mots-clés.")
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ConfigError(f"« {key} » : le mot-clé {keyword!r} doit être du texte.")
    return keywords
