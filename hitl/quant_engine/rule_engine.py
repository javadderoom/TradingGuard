"""
TradingGuard HITL - Quantitative Rule Engine
Represents machine-discovered trading rules as explicit, serializable
symbolic trees over the pure mathematical state space.
Strictly zero human narrative vocabulary.
"""

from dataclasses import dataclass, field
from typing import List, Tuple, Union, Dict, Any, Optional
import json
import numpy as np
import pandas as pd


@dataclass
class FeaturePredicate:
    """
    A single mathematical condition on one state-space dimension.
    e.g. (price_zscore_20 <= -2.15) or (autocorr_lag1 between [-0.4, -0.1])
    """
    feature: str
    op: str  # '<', '<=', '>', '>=', 'between'
    threshold: Union[float, Tuple[float, float], List[float]]

    def evaluate(self, df: pd.DataFrame) -> pd.Series:
        if self.feature not in df.columns:
            raise KeyError(f"Feature '{self.feature}' not found in state space columns")

        series = df[self.feature]
        if self.op == 'between':
            if isinstance(self.threshold, (tuple, list)) and len(self.threshold) >= 2:
                low = min(float(self.threshold[0]), float(self.threshold[1]))
                high = max(float(self.threshold[0]), float(self.threshold[1]))
            else:
                base = float(self.threshold if not isinstance(self.threshold, (tuple, list)) else self.threshold[0])
                low, high = base * 0.9, base * 1.1
            return (series >= low) & (series <= high)

        val = float(self.threshold[0]) if isinstance(self.threshold, (tuple, list)) else float(self.threshold)
        if self.op == '<':
            return series < val
        elif self.op == '<=':
            return series <= val
        elif self.op == '>':
            return series > val
        elif self.op == '>=':
            return series >= val
        else:
            raise ValueError(f"Unsupported operator: {self.op}")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "feature": self.feature,
            "op": self.op,
            "threshold": list(self.threshold) if isinstance(self.threshold, (tuple, list)) else float(self.threshold)
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FeaturePredicate":
        return cls(
            feature=data["feature"],
            op=data["op"],
            threshold=tuple(data["threshold"]) if isinstance(data["threshold"], list) else data["threshold"]
        )

    def __str__(self) -> str:
        if self.op == 'between':
            return f"({float(self.threshold[0]):.4f} <= {self.feature} <= {float(self.threshold[1]):.4f})"
        return f"({self.feature} {self.op} {float(self.threshold):.4f})"


@dataclass
class QuantRule:
    """
    An autonomous quantitative rule composed of mathematical predicates,
    execution direction, and volatility-scaled exit boundaries.
    """
    rule_id: str
    direction: str  # 'BUY' or 'SELL'
    predicates: List[FeaturePredicate]
    tp_atr_mult: float = 3.0
    sl_atr_mult: float = 1.2
    be_ratchet_r: Optional[float] = 1.5
    ttl_bars: int = 36
    cooldown_bars: int = 6  # Minimum bars between consecutive signal triggers

    def evaluate(self, state_df: pd.DataFrame) -> pd.Series:
        """
        Evaluates the conjunction of all predicates vectorially.
        Applies a cooldown refractory filter to prevent clustering on contiguous bars.
        """
        if not self.predicates:
            return pd.Series(False, index=state_df.index)

        cond = pd.Series(True, index=state_df.index)
        for pred in self.predicates:
            cond = cond & pred.evaluate(state_df)

        # Handle NaNs
        cond = cond.fillna(False)

        # Apply refractory cooldown: if signal fired at i, suppress signals for cooldown_bars
        signals = cond.values
        if not np.any(signals):
            return cond

        filtered_signals = np.zeros(len(signals), dtype=bool)
        last_fired = -self.cooldown_bars - 2

        for i in range(len(signals)):
            if signals[i]:
                if i - last_fired > self.cooldown_bars:
                    filtered_signals[i] = True
                    last_fired = i

        return pd.Series(filtered_signals, index=state_df.index)

    def to_formula_str(self) -> str:
        pred_str = " AND ".join(str(p) for p in self.predicates)
        be_str = f", BE: {self.be_ratchet_r:.1f}R" if self.be_ratchet_r else ""
        return (
            f"[{self.direction}] {pred_str} | "
            f"TP: {self.tp_atr_mult:.1f}xATR, SL: {self.sl_atr_mult:.1f}xATR{be_str}, TTL: {self.ttl_bars}b"
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "direction": self.direction,
            "predicates": [p.to_dict() for p in self.predicates],
            "tp_atr_mult": float(self.tp_atr_mult),
            "sl_atr_mult": float(self.sl_atr_mult),
            "be_ratchet_r": float(self.be_ratchet_r) if self.be_ratchet_r is not None else None,
            "ttl_bars": int(self.ttl_bars),
            "cooldown_bars": int(self.cooldown_bars),
            "formula": self.to_formula_str()
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "QuantRule":
        return cls(
            rule_id=data["rule_id"],
            direction=data["direction"],
            predicates=[FeaturePredicate.from_dict(p) for p in data["predicates"]],
            tp_atr_mult=float(data.get("tp_atr_mult", 3.0)),
            sl_atr_mult=float(data.get("sl_atr_mult", 1.2)),
            be_ratchet_r=float(data["be_ratchet_r"]) if data.get("be_ratchet_r") is not None else None,
            ttl_bars=int(data.get("ttl_bars", 36)),
            cooldown_bars=int(data.get("cooldown_bars", 6))
        )


class RuleSet:
    """Container for managing collections of discovered quantitative rules."""

    def __init__(self, rules: Optional[List[QuantRule]] = None):
        self.rules: List[QuantRule] = rules or []

    def add(self, rule: QuantRule):
        self.rules.append(rule)

    def to_json(self, filepath: str):
        data = [r.to_dict() for r in self.rules]
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)

    @classmethod
    def from_json(cls, filepath: str) -> "RuleSet":
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls([QuantRule.from_dict(d) for d in data])
