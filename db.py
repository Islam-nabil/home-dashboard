"""
Thin data-access layer over stdlib sqlite3.

No ORM is used (SQLAlchemy isn't available in this environment and, for a
single-user personal app with ~10 tables, raw SQL behind small typed helper
functions is easier to audit and just as maintainable). Every function here
returns plain dicts (via sqlite3.Row) so route handlers can json.dumps them
directly.
"""
import sqlite3
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime, timezone

import config

_local = threading.local()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_dir():
    os.makedirs(os.path.dirname(config.DATABASE_PATH), exist_ok=True)


def get_conn():
    """Return a connection cached per-thread (Flask's dev server is
    multi-threaded by default; sqlite3 connections are not thread-safe to
    share, so we keep one per thread)."""
    conn = getattr(_local, "conn", None)
    if conn is None:
        _ensure_dir()
        conn = sqlite3.connect(config.DATABASE_PATH, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _local.conn = conn
    return conn


@contextmanager
def cursor(commit=False):
    conn = get_conn()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise


def init_db():
    _ensure_dir()
    conn = get_conn()
    schema_path = os.path.join(config.BASE_DIR, "schema.sql")
    with open(schema_path, "r", encoding="utf-8") as f:
        conn.executescript(f.read())
    conn.commit()


def row_to_dict(row):
    if row is None:
        return None
    return dict(row)


def rows_to_list(rows):
    return [dict(r) for r in rows]


# --- JSON field helpers -------------------------------------------------
JSON_FIELDS = {
    "must_have_features", "scoring_weights", "scoring_dimensions",
    "specs", "features", "pros", "cons", "score_breakdown",
}


def loads_safe(value, default):
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def decode_json_fields(d):
    """Given a dict from row_to_dict, decode any known JSON TEXT fields."""
    if d is None:
        return d
    out = dict(d)
    for field in JSON_FIELDS:
        if field in out:
            default = [] if field in (
                "must_have_features", "scoring_dimensions", "features", "pros", "cons"
            ) else {}
            out[field] = loads_safe(out[field], default)
    return out


def execute(sql, params=(), commit=False):
    with cursor(commit=commit) as cur:
        cur.execute(sql, params)
        return cur


def query_all(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return rows_to_list(cur.fetchall())


def query_one(sql, params=()):
    with cursor() as cur:
        cur.execute(sql, params)
        return row_to_dict(cur.fetchone())


def insert(table, fields: dict):
    keys = list(fields.keys())
    placeholders = ",".join(["?"] * len(keys))
    sql = f"INSERT INTO {table} ({','.join(keys)}) VALUES ({placeholders})"
    with cursor(commit=True) as cur:
        cur.execute(sql, [fields[k] for k in keys])
        return cur.lastrowid


def update(table, id_, fields: dict, id_field="id"):
    if not fields:
        return
    keys = list(fields.keys())
    set_clause = ",".join([f"{k}=?" for k in keys])
    sql = f"UPDATE {table} SET {set_clause} WHERE {id_field}=?"
    with cursor(commit=True) as cur:
        cur.execute(sql, [fields[k] for k in keys] + [id_])


def delete(table, id_, id_field="id"):
    with cursor(commit=True) as cur:
        cur.execute(f"DELETE FROM {table} WHERE {id_field}=?", (id_,))


# --- Settings helpers -----------------------------------------------------
def get_setting(key, default=None):
    row = query_one("SELECT value FROM settings WHERE key=?", (key,))
    if row is None:
        return default
    return loads_safe(row["value"], default)


def set_setting(key, value):
    existing = query_one("SELECT key FROM settings WHERE key=?", (key,))
    encoded = json.dumps(value)
    if existing:
        update("settings", key, {"value": encoded}, id_field="key")
    else:
        insert("settings", {"key": key, "value": encoded})
