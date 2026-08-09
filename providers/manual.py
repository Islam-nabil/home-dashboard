"""
ManualProvider — the guaranteed-to-work fallback (spec section 20/6).

Used for every retailer that doesn't support (or that we choose not to
attempt) automated fetching: requires the user to enter/update prices
themselves through the UI (`POST /api/products/<id>/price`). This is
"tier 5" in the provider preference order and is always available.
"""
from .base import PriceProvider, ProviderUnsupported


class ManualProvider(PriceProvider):
    key = "manual"
    display_name = "Manual Entry"
    tier = 5

    def fetch(self, url: str) -> dict:
        raise ProviderUnsupported(
            "This retailer is tracked manually. Update its price from the product page "
            "(or paste a fresh URL into the wishlist importer) instead of automated fetching."
        )
