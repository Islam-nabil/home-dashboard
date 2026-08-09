"""
Scheduled Price Monitoring subsystem (spec section 20).

run_price_check() implements the pipeline:
  1. load watched (active) product listings
  2. retrieve current price where permitted (via providers/registry.py)
  3. normalize the price
  4. compare against the previous observation
  5. store the new observation
  6. compute discount / update historical low (implicitly, via repository
     aggregation reading straight from price_observations)
  7. recalculate Deal Score
  8. evaluate alert conditions
  9. create alerts (deduplicated)
  10. log notifications (in-app; other channels are stubbed, see notify.py)
  11. log every attempt (success or failure) to price_check_log so failures
      are visible instead of silent

This module has NO Flask dependency and can be run either from the API
(`POST /api/price-check/run`) or standalone via scripts/run_price_check.py
(suitable for a real cron job once deployed somewhere with normal internet
access — see README "Scheduled tasks" section for why this sandbox itself
can't run a persistent background cron).
"""
import db
import repository as repo
import config
from engines import deal_score as deal_score_engine, alerts as alerts_engine, scoring
from providers.registry import get_provider
from providers.base import ProviderError, ProviderUnsupported
import notify


def _log(listing_id, status, detail=""):
    db.insert("price_check_log", {
        "listing_id": listing_id, "ran_at": db.now_iso(), "status": status, "detail": detail,
    })


def check_single_listing(listing_row):
    """Fetch + store one listing's price. Returns a result dict; never
    raises (all provider errors are caught and logged)."""
    listing_id = listing_row["id"]
    retailer = db.query_one("SELECT * FROM retailers WHERE id=?", (listing_row["retailer_id"],))
    if retailer is None:
        _log(listing_id, "failed", "Retailer not found")
        return {"listing_id": listing_id, "status": "failed", "detail": "Retailer not found"}

    provider = get_provider(retailer["provider_key"])

    if provider.key == "manual" or not listing_row.get("url"):
        _log(listing_id, "skipped_unsupported", "Manual-tracked listing — update its price via the UI.")
        return {"listing_id": listing_id, "status": "skipped_unsupported"}

    try:
        result = provider.fetch(listing_row["url"])
    except ProviderUnsupported as e:
        _log(listing_id, "skipped_unsupported", str(e))
        return {"listing_id": listing_id, "status": "skipped_unsupported", "detail": str(e)}
    except ProviderError as e:
        _log(listing_id, "failed", str(e))
        return {"listing_id": listing_id, "status": "failed", "detail": str(e)}
    except Exception as e:  # noqa: BLE001 - a single bad listing must never kill the whole run
        _log(listing_id, "failed", f"Unexpected error: {e}")
        return {"listing_id": listing_id, "status": "failed", "detail": f"Unexpected error: {e}"}

    price = result.get("currentPrice")
    if price is None:
        _log(listing_id, "failed", "Provider returned no price")
        return {"listing_id": listing_id, "status": "failed", "detail": "Provider returned no price"}

    record_price_result(listing_id, price, result.get("availability", "unknown"), source=provider.key)
    _log(listing_id, "ok", f"{price} EGP, {result.get('availability')}")
    return {"listing_id": listing_id, "status": "ok", "price": price}


def record_price_result(listing_id, price, availability, source="manual"):
    """Store one fetched price observation. Split out from check_single_listing
    so callers that already fetched a price elsewhere (e.g. the daily GitHub
    Actions scan, which runs Playwright outside this app entirely and POSTs
    its results to /api/scan/ingest) go through the exact same storage path —
    never a second, slightly-different code path for 'externally fetched'
    prices."""
    repo.add_price_observation(
        listing_id, price, availability=availability, source=source, is_verified=1, observed_at=db.now_iso(),
    )


def evaluate_and_alert(product_id, previous_availability=None):
    return _evaluate_and_alert(product_id, previous_availability=previous_availability)


def _evaluate_and_alert(product_id, previous_availability=None):
    product = repo.get_product(product_id)
    if product is None:
        return []
    category = product["category"]
    pricing = product["pricing"]
    deal = product["deal_score"]

    triggered = alerts_engine.evaluate_conditions(product, category, pricing, deal, previous_availability)
    created = []
    for t in triggered:
        last = repo.get_last_alert(product_id, t["alert_type"])
        if not alerts_engine.should_alert(t["alert_type"], t["price"], last):
            continue
        alert_id = repo.create_alert(
            product_id, pricing.get("best_listing_id"), t["alert_type"], t["message"],
            t["price"], t.get("deal_score"),
            recommendation_text=(repo.get_recommendation_for_product(product_id) or {}).get("explanation", ""),
        )
        if alert_id:
            notify.send(alert_id)
            created.append(alert_id)
    return created


def run_price_check(product_id=None):
    """Run the full pipeline. If product_id is given, only that product's
    listings are checked (used by the manual 'refresh this product' button);
    otherwise every active listing is checked."""
    sql = """
        SELECT pl.* FROM product_listings pl
        WHERE pl.is_active=1
    """
    params = ()
    if product_id:
        sql += " AND pl.product_id=?"
        params = (product_id,)
    listings = db.query_all(sql, params)

    results = {"checked": 0, "updated": 0, "skipped": 0, "failed": 0, "alerts_created": 0, "details": []}

    touched_products = set()
    for listing in listings:
        prior_pricing = repo.get_product_pricing(listing["product_id"])
        r = check_single_listing(listing)
        results["checked"] += 1
        results["details"].append(r)
        if r["status"] == "ok":
            results["updated"] += 1
            touched_products.add((listing["product_id"], prior_pricing.get("availability")))
        elif r["status"] == "failed":
            results["failed"] += 1
        else:
            results["skipped"] += 1

    for pid, prior_availability in touched_products:
        created = _evaluate_and_alert(pid, previous_availability=prior_availability)
        results["alerts_created"] += len(created)

    return results
