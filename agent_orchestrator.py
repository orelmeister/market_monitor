#!/usr/bin/env python3
"""
agent_orchestrator.py — AI Agent Orchestrator for Market Monitor

This module implements an intelligent AI agent that orchestrates all market
monitoring activities. It provides:

  - Multi-tool orchestration with automatic routing
  - MCP server integration (GitHub, Memory, Web Fetching)
  - Natural language interface for market queries
  - Autonomous decision-making for market analysis
  - Persistent memory for tracking market patterns
  - Integration with external data sources

The orchestrator acts as the central intelligence layer that coordinates
between technical analysis, macro analysis, and external data sources.
"""

import asyncio
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Optional, Union
from zoneinfo import ZoneInfo

from config import (
    BENCHMARK,
    ALL_TICKERS,
    CORE_PORTFOLIO,
    DEFENSIVE_INCOME,
    CRYPTO_CANARIES,
    POLYGON_API_KEY,
    FMP_API_KEY,
    TELEGRAM_BOT_TOKEN,
)
from technical_analysis import (
    analyze_sma,
    analyze_trailing_stop,
    analyze_crypto_canary,
    fetch_all_prices,
    get_current_price,
    MarketSignal,
)
from macro_analysis import check_macro_environment, fetch_news_sentiment, fetch_fed_rate
from notifications import send_alert, send_daily_summary
from state_manager import load_state, save_state, update_state, get_state_summary

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# DATA MODELS
# ═══════════════════════════════════════════════════════════════════════════════

class ToolCategory(Enum):
    """Categories for organizing tools."""
    MARKET_DATA = "market_data"
    TECHNICAL_ANALYSIS = "technical_analysis"
    MACRO_ANALYSIS = "macro_analysis"
    NOTIFICATIONS = "notifications"
    STATE_MANAGEMENT = "state_management"
    EXTERNAL_DATA = "external_data"
    MEMORY = "memory"


class AgentMode(Enum):
    """Operating modes for the agent."""
    AUTONOMOUS = "autonomous"      # Agent makes decisions independently
    SUPERVISED = "supervised"      # Agent proposes actions, waits for approval
    INTERACTIVE = "interactive"    # Agent responds to direct queries


@dataclass
class ToolDefinition:
    """Definition of a tool available to the agent."""
    name: str
    description: str
    category: ToolCategory
    parameters: dict[str, Any]
    handler: Callable
    requires_api_key: Optional[str] = None
    rate_limit_per_minute: Optional[int] = None


@dataclass
class ToolResult:
    """Result from executing a tool."""
    success: bool
    data: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0


@dataclass
class AgentContext:
    """Context for agent execution."""
    mode: AgentMode = AgentMode.AUTONOMOUS
    current_state: dict = field(default_factory=dict)
    execution_history: list = field(default_factory=list)
    memory: dict = field(default_factory=dict)
    active_signals: list = field(default_factory=list)


@dataclass
class AgentDecision:
    """A decision made by the agent."""
    action: str
    reasoning: str
    tools_to_execute: list[str]
    parameters: dict[str, Any]
    priority: int = 1  # 1=highest, 5=lowest
    timestamp: datetime = field(default_factory=lambda: datetime.now(ZoneInfo("US/Eastern")))


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL REGISTRY
# ═══════════════════════════════════════════════════════════════════════════════

