# CLAUDE.md — Market Crash & Recovery Monitor

## Project Overview
This is an **always-on Market Sentinel** that monitors financial assets, technical indicators, and news sentiment to detect market crashes (Risk-Off) and recovery signals (Risk-On). It implements a "Core vs. Defense" investment strategy with automated alerting via **Telegram**.

**Deployed on DigitalOcean App Platform as a Worker** (background process, no HTTP port).

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│              market_monitor.py (Main)                │
│         APScheduler runs jobs on schedule            │
├──────────┬──────────┬──────────┬────────────────────┤
│ Technical│  Macro   │  State   │   Notifications    │
│ Analysis │ Analysis │ Manager  │    (Telegram)      │
│          │ (FMP API)│  (.json) │                    │
├──────────┴──────────┴──────────┴────────────────────┤
│              Data Providers                          │
│  Polygon.io (PRIMARY) ←→ yfinance (FALLBACK)        │
│  polygon_provider.py     built-in yfinance calls    │
└─────────────────────────────────────────────────────┘
```

### File Structure
```
CLAUDE.md                 # This file — agent instructions
market_monitor.py         # Entry point: scheduler + main loop
config.py                 # Constants, tickers, thresholds
technical_analysis.py     # SMA, RSI, trailing stops, crypto canary
macro_analysis.py         # FMP news sentiment, Fed rate checks
polygon_provider.py       # Polygon.io REST API wrapper (primary data)
notifications.py          # Telegram Bot alerts
state_manager.py          # JSON state persistence for alert dedup
market_monitor.md         # Original project specification
requirements.txt          # Python dependencies
.env.example              # Environment variable template
.gitignore                # Git ignore rules
.do/app.yaml              # DigitalOcean App Platform deployment spec
Dockerfile                # Container build for deployment
runtime.txt               # Python version pinning
README.md                 # Setup & deployment guide
```

---

## Data Provider Strategy

### Polygon.io (PRIMARY)
- **Server-side SMA**: `/v1/indicators/sma/{ticker}` — One API call replaces downloading 200 days of data
- **Server-side RSI**: `/v1/indicators/rsi/{ticker}` — Bonus overbought/oversold indicator
- **Stock Snapshots**: `/v2/snapshot/locale/us/markets/stocks/tickers` — All prices in 1 call
- **Market Status**: `/v1/marketstatus/now` — Know if market is open/closed
- **Crypto Prices**: `/v2/aggs/ticker/X:BTCUSD/prev` — Previous day close
- **Free Tier**: 5 calls/min, end-of-day data, no credit card needed

### yfinance (FALLBACK)
- Used when `POLYGON_API_KEY` is not set
- Used for trailing stop analysis (needs full OHLC DataFrame)
- Used for crypto canary (needs multi-day percentage calculations)
- Used as fallback when any Polygon call fails

---

## Assets Monitored
| Ticker   | Role               | Check Frequency |
|----------|--------------------|-----------------|
| SPY      | Benchmark (SMA+RSI)| 15 min (market hours) |
| IVV      | Core Portfolio      | 15 min (market hours) |
| BFGFX    | Growth Proxy        | 15 min (market hours) |
| JEPI     | Defensive Income    | 15 min (market hours) |
| JEPQ     | Defensive Income    | 15 min (market hours) |
| BTC-USD  | Crypto Canary       | 30 min (24/7) |
| ETH-USD  | Crypto Canary       | 30 min (24/7) |

---

## Signal Logic

### Technical Signals
- **SPY < 200-SMA** → CRITICAL: "Defensive Mode — Move to JEPI"
- **SPY > 200-SMA** (after being below) → GREEN: "Recovery — Consider IVV Re-entry"
- **SPY RSI > 70** → WARNING: "Overbought — Watch for pullback"
- **SPY RSI < 30** → GREEN: "Oversold — Potential buy opportunity"
- **IVV drops > 5% from 30-day high** → WARNING: "Trailing Stop Hit"
- **BTC drops > 10% in 24h** → WARNING: "Liquidity Drain / Crash Imminent"

### Macro Signals
- **Negative news spike** (keywords: crash, recession, plummet, liquidity crisis) → WARNING
- **Fed rate cut** (rate < previous rate) → INFO: "Fed Pivot — Buy Signal"

---

## Alert Levels
| Level    | Delivery                | Rate Limit           |
|----------|-------------------------|----------------------|
| CRITICAL | Immediate Telegram      | Max 1 per 4 hours    |
| WARNING  | Immediate Telegram      | Max 1 per 2 hours    |
| INFO     | Daily summary digest    | Once per day at 5 PM |

---

## Scheduling (APScheduler)
| Job                | Schedule                              | Timezone |
|--------------------|---------------------------------------|----------|
| Market health      | Every 15 min, Mon-Fri 9:30-16:00     | US/Eastern |
| Crypto canary      | Every 30 min, 24/7                    | UTC      |
| News sentiment     | Every 60 min, Mon-Fri 8:00-18:00     | US/Eastern |
| Daily summary      | Once at 17:00, Mon-Fri               | US/Eastern |

---

## Environment Variables
```
FMP_API_KEY=              # Financial Modeling Prep API key
POLYGON_API_KEY=          # Polygon.io API key (optional, enables server-side SMA/RSI)
TELEGRAM_BOT_TOKEN=       # Telegram bot token from @BotFather
TELEGRAM_CHAT_ID=         # Your Telegram chat ID
ALERT_COOLDOWN_HOURS=4    # Min hours between duplicate alerts (optional)
MONITOR_INTERVAL_MINUTES=15  # Override market check interval (optional)
```

---

## Local Development

```bash
# 1. Clone and install
git clone <repo-url> && cd market_monitor
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env
# Edit .env with your API keys

