"""
Central configuration for the Home Purchase Intelligence Dashboard.

Everything is read from environment variables with sensible defaults, so the
app can be reconfigured without touching code. Copy .env.example to .env and
edit values there (the app loads .env automatically if python-dotenv is
available; otherwise just export the variables in your shell).

Nothing secret is hard-coded here. If you wire up a real LLM provider or a
notification channel (email/Telegram) later, its API key/token must come
from an environment variable, never a literal in source.
"""
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_dotenv_if_present():
    env_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(env_path):
        return
    try:
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, value)
    except OSError:
        pass


_load_dotenv_if_present()


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name, default):
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name, default):
    val = os.environ.get(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


# --- Core budget config -----------------------------------------------------
TOTAL_BUDGET_EGP = _env_float("TOTAL_BUDGET_EGP", 180000.0)
CURRENCY = os.environ.get("CURRENCY", "EGP")

# --- Database ---------------------------------------------------------------
DATABASE_PATH = os.environ.get(
    "DATABASE_PATH", os.path.join(BASE_DIR, "data", "dashboard.db")
)

# --- Price monitoring --------------------------------------------------------
PRICE_CHECK_FREQUENCY_HOURS = _env_int("PRICE_CHECK_FREQUENCY_HOURS", 12)
REQUEST_TIMEOUT_SECONDS = _env_int("REQUEST_TIMEOUT_SECONDS", 12)
REQUEST_USER_AGENT = os.environ.get(
    "REQUEST_USER_AGENT",
    "HomeDashboardPriceBot/1.0 (personal price tracker; contact: owner)",
)
# Minimum delay between requests to the same host, to stay a polite,
# low-volume personal tool rather than anything resembling scraping at scale.
MIN_REQUEST_INTERVAL_SECONDS = _env_int("MIN_REQUEST_INTERVAL_SECONDS", 3)

# --- Deal scoring thresholds --------------------------------------------------
DEAL_SCORE_THRESHOLDS = {
    "exceptional": _env_int("DEAL_THRESHOLD_EXCEPTIONAL", 90),
    "good": _env_int("DEAL_THRESHOLD_GOOD", 75),
    "fair": _env_int("DEAL_THRESHOLD_FAIR", 60),
    "wait": _env_int("DEAL_THRESHOLD_WAIT", 40),
}

# --- Default scoring weights (can be overridden per-category in the DB) -----
DEFAULT_SCORING_WEIGHTS = {
    "reliability": 0.30,
    "price_value": 0.20,
    "warranty_service": 0.15,
    "energy_efficiency": 0.10,
    "performance": 0.15,
    "features": 0.05,
    "user_preference": 0.05,
}

# --- Notification channels ---------------------------------------------------
# v1 ships only "in_app" (stored + surfaced in the dashboard) because it is
# the only channel that needs zero external credentials. email/telegram are
# modeled in the schema and notification_history table so they can be turned
# on later just by adding credentials + a sender implementation.
NOTIFICATION_CHANNELS = json.loads(
    os.environ.get("NOTIFICATION_CHANNELS", '["in_app"]')
)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = _env_int("SMTP_PORT", 587)
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
NOTIFY_EMAIL_TO = os.environ.get("NOTIFY_EMAIL_TO", "")

# --- Optional AI assistant upgrade -------------------------------------------
# The built-in assistant (assistant.py) is fully deterministic and reasons
# only over data already stored in the database - it never invents prices.
# If ANTHROPIC_API_KEY is set, the assistant can optionally use it to turn
# free-text questions into a nicer natural-language answer wrapped around the
# same deterministic data (see assistant.py: `_maybe_polish_with_llm`).
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
ENABLE_LLM_ASSISTANT_POLISH = _env_bool("ENABLE_LLM_ASSISTANT_POLISH", False)

SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-personal-app-secret-change-me")

FLASK_HOST = os.environ.get("FLASK_HOST", "127.0.0.1")
FLASK_PORT = _env_int("FLASK_PORT", 5000)
FLASK_DEBUG = _env_bool("FLASK_DEBUG", True)

# --- Optional simple password gate --------------------------------------------
# This app has no login system (see README "Security & privacy") — it's meant
# for a single household, not multi-user auth. If you deploy it somewhere
# reachable from the internet (e.g. to share with family), set both of these
# to turn on an HTTP Basic Auth prompt in front of every page. Leave either
# blank (the default) to leave the app open, which is fine for local-only use.
BASIC_AUTH_USERNAME = os.environ.get("BASIC_AUTH_USERNAME", "")
BASIC_AUTH_PASSWORD = os.environ.get("BASIC_AUTH_PASSWORD", "")
