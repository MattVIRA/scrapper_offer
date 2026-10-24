"""Read and check config.yaml, and switch its searches on or off."""

import io
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from ruamel.yaml import YAML
from ruamel.yaml.error import YAMLError as RoundTripError

from offers.backups import copy_to_backup, write_text_atomically
from offers.errors import OffersError

# Keys of a source section that are not source-specific options.
COMMON_SOURCE_KEYS = {"enabled", "searches"}
BACKUP_PREFIX = "config_"
# Paths of the « letters » section, relative to the folder of config.yaml.
LETTERS_PATHS = ("profile_dir", "output_dir", "prompt")
LETTERS_KEYS = (*LETTERS_PATHS, "model")
# Long URLs stay on one line when the file is written again.
LINE_WIDTH = 4096


class ConfigError(OffersError):
    """config.yaml is missing or badly filled."""


@dataclass(frozen=True)
class Search:
    """A saved search on a source."""

    name: str
    url: str
    # A search switched off is no longer queried.
    enabled: bool = True


@dataclass(frozen=True)
class SourceConfig:
    """Settings of one source."""

    name: str
    enabled: bool
    searches: list[Search]
    options: dict = field(default_factory=dict)

    def active_searches(self):
        """Return the searches to query."""
        return [search for search in self.searches if search.enabled]


@dataclass(frozen=True)
class LettersConfig:
    """Where to find what a cover letter needs, and where to write it."""

    # cv/, exemples/, consignes.md and coordonnees.yaml (offers.letters.inputs).
    profile_dir: Path = Path("profil")
    output_dir: Path = Path("lettres")
    prompt: Path = Path("prompts/lettre.md")
    # Model given to claude -p; None: the default model of Claude Code.
    model: str | None = None


@dataclass(frozen=True)
class Config:
    """Whole configuration."""

    sources: list[SourceConfig]
    keywords_include: list[str]
    keywords_exclude: list[str]
    letters: LettersConfig = field(default_factory=LettersConfig)

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
        letters=parse_letters(data.get("letters"), Path(path).parent),
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
    enabled = search.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ConfigError(f"{place} : « enabled » doit valoir true ou false.")
    return Search(name=search["name"], url=search["url"], enabled=enabled)


def parse_keywords(data, key):
    """Return a list of keywords; empty if the key is absent."""
    keywords = data.get(key) or []
    if not isinstance(keywords, list):
        raise ConfigError(f"« {key} » doit être une liste de mots-clés.")
    for keyword in keywords:
        if not isinstance(keyword, str):
            raise ConfigError(f"« {key} » : le mot-clé {keyword!r} doit être du texte.")
    return keywords


def parse_letters(section, root):
    """Return the letters settings; missing keys take their default value.

    root: folder the relative paths start from (the one of config.yaml).
    """
    section = section if section is not None else {}
    if not isinstance(section, dict):
        raise ConfigError("La rubrique « letters » doit contenir des réglages (clé: valeur).")
    unknown = sorted(set(section) - set(LETTERS_KEYS))
    if unknown:
        raise ConfigError(
            f"letters : réglage inconnu « {unknown[0]} ». "
            f"Réglages possibles : {', '.join(LETTERS_KEYS)}."
        )
    defaults = LettersConfig()
    paths = {}
    for key in LETTERS_PATHS:
        value = section.get(key, getattr(defaults, key))
        if not isinstance(value, (str, Path)) or not str(value).strip():
            raise ConfigError(
                f"letters.{key} doit être un chemin, par exemple {getattr(defaults, key)}."
            )
        paths[key] = root / value
    model = section.get("model")
    if model is not None and (not isinstance(model, str) or not model.strip()):
        raise ConfigError("letters.model doit être un nom de modèle, par exemple sonnet.")
    return LettersConfig(**paths, model=model)


def set_search_enabled(path, source_name, search_name, enabled, backup_dir, now):
    """Switch a search of config.yaml on or off, keeping the rest of the file.

    Comments, order and quotes are kept. The old file is copied into
    backup_dir first, then the new one replaces it atomically. Nothing is
    written if the file cannot be read or the search is not found.
    """
    path = Path(path)
    round_trip = round_trip_yaml()
    try:
        data = round_trip.load(path.read_text(encoding="utf-8"))
    except OSError as err:
        raise ConfigError(f"Impossible de lire {path} : {err}") from err
    except RoundTripError as err:
        raise ConfigError(f"{path} n'est pas un YAML valide : {err}") from err
    set_enabled(find_search(data, path, source_name, search_name), enabled)
    text = io.StringIO()
    round_trip.dump(data, text)
    backup_config(path, Path(backup_dir), now)
    write_atomically(path, text.getvalue())


def round_trip_yaml():
    """Return a YAML reader and writer that keeps the layout of config.yaml."""
    round_trip = YAML()
    round_trip.preserve_quotes = True
    round_trip.indent(mapping=2, sequence=4, offset=2)
    round_trip.width = LINE_WIDTH
    return round_trip


def find_search(data, path, source_name, search_name):
    """Return the section of a search in the data read from config.yaml."""
    try:
        searches = data["sources"][source_name]["searches"] or []
    except (KeyError, TypeError) as err:
        raise ConfigError(f"{path} : pas de recherches pour la source {source_name}.") from err
    for search in searches:
        if isinstance(search, dict) and search.get("name") == search_name:
            return search
    raise ConfigError(f"{path} : recherche « {search_name} » introuvable pour {source_name}.")


def set_enabled(search, enabled):
    """Set « enabled » in the section of a search.

    A new line goes right after « name »: at the end of the section, it
    would land after the comments that follow the search in the file.
    """
    if "enabled" in search:
        search["enabled"] = enabled
    else:
        search.insert(list(search).index("name") + 1, "enabled", enabled)


def backup_config(path, backup_dir, now):
    """Copy config.yaml into backup_dir, keeping the last backups."""
    try:
        copy_to_backup(path, backup_dir, BACKUP_PREFIX, now)
    except OSError as err:
        raise ConfigError(
            f"Impossible de sauvegarder {path} dans {backup_dir} : {err}. Rien n'a été modifié."
        ) from err


def write_atomically(path, text):
    """Write a temporary file, then replace path with it."""
    try:
        write_text_atomically(path, text)
    except OSError as err:
        raise ConfigError(f"Impossible d'écrire {path} : {err}. Il n'a pas changé.") from err
