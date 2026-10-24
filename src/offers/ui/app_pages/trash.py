"""Page « Corbeille »: the hidden offers, which can be restored, never deleted."""

from offers.ui.offer_table import PageSettings, show_offer_page

show_offer_page(PageSettings(key="trash", title="Corbeille", in_trash=True))
