"""
Product Score engine (spec section 8).

A product's score is a transparent weighted average across dimensions such
as reliability, price/value, warranty & service, energy efficiency, core
performance, features, and user preference. Weights are configurable per
category (stored in categories.scoring_weights) so, e.g., "energy
efficiency" can matter more for an AC than a microwave.

The methodology is intentionally simple and fully visible: every dimension
score and weight used is returned alongside the final number so the UI can
show "why" a product scored the way it did instead of a black box.
"""
import config

DIMENSIONS = [
    "reliability",
    "price_value",
    "warranty_service",
    "energy_efficiency",
    "performance",
    "features",
    "user_preference",
]

DIMENSION_LABELS = {
    "reliability": "Reliability",
    "price_value": "Price / Value",
    "warranty_service": "Warranty & Service (Egypt)",
    "energy_efficiency": "Energy Efficiency",
    "performance": "Core Performance",
    "features": "Features",
    "user_preference": "User Preference",
}


def normalize_weights(weights):
    """Return a dict of dimension->weight that sums to 1.0.

    Falls back to config.DEFAULT_SCORING_WEIGHTS for any dimension not
    present in `weights`, then renormalizes so the total is always 1.0
    (protects against a category config that doesn't sum to 100%).
    """
    base = dict(config.DEFAULT_SCORING_WEIGHTS)
    if weights:
        for k, v in weights.items():
            if k in DIMENSIONS:
                try:
                    base[k] = float(v)
                except (TypeError, ValueError):
                    pass
    total = sum(base.values()) or 1.0
    return {k: v / total for k, v in base.items()}


def compute_product_score(score_breakdown, category_weights):
    """Compute the 0-100 weighted AI/research score for a product.

    score_breakdown: dict of dimension -> 0-100 (not every dimension needs
        to be present; scoring is renormalized over whatever was actually
        assessed, so a missing dimension doesn't silently drag the score
        toward zero).
    category_weights: dict of dimension -> weight (category-specific,
        may be partial/empty -> defaults apply).

    Returns (score: float|None, detail: dict) where detail lists each
    dimension's raw score, its weight, and its contribution - the
    "show the methodology" requirement from the spec.
    """
    if not score_breakdown:
        return None, {"dimensions": [], "note": "No dimensions scored yet."}

    weights = normalize_weights(category_weights)
    scored_dims = {d: v for d, v in score_breakdown.items() if d in DIMENSIONS and v is not None}
    if not scored_dims:
        return None, {"dimensions": [], "note": "No recognized dimensions scored yet."}

    weight_sum = sum(weights[d] for d in scored_dims) or 1.0
    contributions = []
    total = 0.0
    for d in DIMENSIONS:
        if d not in scored_dims:
            continue
        w_effective = weights[d] / weight_sum  # renormalized over dims actually scored
        contribution = scored_dims[d] * w_effective
        total += contribution
        contributions.append({
            "dimension": d,
            "label": DIMENSION_LABELS.get(d, d),
            "raw_score": round(scored_dims[d], 1),
            "weight": round(weights[d], 3),
            "weight_effective": round(w_effective, 3),
            "contribution": round(contribution, 2),
        })

    unscored = [d for d in DIMENSIONS if d not in scored_dims]
    return round(total, 1), {
        "dimensions": contributions,
        "unscored_dimensions": unscored,
        "note": (
            "Weighted average renormalized over the dimensions actually "
            "assessed; unscored dimensions are excluded rather than "
            "counted as zero."
        ),
    }
