"""Page « Offres »: all the offers that are not in the trash."""

import streamlit as st

from offers.ui.offer_table import PageSettings, show_offer_page

st.title("Offres")
show_offer_page(PageSettings(key="offers"))
