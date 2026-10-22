"""Statuses of the user's follow-up of an offer.

No status means a new offer. Being scored is not a status: it is read in
the evaluations table.
"""

# Code stored in the database -> label shown to the user, in display order.
STATUSES = {
    "to_review": "À voir",
    "interesting": "Intéressant",
    "to_write": "À rédiger",
    "letter_ready": "Lettre prête",
    "applied": "Postulé",
    "answered": "Réponse",
    "rejected": "Refusé",
    "not_for_me": "Pas pour moi",
}
CODES_BY_LABEL = {label: code for code, label in STATUSES.items()}


def status_code(label):
    """Return the code of a status label; None if the label is unknown."""
    return CODES_BY_LABEL.get(label.strip())


def status_label(code):
    """Return the label of a status code."""
    return STATUSES[code]
