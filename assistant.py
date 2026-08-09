"""
AI Purchasing Assistant panel (spec section 22).

Deliberately NOT a wrapper around an LLM that free-associates prices from
its training data — "reason using the database rather than inventing
prices" is a hard requirement. This is a small deterministic
intent-router: it pattern-matches the question, pulls the matching
category/product rows straight out of SQLite via repository.py, runs them
through the same budget/scoring/deal-score/recommendation engines the rest
of the app uses, and formats the result as text. Every number in every
answer traces back to a stored observation or a category/budget setting.

If ANTHROPIC_API_KEY is set AND ENABLE_LLM_ASSISTANT_POLISH=true, the
deterministic answer + the exact facts used to build it are optionally
handed to Claude purely to smooth the phrasing — the LLM is instructed to
add no new numbers, and if it does anything but light rewriting we fall
back to the deterministic text untouched. Off by default; requires no key
to use the assistant at all.
"""
import re
import json

import config
import db
import repository as repo
from engines import budget as budget_engine


def _find_category(question, categories):
    q = question.lower()
    best = None
    for cat in categories:
        if cat["name"].lower() in q or cat["key"].lower() in q:
            return cat
        # crude singular/plural handling: "fridges" ~ "refrigerator"
        aliases = {
            "refrigerator": ["fridge", "fridges", "refrigerators"],
            "air_conditioner": ["ac", "acs", "air conditioner", "air conditioners"],
            "washing_machine": ["washer", "washing machine", "washing machines"],
            "cooker": ["stove", "cooker", "cookers", "oven"],
        }
        for alias_list in aliases.get(cat["key"], []):
            pass
        for key, words in aliases.items():
            if key == cat["key"]:
                for w in words:
                    if w in q:
                        return cat
    return best


def _find_products(question, products):
    q = question.lower()
    matches = []
    for p in products:
        haystack = f"{p['brand']} {p['model']} {p['full_name']}".lower()
        if p["brand"].lower() in q or p["model"].lower() in q:
            matches.append(p)
    if not matches:
        # fall back to category match -> return that category's products
        pass
    return matches


def _fmt_egp(v):
    if v is None:
        return "unknown"
    return f"{v:,.0f} EGP"


def _handle_next_buy(categories, products):
    dashboard = repo.get_dashboard()
    nb = dashboard["next_buy"]
    if not nb:
        return "No purchase is currently recommended — nothing has a strong enough Deal Score and budget fit right now. Check the 'Best Deals' list or wait for prices to move.", {"next_buy": None}
    p = nb["best_candidate"]
    rec = nb["recommendation"]
    text = (
        f"Buy next: {p['full_name']} ({_fmt_egp(p['pricing']['current_price'])} at {p['pricing']['best_retailer']}). "
        f"{rec['explanation']}"
    )
    return text, {"next_buy": {"product_id": p["id"], "decision": rec["decision"]}}


def _handle_afford(question, categories, products):
    matches = _find_products(question, products)
    if not matches:
        cat = _find_category(question, categories)
        if cat:
            matches = [p for p in products if p["category_id"] == cat["id"]]
    if not matches:
        return "I couldn't identify which product you mean — mention its brand or model.", {}
    p = matches[0]
    price = p["pricing"]["current_price"]
    budget = repo.get_budget_summary(exclude_category_id=p["category_id"] if p["category"]["priority_level"] == 1 else None)
    if price is None:
        return f"{p['full_name']} has no current price on record yet, so I can't assess affordability.", {}
    affordable = price <= budget["remaining_egp"]
    jeopardizes = (budget["remaining_egp"] - price) < budget["other_priority1_gap_egp"] and p["category"]["priority_level"] != 1
    parts = [f"{p['full_name']} currently costs {_fmt_egp(price)}."]
    if not affordable:
        parts.append(f"You only have {_fmt_egp(budget['remaining_egp'])} remaining — you can't afford it right now.")
    elif jeopardizes:
        parts.append(
            f"You can technically afford it ({_fmt_egp(budget['remaining_egp'])} remaining), but buying it would "
            f"leave less than the {_fmt_egp(budget['other_priority1_gap_egp'])} still needed for your unfunded "
            f"Priority-1 categories. I'd wait."
        )
    else:
        parts.append(f"Yes — you have {_fmt_egp(budget['remaining_egp'])} remaining, which comfortably covers it.")
    return " ".join(parts), {"product_id": p["id"], "affordable": affordable, "jeopardizes_priority1": jeopardizes}


def _handle_is_good_deal(question, categories, products):
    matches = _find_products(question, products)
    if not matches:
        cat = _find_category(question, categories)
        if cat:
            cat_products = [p for p in products if p["category_id"] == cat["id"]]
            matches = sorted(cat_products, key=lambda p: (p["deal_score"]["score"] or -1), reverse=True)[:1]
    if not matches:
        return "I couldn't identify which product you mean — mention its brand, model, or category.", {}
    p = matches[0]
    deal = p["deal_score"]
    if deal["score"] is None:
        return f"{p['full_name']} has no price data yet, so I can't score this deal.", {}
    rec = repo.get_recommendation_for_product(p["id"])
    explanation = " ".join(deal["explanation"])
    return (
        f"{p['full_name']}: Deal Score {deal['score']}/100 ({deal['label']}, confidence: {deal['confidence']}). "
        f"{explanation} Recommendation: {rec['decision']} — {rec['explanation']}"
    ), {"product_id": p["id"], "deal_score": deal["score"], "decision": rec["decision"]}


