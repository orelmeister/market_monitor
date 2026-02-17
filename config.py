"""
config.py — Constants and configuration for Market Monitor.
All thresholds, tickers, and scheduling parameters live here.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ─── API Keys ────────────────────────────────────────────────────────────────
FMP_API_KEY: str = os.getenv("FMP_API_KEY", "")
POLYGON_API_KEY: str = os.getenv("POLYGON_API_KEY", "")
TELEGRAM_BOT_TOKEN: str = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID: str = os.getenv("TELEGRAM_CHAT_ID", "")

# ─── Tickers ─────────────────────────────────────────────────────────────────
CORE_PORTFOLIO = ["IVV", "BFGFX"]
DEFENSIVE_INCOME = ["JEPI", "JEPQ"]
CRYPTO_CANARIES = ["BTC-USD", "ETH-USD"]
BENCHMARK = "SPY"

# ─── Portfolio Meme Tokens (Monitored every 5 minutes) ───────────────────────
# Format: {"name": str, "symbol": str, "address": str, "chain": str}
PORTFOLIO_TOKENS = [
    {
        "name": "Auki",
        "symbol": "AUKI",
        "address": "0x5cba0b7b488633cde1a57b8b406a7a7310d2993e",
        "chain": "ethereum",
    },
    {
        "name": "U.S. Oil",
        "symbol": "USOR",
        "address": "USoRyaQjch6E18nCdDvWoRgTo6osQs9MUd8JXEsspWR",
        "chain": "solana",
    },
]
PORTFOLIO_TOKEN_CHECK_INTERVAL_MIN: int = 5  # Check portfolio tokens every 5 minutes

ALL_EQUITY_TICKERS = CORE_PORTFOLIO + DEFENSIVE_INCOME + [BENCHMARK]
ALL_CRYPTO_TICKERS = CRYPTO_CANARIES
ALL_TICKERS = ALL_EQUITY_TICKERS + ALL_CRYPTO_TICKERS

# ─── Technical Analysis Thresholds ───────────────────────────────────────────
SMA_PERIOD: int = 200                    # 200-day Simple Moving Average
TRAILING_STOP_PERCENT: float = 5.0       # 5% trailing stop from 30-day high
HIGH_WATER_MARK_DAYS: int = 30           # Look-back for high water mark
BTC_CRASH_THRESHOLD_24H: float = -10.0   # BTC 24h drop % for crash alert
BTC_7D_CHANGE_LOOKBACK: int = 7          # 7-day lookback for BTC trend

# ─── RSI Thresholds (Polygon.io) ────────────────────────────────────────────
RSI_PERIOD: int = 14                     # Standard 14-day RSI
RSI_OVERBOUGHT: float = 70.0            # RSI > 70 → overbought warning
RSI_OVERSOLD: float = 30.0              # RSI < 30 → oversold (buy signal)

# ─── News Sentiment ─────────────────────────────────────────────────────────
NEGATIVE_KEYWORDS = [
    "crash", "recession", "plummet", "liquidity crisis",
    "bear market", "sell-off", "selloff", "collapse",
    "downturn", "panic", "correction", "default",
    "bankruptcy", "crisis", "contagion", "meltdown",
]
# Threshold: if >= this many negative keyword hits in latest news batch → WARNING
NEWS_NEGATIVE_THRESHOLD: int = 5

# ─── FMP API Endpoints ──────────────────────────────────────────────────────
FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"
FMP_NEWS_ENDPOINT = f"{FMP_BASE_URL}/stock_news"
FMP_ECONOMIC_CALENDAR_ENDPOINT = f"{FMP_BASE_URL}/economic_calendar"
FMP_NEWS_LIMIT: int = 50

# ─── Alert Rate Limiting ────────────────────────────────────────────────────
ALERT_COOLDOWN_CRITICAL_HOURS: int = int(os.getenv("ALERT_COOLDOWN_HOURS", "4"))
ALERT_COOLDOWN_WARNING_HOURS: int = 2
ALERT_COOLDOWN_INFO_HOURS: int = 24      # INFO alerts batched daily

# ─── Scheduling ──────────────────────────────────────────────────────────────
MARKET_CHECK_INTERVAL_MIN: int = int(os.getenv("MONITOR_INTERVAL_MINUTES", "15"))
CRYPTO_CHECK_INTERVAL_MIN: int = 30
NEWS_CHECK_INTERVAL_MIN: int = 60
DAILY_SUMMARY_HOUR: int = 17             # 5 PM Eastern
DAILY_SUMMARY_MINUTE: int = 0
MARKET_OPEN_HOUR: int = 9
MARKET_OPEN_MINUTE: int = 30
MARKET_CLOSE_HOUR: int = 16
MARKET_CLOSE_MINUTE: int = 0

# ─── State File ──────────────────────────────────────────────────────────────
STATE_FILE_PATH: str = os.getenv("STATE_FILE_PATH", "monitor_state.json")

# ─── Logging ─────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"

# ─── Data Provider Priority ─────────────────────────────────────────────────
# Polygon.io is the PRIMARY data source (server-side SMA/RSI, snapshots)
# yfinance is the FALLBACK when Polygon is unavailable or not configured
USE_POLYGON_PRIMARY: bool = bool(os.getenv("POLYGON_API_KEY", ""))
