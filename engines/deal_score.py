"""
Deal Score engine (spec section 9).

IMPORTANT PHILOSOPHY: a retailer's "SALE" badge is not evidence of a good
deal. This engine only trusts the price history *we ourselves* have
recorded (price_observations), plus the product's independent quality
score and the retailer's credibility rating. A single low observation with
no history behind it gets its score capped and flagged low-confidence
rather than reported as "exceptional."

Score is 0-100, built from six weighted sub-scores:
  - vs_historical_average (25%)
  - vs_historical_low      (20%)
  - vs_target_price        (20%)
  - discount_pct           (15%)   (drop vs. the most recent "normal" price)
  - product_quality        (10%)   (a discount on a mediocre product isn't a good deal)
  - retailer_credibility   (10%)

A confidence cap protects against overconfident scores on thin data.
"""

WEIGHTS = {
    "vs_avg": 0.25,
    "vs_low": 0.20,
    "vs_target": 0.20,
    "discount": 0.15,
    "quality": 0.10,
    "retailer": 0.10,
}

LABELS = [
    (90, "Exceptional Deal"),
    (75, "Good Buy"),
    (60, "Fair Price"),
    (40, "Wait"),
    (0, "Poor Deal"),
]


def _clamp(v, lo=0.0, hi=100.0):
    return max(lo, min(hi, v))


def label_for_score(score):
    for threshold, label in LABELS:
        if score >= threshold:
            return label
    return "Poor Deal"


