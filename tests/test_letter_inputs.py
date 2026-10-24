"""Tests of the reading of the profile folder (offers.letters.inputs)."""

import pytest

from offers.config import LettersConfig
from offers.letters import LettersError
from offers.letters.inputs import Contact, load_inputs, read_text
from tests.letter_files import make_profile, write_docx, write_pdf


def inputs_of(profile):
    return load_inputs(LettersConfig(profile_dir=profile))


def test_complete_profile(tmp_path):
    profile = make_profile(tmp_path)
    (profile / "cv" / "notes.txt").write_text("Anglais courant", encoding="utf-8")

    inputs = inputs_of(profile)

    assert [(cv.name, cv.text.strip()) for cv in inputs.cvs] == [
        ("cv.pdf", "Camille Martin - Data Scientist - Python"),
        ("notes.txt", "Anglais courant"),
    ]
    assert [(e.name, e.text) for e in inputs.examples] == [
        ("lettre_acme.docx", "Madame, Monsieur,\nAncien style.")
    ]
    assert inputs.instructions == "Ton direct, une page."
    assert inputs.contact == Contact(
        name="Camille Martin",
        email="camille@example.com",
        city="Paris",
        address="1 rue de la Paix, 75002 Paris",
        phone="06 00 00 00 00",
    )
    assert inputs.ignored == []


def test_optional_parts_may_be_missing(tmp_path):
    profile = make_profile(tmp_path, contact="name: A\nemail: a@example.com\ncity: Lyon\n")
    (profile / "consignes.md").unlink()
    (profile / "exemples" / "lettre_acme.docx").unlink()

    inputs = inputs_of(profile)

    assert inputs.examples == [] and inputs.instructions == ""
    assert inputs.contact == Contact(name="A", email="a@example.com", city="Lyon")


def test_other_formats_are_ignored_and_listed(tmp_path):
    profile = make_profile(tmp_path)
    (profile / "cv" / "photo.png").write_bytes(b"png")
    (profile / "exemples" / "vieille.odt").write_bytes(b"odt")
    # System and Word lock files are not shown.
    (profile / "cv" / ".DS_Store").write_bytes(b"")
    (profile / "exemples" / "~$ttre.docx").write_bytes(b"")

    inputs = inputs_of(profile)

    assert [path.name for path in inputs.ignored] == ["photo.png", "vieille.odt"]
    assert [cv.name for cv in inputs.cvs] == ["cv.pdf"]


def test_markdown_file(tmp_path):
    path = tmp_path / "cv.md"
    path.write_text("# CV\nPython", encoding="utf-8")
    assert read_text(path) == "# CV\nPython"


def test_missing_profile_folder(tmp_path):
    with pytest.raises(LettersError, match="Dossier du profil introuvable"):
        inputs_of(tmp_path / "profil")


@pytest.mark.parametrize("files", [[], ["photo.png"]])
def test_no_cv(tmp_path, files):
    profile = make_profile(tmp_path)
    (profile / "cv" / "cv.pdf").unlink()
    for name in files:
        (profile / "cv" / name).write_bytes(b"x")

    with pytest.raises(LettersError, match="Aucun CV lisible.*Ajoute ton CV"):
        inputs_of(profile)


def test_missing_contact(tmp_path):
    profile = make_profile(tmp_path, contact=None)
    with pytest.raises(LettersError, match="Coordonnées introuvables : crée .*coordonnees.yaml"):
        inputs_of(profile)


@pytest.mark.parametrize(
    "contact, message",
    [
        ("- name\n", "doit contenir name"),
        ("name: A\nemail: a@example.com\n", "« city » est absent ou vide"),
        ("name: A\nemail: a@example.com\ncity: ''\n", "« city » est absent ou vide"),
        ("name: A\nemail: a@b.c\ncity: Lyon\nphone: 0600000000\n", "« phone » doit être du texte"),
        ("name: [\n", "Impossible de lire"),
    ],
)
def test_badly_filled_contact(tmp_path, contact, message):
    profile = make_profile(tmp_path, contact=contact)
    with pytest.raises(LettersError, match=message):
        inputs_of(profile)


def test_unreadable_files(tmp_path):
    broken_pdf = tmp_path / "cv.pdf"
    broken_pdf.write_bytes(b"pas un pdf")
    broken_docx = tmp_path / "lettre.docx"
    broken_docx.write_bytes(b"pas un docx")
    bad_text = tmp_path / "notes.txt"
    bad_text.write_bytes(b"\xff\xfe\xfa")

    for path in (broken_pdf, broken_docx, bad_text):
        with pytest.raises(LettersError, match=f"Impossible de lire .*{path.name}") as error:
            read_text(path)
        assert error.value.__cause__ is not None


def test_file_without_text(tmp_path):
    empty_pdf = tmp_path / "scan.pdf"
    write_pdf(empty_pdf, "")
    empty_docx = tmp_path / "vide.docx"
    write_docx(empty_docx, [])

    for path in (empty_pdf, empty_docx):
        with pytest.raises(LettersError, match="Aucun texte trouvé"):
            read_text(path)
