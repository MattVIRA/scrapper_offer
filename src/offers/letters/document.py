"""Write a cover letter as a Word document."""

import itertools
import os
import re
import shutil
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
# Gap below the subject and above the signature.
SPACE_BEFORE_BLOCK = Pt(18)
SUBJECT_PREFIX = "Objet : "
# « Objet : » at the start of the subject written by Claude.
SUBJECT_WRITTEN = re.compile(r"^objet\s*:\s*", re.IGNORECASE)
# Folder of the replaced letters, inside the letters folder.
BACKUP_DIR = "backup"
LETTER_PREFIX = "lettre_"
LETTER_SUFFIX = ".docx"
# Longest company part of a file name.
COMPANY_MAX_LENGTH = 80
NO_COMPANY = "entreprise"
# Characters a file name cannot hold (macOS, Windows), replaced by a space.
FORBIDDEN_CHARACTERS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def letter_path(output_dir, offer, taken=frozenset()):
    """Return a free <output_dir>/lettre_<company>.docx.

    If that file exists, or is in taken (paths already given to other
    offers), the name gets _2, _3, ...: a letter is never overwritten.
    """
    stem = letter_stem(offer)
    for number in itertools.count(1):
        suffix = "" if number == 1 else f"_{number}"
        path = Path(output_dir) / f"{stem}{suffix}{LETTER_SUFFIX}"
        if path not in taken and not path.exists():
            return path


def letter_stem(offer):
    """Return "lettre_<company>", the company name as written, without forbidden characters."""
    company = " ".join(FORBIDDEN_CHARACTERS.sub(" ", offer.company or "").split())
    return LETTER_PREFIX + (company[:COMPANY_MAX_LENGTH].strip(" .") or NO_COMPANY)


def follows_naming(path, output_dir, offer):
    """Tell whether path is lettre_<company>.docx (or _2, _3, ...) in output_dir."""
    pattern = rf"{re.escape(letter_stem(offer))}(_\d+)?{re.escape(LETTER_SUFFIX)}"
    return (
        Path(path).parent == Path(output_dir) and re.fullmatch(pattern, Path(path).name) is not None
    )


def write_letter(path, letter, replace=False):
    """Write the letter at path, atomically.

    letter: answer of Claude (LETTER_SCHEMA). No contact details nor date:
    the letter follows the old letters of the profile, which have none.
    An existing file is kept, with a LettersError, unless replace is true:
    it is then copied into the backup folder first.
    """
    path = Path(path)
    if path.exists() and not replace:
        raise LettersError(
            f"La lettre {path} existe déjà, elle n'a pas été remplacée. "
            "Pour la refaire, choisis « Remplacer les lettres existantes »."
        )
    document = build_document(letter)
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


def backup_letter(path, move=False):
    """Copy (or move) a letter into the backup folder, named after its last change.

    Raise OSError if it cannot be done.
    """
    changed = datetime.fromtimestamp(path.stat().st_mtime)
    backup_dir = path.parent / BACKUP_DIR
    backup_dir.mkdir(exist_ok=True)
    target = backup_dir / f"{path.stem}_{changed:%Y-%m-%d_%H%M%S}{path.suffix}"
    if move:
        os.replace(path, target)
    else:
        shutil.copy2(path, target)


def build_document(letter):
    """Return the Word document of a letter."""
    document = docx.Document()
    set_layout(document)
    subject = strip_prefix(letter["subject"].strip())
    # An empty subject: the old letters have none.
    if subject:
        line = add(document, "", space_after=SPACE_BEFORE_BLOCK)
        line.add_run(SUBJECT_PREFIX).bold = True
        line.add_run(subject)
    add(document, letter["salutation"].strip())
    for paragraph in letter["paragraphs"]:
        if paragraph.strip():
            add(document, paragraph.strip(), align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    add(document, letter["closing"].strip(), align=WD_ALIGN_PARAGRAPH.JUSTIFY)
    add(
        document,
        letter["signature"].strip(),
        align=WD_ALIGN_PARAGRAPH.RIGHT,
        before=SPACE_BEFORE_BLOCK,
    )
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


def strip_prefix(subject):
    """Remove an « Objet : » Claude may have written despite the prompt."""
    return SUBJECT_WRITTEN.sub("", subject)
