"""
JSON API. Kept as one blueprint file (rather than one-file-per-resource)
since this is a single-user personal app — the split-by-concern already
lives in engines/, providers/, repository.py, price_check.py, assistant.py,
wishlist.py; this file is just the thin HTTP layer over them.
"""
from flask import Blueprint, request, jsonify

import db
import config
import repository as repo
import price_check
import assistant as assistant_module
import wishlist as wishlist_module
from engines import matching

api_bp = Blueprint("api", __name__)


def _bad_request(msg):
    return jsonify({"error": msg}), 400


def _not_found(msg="Not found"):
    return jsonify({"error": msg}), 404


# ============================= Dashboard =====================================

@api_bp.get("/dashboard")
def api_dashboard():
    return jsonify(repo.get_dashboard())


# ============================= Categories =====================================

@api_bp.get("/categories")
def api_list_categories():
    return jsonify(repo.list_categories())


@api_bp.post("/categories")
def api_create_category():
    data = request.get_json(force=True)
    if not data.get("key") or not data.get("name"):
        return _bad_request("key and name are required")
    cat_id = repo.create_category(data)
    return jsonify(repo.get_category(cat_id)), 201


@api_bp.put("/categories/<int:category_id>")
def api_update_category(category_id):
    if repo.get_category(category_id) is None:
        return _not_found()
    repo.update_category(category_id, request.get_json(force=True))
    return jsonify(repo.get_category(category_id))


@api_bp.delete("/categories/<int:category_id>")
def api_delete_category(category_id):
    repo.delete_category(category_id)
    return jsonify({"ok": True})


@api_bp.post("/categories/reorder")
def api_reorder_categories():
    order = request.get_json(force=True).get("order", [])
    repo.reorder_categories(order)
    return jsonify(repo.list_categories())


# ============================= Retailers =====================================

@api_bp.get("/retailers")
def api_list_retailers():
    return jsonify(repo.list_retailers())


@api_bp.post("/retailers")
def api_create_retailer():
    data = request.get_json(force=True)
    if not data.get("key") or not data.get("name"):
        return _bad_request("key and name are required")
    retailer = repo.get_or_create_retailer(
        data["key"], name=data["name"], base_url=data.get("base_url", ""),
        provider_key=data.get("provider_key", "manual"),
        credibility_score=data.get("credibility_score", 70), notes=data.get("notes", ""),
    )
    return jsonify(retailer), 201


# ============================= Products =====================================

@api_bp.get("/products")
def api_list_products():
    category_id = request.args.get("category_id", type=int)
    status = request.args.get("status")
    return jsonify(repo.list_products(category_id=category_id, status=status))


@api_bp.get("/products/<int:product_id>")
def api_get_product(product_id):
    product = repo.get_product(product_id)
    if product is None:
        return _not_found()
    return jsonify(product)


@api_bp.post("/products")
def api_create_product():
    data = request.get_json(force=True)
    if not data.get("category_id") or not data.get("brand") or not data.get("model"):
        return _bad_request("category_id, brand, and model are required")
    product_id = repo.create_product(data)
    repo.recompute_and_store_ai_score(product_id)
    return jsonify(repo.get_product(product_id)), 201


@api_bp.put("/products/<int:product_id>")
def api_update_product(product_id):
    if repo.get_product(product_id, with_pricing=False) is None:
        return _not_found()
    repo.update_product(product_id, request.get_json(force=True))
    repo.recompute_and_store_ai_score(product_id)
    return jsonify(repo.get_product(product_id))


@api_bp.delete("/products/<int:product_id>")
def api_delete_product(product_id):
    repo.delete_product(product_id)
    return jsonify({"ok": True})


@api_bp.get("/products/<int:product_id>/recommendation")
def api_product_recommendation(product_id):
    rec = repo.get_recommendation_for_product(product_id)
    if rec is None:
        return _not_found()
    return jsonify(rec)


@api_bp.get("/products/<int:product_id>/price-history")
def api_price_history(product_id):
    days = request.args.get("days", type=int)
    return jsonify(repo.get_price_history(product_id, days=days))


@api_bp.post("/products/<int:product_id>/price")
def api_add_price(product_id):
    """Manual price entry — the always-available fallback (spec section 6)."""
    data = request.get_json(force=True)
    retailer_key = data.get("retailer_key")
    price_egp = data.get("price_egp")
    if not retailer_key or price_egp is None:
        return _bad_request("retailer_key and price_egp are required")

    retailer = repo.get_or_create_retailer(retailer_key, name=data.get("retailer_name", retailer_key))

    listings = repo.get_product_listings(product_id)
    listing = next((l for l in listings if l["retailer_id"] == retailer["id"]), None)
    if listing is None:
        listing_id = repo.add_listing(product_id, retailer["id"], url=data.get("url", ""),
                                       match_confidence="manual")
    else:
        listing_id = listing["id"]
        if data.get("url"):
            db.update("product_listings", listing_id, {"url": data["url"]})

    repo.add_price_observation(
        listing_id, price_egp, availability=data.get("availability", "in_stock"),
        source="manual", is_verified=1 if data.get("is_verified", True) else 0,
    )
    if data.get("source_url"):
        repo.add_research_source(product_id, data["source_url"], retailer["name"], confidence="verified",
                                  listing_id=listing_id)

    # Run alert evaluation immediately so the UI reflects it without waiting
    # for the next scheduled check.
    price_check._evaluate_and_alert(product_id)  # noqa: SLF001 - internal reuse within same app

    return jsonify(repo.get_product(product_id)), 201


