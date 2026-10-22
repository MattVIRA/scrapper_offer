"""Entry point of the interface: streamlit run app.py -- --db ... --config ..."""

import sys
from pathlib import Path

import streamlit as st

from offers.errors import OffersError
from offers.ui.session import store_paths

PAGES_DIR = Path(__file__).resolve().parent / "app_pages"
# fmt: off
PAGES = [
    ("offers.py",    "Offres",    ":material/work:"),
    ("favorites.py", "Favoris",   ":material/star:"),
    ("trash.py",     "Corbeille", ":material/delete:"),
    ("collect.py",   "Collecte",  ":material/cloud_download:"),
]
# fmt: on

st.set_page_config(page_title="Offres", page_icon=":material/work:", layout="wide")
store_paths(st.session_state, sys.argv[1:])
page = st.navigation(
    [st.Page(PAGES_DIR / name, title=title, icon=icon) for name, title, icon in PAGES],
    position="top",
)
# The entry point shows the project errors; unexpected ones keep their trace.
try:
    page.run()
except OffersError as err:
    st.error(str(err), icon=":material/error:")
