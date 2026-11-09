"""
TradingGuard HITL - Strict Walk-Forward Cross-Validation & Overfitting Penalizer
Enforces chronological In-Sample (IS) vs. Out-of-Sample (OOS) validation
and penalizes performance degradation, selection bias, and curve-fitting.
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from .rule_engine import QuantRule
from .vectorized_backtester import VectorizedBacktester, BacktestResult


@dataclass
class WalkForwardReport:
    rule_id: str
    symbol: str
    is_bars: int
    oos_bars: int
    is_result: BacktestResult
    oos_result: BacktestResult
    degradation_ratio_pf: float
    walk_forward_efficiency: float
    drawdown_expansion_ratio: float
    verdict: str  # 'RATIFIED' or 'REJECTED'
    rejection_reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "symbol": self.symbol,
            "verdict": self.verdict,
            "rejection_reasons": self.rejection_reasons,
            "in_sample": {
                "bars": self.is_bars,
                "trades": self.is_result.total_fills,
                "win_rate": round(self.is_result.win_rate, 2),
                "net_r": round(self.is_result.net_r, 2),
                "profit_factor": round(self.is_result.profit_factor, 2),
                "max_drawdown_r": round(self.is_result.max_drawdown_r, 2),
                "sharpe_ratio": round(self.is_result.sharpe_ratio, 2)
            },
            "out_of_sample": {
                "bars": self.oos_bars,
                "trades": self.oos_result.total_fills,
                "win_rate": round(self.oos_result.win_rate, 2),
                "net_r": round(self.oos_result.net_r, 2),
                "profit_factor": round(self.oos_result.profit_factor, 2),
                "max_drawdown_r": round(self.oos_result.max_drawdown_r, 2),
                "sharpe_ratio": round(self.oos_result.sharpe_ratio, 2)
            },
            "overfitting_metrics": {
                "degradation_ratio_pf": round(self.degradation_ratio_pf, 3),
                "walk_forward_efficiency": round(self.walk_forward_efficiency, 3),
                "drawdown_expansion_ratio": round(self.drawdown_expansion_ratio, 3)
            }
        }


class WalkForwardValidator:
    """
    Evaluates discovered rules on strictly separated In-Sample and Out-of-Sample windows.
    Applies strict rejection gates for overfitting.
    """

    def __init__(
        self,
        symbol: str,
        spread: Optional[float] = None,
        min_oos_profit_factor: float = 1.15,
        min_oos_trades: int = 6,
        min_degradation_ratio: float = 0.40,
        max_drawdown_expansion: float = 2.50
    ):
        self.symbol = symbol.upper()
        self.backtester = VectorizedBacktester(symbol=self.symbol, spread=spread)
        self.min_oos_pf = min_oos_profit_factor
        self.min_oos_trades = min_oos_trades
        self.min_deg_ratio = min_degradation_ratio
        self.max_dd_expansion = max_drawdown_expansion

    def split_data(
        self,
        state_df: pd.DataFrame,
        is_ratio: float = 0.60,
        purge_bars: int = 50
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits data chronologically with a purged boundary to eliminate trade leakage.
        """
        n = len(state_df)
        split_idx = int(n * is_ratio)

        df_is = state_df.iloc[:split_idx].copy().reset_index(drop=True)
        # Purge buffer
        oos_start = min(n, split_idx + purge_bars)
        df_oos = state_df.iloc[oos_start:].copy().reset_index(drop=True)

        return df_is, df_oos

    def validate_rule(
        self,
        rule: QuantRule,
        df_is: pd.DataFrame,
        df_oos: pd.DataFrame
    ) -> WalkForwardReport:
        """
        Runs dual backtests (IS and OOS) and applies 5 institutional overfitting gates.
        """
        is_res = self.backtester.run(df_is, rule)
        oos_res = self.backtester.run(df_oos, rule)

        # Degradation Ratio of Profit Factor (capped IS base to prevent zero-loss distortion)
        effective_is_pf = min(is_res.profit_factor, 10.0) if is_res.profit_factor > 0 else 0.0
        if effective_is_pf > 0:
            deg_ratio = oos_res.profit_factor / effective_is_pf
        else:
            deg_ratio = 0.0

        # Walk-Forward Efficiency: normalized return per bar
        is_ret_bar = (is_res.net_r / len(df_is)) if len(df_is) > 0 else 0.0
        oos_ret_bar = (oos_res.net_r / len(df_oos)) if len(df_oos) > 0 else 0.0
        wfe = (oos_ret_bar / is_ret_bar) if abs(is_ret_bar) > 1e-9 else 0.0

        # Drawdown expansion ratio
        if is_res.max_drawdown_r > 0:
            dd_exp = oos_res.max_drawdown_r / is_res.max_drawdown_r
        else:
            dd_exp = 1.0 if oos_res.max_drawdown_r == 0 else 99.0

        reasons = []

        # Gate 1: Insufficient Out-of-Sample Trades
        if oos_res.total_fills < self.min_oos_trades:
            reasons.append(
                f"INSUFFICIENT_OOS_SAMPLE: {oos_res.total_fills} trades (min required: {self.min_oos_trades})"
            )

        # Gate 2: Sub-threshold Out-of-Sample Profit Factor
        if oos_res.profit_factor < self.min_oos_pf:
            reasons.append(
                f"FAILED_OOS_PF: PF {oos_res.profit_factor:.2f} < threshold {self.min_oos_pf:.2f}"
            )

        # Gate 3: Negative Out-of-Sample Sharpe / Negative Net Alpha
        if oos_res.sharpe_ratio <= 0.0 or oos_res.net_r <= 0.0:
            reasons.append(
                f"NEGATIVE_OOS_ALPHA: Sharpe {oos_res.sharpe_ratio:.2f}, Net R {oos_res.net_r:+.2f}R"
            )

        # Gate 4: Excessive Performance Degradation (Overfitting Collapse)
        # Note: If OOS Profit Factor is independently robust (>= 1.75), do not penalize for degradation
        if deg_ratio < self.min_deg_ratio and oos_res.profit_factor < 1.75:
            reasons.append(
                f"EXCESSIVE_DEGRADATION: PF dropped by {(1.0 - deg_ratio)*100:.1f}% (ratio {deg_ratio:.2f} < {self.min_deg_ratio:.2f})"
            )

        # Gate 5: Uncontrolled Drawdown Expansion
        if dd_exp > self.max_dd_expansion:
            reasons.append(
                f"DRAWDOWN_EXPLOSION: OOS MaxDD ({oos_res.max_drawdown_r:.2f}R) is {dd_exp:.1f}x IS MaxDD ({is_res.max_drawdown_r:.2f}R)"
            )

        verdict = "RATIFIED" if len(reasons) == 0 else "REJECTED"

        return WalkForwardReport(
            rule_id=rule.rule_id,
            symbol=self.symbol,
            is_bars=len(df_is),
            oos_bars=len(df_oos),
            is_result=is_res,
            oos_result=oos_res,
            degradation_ratio_pf=deg_ratio,
            walk_forward_efficiency=wfe,
            drawdown_expansion_ratio=dd_exp,
            verdict=verdict,
            rejection_reasons=reasons
        )

    def evaluate_cross_asset(
        self,
        rule: QuantRule,
        target_symbol: str,
        target_state_df: pd.DataFrame
    ) -> BacktestResult:
        """
        Evaluates a ratified rule directly across an alternative instrument
        without parameter re-fitting to test structural transferability.
        """
        target_tester = VectorizedBacktester(symbol=target_symbol)
        return target_tester.run(target_state_df, rule)
