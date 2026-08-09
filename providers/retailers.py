"""
Per-retailer adapters (spec section 20 example: BTechProvider,
AmazonEgyptProvider, CarrefourProvider, NoonProvider, ManualProvider).

Each subclasses GenericHtmlProvider (plain HTTP fetch — price is in the raw
HTML), RenderedHtmlProvider (needs a real browser to execute JavaScript
first — price is injected client-side), or ManualProvider (automated
fetching deliberately never attempted — see "BLOCKED" below). Kept as
separate classes so:
  (a) one retailer changing its markup only requires touching one class,
  (b) each can be independently switched between static/rendered/manual if
      real-world testing shows it needs a different strategy,
  (c) retailer-specific selector overrides can be added here later without
      touching the shared extraction logic in generic_html.py.

VERIFIED (2026-08-09), live-tested against real product pages and real
robots.txt files via a real browser session (this app's own sandboxed
fetch has no outbound internet — see generic_html.py's module docstring).
Three groups:

STATIC — price ships in the raw HTML, GenericHtmlProvider works as-is:
  - 2B (TwoBProvider): `product:price:amount` meta tag.
  - Jumia Egypt (JumiaEgyptProvider): full schema.org Product/Offer
    JSON-LD. robots.txt explicitly names ClaudeBot and anthropic-ai with
    "Allow: /" — an explicit invitation, not just silence.
  - Noon Egypt (NoonEgyptProvider): full schema.org Product/Offer
    JSON-LD (earlier assumption that it's an unscrapable JS SPA was
    wrong — the product JSON-LD is server-rendered). robots.txt names
    ClaudeBot with "Allow: /".
  - Zanussi Egypt (ZanussiEgyptProvider): `product:price:amount` meta tag,
    same mechanism as 2B. No robots.txt file exists at all (404) — no
    restriction stated, so no restriction applies.

RENDERED — price is injected by JavaScript, needs RenderedHtmlProvider:
  - B.TECH (BTechProvider): full schema.org Product/Offer JSON-LD once
    rendered.
  - Raya Shop (RayaShopProvider): raw HTML has no price at all (checked
    directly with a plain fetch); the rendered page shows it. No
    AI-bot-specific robots.txt rules either way.

BLOCKED — robots.txt explicitly names AI bots as disallowed. Treated the
same way this app treats 2B's category-page exclusion: an explicit,
site-owner opt-out is respected regardless of what this app's own
User-Agent string happens to say. These stay ManualProvider — automated
fetching (even single-listing price checks) is never attempted:
  - Amazon Egypt (AmazonEgyptProvider): robots.txt disallows ClaudeBot,
    Claude-User, Claude-SearchBot, Claude-Web and GPTBot by name (plus
    dozens of other AI crawlers) with "Disallow: /".
  - Carrefour Egypt (CarrefourEgyptProvider): robots.txt disallows GPTBot
    site-wide, and separately disallows *.html/*.aspx for every crawler
    (which covers essentially all real product/category pages there).
  - Cairo Sales Store (CairoSalesStoreProvider): robots.txt (Cloudflare-
    managed) disallows ClaudeBot by name with "Disallow: /".

RadioShack Egypt (RadioShackEgyptProvider) is STATIC and unblocked (a
`.price` div in the raw HTML, no AI-bot rules) but its own catalog leans
electronics/accessories — large-appliance coverage there is unconfirmed,
so no discovery source was added for it; individual listings you add
still get tracked normally.

price_check.py always catches failures per-listing and never lets one
retailer's breakage stop the run.
"""
from .generic_html import GenericHtmlProvider
from .rendered_html import RenderedHtmlProvider
from .manual import ManualProvider


class BTechProvider(RenderedHtmlProvider):
    key = "btech"
    display_name = "B.TECH"
    notes = (
        "btech.com is a client-rendered storefront - price only appears after JavaScript "
        "runs (verified 2026-08-09). Needs a real browser (Playwright); only runs in the "
        "GitHub Actions daily scan, not on PythonAnywhere's free tier."
    )


class TwoBProvider(GenericHtmlProvider):
    key = "twob"
    display_name = "2B Egypt"
    notes = (
        "2B product pages ship price in the raw HTML (verified 2026-08-09, "
        "product:price:amount meta tag) -> plain fetch works. Its category/listing "
        "pages are deliberately never crawled - 2B's robots.txt disallows it."
    )


