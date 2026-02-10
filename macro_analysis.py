"""
macro_analysis.py — Macro / News sentiment analysis using FMP API.

Implements:
  - News sentiment scanning (keyword-based negative sentiment detection)
  - Federal Reserve interest rate decision tracking (pivot detection)
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

import requests

from config import (
    FMP_API_KEY,
    FMP_NEWS_ENDPOINT,
    FMP_ECONOMIC_CALENDAR_ENDPOINT,
    FMP_NEWS_LIMIT,
    NEGATIVE_KEYWORDS,
    NEWS_NEGATIVE_THRESHOLD,
)

logger = logging.getLogger(__name__)


class MacroSignal:
    """Represents a macro-level signal from news or economic data."""

    def __init__(self, name: str, level: str, message: str, value: Optional[float] = None):
        self.name = name
        self.level = level
        self.message = message
        self.value = value

    def __repr__(self) -> str:
        return f"MacroSignal({self.level}: {self.name} — {self.message})"


# ─── News Sentiment ──────────────────────────────────────────────────────────

def fetch_news_sentiment() -> tuple[Optional[MacroSignal], dict]:
    """
    Fetch latest stock market news from FMP and perform keyword-based
    sentiment analysis.

    FMP Endpoint: GET /api/v3/stock_news?limit=50&apikey={KEY}

    Returns:
        (signal_or_None, state_dict)
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping news sentiment")
        return None, {}

    try:
        url = f"{FMP_NEWS_ENDPOINT}?limit={FMP_NEWS_LIMIT}&apikey={FMP_API_KEY}"
        logger.info("Fetching news from FMP...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        articles = response.json()

        if not isinstance(articles, list):
            logger.warning(f"Unexpected FMP news response format: {type(articles)}")
            return None, {}

        # Count negative keyword hits across all article titles and texts
        negative_hits = 0
        matched_keywords: list[str] = []
        negative_headlines: list[str] = []

        for article in articles:
            title = article.get("title", "").lower()
            text = article.get("text", "").lower()
            combined = f"{title} {text}"

            for keyword in NEGATIVE_KEYWORDS:
                count = combined.count(keyword.lower())
                if count > 0:
                    negative_hits += count
                    if keyword not in matched_keywords:
                        matched_keywords.append(keyword)
                    if title and title not in [h.lower() for h in negative_headlines]:
                        negative_headlines.append(article.get("title", "N/A"))

        state_update = {
            "news_negative_hits": negative_hits,
            "news_matched_keywords": matched_keywords[:10],  # cap for state size
            "news_articles_scanned": len(articles),
            "news_last_check": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"News sentiment: {negative_hits} negative hits across "
            f"{len(articles)} articles (keywords: {matched_keywords})"
        )

        if negative_hits >= NEWS_NEGATIVE_THRESHOLD:
            top_headlines = "\n".join(f"  • {h}" for h in negative_headlines[:5])
            return MacroSignal(
                name="NEWS_SENTIMENT_NEGATIVE",
                level="WARNING",
                message=(
                    f"⚠️ NEGATIVE NEWS SPIKE DETECTED\n"
                    f"Found {negative_hits} negative keyword matches "
                    f"in {len(articles)} articles\n"
                    f"Keywords: {', '.join(matched_keywords[:5])}\n"
                    f"Top headlines:\n{top_headlines}"
                ),
                value=float(negative_hits),
            ), state_update

        return MacroSignal(
            name="NEWS_STATUS",
            level="INFO",
            message=f"News: {negative_hits} neg hits / {len(articles)} articles scanned",
            value=float(negative_hits),
        ), state_update

    except requests.RequestException as e:
        logger.error(f"FMP news API request failed: {e}")
        return None, {"news_last_error": str(e)}
    except Exception as e:
        logger.error(f"News sentiment analysis failed: {e}")
        return None, {"news_last_error": str(e)}


# ─── Federal Reserve Rate Decision ──────────────────────────────────────────

def fetch_fed_rate(previous_state: dict) -> tuple[Optional[MacroSignal], dict]:
    """
    Fetch recent Federal Reserve interest rate decisions from FMP
    economic calendar.

    FMP Endpoint: GET /api/v3/economic_calendar?from={DATE}&to={DATE}&apikey={KEY}

    Looks for events with "Federal Funds Rate" or similar.
    Compares current rate to previous to detect Fed pivot (rate cut).

    Returns:
        (signal_or_None, state_dict)
    """
    if not FMP_API_KEY:
        logger.warning("FMP_API_KEY not set — skipping Fed rate check")
        return None, {}

    try:
        # Look back 90 days for recent Fed decisions
        date_to = datetime.utcnow().strftime("%Y-%m-%d")
        date_from = (datetime.utcnow() - timedelta(days=90)).strftime("%Y-%m-%d")

        url = (
            f"{FMP_ECONOMIC_CALENDAR_ENDPOINT}"
            f"?from={date_from}&to={date_to}&apikey={FMP_API_KEY}"
        )

        logger.info("Fetching economic calendar from FMP...")
        response = requests.get(url, timeout=15)
        response.raise_for_status()
        events = response.json()

        if not isinstance(events, list):
            logger.warning(f"Unexpected FMP calendar response: {type(events)}")
            return None, {}

        # Filter for Federal Funds Rate / Fed Interest Rate events
        fed_events = [
            e for e in events
            if any(
                kw in (e.get("event", "") or "").lower()
                for kw in ["federal funds rate", "interest rate decision", "fed interest rate"]
            )
        ]

        if not fed_events:
            logger.info("No Fed rate events found in the last 90 days")
            return None, {"fed_last_check": datetime.utcnow().isoformat()}

        # Sort by date descending, take the most recent
        fed_events.sort(key=lambda x: x.get("date", ""), reverse=True)
        latest = fed_events[0]

        current_rate = latest.get("actual")
        previous_rate = latest.get("previous")
        event_date = latest.get("date", "N/A")

        state_update = {
            "fed_rate_current": current_rate,
            "fed_rate_previous": previous_rate,
            "fed_rate_date": event_date,
            "fed_last_check": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Fed Rate: current={current_rate}, previous={previous_rate}, "
            f"date={event_date}"
        )

        # Detect rate cut (Fed Pivot)
        if current_rate is not None and previous_rate is not None:
            try:
                curr = float(current_rate)
                prev = float(previous_rate)
                last_known_rate = previous_state.get("fed_rate_current")

                # Only alert if this is a NEW rate change we haven't seen
                if curr < prev and (last_known_rate is None or float(last_known_rate) != curr):
                    return MacroSignal(
                        name="FED_PIVOT",
                        level="INFO",
                        message=(
                            f"🟢 FED PIVOT — RATE CUT DETECTED\n"
                            f"Rate: {prev}% → {curr}%\n"
                            f"Date: {event_date}\n"
                            f"Implication: Dovish — potential BUY signal for equities"
                        ),
                        value=curr,
                    ), state_update

                elif curr > prev and (last_known_rate is None or float(last_known_rate) != curr):
                    return MacroSignal(
                        name="FED_HIKE",
                        level="WARNING",
                        message=(
                            f"🔴 FED RATE HIKE\n"
                            f"Rate: {prev}% → {curr}%\n"
                            f"Date: {event_date}\n"
                            f"Implication: Hawkish — tighten risk"
                        ),
                        value=curr,
                    ), state_update

            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse Fed rate values: {e}")

        return MacroSignal(
            name="FED_STATUS",
            level="INFO",
            message=f"Fed Rate: {current_rate}% (prev: {previous_rate}%) as of {event_date}",
            value=float(current_rate) if current_rate else None,
        ), state_update

    except requests.RequestException as e:
        logger.error(f"FMP economic calendar request failed: {e}")
        return None, {"fed_last_error": str(e)}
    except Exception as e:
        logger.error(f"Fed rate analysis failed: {e}")
        return None, {"fed_last_error": str(e)}


# ─── Full Macro Check ───────────────────────────────────────────────────────

def check_macro_environment(previous_state: dict) -> tuple[list, dict]:
    """
    Run all macro analysis checks (news + Fed rate).

    Returns:
        (list_of_signals, combined_state_update)
    """
    signals: list = []
    combined_state: dict = {}

    # 1. News Sentiment
    news_signal, news_state = fetch_news_sentiment()
    if news_signal:
        signals.append(news_signal)
    combined_state.update(news_state)

    # 2. Fed Rate
    fed_signal, fed_state = fetch_fed_rate(previous_state)
    if fed_signal:
        signals.append(fed_signal)
    combined_state.update(fed_state)

    return signals, combined_state
