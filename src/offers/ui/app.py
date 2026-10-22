"""Entry point of the interface: streamlit run app.py -- --db ... --config ..."""

import argparse
import sys
from pathlib import Path

import streamlit as st

from offers.__main__ import DEFAULT_CONFIG, DEFAULT_DB

PAGES_DIR = Path(__file__).resolve().parent / "app_pages"
# fmt: off
PAGES = [
    ("offers.py",    "Offres",    ":material/work:"),
    ("favorites.py", "Favoris",   ":material/star:"),
    ("trash.py",     "Corbeille", ":material/delete:"),
    ("collect.py",   "Collecte",  ":material/cloud_download:"),
]
# fmt: on


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


st.set_page_config(page_title="Offres", page_icon=":material/work:", layout="wide")
store_paths(st.session_state, sys.argv[1:])
page = st.navigation(
    [st.Page(PAGES_DIR / name, title=title, icon=icon) for name, title, icon in PAGES],
    position="top",
)
page.run()
