#!/usr/bin/env python3
"""
market_monitor.py — Market Crash & Recovery Monitor (Main Entry Point)

A "Market Sentinel" that runs continuously on DigitalOcean App Platform
as a Worker process. Uses APScheduler to run analysis jobs on schedule:

  - Market health check: every 15 min during trading hours (Mon-Fri 9:30-16:00 ET)
  - Crypto canary:       every 30 min, 24/7
  - News sentiment:      every 60 min during extended hours (Mon-Fri 8:00-18:00 ET)
  - Daily summary:       once at 5:00 PM ET (Mon-Fri)

Alerts are sent via Telegram when state changes are detected.
"""

import logging
import signal
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from config import (
    LOG_LEVEL,
    LOG_FORMAT,
    MARKET_CHECK_INTERVAL_MIN,
    CRYPTO_CHECK_INTERVAL_MIN,
    NEWS_CHECK_INTERVAL_MIN,
    DAILY_SUMMARY_HOUR,
    DAILY_SUMMARY_MINUTE,
    ALL_TICKERS,
    FMP_API_KEY,
    TELEGRAM_BOT_TOKEN,
)
from technical_analysis import (
    analyze_sma,
    analyze_trailing_stop,
    analyze_crypto_canary,
    fetch_all_prices,
    MarketSignal,
)
from macro_analysis import check_macro_environment
from notifications import send_alert, send_daily_summary
from state_manager import load_state, save_state, update_state, get_state_summary
from meme_scanner import job_meme_scan, job_trending_scan, job_portfolio_tokens

# ─── Logging Setup ───────────────────────────────────────────────────────────

logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format=LOG_FORMAT)
logger = logging.getLogger("market_monitor")

# Reduce noise from third-party libs
logging.getLogger("yfinance").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("apscheduler").setLevel(logging.WARNING)

# ─── Accumulated INFO signals for daily summary ─────────────────────────────
_daily_info_signals: list = []


# ─── Job: Market Health Check (equities) ────────────────────────────────────

def job_market_health() -> None:
    """
    Scheduled job: Run SMA and trailing stop analysis on equities.
    Runs every 15 min during market hours.
    """
    logger.info("═══ Running Market Health Check ═══")
    try:
        state = load_state()

        # 1. SPY SMA Analysis
        sma_signal, sma_state = analyze_sma(state)
        state = update_state(state, sma_state)

        if sma_signal:
            _handle_signal(sma_signal)

        # 2. IVV Trailing Stop
        stop_signal, stop_state = analyze_trailing_stop(state)
        state = update_state(state, stop_state)

        if stop_signal:
            _handle_signal(stop_signal)

        # Save updated state
        save_state(state)
        logger.info(get_state_summary(state))

    except Exception as e:
        logger.error(f"Market health check failed: {e}", exc_info=True)


# ─── Job: Crypto Canary ─────────────────────────────────────────────────────

def job_crypto_canary() -> None:
    """
    Scheduled job: Monitor BTC for sudden crashes.
    Runs every 30 min, 24/7.
    """
    logger.info("═══ Running Crypto Canary Check ═══")
    try:
        state = load_state()

        crypto_signal, crypto_state = analyze_crypto_canary(state)
        state = update_state(state, crypto_state)

        if crypto_signal:
            _handle_signal(crypto_signal)

        save_state(state)

    except Exception as e:
        logger.error(f"Crypto canary check failed: {e}", exc_info=True)


# ─── Job: News & Macro Sentiment ────────────────────────────────────────────

def job_macro_sentiment() -> None:
    """
    Scheduled job: Check FMP news sentiment and Fed rate decisions.
    Runs every 60 min during extended market hours.
    """
    logger.info("═══ Running Macro Sentiment Check ═══")
    try:
        state = load_state()

        signals, macro_state = check_macro_environment(state)
        state = update_state(state, macro_state)

        for sig in signals:
            _handle_signal(sig)

        save_state(state)

    except Exception as e:
        logger.error(f"Macro sentiment check failed: {e}", exc_info=True)


# ─── Job: Daily Summary ─────────────────────────────────────────────────────

def job_daily_summary() -> None:
    """
    Scheduled job: Send a daily summary at 5 PM ET.
    Includes all current prices, state, and accumulated INFO signals.
    """
    global _daily_info_signals
    logger.info("═══ Sending Daily Summary ═══")

    try:
        state = load_state()

        # Fetch latest prices for all tickers
        prices = fetch_all_prices(ALL_TICKERS)
        for ticker, price in prices.items():
            if price is not None:
                state[f"price_{ticker}"] = price

        save_state(state)

        # Send the summary
        results = send_daily_summary(state, _daily_info_signals)
        logger.info(f"Daily summary sent: {results}")

        # Reset daily accumulator
        _daily_info_signals = []

    except Exception as e:
        logger.error(f"Daily summary failed: {e}", exc_info=True)


