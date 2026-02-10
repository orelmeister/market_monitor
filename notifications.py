"""
notifications.py — Alert delivery via Telegram.

Implements:
  - Telegram Bot API notifications (immediate push)
  - Rate limiting to prevent alert spam
  - Daily summary formatting
"""

import logging
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

import requests

from config import (
    TELEGRAM_BOT_TOKEN,
    TELEGRAM_CHAT_ID,
    ALERT_COOLDOWN_CRITICAL_HOURS,
    ALERT_COOLDOWN_WARNING_HOURS,
    ALERT_COOLDOWN_INFO_HOURS,
)

logger = logging.getLogger(__name__)


# ─── Rate Limiting ───────────────────────────────────────────────────────────

# In-memory cooldown tracker: { "alert_key": datetime_of_last_send }
_alert_cooldowns: dict[str, datetime] = {}


def _get_cooldown_hours(level: str) -> int:
    """Get cooldown period in hours for a given alert level."""
    return {
        "CRITICAL": ALERT_COOLDOWN_CRITICAL_HOURS,
        "WARNING": ALERT_COOLDOWN_WARNING_HOURS,
        "INFO": ALERT_COOLDOWN_INFO_HOURS,
        "GREEN": ALERT_COOLDOWN_WARNING_HOURS,
    }.get(level, ALERT_COOLDOWN_WARNING_HOURS)


def _is_rate_limited(alert_key: str, level: str) -> bool:
    """
    Check if an alert is rate-limited (within cooldown window).
    Returns True if we should NOT send this alert.
    """
    cooldown_hours = _get_cooldown_hours(level)
    last_sent = _alert_cooldowns.get(alert_key)

    if last_sent is None:
        return False

    elapsed = datetime.utcnow() - last_sent
    if elapsed < timedelta(hours=cooldown_hours):
        logger.debug(
            f"Alert '{alert_key}' rate-limited. "
            f"Last sent {elapsed} ago (cooldown: {cooldown_hours}h)"
        )
        return True

    return False


def _record_alert_sent(alert_key: str) -> None:
    """Record that an alert was sent (for rate limiting)."""
    _alert_cooldowns[alert_key] = datetime.utcnow()


# ─── Telegram ────────────────────────────────────────────────────────────────

def send_telegram(message: str) -> bool:
    """
    Send a message via Telegram Bot API.

    Uses: POST https://api.telegram.org/bot{TOKEN}/sendMessage
    Parameters: chat_id, text, parse_mode=HTML

    Returns True if successful.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram not configured (missing BOT_TOKEN or CHAT_ID)")
        return False

    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }

        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()

        result = response.json()
        if result.get("ok"):
            logger.info("Telegram message sent successfully")
            return True
        else:
            logger.error(f"Telegram API error: {result}")
            return False

    except requests.RequestException as e:
        logger.error(f"Telegram send failed: {e}")
        return False


# ─── Unified Alert Dispatcher ────────────────────────────────────────────────

def send_alert(
    subject: str,
    body: str,
    level: str = "INFO",
    alert_key: Optional[str] = None,
) -> dict[str, bool]:
    """
    Send an alert via Telegram, with rate limiting.

    Args:
        subject: Alert subject line
        body: Alert body text
        level: One of "CRITICAL", "WARNING", "INFO", "GREEN"
        alert_key: Unique key for rate limiting (defaults to subject)

    Returns:
        Dict of channel -> success/failure
    """
    key = alert_key or subject
    results: dict[str, bool] = {"telegram": False}

    # Check rate limiting
    if _is_rate_limited(key, level):
        logger.info(f"Alert rate-limited: [{level}] {subject}")
        results["rate_limited"] = True
        return results

    # Format message with level prefix
    level_emoji = {
        "CRITICAL": "🚨",
        "WARNING": "⚠️",
        "INFO": "ℹ️",
        "GREEN": "🟢",
    }.get(level, "📊")

    formatted_body = f"{level_emoji} [{level}] {subject}\n{'─' * 40}\n{body}"

    # Send via Telegram
    logger.info(f"Sending [{level}] alert: {subject}")

    # Telegram: always for CRITICAL/WARNING/GREEN, also for daily summary
    if level in ("CRITICAL", "WARNING", "GREEN") or alert_key == "DAILY_SUMMARY":
        results["telegram"] = send_telegram(formatted_body)

    # Record for rate limiting
    _record_alert_sent(key)

    return results


# ─── Daily Summary ───────────────────────────────────────────────────────────

def send_daily_summary(state: dict, info_signals: list) -> dict[str, bool]:
    """
    Compile and send a daily summary of all INFO-level signals and current state.
    """
    now = datetime.now(ZoneInfo("US/Eastern")).strftime("%Y-%m-%d %I:%M %p %Z")

    lines = [
        f"📊 DAILY MARKET SUMMARY — {now}",
        "═" * 45,
        "",
    ]

    # Current prices from state
    if state.get("spy_price"):
        sma = state.get("spy_sma_200", "N/A")
        regime = "BULLISH ✅" if state.get("spy_above_sma") else "BEARISH ❌"
        lines.append(f"SPY:     ${state['spy_price']:.2f}  (SMA: ${sma})  {regime}")

    if state.get("spy_rsi"):
        rsi = state["spy_rsi"]
        rsi_label = "OVERBOUGHT ⚠️" if rsi >= 70 else "OVERSOLD 🟢" if rsi <= 30 else "NEUTRAL"
        lines.append(f"RSI(14): {rsi:.1f}  {rsi_label}")

    if state.get("ivv_price"):
        hwm = state.get("ivv_high_water_mark", "N/A")
        drop = state.get("ivv_drop_pct", 0)
        lines.append(f"IVV:     ${state['ivv_price']:.2f}  (30d High: ${hwm}, Drop: {drop:.1f}%)")

    if state.get("btc_price"):
        c24 = state.get("btc_change_24h_pct", 0)
        c7d = state.get("btc_change_7d_pct", 0)
        lines.append(f"BTC:     ${state['btc_price']:,.2f}  (24h: {c24:+.1f}%, 7d: {c7d:+.1f}%)")

    lines.append("")

    # Fed rate
    if state.get("fed_rate_current") is not None:
        lines.append(
            f"Fed Rate: {state['fed_rate_current']}% "
            f"(prev: {state.get('fed_rate_previous', 'N/A')}%)"
        )

    # News
    if state.get("news_negative_hits") is not None:
        lines.append(
            f"News:    {state['news_negative_hits']} negative hits / "
            f"{state.get('news_articles_scanned', 0)} articles"
        )

    lines.append("")
    lines.append("─" * 45)

    # INFO signals accumulated today
    if info_signals:
        lines.append("Signals Today:")
        for sig in info_signals:
            lines.append(f"  • {sig.message}")
    else:
        lines.append("No notable signals today.")

    body = "\n".join(lines)

    return send_alert(
        subject="Daily Market Summary",
        body=body,
        level="INFO",
        alert_key="DAILY_SUMMARY",
    )
