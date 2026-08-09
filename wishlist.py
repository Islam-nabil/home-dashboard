"""
Wishlist / manual product tracking (spec section 16).

`extract_from_url` attempts best-effort structured extraction (same tier-3
approach as providers/generic_html.py — JSON-LD / meta / common CSS) so a
pasted product URL can be pre-filled for the user to confirm/correct. If
extraction fails (very likely for JS-heavy sites, or in this sandbox where
outbound fetches to arbitrary hosts are blocked entirely), the caller gets
a clear `extracted: False` result and the UI falls back to a plain manual
entry form — this fallback path always works with zero dependency on
network access.
"""
from urllib.parse import urlparse

from providers.generic_html import GenericHtmlProvider, _extract_jsonld_price, _extract_meta_price, _extract_css_price
from providers.base import ProviderError, ProviderUnsupported
import engines.matching as matching


def guess_retailer_key(url):
    host = urlparse(url).netloc.lower()
    mapping = {
        "btech.com": "btech",
        "amazon.eg": "amazon_eg",
        "amazon.com": "amazon_eg",
        "carrefouregypt.com": "carrefour_eg",
        "noon.com": "noon_eg",
        "2b.com.eg": "twob",
        "rayashop.com": "raya",
    }
    for domain, key in mapping.items():
        if domain in host:
            return key
    return "other"


def extract_from_url(url):
    """Returns dict: {extracted: bool, retailer_key, brand_guess, model_guess,
    full_name, price, availability, image_url, reason_if_failed}."""
    provider = GenericHtmlProvider()
    retailer_key = guess_retailer_key(url)
    try:
        result = provider.fetch(url)
    except (ProviderError, ProviderUnsupported) as e:
        return {
            "extracted": False, "retailer_key": retailer_key, "url": url,
            "reason": str(e),
        }
    except Exception as e:  # noqa: BLE001
        return {"extracted": False, "retailer_key": retailer_key, "url": url, "reason": f"Unexpected error: {e}"}

    title = result.get("product") or ""
    brand_guess, model_guess = _guess_brand_model(title)

    return {
        "extracted": True,
        "retailer_key": retailer_key,
        "url": url,
        "full_name": title,
        "brand_guess": brand_guess,
        "model_guess": model_guess,
        "price": result.get("currentPrice"),
        "availability": result.get("availability"),
        "image_url": result.get("imageUrl"),
    }


_KNOWN_BRANDS = [
    "LG", "Samsung", "Toshiba", "Sharp", "Bosch", "Fresh", "Tornado", "Zanussi",
    "Beko", "Ariston", "Unionaire", "Carrier", "Midea", "Daikin", "Haier",
    "Hisense", "Universal", "La Germania",
]


def _guess_brand_model(title):
    if not title:
        return None, None
    brand = None
    for b in _KNOWN_BRANDS:
        if b.lower() in title.lower():
            brand = b
            break
    model = None
    tokens = title.replace(",", " ").split()
    for tok in tokens:
        # crude heuristic: a token with both letters and digits, length>=4,
        # is probably a model number (e.g. GN-H722HLHL, WW80T4040CX1AS)
        if len(tok) >= 4 and any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            model = tok.strip(".,()")
            break
    return brand, model


def find_matching_products(candidate, existing_products):
    return matching.find_best_match(candidate, existing_products)
