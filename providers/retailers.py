"""
Per-retailer adapters (spec section 20 example: BTechProvider,
AmazonEgyptProvider, CarrefourProvider, NoonProvider, ManualProvider).

Each subclasses GenericHtmlProvider — same tier-3 "structured page
retrieval" strategy — but is kept as its own class so:
  (a) one retailer changing its markup only requires touching one class,
  (b) each can be independently disabled (fall back to manual) if it turns
      out to require JS rendering or blocks simple requests,
  (c) retailer-specific selector overrides can be added here later without
      touching the shared extraction logic in generic_html.py.

None of these were live-verified against the real sites during this build
(see generic_html.py's module docstring for why) — treat SUPPORTED=True as
"worth trying," not "confirmed working." price_check.py always catches
failures per-listing and never lets one retailer's breakage stop the run.
"""
from .generic_html import GenericHtmlProvider


class BTechProvider(GenericHtmlProvider):
    key = "btech"
    display_name = "B.TECH"
    notes = "btech.com product pages generally include JSON-LD product data."


class AmazonEgyptProvider(GenericHtmlProvider):
    key = "amazon_eg"
    display_name = "Amazon Egypt"
    notes = "Amazon pages are frequently protected against automated fetching; expect manual fallback often."


class CarrefourEgyptProvider(GenericHtmlProvider):
    key = "carrefour_eg"
    display_name = "Carrefour Egypt"


class NoonEgyptProvider(GenericHtmlProvider):
    key = "noon_eg"
    display_name = "Noon Egypt"
    notes = "Noon is a JS-heavy SPA; structured-data extraction may frequently fail -> manual fallback expected."


class TwoBProvider(GenericHtmlProvider):
    key = "twob"
    display_name = "2B Egypt"


class RayaShopProvider(GenericHtmlProvider):
    key = "raya"
    display_name = "Raya Shop"


class OfficialBrandStoreProvider(GenericHtmlProvider):
    key = "official_brand"
    display_name = "Official Brand Store"
