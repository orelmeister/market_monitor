"""
technical_analysis.py — Technical analysis functions for Market Monitor.

Implements:
  - 200-Day SMA for SPY (bull/bear regime detection)
  - 14-Day RSI for SPY (overbought/oversold detection) — via Polygon.io
  - Trailing Stop for IVV (high water mark vs. current price)
  - Crypto Canary (BTC 24h crash detection, 7-day trend)

Data Source Priority:
  1. Polygon.io (server-side SMA/RSI, snapshot prices) — PRIMARY
  2. yfinance (local SMA calculation, individual price fetches) — FALLBACK
"""

import logging
from typing import Optional

import yfinance as yf
import pandas as pd

from config import (
    BENCHMARK,
    SMA_PERIOD,
    RSI_PERIOD,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
    TRAILING_STOP_PERCENT,
    HIGH_WATER_MARK_DAYS,
    BTC_CRASH_THRESHOLD_24H,
    BTC_7D_CHANGE_LOOKBACK,
    USE_POLYGON_PRIMARY,
)
from polygon_provider import (
    get_sma as polygon_get_sma,
    get_rsi as polygon_get_rsi,
    get_current_price as polygon_get_price,
    get_all_stock_snapshots,
    get_crypto_price as polygon_get_crypto_price,
    get_aggregates,
)

logger = logging.getLogger(__name__)


# ─── Data Types ──────────────────────────────────────────────────────────────

class MarketSignal:
    """Represents a single analysis signal."""

    def __init__(self, name: str, level: str, message: str, value: Optional[float] = None):
        self.name = name        # e.g., "SMA_CROSS", "TRAILING_STOP", "CRYPTO_CANARY"
        self.level = level      # "CRITICAL", "WARNING", "INFO", "GREEN"
        self.message = message
        self.value = value      # optional numeric value for context

    def __repr__(self) -> str:
        return f"Signal({self.level}: {self.name} — {self.message})"


# ─── Price Fetching (Polygon → yfinance fallback) ───────────────────────────

