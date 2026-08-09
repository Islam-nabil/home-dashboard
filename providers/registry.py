"""Maps retailers.provider_key -> a PriceProvider instance."""
from .manual import ManualProvider
from .retailers import (
    BTechProvider, AmazonEgyptProvider, CarrefourEgyptProvider,
    NoonEgyptProvider, TwoBProvider, RayaShopProvider, OfficialBrandStoreProvider,
    JumiaEgyptProvider, RadioShackEgyptProvider, ZanussiEgyptProvider,
    CairoSalesStoreProvider,
)

_PROVIDERS = {
    "manual": ManualProvider(),
    "btech": BTechProvider(),
    "amazon_eg": AmazonEgyptProvider(),
    "carrefour_eg": CarrefourEgyptProvider(),
    "noon_eg": NoonEgyptProvider(),
    "twob": TwoBProvider(),
    "raya": RayaShopProvider(),
    "official_brand": OfficialBrandStoreProvider(),
    "jumia_eg": JumiaEgyptProvider(),
    "radioshack_eg": RadioShackEgyptProvider(),
    "zanussi_eg": ZanussiEgyptProvider(),
    "cairosales_eg": CairoSalesStoreProvider(),
    # NOTE: "generic_html" is intentionally NOT registered here. Any
    # retailer whose provider_key doesn't match a key in this dict falls
    # through to _DEFAULT (ManualProvider) below - so an unverified
    # retailer never silently gets automated fetching attempted against
    # it. Every retailer that should support automated fetching needs its
    # own verified entry in this dict, matching a class in retailers.py.
}

_DEFAULT = ManualProvider()


def get_provider(provider_key):
    return _PROVIDERS.get(provider_key, _DEFAULT)


def list_providers():
    return [{"key": k, "display_name": p.display_name, "tier": p.tier} for k, p in _PROVIDERS.items()]
