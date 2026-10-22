"""Paths given to the interface on the command line, and database access."""

import argparse
from contextlib import contextmanager
from pathlib import Path

from offers.__main__ import DEFAULT_CONFIG, DEFAULT_DB
from offers.storage.database import connect


def parse_args(argv):
    """Return the paths given after the -- of streamlit run."""
    parser = argparse.ArgumentParser(prog="offers ui")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    return parser.parse_args(argv)


def store_paths(state, argv):
    """Keep the paths in the session state, read once per session."""
    if "db_path" in state:
        return
    args = parse_args(argv)
    state.db_path = args.db
    state.config_path = args.config


@contextmanager
def open_database(path):
    """Open the database for one run or one callback, and close it.

    No connection is shared between sessions or threads.
    """
    conn = connect(path)
    try:
        yield conn
    finally:
        conn.close()
