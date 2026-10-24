"""Tests of the Word document of a letter (offers.letters.document)."""

import os
from pathlib import Path

import docx
import pytest

from offers.letters import LettersError
from offers.letters.document import follows_naming, letter_path, write_letter
from tests.factories import make_offer

LETTER = {
    "subject": "Candidature au poste de Data Analyst (VIE)",
    "salutation": "Madame, Monsieur,",
    "paragraphs": ["Premier paragraphe.", "  ", "Deuxième paragraphe."],
    "closing": "Je vous prie d'agréer mes salutations distinguées.",
    "signature": "Camille Martin",
}


def texts(path):
    """Return the non-empty paragraphs of a Word file."""
    return [p.text for p in docx.Document(str(path)).paragraphs if p.text]


def test_written_letter_can_be_read_back(tmp_path):
    path = tmp_path / "lettres" / "a.docx"

    write_letter(path, LETTER)

    # No contact details nor date: the old letters have none.
    assert texts(path) == [
        "Objet : Candidature au poste de Data Analyst (VIE)",
        "Madame, Monsieur,",
        "Premier paragraphe.",
        "Deuxième paragraphe.",
        "Je vous prie d'agréer mes salutations distinguées.",
        "Camille Martin",
    ]
    assert sorted(p.name for p in path.parent.iterdir()) == ["a.docx"]


def test_empty_subject_gives_no_subject_line(tmp_path):
    path = tmp_path / "a.docx"
    write_letter(path, {**LETTER, "subject": " "})
    assert texts(path)[0] == "Madame, Monsieur,"


def test_subject_already_starting_with_objet(tmp_path):
    path = tmp_path / "a.docx"
    write_letter(path, {**LETTER, "subject": "Objet : Candidature"})
    assert "Objet : Candidature" in texts(path)

    path = tmp_path / "b.docx"
    write_letter(path, {**LETTER, "subject": "Objectif data"})
    assert "Objet : Objectif data" in texts(path)


@pytest.mark.parametrize(
    "company, name",
    [
        ("ACME", "lettre_ACME.docx"),
        # The name as written; only what a file name cannot hold is removed.
        ("Société Générale", "lettre_Société Générale.docx"),
        ("Société Générale / Paris", "lettre_Société Générale Paris.docx"),
        ("L'Oréal (H/F)", "lettre_L'Oréal (H F).docx"),
        (None, "lettre_entreprise.docx"),
        ("???", "lettre_entreprise.docx"),
        ("A" * 50 + " " + "B" * 50, "lettre_" + "A" * 50 + " " + "B" * 29 + ".docx"),
    ],
)
def test_letter_path(company, name, tmp_path):
    assert letter_path(tmp_path, make_offer(company=company)) == tmp_path / name


def test_letter_path_of_a_duplicate(tmp_path):
    offer = make_offer(company="ACME")
    (tmp_path / "lettre_ACME.docx").write_bytes(b"x")
    taken = {tmp_path / "lettre_ACME_2.docx"}

    # An existing file and a name given to another offer are both skipped.
    assert letter_path(tmp_path, offer, taken) == tmp_path / "lettre_ACME_3.docx"


def test_existing_letter_is_not_replaced(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"lettre de l'utilisateur")

    with pytest.raises(LettersError, match="existe déjà.*Remplacer les lettres existantes"):
        write_letter(path, LETTER)

    assert path.read_bytes() == b"lettre de l'utilisateur"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.docx"]


def test_replaced_letter_is_copied_first(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"ancienne")
    os.utime(path, (1761200000, 1761200000))

    write_letter(path, LETTER, replace=True)

    assert "Premier paragraphe." in texts(path)
    (backup,) = (tmp_path / "backup").iterdir()
    assert backup.name.startswith("a_2025-10-") and backup.suffix == ".docx"
    assert backup.read_bytes() == b"ancienne"


def test_nothing_is_left_when_writing_fails(tmp_path, monkeypatch):
    path = tmp_path / "a.docx"

    def failing_save(document, target):
        Path(target).write_bytes(b"moitie")
        raise OSError("disque plein")

    monkeypatch.setattr(docx.document.Document, "save", failing_save)
    with pytest.raises(LettersError, match="Impossible d'écrire la lettre.*disque plein"):
        write_letter(path, LETTER)

    assert list(tmp_path.iterdir()) == []


def test_failed_replacement_keeps_the_old_letter(tmp_path, monkeypatch):
    path = tmp_path / "a.docx"
    path.write_bytes(b"ancienne")

    def failing_replace(source, target):
        raise PermissionError("fichier ouvert dans Word")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(LettersError, match="fichier ouvert dans Word"):
        write_letter(path, LETTER, replace=True)

    assert path.read_bytes() == b"ancienne"
    assert not (tmp_path / "a.docx.tmp").exists()


def test_follows_naming(tmp_path):
    offer = make_offer(company="ACME")
    assert follows_naming(tmp_path / "lettre_ACME.docx", tmp_path, offer)
    assert follows_naming(tmp_path / "lettre_ACME_3.docx", tmp_path, offer)
    assert not follows_naming(tmp_path / "business_france_1_ACME.docx", tmp_path, offer)
    assert not follows_naming(tmp_path / "lettre_Foo.docx", tmp_path, offer)
    assert not follows_naming(tmp_path / "autre" / "lettre_ACME.docx", tmp_path, offer)
