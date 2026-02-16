"""
agent_tools.py — Extensible Tool Definitions for Market Monitor Agent

This module provides a framework for defining and extending tools available
to the AI agent. Tools can be:
  - Built-in (defined in agent_orchestrator.py)
  - Custom (defined here for domain-specific operations)
  - External (via MCP server integration)

Use this module to add new market monitoring capabilities without modifying
the core orchestrator.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo
from enum import Enum

import requests
import pandas as pd

from config import (
    POLYGON_API_KEY,
    FMP_API_KEY,
    BENCHMARK,
    ALL_TICKERS,
    CORE_PORTFOLIO,
    DEFENSIVE_INCOME,
    CRYPTO_CANARIES,
    SMA_PERIOD,
    RSI_PERIOD,
    RSI_OVERBOUGHT,
    RSI_OVERSOLD,
)

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════════
# CUSTOM TOOL DEFINITIONS
# ═══════════════════════════════════════════════════════════════════════════════

class CustomTools:
    """
    Collection of custom tools that extend the agent's capabilities.
    These tools focus on advanced market analysis and portfolio management.
    """
    
    @staticmethod
    async def calculate_portfolio_exposure(holdings: dict[str, float]) -> dict[str, Any]:
        """
        Calculate portfolio exposure across different asset classes.
        
        Args:
            holdings: Dict of ticker -> allocation percentage
            
        Returns:
            Exposure breakdown by category
        """
        exposure = {
            "core": 0.0,
            "defensive": 0.0,
            "crypto": 0.0,
            "other": 0.0,
        }
        
        for ticker, allocation in holdings.items():
            if ticker in CORE_PORTFOLIO or ticker == BENCHMARK:
                exposure["core"] += allocation
            elif ticker in DEFENSIVE_INCOME:
                exposure["defensive"] += allocation
            elif ticker in CRYPTO_CANARIES or "-USD" in ticker:
                exposure["crypto"] += allocation
            else:
                exposure["other"] += allocation
        
        # Calculate risk score (0-100)
        risk_score = (
            exposure["core"] * 0.6 +      # Core is moderate risk
            exposure["defensive"] * 0.2 +  # Defensive is low risk
            exposure["crypto"] * 1.0 +     # Crypto is high risk
            exposure["other"] * 0.5        # Other is moderate
        )
        
        return {
            "exposure": exposure,
            "risk_score": min(100, risk_score),
            "risk_level": "HIGH" if risk_score > 70 else "MEDIUM" if risk_score > 40 else "LOW",
            "recommendation": _get_portfolio_recommendation(exposure, risk_score),
        }
    
    @staticmethod
    async def analyze_correlation(tickers: list[str], period_days: int = 90) -> dict[str, Any]:
        """
        Analyze correlation between tickers over a period.
        Useful for portfolio diversification analysis.
        
        Args:
            tickers: List of ticker symbols
            period_days: Number of days to analyze
            
        Returns:
            Correlation matrix and insights
        """
        try:
            import yfinance as yf
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days)
            
            # Download data for all tickers
            data = yf.download(
                tickers,
                start=start_date,
                end=end_date,
                progress=False,
            )["Close"]
            
            if data.empty:
                return {"error": "Could not fetch data for correlation analysis"}
            
            # Calculate correlation matrix
            correlation = data.pct_change().corr()
            
            # Find highly correlated pairs
            high_correlation_pairs = []
            for i, t1 in enumerate(tickers):
                for t2 in tickers[i+1:]:
                    if t1 in correlation.columns and t2 in correlation.columns:
                        corr_value = correlation.loc[t1, t2]
                        if abs(corr_value) > 0.7:
                            high_correlation_pairs.append({
                                "pair": f"{t1}-{t2}",
                                "correlation": round(corr_value, 3),
                                "interpretation": "highly positive" if corr_value > 0 else "highly negative",
                            })
            
            return {
                "correlation_matrix": correlation.to_dict(),
                "high_correlation_pairs": high_correlation_pairs,
                "diversification_score": _calculate_diversification_score(correlation),
                "period_days": period_days,
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def calculate_volatility_metrics(ticker: str, period_days: int = 30) -> dict[str, Any]:
        """
        Calculate volatility metrics for a ticker.
        
        Args:
            ticker: The ticker symbol
            period_days: Number of days for calculation
            
        Returns:
            Volatility metrics including historical vol and VIX comparison
        """
        try:
            import yfinance as yf
            import numpy as np
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days * 2)  # Extra data for calculations
            
            data = yf.download(ticker, start=start_date, end=end_date, progress=False)
            
            if data.empty or len(data) < period_days:
                return {"error": f"Insufficient data for {ticker}"}
            
            # Calculate daily returns
            returns = data["Close"].pct_change().dropna()
            
            # Historical volatility (annualized)
            daily_vol = returns.std()
            annual_vol = daily_vol * np.sqrt(252)
            
            # Calculate recent vs longer-term volatility
            recent_vol = returns.tail(10).std() * np.sqrt(252)
            
            # Max drawdown
            rolling_max = data["Close"].cummax()
            drawdown = (data["Close"] - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            return {
                "ticker": ticker,
                "period_days": period_days,
                "daily_volatility": round(daily_vol * 100, 2),
                "annualized_volatility": round(annual_vol * 100, 2),
                "recent_10d_volatility": round(recent_vol * 100, 2),
                "volatility_trend": "increasing" if recent_vol > annual_vol else "decreasing",
                "max_drawdown_pct": round(max_drawdown * 100, 2),
                "risk_assessment": _assess_volatility_risk(annual_vol),
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def detect_market_regime(lookback_days: int = 60) -> dict[str, Any]:
        """
        Detect the current market regime based on multiple indicators.
        
        Returns classification:
        - BULL_TRENDING: Strong uptrend
        - BULL_CONSOLIDATING: Uptrend with consolidation
        - BEAR_TRENDING: Strong downtrend
        - BEAR_CONSOLIDATING: Downtrend with consolidation
        - RANGING: No clear trend
        - VOLATILE: High volatility, uncertain direction
        """
        try:
            import yfinance as yf
            import numpy as np
            
            spy = yf.download(BENCHMARK, period=f"{lookback_days}d", progress=False)
            
            if spy.empty or len(spy) < 20:
                return {"error": "Insufficient data for regime detection"}
            
            close = spy["Close"]
            
            # Calculate indicators
            sma_20 = close.rolling(20).mean().iloc[-1]
            sma_50 = close.rolling(50).mean().iloc[-1] if len(close) >= 50 else sma_20
            current_price = close.iloc[-1]
            
            # Price vs SMAs
            above_20 = current_price > sma_20
            above_50 = current_price > sma_50
            sma_20_above_50 = sma_20 > sma_50
            
            # Trend strength (slope of 20-day SMA)
            sma_20_series = close.rolling(20).mean().dropna()
            if len(sma_20_series) >= 10:
                trend_slope = (sma_20_series.iloc[-1] - sma_20_series.iloc[-10]) / sma_20_series.iloc[-10] * 100
            else:
                trend_slope = 0
            
            # Volatility
            returns = close.pct_change().dropna()
            volatility = returns.std() * np.sqrt(252) * 100  # Annualized
            
            # Determine regime
            if volatility > 30:
                regime = "VOLATILE"
            elif above_20 and above_50 and sma_20_above_50:
                if trend_slope > 2:
                    regime = "BULL_TRENDING"
                else:
                    regime = "BULL_CONSOLIDATING"
            elif not above_20 and not above_50 and not sma_20_above_50:
                if trend_slope < -2:
                    regime = "BEAR_TRENDING"
                else:
                    regime = "BEAR_CONSOLIDATING"
            else:
                regime = "RANGING"
            
            # Strategy recommendations per regime
            strategy_map = {
                "BULL_TRENDING": "Stay in core portfolio (IVV), consider adding on dips",
                "BULL_CONSOLIDATING": "Maintain positions, tighten stops, watch for breakout",
                "BEAR_TRENDING": "Move to defensive (JEPI/JEPQ), preserve capital",
                "BEAR_CONSOLIDATING": "Partial defensive, look for reversal signals",
                "RANGING": "Reduce position sizes, focus on income (JEPI/JEPQ)",
                "VOLATILE": "Reduce exposure, increase cash, wait for clarity",
            }
            
            return {
                "regime": regime,
                "indicators": {
                    "current_price": round(current_price, 2),
                    "sma_20": round(sma_20, 2),
                    "sma_50": round(sma_50, 2),
                    "above_20_sma": above_20,
                    "above_50_sma": above_50,
                    "trend_slope_pct": round(trend_slope, 2),
                    "annualized_volatility": round(volatility, 2),
                },
                "strategy_recommendation": strategy_map[regime],
                "lookback_days": lookback_days,
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def get_sector_performance(period: str = "1mo") -> dict[str, Any]:
        """
        Get sector performance to identify rotation opportunities.
        
        Args:
            period: yfinance period (1d, 5d, 1mo, 3mo, 6mo, 1y)
        """
        # Sector ETFs
        sectors = {
            "XLK": "Technology",
            "XLF": "Financials",
            "XLV": "Healthcare",
            "XLE": "Energy",
            "XLY": "Consumer Discretionary",
            "XLP": "Consumer Staples",
            "XLI": "Industrials",
            "XLB": "Materials",
            "XLU": "Utilities",
            "XLRE": "Real Estate",
            "XLC": "Communication Services",
        }
        
        try:
            import yfinance as yf
            
            performance = {}
            for etf, sector in sectors.items():
                try:
                    data = yf.Ticker(etf).history(period=period)
                    if not data.empty and len(data) >= 2:
                        pct_change = ((data["Close"].iloc[-1] / data["Close"].iloc[0]) - 1) * 100
                        performance[sector] = {
                            "etf": etf,
                            "change_pct": round(pct_change, 2),
                        }
                except Exception:
                    continue
            
            # Sort by performance
            sorted_sectors = sorted(performance.items(), key=lambda x: x[1]["change_pct"], reverse=True)
            
            return {
                "period": period,
                "performance": dict(sorted_sectors),
                "leaders": [s[0] for s in sorted_sectors[:3]],
                "laggards": [s[0] for s in sorted_sectors[-3:]],
                "rotation_signal": _analyze_sector_rotation(sorted_sectors),
            }
            
        except Exception as e:
            return {"error": str(e)}
    
    @staticmethod
    async def calculate_risk_metrics(
        portfolio: dict[str, float],
        benchmark: str = "SPY",
        period_days: int = 252
    ) -> dict[str, Any]:
        """
        Calculate comprehensive risk metrics for a portfolio.
        
        Args:
            portfolio: Dict of ticker -> weight (should sum to 1.0)
            benchmark: Benchmark ticker for comparison
            period_days: Days of history to use
        """
        try:
            import yfinance as yf
            import numpy as np
            
            tickers = list(portfolio.keys()) + [benchmark]
            end_date = datetime.now()
            start_date = end_date - timedelta(days=period_days * 1.5)
            
            data = yf.download(tickers, start=start_date, end=end_date, progress=False)["Close"]
            
            if data.empty:
                return {"error": "Could not fetch data"}
            
            returns = data.pct_change().dropna()
            
            # Portfolio returns
            portfolio_returns = pd.Series(0.0, index=returns.index)
            for ticker, weight in portfolio.items():
                if ticker in returns.columns:
                    portfolio_returns += returns[ticker] * weight
            
            benchmark_returns = returns[benchmark] if benchmark in returns.columns else returns.iloc[:, 0]
            
            # Risk metrics
            risk_free_rate = 0.05 / 252  # Approximate daily risk-free rate
            
            # Sharpe Ratio
            excess_returns = portfolio_returns - risk_free_rate
            sharpe_ratio = np.sqrt(252) * excess_returns.mean() / portfolio_returns.std()
            
            # Sortino Ratio
            negative_returns = portfolio_returns[portfolio_returns < 0]
            downside_std = negative_returns.std()
            sortino_ratio = np.sqrt(252) * excess_returns.mean() / downside_std if downside_std > 0 else 0
            
            # Beta
            covariance = portfolio_returns.cov(benchmark_returns)
            benchmark_variance = benchmark_returns.var()
            beta = covariance / benchmark_variance if benchmark_variance > 0 else 1.0
            
            # Alpha (Jensen's Alpha)
            portfolio_annual_return = (1 + portfolio_returns.mean()) ** 252 - 1
            benchmark_annual_return = (1 + benchmark_returns.mean()) ** 252 - 1
            alpha = portfolio_annual_return - (risk_free_rate * 252 + beta * (benchmark_annual_return - risk_free_rate * 252))
            
            # Maximum Drawdown
            cumulative = (1 + portfolio_returns).cumprod()
            rolling_max = cumulative.cummax()
            drawdown = (cumulative - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            # Value at Risk (95%)
            var_95 = np.percentile(portfolio_returns, 5)
            
            return {
                "portfolio": portfolio,
                "period_days": period_days,
                "metrics": {
                    "sharpe_ratio": round(sharpe_ratio, 3),
                    "sortino_ratio": round(sortino_ratio, 3),
                    "beta": round(beta, 3),
                    "alpha": round(alpha * 100, 2),  # As percentage
                    "max_drawdown_pct": round(max_drawdown * 100, 2),
                    "var_95_pct": round(var_95 * 100, 2),
                    "annualized_return_pct": round(portfolio_annual_return * 100, 2),
                    "annualized_volatility_pct": round(portfolio_returns.std() * np.sqrt(252) * 100, 2),
                },
                "interpretation": _interpret_risk_metrics(sharpe_ratio, beta, max_drawdown),
            }
            
        except Exception as e:
            return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

def _get_portfolio_recommendation(exposure: dict, risk_score: float) -> str:
    """Generate portfolio recommendation based on exposure and risk."""
    if risk_score > 70:
        return "Consider reducing core/crypto exposure and increasing defensive positions (JEPI/JEPQ)"
    elif risk_score < 30:
        return "Portfolio is conservative. Consider increasing core exposure if market conditions favor growth"
    else:
        return "Portfolio has balanced risk. Monitor market conditions for tactical adjustments"


def _calculate_diversification_score(correlation_matrix: pd.DataFrame) -> float:
    """Calculate diversification score from correlation matrix."""
    import numpy as np
    
    # Lower average correlation = better diversification
    upper_triangle = correlation_matrix.where(
        np.triu(np.ones(correlation_matrix.shape), k=1).astype(bool)
    )
    avg_correlation = upper_triangle.stack().mean()
    
    # Convert to 0-100 score (lower correlation = higher score)
    score = (1 - abs(avg_correlation)) * 100
    return round(score, 1)


def _assess_volatility_risk(annual_vol: float) -> str:
    """Assess volatility risk level."""
    if annual_vol > 0.40:
        return "HIGH - Significant price swings expected. Consider reducing position sizes."
    elif annual_vol > 0.20:
        return "MEDIUM - Normal market volatility. Standard position sizing appropriate."
    else:
        return "LOW - Relatively stable. May increase position sizes with proper risk management."


def _analyze_sector_rotation(sorted_sectors: list) -> str:
    """Analyze sector rotation pattern."""
    leaders = [s[0] for s in sorted_sectors[:3]]
    
    # Defensive sectors
    defensive = ["Utilities", "Consumer Staples", "Healthcare"]
    # Cyclical sectors
    cyclical = ["Technology", "Consumer Discretionary", "Financials", "Industrials"]
    
    defensive_leading = sum(1 for s in leaders if s in defensive)
    cyclical_leading = sum(1 for s in leaders if s in cyclical)
    
    if defensive_leading >= 2:
        return "DEFENSIVE ROTATION - Risk-off sentiment. Consider defensive positioning."
    elif cyclical_leading >= 2:
        return "CYCLICAL ROTATION - Risk-on sentiment. Growth-oriented assets favored."
    else:
        return "MIXED - No clear rotation pattern. Monitor for emerging trends."


def _interpret_risk_metrics(sharpe: float, beta: float, max_dd: float) -> str:
    """Interpret risk metrics in plain language."""
    interpretations = []
    
    if sharpe > 1.5:
        interpretations.append("Excellent risk-adjusted returns (Sharpe > 1.5)")
    elif sharpe > 1.0:
        interpretations.append("Good risk-adjusted returns (Sharpe > 1.0)")
    elif sharpe > 0.5:
        interpretations.append("Acceptable risk-adjusted returns")
    else:
        interpretations.append("Poor risk-adjusted returns - review strategy")
    
    if beta > 1.2:
        interpretations.append("High market sensitivity (beta > 1.2) - amplified moves")
    elif beta < 0.8:
        interpretations.append("Low market sensitivity (beta < 0.8) - defensive positioning")
    else:
        interpretations.append("Market-like sensitivity")
    
    if max_dd < -0.20:
        interpretations.append(f"Warning: Significant drawdown experienced ({max_dd*100:.1f}%)")
    
    return " | ".join(interpretations)


# ═══════════════════════════════════════════════════════════════════════════════
# TOOL FACTORY
# ═══════════════════════════════════════════════════════════════════════════════

class ToolFactory:
    """
    Factory for creating and registering tools with the agent.
    Use this to dynamically add tools at runtime.
    """
    
    @staticmethod
    def create_price_monitor_tool(ticker: str, threshold_pct: float):
        """
        Create a custom price monitoring tool for a specific ticker.
        
        Args:
            ticker: The ticker to monitor
            threshold_pct: Alert threshold percentage
        """
        async def monitor(current_price: Optional[float] = None) -> dict:
            from technical_analysis import get_current_price
            
            price = current_price or get_current_price(ticker)
            if price is None:
                return {"error": f"Could not get price for {ticker}"}
            
            # Store in memory for comparison
            return {
                "ticker": ticker,
                "price": price,
                "threshold_pct": threshold_pct,
                "status": "monitoring",
            }
        
        return {
            "name": f"monitor_{ticker.lower().replace('-', '_')}",
            "description": f"Monitor {ticker} price with {threshold_pct}% alert threshold",
            "handler": monitor,
        }
    
    @staticmethod
    def create_custom_alert_tool(name: str, condition_fn: Callable, message_template: str):
        """
        Create a custom alert tool with user-defined conditions.
        
        Args:
            name: Tool name
            condition_fn: Function that returns True when alert should trigger
            message_template: Message template with {placeholders}
        """
        async def check_alert(**kwargs) -> dict:
            try:
                should_alert = condition_fn(**kwargs)
                if should_alert:
                    message = message_template.format(**kwargs)
                    return {
                        "alert": True,
                        "message": message,
                        "params": kwargs,
                    }
                return {"alert": False, "params": kwargs}
            except Exception as e:
                return {"error": str(e)}
        
        return {
            "name": name,
            "description": f"Custom alert: {name}",
            "handler": check_alert,
        }


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTS
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    "CustomTools",
    "ToolFactory",
]
