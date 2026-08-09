"""
Repository layer: turns raw SQLite rows into the shapes the engines/*.py
pure functions expect, and turns engine results back into API-ready dicts.
This is the only layer that talks to both db.py and engines/*.
"""
import json
import statistics
from datetime import datetime, timedelta, timezone

import db
import config
from engines import scoring, deal_score as deal_score_engine, budget as budget_engine, \
    recommendation as recommendation_engine, matching as matching_engine, alerts as alerts_engine


# ============================= Categories =====================================

def list_categories():
    rows = db.query_all("SELECT * FROM categories WHERE is_archived=0 ORDER BY sort_order, priority_level, id")
    return [db.decode_json_fields(r) for r in rows]


def get_category(category_id):
    row = db.query_one("SELECT * FROM categories WHERE id=?", (category_id,))
    return db.decode_json_fields(row)


def get_category_by_key(key):
    row = db.query_one("SELECT * FROM categories WHERE key=?", (key,))
    return db.decode_json_fields(row)


def create_category(data):
    now = db.now_iso()
    fields = {
        "key": data["key"],
        "name": data["name"],
        "icon": data.get("icon", ""),
        "priority_level": int(data.get("priority_level", 2)),
        "sort_order": int(data.get("sort_order", 999)),
        "target_budget_egp": float(data.get("target_budget_egp", 0)),
        "must_have_features": json.dumps(data.get("must_have_features", [])),
        "notes": data.get("notes", ""),
        "scoring_weights": json.dumps(data.get("scoring_weights", {})),
        "scoring_dimensions": json.dumps(data.get("scoring_dimensions", [])),
        "created_at": now, "updated_at": now,
    }
    return db.insert("categories", fields)


def update_category(category_id, data):
    allowed = ["name", "icon", "priority_level", "sort_order", "target_budget_egp",
               "must_have_features", "notes", "scoring_weights", "scoring_dimensions", "is_archived"]
    fields = {}
    for k in allowed:
        if k in data:
            v = data[k]
            if k in ("must_have_features", "scoring_weights", "scoring_dimensions"):
                v = json.dumps(v)
            fields[k] = v
    fields["updated_at"] = db.now_iso()
    db.update("categories", category_id, fields)


def delete_category(category_id):
    db.delete("categories", category_id)


def reorder_categories(ordered_ids):
    for idx, cat_id in enumerate(ordered_ids):
        db.update("categories", cat_id, {"sort_order": idx, "updated_at": db.now_iso()})


# ============================= Retailers =====================================

def list_retailers():
    return db.query_all("SELECT * FROM retailers ORDER BY name")


def get_retailer(retailer_id):
    return db.query_one("SELECT * FROM retailers WHERE id=?", (retailer_id,))


def get_or_create_retailer(key, name=None, base_url="", provider_key="manual", credibility_score=70, notes=""):
    row = db.query_one("SELECT * FROM retailers WHERE key=?", (key,))
    if row:
        return dict(row)
    new_id = db.insert("retailers", {
        "key": key, "name": name or key, "base_url": base_url,
        "provider_key": provider_key, "credibility_score": credibility_score, "notes": notes,
    })
    return db.query_one("SELECT * FROM retailers WHERE id=?", (new_id,))


# ============================= Pricing helpers =====================================

