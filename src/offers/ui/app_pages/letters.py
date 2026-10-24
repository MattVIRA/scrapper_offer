"""Page « Lettres »: write the letters of the offers « À rédiger », then find them."""

import streamlit as st

from offers.config import load_config
from offers.letters import LettersError
from offers.letters.generate import letters_to_write
from offers.letters.inputs import load_inputs
from offers.sources import SOURCES
from offers.storage.database import list_letters
from offers.ui import letters_view
from offers.ui.letters_job import get_letters_runner
from offers.ui.session import open_database

st.title("Lettres")
runner = get_letters_runner()
runner.raise_failure()
job = runner.job
letters_config = load_config(str(st.session_state.config_path), set(SOURCES)).letters
db_path = st.session_state.db_path

st.header("Génération")
try:
    inputs, inputs_error = load_inputs(letters_config), None
except LettersError as err:
    inputs, inputs_error = None, str(err)
letters_view.show_inputs(letters_config, inputs, inputs_error)
letters_view.show_prompt(letters_config, db_path)
with open_database(db_path) as conn:
    targets = letters_to_write(conn, letters_config)
letters_view.show_targets(targets)
# A missing input is shown above, in place of the button.
if inputs_error:
    st.error("Corrige les entrées ci-dessus pour générer les lettres.", icon=":material/error:")
else:
    letters_view.show_generate_button(runner, db_path, letters_config, targets)

if job is not None and job.running:
    letters_view.show_progress(job)
elif job is not None:
    letters_view.show_result(job)

with open_database(db_path) as conn:
    letters = list_letters(conn)
letters_view.show_letters(letters, letters_config.output_dir)
