#!/usr/bin/env python3
"""
The "always updated" daily scan — meant to run in the GitHub Actions job
(.github/workflows/daily-scan.yml), NOT on PythonAnywhere. It needs a real
Chromium browser (Playwright) for B.TECH's JS-rendered pages, and
PythonAnywhere's free tier can't run one (~300MB browser binary, tiny
CPU-second budget). GitHub Actions gives a full disposable VM for free, so
that's where the actual scanning happens; this app's own live site is only
ever *talked to* over its normal HTTPS API, the same way a browser would.

What it does, each run:
  1. GET  <DASHBOARD_BASE_URL>/api/scan/targets  — ask the live site what to check
     (which listings need a JS-rendered price check, and which category
     pages to scan for new products — see discovery.py for what's excluded
     and why).
  2. For each price target: render the page, extract the price
     (providers/rendered_html.py — same JSON-LD extraction the rest of the
     app already uses).
  3. For each discovery target: render the category page, collect
     product-detail links not already known, fetch full details for a
     bounded number of new ones.
  4. POST everything to <DASHBOARD_BASE_URL>/api/scan/ingest in one batch.
     The live site applies price updates through its normal alert-
     evaluation path and files new products as *candidates* — nothing is
     ever added to the real catalog without a human approving it on the
     "New Finds" page.

2B is intentionally not part of any of this — its own product pages are
priced automatically by PythonAnywhere's regular price-check (plain HTTP
works fine there), and its category pages are excluded from discovery
entirely because 2B's robots.txt disallows crawling them. See
discovery.py's module docstring.

Required environment variables (set as GitHub Actions secrets):
  DASHBOARD_BASE_URL     e.g. https://islahmed.pythonanywhere.com
  BASIC_AUTH_USERNAME    same credentials the site's Basic Auth prompt uses
  BASIC_AUTH_PASSWORD

Run locally to test (needs `pip install playwright && playwright install
chromium` first, and normal outbound internet — this sandbox has neither):
  DASHBOARD_BASE_URL=http://127.0.0.1:5000 BASIC_AUTH_USERNAME=... \\
    BASIC_AUTH_PASSWORD=... python scripts/run_scan.py
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests

from providers.rendered_html import RenderedHtmlProvider
from providers.base import ProviderError, ProviderUnsupported

MAX_NEW_PER_SOURCE = 15


def _base_url():
    url = os.environ.get("DASHBOARD_BASE_URL", "").rstrip("/")
    if not url:
        print("DASHBOARD_BASE_URL is not set — nothing to scan against. Exiting.")
        sys.exit(1)
    return url


def _auth():
    user = os.environ.get("BASIC_AUTH_USERNAME", "")
    pw = os.environ.get("BASIC_AUTH_PASSWORD", "")
    return (user, pw) if user else None


def fetch_targets(base_url, auth):
    resp = requests.get(f"{base_url}/api/scan/targets", auth=auth, timeout=30)
    resp.raise_for_status()
    return resp.json()


def run_price_targets(price_targets):
    provider = RenderedHtmlProvider()
    results = []
    for t in price_targets:
        try:
            fetched = provider.fetch(t["url"])
            price = fetched.get("currentPrice")
            if price is None:
                print(f"  [skip] listing {t['listing_id']}: no price found")
                continue
            results.append({
                "listing_id": t["listing_id"], "price": price,
                "availability": fetched.get("availability", "unknown"),
            })
            print(f"  [ok] listing {t['listing_id']}: {price} EGP")
        except ProviderUnsupported as e:
            print(f"  [unsupported] listing {t['listing_id']}: {e}")
        except ProviderError as e:
            print(f"  [failed] listing {t['listing_id']}: {e}")
        except Exception as e:  # noqa: BLE001 - one bad listing must never kill the run
            print(f"  [error] listing {t['listing_id']}: {e}")
    return results


def run_discovery_targets(discovery_targets):
    provider = RenderedHtmlProvider()
    candidates = []
    for target in discovery_targets:
        known = set(target.get("known_urls", []))
        print(f"Scanning {target['category_key']} on {target['retailer_key']}: {target['listing_url']}")
        try:
            links = provider.collect_listing_links(target["listing_url"], link_contains="/en/p/")
        except (ProviderError, ProviderUnsupported) as e:
            print(f"  [failed] {e}")
            continue
        except Exception as e:  # noqa: BLE001
            print(f"  [error] {e}")
            continue

        new_links = [l for l in links if l not in known][:MAX_NEW_PER_SOURCE]
        print(f"  found {len(links)} product links, {len(new_links)} not already tracked")

        for link in new_links:
            try:
                fetched = provider.fetch(link)
            except (ProviderError, ProviderUnsupported) as e:
                print(f"    [skip] {link}: {e}")
                continue
            except Exception as e:  # noqa: BLE001
                print(f"    [error] {link}: {e}")
                continue
            if not fetched.get("product"):
                continue
            brand_guess, model_guess = _guess_brand_model(fetched.get("product") or "")
            candidates.append({
                "source_id": target["source_id"], "full_name": fetched.get("product"),
                "url": link, "brand_guess": brand_guess, "model_guess": model_guess,
                "price_egp": fetched.get("currentPrice"), "image_url": fetched.get("imageUrl") or "",
            })
    return candidates


def _guess_brand_model(title):
    # Same lightweight heuristic wishlist.py uses for pasted URLs - kept as
    # a local copy here since this script runs standalone (no Flask app
    # context, no DB) inside a GitHub Actions VM.
    known_brands = [
        "LG", "Samsung", "Toshiba", "Sharp", "Bosch", "Fresh", "Tornado", "Zanussi",
        "Beko", "Ariston", "Unionaire", "Carrier", "Midea", "Daikin", "Haier",
        "Hisense", "Universal", "La Germania",
    ]
    brand = next((b for b in known_brands if b.lower() in title.lower()), None)
    model = None
    for tok in title.replace(",", " ").split():
        if len(tok) >= 4 and any(c.isdigit() for c in tok) and any(c.isalpha() for c in tok):
            model = tok.strip(".,()")
            break
    return brand, model


def main():
    base_url = _base_url()
    auth = _auth()

    print(f"Fetching scan targets from {base_url} ...")
    targets = fetch_targets(base_url, auth)
    print(f"  {len(targets['price_targets'])} price targets, {len(targets['discovery_targets'])} discovery sources")

    print("Running price checks (JS-rendered listings)...")
    price_results = run_price_targets(targets["price_targets"])

    print("Running discovery scan (new products)...")
    candidates = run_discovery_targets(targets["discovery_targets"])

    print(f"Posting results: {len(price_results)} price updates, {len(candidates)} candidates ...")
    resp = requests.post(
        f"{base_url}/api/scan/ingest", auth=auth, timeout=60,
        json={"price_results": price_results, "candidates": candidates},
    )
    resp.raise_for_status()
    print(json.dumps(resp.json(), indent=2))


if __name__ == "__main__":
    main()
