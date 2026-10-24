"""Tests of the « Lettres » page, with a fake Claude, a fake profile and a test database."""

import subprocess
import sys
from datetime import datetime

import pytest
from streamlit.testing.v1 import AppTest

from offers import claude_code
from offers.__main__ import UI_APP
from offers.claude_code import ClaudeError
from offers.letters import LettersError
from offers.letters.prompt import prompt_version
from offers.storage.database import connect, list_letters, record_letter, set_letter_status
from offers.ui import letters_job
from offers.ui.letter_link import reveal_in_finder
from tests.letter_files import make_profile
from tests.test_storage_offers import offer, save
from tests.test_ui_offers import TIMEOUT, button

LETTERS = "app_pages/letters.py"
CONFIG = "sources:\n  business_france:\n    searches: []\n"
PROMPT = "Écris une lettre."
NOW = datetime(2026, 10, 23, 9, 0)
WAIT = 10


def fake_claude(prompt, schema, model=None):
    if "Titre : Data 2\n" in prompt:
        raise ClaudeError("Limite d'usage du forfait Claude atteinte.")
    return {"subject": "S", "salutation": "Madame,", "paragraphs": ["P"], "closing": "C"}


@pytest.fixture
def paths(tmp_path):
    (tmp_path / "config.yaml").write_text(CONFIG, encoding="utf-8")
    make_profile(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "lettre.md").write_text(PROMPT, encoding="utf-8")
    db = tmp_path / "data" / "offers.db"
    conn = connect(db)
    save(conn, [offer(n, company=f"Société {n}") for n in (1, 2, 3)])
    set_letter_status(conn, [1, 2], "to_write", NOW)
    conn.close()
    return {"config": tmp_path / "config.yaml", "db": db}


@pytest.fixture(autouse=True)
def fresh_runner(monkeypatch):
    monkeypatch.setattr(claude_code, "ask_json", fake_claude)
    letters_job.get_letters_runner.clear()
    yield
    letters_job.get_letters_runner.clear()


@pytest.fixture
def open_page(monkeypatch, paths):
    argv = ["app.py", "--db", str(paths["db"]), "--config", str(paths["config"])]
    monkeypatch.setattr(sys, "argv", argv)

    def open_page():
        at = AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT).run()
        return at.switch_page(LETTERS).run()

    return open_page


def texts(elements):
    return [element.value for element in elements]


def letter_count(db):
    conn = connect(db)
    try:
        return len(list_letters(conn))
    finally:
        conn.close()


def generate(at):
    """Click « Générer les lettres », then « Confirmer », wait for the end, show the page."""
    button(at, "Générer les lettres").click().run()
    button(at, "Confirmer").click().run()
    job = letters_job.get_letters_runner().job
    assert job.finished.wait(WAIT)
    return at.run()


# --- Inputs and prompt --------------------------------------------------------


def test_inputs_and_targets_are_listed(open_page, tmp_path):
    (tmp_path / "profil" / "cv" / "photo.png").write_bytes(b"x")
    at = open_page()

    assert not at.exception
    inputs = at.table[0].value
    assert list(inputs.index) == ["CV", "Anciennes lettres", "Consignes", "Coordonnées"]
    assert list(inputs.iloc[:, 0]) == [
        "cv.pdf",
        "lettre_acme.docx",
        "consignes.md",
        "Camille Martin, Paris",
    ]
    assert "photo.png" in texts(at.warning)[0]
    targets = at.dataframe[0].value
    assert list(targets["Titre"]) == ["Data 1", "Data 2"]
    assert at.text_area[0].value == PROMPT
    assert f"version {prompt_version(PROMPT)}" in " ".join(texts(at.caption))
    assert not button(at, "Générer les lettres").disabled


def test_missing_input_replaces_the_button(open_page, tmp_path):
    (tmp_path / "profil" / "cv" / "cv.pdf").unlink()
    at = open_page()

    assert texts(at.error)[0].startswith("Aucun CV lisible")
    assert not [b for b in at.button if b.label == "Générer les lettres"]


def test_prompt_is_saved(open_page, tmp_path, paths):
    at = open_page()
    assert button(at, "Enregistrer le prompt").disabled

    at.text_area[0].set_value("Nouveau prompt.").run()
    assert "Modifications non enregistrées" in " ".join(texts(at.caption))
    button(at, "Enregistrer le prompt").click().run()

    assert (tmp_path / "prompts" / "lettre.md").read_text(encoding="utf-8") == "Nouveau prompt."
    assert "Prompt enregistré." in texts(at.success)
    assert f"version {prompt_version('Nouveau prompt.')}" in " ".join(texts(at.caption))
    (backup,) = (paths["db"].parent / "backup").glob("prompt_*.md")
    assert backup.read_text(encoding="utf-8") == PROMPT


def test_failed_prompt_save_is_shown(open_page, paths, tmp_path):
    (paths["db"].parent / "backup").write_text("pas un dossier")
    at = open_page()

    at.text_area[0].set_value("Nouveau prompt.").run()
    button(at, "Enregistrer le prompt").click().run()

    assert any(t.startswith("Impossible d'enregistrer le prompt") for t in texts(at.error))
    assert (tmp_path / "prompts" / "lettre.md").read_text(encoding="utf-8") == PROMPT


