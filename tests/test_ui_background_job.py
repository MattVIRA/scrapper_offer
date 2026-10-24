"""Tests of the work run in a background thread (offers.ui.background_job)."""

import threading
from datetime import datetime

import pytest

from offers.errors import OffersError
from offers.ui.background_job import BackgroundJob, BackgroundRunner

NOW = datetime(2026, 10, 23, 9, 0)
WAIT = 10


def run(work):
    runner = BackgroundRunner()
    job = BackgroundJob(NOW)
    assert runner.run(job, work)
    assert job.finished.wait(WAIT)
    return runner, job


def test_result_and_progress():
    def work(job):
        job.done.append("étape 1")
        return "fini"

    _, job = run(work)
    assert (job.result, job.done, job.error, job.running) == ("fini", ["étape 1"], None, False)


def test_project_error_is_kept_as_a_message():
    def work(job):
        raise OffersError("site en panne")

    runner, job = run(work)
    assert job.error == "site en panne"
    runner.raise_failure()


def test_unexpected_error_is_raised_once_by_the_page():
    def work(job):
        raise KeyError("bug")

    runner, _ = run(work)
    with pytest.raises(KeyError, match="bug"):
        runner.raise_failure()
    runner.raise_failure()


def test_one_job_at_a_time():
    release = threading.Event()
    runner = BackgroundRunner()
    first = BackgroundJob(NOW)
    assert runner.run(first, lambda job: release.wait(WAIT))

    assert not runner.run(BackgroundJob(NOW), lambda job: None)
    assert runner.job is first

    release.set()
    assert first.finished.wait(WAIT)
    assert runner.run(BackgroundJob(NOW), lambda job: None)
