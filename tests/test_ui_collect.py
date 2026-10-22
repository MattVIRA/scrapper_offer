"""Tests of the « Collecte » page, with fake sources and a test database."""

import sys
import threading

import pytest
from streamlit.testing.v1 import AppTest

from offers import sources as registry
from offers import summary
from offers.__main__ import UI_APP
from offers.config import load_config
from offers.errors import OffersError
from offers.exports.excel import ExcelReport
from offers.storage.database import connect
from offers.ui import collect_job
from tests.factories import FakeSource, make_offer
from tests.test_ui_offers import TIMEOUT, button, by_reference

COLLECT = "app_pages/collect.py"
CONFIG = """
sources:
  fake:
    searches:
      - name: "Data Europe"
        url: "https://example.com/search"
  broken:
    searches: []
keywords_include: [data]
"""
WAIT = 10


def offers():
    return [
        make_offer(source="fake", source_id=str(n), reference=f"F{n}", title=f"Data {n}")
        for n in (1, 2)
    ]


class WorkingSource(FakeSource):
    label = "Source qui marche"

    def __init__(self, config):
        super().__init__(config, found=offers(), online=offers())


class BrokenSource(FakeSource):
    label = "Source en panne"

    def __init__(self, config):
        super().__init__(config, error=OffersError("site en panne"))


class SlowSource(WorkingSource):
    """Waits for RELEASE before answering: the collection stays running."""

    release = threading.Event()

    def online_offers(self):
        assert SlowSource.release.wait(WAIT)
        return super().online_offers()