# ─── Signal Handler ──────────────────────────────────────────────────────────

def _handle_signal(signal_obj) -> None:
    """
    Process a signal: dispatch alerts for WARNING/CRITICAL/GREEN,
    accumulate INFO signals for daily summary.
    """
    global _daily_info_signals

    level = signal_obj.level
    name = signal_obj.name
    message = signal_obj.message

    logger.info(f"Signal: [{level}] {name} — {message[:80]}...")

    if level in ("CRITICAL", "WARNING", "GREEN"):
        # Immediate alert
        results = send_alert(
            subject=name.replace("_", " ").title(),
            body=message,
            level=level,
            alert_key=name,
        )
        logger.info(f"Alert results for {name}: {results}")

    elif level == "INFO":
        # Accumulate for daily summary
        _daily_info_signals.append(signal_obj)


# ─── Startup Validation ─────────────────────────────────────────────────────

def validate_configuration() -> bool:
    """Check that required configuration is present."""
    warnings = []

    if not FMP_API_KEY:
        warnings.append("FMP_API_KEY not set — news/macro analysis will be skipped")

    if not TELEGRAM_BOT_TOKEN:
        warnings.append("TELEGRAM_BOT_TOKEN not set — Telegram alerts disabled")

    for w in warnings:
        logger.warning(f"⚠️  {w}")

    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ No notification channels configured! Set TELEGRAM_BOT_TOKEN env var.")
        return False

    return True


# ─── Startup Notification ───────────────────────────────────────────────────

STARTUP_COOLDOWN_SECONDS = 300  # 5 minutes — suppress duplicate startup alerts

def send_startup_notification() -> None:
    """Send a notification that the monitor has started.
    Persists startup time in state file to prevent duplicate alerts
    when DigitalOcean restarts the container multiple times during deploy.
    """
    eastern = ZoneInfo("US/Eastern")
    now_et = datetime.now(eastern)

    # ── Dedup: skip if we already sent a startup alert recently ──
    state = load_state()
    last_startup_iso = state.get("_last_startup")
    if last_startup_iso:
        try:
            last_startup = datetime.fromisoformat(last_startup_iso)
            # Attach Eastern tz if the stored value is naive
            if last_startup.tzinfo is None:
                last_startup = last_startup.replace(tzinfo=eastern)
            if (now_et - last_startup) < timedelta(seconds=STARTUP_COOLDOWN_SECONDS):
                logger.info(
                    "Startup notification suppressed — last sent %s ago",
                    now_et - last_startup,
                )
                return
        except (ValueError, TypeError):
            pass  # corrupted value, send anyway

    # ── Record this startup ──
    state["_last_startup"] = now_et.isoformat()
    save_state(state)

    now = now_et.strftime("%Y-%m-%d %I:%M %p %Z")
    body = (
        f"🚀 Market Monitor Started\n"
        f"Time: {now}\n"
        f"Schedule:\n"
        f"  • Market check: every {MARKET_CHECK_INTERVAL_MIN} min (market hours)\n"
        f"  • Crypto check: every {CRYPTO_CHECK_INTERVAL_MIN} min (24/7)\n"
        f"  • News check: every {NEWS_CHECK_INTERVAL_MIN} min\n"
        f"  • Daily summary: {DAILY_SUMMARY_HOUR}:00 ET\n"
        f"Channels: "
        f"{'Telegram ✅' if TELEGRAM_BOT_TOKEN else 'Telegram ❌'} | "
        f"{'FMP ✅' if FMP_API_KEY else 'FMP ❌'}"
    )

    send_alert(
        subject="Market Monitor Started",
        body=body,
        level="GREEN",
        alert_key="STARTUP",
    )


# ─── Graceful Shutdown ──────────────────────────────────────────────────────