class JumiaEgyptProvider(GenericHtmlProvider):
    key = "jumia_eg"
    display_name = "Jumia Egypt"
    notes = (
        "Verified 2026-08-09: full schema.org Product/Offer JSON-LD ships in the raw "
        "HTML -> plain fetch works. robots.txt explicitly grants ClaudeBot and "
        "anthropic-ai 'Allow: /' - one of the few sites that names Claude specifically "
        "as welcome. Plain category pages (e.g. /appliances-fridges-freezers/) are "
        "eligible for discovery; deeper faceted/filtered URLs are blocked by robots.txt "
        "and are never used."
    )


class NoonEgyptProvider(GenericHtmlProvider):
    key = "noon_eg"
    display_name = "Noon Egypt"
    notes = (
        "Verified 2026-08-09: full schema.org Product/Offer JSON-LD ships in the raw "
        "HTML -> plain fetch works (this corrects an earlier assumption that Noon is an "
        "unscrapable JS SPA - the product data is actually server-rendered). robots.txt "
        "explicitly grants ClaudeBot 'Allow: /'; the wildcard rule only blocks two "
        "internal service paths."
    )


class RadioShackEgyptProvider(GenericHtmlProvider):
    key = "radioshack_eg"
    display_name = "RadioShack Egypt"
    notes = (
        "Verified 2026-08-09: price ships in the raw HTML in a plain '.price' div (no "
        "JSON-LD, but the CSS-selector fallback catches it) -> plain fetch works. No "
        "AI-bot-specific robots.txt rules. Catalog leans electronics/accessories - large-"
        "appliance selection (fridges/ACs/washing machines) is unconfirmed, so no "
        "discovery source was added; individually-added listings still get tracked."
    )


class ZanussiEgyptProvider(GenericHtmlProvider):
    key = "zanussi_eg"
    display_name = "Zanussi Egypt (official)"
    notes = (
        "Verified 2026-08-09: price ships in the raw HTML (product:price:amount meta "
        "tag, same mechanism as 2B) -> plain fetch works. No robots.txt file exists at "
        "this domain at all (confirmed 404/blank) - no restriction is stated, so none "
        "applies. Official single-brand store, useful for discovery of new Zanussi "
        "models specifically."
    )


class RayaShopProvider(RenderedHtmlProvider):
    key = "raya"
    display_name = "Raya Shop"
    notes = (
        "Verified 2026-08-09: raw HTML has no price at all (checked with a plain fetch, "
        "no JSON-LD/meta/CSS price anywhere); the price only appears after JavaScript "
        "runs -> needs a real browser (Playwright), same as B.TECH. No AI-bot-specific "
        "robots.txt rules. No reliable product-link pattern was found on its category "
        "pages, so no discovery source was added - only listings you add individually "
        "are tracked."
    )


class OfficialBrandStoreProvider(GenericHtmlProvider):
    key = "official_brand"
    display_name = "Official Brand Store"
    notes = "Generic fallback for an official single-brand store not yet individually verified."


class AmazonEgyptProvider(ManualProvider):
    key = "amazon_eg"
    display_name = "Amazon Egypt"
    notes = (
        "BLOCKED (verified 2026-08-09): amazon.eg's robots.txt disallows ClaudeBot "
        "(listed twice), Claude-User, Claude-SearchBot, Claude-Web and GPTBot by name "
        "with 'Disallow: /', alongside dozens of other named AI crawlers. This is an "
        "explicit, unambiguous opt-out from automated AI fetching - respected here the "
        "same way 2B's anthropic-ai exclusion is, regardless of what User-Agent string "
        "this app sends. Tracked manually only; paste prices in yourself."
    )


class CarrefourEgyptProvider(ManualProvider):
    key = "carrefour_eg"
    display_name = "Carrefour Egypt"
    notes = (
        "BLOCKED (verified 2026-08-09): carrefouregypt.com's robots.txt disallows "
        "GPTBot site-wide with 'Disallow: /', and separately disallows *.html/*.aspx "
        "for every crawler - which covers essentially all real product and category "
        "pages on this (legacy ASP-based) site. Tracked manually only."
    )


class CairoSalesStoreProvider(ManualProvider):
    key = "cairosales_eg"
    display_name = "Cairo Sales Store"
    notes = (
        "BLOCKED (verified 2026-08-09): cairosales.com's Cloudflare-managed robots.txt "
        "disallows ClaudeBot by name with 'Disallow: /'. Tracked manually only."
    )
