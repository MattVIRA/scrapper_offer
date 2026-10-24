"""Tests of the generation of the letters, with a fake Claude: never the real one."""

from datetime import datetime

import docx
import pytest

from offers.claude_code import ClaudeError
from offers.config import LettersConfig
from offers.letters import LettersError
from offers.letters.generate import run_letters
from offers.letters.prompt import prompt_version
from offers.storage.database import StorageError, connect, hide, set_letter_status
from offers.summary import letters_summary
from tests.letter_files import make_profile
from tests.test_storage_offers import offer, save, stored

NOW = datetime(2026, 10, 23, 9, 30)
LATER = datetime(2026, 10, 23, 18, 0)


def answer(text="Corps de la lettre."):
    return {
        "subject": "Candidature",
        "salutation": "Madame, Monsieur,",
        "paragraphs": [text],
        "closing": "Bien à vous.",
    }


class FakeClaude:
    """Answers a letter, or raises for the offers whose title is in failing."""

    def __init__(self, failing=(), text="Corps de la lettre."):
        self.failing = set(failing)
        self.text = text
        self.prompts = []

    def __call__(self, prompt, schema, model=None):
        self.prompts.append((prompt, model))
        if any(f"Titre : {title}\n" in prompt for title in self.failing):
            raise ClaudeError("Limite d'usage du forfait Claude atteinte.")
        return answer(self.text)


@pytest.fixture
def letters_config(tmp_path):
    prompt = tmp_path / "prompts" / "lettre.md"
    prompt.parent.mkdir()
    prompt.write_text("Écris une lettre.", encoding="utf-8")
    return LettersConfig(
        profile_dir=make_profile(tmp_path),
        output_dir=tmp_path / "lettres",
        prompt=prompt,
        model="sonnet",
    )


@pytest.fixture
def conn(tmp_path):
    conn = connect(tmp_path / "offers.db")
    save(conn, [offer(n, company=f"Société {n}") for n in (1, 2, 3)])
    set_letter_status(conn, [1, 2, 3], "to_write", NOW)
    return conn


def generate(conn, letters_config, ask, ids=(1, 2, 3), **options):
    return run_letters(conn, letters_config, list(ids), NOW, ask=ask, **options)


def paragraphs(path):
    return [p.text for p in docx.Document(str(path)).paragraphs]


def test_one_offer_in_error_does_not_stop_the_others(conn, letters_config):
    done = []
    ask = FakeClaude(failing=["Data 2"])

    report = generate(conn, letters_config, ask, on_letter_done=done.append)

    assert [r.stored.offer.reference for r in report.written] == ["fake-1", "fake-3"]
    (failed,) = report.failed
    assert failed.stored.offer.reference == "fake-2" and "Limite d'usage" in failed.error
    assert done == report.results
    offers = stored(conn)
    assert [offers[f"fake-{n}"].letter_status for n in (1, 2, 3)] == [
        "written",
        "to_write",
        "written",
    ]
    letter = offers["fake-1"].letter
    assert letter.path == letters_config.output_dir / "fake_1_Societe-1.docx"
    assert "Corps de la lettre." in paragraphs(letter.path)
    assert letter.prompt_version == prompt_version("Écris une lettre.")
    assert sorted(p.name for p in letters_config.output_dir.iterdir()) == [
        "fake_1_Societe-1.docx",
        "fake_3_Societe-3.docx",
    ]
    # Model of the settings, prompt of the file.
    assert {model for _, model in ask.prompts} == {"sonnet"}
    assert all(prompt.startswith("Écris une lettre.") for prompt, _ in ask.prompts)

    lines = letters_summary(report)
    assert lines[0] == "Data 1 (Société 1) : lettre écrite (fake_1_Societe-1.docx)."
    assert lines[1].startswith("Data 2 (Société 2) : en erreur, pas de lettre. Limite")
    assert lines[-1] == (
        "2 lettres écrites, 1 en erreur, 0 déjà présentes. "
        "Les offres en erreur restent « À rédiger » : relance pour les refaire."
    )


def test_running_again_does_not_redo_the_work(conn, letters_config):
    generate(conn, letters_config, FakeClaude(failing=["Data 2"]))
    ask = FakeClaude()

    report = generate(conn, letters_config, ask)

    assert [r.stored.offer.reference for r in report.results] == ["fake-2"]
    assert len(ask.prompts) == 1
    assert conn.execute("SELECT COUNT(*) FROM letters").fetchone()[0] == 3


def test_only_the_chosen_offers_out_of_the_trash(conn, letters_config):
    hide(conn, [3], NOW)
    report = generate(conn, letters_config, FakeClaude(), ids=[2, 3])
    assert [r.stored.offer.reference for r in report.results] == ["fake-2"]


def test_existing_file_is_skipped_without_replace(conn, letters_config):
    generate(conn, letters_config, FakeClaude(), ids=[1])
    set_letter_status(conn, [1], "to_write", NOW)
    ask = FakeClaude(text="Nouvelle version.")

    report = generate(conn, letters_config, ask, ids=[1])

    (skipped,) = report.skipped
    assert ask.prompts == []
    assert "Corps de la lettre." in paragraphs(skipped.path)
    assert stored(conn)["fake-1"].letter_status == "to_write"
    assert letters_summary(report) == [
        "Data 1 (Société 1) : lettre déjà présente (fake_1_Societe-1.docx), non remplacée.",
        "0 lettres écrites, 0 en erreur, 1 déjà présentes.",
    ]


def test_existing_file_is_replaced_on_demand(conn, letters_config):
    generate(conn, letters_config, FakeClaude(), ids=[1])
    set_letter_status(conn, [1], "to_write", NOW)

    report = run_letters(
        conn, letters_config, [1], LATER, replace=True, ask=FakeClaude(text="Nouvelle version.")
    )

    (written,) = report.written
    assert "Nouvelle version." in paragraphs(written.path)
    assert len(list((letters_config.output_dir / "backup").iterdir())) == 1
    letter = stored(conn)["fake-1"].letter
    assert letter.created_at == LATER
    assert conn.execute("SELECT COUNT(*) FROM letters").fetchone()[0] == 1


def test_missing_input_stops_before_any_call(conn, letters_config):
    (letters_config.profile_dir / "cv" / "cv.pdf").unlink()
    ask = FakeClaude()
    with pytest.raises(LettersError, match="Aucun CV"):
        generate(conn, letters_config, ask)
    assert ask.prompts == []


def test_file_is_removed_if_the_database_refuses_it(conn, letters_config, monkeypatch):
    def failing_record(*args):
        raise StorageError("base verrouillée")

    monkeypatch.setattr("offers.letters.generate.record_letter", failing_record)
    report = generate(conn, letters_config, FakeClaude(), ids=[1])

    (failed,) = report.failed
    assert failed.error == "base verrouillée"
    assert list(letters_config.output_dir.iterdir()) == []
    assert stored(conn)["fake-1"].letter_status == "to_write"
