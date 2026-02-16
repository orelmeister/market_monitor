"""
agent_config.py — Configuration for Market Monitor AI Agent

This module centralizes all agent-related configuration including:
  - Agent operating modes and behavior settings
  - Tool availability and permissions
  - MCP server configuration
  - LLM integration settings
  - Monitoring and alerting thresholds
"""

import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional
from dotenv import load_dotenv

load_dotenv()


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT MODES
# ═══════════════════════════════════════════════════════════════════════════════

class AgentOperatingMode(Enum):
    """Operating modes for the AI agent."""
    AUTONOMOUS = "autonomous"      # Agent executes decisions independently
    SUPERVISED = "supervised"      # Agent proposes, user approves
    INTERACTIVE = "interactive"    # Agent responds to queries only
    MONITORING = "monitoring"      # Agent monitors and reports only
    BACKTESTING = "backtesting"    # Agent runs in simulation mode


class AlertDeliveryMode(Enum):
    """How alerts are delivered."""
    IMMEDIATE = "immediate"        # Send alerts immediately
    BATCHED = "batched"           # Batch alerts and send periodically
    DIGEST = "digest"             # Send daily digest only
    SILENT = "silent"             # Log only, no external delivery


# ═══════════════════════════════════════════════════════════════════════════════
# AGENT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AgentSettings:
    """Core agent settings."""
    
    # Operating mode
    mode: AgentOperatingMode = AgentOperatingMode.AUTONOMOUS
    
    # Alert delivery
    alert_mode: AlertDeliveryMode = AlertDeliveryMode.IMMEDIATE
    
    # Decision thresholds
    min_confidence_for_action: float = 0.7      # 70% confidence required
    max_actions_per_hour: int = 10              # Rate limit actions
    cooldown_between_actions_sec: int = 60      # Min time between actions
    
    # Memory settings
    enable_memory: bool = True
    memory_retention_days: int = 90
    max_patterns_stored: int = 100
    
    # Logging
    log_all_decisions: bool = True
    log_tool_calls: bool = True
    verbose_logging: bool = False


@dataclass
class ToolPermissions:
    """Permissions for tool categories."""
    
    # Market data tools - always enabled
    market_data: bool = True
    
    # Technical analysis - always enabled
    technical_analysis: bool = True
    
    # Macro analysis - requires API keys
    macro_analysis: bool = True
    
    # Notifications - can be disabled for testing
    notifications: bool = True
    
    # State management - controlled write access
    state_write: bool = True
    
    # External data - MCP integration
    external_data: bool = True
    
    # Memory operations
    memory_read: bool = True
    memory_write: bool = True


@dataclass
class MCPServerSettings:
    """Settings for MCP server integration."""
    
    # Enable/disable specific servers
    github_enabled: bool = True
    memory_enabled: bool = True
    fetch_enabled: bool = True
    sequential_thinking_enabled: bool = True
    filesystem_enabled: bool = True
    
    # Server-specific settings
    github_repo: str = ""  # Default repo for issue creation
    github_auto_create_issues: bool = False  # Auto-create issues for critical signals
    
    # Memory settings
    memory_auto_store_signals: bool = True
    memory_pattern_detection: bool = True
    
    # Fetch settings
    fetch_cache_duration_sec: int = 300  # Cache fetched pages for 5 min
    fetch_rate_limit_per_min: int = 10
    
    # Thinking settings
    thinking_timeout_sec: int = 60


@dataclass
class LLMSettings:
    """Settings for LLM integration (optional)."""
    
    # Provider selection
    provider: str = "none"  # "openai", "anthropic", "azure", "none"
    
    # Model settings
    model: str = ""
    temperature: float = 0.1  # Low temperature for consistent analysis
    max_tokens: int = 1000
    
    # API configuration
    api_key_env_var: str = ""  # Environment variable name for API key
    
    # Usage limits
    max_calls_per_hour: int = 60
    enable_caching: bool = True


