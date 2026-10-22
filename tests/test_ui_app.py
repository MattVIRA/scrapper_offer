"""Tests of the Streamlit interface, without a browser."""

import sys

import pytest
from streamlit.testing.v1 import AppTest

from offers.__main__ import DEFAULT_CONFIG, DEFAULT_DB, UI_APP
from offers.storage.database import connect

PAGES = {
    "app_pages/offers.py": "Offres",
    "app_pages/favorites.py": "Favoris",
    "app_pages/trash.py": "Corbeille",
    "app_pages/collect.py": "Collecte",
}
# The first run imports Streamlit and the project.
TIMEOUT = 30


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "offers.db"
    connect(path).close()
    return path


def start(monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["app.py", *argv])
    return AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT).run()


@pytest.mark.parametrize("page, title", PAGES.items())
def test_each_page_shows_its_title(monkeypatch, db_path, page, title):
    at = start(monkeypatch, ["--db", str(db_path)])
    at.switch_page(page).run()
    assert not at.exception
    assert at.title[0].value == title


def test_first_page_is_offers(monkeypatch, db_path):
    at = start(monkeypatch, ["--db", str(db_path)])
    assert not at.exception
    assert at.title[0].value == "Offres"


def test_paths_come_from_the_command_line(monkeypatch, db_path, tmp_path):
    config = tmp_path / "config.yaml"
    at = start(monkeypatch, ["--db", str(db_path), "--config", str(config)])
    assert at.session_state["db_path"] == db_path
    assert at.session_state["config_path"] == config


def test_paths_are_read_once_per_session(monkeypatch, db_path, tmp_path):
    at = start(monkeypatch, ["--db", str(db_path)])
    monkeypatch.setattr(sys, "argv", ["app.py", "--db", str(tmp_path / "autre.db")])
    at.run()
    assert at.session_state["db_path"] == db_path


def test_default_paths(monkeypatch):
    # The pages do not open the database yet: the real one is not touched.
    at = start(monkeypatch, [])
    assert at.session_state["db_path"] == DEFAULT_DB
    assert at.session_state["config_path"] == DEFAULT_CONFIG