def compute_deal_score(pricing, quality_score=None, retailer_credibility=70):
    """
    pricing: dict with keys
        current_price (float, required - if None, no deal can be scored)
        historical_low (float|None)
        historical_high (float|None)
        historical_avg (float|None)
        target_buy_price_egp (float|None)
        num_observations (int)
    quality_score: 0-100 product quality (ai_research_score, falls back to
        a neutral 55 if the product hasn't been scored yet)
    retailer_credibility: 0-100

    Returns dict: score, label, confidence, factors(list of subscore dicts),
    explanation (list of human-readable strings).
    """
    current = pricing.get("current_price")
    if current is None:
        return {
            "score": None, "label": "No Price Data", "confidence": "none",
            "factors": [], "explanation": ["No price has been observed for this listing yet."],
        }

    avg = pricing.get("historical_avg")
    low = pricing.get("historical_low")
    high = pricing.get("historical_high")
    target = pricing.get("target_buy_price_egp")
    n_obs = pricing.get("num_observations", 0) or 0
    quality = 55.0 if quality_score is None else float(quality_score)
    retailer_credibility = 70.0 if retailer_credibility is None else float(retailer_credibility)

    explanation = []
    factors = []

    # --- vs historical average -------------------------------------------------
    if avg and avg > 0:
        pct_below_avg = (avg - current) / avg * 100.0
        s_avg = _clamp(50 + pct_below_avg * 2.5)
        if pct_below_avg > 1:
            explanation.append(f"{pct_below_avg:.1f}% below its historical average price ({avg:,.0f} EGP).")
        elif pct_below_avg < -1:
            explanation.append(f"{abs(pct_below_avg):.1f}% above its historical average price ({avg:,.0f} EGP).")
    else:
        s_avg = 50.0
        explanation.append("No historical average yet (too little price history) — treated neutrally.")
    factors.append({"key": "vs_avg", "label": "vs. Historical Average", "score": round(s_avg, 1), "weight": WEIGHTS["vs_avg"]})

    # --- vs historical low -------------------------------------------------
    if low and low > 0:
        if current <= low:
            s_low = 100.0
            if current < low:
                explanation.append(f"New historical low ({current:,.0f} EGP, previous low was {low:,.0f} EGP).")
            else:
                explanation.append(f"Matches the historical low of {low:,.0f} EGP.")
        else:
            pct_above_low = (current - low) / low * 100.0
            s_low = _clamp(100 - pct_above_low * 3)
            explanation.append(f"{pct_above_low:.1f}% above its historical low of {low:,.0f} EGP.")
    else:
        s_low = 50.0
    factors.append({"key": "vs_low", "label": "vs. Historical Low", "score": round(s_low, 1), "weight": WEIGHTS["vs_low"]})

    # --- vs target price -------------------------------------------------
    if target and target > 0:
        if current <= target:
            pct_below_target = (target - current) / target * 100.0
            s_target = _clamp(85 + pct_below_target * 1.5)
            explanation.append(f"At or below your target price of {target:,.0f} EGP.")
        else:
            pct_above_target = (current - target) / target * 100.0
            s_target = _clamp(85 - pct_above_target * 4)
            explanation.append(f"{pct_above_target:.1f}% above your target price of {target:,.0f} EGP.")
    else:
        s_target = 50.0
        explanation.append("No target price set for this product yet — vs-target scored neutrally.")
    factors.append({"key": "vs_target", "label": "vs. Target Price", "score": round(s_target, 1), "weight": WEIGHTS["vs_target"]})

    # --- discount vs recent "normal" price (uses high as reference) -----------
    reference = high if (high and high > current) else avg
    if reference and reference > current:
        discount_pct = (reference - current) / reference * 100.0
        s_discount = _clamp(discount_pct * 4)
        if discount_pct >= 3:
            explanation.append(f"Currently discounted {discount_pct:.1f}% vs. its recent typical price ({reference:,.0f} EGP).")
    else:
        discount_pct = 0.0
        s_discount = 30.0
    factors.append({"key": "discount", "label": "Discount vs. Recent Price", "score": round(s_discount, 1), "weight": WEIGHTS["discount"]})

    # --- product quality -------------------------------------------------
    s_quality = _clamp(quality)
    if quality_score is None:
        explanation.append("Product quality score not yet assessed — used a neutral placeholder; a discount alone doesn't make a low-quality product a good deal.")
    elif quality < 55:
        explanation.append(f"Product quality score is only {quality:.0f}/100 — a discount doesn't fully offset mediocre quality.")
    factors.append({"key": "quality", "label": "Product Quality Score", "score": round(s_quality, 1), "weight": WEIGHTS["quality"]})

    # --- retailer credibility -------------------------------------------------
    s_retailer = _clamp(retailer_credibility)
    if retailer_credibility < 60:
        explanation.append(f"Retailer credibility is only {retailer_credibility:.0f}/100 — verify this listing carefully before buying.")
    factors.append({"key": "retailer", "label": "Retailer Credibility", "score": round(s_retailer, 1), "weight": WEIGHTS["retailer"]})

    raw = sum(f["score"] * f["weight"] for f in factors)

    # --- confidence cap on thin data / "unusual temporary promotion" guard ----
    confidence = "high"
    if n_obs <= 1:
        confidence = "low"
        # Capped below the "Exceptional" band (90+) — a single observation
        # can still support a "Good Buy"/BUY call (e.g. it's already below
        # a user-set target), but never an unqualified "Exceptional Deal",
        # which should require accumulated history to back it up.
        capped = min(raw, 78)
        if capped < raw:
            explanation.append(
                "Only one price observation exists for this listing — confidence is LOW. "
                "Score capped below 'Exceptional' to avoid overstating an unverified single data point."
            )
        raw = capped
    elif n_obs == 2:
        confidence = "medium"
        capped = min(raw, 88)
        if capped < raw:
            explanation.append("Limited price history (2 observations) — confidence is MEDIUM, score capped slightly.")
        raw = capped
    else:
        # Even with history, an implausibly large single-step drop is flagged
        # (possible listing error / flash promo) rather than blindly trusted.
        if reference and reference > 0 and (reference - current) / reference > 0.35:
            explanation.append(
                "This is an unusually large single-step price drop (>35%) — double-check the "
                "listing before buying in case it's a pricing error or an unrepresentative flash promo."
            )

    score = round(_clamp(raw))
    label = label_for_score(score)

    return {
        "score": score,
        "label": label,
        "confidence": confidence,
        "num_observations": n_obs,
        "factors": factors,
        "explanation": explanation,
    }
