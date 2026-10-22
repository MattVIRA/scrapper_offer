"""Statuses of the user's follow-up of an offer.

No status means a new offer. Being scored is not a status: it is read in
the evaluations table. The letter is a separate field, not a status.
"""

# Code stored in the database -> label shown to the user, in display order.
STATUSES = {
    "to_review": "À voir",
    "interesting": "Intéressant",
    "applied": "Postulé",
    "answered": "Réponse",
    "rejected": "Refusé",
    "not_for_me": "Pas pour moi",
}
# No letter status means no letter planned.
LETTER_STATUSES = {
    "to_write": "À rédiger",
    "written": "Rédigée",
}


def status_label(code):
    """Return the label of a status code."""
    return STATUSES[code]


def letter_label(code):
    """Return the label of a letter status code."""
    return LETTER_STATUSES[code]