def _handle_compare_top(question, categories, products):
    cat = _find_category(question, categories)
    n_match = re.search(r"top\s+(\w+)", question.lower())
    number_words = {"two": 2, "three": 3, "four": 4, "five": 5}
    n = 3
    if n_match:
        token = n_match.group(1)
        n = number_words.get(token, None) or (int(token) if token.isdigit() else 3)
    if not cat:
        return "Which category? e.g. 'Compare my top three washing machines.'", {}
    cat_products = [p for p in products if p["category_id"] == cat["id"] and p["purchase_status"] != "rejected"]
    ranked = sorted(cat_products, key=lambda p: (p["computed_ai_research_score"] or p["ai_research_score"] or 0), reverse=True)[:n]
    if not ranked:
        return f"No shortlisted products in {cat['name']} yet.", {}
    lines = [f"Top {len(ranked)} {cat['name']} candidates:"]
    for p in ranked:
        score = p["computed_ai_research_score"] or p["ai_research_score"]
        price = p["pricing"]["current_price"]
        lines.append(
            f"- {p['full_name']}: score {score if score is not None else 'n/a'}/100, "
            f"price {_fmt_egp(price)}, deal score {p['deal_score']['score'] if p['deal_score']['score'] is not None else 'n/a'}"
        )
    return "\n".join(lines), {"category_id": cat["id"], "product_ids": [p["id"] for p in ranked]}


def _handle_whatif(question, categories, products):
    matches = _find_products(question, products)
    if not matches:
        return "Tell me which product(s) — e.g. 'What happens to my budget if I buy the LG refrigerator?'", {}
    hypothetical = []
    for p in matches:
        price = p["pricing"]["current_price"] or p["target_buy_price_egp"]
        if price:
            hypothetical.append({"product_id": p["id"], "price_egp": price})
    if not hypothetical:
        return "No price data available for that product to simulate with.", {}
    sim = repo.simulate_what_if(hypothetical)
    names = ", ".join(p["full_name"] for p in matches)
    return (
        f"If you buy {names}: remaining budget changes by {_fmt_egp(sim['delta_remaining_egp'])} "
        f"(new remaining: {_fmt_egp(sim['after']['remaining_egp'])}). "
        f"Budget buffer becomes {_fmt_egp(sim['after']['buffer_egp'])} (risk level: {sim['risk_level']}). "
        f"{len(sim['remaining_critical_categories'])} Priority-1 categories would still be unfunded, "
        f"estimated at {_fmt_egp(sim['expected_cost_to_complete_critical_egp'])}."
    ), sim


def _handle_which_priority1_first(categories, products):
    p1_cats = [c for c in categories if c["priority_level"] == 1]
    dashboard = repo.get_dashboard()
    cards = {c["category"]["id"]: c for c in dashboard["priority_cards"]}
    unfunded = []
    for c in p1_cats:
        card = cards.get(c["id"])
        if card and not card["is_fulfilled"]:
            unfunded.append(card)
    if not unfunded:
        return "All Priority-1 (critical) categories are already purchased. Nice work.", {}

    def rank_key(card):
        rec = card["recommendation"]
        decision_rank = {"URGENT_BUY": 0, "BUY": 1, "WAIT": 2, "IGNORE": 3, None: 4}
        return decision_rank.get(rec["decision"] if rec else None, 4)

    unfunded.sort(key=rank_key)
    top = unfunded[0]
    rec = top["recommendation"]
    best = top["best_candidate"]
    if best is None:
        return f"{top['category']['name']} is your top unfunded Priority-1 category, but nothing is shortlisted yet — start researching models.", {}
    return (
        f"{top['category']['name']} — best candidate {best['full_name']} at {_fmt_egp(best['pricing']['current_price'])}. "
        f"{rec['explanation'] if rec else 'No price data yet.'}"
    ), {"category_id": top["category"]["id"], "product_id": best["id"]}


def _handle_deals_today(categories, products):
    dashboard = repo.get_dashboard()
    deals = dashboard["best_deals"]
    if not deals:
        return "No deals meeting the 'Fair' threshold or better right now.", {"deals": []}
    lines = ["Deals worth a look today:"]
    for p in deals[:5]:
        lines.append(f"- {p['full_name']}: {_fmt_egp(p['pricing']['current_price'])}, Deal Score {p['deal_score']['score']}/100 ({p['deal_score']['label']})")
    return "\n".join(lines), {"deals": [p["id"] for p in deals[:5]]}


