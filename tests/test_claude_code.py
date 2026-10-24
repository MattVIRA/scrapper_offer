"""Tests of the call to Claude Code, with a fake command runner: never the real claude."""

import json
import logging
import subprocess

import pytest

from offers.claude_code import ClaudeError, ask_json
from offers.letters.prompt import LETTER_SCHEMA

LETTER = {
    "subject": "Candidature",
    "salutation": "Madame, Monsieur,",
    "paragraphs": ["Un.", "Deux."],
    "closing": "Bien à vous.",
    "signature": "Camille Martin",
}


class FakeRun:
    """Stand-in for subprocess.run: records the call, returns a prepared result."""

    def __init__(self, stdout="", returncode=0, stderr="", error=None):
        self.result = subprocess.CompletedProcess([], returncode, stdout, stderr)
        self.error = error
        self.calls = []

    def __call__(self, command, **options):
        self.calls.append((command, options))
        if self.error:
            raise self.error
        return self.result


def envelope(**fields):
    """Return the stdout of claude -p --output-format json."""
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, **fields})


def ask(run, **options):
    return ask_json("Écris la lettre.", LETTER_SCHEMA, run=run, **options)


def test_structured_answer():
    run = FakeRun(envelope(result="", structured_output=LETTER))

    assert ask(run) == LETTER

    ((command, options),) = run.calls
    assert command[:2] == ["claude", "-p"]
    assert command[command.index("--output-format") + 1] == "json"
    # No tool at all.
    assert command[command.index("--tools") + 1] == ""
    assert json.loads(command[command.index("--json-schema") + 1]) == LETTER_SCHEMA
    assert "--model" not in command
    assert options["input"] == "Écris la lettre."
    assert options["text"] and options["capture_output"]
    assert options["timeout"] == 300


def test_model_and_timeout():
    run = FakeRun(envelope(structured_output=LETTER))
    ask(run, model="sonnet", timeout=10)
    command, options = run.calls[0]
    assert command[-2:] == ["--model", "sonnet"]
    assert options["timeout"] == 10


@pytest.mark.parametrize("result", [json.dumps(LETTER), "```json\n" + json.dumps(LETTER) + "\n```"])
def test_answer_in_the_result_text(result):
    assert ask(FakeRun(envelope(result=result))) == LETTER


def test_answer_that_is_not_json(caplog):
    run = FakeRun(envelope(result="Voici votre lettre : Madame, ..."))
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ClaudeError, match="pas répondu en JSON.*Relance"):
            ask(run)
    assert "Voici votre lettre" in caplog.text


def test_answer_that_is_not_an_object():
    with pytest.raises(ClaudeError, match="pas répondu par un objet JSON"):
        ask(FakeRun(envelope(result="[1, 2]")))


def test_envelope_that_is_not_json():
    with pytest.raises(ClaudeError, match="illisible"):
        ask(FakeRun("plantage"))


@pytest.mark.parametrize(
    "answer, message",
    [
        ({**LETTER, "closing": None}, "« closing » doit être du texte"),
        ({key: LETTER[key] for key in ("subject", "salutation", "closing")}, "« paragraphs »"),
        ({**LETTER, "paragraphs": "Un seul"}, "« paragraphs » doit être une liste"),
        ({**LETTER, "paragraphs": ["Un", 2]}, "« paragraphs n°2 » doit être du texte"),
    ],
)
def test_incomplete_answer(answer, message, caplog):
    with caplog.at_level(logging.WARNING):
        with pytest.raises(ClaudeError, match=f"Réponse de Claude incomplète : .*{message}"):
            ask(FakeRun(envelope(structured_output=answer)))
    assert "Réponse de Claude refusée" in caplog.text


def test_numbers_and_booleans_are_checked():
    schema = {
        "type": "object",
        "properties": {"score": {"type": "integer"}, "ok": {"type": "boolean"}},
        "required": ["score"],
    }
    assert ask_json("p", schema, run=FakeRun(envelope(structured_output={"score": 3}))) == {
        "score": 3
    }
    with pytest.raises(ClaudeError, match="« score » doit être un nombre entier"):
        ask_json("p", schema, run=FakeRun(envelope(structured_output={"score": True})))


def test_claude_is_not_installed():
    run = FakeRun(error=FileNotFoundError("claude"))
    with pytest.raises(ClaudeError, match="introuvable.*Installe") as error:
        ask(run)
    assert isinstance(error.value.__cause__, FileNotFoundError)


def test_timeout():
    run = FakeRun(error=subprocess.TimeoutExpired(["claude"], 10))
    with pytest.raises(ClaudeError, match="pas répondu en 10 secondes"):
        ask(run, timeout=10)


@pytest.mark.parametrize(
    "run, message",
    [
        (
            FakeRun(envelope(is_error=True, result="Not logged in · Please run /login"), 1),
            "pas connecté.*/login.*Not logged in",
        ),
        (
            FakeRun("", 1, "Invalid API key · Please run /login"),
            "pas connecté",
        ),
        (
            FakeRun(envelope(is_error=True, result="Claude AI usage limit reached|1761300000"), 1),
            "Limite d'usage du forfait.*réessaie plus tard",
        ),
        (FakeRun("", 2, "error: unknown option '--tools'"), "échoué \\(code 2\\).*unknown option"),
        (FakeRun(envelope(is_error=True, result="API Error: 500"), 0), "échoué.*API Error: 500"),
        (FakeRun("", 1, ""), "échoué \\(code 1\\) : aucun message"),
    ],
)
def test_failed_runs(run, message):
    with pytest.raises(ClaudeError, match=message):
        ask(run)
