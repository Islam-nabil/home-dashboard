"""
"Always updated" — daily discovery of NEW products (spec section: the
2026-08-09 conversation that added this feature).

WHAT THIS DELIBERATELY DOES NOT DO: crawl every retailer's category pages
looking for new SKUs. That was the original ask, but two things made it
impossible to do honestly:
  1. 2B's robots.txt explicitly disallows crawling category/product-view
     paths, AND separately names "anthropic-ai" as disallowed site-wide.
     That's the site owner directly opting out of this kind of access —
     this app has stuck to "never bypass robots.txt" everywhere else, so
     2B is excluded from discovery_sources on principle, not capability.
  2. Most other Egyptian retailer storefronts (Noon, Amazon Egypt, ...)
     haven't been checked yet - discovery_sources starts EMPTY for them.
     Only add a discovery_sources row for a retailer whose robots.txt has
     actually been read and whose category pages actually contain
     `<a>` links to product detail pages once rendered.

WHAT THIS DOES DO, for every retailer that IS eligible (allow_category_scan
= 1 on its `retailers` row, currently just B.TECH — verified 2026-08-09,
see providers/retailers.py): render each configured category listing page,
collect product-detail links, skip anything already tracked, fetch full
details for the rest (same JSON-LD extraction path as a normal price
check), and file each as a `product_candidates` row — NEVER auto-added to
the real catalog. A human approves or dismisses each one on the "New
Finds" page. This mirrors the app's existing "never silently add/merge
data" rule for prices.

WHERE THIS RUNS: only where Playwright/Chromium is installed (the daily
GitHub Actions job — see .github/workflows/daily-scan.yml and
scripts/run_scan.py). Calling run_discovery() somewhere without Playwright
raises ProviderUnsupported per source and just skips it, same as any other
provider.
"""
import repository as repo
import wishlist as wishlist_module
import engines.matching as matching
from providers.rendered_html import RenderedHtmlProvider
from providers.base import ProviderError, ProviderUnsupported

MAX_NEW_LINKS_PER_SOURCE = 15  # politeness/budget cap - see module docstring


def run_discovery(source_row):
    """Scan one discovery_sources row. Returns a result dict; never raises
    (mirrors price_check.check_single_listing's contract)."""
    provider = RenderedHtmlProvider()
    result = {"source_id": source_row["id"], "category_key": source_row["category_key"],
              "retailer_key": source_row["retailer_key"], "found": 0, "new": 0,
              "candidates_created": 0, "status": "ok", "detail": ""}

    known_urls = repo.list_known_listing_urls(source_row["category_id"], source_row["retailer_id"])

    try:
        links = provider.collect_listing_links(source_row["listing_url"], link_contains="/en/p/")
    except ProviderUnsupported as e:
        result["status"] = "skipped_unsupported"
        result["detail"] = str(e)
        return result
    except ProviderError as e:
        result["status"] = "failed"
        result["detail"] = str(e)
        return result
    except Exception as e:  # noqa: BLE001 - one bad source must never kill the whole scan
        result["status"] = "failed"
        result["detail"] = f"Unexpected error: {e}"
        return result

    result["found"] = len(links)
    new_links = [l for l in links if l not in known_urls][:MAX_NEW_LINKS_PER_SOURCE]
    result["new"] = len(new_links)

    existing_products = repo.list_products(category_id=source_row["category_id"], with_pricing=False)

    for link in new_links:
        extracted = wishlist_module.extract_from_url(link, provider=provider)
        if not extracted.get("extracted"):
            continue  # one page failing to parse must never stop the rest

        candidate = {
            "brand": extracted.get("brand_guess") or "", "model": extracted.get("model_guess") or "",
        }
        best_match = matching.find_best_match(candidate, existing_products)
        if best_match is not None:
            # Confidently matches something we already track (e.g. the exact
            # same product under a different URL/offering_id) - not new,
            # skip rather than create a duplicate candidate.
            continue

        created = repo.create_candidate(
            category_id=source_row["category_id"], retailer_id=source_row["retailer_id"],
            full_name=extracted.get("full_name") or "(unnamed product)", url=link,
            brand_guess=extracted.get("brand_guess") or "", model_guess=extracted.get("model_guess") or "",
            price_egp=extracted.get("price"), image_url=extracted.get("image_url") or "",
        )
        if created:
            result["candidates_created"] += 1

    repo.mark_discovery_source_scanned(source_row["id"])
    return result


def run_all_discovery():
    sources = repo.list_discovery_sources()
    results = [run_discovery(s) for s in sources]
    return {
        "sources_checked": len(results),
        "total_new_candidates": sum(r["candidates_created"] for r in results),
        "details": results,
    }
