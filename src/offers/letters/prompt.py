"""Prompt of the cover letter: its file, its version and the text sent to Claude."""

import hashlib
import json
from html import escape
from pathlib import Path

from offers.backups import copy_to_backup, write_text_atomically
from offers.letters import LettersError

# A new version at each change of the prompt, with no number to keep up to date.
VERSION_LENGTH = 8
BACKUP_PREFIX = "prompt_"
# JSON answer expected from Claude, checked before the letter is written.
LETTER_SCHEMA = {
    "type": "object",
    "properties": {
        "subject": {"type": "string"},
        "salutation": {"type": "string"},
        "paragraphs": {"type": "array", "items": {"type": "string"}},
        "closing": {"type": "string"},
        "signature": {"type": "string"},
    },
    "required": ["subject", "salutation", "paragraphs", "closing", "signature"],
}
ANSWER_FORMAT = (
    "Réponds uniquement par un objet JSON qui suit ce schéma, sans texte autour :\n"
    + json.dumps(LETTER_SCHEMA, indent=2)
)


def load_prompt(path):
    """Return the text of the prompt file."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError as err:
        raise LettersError(
            f"Prompt des lettres introuvable : {path}. Vérifie « letters.prompt » "
            "dans config.yaml, ou remets le fichier depuis git."
        ) from err
    except (OSError, UnicodeDecodeError) as err:
        raise LettersError(f"Impossible de lire le prompt des lettres {path} : {err}.") from err


def prompt_version(text):
    """Return a short fingerprint of the prompt: the start of its SHA-256."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:VERSION_LENGTH]


def build_prompt(template, inputs, offer):
    """Return the text sent to Claude for the letter of an offer.

    template: text of the prompt file; inputs: LetterInputs; offer: Offer.
    Each part is in its own tag, so that Claude tells them apart.
    """
    parts = [template.strip()]
    if inputs.instructions:
        parts.append(tagged("consignes", inputs.instructions))
    parts += [tagged("ancienne_lettre", e.text, fichier=e.name) for e in inputs.examples]
    parts += [tagged("cv", cv.text, fichier=cv.name) for cv in inputs.cvs]
    parts.append(tagged("offre", offer_text(offer)))
    parts.append(ANSWER_FORMAT)
    return "\n\n".join(parts) + "\n"


def tagged(name, text, **attributes):
    """Return text between <name ...> and </name>."""
    opening = " ".join([name, *(f'{key}="{escape(value)}"' for key, value in attributes.items())])
    return f"<{opening}>\n{text.strip()}\n</{name}>"


def offer_text(offer):
    """Return what Claude needs to know about an offer."""
    place = ", ".join(part for part in (offer.city, offer.country) if part)
    duration = f"{offer.duration_months} mois" if offer.duration_months else ""
    contract = " de ".join(part for part in (offer.contract_type, duration) if part)
    lines = [
        f"Titre : {offer.title}",
        f"Entreprise : {offer.company or 'non précisée'}",
        f"Lieu : {place or 'non précisé'}",
        f"Contrat : {contract or 'non précisé'}",
        "",
        "Description du poste :",
        offer.description.strip() or "non précisée",
        "",
        "Profil recherché :",
        offer.candidate_profile.strip() or "non précisé",
    ]
    return "\n".join(lines)


def save_prompt(path, text, backup_dir, now):
    """Replace the prompt file, after a copy of the old one into backup_dir.

    Nothing is written if the copy fails; the file is replaced atomically.
    """
    path = Path(path)
    try:
        if path.exists():
            copy_to_backup(path, Path(backup_dir), BACKUP_PREFIX, now)
        path.parent.mkdir(parents=True, exist_ok=True)
        write_text_atomically(path, text)
    except OSError as err:
        raise LettersError(
            f"Impossible d'enregistrer le prompt {path} : {err}. Il n'a pas changé."
        ) from err
