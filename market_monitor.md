# Project Specification: Market Crash & Recovery Monitor

## 1. Project Overview
Create a Python script (`market_monitor.py`) that acts as a "Market Sentinel." It will run periodically (e.g., via cron or a loop) to monitor specific financial assets, technical indicators, and news sentiment. Its goal is to detect market crashes (Risk-Off) and recovery signals (Risk-On) based on the user's "Core vs. Defense" strategy.

## 2. APIs & Libraries
* **yfinance**: For fetching real-time price data and historical data (OHLC) for calculations.
* **Financial Modeling Prep (FMP)**: Use the user's existing API key. Use endpoints for:
    * General Market News / Sentiment.
    * Economic Calendar (specifically looking for "Fed Interest Rate" decisions).
* **smtplib / ssl**: For sending email alerts.
* **requests**: For API calls.
* **dotenv**: To manage sensitive keys (`FMP_API_KEY`, `EMAIL_USER`, `EMAIL_PASS`).

## 3. Assets to Monitor
The script must track the following tickers:
* **Core Portfolio**: `IVV` (S&P 500 Core), `BFGFX` (Growth/SpaceX proxy).
* **Defensive Income**: `JEPI`, `JEPQ`.
* **Leading Indicators**: `BTC-USD` (Bitcoin), `ETH-USD` (Ethereum).
* **Benchmark**: `SPY` (S&P 500 ETF) for technical analysis.

## 4. Key Logic & Functions

### A. Technical Analysis (The "Trigger" System)
Create a function `analyze_market_health()` that calculates:
1.  **200-Day Moving Average (SMA)** for `SPY`.
    * *Logic:* Compare Current Price vs. 200-SMA.
    * *Signal:* If Price < 200-SMA = **BEARISH**. If Price > 200-SMA = **BULLISH**.
2.  **Trailing Stop Calculation**:
    * Store a "High Water Mark" (highest price seen in the last 30 days) for `IVV`.
    * *Signal:* If current price is < 5% of High Water Mark = **STOP LOSS ALERT**.
3.  **Crypto Canary**:
    * Calculate the 7-day percent change for `BTC-USD`.
    * *Signal:* If BTC drops > 10% in 24h = **CRASH IMMINENT ALERT**.

### B. News & Macro Sentiment (FMP API)
Create a function `check_macro_environment()`:
1.  **News Sentiment:** Fetch the latest stock market news via FMP. Perform simple keyword matching (e.g., count occurrences of "Crash", "Recession", "Plummet", "Liquidity Crisis").
2.  **Fed Rate:** Fetch the latest Federal Reserve Interest Rate decision.
    * *Signal:* If Rate < Previous Rate = **FED PIVOT (BUY SIGNAL)**.

### C. Alerting System
Create a function `send_alert(subject, body, level)`:
1.  **Levels:** INFO, WARNING, CRITICAL.
2.  **Channel:** Send via Email (using Gmail SMTP or similar).
    * *Optional:* Add a placeholder for Push Notifications (Pushover/Telegram) if available.
3.  **Rate Limiting:** Ensure we don't spam the user. Only send "Critical" alerts immediately. Summarize "Info" alerts once a day.

## 5. Execution Flow
The `main()` function should:
1.  Load environment variables.
2.  Fetch data for all tickers.
3.  Run Technical Analysis (SMA, Stops, Crypto trends).
4.  Run Macro Analysis (FMP News/Rates).
5.  Construct a status report string.
6.  Compare current status to "Previous State" (saved in a local `.json` file to track state changes).
7.  **Trigger Logic:**
    * IF `SPY` crosses BELOW 200-SMA -> **Send CRITICAL ALERT: "Defensive Mode Triggered - Move to JEPI"**
    * IF `BTC` drops > 10% -> **Send WARNING ALERT: "Liquidity Drain Detected"**
    * IF `IVV` drops > 5% from High -> **Send WARNING ALERT: "Trailing Stop Hit"**
    * IF `SPY` crosses ABOVE 200-SMA -> **Send GREEN ALERT: "Recovery Detected - Consider IVV Re-entry"**

## 6. Project Structure
* `.env` (Stores API Keys - do not commit)
* `market_monitor.py` (Main script)
* `monitor_state.json` (Stores last known prices/states to prevent duplicate alerts)
* `requirements.txt` (yfinance, requests, python-dotenv)

## 7. Instructions for Copilot
* Write the Python code to implement the above.
* Include comments explaining the FMP API endpoints used.
* Ensure error handling for API failures (e.g., if FMP is down, don't crash, just log it).