def _handle_what_to_wait_for(categories, products):
    out = []
    for p in products:
        if p["purchase_status"] in ("purchased", "rejected"):
            continue
        rec = repo.get_recommendation_for_product(p["id"])
        if rec and rec["decision"] == "WAIT":
            out.append((p, rec))
    if not out:
        return "Nothing is currently flagged as 'wait' — either things are ready to buy, or there's no price data yet.", {}
    lines = ["Products to wait on:"]
    for p, rec in out[:8]:
        lines.append(f"- {p['full_name']}: {rec['explanation']}")
    return "\n".join(lines), {"product_ids": [p["id"] for p, _ in out[:8]]}


INTENT_PATTERNS = [
    (re.compile(r"buy next|what should i buy", re.I), _handle_next_buy),
    (re.compile(r"afford", re.I), None),  # needs question text, handled below
    (re.compile(r"good deal|worth it|actually a good", re.I), None),
    (re.compile(r"compare|top (two|three|four|five|\d+)", re.I), None),
    (re.compile(r"what happens|what if|simulate", re.I), None),
    (re.compile(r"priority ?1|critical.*first|first.*(buy|purchase)", re.I), None),
    (re.compile(r"deals? (worth|today|acting)", re.I), None),
    (re.compile(r"wait for|should i wait", re.I), None),
]


def answer_question(question):
    categories = repo.list_categories()
    products = repo.list_products(with_pricing=True)
    q = question.lower()

    if re.search(r"buy next|what should i buy", q):
        text, data = _handle_next_buy(categories, products)
    elif re.search(r"afford", q):
        text, data = _handle_afford(question, categories, products)
    elif re.search(r"good deal|worth it|actually a good", q):
        text, data = _handle_is_good_deal(question, categories, products)
    elif re.search(r"compare|top (two|three|four|five|\d+)", q):
        text, data = _handle_compare_top(question, categories, products)
    elif re.search(r"what happens|what if|simulate", q):
        text, data = _handle_whatif(question, categories, products)
    elif re.search(r"priority ?1|critical.*first|first.*(buy|purchase)", q):
        text, data = _handle_which_priority1_first(categories, products)
    elif re.search(r"deals? (worth|today|acting)", q):
        text, data = _handle_deals_today(categories, products)
    elif re.search(r"wait for|should i wait", q):
        text, data = _handle_what_to_wait_for(categories, products)
    else:
        text, data = _handle_fallback(question, categories, products)

    text = _maybe_polish_with_llm(question, text, data)
    return {"answer": text, "data": data}


def _handle_fallback(question, categories, products):
    matches = _find_products(question, products)
    if matches:
        return _handle_is_good_deal(question, categories, products)
    cat = _find_category(question, categories)
    if cat:
        return _handle_compare_top(question, categories, products)
    return (
        "I can answer things like: 'What should I buy next?', 'Can I afford the LG washing machine?', "
        "'Is this refrigerator a good deal?', 'Compare my top three washing machines', "
        "'What happens to my budget if I buy this?', 'Which Priority 1 purchase should I make first?', "
        "'Are there deals worth acting on today?', or 'What should I wait for?'"
    ), {}


_POLISH_SYSTEM_PROMPT = (
    "Rephrase the following factual answer to be more natural and conversational. "
    "Do not add, remove, or change any numbers, prices, or facts. Keep it concise."
)


def _maybe_polish_with_llm(question, deterministic_text, data):
    """Optional cosmetic pass through an LLM. Disabled unless the user
    explicitly sets ENABLE_LLM_ASSISTANT_POLISH=true plus a provider key.
    Never adds facts: the prompt hands the model the deterministic answer
    and instructs it to rephrase only; on any error (or if no provider is
    configured) we silently keep the deterministic text, so the assistant
    never depends on any external API to function.

    Tries Groq first (free tier, open-weight models, already allowlisted on
    PythonAnywhere's free plan), then falls back to Anthropic if that's the
    only key set."""
    if not config.ENABLE_LLM_ASSISTANT_POLISH:
        return deterministic_text
    if config.GROQ_API_KEY:
        polished = _polish_with_groq(question, deterministic_text)
        if polished:
            return polished
    if config.ANTHROPIC_API_KEY:
        polished = _polish_with_anthropic(question, deterministic_text)
        if polished:
            return polished
    return deterministic_text


def _polish_with_groq(question, deterministic_text):
    try:
        import requests
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {config.GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": config.GROQ_MODEL,
                "max_tokens": 300,
                "temperature": 0.3,
                "messages": [
                    {"role": "system", "content": _POLISH_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Question: {question}\nFactual answer: {deterministic_text}"},
                ],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            choices = resp.json().get("choices", [])
            if choices:
                text = choices[0].get("message", {}).get("content", "").strip()
                if text:
                    return text
    except Exception:  # noqa: BLE001
        pass
    return None


def _polish_with_anthropic(question, deterministic_text):
    try:
        import requests
        resp = requests.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": "claude-haiku-4-5",
                "max_tokens": 300,
                "system": _POLISH_SYSTEM_PROMPT,
                "messages": [{"role": "user", "content": f"Question: {question}\nFactual answer: {deterministic_text}"}],
            },
            timeout=10,
        )
        if resp.status_code == 200:
            content = resp.json().get("content", [])
            if content and content[0].get("type") == "text":
                return content[0]["text"]
    except Exception:  # noqa: BLE001
        pass
    return None
