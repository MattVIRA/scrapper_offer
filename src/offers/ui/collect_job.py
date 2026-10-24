"""Collection run in a background thread (background_job)."""

from dataclasses import dataclass, field
from functools import partial

import streamlit as st

from offers.pipeline import run_collect
from offers.sources import create_source
from offers.ui.background_job import BackgroundJob, BackgroundRunner


@dataclass
class CollectionJob(BackgroundJob):
    """One collection; done holds the SourceReport of each source read."""

    source_names: list[str] = field(default_factory=list)

    @property
    def report(self):
        """CollectReport of the finished collection, or None."""
        return self.result


class CollectionRunner(BackgroundRunner):
    """Runs one collection at a time for the whole app."""

    def start(self, config, source_configs, db_path, excel_path, now):
        """Start a collection of these sources; return False if one is running."""
        job = CollectionJob(now, source_names=[source.name for source in source_configs])
        return self.run(job, partial(collect, config, source_configs, db_path, excel_path))


def collect(config, source_configs, db_path, excel_path, job):
    """Work of the thread: run the collection, noting each source read."""
    sources = [create_source(source) for source in source_configs]
    return run_collect(
        config,
        str(db_path),
        str(excel_path),
        job.started_at,
        sources=sources,
        on_source_done=job.done.append,
    )


@st.cache_resource
def get_runner():
    """Return the runner shared by all the sessions of the app."""
    return CollectionRunner()
