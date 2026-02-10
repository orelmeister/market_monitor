# 📊 Market Crash & Recovery Monitor

An always-on **Market Sentinel** that monitors equities, crypto, and macro indicators to detect market crashes (Risk-Off) and recovery signals (Risk-On). Sends real-time alerts via **Telegram**.

## Features

- **200-Day SMA Tracking** — Detects when SPY crosses above/below the 200-day moving average
- **RSI Overbought/Oversold** — 14-day RSI alerts via Polygon.io server-side calculation
- **Trailing Stop Monitor** — Alerts when IVV drops >5% from its 30-day high
- **Crypto Canary** — BTC 24-hour crash detection (>10% drop = liquidity warning)
- **News Sentiment** — FMP-powered keyword scanning for crash-related headlines
- **Fed Rate Tracking** — Detects Federal Reserve rate cuts (pivot/buy signals)
- **Daily Digest** — End-of-day summary of all monitored assets
- **Rate-Limited Alerts** — No spam, intelligent cooldown per alert type
- **Dual Data Sources** — Polygon.io (primary) with yfinance fallback for reliability

## Architecture

```
market_monitor.py          ← Entry point (APScheduler-based worker)
├── technical_analysis.py  ← SMA, RSI, trailing stop, crypto canary
├── polygon_provider.py    ← Polygon.io REST API (primary data source)
├── macro_analysis.py      ← FMP news sentiment, Fed rate
├── notifications.py       ← Telegram alerting
├── state_manager.py       ← JSON state persistence
└── config.py              ← All constants and thresholds
```

## Quick Start (Local)

```bash
# 1. Clone
git clone https://github.com/orelmeister/market_monitor.git
cd market_monitor

# 2. Set up Python environment
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your API keys (see setup sections below)

# 5. Run
python market_monitor.py
```

## Setup: Telegram Bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot`, follow prompts to create your bot
3. Copy the **Bot Token** → set as `TELEGRAM_BOT_TOKEN`
4. Send any message to your new bot
5. Visit: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
6. Find `"chat":{"id":XXXXXX}` → set as `TELEGRAM_CHAT_ID`

## Setup: FMP API

1. Register at [Financial Modeling Prep](https://financialmodelingprep.com/developer)
2. Copy your API key → set as `FMP_API_KEY`

## Setup: Polygon.io (Optional, Recommended)

1. Sign up at [Polygon.io](https://polygon.io/) — **Free tier** (no credit card)
2. Copy your API key → set as `POLYGON_API_KEY`
3. Free tier provides: 5 API calls/min, end-of-day data
4. Enables: **server-side SMA** (replaces heavy data download), **RSI indicator**, **bulk price snapshots**

> **Note**: Polygon is optional. When not configured, the monitor uses yfinance for all data. When configured, Polygon is used as the primary source with yfinance as automatic fallback.

---

## Deploy to DigitalOcean App Platform

### Option A: Auto-Deploy from GitHub (Recommended)

1. Push this repo to GitHub
2. Go to [DigitalOcean Apps](https://cloud.digitalocean.com/apps) → **Create App**
3. Connect your GitHub repo
4. DO auto-detects `.do/app.yaml` — it creates a **Worker** (no HTTP)
5. Add your environment variables (marked as **Secret**):
   - `FMP_API_KEY`
   - `POLYGON_API_KEY`
   - `TELEGRAM_BOT_TOKEN`
   - `TELEGRAM_CHAT_ID`
6. Click **Deploy** — the worker starts monitoring immediately

### Option B: Using `doctl` CLI

```bash
# Install doctl: https://docs.digitalocean.com/reference/doctl/how-to/install/
doctl auth init

# Edit .do/app.yaml with your GitHub username
# Then:
doctl apps create --spec .do/app.yaml
```

### Cost
- **Worker (Basic)**: ~$5/month (1 vCPU, 0.5 GB RAM)
- More than sufficient for this monitoring workload

---

## Alert Levels

| Level      | Trigger Example                     | Delivery          |
|------------|-------------------------------------|--------------------|
| 🚨 CRITICAL | SPY crosses below 200-SMA          | Immediate (all)    |
| ⚠️ WARNING  | BTC drops >10% in 24h, RSI > 70    | Immediate (all)    |
| 🟢 GREEN    | SPY crosses above 200-SMA, RSI < 30| Immediate (all)    |
| ℹ️ INFO     | Daily status, Fed rate unchanged    | Daily digest       |

## Schedule

| Job             | Frequency                      | Timezone   |
|-----------------|-------------------------------|------------|
| Market health   | Every 15 min (Mon-Fri 9:30-16:00) | US/Eastern |
| Crypto canary   | Every 30 min (24/7)           | UTC        |
| News sentiment  | Every 60 min (Mon-Fri 8:00-18:00) | US/Eastern |
| Daily summary   | 5:00 PM (Mon-Fri)            | US/Eastern |

## Environment Variables

| Variable                  | Required | Description                              |
|---------------------------|----------|------------------------------------------|
| `FMP_API_KEY`             | Yes*     | Financial Modeling Prep API key          |
| `POLYGON_API_KEY`         | No       | Polygon.io API key (enables RSI, server-side SMA) |
| `TELEGRAM_BOT_TOKEN`     | Yes      | Telegram bot token from @BotFather       |
| `TELEGRAM_CHAT_ID`       | Yes      | Your Telegram chat ID                    |
| `LOG_LEVEL`              | No       | Logging level (default: INFO)            |
| `ALERT_COOLDOWN_HOURS`   | No       | Hours between duplicate alerts (default: 4) |
| `MONITOR_INTERVAL_MINUTES` | No     | Market check interval (default: 15)     |

\* Required for news/macro analysis

## License

MIT
