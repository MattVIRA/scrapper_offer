"""Tests of config.yaml reading (offers.config)."""

import os
import shutil
from datetime import datetime

import pytest

from offers import config as config_module
from offers.config import ConfigError, Search, load_config, set_search_enabled

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KNOWN = {"business_france", "other"}

VALID = """
sources:
  business_france:
    enabled: true
    searches:
      - name: "A"
        url: "https://example.com/a"
  other:
    enabled: false
    region: "nord"
keywords_include: [python]
"""


def write(tmp_path, text):
    """Write a config file and return its path."""
    path = tmp_path / "config.yaml"
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_repository_config():
    config = load_config(os.path.join(ROOT, "config.yaml"), KNOWN)
    (source,) = config.sources
    assert source.name == "business_france" and source.enabled
    assert [s.name for s in source.searches] == ["Recherche principale"]
    assert source.searches[0].url.startswith(
        "https://mon-vie-via.businessfrance.fr/offres/recherche?query=&specializationsIds=243"
    )
    assert config.keywords_include == [
        "python",
        "machine learning",
        "data",
        "ia",
        "deep learning",
        "sql",
    ]
    assert config.keywords_exclude == []


def test_valid_config(tmp_path):
    config = load_config(write(tmp_path, VALID), KNOWN)
    first, second = config.sources
    assert first.searches == [Search("A", "https://example.com/a")]
    assert first.options == {}
    assert second.searches == [] and second.options == {"region": "nord"}
    assert config.enabled_sources() == [first]
    assert config.keywords_exclude == []


def test_enabled_defaults_to_true(tmp_path):
    config = load_config(write(tmp_path, "sources:\n  other: {}\n"), KNOWN)
    assert config.sources[0].enabled


@pytest.mark.parametrize(
    "text, message",
    [
        ("sources: [", "YAML valide"),
        ("- a\n- b\n", "clé: valeur"),
        ("keywords_include: [python]\n", "« sources »"),
        ("sources: {}\n", "« sources »"),
        ("sources:\n  unknown: {}\n", "Source inconnue.*unknown.*business_france, other"),
        ("sources:\n  other: [1]\n", "« other »"),
        ("sources:\n  other:\n    enabled: oui\n", "sources.other.enabled"),
        ("sources:\n  other:\n    searches: x\n", "sources.other.searches"),
        ("sources:\n  other:\n    searches: [x]\n", "recherche n°1"),
        ("sources:\n  other:\n    searches:\n      - url: u\n", "n°1 : le champ « name »"),
        (
            "sources:\n  other:\n    searches:\n      - {name: a, url: u}\n      - {name: b}\n",
            "n°2 : le champ « url »",
        ),
        ("sources:\n  other: {}\nkeywords_include: python\n", "« keywords_include » doit"),
        ("sources:\n  other: {}\nkeywords_exclude: [1]\n", "« keywords_exclude ».*1"),
        (
            "sources:\n  other:\n    searches:\n      - {name: a, url: u, enabled: non}\n",
            "n°1 : « enabled » doit valoir true ou false",
        ),
    ],
)
def test_config_errors(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, text), KNOWN)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="introuvable") as error:
        load_config(str(tmp_path / "absent.yaml"), KNOWN)
    assert isinstance(error.value.__cause__, FileNotFoundError)


# --- Searches switched on or off ----------------------------------------------

NOW = datetime(2026, 10, 22, 10, 30)
WITH_COMMENTS = """# Réglages du script.
sources:
  other:
    # Recherches à surveiller.
    searches:
      - name: "A"
        url: "https://example.com/a?x=1&y=2"
      - name: "B"   # deuxième
        url: "https://example.com/b"
        enabled: false
keywords_include: [python]  # mots-clés
"""


def test_search_enabled_defaults_to_true_and_can_be_off(tmp_path):
    (source,) = load_config(write(tmp_path, WITH_COMMENTS), KNOWN).sources
    assert [(s.name, s.enabled) for s in source.searches] == [("A", True), ("B", False)]
    assert [s.name for s in source.active_searches()] == ["A"]


