"""Show a letter, or the letters folder, in the Finder."""

import subprocess
from pathlib import Path

import streamlit as st

from offers.letters import LettersError

# macOS: "open -R" selects a file in the Finder, "open" opens a folder.
OPEN_COMMAND = "open"
REVEAL_OPTION = "-R"
FINDER_LABEL = "Ouvrir dans le Finder"


def reveal_in_finder(path, run=subprocess.run):
    """Select a file (or open a folder) in the Finder.

    run: runs the command, as subprocess.run (replaced in the tests).
    """
    path = Path(path)
    if not path.exists():
        raise LettersError(
            f"Introuvable : {path}. Le fichier a été déplacé ou supprimé ; "
            "pour refaire la lettre, remets son champ Lettre à « À rédiger »."
        )
    command = (
        [OPEN_COMMAND, str(path)] if path.is_dir() else [OPEN_COMMAND, REVEAL_OPTION, str(path)]
    )
    try:
        completed = run(command, check=False, capture_output=True, text=True)
    except OSError as err:
        raise LettersError(f"Impossible d'ouvrir le Finder : {err}.") from err
    if completed.returncode != 0:
        raise LettersError(f"Impossible d'ouvrir le Finder : {completed.stderr.strip()}.")


def finder_button(path, key, label=FINDER_LABEL):
    """Button that shows path in the Finder; an error is shown next to it."""
    if st.button(label, icon=":material/folder_open:", key=key):
        try:
            reveal_in_finder(path, run=subprocess.run)
        except LettersError as err:
            st.error(str(err), icon=":material/error:")
