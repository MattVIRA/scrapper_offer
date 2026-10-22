"""Page « Offres »: all the offers that are not in the trash."""

from offers.ui.offer_table import PageSettings, show_offer_page

show_offer_page(PageSettings(key="offers", title="Offres"))
