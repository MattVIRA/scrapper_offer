"""Tests of the prompt of the cover letter (offers.letters.prompt)."""

import os
from datetime import datetime

import pytest

from offers.letters import LettersError
from offers.letters.inputs import Contact, Document, LetterInputs
from offers.letters.prompt import (
    LETTER_SCHEMA,
    build_prompt,
    load_prompt,
    prompt_version,
    save_prompt,
)
from tests.factories import make_offer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 10, 23, 9, 30)
INPUTS = LetterInputs(
    cvs=[Document("cv.pdf", "Data scientist, Python, 3 ans chez Foo.")],
    examples=[Document("acme.docx", "Ancienne lettre pour ACME."), Document("b.md", "Autre.")],
    instructions="Ton direct.",
    contact=Contact(name="Camille Martin", email="camille@example.com", city="Lyon"),
    ignored=[],
)


def test_repository_prompt_is_readable():
    text = load_prompt(os.path.join(ROOT, "prompts", "lettre.md"))
    # The fields of the answer are explained to Claude.
    for key in LETTER_SCHEMA["required"]:
        assert f"- {key} :" in text


def test_version_follows_the_text():
    assert prompt_version("Écris une lettre.") == prompt_version("Écris une lettre.")
    assert len(prompt_version("Écris une lettre.")) == 8
    assert prompt_version("Écris une lettre.") != prompt_version("Écris une lettre!")


def test_built_prompt_has_every_input_and_the_offer():
    offer = make_offer(
        description="Analyser les ventes.", candidate_profile="Python, SQL.", city="BERLIN"
    )

    text = build_prompt("Tu écris une lettre.\n", INPUTS, offer)

    assert text.startswith("Tu écris une lettre.\n\n<consignes>\nTon direct.\n</consignes>")
    assert '<cv fichier="cv.pdf">\nData scientist, Python, 3 ans chez Foo.\n</cv>' in text
    assert '<ancienne_lettre fichier="acme.docx">\nAncienne lettre pour ACME.' in text
    assert '<ancienne_lettre fichier="b.md">' in text
    offer_part = text[text.index("<offre>") : text.index("</offre>")]
    for expected in (
        "Titre : Data Analyst",
        "Entreprise : ACME",
        "Lieu : BERLIN, FRANCE",
        "Contrat : VIE de 12 mois",
        "Analyser les ventes.",
        "Python, SQL.",
    ):
        assert expected in offer_part
    assert '"paragraphs"' in text[text.index("</offre>") :]
    # The contact details are added by the program, never sent.
    assert "camille@example.com" not in text


def test_missing_parts_of_the_offer_and_no_instructions():
    inputs = LetterInputs(INPUTS.cvs, [], "", INPUTS.contact, [])
    offer = make_offer(company=None, city=None, country=None, duration_months=None)

    text = build_prompt("Prompt", inputs, offer)

    assert "<consignes>" not in text and "<ancienne_lettre" not in text
    assert "Entreprise : non précisée" in text and "Lieu : non précisé" in text
    assert "Contrat : VIE\n" in text
    assert "Description du poste :\nnon précisée" in text


def test_file_names_cannot_break_the_tags():
    inputs = LetterInputs([Document('a"b.txt', "CV")], [], "", INPUTS.contact, [])
    assert '<cv fichier="a&quot;b.txt">' in build_prompt("P", inputs, make_offer())


def test_missing_prompt(tmp_path):
    with pytest.raises(LettersError, match="Prompt des lettres introuvable.*letters.prompt"):
        load_prompt(tmp_path / "lettre.md")


def test_save_prompt_keeps_a_backup(tmp_path):
    path = tmp_path / "prompts" / "lettre.md"
    path.parent.mkdir()
    path.write_text("Ancien", encoding="utf-8")

    save_prompt(path, "Nouveau", tmp_path / "backup", NOW)

    assert path.read_text(encoding="utf-8") == "Nouveau"
    (backup,) = (tmp_path / "backup").iterdir()
    assert backup.name == "prompt_2026-10-23_093000.md"
    assert backup.read_text(encoding="utf-8") == "Ancien"


def test_save_a_new_prompt(tmp_path):
    path = tmp_path / "prompts" / "lettre.md"
    save_prompt(path, "Premier", tmp_path / "backup", NOW)
    assert path.read_text(encoding="utf-8") == "Premier"
    assert not (tmp_path / "backup").exists()


def test_save_prompt_writes_nothing_if_the_backup_fails(tmp_path):
    path = tmp_path / "lettre.md"
    path.write_text("Ancien", encoding="utf-8")
    # A file where the backup folder should be.
    blocked = tmp_path / "backup"
    blocked.write_text("", encoding="utf-8")

    with pytest.raises(LettersError, match="Impossible d'enregistrer le prompt.*n'a pas changé"):
        save_prompt(path, "Nouveau", blocked, NOW)

    assert path.read_text(encoding="utf-8") == "Ancien"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["backup", "lettre.md"]


def test_save_prompt_failed_write_keeps_the_old_file(tmp_path, monkeypatch):
    path = tmp_path / "lettre.md"
    path.write_text("Ancien", encoding="utf-8")

    def failing_replace(source, target):
        raise PermissionError("disque protégé")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(LettersError, match="disque protégé"):
        save_prompt(path, "Nouveau", tmp_path / "backup", NOW)
    assert path.read_text(encoding="utf-8") == "Ancien"
    assert not (tmp_path / "lettre.md.tmp").exists()
