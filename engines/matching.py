"""
Product matching / data-quality engine (spec section 21).

"LG refrigerator 400L" is not enough to prove two listings are the same
product. This module ranks how confident we are that a new item (e.g. a
pasted wishlist URL, or a newly discovered listing) refers to an EXISTING
product in the catalog, in priority order:
  1. exact SKU match
  2. exact normalized model-number match
  3. brand + fuzzy model match
  4. specification similarity
  5. uncertain (no confident match -> should be created as a new product,
     flagged for the user to confirm, never silently merged)
"""
import re

CONFIDENCE_ORDER = ["sku", "exact_model", "brand_model", "spec_similarity", "uncertain"]


def normalize_model(s):
    if not s:
        return ""
    return re.sub(r"[^A-Z0-9]", "", s.upper())


def normalize_brand(s):
    return (s or "").strip().lower()


def _model_similarity(a, b):
    """Cheap similarity: normalized longest-common-substring ratio. No
    external dependency (difflib is stdlib) keeps this deterministic and
    dependency-free."""
    import difflib
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def match_confidence(candidate, existing_product):
    """
    candidate / existing_product: dicts with optional keys
        sku, model, brand, specs (dict)

    Returns (confidence: str, score: float 0-1, reason: str)
    """
    c_sku = normalize_model(candidate.get("sku", ""))
    e_sku = normalize_model(existing_product.get("sku", ""))
    if c_sku and e_sku and c_sku == e_sku:
        return "sku", 1.0, "Exact SKU/manufacturer code match."

    c_model = normalize_model(candidate.get("model", ""))
    e_model = normalize_model(existing_product.get("model", ""))
    if c_model and e_model and c_model == e_model:
        return "exact_model", 0.95, "Exact model-number match."

    c_brand = normalize_brand(candidate.get("brand", ""))
    e_brand = normalize_brand(existing_product.get("brand", ""))
    if c_brand and e_brand and c_brand == e_brand and c_model and e_model:
        sim = _model_similarity(c_model, e_model)
        if sim >= 0.82:
            return "brand_model", round(0.6 + 0.3 * sim, 2), (
                f"Same brand and closely similar model string ({sim:.0%} match) — verify manually."
            )

    # Spec-similarity fallback: compare capacity string if present.
    c_cap = str(candidate.get("capacity", "")).strip().lower()
    e_cap = str(existing_product.get("capacity", "")).strip().lower()
    if c_brand and e_brand and c_brand == e_brand and c_cap and e_cap and c_cap == e_cap:
        return "spec_similarity", 0.4, (
            "Same brand and matching capacity/size only — model numbers differ or are unknown. "
            "Treat as a possible variant, not a confirmed match."
        )

    return "uncertain", 0.0, "No strong matching signal — will be treated as a new/distinct product."


def find_best_match(candidate, existing_products):
    """Rank existing_products by match confidence against candidate.
    Returns the best match dict {product, confidence, score, reason} or
    None if nothing scores above 'uncertain'."""
    best = None
    for product in existing_products:
        confidence, score, reason = match_confidence(candidate, product)
        if confidence == "uncertain":
            continue
        if best is None or score > best["score"]:
            best = {"product": product, "confidence": confidence, "score": score, "reason": reason}
    return best