@dataclass
class MonitoringThresholds:
    """Thresholds for monitoring and alerting."""
    
    # SMA thresholds
    sma_period: int = 200
    sma_buffer_percent: float = 1.0  # Buffer zone around SMA
    
    # RSI thresholds
    rsi_period: int = 14
    rsi_overbought: float = 70.0
    rsi_oversold: float = 30.0
    rsi_extreme_overbought: float = 80.0
    rsi_extreme_oversold: float = 20.0
    
    # Trailing stop
    trailing_stop_percent: float = 5.0
    high_water_mark_days: int = 30
    
    # Crypto canary
    btc_crash_threshold_24h: float = -10.0
    btc_warning_threshold_24h: float = -5.0
    btc_crash_threshold_7d: float = -20.0
    
    # News sentiment
    news_negative_threshold: int = 5
    news_extreme_negative_threshold: int = 10
    
    # Volatility
    vix_elevated_threshold: float = 20.0
    vix_high_threshold: float = 30.0
    vix_extreme_threshold: float = 40.0


# ═══════════════════════════════════════════════════════════════════════════════
# COMPLETE AGENT CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AgentConfiguration:
    """Complete configuration for the Market Monitor Agent."""
    
    settings: AgentSettings = field(default_factory=AgentSettings)
    permissions: ToolPermissions = field(default_factory=ToolPermissions)
    mcp: MCPServerSettings = field(default_factory=MCPServerSettings)
    llm: LLMSettings = field(default_factory=LLMSettings)
    thresholds: MonitoringThresholds = field(default_factory=MonitoringThresholds)
    
    def validate(self) -> list[str]:
        """Validate configuration and return list of issues."""
        issues = []
        
        # Check API keys
        if self.permissions.macro_analysis:
            if not os.getenv("FMP_API_KEY"):
                issues.append("FMP_API_KEY not set - macro analysis will be limited")
        
        if self.permissions.market_data:
            if not os.getenv("POLYGON_API_KEY"):
                issues.append("POLYGON_API_KEY not set - will use yfinance fallback")
        
        if self.permissions.notifications:
            if not os.getenv("TELEGRAM_BOT_TOKEN"):
                issues.append("TELEGRAM_BOT_TOKEN not set - alerts disabled")
            if not os.getenv("TELEGRAM_CHAT_ID"):
                issues.append("TELEGRAM_CHAT_ID not set - alerts disabled")
        
        # Check MCP settings
        if self.mcp.github_enabled and self.mcp.github_auto_create_issues:
            if not self.mcp.github_repo:
                issues.append("GitHub repo not configured for auto-issue creation")
            if not os.getenv("GITHUB_TOKEN"):
                issues.append("GITHUB_TOKEN not set - GitHub MCP disabled")
        
        # Check LLM settings
        if self.llm.provider != "none":
            if self.llm.api_key_env_var and not os.getenv(self.llm.api_key_env_var):
                issues.append(f"LLM API key ({self.llm.api_key_env_var}) not set")
        
        return issues
    
    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to dictionary."""
        return {
            "settings": {
                "mode": self.settings.mode.value,
                "alert_mode": self.settings.alert_mode.value,
                "min_confidence_for_action": self.settings.min_confidence_for_action,
                "max_actions_per_hour": self.settings.max_actions_per_hour,
                "enable_memory": self.settings.enable_memory,
            },
            "permissions": {
                "market_data": self.permissions.market_data,
                "technical_analysis": self.permissions.technical_analysis,
                "macro_analysis": self.permissions.macro_analysis,
                "notifications": self.permissions.notifications,
                "state_write": self.permissions.state_write,
                "external_data": self.permissions.external_data,
            },
            "mcp": {
                "github_enabled": self.mcp.github_enabled,
                "memory_enabled": self.mcp.memory_enabled,
                "fetch_enabled": self.mcp.fetch_enabled,
                "sequential_thinking_enabled": self.mcp.sequential_thinking_enabled,
            },
            "thresholds": {
                "sma_period": self.thresholds.sma_period,
                "rsi_overbought": self.thresholds.rsi_overbought,
                "rsi_oversold": self.thresholds.rsi_oversold,
                "trailing_stop_percent": self.thresholds.trailing_stop_percent,
                "btc_crash_threshold_24h": self.thresholds.btc_crash_threshold_24h,
            },
        }


# ═══════════════════════════════════════════════════════════════════════════════
# PRESET CONFIGURATIONS
# ═══════════════════════════════════════════════════════════════════════════════

def get_default_config() -> AgentConfiguration:
    """Get default agent configuration."""
    return AgentConfiguration()


def get_conservative_config() -> AgentConfiguration:
    """Get conservative configuration with tighter thresholds."""
    config = AgentConfiguration()
    config.settings.mode = AgentOperatingMode.SUPERVISED
    config.thresholds.trailing_stop_percent = 3.0
    config.thresholds.btc_crash_threshold_24h = -7.0
    config.thresholds.rsi_overbought = 65.0
    config.thresholds.rsi_oversold = 35.0
    return config


def get_aggressive_config() -> AgentConfiguration:
    """Get aggressive configuration with looser thresholds."""
    config = AgentConfiguration()
    config.settings.mode = AgentOperatingMode.AUTONOMOUS
    config.thresholds.trailing_stop_percent = 8.0
    config.thresholds.btc_crash_threshold_24h = -15.0
    config.thresholds.rsi_overbought = 75.0
    config.thresholds.rsi_oversold = 25.0
    return config


def get_testing_config() -> AgentConfiguration:
    """Get configuration for testing (no external calls)."""
    config = AgentConfiguration()
    config.settings.mode = AgentOperatingMode.MONITORING
    config.settings.alert_mode = AlertDeliveryMode.SILENT
    config.permissions.notifications = False
    config.mcp.github_enabled = False
    config.mcp.fetch_enabled = False
    return config


def get_backtest_config() -> AgentConfiguration:
    """Get configuration for backtesting."""
    config = AgentConfiguration()
    config.settings.mode = AgentOperatingMode.BACKTESTING
    config.settings.alert_mode = AlertDeliveryMode.SILENT
    config.permissions.notifications = False
    config.permissions.state_write = False
    config.mcp.github_enabled = False
    config.mcp.memory_enabled = False
    config.mcp.fetch_enabled = False
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# ENVIRONMENT-BASED CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

def load_config_from_env() -> AgentConfiguration:
    """Load configuration from environment variables."""
    config = AgentConfiguration()
    
    # Agent mode
    mode_str = os.getenv("AGENT_MODE", "autonomous").lower()
    mode_map = {
        "autonomous": AgentOperatingMode.AUTONOMOUS,
        "supervised": AgentOperatingMode.SUPERVISED,
        "interactive": AgentOperatingMode.INTERACTIVE,
        "monitoring": AgentOperatingMode.MONITORING,
        "backtesting": AgentOperatingMode.BACKTESTING,
    }
    config.settings.mode = mode_map.get(mode_str, AgentOperatingMode.AUTONOMOUS)
    
    # Alert mode
    alert_str = os.getenv("ALERT_MODE", "immediate").lower()
    alert_map = {
        "immediate": AlertDeliveryMode.IMMEDIATE,
        "batched": AlertDeliveryMode.BATCHED,
        "digest": AlertDeliveryMode.DIGEST,
        "silent": AlertDeliveryMode.SILENT,
    }
    config.settings.alert_mode = alert_map.get(alert_str, AlertDeliveryMode.IMMEDIATE)
    
    # Thresholds
    if os.getenv("TRAILING_STOP_PERCENT"):
        config.thresholds.trailing_stop_percent = float(os.getenv("TRAILING_STOP_PERCENT"))
    
    if os.getenv("BTC_CRASH_THRESHOLD"):
        config.thresholds.btc_crash_threshold_24h = float(os.getenv("BTC_CRASH_THRESHOLD"))
    
    # MCP settings
    config.mcp.github_enabled = os.getenv("MCP_GITHUB_ENABLED", "true").lower() == "true"
    config.mcp.memory_enabled = os.getenv("MCP_MEMORY_ENABLED", "true").lower() == "true"
    config.mcp.fetch_enabled = os.getenv("MCP_FETCH_ENABLED", "true").lower() == "true"
    config.mcp.github_repo = os.getenv("GITHUB_REPO", "")
    
    # LLM settings
    config.llm.provider = os.getenv("LLM_PROVIDER", "none")
    config.llm.model = os.getenv("LLM_MODEL", "")
    config.llm.api_key_env_var = os.getenv("LLM_API_KEY_VAR", "")
    
    return config


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

# Default configuration instance
DEFAULT_CONFIG = get_default_config()

__all__ = [
    "AgentOperatingMode",
    "AlertDeliveryMode",
    "AgentSettings",
    "ToolPermissions",
    "MCPServerSettings",
    "LLMSettings",
    "MonitoringThresholds",
    "AgentConfiguration",
    "get_default_config",
    "get_conservative_config",
    "get_aggressive_config",
    "get_testing_config",
    "get_backtest_config",
    "load_config_from_env",
    "DEFAULT_CONFIG",
]
