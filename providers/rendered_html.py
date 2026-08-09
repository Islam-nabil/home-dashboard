"""
RenderedHtmlProvider — same "tier 3" structured-data extraction strategy as
GenericHtmlProvider, but for sites that only expose price via client-side
JavaScript (confirmed for B.TECH — see below). Reuses every extraction
helper from generic_html.py so a listing that switches from plain-HTML to
JS-rendering only needs its class changed in providers/retailers.py, never
duplicated parsing logic.

WHY THIS EXISTS (verified 2026-08-09, not guessed): a plain `requests.get()`
against a real btech.com product page returns a near-empty React/Vue shell —
the literal string "Loading..." is in the markup and the price is absent.
Rendering the same page in a real browser and reading the DOM afterward
shows a `<script type="application/ld+json">` block with full schema.org
Product/Offer data (name, sku, image, brand, price, availability) — i.e.
exactly the same JSON-LD shape GenericHtmlProvider already knows how to
read; it just isn't in the response body until JavaScript runs.

WHAT THIS IS NOT: an anti-bot bypass. There is no CAPTCHA on these pages, no
login wall, no IP rotation, no fingerprint spoofing — btech.com's
robots.txt places no restriction on product or category paths and does not
block AI/scraper user-agents (checked 2026-08-09; contrast with 2B, whose
robots.txt explicitly disallows category/product-view crawling AND names
"anthropic-ai" — that site is deliberately NOT scanned by this app, see
discovery.py). This provider renders the page the same way any visitor's
browser would and self-identifies honestly via config.REQUEST_USER_AGENT,
same as GenericHtmlProvider. It is only "rendering", not "evading".

WHERE THIS CAN ACTUALLY RUN: Playwright + a real Chromium binary. That's a
~300MB download and meaningfully more CPU than PythonAnywhere's free tier
allows (100 CPU-seconds/day, no headless-browser support in practice) — so
this provider is not expected to work when the deployed app itself calls
it (e.g. via the "Run price check now" button on PythonAnywhere). It's
built to run inside the daily GitHub Actions job instead, which has a full
VM and installs Playwright fresh each run (see
.github/workflows/daily-scan.yml). If Playwright/Chromium simply isn't
available wherever this code runs, `fetch()` raises ProviderUnsupported —
same graceful "skip, don't crash" contract as every other provider.
"""
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from .base import PriceProvider, ProviderError, ProviderUnsupported
from .generic_html import (
    _extract_jsonld_price, _extract_meta_price, _extract_css_price,
    _robots_allowed, _throttle,
)
import config

RENDER_TIMEOUT_MS = 20000
RENDER_WAIT_MS = 1500  # settle time after networkidle for late JSON-LD injection


def render_html(url):
    """Fetch `url` in a real (headless) browser and return the fully
    rendered HTML. Raises ProviderUnsupported if Playwright/Chromium isn't
    installed in this environment, ProviderError on navigation failure."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ProviderUnsupported(
            "Playwright isn't installed here — JS-rendered listings only run in the "
            "GitHub Actions daily scan, not this environment. See README 'Always-updated scanning'."
        )

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                context = browser.new_context(user_agent=config.REQUEST_USER_AGENT)
                page = context.new_page()
                page.goto(url, timeout=RENDER_TIMEOUT_MS, wait_until="networkidle")
                page.wait_for_timeout(RENDER_WAIT_MS)
                html = page.content()
            finally:
                browser.close()
    except ProviderUnsupported:
        raise
    except Exception as e:  # noqa: BLE001 - any Playwright/browser failure -> clean provider error
        raise ProviderError(f"Rendering failed: {e}")

    return html


class RenderedHtmlProvider(PriceProvider):
    key = "rendered_html"
    display_name = "Rendered Page Fetch"
    tier = 3

    def fetch(self, url: str) -> dict:
        if not url:
            raise ProviderError("No URL configured for this listing.")
        if not _robots_allowed(url):
            raise ProviderUnsupported(f"robots.txt disallows fetching this URL: {url}")

        host = urlparse(url).netloc
        _throttle(host)

        html = render_html(url)
        soup = BeautifulSoup(html, "lxml")

        price, availability, title = _extract_jsonld_price(soup)
        if price is None:
            price = _extract_meta_price(soup)
        if price is None:
            price = _extract_css_price(soup)
        if title is None:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else None

        image_url = None
        og_image = soup.find("meta", property="og:image") or soup.find("meta", attrs={"name": "og:image"})
        if og_image and og_image.get("content"):
            image_url = og_image["content"].strip()

        if price is None:
            raise ProviderError(
                "Could not find a structured price even after rendering the page — "
                "the site's markup may have changed. Track this listing manually instead."
            )

        return self._result(url, retailer=urlparse(url).netloc, product=title,
                             current_price=price, availability=availability or "unknown",
                             image_url=image_url)

    def collect_listing_links(self, listing_url, link_contains):
        """Render a category/listing page and return the de-duplicated set
        of absolute product-detail URLs on it whose path contains
        `link_contains` (e.g. '/en/p/' for B.TECH). Used by discovery.py —
        never returns price/name data itself, just candidate URLs to visit
        individually through fetch() (so every extraction still goes
        through the same robots.txt check + honest self-identification)."""
        if not _robots_allowed(listing_url):
            raise ProviderUnsupported(f"robots.txt disallows fetching this URL: {listing_url}")
        host = urlparse(listing_url).netloc
        _throttle(host)

        html = render_html(listing_url)
        soup = BeautifulSoup(html, "lxml")
        origin = f"{urlparse(listing_url).scheme}://{host}"
        links = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if link_contains not in href:
                continue
            if href.startswith("http"):
                links.add(href.split("?")[0])
            elif href.startswith("/"):
                links.add((origin + href).split("?")[0])
        return sorted(links)