def test_switch_off_adds_the_line_and_keeps_the_comments(tmp_path):
    path = write(tmp_path, WITH_COMMENTS)

    set_search_enabled(path, "other", "A", False, tmp_path / "backup", NOW)

    lines = WITH_COMMENTS.splitlines()
    # Right after « name »: the comments of the file stay where they were.
    lines.insert(6, "        enabled: false")
    assert open(path, encoding="utf-8").read().splitlines() == lines
    (source,) = load_config(path, KNOWN).sources
    assert source.active_searches() == []


def test_new_line_of_the_last_search_stays_above_the_next_comments(tmp_path):
    text = """sources:
  other:
    searches:
      - name: "A"
        url: "https://example.com/a"

# Mots-clés cherchés.
keywords_include: [python]
"""
    path = write(tmp_path, text)

    set_search_enabled(path, "other", "A", False, tmp_path / "backup", NOW)

    assert open(path, encoding="utf-8").read() == text.replace(
        '      - name: "A"\n', '      - name: "A"\n        enabled: false\n'
    )


def test_switch_on_changes_the_line(tmp_path):
    path = write(tmp_path, WITH_COMMENTS)

    set_search_enabled(path, "other", "B", True, tmp_path / "backup", NOW)

    assert open(path, encoding="utf-8").read() == WITH_COMMENTS.replace(
        "enabled: false", "enabled: true"
    )


def test_old_file_is_saved_first(tmp_path):
    path = write(tmp_path, WITH_COMMENTS)
    set_search_enabled(path, "other", "A", False, tmp_path / "backup", NOW)

    (backup,) = (tmp_path / "backup").iterdir()
    assert backup.name == "config_2026-10-22_103000.yaml"
    assert backup.read_text(encoding="utf-8") == WITH_COMMENTS


def test_repository_config_only_gets_the_enabled_line(tmp_path):
    path = tmp_path / "config.yaml"
    shutil.copy(os.path.join(ROOT, "config.yaml"), path)

    set_search_enabled(path, "business_france", "Recherche principale", False, tmp_path, NOW)

    before = open(os.path.join(ROOT, "config.yaml"), encoding="utf-8").read().splitlines()
    after = path.read_text(encoding="utf-8").splitlines()
    name_line = before.index('      - name: "Recherche principale"')
    # The repository file has no « enabled » line for its search.
    assert after == before[: name_line + 1] + ["        enabled: false"] + before[name_line + 1 :]


@pytest.mark.parametrize(
    "text, source, search, message",
    [
        (WITH_COMMENTS, "other", "Z", "« Z » introuvable"),
        (WITH_COMMENTS, "business_france", "A", "pas de recherches pour la source"),
        ("sources: [", "other", "A", "YAML valide"),
    ],
)
def test_nothing_is_written_on_error(tmp_path, text, source, search, message):
    path = write(tmp_path, text)

    with pytest.raises(ConfigError, match=message):
        set_search_enabled(path, source, search, False, tmp_path / "backup", NOW)

    assert open(path, encoding="utf-8").read() == text
    assert not (tmp_path / "backup").exists()


def test_failed_write_keeps_the_old_file(tmp_path, monkeypatch):
    path = write(tmp_path, WITH_COMMENTS)

    def failing_replace(source, target):
        raise PermissionError("disque protégé")

    monkeypatch.setattr(config_module.os, "replace", failing_replace)
    with pytest.raises(ConfigError, match="Impossible d'écrire.*disque protégé"):
        set_search_enabled(path, "other", "A", False, tmp_path / "backup", NOW)
    assert open(path, encoding="utf-8").read() == WITH_COMMENTS
    assert not (tmp_path / "config.yaml.tmp").exists()


def test_missing_file_to_switch(tmp_path):
    with pytest.raises(ConfigError, match="Impossible de lire"):
        set_search_enabled(tmp_path / "absent.yaml", "other", "A", False, tmp_path, NOW)
