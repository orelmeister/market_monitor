"""
polygon_provider.py — Polygon.io data provider for Market Monitor.

Uses Polygon.io REST API as the PRIMARY data source for:
  - Current prices (Snapshot endpoint — all tickers in 1 call)
  - Server-side SMA calculation (no need to download 200 days of data)
  - Server-side RSI calculation (bonus indicator)
  - Market open/closed status
  - Crypto prices

Falls back to yfinance when Polygon is unavailable or not configured.

Polygon.io Premium: Real-time data, unlimited API calls.
Sign up: https://polygon.io/

API Endpoints Used:
  - GET /v2/aggs/ticker/{ticker}/prev          — Previous day close
  - GET /v2/snapshot/locale/us/markets/stocks/tickers  — All stock snapshots
  - GET /v1/indicators/sma/{ticker}            — Server-side SMA
  - GET /v1/indicators/rsi/{ticker}            — Server-side RSI
  - GET /v1/marketstatus/now                   — Current market status
  - GET /v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from}/{to} — Aggregates
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import POLYGON_API_KEY

logger = logging.getLogger(__name__)

BASE_URL = "https://api.polygon.io"


def _polygon_available() -> bool:
    """Check if Polygon API key is configured."""
    if not POLYGON_API_KEY:
        logger.debug("Polygon API key not configured — will use yfinance fallback")
        return False
    return True


def _get(endpoint: str, params: Optional[dict] = None) -> Optional[dict]:
    """
    Make a GET request to Polygon.io API.
    Returns parsed JSON or None on failure.
    """
    if not _polygon_available():
        return None

    url = f"{BASE_URL}{endpoint}"
    if params is None:
        params = {}
    params["apiKey"] = POLYGON_API_KEY

    try:
        response = requests.get(url, params=params, timeout=15)

        if response.status_code == 429:
            logger.warning("Polygon rate limit hit")
            return None

        response.raise_for_status()
        return response.json()

    except requests.RequestException as e:
        logger.error(f"Polygon API request failed: {endpoint} — {e}")
        return None


# ─── Market Status ───────────────────────────────────────────────────────────

def get_market_status() -> Optional[dict]:
    """
    Check if the US stock market is currently open.

    Endpoint: GET /v1/marketstatus/now

    Returns dict with:
      - market: "open" | "closed" | "early-hours" | "extended-hours"
      - serverTime: current server time
      - exchanges: { nyse: "open", nasdaq: "open", ... }
      - currencies: { fx: "open", crypto: "open" }
    """
    data = _get("/v1/marketstatus/now")
    if data is None:
        return None

    market = data.get("market", "unknown")
    logger.info(f"Polygon Market Status: {market}")
    return data


def is_market_open() -> Optional[bool]:
    """Simple check: is the US stock market open right now?"""
    status = get_market_status()
    if status is None:
        return None
    return status.get("market") == "open"


# ─── Price Data ──────────────────────────────────────────────────────────────

def get_previous_close(ticker: str) -> Optional[dict]:
    """
    Get previous day's OHLCV data for a ticker.

    Endpoint: GET /v2/aggs/ticker/{ticker}/prev

    Returns dict with: open, high, low, close, volume, vwap
    """
    # Polygon uses "X:" prefix for crypto (e.g., "X:BTCUSD")
    poly_ticker = _convert_ticker(ticker)
    data = _get(f"/v2/aggs/ticker/{poly_ticker}/prev")

    if data is None or data.get("resultsCount", 0) == 0:
        return None

    result = data["results"][0]
    return {
        "ticker": ticker,
        "open": result.get("o"),
        "high": result.get("h"),
        "low": result.get("l"),
        "close": result.get("c"),
        "volume": result.get("v"),
        "vwap": result.get("vw"),
        "timestamp": result.get("t"),
    }


def get_current_price(ticker: str) -> Optional[float]:
    """
    Get the most recent price for a ticker via Polygon.
    With premium: tries snapshot for real-time last-trade price first.
    Falls back to previous day close.
    """
    # Try snapshot for real-time price (premium)
    if not ticker.endswith("-USD"):
        snapshots = get_all_stock_snapshots([ticker])
        snap = snapshots.get(ticker)
        if snap and snap.get("price"):
            return float(snap["price"])

    # Fallback to previous close
    prev = get_previous_close(ticker)
    if prev and prev.get("close"):
        return float(prev["close"])
    return None


def get_aggregates(
    ticker: str,
    multiplier: int = 1,
    timespan: str = "day",
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    limit: int = 250,
) -> Optional[list[dict]]:
    """
    Get aggregate bars (OHLCV) for a ticker.

    Endpoint: GET /v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from}/{to}

    Args:
        ticker: Stock/crypto ticker
        multiplier: Size of the timespan multiplier
        timespan: day, hour, minute, week, month, quarter, year
        from_date: Start date (YYYY-MM-DD)
        to_date: End date (YYYY-MM-DD)
        limit: Max number of bars

    Returns list of dicts with: timestamp, open, high, low, close, volume
    """
    poly_ticker = _convert_ticker(ticker)

    if to_date is None:
        to_date = datetime.utcnow().strftime("%Y-%m-%d")
    if from_date is None:
        from_date = (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d")

    data = _get(
        f"/v2/aggs/ticker/{poly_ticker}/range/{multiplier}/{timespan}/{from_date}/{to_date}",
        params={"limit": limit, "sort": "asc"},
    )

    if data is None or data.get("resultsCount", 0) == 0:
        return None

    bars = []
    for r in data["results"]:
        bars.append({
            "timestamp": r.get("t"),
            "open": r.get("o"),
            "high": r.get("h"),
            "low": r.get("l"),
            "close": r.get("c"),
            "volume": r.get("v"),
        })

    return bars


# ─── Technical Indicators (Server-Side) ─────────────────────────────────────

def get_sma(
    ticker: str,
    window: int = 200,
    timespan: str = "day",
    series_type: str = "close",
) -> Optional[float]:
    """
    Get Simple Moving Average calculated server-side by Polygon.

    Endpoint: GET /v1/indicators/sma/{ticker}

    This replaces the need to download 200 days of data and calculate locally!
    One API call instead of a heavy data download.

    Args:
        ticker: Stock ticker (e.g., "SPY")
        window: SMA period (e.g., 200 for 200-day SMA)
        timespan: day, week, month
        series_type: close, open, high, low

    Returns the most recent SMA value, or None on failure.
    """
    poly_ticker = _convert_ticker(ticker)
    data = _get(
        f"/v1/indicators/sma/{poly_ticker}",
        params={
            "timespan": timespan,
            "window": window,
            "series_type": series_type,
            "order": "desc",
            "limit": 1,
        },
    )

    if data is None:
        return None

    results = data.get("results", {}).get("values", [])
    if not results:
        logger.warning(f"No SMA data returned for {ticker} (window={window})")
        return None

    sma_value = results[0].get("value")
    logger.info(f"Polygon SMA({window}) for {ticker}: {sma_value:.2f}")
    return float(sma_value)


def get_rsi(
    ticker: str,
    window: int = 14,
    timespan: str = "day",
    series_type: str = "close",
) -> Optional[float]:
    """
    Get Relative Strength Index calculated server-side by Polygon.

    Endpoint: GET /v1/indicators/rsi/{ticker}

    RSI Interpretation:
      - RSI > 70: Overbought (potential sell signal)
      - RSI < 30: Oversold (potential buy signal)
      - RSI 30-70: Neutral

    Args:
        ticker: Stock ticker
        window: RSI period (typically 14)
        timespan: day, week, month
        series_type: close, open, high, low

    Returns the most recent RSI value, or None on failure.
    """
    poly_ticker = _convert_ticker(ticker)
    data = _get(
        f"/v1/indicators/rsi/{poly_ticker}",
        params={
            "timespan": timespan,
            "window": window,
            "series_type": series_type,
            "order": "desc",
            "limit": 1,
        },
    )

    if data is None:
        return None

    results = data.get("results", {}).get("values", [])
    if not results:
        logger.warning(f"No RSI data returned for {ticker} (window={window})")
        return None

    rsi_value = results[0].get("value")
    logger.info(f"Polygon RSI({window}) for {ticker}: {rsi_value:.2f}")
    return float(rsi_value)


# ─── Multi-Ticker Snapshot ──────────────────────────────────────────────────

def get_all_stock_snapshots(tickers: list[str]) -> dict[str, dict]:
    """
    Get snapshots for multiple stock tickers in ONE API call.

    Endpoint: GET /v2/snapshot/locale/us/markets/stocks/tickers

    Returns dict of ticker -> { price, change, change_pct, day_high, day_low, ... }
    """
    # Filter to stocks only (not crypto)
    stock_tickers = [t for t in tickers if not t.endswith("-USD")]
    if not stock_tickers:
        return {}

    poly_tickers = ",".join(_convert_ticker(t) for t in stock_tickers)
    data = _get(
        "/v2/snapshot/locale/us/markets/stocks/tickers",
        params={"tickers": poly_tickers},
    )

    if data is None or not data.get("tickers"):
        return {}

    snapshots = {}
    for snap in data["tickers"]:
        ticker = snap.get("ticker", "")
        day = snap.get("day", {})
        prev_day = snap.get("prevDay", {})
        last_trade = snap.get("lastTrade", {})
        # Prefer real-time lastTrade price → day close → prev day close
        price = last_trade.get("p") or day.get("c") or prev_day.get("c")
        snapshots[ticker] = {
            "price": price,
            "open": day.get("o"),
            "high": day.get("h"),
            "low": day.get("l"),
            "volume": day.get("v"),
            "prev_close": prev_day.get("c"),
            "change": snap.get("todaysChange"),
            "change_pct": snap.get("todaysChangePerc"),
            "last_trade_price": last_trade.get("p"),
        }

    return snapshots


# ─── Crypto ──────────────────────────────────────────────────────────────────

def get_crypto_price(ticker: str) -> Optional[float]:
    """
    Get crypto price via Polygon previous close.
    Polygon uses X:BTCUSD format for crypto.
    """
    return get_current_price(ticker)


# ─── Ticker Conversion ──────────────────────────────────────────────────────

def _convert_ticker(ticker: str) -> str:
    """
    Convert yfinance-style tickers to Polygon format.
    - BTC-USD → X:BTCUSD
    - ETH-USD → X:ETHUSD
    - Regular stocks stay the same
    """
    if ticker.endswith("-USD"):
        # Crypto: BTC-USD → X:BTCUSD
        base = ticker.replace("-USD", "")
        return f"X:{base}USD"
    return ticker


# ─── Health Check ────────────────────────────────────────────────────────────

def polygon_health_check() -> dict:
    """
    Quick health check: verify Polygon API is reachable and key is valid.
    Returns dict with status and details.
    """
    if not _polygon_available():
        return {"status": "disabled", "reason": "POLYGON_API_KEY not set"}

    status = get_market_status()
    if status is None:
        return {"status": "error", "reason": "API call failed"}

    return {
        "status": "ok",
        "market": status.get("market", "unknown"),
        "server_time": status.get("serverTime", "unknown"),
    }