# 3. Run
python market_monitor.py
```

---

## DigitalOcean Deployment

### Option A: App Platform (Recommended)
1. Push code to GitHub
2. Go to DigitalOcean → Apps → Create App
3. Connect GitHub repo
4. It auto-detects `.do/app.yaml`
5. Add environment variables in the DO dashboard (encrypted)
6. Deploy — the Worker runs continuously

### Option B: Using `doctl` CLI
```bash
doctl apps create --spec .do/app.yaml
doctl apps update <app-id> --spec .do/app.yaml
```

### Cost
- **Worker (Basic)**: ~$5/month (1 vCPU, 0.5 GB RAM)
- Sufficient for this monitoring workload

---

## Coding Conventions
- **Python 3.12+**
- Use `logging` module (not print statements)
- All API calls wrapped in try/except with logging
- Type hints on all function signatures
- Constants in `config.py`, never hardcoded in logic
- State changes tracked via `state_manager.py` to prevent alert spam
- Modular design: each file has a single responsibility

---

## Telegram Bot Setup
1. Message `@BotFather` on Telegram → `/newbot`
2. Save the bot token as `TELEGRAM_BOT_TOKEN`
3. Message your bot, then visit:
   `https://api.telegram.org/bot{TOKEN}/getUpdates`
4. Find your `chat_id` in the response → save as `TELEGRAM_CHAT_ID`

---

## API Endpoints Used

### FMP (Financial Modeling Prep)
- **Stock News**: `GET /api/v3/stock_news?limit=50&apikey={KEY}`
- **Economic Calendar**: `GET /api/v3/economic_calendar?from={DATE}&to={DATE}&apikey={KEY}`

### Polygon.io
- **SMA (Server-side)**: `GET /v1/indicators/sma/{ticker}?window=200&timespan=day`
- **RSI (Server-side)**: `GET /v1/indicators/rsi/{ticker}?window=14&timespan=day`
- **Previous Close**: `GET /v2/aggs/ticker/{ticker}/prev`
- **Stock Snapshots**: `GET /v2/snapshot/locale/us/markets/stocks/tickers?tickers=SPY,IVV,...`
- **Market Status**: `GET /v1/marketstatus/now`
- **Aggregates**: `GET /v2/aggs/ticker/{ticker}/range/{mult}/{timespan}/{from}/{to}`

---

## Error Handling Strategy
- API failures are logged and skipped (never crash the worker)
- Polygon failures fall back to yfinance automatically
- yfinance timeouts: retry once, then skip with WARNING log
- FMP failures: use cached last-known data from state file
- Telegram failures: log error, continue execution
- Scheduler keeps running even if individual jobs fail