def fetch_price_data(ticker: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch OHLC data from yfinance.
    Returns DataFrame with columns: Open, High, Low, Close, Volume.
    Returns None on failure.

    Note: This is the yfinance path — used as fallback when Polygon is
    unavailable, or when we need full DataFrame (e.g., trailing stop).
    """
    try:
        logger.info(f"Fetching price data for {ticker} via yfinance (period={period}, interval={interval})")
        data = yf.download(ticker, period=period, interval=interval, progress=False)
        if data is None or data.empty:
            logger.warning(f"No data returned for {ticker}")
            return None
        # Flatten MultiIndex columns if present (yfinance sometimes returns multi-level)
        if isinstance(data.columns, pd.MultiIndex):
            data.columns = data.columns.get_level_values(0)
        return data
    except Exception as e:
        logger.error(f"Failed to fetch data for {ticker}: {e}")
        return None


def get_current_price(ticker: str) -> Optional[float]:
    """
    Get the most recent closing price for a ticker.
    Tries Polygon first, falls back to yfinance.
    """
    if USE_POLYGON_PRIMARY:
        price = polygon_get_price(ticker)
        if price is not None:
            return price
        logger.info(f"Polygon price unavailable for {ticker}, falling back to yfinance")

    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if hist is None or hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"Failed to get current price for {ticker}: {e}")
        return None


# ─── 200-Day SMA Analysis ───────────────────────────────────────────────────

def _get_sma_polygon(ticker: str) -> Optional[tuple[float, float]]:
    """
    Get current price and SMA via Polygon.io server-side calculation.
    Returns (current_price, sma_value) or None.
    One API call instead of downloading 200 days of data!
    """
    sma_value = polygon_get_sma(ticker, window=SMA_PERIOD)
    if sma_value is None:
        return None

    price = polygon_get_price(ticker)
    if price is None:
        return None

    return (price, sma_value)


def _get_sma_yfinance(ticker: str) -> Optional[tuple[float, float]]:
    """
    Calculate SMA locally using yfinance data (fallback).
    Returns (current_price, sma_value) or None.
    """
    data = fetch_price_data(ticker, period="1y", interval="1d")
    if data is None or len(data) < SMA_PERIOD:
        logger.warning(f"Insufficient data for {SMA_PERIOD}-day SMA on {ticker}")
        return None

    data["SMA_200"] = data["Close"].rolling(window=SMA_PERIOD).mean()
    current_price = float(data["Close"].iloc[-1])
    sma_value = float(data["SMA_200"].iloc[-1])
    return (current_price, sma_value)


def analyze_sma(previous_state: dict) -> tuple[Optional[MarketSignal], dict]:
    """
    Calculate 200-day SMA for SPY and detect regime changes.
    Uses Polygon server-side SMA when available, yfinance as fallback.

    Returns:
        (signal_or_None, updated_state_dict)
    """
    # Try Polygon first, then yfinance
    result = None
    if USE_POLYGON_PRIMARY:
        result = _get_sma_polygon(BENCHMARK)
        if result:
            logger.info(f"SMA data via Polygon.io for {BENCHMARK}")

    if result is None:
        result = _get_sma_yfinance(BENCHMARK)
        if result:
            logger.info(f"SMA data via yfinance fallback for {BENCHMARK}")

    if result is None:
        logger.warning(f"Could not get SMA data for {BENCHMARK} from any source")
        return None, {}

    current_price, sma_value = result
    is_above_sma = current_price > sma_value

    state_update = {
        "spy_price": current_price,
        "spy_sma_200": round(sma_value, 2),
        "spy_above_sma": is_above_sma,
    }

    was_above = previous_state.get("spy_above_sma")

    logger.info(
        f"SPY: ${current_price:.2f} | 200-SMA: ${sma_value:.2f} | "
        f"{'ABOVE' if is_above_sma else 'BELOW'} SMA"
    )

    # Detect CROSSOVER events (state change)
    if was_above is not None:
        if was_above and not is_above_sma:
            # Crossed BELOW → CRITICAL bearish signal
            return MarketSignal(
                name="SMA_CROSS_BELOW",
                level="CRITICAL",
                message=(
                    f"🔴 DEFENSIVE MODE TRIGGERED\n"
                    f"SPY crossed BELOW 200-day SMA\n"
                    f"Price: ${current_price:.2f} | SMA: ${sma_value:.2f}\n"
                    f"Action: Consider moving to JEPI/JEPQ"
                ),
                value=current_price,
            ), state_update

        elif not was_above and is_above_sma:
            # Crossed ABOVE → GREEN recovery signal
            return MarketSignal(
                name="SMA_CROSS_ABOVE",
                level="GREEN",
                message=(
                    f"🟢 RECOVERY DETECTED\n"
                    f"SPY crossed ABOVE 200-day SMA\n"
                    f"Price: ${current_price:.2f} | SMA: ${sma_value:.2f}\n"
                    f"Action: Consider IVV re-entry"
                ),
                value=current_price,
            ), state_update

    # No crossover — return current state as INFO
    regime = "BULLISH" if is_above_sma else "BEARISH"
    return MarketSignal(
        name="SMA_STATUS",
        level="INFO",
        message=f"SPY ${current_price:.2f} | SMA ${sma_value:.2f} | Regime: {regime}",
        value=current_price,
    ), state_update


# ─── RSI Analysis (Polygon.io) ──────────────────────────────────────────────

def analyze_rsi(previous_state: dict) -> tuple[Optional[MarketSignal], dict]:
    """
    Calculate 14-day RSI for SPY via Polygon.io server-side endpoint.
    Detects overbought (>70) and oversold (<30) conditions.

    Only runs when Polygon is configured — RSI is a bonus indicator.

    Returns:
        (signal_or_None, updated_state_dict)
    """
    if not USE_POLYGON_PRIMARY:
        logger.debug("RSI analysis skipped — Polygon not configured")
        return None, {}

    rsi_value = polygon_get_rsi(BENCHMARK, window=RSI_PERIOD)
    if rsi_value is None:
        logger.warning(f"Could not get RSI data for {BENCHMARK}")
        return None, {}

    state_update = {
        "spy_rsi": round(rsi_value, 2),
    }

    logger.info(f"SPY RSI({RSI_PERIOD}): {rsi_value:.2f}")

    was_overbought = previous_state.get("spy_rsi_overbought", False)
    was_oversold = previous_state.get("spy_rsi_oversold", False)

    if rsi_value >= RSI_OVERBOUGHT:
        state_update["spy_rsi_overbought"] = True
        state_update["spy_rsi_oversold"] = False
        if not was_overbought:
            return MarketSignal(
                name="RSI_OVERBOUGHT",
                level="WARNING",
                message=(
                    f"⚠️ SPY OVERBOUGHT — RSI = {rsi_value:.1f}\n"
                    f"RSI above {RSI_OVERBOUGHT} threshold\n"
                    f"Market may be extended — watch for pullback"
                ),
                value=rsi_value,
            ), state_update

    elif rsi_value <= RSI_OVERSOLD:
        state_update["spy_rsi_overbought"] = False
        state_update["spy_rsi_oversold"] = True
        if not was_oversold:
            return MarketSignal(
                name="RSI_OVERSOLD",
                level="GREEN",
                message=(
                    f"🟢 SPY OVERSOLD — RSI = {rsi_value:.1f}\n"
                    f"RSI below {RSI_OVERSOLD} threshold\n"
                    f"Potential buy opportunity — market may be bottoming"
                ),
                value=rsi_value,
            ), state_update

    else:
        state_update["spy_rsi_overbought"] = False
        state_update["spy_rsi_oversold"] = False

    return MarketSignal(
        name="RSI_STATUS",
        level="INFO",
        message=f"SPY RSI({RSI_PERIOD}): {rsi_value:.1f}",
        value=rsi_value,
    ), state_update


# ─── Trailing Stop (IVV) ────────────────────────────────────────────────────

def analyze_trailing_stop(previous_state: dict) -> tuple[Optional[MarketSignal], dict]:
    """
    Track IVV high water mark (30-day high) and detect trailing stop breach.
    Uses yfinance for full OHLC DataFrame (need High column for water mark).

    Returns:
        (signal_or_None, updated_state_dict)
    """
    data = fetch_price_data("IVV", period="2mo", interval="1d")
    if data is None or data.empty:
        logger.warning("No data for IVV trailing stop analysis")
        return None, {}

    recent = data.tail(HIGH_WATER_MARK_DAYS)
    high_water_mark = float(recent["High"].max())
    current_price = float(data["Close"].iloc[-1])
    drop_pct = ((current_price - high_water_mark) / high_water_mark) * 100

    state_update = {
        "ivv_price": current_price,
        "ivv_high_water_mark": round(high_water_mark, 2),
        "ivv_drop_pct": round(drop_pct, 2),
    }

    logger.info(
        f"IVV: ${current_price:.2f} | 30d High: ${high_water_mark:.2f} | "
        f"Drop: {drop_pct:.2f}%"
    )

    if drop_pct <= -TRAILING_STOP_PERCENT:
        was_stopped = previous_state.get("ivv_trailing_stop_hit", False)
        state_update["ivv_trailing_stop_hit"] = True

        if not was_stopped:
            return MarketSignal(
                name="TRAILING_STOP",
                level="WARNING",
                message=(
                    f"⚠️ TRAILING STOP HIT — IVV\n"
                    f"Price: ${current_price:.2f} | 30d High: ${high_water_mark:.2f}\n"
                    f"Drop: {drop_pct:.2f}% (threshold: -{TRAILING_STOP_PERCENT}%)\n"
                    f"Action: Review position / consider defensive shift"
                ),
                value=drop_pct,
            ), state_update
    else:
        state_update["ivv_trailing_stop_hit"] = False

    return MarketSignal(
        name="TRAILING_STOP_STATUS",
        level="INFO",
        message=f"IVV ${current_price:.2f} | High: ${high_water_mark:.2f} | Drop: {drop_pct:.2f}%",
        value=drop_pct,
    ), state_update


# ─── Crypto Canary (BTC) ────────────────────────────────────────────────────

def analyze_crypto_canary(previous_state: dict) -> tuple[Optional[MarketSignal], dict]:
    """
    Monitor BTC for sudden crashes (24h drop > 10%) and 7-day trend.
    Uses yfinance for multi-day DataFrame needed for percentage calculations.

    Returns:
        (signal_or_None, updated_state_dict)
    """
    data = fetch_price_data("BTC-USD", period="1mo", interval="1d")
    if data is None or len(data) < 2:
        logger.warning("Insufficient BTC data for crypto canary")
        return None, {}

    current_price = float(data["Close"].iloc[-1])
    prev_price = float(data["Close"].iloc[-2])
    change_24h_pct = ((current_price - prev_price) / prev_price) * 100

    # 7-day change
    change_7d_pct = 0.0
    if len(data) >= BTC_7D_CHANGE_LOOKBACK:
        price_7d_ago = float(data["Close"].iloc[-BTC_7D_CHANGE_LOOKBACK])
        change_7d_pct = ((current_price - price_7d_ago) / price_7d_ago) * 100

    state_update = {
        "btc_price": current_price,
        "btc_change_24h_pct": round(change_24h_pct, 2),
        "btc_change_7d_pct": round(change_7d_pct, 2),
    }

    logger.info(
        f"BTC: ${current_price:,.2f} | 24h: {change_24h_pct:+.2f}% | "
        f"7d: {change_7d_pct:+.2f}%"
    )

    if change_24h_pct <= BTC_CRASH_THRESHOLD_24H:
        was_crashing = previous_state.get("btc_crash_alert_active", False)
        state_update["btc_crash_alert_active"] = True

        if not was_crashing:
            return MarketSignal(
                name="CRYPTO_CANARY",
                level="WARNING",
                message=(
                    f"⚠️ LIQUIDITY DRAIN DETECTED — BTC\n"
                    f"BTC dropped {change_24h_pct:.2f}% in 24 hours\n"
                    f"Price: ${current_price:,.2f}\n"
                    f"7-day trend: {change_7d_pct:+.2f}%\n"
                    f"Possible crash imminent — review risk exposure"
                ),
                value=change_24h_pct,
            ), state_update
    else:
        state_update["btc_crash_alert_active"] = False

    return MarketSignal(
        name="CRYPTO_STATUS",
        level="INFO",
        message=(
            f"BTC ${current_price:,.2f} | 24h: {change_24h_pct:+.2f}% | "
            f"7d: {change_7d_pct:+.2f}%"
        ),
        value=change_24h_pct,
    ), state_update


# ─── Fetch All Prices (for summary) ─────────────────────────────────────────

def fetch_all_prices(tickers: list[str]) -> dict[str, Optional[float]]:
    """
    Fetch current prices for a list of tickers.
    Uses Polygon snapshot for stocks (1 API call for all), yfinance as fallback.
    """
    prices: dict[str, Optional[float]] = {}

    if USE_POLYGON_PRIMARY:
        # Try Polygon snapshot for all stocks in one call
        stock_tickers = [t for t in tickers if not t.endswith("-USD")]
        crypto_tickers = [t for t in tickers if t.endswith("-USD")]

        snapshots = get_all_stock_snapshots(stock_tickers)
        for ticker in stock_tickers:
            snap = snapshots.get(ticker)
            if snap and snap.get("price"):
                prices[ticker] = float(snap["price"])
                continue
            # Fallback to yfinance for this ticker
            prices[ticker] = _yfinance_price(ticker)

        # Crypto via Polygon individual calls or yfinance
        for ticker in crypto_tickers:
            price = polygon_get_crypto_price(ticker)
            if price is not None:
                prices[ticker] = price
            else:
                prices[ticker] = _yfinance_price(ticker)

        logger.info(f"Fetched {len(prices)} prices (Polygon primary)")
    else:
        # Pure yfinance path
        for ticker in tickers:
            prices[ticker] = _yfinance_price(ticker)
        logger.info(f"Fetched {len(prices)} prices (yfinance only)")

    return prices


def _yfinance_price(ticker: str) -> Optional[float]:
    """Get price via yfinance (helper for fallback)."""
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if hist is None or hist.empty:
            return None
        return float(hist["Close"].iloc[-1])
    except Exception as e:
        logger.error(f"yfinance price failed for {ticker}: {e}")
        return None


# ─── Full Analysis Run ──────────────────────────────────────────────────────

def analyze_market_health(previous_state: dict) -> tuple[list[MarketSignal], dict]:
    """
    Run all technical analysis checks.

    Returns:
        (list_of_signals, combined_state_update)
    """
    signals: list[MarketSignal] = []
    combined_state: dict = {}

    # 1. SMA Analysis (Polygon primary → yfinance fallback)
    sma_signal, sma_state = analyze_sma(previous_state)
    if sma_signal:
        signals.append(sma_signal)
    combined_state.update(sma_state)

    # 2. RSI Analysis (Polygon only — bonus indicator)
    rsi_signal, rsi_state = analyze_rsi(previous_state)
    if rsi_signal:
        signals.append(rsi_signal)
    combined_state.update(rsi_state)

    # 3. Trailing Stop (yfinance — needs full OHLC DataFrame)
    stop_signal, stop_state = analyze_trailing_stop(previous_state)
    if stop_signal:
        signals.append(stop_signal)
    combined_state.update(stop_state)

    # 4. Crypto Canary (yfinance — needs multi-day data)
    crypto_signal, crypto_state = analyze_crypto_canary(previous_state)
    if crypto_signal:
        signals.append(crypto_signal)
    combined_state.update(crypto_state)

    return signals, combined_state
