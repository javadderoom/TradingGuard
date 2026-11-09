"""
TradingGuard HITL - Autonomous Machine-Discovered Quant Strategy Generation Engine
Pure mathematical state space, genetic rule induction, vectorized backtesting,
and strict Walk-Forward In-Sample vs. Out-of-Sample cross-validation.
"""

from .state_space import MathematicalStateSpace, StateSpaceConfig
from .rule_engine import QuantRule, FeaturePredicate, RuleSet
from .vectorized_backtester import VectorizedBacktester, BacktestResult, TradeRecord
from .evolution import QuantEvolutionEngine, EvolutionConfig
from .walk_forward_validator import WalkForwardValidator, WalkForwardReport

__all__ = [
    "MathematicalStateSpace",
    "StateSpaceConfig",
    "QuantRule",
    "FeaturePredicate",
    "RuleSet",
    "VectorizedBacktester",
    "BacktestResult",
    "TradeRecord",
    "QuantEvolutionEngine",
    "EvolutionConfig",
    "WalkForwardValidator",
    "WalkForwardReport",
]
