"""Ask Claude Code (claude -p, with the user's subscription) for a JSON answer.

Claude gets no tool: everything it needs is in the prompt, and it reads or
writes no file. The program checks the answer before using it.
"""

import json
import logging
import subprocess
import tempfile

from offers.errors import OffersError

CLAUDE_COMMAND = "claude"
# No tool, no MCP server, no slash command, no saved session: Claude only answers.
CLAUDE_OPTIONS = [
    "-p",
    "--output-format", "json",
    "--tools", "",
    "--strict-mcp-config",
    "--disable-slash-commands",
    "--no-session-persistence",
]  # fmt: skip
# A letter takes about a minute; beyond this, something is wrong.
TIMEOUT_SECONDS = 300
# Run outside the project, so that its CLAUDE.md is not added to the prompt.
NEUTRAL_DIR = tempfile.gettempdir()
# Characters of a refused answer written in the log.
LOGGED_ANSWER_LENGTH = 500
# Words of Claude Code's error messages, in lower case.
LOGIN_MARKERS = ("not logged in", "/login", "log in", "authenticat", "invalid api key")
LIMIT_MARKERS = ("usage limit", "rate limit", "limit reached", "limit will reset")
JSON_TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
}
TYPE_LABELS = {
    "object": "un objet",
    "array": "une liste",
    "string": "du texte",
    "integer": "un nombre entier",
    "number": "un nombre",
    "boolean": "true ou false",
}

logger = logging.getLogger(__name__)


class ClaudeError(OffersError):
    """Claude Code could not give a valid answer."""


def ask_json(prompt, schema, model=None, run=subprocess.run, timeout=TIMEOUT_SECONDS):
    """Send prompt to claude -p and return its JSON answer, checked against schema.

    schema: JSON Schema of the answer (types, properties, required, items).
    model: model name or alias given to --model; None for the default one.
    run: runs the command, as subprocess.run (replaced in the tests).
    """
    try:
        completed = run(
            claude_command(schema, model),
            input=prompt,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=NEUTRAL_DIR,
        )
    except FileNotFoundError as err:
        raise ClaudeError(
            "Claude Code est introuvable (commande « claude »). Installe-le "
            "(https://claude.com/claude-code), lance « claude » une fois pour te "
            "connecter, puis réessaie."
        ) from err
    except subprocess.TimeoutExpired as err:
        raise ClaudeError(
            f"Claude n'a pas répondu en {timeout} secondes. Réessaie plus tard."
        ) from err
    answer = read_answer(completed)
    try:
        check_schema(answer, schema)
    except ValueError as err:
        log_refused(answer)
        raise ClaudeError(f"Réponse de Claude incomplète : {err}. Relance la génération.") from err
    return answer


def claude_command(schema, model):
    """Return the claude -p command; the prompt goes on standard input."""
    command = [CLAUDE_COMMAND, *CLAUDE_OPTIONS, "--json-schema", json.dumps(schema)]
    if model:
        command += ["--model", model]
    return command


def read_answer(completed):
    """Return the JSON answer of Claude from the envelope written by claude -p."""
    try:
        envelope = json.loads(completed.stdout)
    except json.JSONDecodeError:
        envelope = None
    if completed.returncode != 0 or not isinstance(envelope, dict) or envelope.get("is_error"):
        raise failure(completed, envelope)
    # With --json-schema, the checked answer is in structured_output.
    if isinstance(envelope.get("structured_output"), dict):
        return envelope["structured_output"]
    return decode_json(envelope.get("result") or "")


def failure(completed, envelope):
    """Return the ClaudeError of a failed run, saying what to do."""
    message = " ".join(
        part.strip()
        for part in (
            str(envelope.get("result") or "") if isinstance(envelope, dict) else completed.stdout,
            completed.stderr or "",
        )
        if part and part.strip()
    )
    lowered = message.lower()
    if any(marker in lowered for marker in LOGIN_MARKERS):
        return ClaudeError(
            "Claude Code n'est pas connecté : lance « claude » dans un terminal, "
            f"connecte-toi (/login), puis réessaie. Message : {message}"
        )
    if any(marker in lowered for marker in LIMIT_MARKERS):
        return ClaudeError(
            f"Limite d'usage du forfait Claude atteinte : réessaie plus tard. Message : {message}"
        )
    if completed.returncode == 0 and envelope is None:
        log_refused(completed.stdout)
        return ClaudeError("Réponse de Claude Code illisible (pas du JSON). Relance la génération.")
    return ClaudeError(
        f"Claude Code a échoué (code {completed.returncode}) : {message or 'aucun message'}."
    )


def decode_json(text):
    """Return the JSON object of the text of an answer, maybe in a ``` block."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        answer = json.loads(cleaned)
    except json.JSONDecodeError as err:
        log_refused(text)
        raise ClaudeError(
            "Claude n'a pas répondu en JSON comme demandé. Relance la génération."
        ) from err
    if not isinstance(answer, dict):
        log_refused(text)
        raise ClaudeError("Claude n'a pas répondu par un objet JSON. Relance la génération.")
    return answer


def check_schema(value, schema, place="réponse"):
    """Raise ValueError if value does not follow schema (types, required, items)."""
    expected = schema.get("type")
    # bool is an int in Python, but not a JSON number.
    if expected and (
        not isinstance(value, JSON_TYPES[expected])
        or (isinstance(value, bool) and expected != "boolean")
    ):
        raise ValueError(f"« {place} » doit être {TYPE_LABELS[expected]}")
    if expected == "object":
        for key in schema.get("required", []):
            if key not in value:
                raise ValueError(f"le champ « {key} » manque")
        for key, sub_schema in schema.get("properties", {}).items():
            if key in value:
                check_schema(value[key], sub_schema, key)
    if expected == "array" and "items" in schema:
        for number, item in enumerate(value, 1):
            check_schema(item, schema["items"], f"{place} n°{number}")


def log_refused(answer):
    """Log the start of a refused answer, to understand what Claude sent."""
    logger.warning("Réponse de Claude refusée : %.*s", LOGGED_ANSWER_LENGTH, str(answer))
