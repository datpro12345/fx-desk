import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def project_root_for_data() -> Path:
    """Directory that owns the ``data/`` tree (repo root or ``FX_DESK_DATA_ROOT``)."""
    override = os.environ.get("FX_DESK_DATA_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return REPO_ROOT


def _data_path(*parts: str) -> Path:
    return project_root_for_data().joinpath("data", *parts)


# Medallion paths (see docs/architecture.md)
BRONZE_RAW_CALENDAR_DIR = _data_path("bronze", "raw", "calendar")
BRONZE_LANDING_DIR = _data_path("bronze", "landing", "calendar_events")
SILVER_EVENTS_DIR = _data_path("silver", "calendar_events")
SILVER_CHANGES_DIR = _data_path("silver", "calendar_event_changes")
GOLD_GCAL_DIR = _data_path("gold", "google_calendar")
GOLD_MART_DIR = _data_path("gold", "mart")

# ICT Institutional Layer (Phase 2) — public zero-key sources
BRONZE_RAW_CFTC_DIR = _data_path("bronze", "raw", "cftc")
BRONZE_RAW_BINANCE_DIR = _data_path("bronze", "raw", "binance")
BRONZE_RAW_STOOQ_DIR = _data_path("bronze", "raw", "stooq")
BRONZE_RAW_YAHOO_DIR = _data_path("bronze", "raw", "yahoo")
SILVER_COT_DIR = _data_path("silver", "cot_positions")
SILVER_OHLCV_DIR = _data_path("silver", "ohlcv")
GOLD_ICT_DIR = _data_path("gold", "ict")

CFTC_SODA_URL = "https://data.cftc.gov/resource/6dca-aqww.json"
CFTC_CONTRACT_CODES = {
    "XAUUSD": "088691",
    "EURUSD": "099741",
    "DXY": "098662",
    "BTCUSDT": "133741",
}
BINANCE_KLINES_URL = "https://api.binance.com/api/v3/klines"
STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
YFINANCE_TICKERS = {
    "DXY": "DX-Y.NYB",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "XAUUSD": "GC=F",
    "XAGUSD": "SI=F",
    "ES": "ES=F",
    "NQ": "NQ=F",
    "YM": "YM=F",
    "US10Y": "^TNX",
}
STOOQ_SYMBOLS = {
    "XAUUSD": "xauusd",
    "DXY": "dx.f",
}
SEASONAL_CACHE_MAX_AGE_DAYS = 7
YAHOO_SLEEP_SECONDS = 1.5
COT_FETCH_WEEKS = 157  # 156w lookback + 1 prior week for reversal

# Legacy paths (pre-medallion; do not write new files here)
LEGACY_BRONZE_MONTHLY_DIR = _data_path("bronze", "monthly")
LEGACY_SILVER_MONTHLY_DIR = _data_path("silver", "monthly")

# Back-compat aliases used by older scripts
BRONZE_MONTHLY_DIR = LEGACY_BRONZE_MONTHLY_DIR
BRONZE_WEEKLY_DIR = _data_path("bronze", "weekly")

BRONZE_LANDING_COLUMNS = [
    "date",
    "time",
    "currency",
    "impact",
    "event",
    "actual",
    "forecast",
    "previous",
    "source_file",
    "ingested_at",
]

# Legacy 8-col bronze (parsed only)
BRONZE_COLUMNS = [
    "date",
    "time",
    "currency",
    "impact",
    "event",
    "actual",
    "forecast",
    "previous",
]

SILVER_COLUMNS = [
    "event_uid",
    "event_date",
    "time_raw",
    "event_datetime_utc",
    "event_datetime_hcm",
    "currency",
    "impact",
    "event",
    "actual",
    "forecast",
    "previous",
    "source_timezone",
    "first_seen_at",
    "updated_at",
]

# Append-only audit of every silver change (late-arriving actual, revisions).
SILVER_CHANGES_COLUMNS = [
    "changed_at",
    "source",
    "change_type",
    "event_uid",
    "event_date",
    "currency",
    "event",
    "field",
    "old_value",
    "new_value",
]

ALLOWED_CURRENCIES = frozenset(
    {"AUD", "CAD", "CHF", "CNY", "EUR", "GBP", "JPY", "NZD", "USD"}
)

IMPACT_CLASS_MAP = {
    "icon icon--ff-impact-yel": "yellow",
    "icon icon--ff-impact-ora": "orange",
    "icon icon--ff-impact-red": "red",
    "icon icon--ff-impact-gra": "gray",
}

FF_BASE_URL = "https://www.forexfactory.com"
FF_CALENDAR_URL = f"{FF_BASE_URL}/calendar"

# Official-ish weekly feed (this week only; rate-limited ~2 req / 5 min).
# Prefer this over HTML scrape for the current week.
FF_WEEKLY_EXPORT_BASE = "https://nfs.faireconomy.media/ff_calendar_thisweek"
FF_WEEKLY_EXPORT_FORMATS = ("csv", "xml", "json")

DEFAULT_IMPERSONATE = "firefox135"
MAX_FETCH_RETRIES = 5
RETRY_BACKOFF_SECONDS = 3

# Cloudflare-safe pacing between impact-layer fetches
IMPACT_FETCH_GAP_SECONDS = 45
# Random human-like delay range (seconds) applied around paced gaps
FETCH_JITTER_SECONDS = (2.0, 5.0)

# Optional egress when WARP is off: residential proxy URL.
# WARP Traffic+DNS (UDP) is the proven path for historical HTML (see docs/scrape_strategy.md).
PROXY_ENV_KEYS = ("FF_HTTP_PROXY", "HTTPS_PROXY", "HTTP_PROXY")

# Rotating browser-like User-Agents (used by cloudscraper / header builds)
USER_AGENTS = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36",
)

# FF impact filter IDs → bronze impact label
# https://www.forexfactory.com/calendar?...&impacts=3,2,1,0
# 0 = holiday / non-economic (bank holidays, session closures). Required for
# liquidity: a closed cash session thins FX even when no red print is scheduled.
IMPACT_LAYERS = (
    ("red", 3),
    ("orange", 2),
    ("yellow", 1),
    ("gray", 0),
)
