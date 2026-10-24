"""Generation of the letters in a background thread (background_job).

A letter takes about a minute: the page only reads the progress.
"""

from dataclasses import dataclass, field
from functools import partial

import streamlit as st

from offers import claude_code
from offers.letters.generate import run_letters
from offers.storage.database import backup_database
from offers.ui.background_job import BackgroundJob, BackgroundRunner
from offers.ui.session import open_database


@dataclass
class LettersJob(BackgroundJob):
    """One generation; done holds the LetterResult of each offer."""

    offer_ids: list[int] = field(default_factory=list)

    @property
    def report(self):
        """LettersReport of the finished generation, or None."""
        return self.result


class LettersRunner(BackgroundRunner):
    """Runs one generation at a time for the whole app."""

    def start(self, db_path, letters_config, offer_ids, replace, now):
        """Start writing the letters of these offers; return False if one is running."""
        job = LettersJob(now, offer_ids=list(offer_ids))
        return self.run(job, partial(generate, db_path, letters_config, replace))


def generate(db_path, letters_config, replace, job):
    """Work of the thread: save the database, then write the letters."""
    backup_database(db_path, job.started_at)
    # The connection is opened in the thread that uses it.
    with open_database(db_path) as conn:
        return run_letters(
            conn,
            letters_config,
            job.offer_ids,
            job.started_at,
            replace=replace,
            # Looked up at each run, so that the tests can replace Claude.
            ask=claude_code.ask_json,
            on_letter_done=job.done.append,
        )


@st.cache_resource
def get_letters_runner():
    """Return the runner shared by all the sessions of the app."""
    return LettersRunner()
