"""Tests of the command line (python -m offers)."""

import pytest

from offers import __main__ as cli
from offers import sources as registry
from offers.errors import OffersError
from tests.factories import FakeSource, make_offer

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

    assert cli.main(["ui", "--db", str(db), "--config", str(config)]) == 0
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
