"""Work run in a background thread, so that the interface stays usable.

A Streamlit script stops as soon as the user clicks elsewhere or changes
page: a long work run inside it could be cut in the middle. The thread
does not use Streamlit; the page only reads the progress of its job.
Shared by the collection and the generation of the letters.
"""

import threading
from dataclasses import dataclass, field
from datetime import datetime

from offers.errors import OffersError


@dataclass
class BackgroundJob:
    """One work: its progress, then its result or its error."""

    started_at: datetime
    # Results of the steps already done (one per source, one per letter), in order.
    done: list = field(default_factory=list)
    result: object = None
    # Message of a project error that stopped the whole work.
    error: str | None = None
    # Unexpected error, raised again by the page so that its trace is seen.
    failure: BaseException | None = None
    finished: threading.Event = field(default_factory=threading.Event)
    # Set by the page; the work checks it between two steps.
    stop_requested: threading.Event = field(default_factory=threading.Event)

    @property
    def running(self):
        return not self.finished.is_set()


class BackgroundRunner:
    """Runs one job at a time for the whole app, and keeps the last one."""

    def __init__(self):
        self.lock = threading.Lock()
        self.job = None

    def run(self, job, work):
        """Start work(job) in a thread; return False if a job is running."""
        with self.lock:
            if self.job is not None and self.job.running:
                return False
            self.job = job
        threading.Thread(target=run_job, args=(job, work), daemon=True).start()
        return True

    def raise_failure(self):
        """Raise, once, the unexpected error of the last job, if any."""
        job = self.job
        if job is not None and job.failure is not None:
            failure, job.failure = job.failure, None
            raise failure


def run_job(job, work):
    """Body of the thread: run the work and keep its outcome in the job."""
    try:
        job.result = work(job)
    except OffersError as err:
        job.error = str(err)
    except BaseException as err:
        # Nobody would see it in this thread: the page raises it again.
        job.failure = err
    finally:
        job.finished.set()