# --- Generation ---------------------------------------------------------------


def test_no_target_no_generation(open_page, paths):
    conn = connect(paths["db"])
    set_letter_status(conn, [1, 2], None, NOW)
    conn.close()
    at = open_page()

    assert button(at, "Générer les lettres").disabled
    assert any("Aucune offre « À rédiger »" in t for t in texts(at.info))


def test_nothing_starts_without_confirmation(open_page, paths):
    at = open_page()
    button(at, "Générer les lettres").click().run()

    assert "Data 1 — Société 1" in at.text[0].value
    assert any("forfait Claude" in t for t in texts(at.warning))
    button(at, "Annuler").click().run()

    assert letters_job.get_letters_runner().job is None
    assert not [b for b in at.button if b.label == "Confirmer"]
    assert letter_count(paths["db"]) == 0


def test_confirmed_generation_writes_the_letters_and_shows_the_summary(open_page, paths):
    at = generate(open_page())

    assert not at.exception
    assert texts(at.success) == ["Data 1 (Société 1) : lettre écrite (fake_1_Societe-1.docx)."]
    assert texts(at.error) == [
        "Data 2 (Société 2) : en erreur, pas de lettre. Limite d'usage du forfait Claude atteinte."
    ]
    assert letter_count(paths["db"]) == 1
    # The database was saved first.
    assert list((paths["db"].parent / "backup").glob("offers_*.db"))
    # Data 1 is no longer « À rédiger ».
    assert list(at.dataframe[0].value["Titre"]) == ["Data 2"]


def test_existing_letter_can_be_replaced(open_page, paths, tmp_path):
    (tmp_path / "lettres").mkdir()
    (tmp_path / "lettres" / "fake_1_Societe-1.docx").write_bytes(b"ancienne")
    at = open_page()
    assert list(at.dataframe[0].value["Lettre"]) == ["déjà présente", ""]

    button(at, "Générer les lettres").click().run()
    at.checkbox(key="letters_replace").check().run()
    button(at, "Confirmer").click().run()
    assert letters_job.get_letters_runner().job.finished.wait(WAIT)
    at.run()

    assert texts(at.success) == ["Data 1 (Société 1) : lettre écrite (fake_1_Societe-1.docx)."]
    assert list((tmp_path / "lettres" / "backup").iterdir())


# --- Letters written (T5.8) ---------------------------------------------------


def test_letters_written_are_listed_with_a_finder_button(open_page, paths, tmp_path):
    conn = connect(paths["db"])
    record_letter(conn, 3, tmp_path / "lettres" / "c.docx", "abcd1234", NOW)
    conn.close()
    at = generate(open_page())

    assert any("Data 1" in m.value for m in at.markdown)
    assert any("Data 3" in m.value for m in at.markdown)
    captions = [t for t in texts(at.caption) if t.startswith("Lettre du")]
    # The most recent first.
    assert captions[1] == "Lettre du 23/10/2026 à 09:00 · prompt abcd1234 · Sans statut · c.docx"
    finder = [b for b in at.button if b.label == "Ouvrir dans le Finder"]
    assert len(finder) == 2
    assert button(at, "Ouvrir le dossier des lettres")


def test_finder_button_of_a_missing_file(open_page, paths, tmp_path, monkeypatch):
    conn = connect(paths["db"])
    record_letter(conn, 3, tmp_path / "lettres" / "absente.docx", "v1", NOW)
    conn.close()
    calls = []
    monkeypatch.setattr(subprocess, "run", lambda command, **options: calls.append(command))
    at = open_page()

    button(at, "Ouvrir dans le Finder").click().run()

    assert not at.exception
    assert any(t.startswith("Introuvable") for t in texts(at.error))
    assert calls == []


def test_no_letter_yet(open_page):
    at = open_page()
    assert "Aucune lettre pour l'instant." in texts(at.info)


# --- Finder -------------------------------------------------------------------


class FakeRun:
    def __init__(self, returncode=0, stderr=""):
        self.returncode, self.stderr = returncode, stderr
        self.commands = []

    def __call__(self, command, **options):
        self.commands.append(command)
        return subprocess.CompletedProcess(command, self.returncode, "", self.stderr)


def test_reveal_a_file_or_a_folder(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"x")
    run = FakeRun()

    reveal_in_finder(path, run=run)
    reveal_in_finder(tmp_path, run=run)

    assert run.commands == [["open", "-R", str(path)], ["open", str(tmp_path)]]


def test_reveal_errors(tmp_path):
    with pytest.raises(LettersError, match="Introuvable.*« À rédiger »"):
        reveal_in_finder(tmp_path / "absent.docx", run=FakeRun())
    with pytest.raises(LettersError, match="Impossible d'ouvrir le Finder : refusé"):
        reveal_in_finder(tmp_path, run=FakeRun(1, "refusé"))
