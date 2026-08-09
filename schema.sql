-- Home Purchase Intelligence Dashboard — SQLite schema
-- Design notes:
--   * SQLite via Python's stdlib sqlite3 (no extra dependency, fully
--     portable, trivially backed up as a single file). See README for why
--     this was chosen over Postgres for a single-user personal app.
--   * JSON-ish list/dict fields are stored as TEXT containing JSON, read
--     with json.loads/json.dumps in db.py. SQLite has no native JSON type;
--     this keeps the schema simple while remaining queryable enough (we
--     never need to filter/aggregate inside these blobs).
--   * Timestamps are stored as ISO-8601 strings (UTC) for easy sorting and
--     human readability in a quick `sqlite3` shell inspection.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS categories (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    key                 TEXT NOT NULL UNIQUE,        -- e.g. 'refrigerator'
    name                TEXT NOT NULL,                -- e.g. 'Refrigerator'
    icon                TEXT DEFAULT '',
    priority_level      INTEGER NOT NULL DEFAULT 2,   -- 1=critical 2=important 3=convenience
    sort_order          INTEGER NOT NULL DEFAULT 0,
    target_budget_egp   REAL NOT NULL DEFAULT 0,
    must_have_features  TEXT NOT NULL DEFAULT '[]',   -- JSON array of strings
    notes               TEXT NOT NULL DEFAULT '',
    scoring_weights     TEXT NOT NULL DEFAULT '{}',   -- JSON dict, falls back to DEFAULT_SCORING_WEIGHTS
    scoring_dimensions  TEXT NOT NULL DEFAULT '[]',   -- JSON array describing category-specific criteria (for display)
    is_archived         INTEGER NOT NULL DEFAULT 0,
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retailers (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    key                 TEXT NOT NULL UNIQUE,        -- 'btech', 'amazon_eg', ...
    name                TEXT NOT NULL,
    base_url            TEXT NOT NULL DEFAULT '',
    provider_key        TEXT NOT NULL DEFAULT 'manual', -- matches providers/registry.py
    credibility_score   INTEGER NOT NULL DEFAULT 70, -- 0-100, manually assessed trustworthiness
    notes               TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS products (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    category_id                 INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    brand                        TEXT NOT NULL,
    model                        TEXT NOT NULL,        -- primary matching signal
    sku                          TEXT DEFAULT '',
    full_name                    TEXT NOT NULL,
    image_url                    TEXT DEFAULT '',
    capacity                     TEXT DEFAULT '',       -- '506L' / '1.5 HP' / '8kg' etc
    specs                        TEXT NOT NULL DEFAULT '{}',  -- JSON dict
    warranty_years               REAL DEFAULT 0,
    features                     TEXT NOT NULL DEFAULT '[]',  -- JSON array
    pros                         TEXT NOT NULL DEFAULT '[]',  -- JSON array
    cons                         TEXT NOT NULL DEFAULT '[]',  -- JSON array
    reliability_assessment       TEXT DEFAULT '',
    egypt_service_assessment     TEXT DEFAULT '',
    score_breakdown              TEXT NOT NULL DEFAULT '{}',  -- JSON dict of dimension -> 0-100
    ai_research_score            REAL DEFAULT NULL,      -- 0-100, computed from score_breakdown + category weights
    user_score                   REAL DEFAULT NULL,      -- 0-100, user's own opinion, optional
    target_buy_price_egp         REAL DEFAULT NULL,
    purchase_status               TEXT NOT NULL DEFAULT 'researching',
        -- researching | shortlisted | watching | ready_to_buy | purchased | rejected
    is_demo_data                 INTEGER NOT NULL DEFAULT 0,  -- 1 = seeded with an unverified/estimated price
    created_at                   TEXT NOT NULL,
    updated_at                   TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_products_category ON products(category_id);
CREATE INDEX IF NOT EXISTS idx_products_status ON products(purchase_status);
CREATE INDEX IF NOT EXISTS idx_products_brand_model ON products(brand, model);

CREATE TABLE IF NOT EXISTS product_listings (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    retailer_id         INTEGER NOT NULL REFERENCES retailers(id) ON DELETE CASCADE,
    url                 TEXT DEFAULT '',
    match_confidence    TEXT NOT NULL DEFAULT 'uncertain',
        -- exact_model | sku | brand_model | spec_similarity | uncertain
    is_active           INTEGER NOT NULL DEFAULT 1,
    created_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_listings_product ON product_listings(product_id);
CREATE INDEX IF NOT EXISTS idx_listings_retailer ON product_listings(retailer_id);

CREATE TABLE IF NOT EXISTS price_observations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER NOT NULL REFERENCES product_listings(id) ON DELETE CASCADE,
    price_egp       REAL NOT NULL,
    availability    TEXT NOT NULL DEFAULT 'unknown',  -- in_stock | out_of_stock | unknown
    observed_at     TEXT NOT NULL,
    source          TEXT NOT NULL DEFAULT 'manual',   -- 'manual' or a provider_key
    is_verified     INTEGER NOT NULL DEFAULT 1,       -- 0 = estimated/demo, not a real fetched price
    raw_note        TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_priceobs_listing_time ON price_observations(listing_id, observed_at);

CREATE TABLE IF NOT EXISTS purchase_plans (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    planned_price_egp   REAL NOT NULL,
    status              TEXT NOT NULL DEFAULT 'planned', -- planned | committed | cancelled
    created_at          TEXT NOT NULL,
    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_plans_product ON purchase_plans(product_id);

CREATE TABLE IF NOT EXISTS purchases (
    id                          INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id                  INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    retailer_id                 INTEGER REFERENCES retailers(id),
    purchase_price_egp          REAL NOT NULL,
    purchase_date                TEXT NOT NULL,
    warranty_period_months       INTEGER DEFAULT 0,
    invoice_number                TEXT DEFAULT '',
    notes                        TEXT DEFAULT '',
    created_at                  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_purchases_product ON purchases(product_id);

CREATE TABLE IF NOT EXISTS alerts (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id          INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    listing_id          INTEGER REFERENCES product_listings(id),
    alert_type          TEXT NOT NULL,
        -- below_target | drop_10pct | new_low | exceptional_deal | high_priority_sale | back_in_stock
    message             TEXT NOT NULL,
    price_at_alert      REAL,
    deal_score_at_alert REAL,
    recommendation      TEXT DEFAULT '',
    triggered_at        TEXT NOT NULL,
    dedup_key           TEXT NOT NULL,   -- prevents re-alerting on an unchanged condition
    is_read             INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_alerts_product_time ON alerts(product_id, triggered_at);
CREATE UNIQUE INDEX IF NOT EXISTS idx_alerts_dedup ON alerts(dedup_key);

CREATE TABLE IF NOT EXISTS notification_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_id    INTEGER NOT NULL REFERENCES alerts(id) ON DELETE CASCADE,
    channel     TEXT NOT NULL DEFAULT 'in_app',
    sent_at     TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'sent',  -- sent | failed | skipped
    detail      TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_notif_alert ON notification_history(alert_id);

CREATE TABLE IF NOT EXISTS research_sources (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id      INTEGER REFERENCES products(id) ON DELETE CASCADE,
    listing_id      INTEGER REFERENCES product_listings(id) ON DELETE CASCADE,
    url             TEXT DEFAULT '',
    retailer        TEXT DEFAULT '',
    retrieved_at    TEXT NOT NULL,
    confidence      TEXT NOT NULL DEFAULT 'verified',  -- verified | estimated | range
    note            TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_sources_product ON research_sources(product_id);

CREATE TABLE IF NOT EXISTS settings (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL   -- JSON-encoded
);

CREATE TABLE IF NOT EXISTS price_check_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id      INTEGER REFERENCES product_listings(id) ON DELETE CASCADE,
    ran_at          TEXT NOT NULL,
    status          TEXT NOT NULL,   -- ok | failed | skipped_unsupported
    detail          TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_checklog_listing ON price_check_log(listing_id);

-- "Who did what" activity feed — this is a shared household tool (not
-- multi-account auth, see README Security), so "identity" here is just a
-- display name someone picks in the top bar (stored in their browser
-- session cookie), not a password-protected account. Good enough to answer
-- "did you add this or did she?" without building real user accounts.
CREATE TABLE IF NOT EXISTS activity_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    actor           TEXT NOT NULL DEFAULT 'Someone',
    action          TEXT NOT NULL,   -- added | updated_status | updated_target | priced | purchased | wishlisted
    entity_type     TEXT NOT NULL DEFAULT 'product',
    entity_id       INTEGER,
    summary         TEXT NOT NULL,
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_activity_time ON activity_log(created_at);