---

## AI Agent Orchestrator

The Market Monitor includes an AI Agent Orchestrator that provides intelligent market analysis and decision-making capabilities.

### Agent Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      AgentOrchestrator                               │
│              (Central Intelligence Layer)                            │
├──────────────┬──────────────┬──────────────┬───────────────────────┤
│  ToolRegistry│  MCPCoordinator│  AgentContext│  Decision Engine    │
│  (20+ tools) │  (5 servers)   │  (State/Mem) │  (Query Router)     │
├──────────────┴──────────────┴──────────────┴───────────────────────┤
│                        MCP Server Integration                        │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐ ┌───────────┐ │
│  │ GitHub  │ │ Memory  │ │  Fetch  │ │ Sequential  │ │Filesystem │ │
│  │  MCP    │ │   MCP   │ │   MCP   │ │  Thinking   │ │    MCP    │ │
│  └─────────┘ └─────────┘ └─────────┘ └─────────────┘ └───────────┘ │
└─────────────────────────────────────────────────────────────────────┘
```

### Agent Files

| File | Purpose |
|------|---------|
| `agent_orchestrator.py` | Main agent class, tool execution, query handling |
| `agent_tools.py` | Custom tool definitions, portfolio analytics |
| `agent_config.py` | Agent settings, permissions, presets |
| `mcp_integration.py` | MCP server interfaces and coordination |
| `mcp_config.json` | MCP server configuration |

### Available Tools

#### Market Data Tools
- `get_current_price` - Get price for any ticker
- `fetch_all_prices` - Get prices for all monitored tickers
- `get_market_status` - Check if market is open (Polygon)

#### Technical Analysis Tools
- `analyze_sma` - SPY 200-day SMA regime detection
- `analyze_rsi` - RSI overbought/oversold detection
- `analyze_trailing_stop` - IVV trailing stop check
- `analyze_crypto_canary` - BTC/ETH crash detection
- `run_full_technical_analysis` - Complete technical suite

#### Macro Analysis Tools
- `analyze_news_sentiment` - FMP news sentiment scan
- `check_fed_rate` - Fed rate decision tracking
- `run_macro_analysis` - Complete macro analysis

#### Advanced Analytics (agent_tools.py)
- `calculate_portfolio_exposure` - Risk exposure breakdown
- `analyze_correlation` - Cross-asset correlation matrix
- `calculate_volatility_metrics` - Vol analysis with drawdown
- `detect_market_regime` - BULL/BEAR/RANGING detection
- `get_sector_performance` - Sector rotation analysis
- `calculate_risk_metrics` - Sharpe, Beta, Alpha, VaR

### Agent Operating Modes

| Mode | Description |
|------|-------------|
| `AUTONOMOUS` | Agent executes decisions independently |
| `SUPERVISED` | Agent proposes actions, waits for approval |
| `INTERACTIVE` | Agent responds to queries only |
| `MONITORING` | Agent monitors and reports only |
| `BACKTESTING` | Agent runs in simulation mode |

### Running the Agent

```bash
# Interactive mode (query-based)
python agent_orchestrator.py --interactive

# Single health check
python agent_orchestrator.py

# With specific mode
AGENT_MODE=supervised python agent_orchestrator.py
```

### Example Agent Queries

```python
# In interactive mode
Agent> What's the current price of SPY?
Agent> Is the market overbought?
Agent> Run a full health check
Agent> What's the current market regime?
Agent> Show me sector performance
Agent> What tools are available?
```

---

## MCP Server Integration

The agent integrates with multiple MCP (Model Context Protocol) servers for extended capabilities.

### Configured MCP Servers

| Server | Purpose | Key Tools |
|--------|---------|-----------|
| **GitHub** | Issue tracking, code search | `github_create_issue`, `github_search_code` |
| **Memory** | Pattern storage, knowledge graph | `create_entities`, `add_observations`, `search_nodes` |
| **Fetch** | Web data fetching | `fetch_webpage` |
| **Sequential Thinking** | Complex analysis | `sequentialthinking` |
| **Filesystem** | Local storage | `read_file`, `write_file` |

### MCP Use Cases

#### GitHub MCP
- Track significant market events as issues
- Search for trading strategies in repositories
- Document strategy changes in the repo

#### Memory MCP
- Store market signals for pattern detection
- Build knowledge graph of market relationships
- Track pattern occurrences over time
- Remember user preferences and strategies

#### Fetch MCP
- Real-time news from MarketWatch, Reuters, Bloomberg
- Fed announcements and economic calendar
- VIX and Fear & Greed Index data
- Earnings calendars

#### Sequential Thinking MCP
- Multi-step crash assessment
- Recovery signal evaluation
- Portfolio rebalancing decisions
- Conflicting signal resolution

### MCP Configuration

Configure MCP servers in `mcp_config.json`:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"
      }
    },
    "memory": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-memory"]
    }
  }
}
```

