"""Page « Collecte »: run a collection, see its summary, export the Excel file."""

from datetime import date, datetime

import pandas as pd
import streamlit as st

from offers.config import ConfigError, load_config, set_search_enabled
from offers.exports.excel import ExcelError
from offers.pipeline import export_workbook
from offers.sources import SOURCES, source_label
from offers.storage.database import last_runs
from offers.summary import (
    duplicates_summary,
    excel_skipped_summary,
    excel_summary,
    source_summary,
)
from offers.ui.collect_job import get_runner
from offers.ui.session import open_database

RUNS_SHOWN = 20
# How often the page looks at a running collection.
PROGRESS_REFRESH = "2s"
RUN_RESULTS = {"ok": "OK", "error": "Erreur"}
# config.yaml is saved next to the database backups.
BACKUP_DIR = "backup"
CONFIG_ERROR_KEY = "collect_config_error"


def start_collection(runner, config, chosen):
    runner.start(
        config,
        chosen,
        st.session_state.db_path,
        st.session_state.excel_path,
        datetime.now(),
    )


def search_key(source_name, search_name):
    return f"collect_search_{source_name}_{search_name}"


def switch_search(source_name, search_name):
    """Callback of a search toggle: write it at once into config.yaml."""
    key = search_key(source_name, search_name)
    enabled = st.session_state[key]
    try:
        set_search_enabled(
            st.session_state.config_path,
            source_name,
            search_name,
            enabled,
            st.session_state.db_path.parent / BACKUP_DIR,
            datetime.now(),
        )
    except ConfigError as err:
        # The toggle goes back to what the file says, and the page explains why.
        st.session_state[key] = not enabled
        st.session_state[CONFIG_ERROR_KEY] = str(err)


def show_search_toggles(source, disabled):
    """One toggle per search of a source, written at once into config.yaml."""
    if not source.searches:
        st.caption("Aucune recherche dans config.yaml.")
    for search in source.searches:
        key = search_key(source.name, search.name)
        st.session_state.setdefault(key, search.enabled)
        st.toggle(
            search.name,
            key=key,
            disabled=disabled,
            on_change=switch_search,
            args=(source.name, search.name),
        )


@st.fragment(run_every=PROGRESS_REFRESH)
def show_progress(job):
    """Progress of the running collection; the whole page reruns at the end."""
    if not job.running:
        st.rerun()
    label = f"Collecte en cours : {len(job.done)} sources lues sur {len(job.source_names)}"
    with st.status(label, expanded=True):
        for report in job.done:
            st.text(source_summary(report))


def show_result(job):
    """Summary of the last collection, with the texts of the command line."""
    st.subheader("Dernière collecte")
    st.caption(f"Lancée le {job.started_at:%d/%m/%Y à %H:%M}")
    if job.error:
        st.error(job.error, icon=":material/error:")
        return
    report = job.report
    for source in report.sources:
        if source.error:
            st.error(source_summary(source), icon=":material/error:")
        else:
            st.success(source_summary(source), icon=":material/check_circle:")
    if report.excel is None:
        st.warning(excel_skipped_summary(report.excel_error), icon=":material/warning:")
    else:
        st.success(excel_summary(report.excel, st.session_state.excel_path))
    if report.duplicates:
        st.info(duplicates_summary(report.duplicates), icon=":material/content_copy:")


def runs_frame(runs):
    """Return the table of the last runs (database.Run), most recent first."""
    return pd.DataFrame(
        [
            {
                "Début": run.started_at,
                "Source": source_label(run.source),
                "Résultat": RUN_RESULTS.get(run.status, run.status),
                "Trouvées": run.found,
                "Ajoutées": run.added,
                "Hors ligne": run.removed,
                "Durée (s)": round((run.finished_at - run.started_at).total_seconds()),
                "Erreur": run.error,
            }
            for run in runs
        ]
    )


st.title("Collecte")
runner = get_runner()
job = runner.job
if job is not None and job.failure is not None:
    failure, job.failure = job.failure, None
    raise failure
running = job is not None and job.running
config = load_config(str(st.session_state.config_path), set(SOURCES))

st.subheader("Sources")
st.caption("Les recherches coupées ne sont plus interrogées ; elles restent dans config.yaml.")
config_error = st.session_state.pop(CONFIG_ERROR_KEY, None)
if config_error:
    st.error(f"Recherche non modifiée. {config_error}", icon=":material/error:")
chosen = []
for source in config.enabled_sources():
    if st.checkbox(
        source_label(source.name), value=True, key=f"collect_{source.name}", disabled=running
    ):
        chosen.append(source)
    show_search_toggles(source, disabled=running)
if not config.enabled_sources():
    st.info("Aucune source activée dans config.yaml.", icon=":material/info:")
st.button(
    "Lancer la collecte",
    type="primary",
    icon=":material/play_arrow:",
    disabled=running or not chosen,
    key="collect_start",
    on_click=start_collection,
    args=(runner, config, chosen),
)

if running:
    show_progress(job)
elif job is not None:
    show_result(job)

st.subheader("Excel")
st.caption(f"Fichier : {st.session_state.excel_path}")
if st.button("Exporter l'Excel", icon=":material/table_view:", key="collect_export"):
    # The error is shown next to the button: the rest of the page stays usable.
    try:
        with open_database(st.session_state.db_path) as conn:
            excel = export_workbook(conn, st.session_state.excel_path, date.today())
        st.success(excel_summary(excel, st.session_state.excel_path))
    except ExcelError as err:
        st.error(str(err), icon=":material/error:")

st.subheader("Derniers lancements")
with open_database(st.session_state.db_path) as conn:
    runs = last_runs(conn, RUNS_SHOWN)
if runs:
    st.dataframe(
        runs_frame(runs),
        hide_index=True,
        column_config={"Début": st.column_config.DatetimeColumn(format="DD/MM/YYYY HH:mm")},
        alt="Derniers lancements de la collecte, par source",
    )
else:
    st.info("Aucun lancement pour l'instant.", icon=":material/info:")