def _parse_ts(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return datetime.min


def get_product_listings(product_id):
    return db.query_all("""
        SELECT pl.*, r.name as retailer_name, r.key as retailer_key,
               r.credibility_score as retailer_credibility
        FROM product_listings pl JOIN retailers r ON r.id = pl.retailer_id
        WHERE pl.product_id=? ORDER BY pl.id
    """, (product_id,))


def get_listing_observations(listing_id, limit=None):
    sql = "SELECT * FROM price_observations WHERE listing_id=? ORDER BY observed_at DESC"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return db.query_all(sql, (listing_id,))


def get_product_pricing(product_id):
    """Aggregate pricing across all active listings of a product.

    current_price = most recent observation across all listings (ties broken
        toward verified data).
    historical stats computed across ALL observations we've stored; the
    *verified* observation count is what feeds Deal Score's confidence cap,
    so a product seeded only with unverified/demo data is automatically
    treated as low-confidence rather than as a trustworthy "exceptional deal."
    """
    listings = get_product_listings(product_id)
    if not listings:
        return {
            "current_price": None, "previous_price": None, "historical_low": None,
            "historical_high": None, "historical_avg": None, "num_observations": 0,
            "availability": "unknown", "best_retailer": None, "best_retailer_credibility": None,
            "best_listing_id": None, "all_time_low_ever": None,
        }

    all_obs = []
    for listing in listings:
        obs = get_listing_observations(listing["id"])
        for o in obs:
            o = dict(o)
            o["listing"] = listing
            all_obs.append(o)

    if not all_obs:
        return {
            "current_price": None, "previous_price": None, "historical_low": None,
            "historical_high": None, "historical_avg": None, "num_observations": 0,
            "availability": "unknown", "best_retailer": None, "best_retailer_credibility": None,
            "best_listing_id": None, "all_time_low_ever": None,
        }

    all_obs.sort(key=lambda o: _parse_ts(o["observed_at"]), reverse=True)
    most_recent_ts = _parse_ts(all_obs[0]["observed_at"])
    # "current" = the set of observations from the latest check across listings
    # (each listing gets its own latest reading); pick the cheapest in-stock one.
    latest_per_listing = {}
    for o in all_obs:
        lid = o["listing_id"]
        if lid not in latest_per_listing:
            latest_per_listing[lid] = o
    candidates = list(latest_per_listing.values())
    in_stock = [c for c in candidates if c["availability"] == "in_stock"]
    pool = in_stock or candidates
    best = min(pool, key=lambda o: o["price_egp"])

    prices = [o["price_egp"] for o in all_obs]
    verified_prices = [o["price_egp"] for o in all_obs if o["is_verified"]]
    stat_prices = verified_prices if verified_prices else prices

    # previous_price: the chronologically-preceding observation to `best`
    # on the SAME listing, if any (fallback: 2nd most recent overall).
    same_listing_obs = [o for o in all_obs if o["listing_id"] == best["listing_id"]]
    previous_price = None
    for i, o in enumerate(same_listing_obs):
        if o["id"] == best["id"] and i + 1 < len(same_listing_obs):
            previous_price = same_listing_obs[i + 1]["price_egp"]
            break
    if previous_price is None and len(all_obs) > 1:
        for o in all_obs:
            if o["id"] != best["id"]:
                previous_price = o["price_egp"]
                break

    retailer = best["listing"]

    return {
        "current_price": best["price_egp"],
        "previous_price": previous_price,
        "historical_low": min(stat_prices) if stat_prices else None,
        "historical_high": max(stat_prices) if stat_prices else None,
        "historical_avg": round(statistics.mean(stat_prices), 2) if stat_prices else None,
        "num_observations": len(verified_prices),
        "num_observations_total": len(all_obs),
        "availability": best["availability"],
        "best_retailer": retailer["retailer_name"],
        "best_retailer_key": retailer["retailer_key"],
        "best_retailer_credibility": retailer["retailer_credibility"],
        "best_listing_id": best["listing_id"],
        "last_checked_at": best["observed_at"],
        "has_verified_data": bool(verified_prices),
    }


def get_price_history(product_id, days=None):
    listings = get_product_listings(product_id)
    listing_ids = [l["id"] for l in listings]
    if not listing_ids:
        return []
    placeholders = ",".join(["?"] * len(listing_ids))
    sql = f"""
        SELECT po.*, pl.retailer_id, r.name as retailer_name
        FROM price_observations po
        JOIN product_listings pl ON pl.id = po.listing_id
        JOIN retailers r ON r.id = pl.retailer_id
        WHERE po.listing_id IN ({placeholders})
        ORDER BY po.observed_at ASC
    """
    rows = db.query_all(sql, listing_ids)
    if days:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        rows = [r for r in rows if _parse_ts(r["observed_at"]) >= cutoff.replace(tzinfo=None)]
    return rows


def add_listing(product_id, retailer_id, url="", match_confidence="uncertain"):
    return db.insert("product_listings", {
        "product_id": product_id, "retailer_id": retailer_id, "url": url,
        "match_confidence": match_confidence, "is_active": 1, "created_at": db.now_iso(),
    })


def add_price_observation(listing_id, price_egp, availability="in_stock", source="manual",
                            is_verified=1, observed_at=None, raw_note=""):
    return db.insert("price_observations", {
        "listing_id": listing_id, "price_egp": price_egp, "availability": availability,
        "observed_at": observed_at or db.now_iso(), "source": source,
        "is_verified": 1 if is_verified else 0, "raw_note": raw_note,
    })


# ============================= Products =====================================

def _hydrate_product(row, with_pricing=True, with_deal=True, category=None):
    p = db.decode_json_fields(row)
    if p is None:
        return None
    category = category or get_category(p["category_id"])
    score, score_detail = scoring.compute_product_score(p.get("score_breakdown", {}), category.get("scoring_weights", {}) if category else {})
    p["computed_ai_research_score"] = score
    p["score_detail"] = score_detail
    p["category"] = category

    if with_pricing:
        pricing = get_product_pricing(p["id"])
        p["pricing"] = pricing
        if with_deal:
            quality = p.get("user_score") if p.get("user_score") is not None else (score if score is not None else p.get("ai_research_score"))
            pricing_for_deal = dict(pricing)
            pricing_for_deal["target_buy_price_egp"] = p.get("target_buy_price_egp")
            deal = deal_score_engine.compute_deal_score(
                pricing_for_deal,
                quality_score=quality,
                retailer_credibility=pricing.get("best_retailer_credibility"),
            )
            p["deal_score"] = deal
    return p


def list_products(category_id=None, status=None, with_pricing=True):
    sql = "SELECT * FROM products WHERE 1=1"
    params = []
    if category_id:
        sql += " AND category_id=?"
        params.append(category_id)
    if status:
        sql += " AND purchase_status=?"
        params.append(status)
    sql += " ORDER BY id"
    rows = db.query_all(sql, params)
    categories = {c["id"]: c for c in list_categories()}
    return [_hydrate_product(r, with_pricing=with_pricing, category=categories.get(r["category_id"])) for r in rows]


def get_product(product_id, with_pricing=True):
    row = db.query_one("SELECT * FROM products WHERE id=?", (product_id,))
    if row is None:
        return None
    product = _hydrate_product(row, with_pricing=with_pricing)
    product["listings"] = get_product_listings(product_id)
    product["purchases"] = db.query_all("SELECT * FROM purchases WHERE product_id=? ORDER BY purchase_date DESC", (product_id,))
    product["sources"] = db.query_all("SELECT * FROM research_sources WHERE product_id=? ORDER BY retrieved_at DESC", (product_id,))
    return product


def create_product(data):
    now = db.now_iso()
    fields = {
        "category_id": data["category_id"], "brand": data.get("brand", ""),
        "model": data.get("model", ""), "sku": data.get("sku", ""),
        "full_name": data.get("full_name") or f"{data.get('brand','')} {data.get('model','')}".strip(),
        "image_url": data.get("image_url", ""), "capacity": data.get("capacity", ""),
        "specs": json.dumps(data.get("specs", {})), "warranty_years": data.get("warranty_years", 0),
        "features": json.dumps(data.get("features", [])), "pros": json.dumps(data.get("pros", [])),
        "cons": json.dumps(data.get("cons", [])),
        "reliability_assessment": data.get("reliability_assessment", ""),
        "egypt_service_assessment": data.get("egypt_service_assessment", ""),
        "score_breakdown": json.dumps(data.get("score_breakdown", {})),
        "ai_research_score": data.get("ai_research_score"),
        "user_score": data.get("user_score"),
        "target_buy_price_egp": data.get("target_buy_price_egp"),
        "purchase_status": data.get("purchase_status", "researching"),
        "is_demo_data": 1 if data.get("is_demo_data") else 0,
        "created_at": now, "updated_at": now,
    }
    return db.insert("products", fields)


def update_product(product_id, data):
    allowed = ["category_id", "brand", "model", "sku", "full_name", "image_url", "capacity",
               "specs", "warranty_years", "features", "pros", "cons", "reliability_assessment",
               "egypt_service_assessment", "score_breakdown", "ai_research_score", "user_score",
               "target_buy_price_egp", "purchase_status", "is_demo_data"]
    fields = {}
    for k in allowed:
        if k in data:
            v = data[k]
            if k in ("specs", "features", "pros", "cons", "score_breakdown"):
                v = json.dumps(v)
            fields[k] = v
    fields["updated_at"] = db.now_iso()
    db.update("products", product_id, fields)


def delete_product(product_id):
    db.delete("products", product_id)


def recompute_and_store_ai_score(product_id):
    p = db.query_one("SELECT * FROM products WHERE id=?", (product_id,))
    p = db.decode_json_fields(p)
    category = get_category(p["category_id"])
    score, _ = scoring.compute_product_score(p.get("score_breakdown", {}), category.get("scoring_weights", {}))
    if score is not None:
        db.update("products", product_id, {"ai_research_score": score, "updated_at": db.now_iso()})
    return score


# ============================= Purchases =====================================

def list_purchases():
    return db.query_all("""
        SELECT pu.*, p.full_name, p.brand, p.model, p.category_id, r.name as retailer_name
        FROM purchases pu JOIN products p ON p.id = pu.product_id
        LEFT JOIN retailers r ON r.id = pu.retailer_id
        ORDER BY pu.purchase_date DESC
    """)


def create_purchase(data):
    now = db.now_iso()
    fields = {
        "product_id": data["product_id"], "retailer_id": data.get("retailer_id"),
        "purchase_price_egp": data["purchase_price_egp"], "purchase_date": data.get("purchase_date", now[:10]),
        "warranty_period_months": data.get("warranty_period_months", 0),
        "invoice_number": data.get("invoice_number", ""), "notes": data.get("notes", ""),
        "created_at": now,
    }
    purchase_id = db.insert("purchases", fields)
    db.update("products", data["product_id"], {"purchase_status": "purchased", "updated_at": now})
    return purchase_id


# ============================= Budget =====================================

def _products_for_budget():
    rows = db.query_all("SELECT id, category_id, purchase_status, target_buy_price_egp FROM products")
    out = []
    for r in rows:
        pricing = get_product_pricing(r["id"])
        out.append({
            "id": r["id"], "category_id": r["category_id"], "purchase_status": r["purchase_status"],
            "target_buy_price_egp": r["target_buy_price_egp"], "current_price": pricing["current_price"],
        })
    return out


def get_budget_summary(exclude_category_id=None):
    total_budget = db.get_setting("total_budget_egp", config.TOTAL_BUDGET_EGP)
    categories = list_categories()
    products = _products_for_budget()
    purchases = db.query_all("SELECT product_id, purchase_price_egp FROM purchases")
    return budget_engine.compute_budget(total_budget, categories, products, purchases,
                                         exclude_category_id=exclude_category_id)


def simulate_what_if(hypothetical):
    total_budget = db.get_setting("total_budget_egp", config.TOTAL_BUDGET_EGP)
    categories = list_categories()
    products = _products_for_budget()
    purchases = db.query_all("SELECT product_id, purchase_price_egp FROM purchases")
    return budget_engine.simulate_purchases(total_budget, categories, products, purchases, hypothetical)


def get_recommendation_for_product(product_id):
    product = get_product(product_id)
    if product is None:
        return None
    category = product["category"]
    budget = get_budget_summary(exclude_category_id=category["id"] if category.get("priority_level") == 1 else None)
    current_price = product["pricing"]["current_price"]
    rec = recommendation_engine.recommend(product, category, product["deal_score"], budget, current_price)
    return rec


# ============================= Alerts =====================================

def list_alerts(unread_only=False, limit=50):
    sql = "SELECT a.*, p.full_name, p.brand, p.model FROM alerts a JOIN products p ON p.id=a.product_id"
    if unread_only:
        sql += " WHERE a.is_read=0"
    sql += " ORDER BY a.triggered_at DESC LIMIT ?"
    return db.query_all(sql, (limit,))


def get_last_alert(product_id, alert_type):
    return db.query_one(
        "SELECT * FROM alerts WHERE product_id=? AND alert_type=? ORDER BY triggered_at DESC LIMIT 1",
        (product_id, alert_type),
    )


def create_alert(product_id, listing_id, alert_type, message, price, deal_score_value, recommendation_text):
    dedup_key = alerts_engine.make_dedup_key(product_id, alert_type, price)
    existing = db.query_one("SELECT id FROM alerts WHERE dedup_key=?", (dedup_key,))
    if existing:
        return None
    return db.insert("alerts", {
        "product_id": product_id, "listing_id": listing_id, "alert_type": alert_type,
        "message": message, "price_at_alert": price, "deal_score_at_alert": deal_score_value,
        "recommendation": recommendation_text, "triggered_at": db.now_iso(),
        "dedup_key": dedup_key, "is_read": 0,
    })


def mark_alert_read(alert_id):
    db.update("alerts", alert_id, {"is_read": 1})


def log_notification(alert_id, channel, status, detail=""):
    db.insert("notification_history", {
        "alert_id": alert_id, "channel": channel, "sent_at": db.now_iso(),
        "status": status, "detail": detail,
    })


# ============================= Activity feed =====================================

def log_activity(actor, action, summary, entity_type="product", entity_id=None):
    db.insert("activity_log", {
        "actor": actor or "Someone", "action": action, "entity_type": entity_type,
        "entity_id": entity_id, "summary": summary, "created_at": db.now_iso(),
    })


def list_activity(limit=50):
    return db.query_all("SELECT * FROM activity_log ORDER BY created_at DESC LIMIT ?", (limit,))


# ============================= Research sources =====================================

def add_research_source(product_id, url, retailer, confidence="verified", note="", listing_id=None):
    return db.insert("research_sources", {
        "product_id": product_id, "listing_id": listing_id, "url": url, "retailer": retailer,
        "retrieved_at": db.now_iso(), "confidence": confidence, "note": note,
    })


# ============================= Dashboard aggregation =====================================

def get_dashboard():
    categories = list_categories()
    products = list_products(with_pricing=True)
    products_by_cat = {}
    for p in products:
        products_by_cat.setdefault(p["category_id"], []).append(p)

    budget = get_budget_summary()

    priority_cards = []
    for cat in categories:
        cat_products = products_by_cat.get(cat["id"], [])
        active = [p for p in cat_products if p["purchase_status"] not in ("rejected", "purchased")]
        purchased = [p for p in cat_products if p["purchase_status"] == "purchased"]
        best = None
        if active:
            priced = [p for p in active if p["pricing"]["current_price"] is not None]
            pool = priced or active
            best = min(pool, key=lambda p: p["pricing"]["current_price"] if p["pricing"]["current_price"] is not None else float("inf")) if priced else pool[0]
        rec = None
        if best and best["pricing"]["current_price"] is not None:
            budget_ex = get_budget_summary(exclude_category_id=cat["id"] if cat["priority_level"] == 1 else None)
            rec = recommendation_engine.recommend(best, cat, best["deal_score"], budget_ex, best["pricing"]["current_price"])
        priority_cards.append({
            "category": cat,
            "is_fulfilled": bool(purchased),
            "best_candidate": best,
            "recommendation": rec,
            "num_shortlisted": len(cat_products),
        })

    # Best deals today: products with a decent deal score, sorted desc, excluding purchased/rejected.
    deal_candidates = [p for p in products if p["purchase_status"] not in ("purchased", "rejected")
                        and p["deal_score"]["score"] is not None]
    best_deals = sorted(deal_candidates, key=lambda p: p["deal_score"]["score"], reverse=True)
    best_deals = [p for p in best_deals if p["deal_score"]["score"] >= config.DEAL_SCORE_THRESHOLDS["fair"]][:8]

    recent_alerts = list_alerts(limit=10)

    # "What should I buy next?" — rank BUY/URGENT_BUY recommendations,
    # prioritizing URGENT_BUY, then priority level, then deal score.
    buy_candidates = []
    for card in priority_cards:
        if card["recommendation"] and card["recommendation"]["decision"] in ("BUY", "URGENT_BUY"):
            buy_candidates.append(card)
    decision_rank = {"URGENT_BUY": 0, "BUY": 1}
    buy_candidates.sort(key=lambda c: (
        decision_rank.get(c["recommendation"]["decision"], 9),
        c["category"]["priority_level"],
        -(c["recommendation"]["deal_score"] or 0),
    ))
    next_buy = buy_candidates[0] if buy_candidates else None

    return {
        "budget": budget,
        "priority_cards": priority_cards,
        "best_deals": best_deals,
        "recent_alerts": recent_alerts,
        "next_buy": next_buy,
        "total_budget_egp": budget["total_budget_egp"],
    }
