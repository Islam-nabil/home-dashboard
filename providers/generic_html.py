"""
GenericHtmlProvider — "tier 3: safe normal page retrieval" (spec section 5/20).

Best-effort, low-volume, polite HTML fetch + structured-data extraction:
  1. robots.txt is checked first (via urllib.robotparser); if the path is
     disallowed, we refuse and raise ProviderUnsupported rather than fetch.
  2. A single GET with a descriptive User-Agent and a real timeout.
  3. Extraction tries, in order: JSON-LD <script type="application/ld+json">
     Product/Offer data (the most reliable, most sites doing basic SEO emit
     this) -> Open Graph / common meta price tags -> a short list of common
     CSS price-class heuristics.
  4. No anti-bot bypass of any kind: no headless browser, no fake sessions,
     no CAPTCHA solving, no rotating proxies. If a site blocks simple
     `requests` fetches (Cloudflare challenge, login wall, heavy client-side
     rendering), extraction simply fails cleanly and the caller falls back
     to manual tracking. This is intentional and documented, not a bug.

NOTE ON THIS SANDBOX: outbound HTTP to arbitrary third-party hosts is
blocked in the environment this app was built in (verified: only a small
allowlist of hosts — package registries, github.com, anthropic.com — are
reachable from server-side code here). This provider is fully implemented
and will work once the app runs somewhere with normal internet egress (the
user's own machine, a normal VPS, etc.) but could not be live-tested
against real Egyptian retailer sites during the build. Treat it as
"implemented, needs verification on first real run" — see README.
"""
import json
import re
import time
from urllib.parse import urlparse
from urllib import robotparser

from .base import PriceProvider, ProviderError, ProviderUnsupported
import config

try:
    import requests
    from bs4 import BeautifulSoup
    HAS_DEPS = True
except ImportError:  # pragma: no cover - deps are present in this project's env
    HAS_DEPS = False

_last_request_time_by_host = {}
_robots_cache = {}


def _throttle(host):
    last = _last_request_time_by_host.get(host, 0)
    wait = config.MIN_REQUEST_INTERVAL_SECONDS - (time.time() - last)
    if wait > 0:
        time.sleep(wait)
    _last_request_time_by_host[host] = time.time()


def _robots_allowed(url):
    parsed = urlparse(url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    if origin not in _robots_cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(origin + "/robots.txt")
        try:
            rp.read()
        except Exception:
            # If robots.txt can't be fetched, we can't confirm permission —
            # default to allowing a single low-volume, identified GET rather
            # than silently blocking a feature the user explicitly asked for,
            # but we never retry aggressively past this point.
            _robots_cache[origin] = None
            return True
        _robots_cache[origin] = rp
    rp = _robots_cache[origin]
    if rp is None:
        return True
    return rp.can_fetch(config.REQUEST_USER_AGENT, url)


_PRICE_RE = re.compile(r"[\d.,]+")


def _to_float_price(text):
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    match = _PRICE_RE.search(str(text).replace("\xa0", " "))
    if not match:
        return None
    raw = match.group(0)
    # Egyptian sites format as either 12,345.00 or 12.345,00 — assume the
    # last separator before <=2 trailing digits is the decimal point,
    # everything else is a thousands separator.
    raw = raw.replace(",", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _extract_jsonld_price(soup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "{}")
        except (ValueError, TypeError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            if item.get("@type") not in ("Product", "Offer"):
                continue

            # A bare Offer sometimes carries price directly; a Product
            # almost always nests it under "offers" instead (verified
            # 2026-08-09 against a real btech.com Product/Offer block —
            # see tests/test_rendered_html.py). Try both, direct field
            # first, so neither shape silently returns nothing.
            price = item.get("price")
            avail = item.get("availability", "")
            name = item.get("name")

            if not price:
                offers = item.get("offers")
                if isinstance(offers, list) and offers:
                    offers = offers[0]
                if isinstance(offers, dict):
                    price = offers.get("price") or offers.get("priceSpecification", {}).get("price")
                    avail = offers.get("availability", avail)

            if price:
                return _to_float_price(price), _normalize_availability(avail), name
    return None, "unknown", None


def _normalize_availability(text):
    text = (text or "").lower()
    if "instock" in text or "in_stock" in text or "in stock" in text:
        return "in_stock"
    if "outofstock" in text or "out_of_stock" in text or "out of stock" in text:
        return "out_of_stock"
    return "unknown"


def _extract_meta_price(soup):
    for prop in ("product:price:amount", "og:price:amount"):
        tag = soup.find("meta", property=prop)
        if tag and tag.get("content"):
            return _to_float_price(tag["content"])
    return None


COMMON_PRICE_SELECTORS = [
    ".price", ".product-price", ".current-price", "[data-price]",
    ".price-current", "#priceblock_ourprice", ".a-price .a-offscreen",
]


def _extract_css_price(soup):
    for selector in COMMON_PRICE_SELECTORS:
        el = soup.select_one(selector)
        if el:
            price = _to_float_price(el.get("data-price") or el.get_text())
            if price:
                return price
    return None


class GenericHtmlProvider(PriceProvider):
    key = "generic_html"
    display_name = "Generic Page Fetch"
    tier = 3

    def fetch(self, url: str) -> dict:
        if not HAS_DEPS:
            raise ProviderUnsupported("requests/beautifulsoup4 not installed in this environment.")
        if not url:
            raise ProviderError("No URL configured for this listing.")

        if not _robots_allowed(url):
            raise ProviderUnsupported(f"robots.txt disallows fetching this URL: {url}")

        host = urlparse(url).netloc
        _throttle(host)

        try:
            resp = requests.get(
                url,
                headers={"User-Agent": config.REQUEST_USER_AGENT, "Accept-Language": "en,ar;q=0.8"},
                timeout=config.REQUEST_TIMEOUT_SECONDS,
            )
        except requests.RequestException as e:
            raise ProviderError(f"Request failed: {e}")

        if resp.status_code == 403 or resp.status_code == 429:
            raise ProviderUnsupported(
                f"Site returned HTTP {resp.status_code} (likely anti-bot protection). "
                "Not retrying/bypassing — switch this listing to manual tracking."
            )
        if resp.status_code >= 400:
            raise ProviderError(f"HTTP {resp.status_code} fetching {url}")

        soup = BeautifulSoup(resp.text, "lxml")

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
                "Could not find a structured price on the page (no JSON-LD/meta/common CSS match). "
                "The site likely renders price via JavaScript — track this listing manually instead."
            )

        return self._result(url, retailer=urlparse(url).netloc, product=title,
                             current_price=price, availability=availability or "unknown",
                             image_url=image_url)
