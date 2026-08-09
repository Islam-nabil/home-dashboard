"""
Alert condition evaluation + deduplication (spec sections 12, 28).

Design goal: "don't notify repeatedly about unchanged prices." Each alert
type has its own should_alert() rule based on the STATE CHANGE since the
last alert of that type for that product, not just "condition is currently
true" (which would refire every price-check cycle for as long as a sale
lasts).
"""

ALERT_TYPES = [
    "below_target",
    "drop_10pct",
    "new_low",
    "exceptional_deal",
    "high_priority_sale",
    "back_in_stock",
]

# Minimum relative price change required to re-fire a "still true" style
# alert (below_target / exceptional_deal / high_priority_sale) so a price
# sitting flat under the target doesn't alert every single check.
RE_ALERT_MIN_PCT_CHANGE = 0.02


def make_dedup_key(product_id, alert_type, price):
    """Idempotency key: re-running a price check with an unchanged price
    must not create a duplicate row (DB has a UNIQUE index on this)."""
    bucket = round(price) if price is not None else "na"
    return f"{product_id}:{alert_type}:{bucket}"


def evaluate_conditions(product, category, pricing, deal_score_result, previous_availability=None):
    """
    Returns a list of alert dicts (possibly empty): each has alert_type,
    message, price, deal_score.

    pricing: {current_price, previous_price, historical_low, availability}
    """
    triggered = []
    current = pricing.get("current_price")
    previous = pricing.get("previous_price")
    low = pricing.get("historical_low")
    target = product.get("target_buy_price_egp")
    score = (deal_score_result or {}).get("score")
    availability = pricing.get("availability")

    if current is None:
        return triggered

    name = product.get("full_name") or f"{product.get('brand', '')} {product.get('model', '')}".strip()

    if target is not None and current <= target:
        triggered.append({
            "alert_type": "below_target",
            "message": f"{name} dropped to {current:,.0f} EGP, at or below your target of {target:,.0f} EGP.",
        })

    if previous and previous > 0:
        pct_drop = (previous - current) / previous * 100.0
        if pct_drop >= 10:
            triggered.append({
                "alert_type": "drop_10pct",
                "message": f"{name} dropped {pct_drop:.1f}% ({previous:,.0f} -> {current:,.0f} EGP).",
            })

    if low is not None and current < low:
        triggered.append({
            "alert_type": "new_low",
            "message": f"{name} hit a new historical low: {current:,.0f} EGP (previous low {low:,.0f} EGP).",
        })
    elif low is None:
        # First-ever observation on this listing is trivially its own low;
        # not alert-worthy on its own.
        pass

    if score is not None and score >= 90:
        triggered.append({
            "alert_type": "exceptional_deal",
            "message": f"{name} has an exceptional Deal Score of {score}/100 right now.",
        })

    if category.get("priority_level") == 1 and previous and previous > 0:
        pct_drop = (previous - current) / previous * 100.0
        if pct_drop >= 5:
            triggered.append({
                "alert_type": "high_priority_sale",
                "message": f"{name} (Priority 1 / Critical) just dropped {pct_drop:.1f}%.",
            })

    if previous_availability == "out_of_stock" and availability == "in_stock":
        triggered.append({
            "alert_type": "back_in_stock",
            "message": f"{name} is back in stock.",
        })

    for t in triggered:
        t["price"] = current
        t["deal_score"] = score

    return triggered


def should_alert(alert_type, current_price, last_alert):
    """Given the last alert row of this alert_type for this product (or
    None), decide whether firing a new one is warranted right now."""
    if last_alert is None:
        return True

    last_price = last_alert.get("price_at_alert")
    if last_price is None or current_price is None:
        return True

    if alert_type == "new_low":
        return current_price < last_price

    if alert_type == "back_in_stock":
        # Only re-alert back-in-stock if it went out of stock again in
        # between; caller only invokes this on an actual state transition,
        # so always allow it here.
        return True

    # below_target / exceptional_deal / high_priority_sale / drop_10pct:
    # only re-fire if price moved meaningfully since the last alert.
    if last_price == 0:
        return True
    pct_change = abs(current_price - last_price) / last_price
    return pct_change >= RE_ALERT_MIN_PCT_CHANGE
