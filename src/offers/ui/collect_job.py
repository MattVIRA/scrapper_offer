"""Collection run in a background thread, so that the interface stays usable.

A Streamlit script stops as soon as the user clicks elsewhere or changes
page: a collection run inside it could be cut in the middle. The thread
does not use Streamlit; the Collecte page only reads its progress.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime

import streamlit as st

from offers.errors import OffersError
from offers.pipeline import CollectReport, SourceReport, run_collect
from offers.sources import create_source


@dataclass
class CollectionJob:
    """One collection: its progress, then its report or its error."""

    source_names: list[str]
    started_at: datetime
    # SourceReport of each source already read, in order.
    done: list[SourceReport] = field(default_factory=list)
    report: CollectReport | None = None
    # Message of a project error (no source could be read, for example).
    error: str | None = None
    # Unexpected error, raised again by the page so that its trace is seen.
    failure: BaseException | None = None
    finished: threading.Event = field(default_factory=threading.Event)

    @property
    def running(self):
        return not self.finished.is_set()


class CollectionRunner:
    """Runs one collection at a time for the whole app, and keeps the last one."""

    def __init__(self):
        self.lock = threading.Lock()
        self.job = None

    def start(self, config, source_configs, db_path, excel_path, now):
        """Start a collection of these sources; return False if one is running."""
        with self.lock:
            if self.job is not None and self.job.running:
                return False
            job = CollectionJob([source.name for source in source_configs], now)
            self.job = job
        thread = threading.Thread(
            target=run_job,
            args=(job, config, source_configs, db_path, excel_path),
            daemon=True,
        )
        thread.start()
        return True


def run_job(job, config, source_configs, db_path, excel_path):
    """Body of the thread: run the collection and keep its outcome in the job."""
    try:
        sources = [create_source(source) for source in source_configs]
        job.report = run_collect(
            config,
            str(db_path),
            str(excel_path),
            job.started_at,
            sources=sources,
            on_source_done=job.done.append,
        )
    except OffersError as err:
        job.error = str(err)
    except BaseException as err:
        # Nobody would see it in this thread: the page raises it again.
        job.failure = err
    finally:
        job.finished.set()


@st.cache_resource
def get_runner():
    """Return the runner shared by all the sessions of the app."""
    return CollectionRunner()
