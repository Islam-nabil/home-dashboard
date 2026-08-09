"""
Decision Engine (spec section 10): BUY / WAIT / IGNORE / URGENT BUY.

This is deliberately budget-aware and priority-aware, not just a re-labeling
of the Deal Score. The key rule (spec section 10 + the critical test in
section 28): a good discount on a LOW-priority item must NOT be recommended
if buying it would eat into the budget reserved for still-unfunded Priority-1
(critical) categories. Conversely a Priority-1 item at an unusually low price
can be elevated all the way to URGENT_BUY.

Every decision returns a plain-English explanation built from the same
numbers used to make it - no hidden reasoning.
"""
import config

EXCEPTIONAL = config.DEAL_SCORE_THRESHOLDS["exceptional"]
GOOD = config.DEAL_SCORE_THRESHOLDS["good"]
FAIR = config.DEAL_SCORE_THRESHOLDS["fair"]
WAIT_FLOOR = config.DEAL_SCORE_THRESHOLDS["wait"]

BUY = "BUY"
WAIT = "WAIT"
IGNORE = "IGNORE"
URGENT_BUY = "URGENT_BUY"


def recommend(product, category, deal_score_result, budget_summary, current_price):
    """
    product: dict with at least purchase_status, target_buy_price_egp, ai_research_score
    category: dict with priority_level, id, name
    deal_score_result: output of engines.deal_score.compute_deal_score
    budget_summary: output of engines.budget.compute_budget (see engines/budget.py) -
        specifically uses 'remaining_egp' and 'priority1_gap_egp' (money still
        needed to cover un-purchased Priority-1 categories, EXCLUDING this
        product's own category if this product is itself Priority-1).
    current_price: float, the price being evaluated

    Returns dict: decision, explanation (str), risk_flags (list[str]), deal_score (int|None)
    """
    priority = category.get("priority_level", 2)
    score = deal_score_result.get("score")
    risk_flags = []

    if current_price is None or score is None:
        return {
            "decision": WAIT,
            "explanation": "No verified current price is available for this product yet, so no purchase decision can be made — keep researching or add a listing to track.",
            "risk_flags": ["no_price_data"],
            "deal_score": None,
        }

    remaining = budget_summary.get("remaining_egp", 0)
    # Money still needed for OTHER unpurchased Priority-1 categories (this
    # product's own category is excluded by the caller when it is itself P1).
    other_priority1_gap = budget_summary.get("other_priority1_gap_egp", 0)

    exceeds_remaining = current_price > remaining
    would_exceed_after_purchase = (remaining - current_price) < other_priority1_gap

    if exceeds_remaining:
        risk_flags.append("exceeds_remaining_budget")
        return {
            "decision": IGNORE,
            "explanation": (
                f"This purchase ({current_price:,.0f} EGP) exceeds your entire remaining budget "
                f"({remaining:,.0f} EGP). Not affordable right now regardless of deal quality."
            ),
            "risk_flags": risk_flags,
            "deal_score": score,
        }

    quality = product.get("ai_research_score")
    low_quality = quality is not None and quality < 50

    if would_exceed_after_purchase and priority != 1:
        risk_flags.append("jeopardizes_priority1_budget")
        decision = WAIT if score >= FAIR else IGNORE
        explanation = (
            f"Buying this now ({current_price:,.0f} EGP) would leave only "
            f"{remaining - current_price:,.0f} EGP, below the "
            f"{other_priority1_gap:,.0f} EGP still needed for your unfunded Priority-1 "
            f"(critical) categories. Even with a Deal Score of {score}/100, this is not "
            f"financially sensible right now."
        )
        return {"decision": decision, "explanation": explanation, "risk_flags": risk_flags, "deal_score": score}

    if low_quality and score < GOOD:
        risk_flags.append("low_quality_product")
        return {
            "decision": IGNORE,
            "explanation": (
                f"Product quality score is low ({quality:.0f}/100) and the current discount "
                f"(Deal Score {score}/100) isn't strong enough to outweigh that."
            ),
            "risk_flags": risk_flags,
            "deal_score": score,
        }

    at_new_low = any(
        "new historical low" in e.lower() for e in deal_score_result.get("explanation", [])
    )

    if priority == 1 and score >= EXCEPTIONAL:
        decision = URGENT_BUY
        explanation = (
            f"URGENT BUY — Deal Score {score}/100 on a Priority-1 (critical) category"
            + (", and it's a new historical low" if at_new_low else "")
            + f". Sufficient budget remains ({remaining - current_price:,.0f} EGP left after buying) "
              f"for your other critical purchases."
        )
        return {"decision": decision, "explanation": explanation, "risk_flags": risk_flags, "deal_score": score}

    target = product.get("target_buy_price_egp")
    at_or_below_target = target is not None and current_price <= target

    if score >= GOOD and (at_or_below_target or at_new_low):
        decision = BUY
        reason_bits = []
        if at_new_low:
            reason_bits.append("at a new historical low")
        if at_or_below_target:
            reason_bits.append(f"at/below your target of {target:,.0f} EGP")
        explanation = (
            f"BUY — Deal Score {score}/100, " + " and ".join(reason_bits) +
            f". {remaining - current_price:,.0f} EGP remains after purchase, which still "
            f"covers your other unfunded Priority-1 needs ({other_priority1_gap:,.0f} EGP)."
        )
        return {"decision": decision, "explanation": explanation, "risk_flags": risk_flags, "deal_score": score}

    if score >= GOOD:
        decision = BUY if priority == 1 else WAIT
        explanation = (
            f"Deal Score {score}/100 is good, but the price hasn't reached your target yet and "
            "isn't a new historical low. "
            + ("Still worth buying given this is a Priority-1 essential." if priority == 1
               else "Consider waiting for it to hit your target or a fresh low.")
        )
        return {"decision": decision, "explanation": explanation, "risk_flags": risk_flags, "deal_score": score}

    if score >= FAIR:
        return {
            "decision": WAIT,
            "explanation": f"Deal Score {score}/100 — a fair price, but not compelling enough to buy yet. Keep watching.",
            "risk_flags": risk_flags,
            "deal_score": score,
        }

    if score >= WAIT_FLOOR:
        return {
            "decision": WAIT,
            "explanation": f"Deal Score {score}/100 — below-average deal quality right now. Hold off.",
            "risk_flags": risk_flags,
            "deal_score": score,
        }

    return {
        "decision": IGNORE,
        "explanation": f"Deal Score {score}/100 — poor deal (price is high relative to history and/or target). Not worth acting on.",
        "risk_flags": risk_flags,
        "deal_score": score,
    }
