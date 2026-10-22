"""Tests of keyword scoring (offers.scoring.keywords)."""

from offers.scoring.keywords import KeywordScorer, contains, normalize
from tests.factories import make_offer


def score(include, exclude=(), **fields):
    return KeywordScorer(include, exclude).score(make_offer(**fields))


def test_normalize_lowercases():
    assert normalize("Python SQL") == "python sql"


def test_normalize_removes_accents():
    assert normalize("Ingénieur Données À Pékin") == "ingenieur donnees a pekin"


def test_contains_finds_a_whole_word():
    assert contains("projet ia et data", "ia")


def test_contains_ignores_a_word_inside_another():
    # "ia" must not be found in "media".
    assert not contains("agence media", "ia")


def test_contains_accepts_punctuation_around():
    assert contains("(python), sql.", "python")
    assert contains("(python), sql.", "sql")


def test_contains_finds_a_compound_word():
    assert contains("experience en machine learning", "machine learning")
    assert not contains("machine de learning", "machine learning")


def test_contains_normalizes_the_keyword():
    # The text is already normalized, the keyword is not.
    assert contains("analyse de donnees", "Données")


def test_score_counts_found_words():
    result = score(
        ["python", "sql", "data", "java"],
        title="Data Analyst",
        description="Projets IA en Python.",
        candidate_profile="Bonne maîtrise de SQL.",
    )
    assert result == (3, "python, sql, data")


def test_score_counts_a_word_once():
    assert score(["python"], title="Python", description="python, python") == (1, "python")


def test_score_only_reads_text_fields():
    assert score(["python"], title="Commercial", company="Python Corp") == (0, "")


def test_score_is_zero_if_an_excluded_word_is_found():
    result = score(
        ["python", "data"],
        ["stage", "alternance"],
        title="Data Analyst stage",
        description="Python",
    )
    assert result == (0, "exclu : stage")


def test_score_lists_all_excluded_words():
    result = score([], ["stage", "alternance"], title="Stage en alternance")
    assert result == (0, "exclu : stage, alternance")


def test_score_accepts_empty_fields():
    assert score(["python"], title="", description="") == (0, "")
    assert score(["python"], ["stage"], title="") == (0, "")
