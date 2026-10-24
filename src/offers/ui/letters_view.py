"""Sections of the « Lettres » page: inputs, prompt, generation, letters written."""

from datetime import datetime

import streamlit as st

from offers.letters import LettersError
from offers.letters.generate import has_letter
from offers.letters.inputs import CV_DIR, EXAMPLES_DIR, INSTRUCTIONS_FILE
from offers.letters.prompt import load_prompt, prompt_version, save_prompt
from offers.summary import letter_line, letters_total
from offers.tracking import status_label
from offers.ui.letter_link import finder_button

PROMPT_KEY = "letters_prompt"
PROMPT_HEIGHT = 400
PROMPT_ERROR_KEY = "letters_prompt_error"
PROMPT_SAVED_KEY = "letters_prompt_saved"
CONFIRMING_KEY = "letters_confirming"
REPLACE_KEY = "letters_replace"
# The prompt is saved next to the database backups, as config.yaml.
BACKUP_DIR = "backup"
# How often the page looks at a running generation.
PROGRESS_REFRESH = "2s"
DATE_FORMAT = "%d/%m/%Y à %H:%M"
NO_STATUS = "Sans statut"
NO_COMPANY = "entreprise non précisée"


def offer_name(offer):
    return f"{offer.title} — {offer.company or NO_COMPANY}"


def file_names(documents):
    return ", ".join(document.name for document in documents)


def show_inputs(letters_config, inputs, error):
    """What the letters are written from, found in the profile folder."""
    st.subheader("Entrées")
    st.caption(
        f"Dossier du profil : {letters_config.profile_dir} ({CV_DIR}/, {EXAMPLES_DIR}/, "
        f"{INSTRUCTIONS_FILE})"
    )
    if error:
        st.error(error, icon=":material/error:")
        return
    st.table(
        {
            "CV": file_names(inputs.cvs),
            "Anciennes lettres": file_names(inputs.examples) or "aucune",
            "Consignes": INSTRUCTIONS_FILE if inputs.instructions else "aucune",
        },
        border="horizontal",
        width="content",
    )
    if inputs.ignored:
        names = ", ".join(path.name for path in inputs.ignored)
        st.warning(
            f"Fichiers ignorés (format non lu : .pdf, .docx, .md ou .txt) : {names}",
            icon=":material/warning:",
        )


def save_prompt_text(path, backup_dir):
    """Callback of « Enregistrer le prompt »: write the text area into the file."""
    try:
        save_prompt(path, st.session_state[PROMPT_KEY], backup_dir, datetime.now())
        st.session_state[PROMPT_SAVED_KEY] = True
    except LettersError as err:
        st.session_state[PROMPT_ERROR_KEY] = str(err)


def show_prompt(letters_config, db_path):
    """Prompt of the letters, with its version; it can be changed and saved."""
    st.subheader("Prompt")
    try:
        saved_text = load_prompt(letters_config.prompt)
    except LettersError as err:
        st.error(f"{err} « Enregistrer le prompt » le crée.", icon=":material/error:")
        saved_text = ""
    st.caption(f"Fichier : {letters_config.prompt} · version {prompt_version(saved_text)}")
    st.session_state.setdefault(PROMPT_KEY, saved_text)
    st.text_area(
        "Prompt envoyé à Claude",
        key=PROMPT_KEY,
        height=PROMPT_HEIGHT,
        label_visibility="collapsed",
    )
    with st.container(horizontal=True, vertical_alignment="center"):
        st.button(
            "Enregistrer le prompt",
            icon=":material/save:",
            key="letters_prompt_save",
            disabled=st.session_state[PROMPT_KEY] == saved_text,
            on_click=save_prompt_text,
            args=(letters_config.prompt, db_path.parent / BACKUP_DIR),
        )
        if st.session_state[PROMPT_KEY] != saved_text:
            st.caption(
                "Modifications non enregistrées : les lettres utilisent le prompt enregistré."
            )
    error = st.session_state.pop(PROMPT_ERROR_KEY, None)
    if error:
        st.error(error, icon=":material/error:")
    if st.session_state.pop(PROMPT_SAVED_KEY, False):
        st.success("Prompt enregistré.", icon=":material/check_circle:")


def show_targets(targets):
    """Offers whose letter is « À rédiger », out of the trash."""
    st.subheader("Offres ciblées")
    if not targets:
        st.info(
            "Aucune offre « À rédiger ». Mets le champ Lettre d'une offre à « À rédiger » "
            "depuis sa fiche ou les actions groupées.",
            icon=":material/info:",
        )
        return
    st.caption(f"{len(targets)} offres « À rédiger »")
    st.dataframe(
        [
            {
                "Titre": stored.offer.title,
                "Entreprise": stored.offer.company or "",
                "Lettre": "déjà présente" if has_letter(stored) else "",
            }
            for stored, path in targets
        ],
        hide_index=True,
        alt="Offres dont la lettre est à rédiger",
    )


