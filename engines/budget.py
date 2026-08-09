"""
Budget & priority engine (spec sections 2, 3, 9, 10, 23).

All functions here are pure (no DB access) so they're easy to unit test:
callers (routes/repository) gather the raw rows from SQLite, shape them
into the small dicts documented below, and pass them in.
"""


def _best_estimate_cost(products_in_category):
    """Best-effort 'what will this category cost' estimate, in priority
    order: cheapest current verified price among live candidates -> cheapest
    target price set by the user -> None (caller falls back to category
    target_budget_egp)."""
    current_prices = [p["current_price"] for p in products_in_category
                       if p.get("current_price") is not None
                       and p.get("purchase_status") not in ("rejected",)]
    if current_prices:
        return min(current_prices)
    targets = [p["target_buy_price_egp"] for p in products_in_category
               if p.get("target_buy_price_egp") is not None
               and p.get("purchase_status") not in ("rejected",)]
    if targets:
        return min(targets)
    return None


def compute_budget(total_budget_egp, categories, products, purchases,
                    exclude_category_id=None):
    """
    categories: list of dicts {id, name, priority_level, target_budget_egp}
    products:   list of dicts {id, category_id, purchase_status,
                                target_buy_price_egp, current_price}
    purchases:  list of dicts {product_id, purchase_price_egp}
    exclude_category_id: when computing the "gap" to decide whether buying
        THIS product would jeopardize other Priority-1 categories, the
        product's own category is excluded from the gap calculation.

    Returns a dict — see inline comments for each field's meaning.
    """
    spent = round(sum(p["purchase_price_egp"] for p in purchases), 2)

    purchased_product_ids = {p["product_id"] for p in purchases}

    # Committed = money earmarked for items marked 'ready_to_buy' that
    # haven't been purchased yet (i.e. the user has decided to buy them).
    committed = 0.0
    for p in products:
        if p["id"] in purchased_product_ids:
            continue
        if p.get("purchase_status") == "ready_to_buy":
            amount = p.get("current_price") or p.get("target_buy_price_egp") or 0
            committed += amount
    committed = round(committed, 2)

    remaining_egp = round(total_budget_egp - spent - committed, 2)

    products_by_category = {}
    for p in products:
        products_by_category.setdefault(p["category_id"], []).append(p)

    category_breakdown = []
    estimated_remaining_essential = 0.0
    priority1_gap = 0.0
    critical_total = 0
    critical_purchased = 0
    categories_with_purchase = 0

    for cat in categories:
        cat_products = products_by_category.get(cat["id"], [])
        has_purchase = any(p["id"] in purchased_product_ids for p in cat_products)
        if has_purchase:
            categories_with_purchase += 1
        if cat.get("priority_level") == 1:
            critical_total += 1
            if has_purchase:
                critical_purchased += 1

        estimate = _best_estimate_cost(cat_products)
        if estimate is None:
            estimate = cat.get("target_budget_egp") or 0

        gap_for_category = 0 if has_purchase else estimate

        if cat.get("priority_level") == 1:
            estimated_remaining_essential += gap_for_category
            if cat["id"] != exclude_category_id:
                priority1_gap += gap_for_category

        spent_in_category = round(sum(
            pu["purchase_price_egp"] for pu in purchases
            if pu["product_id"] in {p["id"] for p in cat_products}
        ), 2)

        category_breakdown.append({
            "category_id": cat["id"],
            "name": cat["name"],
            "priority_level": cat.get("priority_level"),
            "target_budget_egp": cat.get("target_budget_egp"),
            "has_purchase": has_purchase,
            "estimated_cost_egp": estimate,
            "spent_egp": spent_in_category,
        })

    estimated_remaining_essential = round(estimated_remaining_essential, 2)
    buffer_egp = round(remaining_egp - estimated_remaining_essential, 2)

    percent_complete = 0.0
    if categories:
        percent_complete = round(100.0 * categories_with_purchase / len(categories), 1)

    return {
        "total_budget_egp": total_budget_egp,
        "spent_egp": spent,
        "committed_egp": committed,
        "remaining_egp": remaining_egp,
        "estimated_remaining_essential_egp": estimated_remaining_essential,
        "buffer_egp": buffer_egp,
        "percent_complete": percent_complete,
        "critical_purchased": critical_purchased,
        "critical_total": critical_total,
        "categories_with_purchase": categories_with_purchase,
        "categories_total": len(categories),
        "other_priority1_gap_egp": round(priority1_gap, 2),
        "category_breakdown": category_breakdown,
        "risk_level": _risk_level(buffer_egp, total_budget_egp),
    }


def _risk_level(buffer_egp, total_budget_egp):
    if total_budget_egp <= 0:
        return "unknown"
    ratio = buffer_egp / total_budget_egp
    if buffer_egp < 0:
        return "over_budget"
    if ratio < 0.05:
        return "tight"
    if ratio < 0.15:
        return "moderate"
    return "comfortable"


def simulate_purchases(total_budget_egp, categories, products, purchases, hypothetical_purchases):
    """'What If?' simulator (spec section 23).

    hypothetical_purchases: list of {product_id, price_egp}
    Returns the resulting compute_budget() output as if those purchases had
    already happened, plus a summary of what changed.
    """
    before = compute_budget(total_budget_egp, categories, products, purchases)

    sim_purchases = list(purchases) + [
        {"product_id": hp["product_id"], "purchase_price_egp": hp["price_egp"]}
        for hp in hypothetical_purchases
    ]
    hypothetical_ids = {hp["product_id"] for hp in hypothetical_purchases}
    sim_products = []
    for p in products:
        if p["id"] in hypothetical_ids and p.get("purchase_status") != "purchased":
            p = dict(p)
            p["purchase_status"] = "purchased"
        sim_products.append(p)

    after = compute_budget(total_budget_egp, categories, sim_products, sim_purchases)

    remaining_critical_categories = [
        c for c in after["category_breakdown"]
        if c["priority_level"] == 1 and not c["has_purchase"]
    ]

    return {
        "before": before,
        "after": after,
        "delta_remaining_egp": round(after["remaining_egp"] - before["remaining_egp"], 2),
        "delta_buffer_egp": round(after["buffer_egp"] - before["buffer_egp"], 2),
        "remaining_critical_categories": remaining_critical_categories,
        "expected_cost_to_complete_critical_egp": round(
            sum(c["estimated_cost_egp"] or 0 for c in remaining_critical_categories), 2
        ),
        "risk_level": after["risk_level"],
    }
