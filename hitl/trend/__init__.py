"""
TradingGuard HITL - OmniTrend Oracle Service
Multi-horizon trend, regime, and Draw on Liquidity (DOL) prediction service
combining on-chart market microstructure and off-chart macro/sentiment intelligence.
"""

from hitl.trend.trend_oracle import TrendOracle, trend_oracle

__all__ = ["TrendOracle", "trend_oracle"]