# ============================= Purchases =====================================

@api_bp.get("/purchases")
def api_list_purchases():
    return jsonify(repo.list_purchases())


@api_bp.post("/purchases")
def api_create_purchase():
    data = request.get_json(force=True)
    if not data.get("product_id") or data.get("purchase_price_egp") is None:
        return _bad_request("product_id and purchase_price_egp are required")
    if not data.get("retailer_id") and data.get("retailer_key"):
        retailer = repo.get_or_create_retailer(data["retailer_key"], name=data.get("retailer_name", data["retailer_key"]))
        data["retailer_id"] = retailer["id"]
    purchase_id = repo.create_purchase(data)
    return jsonify({"id": purchase_id, "product": repo.get_product(data["product_id"])}), 201


# ============================= Alerts =====================================

@api_bp.get("/alerts")
def api_list_alerts():
    unread_only = request.args.get("unread_only", "false").lower() == "true"
    return jsonify(repo.list_alerts(unread_only=unread_only))


@api_bp.post("/alerts/<int:alert_id>/read")
def api_mark_alert_read(alert_id):
    repo.mark_alert_read(alert_id)
    return jsonify({"ok": True})


# ============================= What-if simulator =====================================

@api_bp.post("/whatif")
def api_whatif():
    data = request.get_json(force=True)
    hypothetical = data.get("purchases", [])
    if not hypothetical:
        return _bad_request("purchases: [{product_id, price_egp}] is required")
    return jsonify(repo.simulate_what_if(hypothetical))


# ============================= Wishlist / manual tracking =====================================

@api_bp.post("/wishlist/extract")
def api_wishlist_extract():
    data = request.get_json(force=True)
    url = data.get("url")
    if not url:
        return _bad_request("url is required")
    result = wishlist_module.extract_from_url(url)

    if result.get("extracted"):
        existing = repo.list_products(with_pricing=False)
        candidate = {
            "brand": result.get("brand_guess") or "", "model": result.get("model_guess") or "",
            "sku": "", "capacity": "",
        }
        best_match = wishlist_module.find_matching_products(candidate, existing)
        result["possible_existing_match"] = best_match
    return jsonify(result)


@api_bp.post("/wishlist/confirm")
def api_wishlist_confirm():
    """Create (or attach a listing to an existing) product from confirmed
    wishlist data — works whether extraction succeeded or the user filled
    the form manually."""
    data = request.get_json(force=True)
    retailer_key = data.get("retailer_key", "other")
    retailer = repo.get_or_create_retailer(retailer_key, name=data.get("retailer_name", retailer_key))

    product_id = data.get("existing_product_id")
    if not product_id:
        if not data.get("category_id"):
            return _bad_request("category_id is required to create a new product")
        product_id = repo.create_product({
            "category_id": data["category_id"], "brand": data.get("brand", "Unknown"),
            "model": data.get("model", "Unknown"), "full_name": data.get("full_name", ""),
            "capacity": data.get("capacity", ""), "target_buy_price_egp": data.get("target_buy_price_egp"),
            "image_url": data.get("image_url", ""),
            "purchase_status": "shortlisted", "is_demo_data": 0,
        })

    listing_id = repo.add_listing(product_id, retailer["id"], url=data.get("url", ""),
                                   match_confidence=data.get("match_confidence", "uncertain"))
    if data.get("price_egp") is not None:
        repo.add_price_observation(listing_id, data["price_egp"], availability=data.get("availability", "in_stock"),
                                    source="manual", is_verified=1)
    if data.get("url"):
        repo.add_research_source(product_id, data["url"], retailer["name"], confidence="verified", listing_id=listing_id)

    return jsonify(repo.get_product(product_id)), 201


# ============================= Assistant =====================================

@api_bp.post("/assistant")
def api_assistant():
    data = request.get_json(force=True)
    question = data.get("question", "").strip()
    if not question:
        return _bad_request("question is required")
    return jsonify(assistant_module.answer_question(question))


# ============================= Price check =====================================

@api_bp.post("/price-check/run")
def api_run_price_check():
    data = request.get_json(silent=True) or {}
    product_id = data.get("product_id")
    result = price_check.run_price_check(product_id=product_id)
    return jsonify(result)


@api_bp.get("/price-check/log")
def api_price_check_log():
    limit = request.args.get("limit", 50, type=int)
    rows = db.query_all("SELECT * FROM price_check_log ORDER BY ran_at DESC LIMIT ?", (limit,))
    return jsonify(rows)


# ============================= Settings =====================================

@api_bp.get("/settings")
def api_get_settings():
    return jsonify({
        "total_budget_egp": db.get_setting("total_budget_egp", config.TOTAL_BUDGET_EGP),
        "price_check_frequency_hours": db.get_setting("price_check_frequency_hours", config.PRICE_CHECK_FREQUENCY_HOURS),
        "deal_score_thresholds": db.get_setting("deal_score_thresholds", config.DEAL_SCORE_THRESHOLDS),
        "notification_channels": db.get_setting("notification_channels", config.NOTIFICATION_CHANNELS),
    })


@api_bp.put("/settings")
def api_update_settings():
    data = request.get_json(force=True)
    for key in ("total_budget_egp", "price_check_frequency_hours", "deal_score_thresholds", "notification_channels"):
        if key in data:
            db.set_setting(key, data[key])
    return jsonify({"ok": True})
