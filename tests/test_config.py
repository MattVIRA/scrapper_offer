"""Tests of config.yaml reading (offers.config)."""

import os

import pytest

from offers.config import ConfigError, Search, load_config

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
    ],
)
def test_config_errors(tmp_path, text, message):
    with pytest.raises(ConfigError, match=message):
        load_config(write(tmp_path, text), KNOWN)


def test_missing_file(tmp_path):
    with pytest.raises(ConfigError, match="introuvable") as error:
        load_config(str(tmp_path / "absent.yaml"), KNOWN)
    assert isinstance(error.value.__cause__, FileNotFoundError)