@pytest.fixture
def paths(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(CONFIG, encoding="utf-8")
    db = tmp_path / "data" / "offers.db"
    connect(db).close()
    return {"config": config, "db": db, "excel": tmp_path / "out" / "offres.xlsx"}


@pytest.fixture(autouse=True)
def fresh_runner():
    # The runner is shared by the whole app: each test starts without a job.
    collect_job.get_runner.clear()
    yield
    SlowSource.release.set()
    collect_job.get_runner.clear()


@pytest.fixture
def open_page(monkeypatch, paths):
    """Return a function that opens the Collecte page with these sources."""
    argv = ["app.py", *[arg for name, path in paths.items() for arg in (f"--{name}", str(path))]]
    monkeypatch.setattr(sys, "argv", argv)

    def open_page(fake=WorkingSource, broken=BrokenSource):
        monkeypatch.setitem(registry.SOURCES, "fake", fake)
        monkeypatch.setitem(registry.SOURCES, "broken", broken)
        at = AppTest.from_file(str(UI_APP), default_timeout=TIMEOUT).run()
        return at.switch_page(COLLECT).run()

    return open_page


def run_collection(at):
    """Click « Lancer la collecte », wait for its end, show the page again."""
    button(at, "Lancer la collecte").click().run()
    job = collect_job.get_runner().job
    assert job.finished.wait(WAIT)
    return at.run()


def texts(elements):
    return [element.value for element in elements]


# --- Page ---------------------------------------------------------------------


def test_sources_are_checked_with_their_searches(open_page):
    at = open_page()

    assert not at.exception
    assert [(c.label, c.value) for c in at.checkbox] == [
        ("Source qui marche", True),
        ("Source en panne", True),
    ]
    assert [(t.label, t.value) for t in at.toggle] == [("Data Europe", True)]
    assert "Aucune recherche dans config.yaml." in texts(at.caption)
    assert "Aucun lancement pour l'instant." in texts(at.info)


def test_no_source_checked_no_collection(open_page):
    at = open_page()
    for checkbox in at.checkbox:
        checkbox.uncheck()
    at.run()
    assert button(at, "Lancer la collecte").disabled


# --- Collection ---------------------------------------------------------------


def test_collection_updates_the_database_and_shows_the_summary(open_page, paths):
    at = open_page()
    at.checkbox[1].uncheck().run()

    run_collection(at)

    assert not at.exception
    assert set(by_reference(paths["db"])) == {"F1", "F2"}
    report = collect_job.get_runner().job.report
    # The same texts as python -m offers collect.
    expected = summary.collect_summary(report, paths["excel"])
    assert texts(at.success) == expected
    assert expected[0] == (
        "Source qui marche : 2 offres trouvées, 2 nouvelles ajoutées (2 pertinentes), "
        "0 passées « plus en ligne »."
    )
    assert paths["excel"].exists()
    runs = at.dataframe[0].value
    assert list(runs["Source"]) == ["Source qui marche"]
    assert list(runs["Ajoutées"]) == [2]


def test_error_of_one_source_is_shown(open_page, paths):
    at = run_collection(open_page())

    assert texts(at.error) == [
        "Source en panne : en erreur, ses offres ne changent pas. site en panne"
    ]
    assert texts(at.success)[0].startswith("Source qui marche : 2 offres trouvées")
    assert list(at.dataframe[0].value["Résultat"]) == ["Erreur", "OK"]


def test_no_source_read(open_page):
    at = open_page()
    at.checkbox[0].uncheck().run()

    run_collection(at)

    assert texts(at.error)[0].startswith("Aucune source n'a pu être lue")
    assert not at.success


def test_open_excel_only_skips_the_export(open_page, paths):
    paths["excel"].parent.mkdir()
    (paths["excel"].parent / "~$offres.xlsx").touch()

    at = run_collection(open_page())

    assert set(by_reference(paths["db"])) == {"F1", "F2"}
    assert texts(at.warning) == [
        summary.excel_skipped_summary("offres.xlsx est ouvert : ferme l'Excel puis relance.")
    ]
    assert not paths["excel"].exists()


def test_no_second_collection_while_one_is_running(open_page, paths):
    SlowSource.release.clear()
    at = open_page(fake=SlowSource)
    at.checkbox[1].uncheck().run()
    button(at, "Lancer la collecte").click().run()

    assert button(at, "Lancer la collecte").disabled
    assert at.checkbox[0].disabled
    assert at.status[0].label == "Collecte en cours : 0 sources lues sur 1"
    runner = collect_job.get_runner()
    assert not runner.start(None, [], paths["db"], paths["excel"], None)

    SlowSource.release.set()
    assert runner.job.finished.wait(WAIT)
    at.run()
    assert not button(at, "Lancer la collecte").disabled
    assert texts(at.success)[0].startswith("Source qui marche")


# --- Export -------------------------------------------------------------------


def test_export_button_writes_the_excel(open_page, paths):
    at = run_collection(open_page())
    paths["excel"].unlink()

    button(at, "Exporter l'Excel").click().run()

    assert paths["excel"].exists()
    assert summary.excel_summary(ExcelReport(rows=2), paths["excel"]) in texts(at.success)


def test_export_with_the_excel_open(open_page, paths):
    paths["excel"].parent.mkdir()
    (paths["excel"].parent / "~$offres.xlsx").touch()
    at = open_page()

    button(at, "Exporter l'Excel").click().run()

    assert texts(at.error) == ["offres.xlsx est ouvert : ferme l'Excel puis relance."]
    assert not paths["excel"].exists()


# --- Searches -----------------------------------------------------------------


def test_switching_a_search_off_writes_config_yaml(open_page, paths):
    at = open_page()

    at.toggle(key="collect_search_fake_Data Europe").set_value(False).run()

    assert not at.exception and not at.error
    text = paths["config"].read_text(encoding="utf-8")
    assert "enabled: false" in text
    (fake, _) = load_config(str(paths["config"]), {"fake", "broken"}).sources
    assert fake.active_searches() == []
    # The old file is saved next to the database backups.
    (backup,) = (paths["db"].parent / "backup").glob("config_*.yaml")
    assert backup.read_text(encoding="utf-8") == CONFIG


def test_failed_switch_is_explained_and_undone(open_page, paths):
    # A file where the backup folder should be: the backup fails.
    (paths["db"].parent / "backup").write_text("pas un dossier")
    at = open_page()

    at.toggle(key="collect_search_fake_Data Europe").set_value(False).run()

    assert at.error[0].value.startswith("Recherche non modifiée. Impossible de sauvegarder")
    assert at.toggle[0].value is True
    assert paths["config"].read_text(encoding="utf-8") == CONFIG


def test_toggles_are_off_while_collecting(open_page):
    SlowSource.release.clear()
    at = open_page(fake=SlowSource)
    button(at, "Lancer la collecte").click().run()
    assert at.toggle[0].disabled
    SlowSource.release.set()
    assert collect_job.get_runner().job.finished.wait(WAIT)
