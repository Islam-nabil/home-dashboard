"""Maps retailers.provider_key -> a PriceProvider instance."""
from .manual import ManualProvider
from .retailers import (
    BTechProvider, AmazonEgyptProvider, CarrefourEgyptProvider,
    NoonEgyptProvider, TwoBProvider, RayaShopProvider, OfficialBrandStoreProvider,
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
}

_DEFAULT = ManualProvider()


def get_provider(provider_key):
    return _PROVIDERS.get(provider_key, _DEFAULT)


def list_providers():
    return [{"key": k, "display_name": p.display_name, "tier": p.tier} for k, p in _PROVIDERS.items()]
