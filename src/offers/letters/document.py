"""Write a cover letter as a Word document."""

import os
import re
import shutil
import unicodedata
from datetime import datetime
from pathlib import Path

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Pt

from offers.letters import LettersError

FONT_NAME = "Calibri"
FONT_SIZE = Pt(11)
MARGIN = Cm(2.5)
SPACE_AFTER = Pt(6)
# Gap above the date, the subject and the signature.
SPACE_BEFORE_BLOCK = Pt(18)
SUBJECT_PREFIX = "Objet : "
# « Objet : » at the start of the subject written by Claude.
SUBJECT_WRITTEN = re.compile(r"^objet\s*:\s*", re.IGNORECASE)
# Folder of the replaced letters, inside the letters folder.
BACKUP_DIR = "backup"
# Longest company part of a file name.
COMPANY_MAX_LENGTH = 40
NO_COMPANY = "entreprise"
# Runs of characters other than ASCII letters and digits, in file names.
UNSAFE_CHARACTERS = re.compile(r"[^A-Za-z0-9]+")
MONTHS = (
    "janvier", "février", "mars", "avril", "mai", "juin",
    "juillet", "août", "septembre", "octobre", "novembre", "décembre",
)  # fmt: skip


def letter_path(output_dir, offer):
    """Return <output_dir>/<source>_<id>_<company>.docx, with a safe file name."""
    company = safe_name(offer.company or "")[:COMPANY_MAX_LENGTH].strip("-") or NO_COMPANY
    name = "_".join([safe_name(offer.source), safe_name(offer.source_id), company])
    return Path(output_dir) / f"{name}.docx"


def safe_name(text):
    """Return text without accents, with "-" instead of spaces and other characters."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return UNSAFE_CHARACTERS.sub("-", ascii_text).strip("-")


def write_letter(path, letter, contact, offer, today, replace=False):
    """Write the letter at path, atomically.

    letter: answer of Claude (LETTER_SCHEMA); contact: Contact; offer: Offer.
    An existing file is kept, with a LettersError, unless replace is true:
    it is then copied into the backup folder first.
    """
    path = Path(path)
    if path.exists() and not replace:
        raise LettersError(
            f"La lettre {path} existe déjà, elle n'a pas été remplacée. "
            "Pour la refaire, choisis « Remplacer les lettres existantes »."
        )
    document = build_document(letter, contact, offer, today)
    temporary = path.with_name(path.name + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            backup_letter(path)
        document.save(str(temporary))
        os.replace(temporary, path)
    except OSError as err:
        temporary.unlink(missing_ok=True)
        raise LettersError(f"Impossible d'écrire la lettre {path} : {err}.") from err


def backup_letter(path):
    """Copy a letter about to be replaced, named after its last change."""
    changed = datetime.fromtimestamp(path.stat().st_mtime)
    backup_dir = path.parent / BACKUP_DIR
    backup_dir.mkdir(exist_ok=True)
    shutil.copy2(path, backup_dir / f"{path.stem}_{changed:%Y-%m-%d_%H%M%S}{path.suffix}")


def build_document(letter, contact, offer, today):
    """Return the Word document of a letter."""
    document = docx.Document()
    set_layout(document)
    for number, line in enumerate(contact_lines(contact)):
        add(document, line, bold=number == 0, space_after=0)
    if offer.company:
        add(document, offer.company, align=WD_ALIGN_PARAGRAPH.RIGHT, before=SPACE_BEFORE_BLOCK)
    add(
        document,
        f"{contact.city}, le {french_date(today)}",
        align=WD_ALIGN_PARAGRAPH.RIGHT,
        before=SPACE_BEFORE_BLOCK,
    )
    subject = add(document, "", before=SPACE_BEFORE_BLOCK)
    subject.add_run(SUBJECT_PREFIX).bold = True
    subject.add_run(strip_prefix(letter["subject"].strip()))
    add(document, letter["salutation"].strip(), before=SPACE_BEFORE_BLOCK)
    for paragraph in letter["paragraphs"]:
        if paragraph.strip():
            add(document, paragraph.strip(), align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    add(document, letter["closing"].strip(), align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    add(document, contact.name, align=WD_ALIGN_PARAGRAPH.RIGHT, before=SPACE_BEFORE_BLOCK)
    return document


def set_layout(document):
    """Set the margins and the font of the whole document."""
    for section in document.sections:
        section.top_margin = section.bottom_margin = MARGIN
        section.left_margin = section.right_margin = MARGIN
    font = document.styles["Normal"].font
    font.name = FONT_NAME
    font.size = FONT_SIZE


def add(document, text, align=None, bold=False, before=None, space_after=SPACE_AFTER):
    """Add a paragraph and return it."""
    paragraph = document.add_paragraph()
    if text:
        paragraph.add_run(text).bold = bold
    paragraph.alignment = align
    paragraph.paragraph_format.space_after = space_after
    if before is not None:
        paragraph.paragraph_format.space_before = before
    return paragraph


def contact_lines(contact):
    """Return the lines of the header: name, address, phone, e-mail."""
    lines = [contact.name, *contact.address.splitlines(), contact.phone, contact.email]
    return [line.strip() for line in lines if line.strip()]


def strip_prefix(subject):
    """Remove an « Objet : » Claude may have written despite the prompt."""
    return SUBJECT_WRITTEN.sub("", subject)


def french_date(day):
    """Return a date as in a French letter: "1er mars 2026", "23 octobre 2026"."""
    number = "1er" if day.day == 1 else str(day.day)
    return f"{number} {MONTHS[day.month - 1]} {day.year}"
