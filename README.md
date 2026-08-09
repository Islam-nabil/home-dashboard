# Home Purchase Intelligence Dashboard

A personal dashboard for managing a **180,000 EGP** home-appliance budget in
Egypt: what you still need, what it's worth, whether today's price is
actually a good deal, and whether buying it jeopardizes money you're
holding for something more important.

This is not a CRUD demo. It has a real budget/priority engine, a
transparent weighted product-scoring system, a Deal Score that refuses to
trust retailer "SALE" badges, a budget-aware BUY/WAIT/IGNORE/URGENT_BUY
recommendation engine, a per-retailer price-monitoring architecture, a
dedup'd alert system, and a rule-based purchasing assistant — all backed by
28 passing unit tests and seeded with real researched Egyptian retail
prices (see [Seed data](#seed-data--what-is-real-vs-demo)).

---

## 1. Why this stack (read this first)

The spec suggested Next.js/Prisma/Postgres. This build environment turned
out to have **no outbound network access to npm, PyPI, or any CDN** — `npm
install`, `pip install <anything not already present>`, and even
`<script src="cdn...">` all fail here. Rather than hand you an
architecture that can't actually run, I built this as:

- **Backend:** Flask (Python stdlib + Flask + Jinja2 — all pre-installed,
  zero install step needed)
- **Database:** SQLite via Python's built-in `sqlite3` module — no server
  to run, no ORM dependency, the whole database is one file
  (`data/dashboard.db`) you can back up by copying it
- **Frontend:** Server-rendered Jinja2 templates + hand-written vanilla
  JS/CSS — no build step, no bundler, no CDN dependency. Tables sort/filter
  in the browser, the price chart is drawn on a `<canvas>` with ~40 lines
  of JS, no chart library needed.
- **Tests:** Python's built-in `unittest` (no pytest install needed)

This is a legitimate engineering choice even outside this sandbox: it's a
**single-user personal tool**. Postgres + Prisma + a Next.js build pipeline
would be pure overhead here. SQLite handles this data volume trivially,
Flask needs no build step, and the whole app runs with `python app.py` on
any machine with Python 3.9+ — no `npm install`, no Docker, nothing to go
stale. If you later want to deploy this multi-user or want a richer
frontend, the engine/repository/route layers are cleanly separated (see
[Architecture](#3-architecture)) so swapping the persistence layer or
bolting a JS frontend onto the JSON API doesn't require rewriting the
business logic.

**requests / beautifulsoup4 / lxml** (used for real-world price scraping)
happened to already be installed in this sandbox too — see
[Scheduled price monitoring](#8-scheduled-price-monitoring) for what that
does and doesn't mean for you.

---

## 2. Quick start

```bash
cd home-dashboard
pip install -r requirements.txt      # usually a no-op — see requirements.txt
cp .env.example .env                 # optional, every setting has a default
python scripts/run_seed.py           # creates data/dashboard.db and seeds it (idempotent)
python app.py                        # http://127.0.0.1:5000
```

Run the tests:

```bash
python -m unittest discover -s tests -t .
```

Run a price check by hand (also available as a button on the Settings
page, or `POST /api/price-check/run`):

```bash
python scripts/run_price_check.py
```

That's the entire setup. No database server, no build step, no API keys
required for any of this to work.

---

## 3. Architecture

```
config.py            Central config, all from env vars with defaults (never hard-coded secrets)
schema.sql            SQLite schema (10 tables, see below)
db.py                  Thin sqlite3 wrapper (per-thread connections, JSON field helpers)
repository.py          Turns raw rows into the shapes engines/ expects, and back into API dicts
engines/                Pure, dependency-free, fully unit-tested business logic
  budget.py               Budget/priority math (spent/committed/remaining/buffer, what-if simulation)
  scoring.py               Product Score: transparent weighted average across 7 dimensions
  deal_score.py             Deal Score: 0-100, confidence-capped on thin price history
  recommendation.py          BUY / WAIT / IGNORE / URGENT_BUY, budget- and priority-aware
  matching.py                 Product matching confidence (SKU > model > brand+model > specs > uncertain)
  alerts.py                    Alert condition evaluation + spam-prevention dedup logic
providers/               Per-retailer price-fetch adapters behind one interface (PriceProvider)
  base.py / manual.py / generic_html.py / retailers.py / registry.py
price_check.py         Orchestrates the scheduled monitoring pipeline (spec section 20's 11 steps)
notify.py               Notification channels (in_app always works; email/telegram if configured)
assistant.py            Deterministic Q&A router — reasons over the DB, never invents a price
wishlist.py              Paste-a-URL best-effort extraction + product matching
seed.py                  Real (+ clearly labeled demo) seed data, idempotent
routes/
  pages.py                 Server-rendered HTML pages
  api.py                     JSON API (used by both the pages' JS and anything else you build)
templates/, static/     Jinja2 templates, hand-written CSS/JS (no CDN, no build step)
tests/                  28 unit tests over every engine
```

**Why the engines are separated from Flask:** `engines/*.py` have zero
Flask/DB imports — they're plain functions taking/returning dicts. That's
what makes `tests/` fast (no test database, no HTTP) and it's what makes
the logic reusable if you ever want to run it outside a web request (e.g.
a cron job, a CLI report).

### Database schema

`categories`, `retailers`, `products`, `product_listings`,
`price_observations`, `purchase_plans`, `purchases`, `alerts`,
`notification_history`, `research_sources`, `settings`, `price_check_log`
— see `schema.sql` for full column definitions, foreign keys, and indexes.
Key relationships: a `product` belongs to a `category` and has many
`product_listings` (one per retailer it's tracked at); each listing has
many `price_observations` over time. A `purchase` references the `product`
it was bought as. Everything is indexed on its obvious foreign key +
time-ordering column.

---

## 4. The budget & priority engine

Editable, reorderable categories (`/settings`, or `PUT /api/categories/<id>`),
each with a `priority_level` (1=Critical, 2=Important, 3=Convenience), a
`target_budget_egp`, must-have features, notes, and its own scoring weights.

The header numbers (`engines/budget.py::compute_budget`):

- **Spent** — sum of `purchases.purchase_price_egp`
- **Committed** — current/target price of anything marked `ready_to_buy`
  but not yet purchased
- **Remaining** — Total − Spent − Committed
- **Estimated Remaining Essentials** — for every Priority-1 category with
  no purchase yet, the cheapest current price among its shortlisted
  products (falling back to the cheapest target price, then the category's
  target budget)
- **Budget Buffer** — Remaining − Estimated Remaining Essentials (this is
  the number that goes negative when you're about to overspend on
  non-essentials)
- **Percent complete** — categories with a purchase / total categories

The **What If? simulator** (`POST /api/whatif`, also driven from the
assistant) reuses the exact same function against a hypothetical purchase
list, so "what happens to my budget if I buy this" always matches reality.

---

## 5. Product Score (transparent, configurable, never a black box)

`engines/scoring.py` computes a 0-100 score as a weighted average across 7
dimensions: reliability, price/value, warranty & service in Egypt, energy
efficiency, core performance, features, user preference. Default weights
live in `config.DEFAULT_SCORING_WEIGHTS`; every category can override them
(`categories.scoring_weights`, edit via `PUT /api/categories/<id>`).

If a product hasn't been scored on every dimension, the engine
**renormalizes over only the dimensions actually assessed** rather than
silently treating missing ones as zero — see `test_missing_dimensions_are_
renormalized_not_zeroed`. The product page's "Product Score Methodology"
card shows every dimension's raw score, its effective weight, and its
contribution, so the number is always auditable, never a guess presented
as fact.

---

## 6. Deal Score — the part that resists hype

A "SALE" sticker is not evidence. `engines/deal_score.py` computes 0-100
from six weighted, explained sub-scores: price vs. historical average,
price vs. historical low, price vs. your target, discount vs. the most
recent "normal" price, the product's own quality score, and retailer
credibility.

Two anti-hype mechanisms:

1. **Confidence capping.** A listing with 0-1 verified observations is
   capped below the "Exceptional" band (90+) — a single data point can
   support "this is fair/good," never "this is exceptional," because
   there's no history to back that claim. 2 observations cap slightly
   lower than full confidence. The cap relaxes as real observations
   accumulate.
2. **Implausible-drop flagging.** A single-step price drop over ~35% with
   real history behind it gets an explicit "double-check this isn't a
   listing error" note instead of an uncritical "amazing deal."

Labels: 90-100 Exceptional · 75-89 Good Buy · 60-74 Fair Price · 40-59
Wait · 0-39 Poor Deal (thresholds are env-configurable, see
`.env.example`).

---

## 7. The Decision Engine (BUY / WAIT / IGNORE / URGENT_BUY)

`engines/recommendation.py` is deliberately budget-aware, not just a
relabeling of the Deal Score. The rule that matters most: **a good
discount on a low-priority item must not be recommended if buying it would
eat into the budget still needed for unfunded Priority-1 categories.**
This is directly unit-tested
(`test_critical_scenario_microwave_good_discount_but_jeopardizes_priority1_is_not_buy`)
using the exact scenario from the spec: a discounted microwave that would
leave insufficient budget for a critical appliance gets WAIT/IGNORE, never
BUY, regardless of how good its own Deal Score is.

Conversely, a Priority-1 item at Deal Score ≥ 90 with budget room becomes
`URGENT_BUY`. Every decision returns a plain-English `explanation` string
built from the same numbers that produced it — never a hidden heuristic.

---

## 8. Scheduled price monitoring

`price_check.py::run_price_check()` implements the full pipeline: load
active listings → fetch (where a listing isn't manual) → normalize →
compare to the previous observation → store → recompute Deal Score →
evaluate alert conditions → create deduplicated alerts → log every attempt
(success or failure) to `price_check_log`. One retailer's page changing
its HTML only breaks that one listing's check — every fetch is wrapped in
try/except and logged, never allowed to crash the run.

**Retailer providers** (`providers/`): each retailer is its own thin
adapter over `GenericHtmlProvider`, which:
1. Checks `robots.txt` via `urllib.robotparser` before fetching anything,
   and refuses if disallowed.
2. Makes one polite, rate-limited, identified (`User-Agent`) GET request.
3. Extracts price from JSON-LD Product/Offer structured data first (most
   sites with basic SEO emit this), then Open Graph/meta price tags, then
   a short list of common CSS price-class selectors.
4. **Does not** run a headless browser, solve CAPTCHAs, rotate proxies, or
   retry past a 403/429 — if a site blocks a plain `requests` GET, the
   listing just falls back to manual tracking. This is intentional, not a
   bug: the spec explicitly asks for no anti-bot bypassing.

**Manual tracking is the guaranteed-available fallback** for every
retailer — `POST /api/products/<id>/price` (also a form on the product
page) lets you type in a price you saw yourself. This is retailer
key `manual` / provider tier 5, and it's what most listings will
realistically use unless you deploy somewhere with normal internet access
and verify the automated adapters against the live sites.

**Important honesty note about this build environment specifically:**
outbound HTTP to arbitrary third-party hosts (btech.com, amazon.eg, etc.)
is blocked in the sandbox this app was built in — verified directly (see
`providers/generic_html.py`'s docstring). The automated providers are
fully implemented and will start working the moment you run this
somewhere with normal internet access (your own machine, a VPS, etc.), but
**they were not live-tested against the real retailer sites during this
build** — the seed data's prices came from Claude's web-search tool (a
different, sandboxed research path), not from this app's own fetch code.
Treat the automated adapters as "implemented, verify on first real run,"
and lean on manual price entry until you've confirmed they work against
each site's current markup.

**Running it on a schedule:** this sandbox cannot run a persistent
background cron (the session ends and any in-process scheduler goes with
it), so scheduling is left as a real OS-level job for wherever you deploy:

```cron
# every 12 hours
0 */12 * * * cd /path/to/home-dashboard && /usr/bin/python3 scripts/run_price_check.py >> price_check.log 2>&1
```

Or any equivalent (systemd timer, Render/Railway cron, GitHub Actions
schedule hitting `POST /api/price-check/run`, etc). Until you set one up,
the "Run price check now" button on the Settings page does the same thing
on demand.

**Adding another retailer:** create a class in `providers/retailers.py`
subclassing `GenericHtmlProvider` (or `PriceProvider` directly for a
retailer with a real API), register it in `providers/registry.py`'s
`_PROVIDERS` dict, and add a row via `POST /api/retailers` with the
matching `provider_key`. If the generic JSON-LD/meta/CSS extraction
doesn't find that site's price, override `fetch()` with a
site-specific selector.

---

## 9. Alerts & notifications

`engines/alerts.py` evaluates six alert types (below_target, drop_10pct,
new_low, exceptional_deal, high_priority_sale, back_in_stock) and — this
is the part that prevents spam — only re-fires a "still true" style alert
(below_target/exceptional_deal/high_priority_sale) if the price has moved
≥2% since the last alert of that type, and only re-fires `new_low` if the
price is strictly lower than the last alert's recorded low. A price
sitting flat under your target will not re-notify you every single check.
`make_dedup_key()` additionally guards against literal duplicate rows if
a check runs twice against unchanged data.

**Channels:** `in_app` always works (every alert is stored and shown on
`/alerts` and the dashboard). `email` and `telegram` are real, working
senders that activate the moment you set `SMTP_*`/`TELEGRAM_*` env vars —
see `.env.example`. `whatsapp` is deliberately not implemented: the only
legitimate path is the paid WhatsApp Business Cloud API requiring a Meta
developer account, out of scope for a v1 personal tool with no such
account — this is documented rather than faked.

---

## 10. AI Purchasing Assistant

`assistant.py` is a deterministic intent router, **not** a wrapper that
lets an LLM invent prices. It pattern-matches your question, pulls the
matching category/product rows straight from SQLite, runs them through the
exact same budget/scoring/deal-score/recommendation engines the rest of
the app uses, and formats the result as text — every number in every
answer traces back to a stored observation or a budget setting.

Supported today: "What should I buy next?", "Can I afford the LG washing
machine?", "Is this refrigerator a good deal?", "Compare my top three
washing machines", "What happens to my budget if I buy this?", "Which
Priority 1 purchase should I make first?", "Are there deals worth acting
on today?", "What should I wait for?"

If you set `ANTHROPIC_API_KEY` and `ENABLE_LLM_ASSISTANT_POLISH=true`, the
deterministic answer is optionally passed through the real Claude API
purely to smooth its phrasing (the prompt explicitly forbids adding new
numbers); on any error it silently falls back to the deterministic text.
Off by default — the assistant is fully useful with zero API key.

---

## 11. Seed data — what is real vs. demo

Real, retailer-verified prices were gathered via live web research on
**2026-08-09** for Refrigerators, Cookers/Stoves, Air Conditioners, and
Washing Machines (17 of 21 seeded products) — each has a `research_sources`
entry with the actual retailer and URL. Where no verified single price
could be found (a few cooker variants), the product is flagged
`is_demo_data=1` with a range-estimate midpoint and shows a **DEMO** badge
in the UI — never presented as a real market price.

**TV, Water Heater, Microwave, and Air Fryer** had no live research
performed in v1 (out of scope for the initial 4 core categories the spec
emphasized) — every product in these categories is a clearly labeled DEMO
placeholder, included so all three priority tiers have a working example
of the full system, not to be trusted as real pricing. Replace them via
the Wishlist importer or `POST /api/products` once you've done real
research.

**Why the dashboard shows "WAIT" on everything at first.** Deal Score
confidence is capped hard on thin price history (see section 6). A
freshly seeded product has 0-1 real observations, so it correctly can't
earn an "Exceptional" score or an unqualified BUY yet — that's the
anti-hype design working as intended, not a bug. As you run price checks
(or log prices manually) over days/weeks, real history accumulates,
confidence caps relax, and BUY/URGENT_BUY recommendations become
reachable. The Samsung washing machine already ships with two real data
points (its listed vs. discounted price, both verified) as a small
built-in example of how the system looks once there's real history.

---

## 12. Testing

```bash
python -m unittest discover -s tests -t .
```

28 tests across every engine: budget math (spent/committed/remaining/
buffer, the what-if simulator), product scoring (weighted average,
renormalization over missing dimensions), Deal Score (new-low + below-
target scoring high, thin-data confidence capping, quality dragging down
an otherwise-good discount), the Decision Engine (including the exact
"microwave discount shouldn't jeopardize the refrigerator budget"
scenario from the spec, and "refrigerator at a historical low with budget
room becomes URGENT_BUY"), product matching (SKU/model/brand+model/spec
confidence tiers, never silently merging unrelated products), and alert
deduplication (no repeat alerts on an unchanged price, `new_low` requires
a strictly lower price than the last alert).

---

## 13. Configuration

Everything in `config.py` reads from an environment variable with a
default — copy `.env.example` to `.env` and edit. Nothing is hard-coded:
`TOTAL_BUDGET_EGP`, price-check frequency, Deal Score thresholds,
notification channels + credentials, and `SECRET_KEY` are all
externalized. No API key is required for the app to be fully functional —
`ANTHROPIC_API_KEY` is strictly optional cosmetic polish for the
assistant.

---

## 14. Deployment

This is a plain Flask app — deploy it anywhere Python runs. The one thing
that matters most for THIS app: the database is a single SQLite **file**
(`data/dashboard.db`). Any host that wipes its filesystem between requests
or on every restart will silently lose your price history, wishlist, and
purchases. That rules out most "free" PaaS web-service tiers (Render,
Railway, Fly.io free tiers do **not** include a persistent disk — you'd
need to pay a few $/month for one). The recommended free option below
avoids that trap entirely.

### Recommended free option: PythonAnywhere

PythonAnywhere's free tier gives you a real, always-there Linux home
directory (files persist forever, no surprise resets) and a free
`<you>.pythonanywhere.com` subdomain — a good fit for a small single-user
Flask + SQLite app like this one.

1. Create a free account at pythonanywhere.com.
2. **Upload the code.** Easiest path: push this folder to a GitHub repo,
   then in a PythonAnywhere Bash console run `git clone <your-repo-url>`.
   (Or use their "Files" tab to upload a zip and unzip it.)
3. Open a Bash console in PythonAnywhere and install dependencies into a
   virtualenv:
   ```
   cd home-dashboard
   python3.10 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   cp .env.example .env   # then edit .env: set SECRET_KEY, and
                           # BASIC_AUTH_USERNAME/PASSWORD if you want a
                           # password prompt (recommended — see below)
   python scripts/run_seed.py   # first time only, populates the DB
   ```
4. Go to the **Web** tab → "Add a new web app" → choose **Manual
   configuration** (not "Flask", since we already have our own `app.py`) →
   pick the same Python version as your venv.
5. Set the **virtualenv** path to `/home/<you>/home-dashboard/venv`.
6. Edit the generated **WSGI configuration file** (linked from the Web
   tab) so it imports this app:
   ```python
   import sys
   path = '/home/<you>/home-dashboard'
   if path not in sys.path:
       sys.path.insert(0, path)
   from app import app as application
   ```
7. Click **Reload**. Your dashboard is live at `https://<you>.pythonanywhere.com`.
8. (Optional but recommended for a public link) Set `BASIC_AUTH_USERNAME`
   / `BASIC_AUTH_PASSWORD` in `.env` before reloading — this puts a simple
   username/password prompt in front of the whole app, since it'll have
   your household budget on a public URL.
9. **Scheduled price checks:** the Free plan includes one scheduled task
   slot (Tasks tab) — point it at
   `/home/<you>/home-dashboard/venv/bin/python /home/<you>/home-dashboard/scripts/run_price_check.py`
   once a day. (Free-tier tasks run once/day; paid tiers allow hourly.)

### Other options

- **Your own machine / a VPS:** `pip install -r requirements.txt &&
  gunicorn -w 2 -b 0.0.0.0:8000 app:app` behind whatever reverse proxy/TLS
  you prefer (or just `python app.py` on your home network — this is what
  "run it locally and share on WiFi" means in practice).
- **Render/Railway/Fly.io:** works the same way (`gunicorn app:app`,
  env vars from `.env.example`) but **you must attach a persistent disk**
  mounted at `data/` (a small paid add-on on these platforms) or the
  database resets on every deploy/restart. Also add a scheduled job
  hitting `python scripts/run_price_check.py` or `POST
  /api/price-check/run` for automated price monitoring.
- **Single-user only, no accounts/login system** — see
  [Security](#15-security--privacy). The optional Basic Auth gate above is
  the recommended minimum if the URL is reachable from the internet.

---

## 15. Security & privacy

Personal single-user app, deliberately not over-engineered with
enterprise auth. What IS in place: no hard-coded credentials anywhere
(everything sensitive is `os.environ.get(...)`, see `config.py`), all
database access goes through parameterized queries (`db.py` — no string-
formatted SQL), external data (scraped HTML, pasted URLs) is parsed
defensively and never `eval`'d, and no API key is ever sent to the browser
(the assistant's optional LLM call happens server-side only). If you
deploy this somewhere reachable from the internet, put it behind your own
auth (a reverse proxy with basic auth, a VPN, Tailscale, etc.) — the app
itself has no login screen.

---

## 16. Current limitations

- **Automated retailer price fetching is implemented but unverified live**
  against the real sites (see section 8) — this sandbox has no outbound
  access to test against btech.com/noon.com/etc. Budget time to verify/
  tune the CSS selectors in `providers/generic_html.py` against each
  site's actual current markup after you deploy somewhere with normal
  internet access.
- **No persistent background scheduler ships built-in** — you provide the
  cron/systemd timer/PaaS scheduled job (section 8). This is a correct
  architectural choice, not a shortcut: a web app process shouldn't also
  be its own cron daemon.
- **TV / Water Heater / Microwave / Air Fryer have zero live research** —
  demo placeholders only (section 11).
- **Single user, no auth** — by design for v1 (section 15).
- **WhatsApp notifications not implemented** — no legitimate free path
  without a Meta Business account (section 9).
- **The LLM assistant polish is unused by default** — no API key is
  shipped or required; enabling it is your choice.
- Currency conversion isn't handled — everything assumes EGP throughout.

## 17. Recommended next improvements

1. Verify and tune `providers/generic_html.py` selectors against each real
   retailer once deployed with normal internet access; add retailer-
   specific overrides where the generic JSON-LD/meta approach misses.
2. Do the live research pass for TV/Water Heater/Microwave/Air Fryer and
   replace the demo placeholders.
3. Wire up a real scheduler (cron/systemd/PaaS) per section 8.
4. Add a lightweight login (even just HTTP basic auth via the reverse
   proxy) before exposing this outside your home network.
5. If you outgrow SQLite (unlikely for one household), the
   engines/repository split means swapping in Postgres only touches
   `db.py` + `schema.sql`.
