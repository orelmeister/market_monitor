"""
state_manager.py — JSON-based state persistence for Market Monitor.

Tracks previous market state to:
  - Detect state CHANGES (crossovers, new alerts)
  - Prevent duplicate alert spam
  - Persist across restarts (within the same deployment)

State is stored in a local JSON file (monitor_state.json).
On DigitalOcean App Platform, this file is ephemeral (resets on redeploy),
which is acceptable since alerts are triggered by state changes.
"""

import json
import logging
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from config import STATE_FILE_PATH

logger = logging.getLogger(__name__)


def load_state() -> dict[str, Any]:
    """
    Load the previous state from the JSON file.
    Returns empty dict if file doesn't exist or is corrupt.
    """
    if not os.path.exists(STATE_FILE_PATH):
        logger.info(f"No state file found at {STATE_FILE_PATH} — starting fresh")
        return {}

    try:
        with open(STATE_FILE_PATH, "r") as f:
            state = json.load(f)
            logger.info(f"Loaded state from {STATE_FILE_PATH} ({len(state)} keys)")
            return state
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Failed to load state file: {e} — starting fresh")
        return {}


def save_state(state: dict[str, Any]) -> bool:
    """
    Save the current state to the JSON file.
    Returns True if successful.
    """
    try:
        # Add metadata
        state["_last_updated"] = datetime.now(ZoneInfo("US/Eastern")).isoformat()
        state["_version"] = "1.0"

        with open(STATE_FILE_PATH, "w") as f:
            json.dump(state, f, indent=2, default=str)

        logger.info(f"State saved to {STATE_FILE_PATH}")
        return True
    except (IOError, TypeError) as e:
        logger.error(f"Failed to save state: {e}")
        return False


def update_state(current_state: dict[str, Any], updates: dict[str, Any]) -> dict[str, Any]:
    """
    Merge updates into the current state.
    Returns the merged state (does NOT save to disk — call save_state separately).
    """
    merged = {**current_state, **updates}
    return merged


def get_state_value(state: dict, key: str, default: Any = None) -> Any:
    """Safely get a value from state with a default."""
    return state.get(key, default)


def clear_state() -> bool:
    """Delete the state file (used for testing / reset)."""
    try:
        if os.path.exists(STATE_FILE_PATH):
            os.remove(STATE_FILE_PATH)
            logger.info(f"State file deleted: {STATE_FILE_PATH}")
        return True
    except IOError as e:
        logger.error(f"Failed to delete state file: {e}")
        return False


def get_state_summary(state: dict) -> str:
    """Generate a human-readable summary of the current state."""
    lines = ["Current Monitor State:"]

    if state.get("spy_price"):
        regime = "BULLISH" if state.get("spy_above_sma") else "BEARISH"
        lines.append(f"  SPY: ${state['spy_price']:.2f} (SMA: {state.get('spy_sma_200', 'N/A')}) [{regime}]")

    if state.get("ivv_price"):
        lines.append(
            f"  IVV: ${state['ivv_price']:.2f} "
            f"(HWM: {state.get('ivv_high_water_mark', 'N/A')}, "
            f"Drop: {state.get('ivv_drop_pct', 0):.1f}%)"
        )

    if state.get("btc_price"):
        lines.append(
            f"  BTC: ${state['btc_price']:,.2f} "
            f"(24h: {state.get('btc_change_24h_pct', 0):+.1f}%, "
            f"7d: {state.get('btc_change_7d_pct', 0):+.1f}%)"
        )

    if state.get("fed_rate_current") is not None:
        lines.append(f"  Fed Rate: {state['fed_rate_current']}%")

    if state.get("news_negative_hits") is not None:
        lines.append(f"  News: {state['news_negative_hits']} negative hits")

    lines.append(f"  Last Updated: {state.get('_last_updated', 'N/A')}")

    return "\n".join(lines)
