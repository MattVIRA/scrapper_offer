"""Choices of status and letter, as offered in the widgets of the interface."""

from offers.tracking import LETTER_STATUSES, STATUSES, letter_label, status_label

# Stands for "no status" / "no letter" in the widgets, which need a value.
NONE_CODE = ""
NONE_STATUS_LABEL = "Sans statut"
NONE_LETTER_LABEL = "Aucune"
STATUS_CHOICES = [NONE_CODE, *STATUSES]
LETTER_CHOICES = [NONE_CODE, *LETTER_STATUSES]


def status_choice_label(code):
    return NONE_STATUS_LABEL if code == NONE_CODE else status_label(code)


def letter_choice_label(code):
    return NONE_LETTER_LABEL if code == NONE_CODE else letter_label(code)


def to_widget_code(code):
    """Return the widget value of a database code (None: no status or letter)."""
    return NONE_CODE if code is None else code


def to_database_code(code):
    """Return the database code of a widget value."""
    return None if code == NONE_CODE else code
