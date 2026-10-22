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
    return ["--config", str(config), "--excel", str(tmp_path / "out" / "offres.xlsx")]


def test_collect_success(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    assert cli.main(["collect", *paths]) == 0
    output = capsys.readouterr().out
    assert "1 offres en ligne, 1 nouvelles ajoutées (1 pertinentes), 0 passées" in output
    assert "Fichier : " in output
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
    assert "Source « broken » en erreur : site en panne" in output
    assert "Aucune offre n'est passée « plus en ligne »" in output


def test_command_is_required(capsys):
    with pytest.raises(SystemExit):
        cli.main([])
