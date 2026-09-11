"""Central configuration for OPINION."""
from dataclasses import dataclass, field
from typing import Literal

# ── Versions ─────────────────────────────────────────────────────────────────
DATASET_VERSION = "1.0.0"
FEATURE_VERSION = "1.0.0"

# ── Forecast horizons ─────────────────────────────────────────────────────────
@dataclass(frozen=True)
class HorizonDef:
    code: str
    steps: int          # number of hourly market-time steps
    minutes: int        # nominal minutes (for storage; actual target from real bars)
    label: str

HORIZONS: list[HorizonDef] = [
    HorizonDef("1h",  1,   60,   "+1 hour"),
    HorizonDef("5h",  5,   300,  "+5 hours"),
    HorizonDef("12h", 12,  720,  "+12 hours"),
    HorizonDef("24h", 24,  1440, "+24 hours"),
    HorizonDef("48h", 48,  2880, "+48 hours"),
]
HORIZON_BY_CODE: dict[str, HorizonDef] = {h.code: h for h in HORIZONS}
MAX_HORIZON_STEPS = max(h.steps for h in HORIZONS)  # 48

# ── Assets ────────────────────────────────────────────────────────────────────
ASSETS = ["XAU", "XAG"]
ASSET_LABELS = {"XAU": "Gold", "XAG": "Silver"}

# ── Currencies ────────────────────────────────────────────────────────────────
CURRENCIES = ["INR", "USD", "EUR", "CNY"]
PRIMARY_CURRENCY = "INR"

# ── FX pairs (all → INR) ──────────────────────────────────────────────────────
@dataclass(frozen=True)
class FXPair:
    pair: str           # e.g. "USD/INR"
    yf_ticker: str      # e.g. "USDINR=X"
    base: str           # e.g. "USD"
    quote: str          # "INR"
    fallback: str       # e.g. "open.er-api.com cross"

FX_PAIRS: list[FXPair] = [
    FXPair("USD/INR", "USDINR=X",  "USD", "INR", "open.er-api.com"),
    FXPair("EUR/INR", "EURINR=X",  "EUR", "INR", "EUR/USD × USD/INR cross"),
    FXPair("CNY/INR", "CNYINR=X",  "CNY", "INR", "CNY/USD × USD/INR cross"),
    FXPair("JPY/INR", "JPYINR=X",  "JPY", "INR", "JPY/USD × USD/INR cross"),
    FXPair("CHF/INR", "CHFINR=X",  "CHF", "INR", "CHF/USD × USD/INR cross"),
]
FX_BY_PAIR: dict[str, FXPair] = {p.pair: p for p in FX_PAIRS}

# ── Metals tickers ────────────────────────────────────────────────────────────
METAL_FUTURES_TICKERS = {
    "XAU": "GC=F",   # Gold futures (COMEX) — FUTURES, not spot
    "XAG": "SI=F",   # Silver futures (COMEX) — FUTURES, not spot
}

# ── Data quality thresholds ───────────────────────────────────────────────────
XAU_INR_CROSS_CHECK_THRESHOLD_PCT = 0.5   # flag anomaly if delta > 0.5 %
PRICE_STALE_SECONDS = 300                  # 5 min: LIVE → STALE
PRICE_UNAVAILABLE_SECONDS = 3600           # 1 h: STALE → UNAVAILABLE
FX_STALE_SECONDS = 600                     # 10 min
NEWS_STALE_SECONDS = 3600 * 4              # 4 h

# ── Refresh intervals (milliseconds, for dcc.Interval) ───────────────────────
REFRESH_PRICES_MS = 60_000      # 1 min
REFRESH_FX_MS = 60_000
REFRESH_HEALTH_MS = 30_000
REFRESH_NEWS_MS = 600_000       # 10 min

# ── yfinance fetch params ─────────────────────────────────────────────────────
YF_PERIOD = "730d"       # max history for 1h interval
YF_INTERVAL = "1h"

# ── Scoring ───────────────────────────────────────────────────────────────────
SCORE_CORRECT = 3
SCORE_INCORRECT = -6
SCORE_PENDING = 0

# ── Plausible price ranges (for anomaly detection) ───────────────────────────
PRICE_RANGE_USD = {
    "XAU": (500.0, 5000.0),    # gold USD/oz
    "XAG": (5.0, 200.0),       # silver USD/oz
}

# ── SQLite path (overridable in tests) ───────────────────────────────────────
import os
from pathlib import Path
DB_PATH = Path(os.environ.get("OPINION_DB", Path(__file__).parent / "opinion.db"))
