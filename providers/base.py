"""
PriceProvider interface (spec section 20).

Every retailer adapter implements `fetch(url) -> dict` returning a
normalized result:
    {
        "retailer": str,
        "product": str | None,      # title text found on the page, if any
        "currentPrice": float | None,
        "availability": "in_stock" | "out_of_stock" | "unknown",
        "url": str,
        "retrievedAt": iso8601 str,
    }

Or raises ProviderError with a human-readable reason. One retailer's site
changing its HTML must only break that one adapter, never the whole price
check run — price_check.py always wraps fetch() in try/except and logs
failures to price_check_log instead of crashing.
"""
from abc import ABC, abstractmethod


class ProviderError(Exception):
    pass


class ProviderUnsupported(ProviderError):
    """Raised by adapters that intentionally do not support automated
    fetching (e.g. sites requiring auth, heavy JS rendering, or that
    disallow it via robots.txt) — signals "use manual tracking" rather
    than a transient failure."""
    pass


class PriceProvider(ABC):
    key = "base"
    display_name = "Base Provider"
    tier = 5  # 1=official API, 2=structured public data, 3=page retrieval,
              # 4=search-based, 5=manual

    @abstractmethod
    def fetch(self, url: str) -> dict:
        raise NotImplementedError

    def _result(self, url, retailer=None, product=None, current_price=None, availability="unknown"):
        import db
        return {
            "retailer": retailer or self.display_name,
            "product": product,
            "currentPrice": current_price,
            "availability": availability,
            "url": url,
            "retrievedAt": db.now_iso(),
        }