class ToolRegistry:
    """Registry of all available tools for the agent."""
    
    def __init__(self):
        self._tools: dict[str, ToolDefinition] = {}
        self._register_builtin_tools()
    
    def register(self, tool: ToolDefinition) -> None:
        """Register a new tool."""
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name} ({tool.category.value})")
    
    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool by name."""
        return self._tools.get(name)
    
    def list_tools(self, category: Optional[ToolCategory] = None) -> list[ToolDefinition]:
        """List all tools, optionally filtered by category."""
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools
    
    def get_tool_descriptions(self) -> str:
        """Get formatted descriptions of all tools for LLM context."""
        lines = ["Available Tools:"]
        for cat in ToolCategory:
            cat_tools = self.list_tools(cat)
            if cat_tools:
                lines.append(f"\n## {cat.value.replace('_', ' ').title()}")
                for tool in cat_tools:
                    params_str = ", ".join(tool.parameters.keys()) if tool.parameters else "none"
                    lines.append(f"  - {tool.name}: {tool.description} (params: {params_str})")
        return "\n".join(lines)
    
    def _register_builtin_tools(self) -> None:
        """Register all built-in market monitoring tools."""
        
        # ─── Market Data Tools ───────────────────────────────────────────
        self.register(ToolDefinition(
            name="get_current_price",
            description="Get the current price for a ticker symbol",
            category=ToolCategory.MARKET_DATA,
            parameters={"ticker": "str - The ticker symbol (e.g., SPY, BTC-USD)"},
            handler=self._tool_get_current_price,
        ))
        
        self.register(ToolDefinition(
            name="fetch_all_prices",
            description="Fetch current prices for all monitored tickers",
            category=ToolCategory.MARKET_DATA,
            parameters={"tickers": "list[str] - Optional list of tickers, defaults to all monitored"},
            handler=self._tool_fetch_all_prices,
        ))
        
        self.register(ToolDefinition(
            name="get_market_status",
            description="Check if the US stock market is currently open",
            category=ToolCategory.MARKET_DATA,
            parameters={},
            handler=self._tool_get_market_status,
            requires_api_key="POLYGON_API_KEY",
        ))
        
        # ─── Technical Analysis Tools ────────────────────────────────────
        self.register(ToolDefinition(
            name="analyze_sma",
            description="Analyze SPY against its 200-day SMA to detect bull/bear regime",
            category=ToolCategory.TECHNICAL_ANALYSIS,
            parameters={},
            handler=self._tool_analyze_sma,
        ))
        
        self.register(ToolDefinition(
            name="analyze_rsi",
            description="Analyze RSI for a ticker to detect overbought/oversold conditions",
            category=ToolCategory.TECHNICAL_ANALYSIS,
            parameters={"ticker": "str - The ticker symbol (default: SPY)"},
            handler=self._tool_analyze_rsi,
            requires_api_key="POLYGON_API_KEY",
        ))
        
        self.register(ToolDefinition(
            name="analyze_trailing_stop",
            description="Check if IVV has triggered a trailing stop (dropped >5% from 30-day high)",
            category=ToolCategory.TECHNICAL_ANALYSIS,
            parameters={},
            handler=self._tool_analyze_trailing_stop,
        ))
        
        self.register(ToolDefinition(
            name="analyze_crypto_canary",
            description="Analyze BTC/ETH for crash signals (>10% drop in 24h)",
            category=ToolCategory.TECHNICAL_ANALYSIS,
            parameters={},
            handler=self._tool_analyze_crypto_canary,
        ))
        
        self.register(ToolDefinition(
            name="run_full_technical_analysis",
            description="Run complete technical analysis suite (SMA, trailing stop, crypto canary)",
            category=ToolCategory.TECHNICAL_ANALYSIS,
            parameters={},
            handler=self._tool_run_full_technical_analysis,
        ))
        
        # ─── Macro Analysis Tools ────────────────────────────────────────
        self.register(ToolDefinition(
            name="analyze_news_sentiment",
            description="Analyze market news for negative sentiment signals",
            category=ToolCategory.MACRO_ANALYSIS,
            parameters={},
            handler=self._tool_analyze_news_sentiment,
            requires_api_key="FMP_API_KEY",
        ))
        
        self.register(ToolDefinition(
            name="check_fed_rate",
            description="Check Federal Reserve interest rate decisions for pivot signals",
            category=ToolCategory.MACRO_ANALYSIS,
            parameters={},
            handler=self._tool_check_fed_rate,
            requires_api_key="FMP_API_KEY",
        ))
        
        self.register(ToolDefinition(
            name="run_macro_analysis",
            description="Run complete macro environment analysis (news + Fed rate)",
            category=ToolCategory.MACRO_ANALYSIS,
            parameters={},
            handler=self._tool_run_macro_analysis,
            requires_api_key="FMP_API_KEY",
        ))
        
        # ─── Notification Tools ──────────────────────────────────────────
        self.register(ToolDefinition(
            name="send_alert",
            description="Send an alert via Telegram",
            category=ToolCategory.NOTIFICATIONS,
            parameters={
                "subject": "str - Alert subject",
                "body": "str - Alert message body",
                "level": "str - Alert level (CRITICAL, WARNING, INFO, GREEN)",
            },
            handler=self._tool_send_alert,
            requires_api_key="TELEGRAM_BOT_TOKEN",
        ))
        
        self.register(ToolDefinition(
            name="send_daily_summary",
            description="Send the daily market summary via Telegram",
            category=ToolCategory.NOTIFICATIONS,
            parameters={"prices": "dict - Current prices", "state": "dict - Current state"},
            handler=self._tool_send_daily_summary,
            requires_api_key="TELEGRAM_BOT_TOKEN",
        ))
        
        # ─── State Management Tools ──────────────────────────────────────
        self.register(ToolDefinition(
            name="get_current_state",
            description="Get the current market monitor state",
            category=ToolCategory.STATE_MANAGEMENT,
            parameters={},
            handler=self._tool_get_current_state,
        ))
        
        self.register(ToolDefinition(
            name="get_state_summary",
            description="Get a human-readable summary of the current state",
            category=ToolCategory.STATE_MANAGEMENT,
            parameters={},
            handler=self._tool_get_state_summary,
        ))
        
        self.register(ToolDefinition(
            name="update_state",
            description="Update the market monitor state with new data",
            category=ToolCategory.STATE_MANAGEMENT,
            parameters={"updates": "dict - Key-value pairs to update"},
            handler=self._tool_update_state,
        ))
        
        # ─── External Data Tools ─────────────────────────────────────────
        self.register(ToolDefinition(
            name="fetch_external_news",
            description="Fetch market news from external sources",
            category=ToolCategory.EXTERNAL_DATA,
            parameters={"query": "str - Search query for news", "limit": "int - Max results"},
            handler=self._tool_fetch_external_news,
        ))
        
        self.register(ToolDefinition(
            name="get_economic_calendar",
            description="Get upcoming economic events that may impact markets",
            category=ToolCategory.EXTERNAL_DATA,
            parameters={"days_ahead": "int - Number of days to look ahead"},
            handler=self._tool_get_economic_calendar,
            requires_api_key="FMP_API_KEY",
        ))
        
        # ─── Memory Tools ────────────────────────────────────────────────
        self.register(ToolDefinition(
            name="store_memory",
            description="Store information in agent memory for future reference",
            category=ToolCategory.MEMORY,
            parameters={"key": "str - Memory key", "value": "any - Value to store"},
            handler=self._tool_store_memory,
        ))
        
        self.register(ToolDefinition(
            name="recall_memory",
            description="Recall information from agent memory",
            category=ToolCategory.MEMORY,
            parameters={"key": "str - Memory key to recall"},
            handler=self._tool_recall_memory,
        ))
        
        self.register(ToolDefinition(
            name="list_memories",
            description="List all stored memory keys",
            category=ToolCategory.MEMORY,
            parameters={},
            handler=self._tool_list_memories,
        ))
    
    # ─── Tool Handler Implementations ────────────────────────────────────────
    
    async def _tool_get_current_price(self, ticker: str) -> ToolResult:
        """Get current price for a ticker."""
        try:
            price = get_current_price(ticker)
            if price is None:
                return ToolResult(success=False, data=None, error=f"Could not fetch price for {ticker}")
            return ToolResult(success=True, data={"ticker": ticker, "price": price})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_fetch_all_prices(self, tickers: Optional[list[str]] = None) -> ToolResult:
        """Fetch all prices."""
        try:
            tickers = tickers or ALL_TICKERS
            prices = fetch_all_prices(tickers)
            return ToolResult(success=True, data=prices)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_get_market_status(self) -> ToolResult:
        """Check market status."""
        try:
            from polygon_provider import get_market_status
            status = get_market_status()
            if status is None:
                return ToolResult(success=False, data=None, error="Could not fetch market status")
            return ToolResult(success=True, data=status)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_analyze_sma(self) -> ToolResult:
        """Analyze SMA."""
        try:
            state = load_state()
            signal, state_update = analyze_sma(state)
            if state_update:
                state = update_state(state, state_update)
                save_state(state)
            return ToolResult(
                success=True,
                data={
                    "signal": signal.__dict__ if signal else None,
                    "state_update": state_update,
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_analyze_rsi(self, ticker: str = "SPY") -> ToolResult:
        """Analyze RSI."""
        try:
            from polygon_provider import get_rsi
            rsi = get_rsi(ticker)
            if rsi is None:
                return ToolResult(success=False, data=None, error=f"Could not fetch RSI for {ticker}")
            
            status = "neutral"
            if rsi > 70:
                status = "overbought"
            elif rsi < 30:
                status = "oversold"
            
            return ToolResult(success=True, data={
                "ticker": ticker,
                "rsi": rsi,
                "status": status,
            })
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_analyze_trailing_stop(self) -> ToolResult:
        """Analyze trailing stop."""
        try:
            state = load_state()
            signal, state_update = analyze_trailing_stop(state)
            if state_update:
                state = update_state(state, state_update)
                save_state(state)
            return ToolResult(
                success=True,
                data={
                    "signal": signal.__dict__ if signal else None,
                    "state_update": state_update,
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_analyze_crypto_canary(self) -> ToolResult:
        """Analyze crypto canary."""
        try:
            state = load_state()
            signal, state_update = analyze_crypto_canary(state)
            if state_update:
                state = update_state(state, state_update)
                save_state(state)
            return ToolResult(
                success=True,
                data={
                    "signal": signal.__dict__ if signal else None,
                    "state_update": state_update,
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_run_full_technical_analysis(self) -> ToolResult:
        """Run full technical analysis."""
        try:
            results = {
                "sma": await self._tool_analyze_sma(),
                "trailing_stop": await self._tool_analyze_trailing_stop(),
                "crypto_canary": await self._tool_analyze_crypto_canary(),
            }
            
            signals = []
            for name, result in results.items():
                if result.success and result.data and result.data.get("signal"):
                    signals.append(result.data["signal"])
            
            return ToolResult(success=True, data={
                "results": {k: v.data for k, v in results.items()},
                "signals": signals,
                "signal_count": len(signals),
            })
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_analyze_news_sentiment(self) -> ToolResult:
        """Analyze news sentiment."""
        try:
            signal, state_update = fetch_news_sentiment()
            return ToolResult(
                success=True,
                data={
                    "signal": signal.__dict__ if signal else None,
                    "state_update": state_update,
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_check_fed_rate(self) -> ToolResult:
        """Check Fed rate."""
        try:
            state = load_state()
            signal, state_update = fetch_fed_rate(state)
            if state_update:
                state = update_state(state, state_update)
                save_state(state)
            return ToolResult(
                success=True,
                data={
                    "signal": signal.__dict__ if signal else None,
                    "state_update": state_update,
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_run_macro_analysis(self) -> ToolResult:
        """Run macro analysis."""
        try:
            state = load_state()
            signals, state_update = check_macro_environment(state)
            if state_update:
                state = update_state(state, state_update)
                save_state(state)
            return ToolResult(
                success=True,
                data={
                    "signals": [s.__dict__ for s in signals] if signals else [],
                    "state_update": state_update,
                }
            )
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_send_alert(self, subject: str, body: str, level: str = "INFO") -> ToolResult:
        """Send alert."""
        try:
            result = send_alert(subject=subject, body=body, level=level)
            return ToolResult(success=result.get("telegram", False), data=result)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_send_daily_summary(self, prices: dict, state: dict) -> ToolResult:
        """Send daily summary."""
        try:
            result = send_daily_summary(prices=prices, state=state, info_signals=[])
            return ToolResult(success=result, data={"sent": result})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_get_current_state(self) -> ToolResult:
        """Get current state."""
        try:
            state = load_state()
            return ToolResult(success=True, data=state)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_get_state_summary(self) -> ToolResult:
        """Get state summary."""
        try:
            state = load_state()
            summary = get_state_summary(state)
            return ToolResult(success=True, data={"summary": summary, "state": state})
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_update_state(self, updates: dict) -> ToolResult:
        """Update state."""
        try:
            state = load_state()
            state = update_state(state, updates)
            save_state(state)
            return ToolResult(success=True, data=state)
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    async def _tool_fetch_external_news(self, query: str = "market", limit: int = 10) -> ToolResult:
        """Fetch external news - placeholder for MCP integration."""
        # This would integrate with fetch_webpage MCP tool
        return ToolResult(
            success=True,
            data={
                "message": "External news fetching requires MCP server integration",
                "query": query,
                "limit": limit,
            }
        )
    
    async def _tool_get_economic_calendar(self, days_ahead: int = 7) -> ToolResult:
        """Get economic calendar."""
        try:
            from datetime import timedelta
            import requests
            
            if not FMP_API_KEY:
                return ToolResult(success=False, data=None, error="FMP_API_KEY not configured")
            
            today = datetime.utcnow()
            end_date = today + timedelta(days=days_ahead)
            
            url = f"https://financialmodelingprep.com/api/v3/economic_calendar"
            params = {
                "from": today.strftime("%Y-%m-%d"),
                "to": end_date.strftime("%Y-%m-%d"),
                "apikey": FMP_API_KEY,
            }
            
            response = requests.get(url, params=params, timeout=15)
            response.raise_for_status()
            events = response.json()
            
            return ToolResult(success=True, data={
                "events": events[:20],  # Limit to 20 events
                "total_count": len(events),
            })
        except Exception as e:
            return ToolResult(success=False, data=None, error=str(e))
    
    # Memory tool implementations using in-memory storage
    _memory_store: dict = {}
    
    async def _tool_store_memory(self, key: str, value: Any) -> ToolResult:
        """Store in memory."""
        self._memory_store[key] = {
            "value": value,
            "stored_at": datetime.now(ZoneInfo("US/Eastern")).isoformat(),
        }
        return ToolResult(success=True, data={"key": key, "stored": True})
    
    async def _tool_recall_memory(self, key: str) -> ToolResult:
        """Recall from memory."""
        if key in self._memory_store:
            return ToolResult(success=True, data=self._memory_store[key])
        return ToolResult(success=False, data=None, error=f"Key '{key}' not found in memory")
    
    async def _tool_list_memories(self) -> ToolResult:
        """List all memories."""
        return ToolResult(success=True, data={
            "keys": list(self._memory_store.keys()),
            "count": len(self._memory_store),
        })


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT ORCHESTRATOR
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOrchestrator:
    """
    Main AI Agent Orchestrator for Market Monitor.
    
    This class coordinates all market monitoring activities through:
    - Tool execution and management
    - Decision making based on market conditions
    - Memory management for pattern recognition
    - Integration with external MCP servers
    """
    
    def __init__(self, mode: AgentMode = AgentMode.AUTONOMOUS):
        self.mode = mode
        self.registry = ToolRegistry()
        self.context = AgentContext(mode=mode)
        self._running = False
        logger.info(f"Agent Orchestrator initialized in {mode.value} mode")
    
    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        """Execute a single tool by name."""
        tool = self.registry.get(tool_name)
        if not tool:
            return ToolResult(success=False, data=None, error=f"Tool '{tool_name}' not found")
        
        # Check API key requirements
        if tool.requires_api_key:
            api_key = globals().get(tool.requires_api_key) or locals().get(tool.requires_api_key)
            if not api_key:
                return ToolResult(
                    success=False,
                    data=None,
                    error=f"Tool '{tool_name}' requires {tool.requires_api_key} to be configured"
                )
        
        # Execute the tool
        start_time = datetime.now()
        try:
            result = await tool.handler(**kwargs)
            result.execution_time_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Log execution
            self.context.execution_history.append({
                "tool": tool_name,
                "params": kwargs,
                "success": result.success,
                "timestamp": start_time.isoformat(),
                "execution_time_ms": result.execution_time_ms,
            })
            
            return result
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name} - {e}")
            return ToolResult(success=False, data=None, error=str(e))
    
    async def run_market_health_check(self) -> dict[str, Any]:
        """
        Run a comprehensive market health check.
        This is the primary autonomous function.
        """
        logger.info("═══ Running Agent Market Health Check ═══")
        
        results = {
            "timestamp": datetime.now(ZoneInfo("US/Eastern")).isoformat(),
            "analysis": {},
            "signals": [],
            "actions_taken": [],
        }
        
        # 1. Technical Analysis
        tech_result = await self.execute_tool("run_full_technical_analysis")
        results["analysis"]["technical"] = tech_result.data
        if tech_result.success and tech_result.data:
            results["signals"].extend(tech_result.data.get("signals", []))
        
        # 2. Macro Analysis
        macro_result = await self.execute_tool("run_macro_analysis")
        results["analysis"]["macro"] = macro_result.data
        if macro_result.success and macro_result.data:
            results["signals"].extend(macro_result.data.get("signals", []))
        
        # 3. Process signals and take actions
        for signal in results["signals"]:
            if signal.get("level") in ["CRITICAL", "WARNING"]:
                alert_result = await self.execute_tool(
                    "send_alert",
                    subject=signal.get("name", "Market Signal"),
                    body=signal.get("message", "No details"),
                    level=signal.get("level", "INFO"),
                )
                results["actions_taken"].append({
                    "action": "send_alert",
                    "signal": signal.get("name"),
                    "success": alert_result.success,
                })
        
        # 4. Update context
        self.context.active_signals = results["signals"]
        self.context.current_state = (await self.execute_tool("get_current_state")).data or {}
        
        return results
    
    async def handle_query(self, query: str) -> dict[str, Any]:
        """
        Handle a natural language query from the user.
        Routes to appropriate tools based on query content.
        """
        query_lower = query.lower()
        
        # Simple keyword-based routing (can be enhanced with LLM)
        if any(word in query_lower for word in ["price", "quote", "cost"]):
            # Extract ticker if mentioned
            for ticker in ALL_TICKERS:
                if ticker.lower() in query_lower:
                    result = await self.execute_tool("get_current_price", ticker=ticker)
                    return {"query": query, "result": result.data, "tool_used": "get_current_price"}
            # Default to all prices
            result = await self.execute_tool("fetch_all_prices")
            return {"query": query, "result": result.data, "tool_used": "fetch_all_prices"}
        
        elif any(word in query_lower for word in ["sma", "moving average", "trend"]):
            result = await self.execute_tool("analyze_sma")
            return {"query": query, "result": result.data, "tool_used": "analyze_sma"}
        
        elif any(word in query_lower for word in ["rsi", "overbought", "oversold"]):
            result = await self.execute_tool("analyze_rsi")
            return {"query": query, "result": result.data, "tool_used": "analyze_rsi"}
        
        elif any(word in query_lower for word in ["crypto", "bitcoin", "btc", "eth"]):
            result = await self.execute_tool("analyze_crypto_canary")
            return {"query": query, "result": result.data, "tool_used": "analyze_crypto_canary"}
        
        elif any(word in query_lower for word in ["news", "sentiment"]):
            result = await self.execute_tool("analyze_news_sentiment")
            return {"query": query, "result": result.data, "tool_used": "analyze_news_sentiment"}
        
        elif any(word in query_lower for word in ["fed", "rate", "fomc"]):
            result = await self.execute_tool("check_fed_rate")
            return {"query": query, "result": result.data, "tool_used": "check_fed_rate"}
        
        elif any(word in query_lower for word in ["state", "status", "summary"]):
            result = await self.execute_tool("get_state_summary")
            return {"query": query, "result": result.data, "tool_used": "get_state_summary"}
        
        elif any(word in query_lower for word in ["calendar", "events", "upcoming"]):
            result = await self.execute_tool("get_economic_calendar")
            return {"query": query, "result": result.data, "tool_used": "get_economic_calendar"}
        
        elif any(word in query_lower for word in ["health", "check", "full", "complete"]):
            result = await self.run_market_health_check()
            return {"query": query, "result": result, "tool_used": "run_market_health_check"}
        
        elif any(word in query_lower for word in ["tools", "help", "available"]):
            return {
                "query": query,
                "result": self.registry.get_tool_descriptions(),
                "tool_used": "list_tools",
            }
        
        else:
            # Default: run state summary
            result = await self.execute_tool("get_state_summary")
            return {
                "query": query,
                "result": result.data,
                "tool_used": "get_state_summary",
                "note": "Query not matched to specific tool, showing current state",
            }
    
    def get_system_prompt(self) -> str:
        """
        Get the system prompt for LLM integration.
        This can be used with OpenAI, Anthropic, or other LLM providers.
        """
        tool_descriptions = self.registry.get_tool_descriptions()
        
        return f"""You are an AI Market Monitor Agent specialized in financial market analysis.
