"""Read what a cover letter is written from: the files of the profile folder."""

import zipfile
from dataclasses import dataclass
from pathlib import Path

import docx
import yaml
from docx.opc.exceptions import PackageNotFoundError
from pypdf import PdfReader
from pypdf.errors import PyPdfError

from offers.letters import LettersError

# Layout of the profile folder (LettersConfig.profile_dir).
CV_DIR = "cv"
EXAMPLES_DIR = "exemples"
INSTRUCTIONS_FILE = "consignes.md"
CONTACT_FILE = "coordonnees.yaml"
# Keys of coordonnees.yaml; the required ones go in the header and signature.
CONTACT_REQUIRED = ("name", "email", "city")
CONTACT_OPTIONAL = ("address", "phone")
TEXT_SUFFIXES = {".md", ".txt"}
# System files and Word lock files, never shown as ignored.
HIDDEN_PREFIXES = (".", "~$")


@dataclass(frozen=True)
class Document:
    """Text read from a file of the profile."""

    name: str
    text: str


@dataclass(frozen=True)
class Contact:
    """Contact details, for the header and the signature of the letter."""

    name: str
    email: str
    city: str
    address: str = ""
    phone: str = ""


@dataclass(frozen=True)
class LetterInputs:
    """Everything a letter is written from, read from the profile folder."""

    cvs: list[Document]
    # Old letters, for the style.
    examples: list[Document]
    # Empty when consignes.md does not exist.
    instructions: str
    contact: Contact
    # Files of cv/ and exemples/ in a format that cannot be read.
    ignored: list[Path]


def load_inputs(letters_config):
    """Read the profile folder; raise LettersError if something is missing."""
    profile_dir = Path(letters_config.profile_dir)
    if not profile_dir.is_dir():
        raise LettersError(
            f"Dossier du profil introuvable : {profile_dir}. Crée-le avec dedans {CV_DIR}/, "
            f"{EXAMPLES_DIR}/ et {CONTACT_FILE} (voir « letters » dans config.yaml)."
        )
    cvs, ignored_cvs = read_folder(profile_dir / CV_DIR)
    if not cvs:
        raise LettersError(
            f"Aucun CV lisible dans {profile_dir / CV_DIR}. "
            "Ajoute ton CV en .pdf, .docx, .md ou .txt."
        )
    examples, ignored_examples = read_folder(profile_dir / EXAMPLES_DIR)
    instructions_path = profile_dir / INSTRUCTIONS_FILE
    instructions = read_text(instructions_path) if instructions_path.exists() else ""
    return LetterInputs(
        cvs=cvs,
        examples=examples,
        instructions=instructions.strip(),
        contact=load_contact(profile_dir / CONTACT_FILE),
        ignored=ignored_cvs + ignored_examples,
    )


def read_folder(folder):
    """Return (documents read, files ignored) of a folder, by file name.

    A missing folder has no documents.
    """
    if not folder.is_dir():
        return [], []
    documents, ignored = [], []
    for path in sorted(folder.iterdir()):
        if path.name.startswith(HIDDEN_PREFIXES) or not path.is_file():
            continue
        if path.suffix.lower() in READERS:
            documents.append(Document(path.name, read_text(path)))
        else:
            ignored.append(path)
    return documents, ignored


def read_text(path):
    """Return the text of a .pdf, .docx, .md or .txt file."""
    reader = READERS.get(path.suffix.lower(), read_plain_text)
    try:
        text = reader(path)
    except (
        OSError,
        UnicodeDecodeError,
        PyPdfError,
        PackageNotFoundError,
        zipfile.BadZipFile,
    ) as err:
        raise LettersError(
            f"Impossible de lire {path} : {err}. Vérifie que le fichier s'ouvre, "
            "ou enregistre-le dans un autre format (.pdf, .docx, .md, .txt)."
        ) from err
    if not text.strip():
        raise LettersError(
            f"Aucun texte trouvé dans {path} (PDF scanné ?). "
            "Enregistre-le en .docx ou .txt, ou retire-le du dossier."
        )
    return text


def read_pdf(path):
    """Return the text of the pages of a PDF file."""
    return "\n".join(page.extract_text() or "" for page in PdfReader(path).pages)


def read_docx(path):
    """Return the text of the paragraphs of a Word file."""
    return "\n".join(paragraph.text for paragraph in docx.Document(str(path)).paragraphs)


def read_plain_text(path):
    """Return the text of a .md or .txt file."""
    return path.read_text(encoding="utf-8")


READERS = {".pdf": read_pdf, ".docx": read_docx} | {
    suffix: read_plain_text for suffix in TEXT_SUFFIXES
}


def load_contact(path):
    """Return the contact details of coordonnees.yaml."""
    example = ", ".join(f"{key}: ..." for key in CONTACT_REQUIRED + CONTACT_OPTIONAL)
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as err:
        raise LettersError(f"Coordonnées introuvables : crée {path} avec {example}.") from err
    except (OSError, UnicodeDecodeError, yaml.YAMLError) as err:
        raise LettersError(f"Impossible de lire {path} : {err}.") from err
    if not isinstance(data, dict):
        raise LettersError(f"{path} doit contenir {example}.")
    values = {}
    for key in CONTACT_REQUIRED + CONTACT_OPTIONAL:
        value = data.get(key) or ""
        if not isinstance(value, str):
            raise LettersError(
                f"{path} : « {key} » doit être du texte "
                "(entre guillemets s'il n'a que des chiffres)."
            )
        if key in CONTACT_REQUIRED and not value.strip():
            raise LettersError(f"{path} : « {key} » est absent ou vide ({example}).")
        values[key] = value.strip()
    return Contact(**values)