def handle_shutdown(signum, frame):
    """Handle SIGTERM/SIGINT for graceful shutdown."""
    logger.info(f"Received signal {signum} — shutting down gracefully...")
    send_alert(
        subject="Market Monitor Stopped",
        body=f"Monitor shut down at {datetime.now(ZoneInfo('US/Eastern')).strftime('%Y-%m-%d %I:%M %p %Z')}",
        level="INFO",
        alert_key="SHUTDOWN",
    )
    sys.exit(0)


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    """
    Main entry point. Sets up APScheduler with all monitoring jobs
    and runs the blocking scheduler loop.
    """
    logger.info("=" * 60)
    logger.info("  MARKET CRASH & RECOVERY MONITOR")
    logger.info("  Starting up...")
    logger.info("=" * 60)

    # Validate configuration
    if not validate_configuration():
        logger.error("Configuration validation failed. Exiting.")
        sys.exit(1)

    # Register shutdown handlers
    signal.signal(signal.SIGTERM, handle_shutdown)
    signal.signal(signal.SIGINT, handle_shutdown)

    # Send startup notification
    send_startup_notification()

    # Run an initial check immediately
    logger.info("Running initial checks...")
    try:
        job_market_health()
        job_crypto_canary()
        job_macro_sentiment()
        job_meme_scan()  # Initial meme coin scan
        job_portfolio_tokens()  # Initial portfolio token check (AUKI, USOR)
    except Exception as e:
        logger.error(f"Initial check failed (non-fatal): {e}")

    # ─── Set Up Scheduler ────────────────────────────────────────────────

    scheduler = BlockingScheduler(timezone="US/Eastern")

    # Market health: every 15 min, Mon-Fri during market hours (9:30 AM - 4:00 PM ET)
    scheduler.add_job(
        job_market_health,
        CronTrigger(
            day_of_week="mon-fri",
            hour="9-15",
            minute=f"*/{MARKET_CHECK_INTERVAL_MIN}",
            timezone="US/Eastern",
        ),
        id="market_health",
        name="Market Health Check",
        misfire_grace_time=300,
    )

    # Also run at market open and close
    scheduler.add_job(
        job_market_health,
        CronTrigger(day_of_week="mon-fri", hour=9, minute=30, timezone="US/Eastern"),
        id="market_open",
        name="Market Open Check",
        misfire_grace_time=120,
    )

    scheduler.add_job(
        job_market_health,
        CronTrigger(day_of_week="mon-fri", hour=16, minute=5, timezone="US/Eastern"),
        id="market_close",
        name="Market Close Check",
        misfire_grace_time=120,
    )

    # Crypto canary: every 30 min, 24/7
    scheduler.add_job(
        job_crypto_canary,
        IntervalTrigger(minutes=CRYPTO_CHECK_INTERVAL_MIN),
        id="crypto_canary",
        name="Crypto Canary",
        misfire_grace_time=300,
    )

    # ─── Meme Coin Monitoring (24/7) ─────────────────────────────────────────
    
    # New token scan: every 2 minutes, 24/7
    scheduler.add_job(
        job_meme_scan,
        IntervalTrigger(minutes=2),
        id="meme_scan",
        name="Meme Coin Scanner",
        misfire_grace_time=60,
    )

    # Trending tokens: every 5 minutes, 24/7
    scheduler.add_job(
        job_trending_scan,
        IntervalTrigger(minutes=5),
        id="trending_scan",
        name="Trending Tokens",
        misfire_grace_time=120,
    )

    # Portfolio tokens: every 5 minutes, 24/7 (AUKI, USOR, etc.)
    scheduler.add_job(
        job_portfolio_tokens,
        IntervalTrigger(minutes=5),
        id="portfolio_tokens",
        name="Portfolio Token Monitor",
        misfire_grace_time=120,
    )

    # News/Macro sentiment: every 60 min, Mon-Fri 8 AM - 6 PM ET
    scheduler.add_job(
        job_macro_sentiment,
        CronTrigger(
            day_of_week="mon-fri",
            hour="8-17",
            minute=0,
            timezone="US/Eastern",
        ),
        id="macro_sentiment",
        name="Macro Sentiment",
        misfire_grace_time=300,
    )

    # Daily summary: 5:00 PM ET, Mon-Fri
    scheduler.add_job(
        job_daily_summary,
        CronTrigger(
            day_of_week="mon-fri",
            hour=DAILY_SUMMARY_HOUR,
            minute=DAILY_SUMMARY_MINUTE,
            timezone="US/Eastern",
        ),
        id="daily_summary",
        name="Daily Summary",
        misfire_grace_time=600,
    )

    # Log scheduled jobs
    logger.info("Scheduled jobs:")
    for job in scheduler.get_jobs():
        logger.info(f"  • {job.name} — {job.trigger}")

    logger.info("Scheduler started. Monitoring markets...")
    logger.info("=" * 60)

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")


if __name__ == "__main__":
    main()