Your role is to monitor markets, detect crashes/recoveries, and alert users to important signals.

## Your Capabilities
{tool_descriptions}

## Investment Strategy Context
You are implementing a "Core vs. Defense" investment strategy:
- **Core Portfolio**: IVV, BFGFX (growth-oriented)
- **Defensive Portfolio**: JEPI, JEPQ (income-focused)
- **Benchmark**: SPY (S&P 500)
- **Crypto Canaries**: BTC-USD, ETH-USD (early warning indicators)

## Signal Logic
- SPY < 200-SMA → CRITICAL: Move to defensive (JEPI/JEPQ)
- SPY > 200-SMA (recovery) → GREEN: Consider returning to core (IVV)
- RSI > 70 → WARNING: Overbought, potential pullback
- RSI < 30 → GREEN: Oversold, potential buy opportunity
- IVV drops >5% from 30-day high → WARNING: Trailing stop hit
- BTC drops >10% in 24h → WARNING: Liquidity crisis signal

## Guidelines
1. Be concise and actionable in your responses
2. Always cite specific data when making recommendations
3. Prioritize risk warnings over opportunity alerts
4. Consider market hours when interpreting data (9:30-16:00 ET)
5. Cross-reference technical and macro signals for stronger conviction

Current Time: {datetime.now(ZoneInfo("US/Eastern")).strftime("%Y-%m-%d %H:%M %Z")}
"""
    
    def get_available_mcp_servers(self) -> list[dict]:
        """
        List of recommended MCP servers for expanded monitoring.
        These can be configured in the MCP settings.
        """
        return [
            {
                "name": "github",
                "description": "Access GitHub for tracking market-related repositories, issues, and code",
                "tools": [
                    "github_search_code",
                    "github_search_issues",
                    "github_get_file_contents",
                    "github_create_issue",
                ],
                "use_cases": [
                    "Track market monitoring tool updates",
                    "File bugs and feature requests",
                    "Collaborate on strategy improvements",
                ],
            },
            {
                "name": "memory",
                "description": "Persistent memory for tracking market patterns over time",
                "tools": [
                    "create_entities",
                    "add_observations",
                    "search_nodes",
                    "read_graph",
                ],
                "use_cases": [
                    "Remember significant market events",
                    "Track pattern occurrences",
                    "Build knowledge graph of market relationships",
                ],
            },
            {
                "name": "fetch",
                "description": "Fetch data from external web sources",
                "tools": [
                    "fetch_webpage",
                ],
                "use_cases": [
                    "Get real-time news from financial sites",
                    "Fetch Fed announcements",
                    "Monitor MarketWatch, Bloomberg, Reuters",
                ],
            },
            {
                "name": "sequential_thinking",
                "description": "Complex multi-step reasoning for market analysis",
                "tools": [
                    "sequentialthinking",
                ],
                "use_cases": [
                    "Analyze complex market scenarios",
                    "Build investment theses",
                    "Reason through multi-signal situations",
                ],
            },
        ]


# ═══════════════════════════════════════════════════════════════════════════════
# CLI INTERFACE
# ═══════════════════════════════════════════════════════════════════════════════

async def interactive_mode():
    """Run the agent in interactive mode."""
    agent = AgentOrchestrator(mode=AgentMode.INTERACTIVE)
    
    print("\n" + "="*60)
    print("Market Monitor Agent - Interactive Mode")
    print("="*60)
    print("\nType 'help' for available commands, 'quit' to exit.\n")
    
    while True:
        try:
            query = input("Agent> ").strip()
            
            if not query:
                continue
            
            if query.lower() in ["quit", "exit", "q"]:
                print("Goodbye!")
                break
            
            if query.lower() == "help":
                print(agent.registry.get_tool_descriptions())
                continue
            
            result = await agent.handle_query(query)
            print(f"\n{json.dumps(result, indent=2, default=str)}\n")
            
        except KeyboardInterrupt:
            print("\nGoodbye!")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main entry point."""
    import sys
    
    if "--interactive" in sys.argv or "-i" in sys.argv:
        asyncio.run(interactive_mode())
    else:
        # Default: run a single health check
        async def single_check():
            agent = AgentOrchestrator()
            result = await agent.run_market_health_check()
            print(json.dumps(result, indent=2, default=str))
        
        asyncio.run(single_check())


if __name__ == "__main__":
    main()
