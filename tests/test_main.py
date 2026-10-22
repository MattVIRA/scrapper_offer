"""Tests of the command line (python -m offers)."""

from datetime import date

import pytest

from offers import __main__ as cli
from offers import sources as registry
from offers.errors import OffersError
from tests.factories import FakeSource, make_offer
from tests.test_excel_import import annotations, edit, offers_of, write_excel

DAY = date(2026, 10, 20)
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
        "Excel : 1 lignes ajoutées, 0 passées « plus en ligne ».",
        f"Fichier : {tmp_path / 'out' / 'offres.xlsx'}",
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


def test_collect_shows_the_synchronized_tracking(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    cli.main(["collect", *paths])
    edit(str(tmp_path / "out" / "offres.xlsx"), {("F1", "Statut"): "Entretien"})
    capsys.readouterr()

    assert cli.main(["collect", *paths]) == 0
    output = capsys.readouterr().out
    assert "Suivi recopié depuis l'Excel : 1 offres mises à jour." in output
    assert "Statut inconnu « Entretien » (1 lignes)" in output


def test_collect_stops_if_the_excel_was_not_imported(monkeypatch, capsys, paths, tmp_path):
    monkeypatch.setitem(registry.SOURCES, "fake", WorkingSource)
    excel_path = tmp_path / "out" / "offres.xlsx"
    write_excel(str(excel_path), DAY, [make_offer(source="fake", reference="F9")])
    before = excel_path.read_bytes()

    assert cli.main(["collect", *paths]) == 1
    output = capsys.readouterr().out
    assert "est vide alors que l'Excel" in output
    assert "python -m offers import-excel" in output
    assert excel_path.read_bytes() == before
    assert not (tmp_path / "data" / "offers.db").exists()


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


def test_import_excel(capsys, tmp_path, business_france_search):
    excel_path = str(tmp_path / "offres.xlsx")
    offers = offers_of(business_france_search)
    write_excel(excel_path, DAY, offers)
    edit(excel_path, {**annotations(offers), (offers[2].reference, "Statut"): "Entretien"})
    db = tmp_path / "data" / "offers.db"

    assert cli.main(["import-excel", "--excel", excel_path, "--db", str(db)]) == 0
    output = capsys.readouterr().out
    assert "5 offres importées, 3 suivis importés" in output
    assert "Statut inconnu « Entretien » (1 lignes)" in output
    assert f"Base : {db}" in output

    # Second import: the database is saved first.
    assert cli.main(["import-excel", "--excel", excel_path, "--db", str(db)]) == 0
    assert "0 offres importées, 0 suivis importés" in capsys.readouterr().out
    assert len(list((db.parent / "backup").iterdir())) == 1


def test_import_excel_missing_file(capsys, tmp_path):
    db = tmp_path / "offers.db"
    assert (
        cli.main(["import-excel", "--excel", str(tmp_path / "absent.xlsx"), "--db", str(db)]) == 1
    )
    assert "Erreur : Fichier Excel introuvable" in capsys.readouterr().out
    assert not db.exists()


def test_export(capsys, tmp_path, business_france_search):
    excel_path = tmp_path / "offres.xlsx"
    offers = offers_of(business_france_search)
    write_excel(str(excel_path), DAY, offers[:3])
    db = tmp_path / "offers.db"
    cli.main(["import-excel", "--excel", str(excel_path), "--db", str(db)])
    capsys.readouterr()
    other = tmp_path / "autre.xlsx"

    assert cli.main(["export", "--db", str(db), "--excel", str(other)]) == 0
    assert capsys.readouterr().out == (
        f"3 offres ajoutées, 0 passées « plus en ligne ».\nFichier : {other}\n"
    )
    assert other.exists()


def test_export_without_database(capsys, tmp_path):
    db = tmp_path / "offers.db"
    assert cli.main(["export", "--db", str(db), "--excel", str(tmp_path / "x.xlsx")]) == 1
    assert "Erreur : Base introuvable" in capsys.readouterr().out
    assert not db.exists()
