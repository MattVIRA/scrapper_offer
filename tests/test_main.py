"""Tests of the command line (python -m offers)."""

from datetime import datetime
from functools import partial

import pytest

from offers import __main__ as cli
from offers import sources as registry
from offers.errors import OffersError
from offers.letters import generate
from offers.storage.database import connect, set_letter_status
from tests.factories import FakeSource, make_offer
from tests.letter_files import make_profile
from tests.test_storage_offers import offer, save

CONFIG = """
sources:
  fake:
    enabled: true
keywords_include: [data]
"""


class WorkingSource(FakeSource):
    def __init__(self, config):
        offers = [make_offer(source="fake", source_id="1", reference="F1")]
        super().__init__(config, found=offers, online=offers)


class BrokenSource(FakeSource):
    def __init__(self, config):
        super().__init__(config, error=OffersError("site en panne"))


@pytest.fixture
def paths(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    return [
        "--config",
        str(config),
        "--excel",
        str(tmp_path / "out" / "offres.xlsx"),
        "--db",
        str(tmp_path / "data" / "offers.db"),
    ]


def test_collect_success(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    assert cli.main(["collect", *paths]) == 0
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "Fausse source : 1 offres trouvées, 1 nouvelles ajoutées (1 pertinentes), "
        "0 passées « plus en ligne ».",
        f"Excel régénéré : 1 offres (hors corbeille). Fichier : {tmp_path / 'out' / 'offres.xlsx'}",
    ]
    assert (tmp_path / "out" / "offres.xlsx").exists()


def test_collect_error(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", BrokenSource)
    assert cli.main(["collect", *paths]) == 1
    output = capsys.readouterr().out
    assert output.startswith("Erreur : Aucune source n'a pu être lue")
    assert "site en panne" in output
    assert not (tmp_path / "out" / "offres.xlsx").exists()


def test_collect_config_error(capsys, tmp_path):
    assert cli.main(["collect", "--config", str(tmp_path / "absent.yaml")]) == 1
    assert "Erreur : Fichier de réglages introuvable" in capsys.readouterr().out


def test_collect_partial_error_is_shown(monkeypatch, capsys, paths, tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(
        "sources:\n  fake: {}\n  broken: {}\nkeywords_include: [data]\n", encoding="utf-8"
    )
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    monkeypatch.setitem(registry.SOURCES, "broken", BrokenSource)

    assert cli.main(["collect", *paths]) == 0
    output = capsys.readouterr().out
    assert "Fausse source : en erreur, ses offres ne changent pas. site en panne" in output
    assert "Fausse source : 1 offres trouvées" in output


class DuplicatingSource(FakeSource):
    def __init__(self, config):
        offers = [make_offer(source="fake", source_id=n, reference=f"F{n}") for n in "12"]
        super().__init__(config, found=offers, online=offers)


def test_collect_shows_the_duplicates(monkeypatch, capsys, paths):
    monkeypatch.setitem(registry.SOURCES, "fake", DuplicatingSource)
    assert cli.main(["collect", *paths]) == 0
    output = capsys.readouterr().out
    assert output.endswith("1 doublons probables : python -m offers duplicates pour les voir.\n")


def test_collect_with_the_excel_open(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    (tmp_path / "out").mkdir()
    (tmp_path / "out" / "~$offres.xlsx").touch()

    assert cli.main(["collect", *paths]) == 0
    output = capsys.readouterr().out.splitlines()
    assert output[0].startswith("Fausse source : 1 offres trouvées")
    assert output[1] == (
        "Export Excel non fait, la collecte est enregistrée. offres.xlsx est ouvert : "
        "ferme l'Excel puis relance. Ensuite : bouton « Exporter l'Excel » ou "
        "python -m offers export."
    )
    assert not (tmp_path / "out" / "offres.xlsx").exists()


def test_command_is_required(capsys):
    with pytest.raises(SystemExit):
        cli.main([])


def test_export(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    cli.main(["collect", *paths])
    capsys.readouterr()
    other = tmp_path / "autre.xlsx"

    db = tmp_path / "data" / "offers.db"
    assert cli.main(["export", "--db", str(db), "--excel", str(other)]) == 0
    assert capsys.readouterr().out == (
        f"Excel régénéré : 1 offres (hors corbeille). Fichier : {other}\n"
    )
    assert other.exists()


def test_import_excel_no_longer_exists(capsys):
    with pytest.raises(SystemExit):
        cli.main(["import-excel"])


class FakeRun:
    """Stands for subprocess.run: keeps the command instead of running it."""

    def __init__(self, error=None):
        self.commands = []
        self.error = error

    def __call__(self, command, check):
        self.commands.append(command)
        if self.error:
            raise self.error


def test_ui_runs_streamlit_on_localhost(monkeypatch, capsys, tmp_path):
    db = tmp_path / "offers.db"
    db.touch()
    config = tmp_path / "config.yaml"
    run = FakeRun()
    monkeypatch.setattr(cli.subprocess, "run", run)

    excel = tmp_path / "offres.xlsx"
    assert cli.main(["ui", "--db", str(db), "--config", str(config), "--excel", str(excel)]) == 0
    assert run.commands == [
        [
            cli.sys.executable,
            "-m",
            "streamlit",
            "run",
            str(cli.UI_APP),
            "--server.address=localhost",
            "--browser.gatherUsageStats=false",
            "--",
            "--db",
            str(db),
            "--config",
            str(config),
            "--excel",
            str(excel),
        ]
    ]
    assert cli.UI_APP.exists()
    assert "Ctrl+C pour l'arrêter" in capsys.readouterr().out
    # The database is saved before the interface can change it.
    assert len(list((tmp_path / "backup").iterdir())) == 1


def test_ui_stops_quietly_on_ctrl_c(monkeypatch, capsys, tmp_path):
    db = tmp_path / "offers.db"
    db.touch()
    monkeypatch.setattr(cli.subprocess, "run", FakeRun(KeyboardInterrupt()))

    assert cli.main(["ui", "--db", str(db)]) == 0
    assert capsys.readouterr().out.endswith("Interface arrêtée.\n")


def test_ui_without_database(monkeypatch, capsys, tmp_path):
    run = FakeRun()
    monkeypatch.setattr(cli.subprocess, "run", run)
    db = tmp_path / "offers.db"

    assert cli.main(["ui", "--db", str(db)]) == 1
    output = capsys.readouterr().out
    assert "Erreur : Base introuvable" in output
    assert "python -m offers collect" in output
    assert run.commands == []
    assert not db.exists()


def test_export_without_database(capsys, tmp_path):
    db = tmp_path / "offers.db"
    assert cli.main(["export", "--db", str(db), "--excel", str(tmp_path / "x.xlsx")]) == 1
    assert "Erreur : Base introuvable" in capsys.readouterr().out
    assert not db.exists()


# --- letters ------------------------------------------------------------------


@pytest.fixture
def letters_setup(tmp_path, paths, monkeypatch):
    """Profile, prompt and a database with two offers « À rédiger »."""
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    make_profile(tmp_path)
    (tmp_path / "prompts").mkdir()
    (tmp_path / "prompts" / "lettre.md").write_text("Écris une lettre.", encoding="utf-8")
    conn = connect(tmp_path / "data" / "offers.db")
    save(conn, [offer(1, company="ACME"), offer(2, company="Foo")])
    set_letter_status(conn, [1, 2], "to_write", datetime(2026, 10, 23, 9, 0))
    conn.close()
    return paths


def fake_claude(prompt, schema, model=None):
    return {
        "subject": "S",
        "salutation": "Madame,",
        "paragraphs": ["P"],
        "closing": "C",
        "signature": "N",
    }


@pytest.fixture
def with_fake_claude(monkeypatch):
    monkeypatch.setattr(cli, "run_letters", partial(generate.run_letters, ask=fake_claude))


def letters_in_db(tmp_path):
    conn = connect(tmp_path / "data" / "offers.db")
    return conn.execute("SELECT COUNT(*) FROM letters").fetchone()[0]


def test_letters_refused_confirmation_writes_nothing(
    monkeypatch, capsys, letters_setup, tmp_path, with_fake_claude
):
    monkeypatch.setattr("builtins.input", lambda question: "n")

    assert cli.main(["letters", *letters_setup[:2], *letters_setup[4:]]) == 0

    output = capsys.readouterr().out
    assert "2 offres « À rédiger » :\n  Data 1 — ACME\n  Data 2 — Foo\n" in output
    assert output.endswith("Annulé : aucune lettre écrite.\n")
    assert not (tmp_path / "lettres").exists()
    assert letters_in_db(tmp_path) == 0
    assert not (tmp_path / "data" / "backup").exists()


def test_letters_confirmed(monkeypatch, capsys, letters_setup, tmp_path, with_fake_claude):
    questions = []
    monkeypatch.setattr("builtins.input", lambda question: questions.append(question) or "o")

    assert cli.main(["letters", *letters_setup[:2], *letters_setup[4:]]) == 0

    assert "forfait Claude" in questions[0]
    output = capsys.readouterr().out.splitlines()
    assert output[-3:] == [
        "Data 1 (ACME) : lettre écrite (lettre_ACME.docx).",
        "Data 2 (Foo) : lettre écrite (lettre_Foo.docx).",
        "2 lettres écrites, 0 en erreur, 0 déjà présentes.",
    ]
    assert letters_in_db(tmp_path) == 2
    assert len(list((tmp_path / "data" / "backup").iterdir())) == 1

    # Nothing left to do on a second run.
    assert cli.main(["letters", "--yes", *letters_setup[:2], *letters_setup[4:]]) == 0
    assert capsys.readouterr().out == "Aucune offre « À rédiger » : rien à faire.\n"


def test_letters_yes_and_replace(capsys, letters_setup, tmp_path, with_fake_claude):
    options = [*letters_setup[:2], *letters_setup[4:]]
    assert cli.main(["letters", "--yes", *options]) == 0
    conn = connect(tmp_path / "data" / "offers.db")
    set_letter_status(conn, [1], "to_write", datetime(2026, 10, 24, 9, 0))
    conn.close()
    capsys.readouterr()

    assert cli.main(["letters", "--yes", *options]) == 0
    output = capsys.readouterr().out
    assert "Data 1 — ACME (lettre déjà présente)" in output
    assert "0 lettres écrites, 0 en erreur, 1 déjà présentes." in output

    assert cli.main(["letters", "--yes", "--replace", *options]) == 0
    assert "Data 1 (ACME) : lettre écrite (lettre_ACME.docx)." in capsys.readouterr().out
    assert letters_in_db(tmp_path) == 2
    assert len(list((tmp_path / "lettres" / "backup").iterdir())) == 1


def test_letters_never_overwrite_a_file_of_the_user(
    capsys, letters_setup, tmp_path, with_fake_claude
):
    (tmp_path / "lettres").mkdir()
    (tmp_path / "lettres" / "lettre_ACME.docx").write_bytes(b"lettre de l'utilisateur")

    assert cli.main(["letters", "--yes", *letters_setup[:2], *letters_setup[4:]]) == 0

    assert "Data 1 (ACME) : lettre écrite (lettre_ACME_2.docx)." in capsys.readouterr().out
    assert (tmp_path / "lettres" / "lettre_ACME.docx").read_bytes() == b"lettre de l'utilisateur"


def test_letters_missing_input(capsys, letters_setup, tmp_path, with_fake_claude):
    (tmp_path / "profil" / "cv" / "cv.pdf").unlink()
    assert cli.main(["letters", "--yes", *letters_setup[:2], *letters_setup[4:]]) == 1
    assert "Erreur : Aucun CV lisible" in capsys.readouterr().out