---

## Agent Configuration

### Environment Variables (Additional)

```bash
# Agent Settings
AGENT_MODE=autonomous          # autonomous, supervised, interactive, monitoring
ALERT_MODE=immediate           # immediate, batched, digest, silent

# Thresholds (Override defaults)
TRAILING_STOP_PERCENT=5.0
BTC_CRASH_THRESHOLD=-10.0

# MCP Settings
MCP_GITHUB_ENABLED=true
MCP_MEMORY_ENABLED=true
MCP_FETCH_ENABLED=true
GITHUB_REPO=owner/repo
GITHUB_TOKEN=ghp_xxxxx

# LLM Integration (Optional)
LLM_PROVIDER=none              # openai, anthropic, azure, none
LLM_MODEL=gpt-4
LLM_API_KEY_VAR=OPENAI_API_KEY
```

### Configuration Presets

```python
from agent_config import (
    get_default_config,
    get_conservative_config,
    get_aggressive_config,
    get_testing_config,
)

# Conservative: tighter stops, supervised mode
config = get_conservative_config()

# Aggressive: looser thresholds, autonomous
config = get_aggressive_config()

# Testing: no external calls
config = get_testing_config()
```

---

## Extended File Structure

```
CLAUDE.md                 # This file — agent instructions
market_monitor.py         # Entry point: scheduler + main loop
config.py                 # Constants, tickers, thresholds
technical_analysis.py     # SMA, RSI, trailing stops, crypto canary
macro_analysis.py         # FMP news sentiment, Fed rate checks
polygon_provider.py       # Polygon.io REST API wrapper
notifications.py          # Telegram Bot alerts
state_manager.py          # JSON state persistence

# Agent System (NEW)
agent_orchestrator.py     # AI Agent main class + tool execution
agent_tools.py            # Custom tools + portfolio analytics
agent_config.py           # Agent settings, modes, presets
mcp_integration.py        # MCP server interfaces
mcp_config.json           # MCP server configuration

# Support Files
market_monitor.md         # Original project specification
requirements.txt          # Python dependencies
.env.example              # Environment variable template
.gitignore                # Git ignore rules
.do/app.yaml              # DigitalOcean deployment spec
Dockerfile                # Container build
runtime.txt               # Python version pinning
README.md                 # Setup & deployment guide
```

---

## Agent Development Guidelines

### Adding New Tools

1. Define tool in `ToolRegistry._register_builtin_tools()`:
```python
self.register(ToolDefinition(
    name="my_new_tool",
    description="What this tool does",
    category=ToolCategory.MARKET_DATA,
    parameters={"param1": "str - Description"},
    handler=self._tool_my_new_tool,
    requires_api_key="OPTIONAL_API_KEY",
))
```

2. Implement handler:
```python
async def _tool_my_new_tool(self, param1: str) -> ToolResult:
    try:
        # Tool logic here
        return ToolResult(success=True, data={"result": "value"})
    except Exception as e:
        return ToolResult(success=False, error=str(e))
```

### Adding MCP Server Integration

1. Add server to `mcp_config.json`
2. Create interface class in `mcp_integration.py`
3. Add tool mappings in `MCPCoordinator`

### Best Practices

- All tools should be async for concurrent execution
- Use `ToolResult` for consistent return types
- Log all tool executions for debugging
- Rate limit external API calls
- Validate inputs before execution
- Handle errors gracefully, never crash the agent
