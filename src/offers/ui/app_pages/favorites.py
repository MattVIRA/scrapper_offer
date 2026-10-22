"""Page « Favoris »: the offers marked as favorite, without their yellow marker."""

from offers.ui.offer_table import PageSettings, show_offer_page

show_offer_page(
    PageSettings(key="favorites", title="Favoris", favorites_only=True, count_in_title=True)
)
