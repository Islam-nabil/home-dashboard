"""
Per-retailer adapters (spec section 20 example: BTechProvider,
AmazonEgyptProvider, CarrefourProvider, NoonProvider, ManualProvider).

Each subclasses either GenericHtmlProvider (plain HTTP fetch — price is in
the raw HTML) or RenderedHtmlProvider (needs a real browser to execute
JavaScript first — price is injected client-side). Kept as separate classes
so:
  (a) one retailer changing its markup only requires touching one class,
  (b) each can be independently switched between static/rendered/manual if
      real-world testing shows it needs a different strategy,
  (c) retailer-specific selector overrides can be added here later without
      touching the shared extraction logic in generic_html.py.

VERIFIED vs UNVERIFIED (2026-08-09): BTechProvider and TwoBProvider were
live-tested against real product pages (via a real browser session, not
this app's own sandboxed fetch, which has no outbound internet — see
generic_html.py's module docstring) and their render_mode below matches
what was actually observed:
  - 2B (TwoBProvider): price ships in the raw HTML (`product:price:amount`
    meta tag) -> GenericHtmlProvider, render_mode='static'. Confirmed
    working. Its category/listing pages are NOT scanned for new products —
    2B's robots.txt explicitly disallows crawling them (and separately
    names "anthropic-ai" as disallowed site-wide) — see discovery.py.
  - B.TECH (BTechProvider): price is injected by JavaScript after load;
    the raw HTML the server sends has no price in it at all. Rendering the
    page first exposes a full schema.org Product/Offer JSON-LD block ->
    RenderedHtmlProvider, render_mode='js'. B.TECH's robots.txt places no
    restriction on product or category paths, so its listing pages ARE
    eligible for new-product discovery (see discovery_sources seed data).

Everyone else below (Amazon/Carrefour/Noon/Raya/official brand sites)
remains untested — treat SUPPORTED=True as "worth trying," not "confirmed
working." price_check.py always catches failures per-listing and never
lets one retailer's breakage stop the run.
"""
from .generic_html import GenericHtmlProvider
from .rendered_html import RenderedHtmlProvider


class BTechProvider(RenderedHtmlProvider):
    key = "btech"
    display_name = "B.TECH"
    notes = (
        "btech.com is a client-rendered storefront - price only appears after JavaScript "
        "runs (verified 2026-08-09). Needs a real browser (Playwright); only runs in the "
        "GitHub Actions daily scan, not on PythonAnywhere's free tier."
    )


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
    notes = (
        "2B product pages ship price in the raw HTML (verified 2026-08-09, "
        "product:price:amount meta tag) -> plain fetch works. Its category/listing "
        "pages are deliberately never crawled - 2B's robots.txt disallows it."
    )


class RayaShopProvider(GenericHtmlProvider):
    key = "raya"
    display_name = "Raya Shop"


class OfficialBrandStoreProvider(GenericHtmlProvider):
    key = "official_brand"
    display_name = "Official Brand Store"
