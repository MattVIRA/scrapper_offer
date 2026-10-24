"""Tests of the Word document of a letter (offers.letters.document)."""

import os
from datetime import date
from pathlib import Path

import docx
import pytest

from offers.letters import LettersError
from offers.letters.document import french_date, letter_path, write_letter
from offers.letters.inputs import Contact
from tests.factories import make_offer

TODAY = date(2026, 10, 23)
LETTER = {
    "subject": "Candidature au poste de Data Analyst (VIE)",
    "salutation": "Madame, Monsieur,",
    "paragraphs": ["Premier paragraphe.", "  ", "Deuxième paragraphe."],
    "closing": "Je vous prie d'agréer mes salutations distinguées.",
}
CONTACT = Contact(
    name="Camille Martin",
    email="camille@example.com",
    city="Lyon",
    address="1 rue de la Paix\n69001 Lyon",
    phone="06 00 00 00 00",
)
OFFER = make_offer(company="ACME")


def texts(path):
    """Return the non-empty paragraphs of a Word file."""
    return [p.text for p in docx.Document(str(path)).paragraphs if p.text]


def test_written_letter_can_be_read_back(tmp_path):
    path = tmp_path / "lettres" / "a.docx"

    write_letter(path, LETTER, CONTACT, OFFER, TODAY)

    assert texts(path) == [
        "Camille Martin",
        "1 rue de la Paix",
        "69001 Lyon",
        "06 00 00 00 00",
        "camille@example.com",
        "ACME",
        "Lyon, le 23 octobre 2026",
        "Objet : Candidature au poste de Data Analyst (VIE)",
        "Madame, Monsieur,",
        "Premier paragraphe.",
        "Deuxième paragraphe.",
        "Je vous prie d'agréer mes salutations distinguées.",
        "Camille Martin",
    ]
    assert sorted(p.name for p in path.parent.iterdir()) == ["a.docx"]


def test_subject_already_starting_with_objet(tmp_path):
    path = tmp_path / "a.docx"
    write_letter(path, {**LETTER, "subject": "Objet : Candidature"}, CONTACT, OFFER, TODAY)
    assert "Objet : Candidature" in texts(path)

    path = tmp_path / "b.docx"
    write_letter(path, {**LETTER, "subject": "Objectif data"}, CONTACT, OFFER, TODAY)
    assert "Objet : Objectif data" in texts(path)


def test_minimal_contact_and_no_company(tmp_path):
    path = tmp_path / "a.docx"
    contact = Contact(name="A", email="a@example.com", city="Lyon")
    write_letter(path, LETTER, contact, make_offer(company=None), TODAY)
    assert texts(path)[:3] == ["A", "a@example.com", "Lyon, le 23 octobre 2026"]


def test_french_date():
    assert french_date(date(2026, 3, 1)) == "1er mars 2026"
    assert french_date(date(2026, 8, 15)) == "15 août 2026"


@pytest.mark.parametrize(
    "company, name",
    [
        ("ACME", "test_7_ACME.docx"),
        ("Société Générale / Paris", "test_7_Societe-Generale-Paris.docx"),
        ("L'Oréal (H/F) ...", "test_7_L-Oreal-H-F.docx"),
        (None, "test_7_entreprise.docx"),
        ("???", "test_7_entreprise.docx"),
        ("A" * 30 + " " + "B" * 30, "test_7_" + "A" * 30 + "-" + "B" * 9 + ".docx"),
    ],
)
def test_letter_path(company, name):
    offer = make_offer(source_id="7", company=company)
    assert letter_path(Path("/l"), offer) == Path("/l") / name


def test_source_id_is_made_safe():
    offer = make_offer(source_id="a/b c", company="X")
    assert letter_path("/l", offer).name == "test_a-b-c_X.docx"


def test_existing_letter_is_not_replaced(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"lettre de l'utilisateur")

    with pytest.raises(LettersError, match="existe déjà.*Remplacer les lettres existantes"):
        write_letter(path, LETTER, CONTACT, OFFER, TODAY)

    assert path.read_bytes() == b"lettre de l'utilisateur"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.docx"]


def test_replaced_letter_is_copied_first(tmp_path):
    path = tmp_path / "a.docx"
    path.write_bytes(b"ancienne")
    os.utime(path, (1761200000, 1761200000))

    write_letter(path, LETTER, CONTACT, OFFER, TODAY, replace=True)

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
        write_letter(path, LETTER, CONTACT, OFFER, TODAY)

    assert list(tmp_path.iterdir()) == []


def test_failed_replacement_keeps_the_old_letter(tmp_path, monkeypatch):
    path = tmp_path / "a.docx"
    path.write_bytes(b"ancienne")

    def failing_replace(source, target):
        raise PermissionError("fichier ouvert dans Word")

    monkeypatch.setattr(os, "replace", failing_replace)
    with pytest.raises(LettersError, match="fichier ouvert dans Word"):
        write_letter(path, LETTER, CONTACT, OFFER, TODAY, replace=True)

    assert path.read_bytes() == b"ancienne"
    assert not (tmp_path / "a.docx.tmp").exists()
