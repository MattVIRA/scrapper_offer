"""Generate the letters of the offers « À rédiger »: prompt, Claude, .docx, database."""

from dataclasses import dataclass
from pathlib import Path

from offers.claude_code import ask_json
from offers.errors import OffersError
from offers.letters.document import letter_path, write_letter
from offers.letters.inputs import load_inputs
from offers.letters.prompt import LETTER_SCHEMA, build_prompt, load_prompt, prompt_version
from offers.storage.database import StoredOffer, offers_to_write, record_letter


@dataclass(frozen=True)
class LetterResult:
    """What happened to the letter of one offer."""

    stored: StoredOffer
    path: Path
    # Message of the error that stopped this letter.
    error: str | None = None
    # A file was already there and was not replaced.
    skipped: bool = False

    @property
    def written(self):
        return self.error is None and not self.skipped


@dataclass(frozen=True)
class LettersReport:
    """Outcome of a generation, one LetterResult per offer, in order."""

    results: list[LetterResult]

    @property
    def written(self):
        return [result for result in self.results if result.written]

    @property
    def failed(self):
        return [result for result in self.results if result.error]

    @property
    def skipped(self):
        return [result for result in self.results if result.skipped]


def letters_to_write(conn, letters_config):
    """Return [(StoredOffer, path of its letter)] of the offers « À rédiger »."""
    return [
        (stored, letter_path(letters_config.output_dir, stored.offer))
        for stored in offers_to_write(conn)
    ]


def run_letters(
    conn, letters_config, offer_ids, now, replace=False, ask=ask_json, on_letter_done=None
):
    """Write the letter of each offer of offer_ids that is still « À rédiger ».

    An offer in error does not stop the others. The inputs and the prompt
    are read once, before the first call: a missing one stops everything
    (LettersError). ask: sends a prompt to Claude, as claude_code.ask_json.
    on_letter_done: called with the LetterResult of each offer.
    """
    inputs = load_inputs(letters_config)
    template = load_prompt(letters_config.prompt)
    version = prompt_version(template)

    def ask_letter(offer):
        prompt = build_prompt(template, inputs, offer)
        return ask(prompt, LETTER_SCHEMA, model=letters_config.model)

    wanted = set(offer_ids)
    results = []
    for stored, path in letters_to_write(conn, letters_config):
        if stored.id not in wanted:
            continue
        if path.exists() and not replace:
            result = LetterResult(stored, path, skipped=True)
        else:
            result = write_one(
                conn, stored, path, ask_letter, inputs.contact, version, now, replace
            )
        results.append(result)
        if on_letter_done:
            on_letter_done(result)
    return LettersReport(results)


def write_one(conn, stored, path, ask_letter, contact, version, now, replace):
    """Write the letter of one offer and record it; return its LetterResult.

    ask_letter: returns the answer of Claude for an Offer.
    """
    try:
        answer = ask_letter(stored.offer)
        write_letter(path, answer, contact, stored.offer, now.date(), replace=replace)
    except OffersError as err:
        return LetterResult(stored, path, error=str(err))
    try:
        record_letter(conn, stored.id, path, version, now)
    except OffersError as err:
        # Nothing half done: a letter missing from the database is removed.
        path.unlink(missing_ok=True)
        return LetterResult(stored, path, error=str(err))
    return LetterResult(stored, path)