def open_confirmation():
    st.session_state[CONFIRMING_KEY] = True


def close_confirmation():
    st.session_state[CONFIRMING_KEY] = False


def start_generation(runner, db_path, letters_config, targets):
    """Callback of « Confirmer »: start the generation in the background."""
    replace = st.session_state.get(REPLACE_KEY, False)
    runner.start(db_path, letters_config, [s.id for s, _ in targets], replace, datetime.now())
    close_confirmation()


# The open state is kept in the session: a click in the dialog reruns the page.
@st.dialog("Générer les lettres", width="medium", on_dismiss=close_confirmation)
def confirm_generation(runner, db_path, letters_config, targets):
    """Confirmation of the offers targeted, before any call to Claude."""
    st.markdown(f"**{len(targets)} lettres** vont être écrites :")
    st.text(
        "\n".join(
            f"• {offer_name(stored.offer)}"
            + (" (lettre déjà présente)" if has_letter(stored) else "")
            for stored, path in targets
        )
    )
    st.warning(
        "Chaque lettre utilise ton forfait Claude, environ une minute par lettre.",
        icon=":material/info:",
    )
    if any(has_letter(stored) for stored, _ in targets):
        st.checkbox(
            "Remplacer les lettres existantes",
            key=REPLACE_KEY,
            help="L'ancienne lettre est gardée dans le dossier backup des lettres. "
            "Sans cette case, les offres qui en ont une sont sautées.",
        )
    with st.container(horizontal=True, horizontal_alignment="right"):
        cancelled = st.button("Annuler", key="letters_cancel", on_click=close_confirmation)
        confirmed = st.button(
            "Confirmer",
            type="primary",
            key="letters_confirm",
            on_click=start_generation,
            args=(runner, db_path, letters_config, targets),
        )
    # A click in a dialog only reruns the dialog: the whole page must rerun to close it.
    if cancelled or confirmed:
        st.rerun()


def show_generate_button(runner, db_path, letters_config, targets):
    """Large « Générer les lettres » button, then its confirmation."""
    running = runner.job is not None and runner.job.running
    _, middle, _ = st.columns([1, 2, 1])
    middle.button(
        "Générer les lettres",
        type="primary",
        icon=":material/edit_note:",
        width="stretch",
        key="letters_generate",
        disabled=running or not targets,
        on_click=open_confirmation,
    )
    if st.session_state.get(CONFIRMING_KEY) and targets and not running:
        confirm_generation(runner, db_path, letters_config, targets)


@st.fragment(run_every=PROGRESS_REFRESH)
def show_progress(job):
    """Progress of the running generation; the whole page reruns at the end."""
    if not job.running:
        st.rerun()
    stopping = job.stop_requested.is_set()
    if stopping:
        label = "Arrêt demandé : la lettre en cours se termine, puis la génération s'arrête"
    else:
        label = f"Génération en cours : {len(job.done)} lettres sur {len(job.offer_ids)}"
    with st.status(label, expanded=True, state="running"):
        for result in job.done:
            st.text(letter_line(result))
    st.button(
        "Arrêter la génération",
        icon=":material/stop_circle:",
        key="letters_stop",
        disabled=stopping,
        on_click=job.stop_requested.set,
    )


def show_result(job):
    """Summary of the last generation, with the texts of the command line."""
    st.subheader("Dernière génération")
    st.caption(f"Lancée le {job.started_at:{DATE_FORMAT}}")
    if job.error:
        st.error(job.error, icon=":material/error:")
        return
    report = job.report
    for result in report.results:
        if result.error:
            st.error(letter_line(result), icon=":material/error:")
        elif result.skipped:
            st.info(letter_line(result), icon=":material/info:")
        else:
            st.success(letter_line(result), icon=":material/check_circle:")
    st.markdown(letters_total(report))


def show_letters(letters, output_dir):
    """Offers that have a letter, the most recent first, each with its Finder button."""
    st.subheader("Lettres générées")
    finder_button(output_dir, key="letters_folder", label="Ouvrir le dossier des lettres")
    if not letters:
        st.info("Aucune lettre pour l'instant.", icon=":material/info:")
        return
    for stored in letters:
        letter = stored.letter
        status = status_label(stored.status) if stored.status else NO_STATUS
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            with st.container():
                st.markdown(f"**{stored.offer.title}** — {stored.offer.company or NO_COMPANY}")
                st.caption(
                    f"Lettre du {letter.created_at:{DATE_FORMAT}} · prompt {letter.prompt_version}"
                    f" · {status} · {letter.path.name}"
                )
            finder_button(letter.path, key=f"letters_finder_{stored.id}")
