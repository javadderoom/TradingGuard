"""
TradingGuard HITL - Pure Mathematical Quantitative Alpha Discovery & Backtesting Engine
Strictly zero human narrative vocabulary (zero SMC, zero ICT, zero subjective chart patterns).
Discovers, evolves, and validates systematic quant models across 100,000 M5 bars (June 2025 to November 2026).
Enforces 5 institutional overfitting gates, multi-seasonal consistency, and Student's t-statistic significance.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import os
import json
import time
import hashlib
from pathlib import Path
from typing import Dict, Any, List, Tuple, Optional
import numpy as np
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.quant_engine.state_space import MathematicalStateSpace
from hitl.quant_engine.rule_engine import QuantRule, FeaturePredicate
from hitl.quant_engine.vectorized_backtester import VectorizedBacktester, BacktestResult, TradeRecord
from hitl.quant_engine.walk_forward_validator import WalkForwardValidator, WalkForwardReport
from hitl.quant_engine.evolution import QuantEvolutionEngine, EvolutionConfig
from hitl.quant_engine.annual_backtest_runner import load_1year_data

OUTPUT_DIR = BASE_DIR / "backtest_results" / "quant_discovery"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SPREADS = {
    "XAUUSD": 0.22,
    "GOLD": 0.22,
    "NQ": 1.00,
    "US100": 1.00,
    "BTCUSD": 0.20,
    "GBPUSD": 0.00006,
    "EURUSD": 0.00005,
}

COMMISSION_USD = 0.10


def calculate_t_statistic(r_returns: List[float]) -> float:
    """Calculates Student's t-statistic: t = (mean * sqrt(N)) / std."""
    if len(r_returns) < 5:
        return 0.0
    arr = np.array(r_returns, dtype=float)
    std = float(np.std(arr, ddof=1))
    if std < 1e-9:
        return 0.0
    mean = float(np.mean(arr))
    return float((mean * np.sqrt(len(arr))) / std)


def compute_seasonal_breakdown(trades: List[TradeRecord]) -> Dict[str, Dict[str, Any]]:
    """
    Computes performance broken down across the 4 calendar seasons of 2026:
    - Winter 2026: Jan 1 to Feb 28
    - Spring 2026: Mar 1 to May 31
    - Summer 2026: Jun 1 to Aug 31
    - Autumn 2026: Sep 1 to Nov 15
    - Prior 2025: June 2025 to Dec 31, 2025
    """
    seasons = {
        "Prior_2025": [],
        "Winter_2026": [],
        "Spring_2026": [],
        "Summer_2026": [],
        "Autumn_2026": []
    }

    for t in trades:
        dt = pd.to_datetime(t.entry_time, unit='s')
        if dt.year == 2025:
            seasons["Prior_2025"].append(t)
        elif dt.year == 2026:
            if dt.month in (1, 2):
                seasons["Winter_2026"].append(t)
            elif dt.month in (3, 4, 5):
                seasons["Spring_2026"].append(t)
            elif dt.month in (6, 7, 8):
                seasons["Summer_2026"].append(t)
            else:
                seasons["Autumn_2026"].append(t)

    out = {}
    for s_name, s_trades in seasons.items():
        n = len(s_trades)
        if n == 0:
            out[s_name] = {"trades": 0, "net_r": 0.0, "profit_factor": 0.0, "win_rate": 0.0}
            continue
        wins = [x for x in s_trades if x.status == 'WIN']
        losses = [x for x in s_trades if x.status == 'LOSS']
        gross_w = sum(x.r_realized for x in wins)
        gross_l = abs(sum(x.r_realized for x in losses))
        pf = (gross_w / gross_l) if gross_l > 0 else (99.0 if gross_w > 0 else 0.0)
        net_r = sum(x.r_realized for x in s_trades)
        wr = (len(wins) / n) * 100.0
        out[s_name] = {
            "trades": n,
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(wr, 1),
            "net_r": round(net_r, 2),
            "profit_factor": round(pf, 2)
        }
    return out


class QuantAlphaMiner:
    """
    Systematic Quantitative Alpha Miner & Strategy Evaluator.
    Explores mathematical hypotheses and genetic combinations with zero SMC vocabulary.
    """

    def __init__(self, symbol: str, spread: Optional[float] = None):
        self.symbol = symbol.upper()
        self.spread = spread if spread is not None else SPREADS.get(self.symbol, 1.0)
        self.state_space_engine = MathematicalStateSpace()
        self.backtester = VectorizedBacktester(symbol=self.symbol, spread=self.spread)
        self.validator = WalkForwardValidator(
            symbol=self.symbol,
            spread=self.spread,
            min_oos_profit_factor=1.20,
            min_oos_trades=15,
            min_degradation_ratio=0.48,
            max_drawdown_expansion=2.20
        )

    def load_and_transform(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Loads 100,000 M5 bars and transforms to mathematical state space."""
        raw_df = load_1year_data(self.symbol)
        state_df = self.state_space_engine.transform(raw_df)
        return raw_df, state_df

    def synthesize_hypothesis_candidates(self, state_df: pd.DataFrame) -> List[QuantRule]:
        """
        Synthesizes structured candidate rules derived from quantitative market microstructure theory:
        1. Leptokurtic Momentum Shock (Velocity + Kurtosis)
        2. Volatility Compression Coil & Kinetic Breakout (Carter Squeeze)
        3. Statistical Mean Reversion (Variance Ratio + Quantile + Z-Score)
        4. Autocorrelation & Asymmetric Tail Reversion
        5. Momentum Convexity Acceleration
        """
        candidates: List[QuantRule] = []

        # Quant Rule 1: Leptokurtic Fat-Tail Momentum Continuation (Gold / BTC / NQ)
        for dir_name, dir_sign in [('BUY', 1), ('SELL', -1)]:
            for v_thresh in [0.0050, 0.0070, 0.0090]:
                for k_thresh in [1.0, 1.2, 1.5]:
                    r_id = f"HYP_KURT_{dir_name}_{int(v_thresh*10000)}v_{int(k_thresh*10)}k"
                    if dir_name == 'BUY':
                        preds = [
                            FeaturePredicate('velocity_55', '>=', v_thresh),
                            FeaturePredicate('kurtosis_30', '>', k_thresh),
                        ]
                    else:
                        preds = [
                            FeaturePredicate('velocity_55', '<=', -v_thresh),
                            FeaturePredicate('kurtosis_30', '>', k_thresh),
                        ]
                    candidates.append(QuantRule(
                        rule_id=r_id,
                        direction=dir_name,
                        predicates=preds,
                        tp_atr_mult=3.0,
                        sl_atr_mult=1.2,
                        be_ratchet_r=2.0,
                        ttl_bars=24,
                        cooldown_bars=6
                    ))

        # Quant Rule 2: Volatility Squeeze Kinetic Breakout (Carter Squeeze)
        for dir_name in ['BUY', 'SELL']:
            for sq_thresh in [0.85, 0.90, 0.95]:
                for v_fast in [0.0010, 0.0020]:
                    r_id = f"HYP_SQZ_{dir_name}_{int(sq_thresh*100)}sq_{int(v_fast*10000)}v"
                    if dir_name == 'BUY':
                        preds = [
                            FeaturePredicate('bb_keltner_squeeze', '<', sq_thresh),
                            FeaturePredicate('velocity_21', '>', v_fast),
                            FeaturePredicate('directional_vol_imb', '>', 0.30),
                        ]
                    else:
                        preds = [
                            FeaturePredicate('bb_keltner_squeeze', '<', sq_thresh),
                            FeaturePredicate('velocity_21', '<', -v_fast),
                            FeaturePredicate('directional_vol_imb', '<', -0.30),
                        ]
                    candidates.append(QuantRule(
                        rule_id=r_id,
                        direction=dir_name,
                        predicates=preds,
                        tp_atr_mult=3.5,
                        sl_atr_mult=1.5,
                        be_ratchet_r=1.8,
                        ttl_bars=36,
                        cooldown_bars=8
                    ))

        # Quant Rule 3: Statistical Mean Reversion (Variance Ratio + Rolling Quantile)
        for dir_name in ['BUY', 'SELL']:
            for vr_val in [0.75, 0.85]:
                for z_val in [1.8, 2.2]:
                    r_id = f"HYP_MR_{dir_name}_{int(vr_val*100)}vr_{int(z_val*10)}z"
                    if dir_name == 'BUY':
                        preds = [
                            FeaturePredicate('variance_ratio_20', '<', vr_val),
                            FeaturePredicate('rolling_quantile_100', '<=', 0.08),
                            FeaturePredicate('price_zscore_50', '<=', -z_val),
                        ]
                    else:
                        preds = [
                            FeaturePredicate('variance_ratio_20', '<', vr_val),
                            FeaturePredicate('rolling_quantile_100', '>=', 0.92),
                            FeaturePredicate('price_zscore_50', '>=', z_val),
                        ]
                    candidates.append(QuantRule(
                        rule_id=r_id,
                        direction=dir_name,
                        predicates=preds,
                        tp_atr_mult=2.5,
                        sl_atr_mult=1.2,
                        be_ratchet_r=1.5,
                        ttl_bars=30,
                        cooldown_bars=6
                    ))

        # Quant Rule 4: Multi-Scale Autocorrelation & Asymmetric Tail Reversion
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_ASYM_AC_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('autocorr_lag1', '<', -0.15),
                    FeaturePredicate('downside_semi_var_ratio_30', '>', 0.65),
                    FeaturePredicate('directional_vol_imb', '>', 0.20),
                ]
            else:
                preds = [
                    FeaturePredicate('autocorr_lag1', '<', -0.15),
                    FeaturePredicate('downside_semi_var_ratio_30', '<', 0.35),
                    FeaturePredicate('directional_vol_imb', '<', -0.20),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=2.5,
                sl_atr_mult=1.0,
                be_ratchet_r=1.5,
                ttl_bars=24,
                cooldown_bars=6
            ))

        # Quant Rule 5: Kinetic Velocity & Convexity Acceleration
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_CONVEX_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('velocity_21', '>', 0.0015),
                    FeaturePredicate('acceleration_convexity', '>', 0.0),
                    FeaturePredicate('volume_ratio', '>', 1.3),
                ]
            else:
                preds = [
                    FeaturePredicate('velocity_21', '<', -0.0015),
                    FeaturePredicate('acceleration_convexity', '<', 0.0),
                    FeaturePredicate('volume_ratio', '>', 1.3),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=3.0,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=30,
                cooldown_bars=6
            ))

        # Quant Rule 6: Yang-Zhang Volatility Jump Expansion
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_YZ_EXPANSION_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('yang_zhang_vol', '>', 0.0015),
                    FeaturePredicate('velocity_21', '>', 0.0012),
                    FeaturePredicate('acceleration_convexity', '>', 0.20),
                ]
            else:
                preds = [
                    FeaturePredicate('yang_zhang_vol', '>', 0.0015),
                    FeaturePredicate('velocity_21', '<', -0.0012),
                    FeaturePredicate('acceleration_convexity', '<', -0.20),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=30,
                cooldown_bars=6
            ))

        # Quant Rule 7: VPIN Orderflow Toxicity & Liquidation Shock
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_VPIN_TOXICITY_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('vpin_proxy', '>', 0.50),
                    FeaturePredicate('downside_semi_var_ratio_30', '<', 0.40),
                    FeaturePredicate('directional_vol_imb', '>', 0.20),
                ]
            else:
                preds = [
                    FeaturePredicate('vpin_proxy', '>', 0.50),
                    FeaturePredicate('downside_semi_var_ratio_30', '>', 0.60),
                    FeaturePredicate('directional_vol_imb', '<', -0.20),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))

        # Quant Rule 8: Microstructure Iceberg Absorption Exhaustion Snapback
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_ABSORPTION_REV_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('orderflow_abs_z', '>', 1.50),
                    FeaturePredicate('rolling_quantile_100', '<=', 0.12),
                    FeaturePredicate('rsi_stationary_14', '<=', -1.0),
                ]
            else:
                preds = [
                    FeaturePredicate('orderflow_abs_z', '>', 1.50),
                    FeaturePredicate('rolling_quantile_100', '>=', 0.88),
                    FeaturePredicate('rsi_stationary_14', '>=', 1.0),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=2.5,
                sl_atr_mult=1.0,
                be_ratchet_r=1.5,
                ttl_bars=24,
                cooldown_bars=6
            ))

        # Quant Rule 9: Fractal Hurst Persistence Momentum
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_HURST_MOM_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('hurst_proxy', '>', 0.55),
                    FeaturePredicate('variance_ratio_20', '>', 1.08),
                    FeaturePredicate('velocity_55', '>', 0.0025),
                ]
            else:
                preds = [
                    FeaturePredicate('hurst_proxy', '>', 0.55),
                    FeaturePredicate('variance_ratio_20', '>', 1.08),
                    FeaturePredicate('velocity_55', '<', -0.0025),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=4.0,
                sl_atr_mult=1.5,
                be_ratchet_r=2.0,
                ttl_bars=48,
                cooldown_bars=8
            ))

        # Quant Rule 10: Higher-Moment Tail Shock (Nonlinear Skew-Kurt Interaction)
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_TAIL_SHOCK_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('skew_kurt_interaction', '>', 1.0),
                    FeaturePredicate('velocity_8', '>', 0.0010),
                ]
            else:
                preds = [
                    FeaturePredicate('skew_kurt_interaction', '<', -1.0),
                    FeaturePredicate('velocity_8', '<', -0.0010),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=30,
                cooldown_bars=6
            ))

        # Quant Rule 11: Intraday Cyclical Harmonic Waves
        for dir_name in ['BUY', 'SELL']:
            r_id = f"HYP_CYCLE_WAVE_{dir_name}"
            if dir_name == 'BUY':
                preds = [
                    FeaturePredicate('bb_keltner_squeeze', '<', 0.90),
                    FeaturePredicate('velocity_21', '>', 0.0012),
                    FeaturePredicate('intraday_cycle_sin', 'between', (-0.85, 0.85)),
                ]
            else:
                preds = [
                    FeaturePredicate('bb_keltner_squeeze', '<', 0.90),
                    FeaturePredicate('velocity_21', '<', -0.0012),
                    FeaturePredicate('intraday_cycle_sin', 'between', (-0.85, 0.85)),
                ]
            candidates.append(QuantRule(
                rule_id=r_id,
                direction=dir_name,
                predicates=preds,
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))

        # Quant Rule 12: Asset-Specialized Structural Hypotheses
        if "NQ" in self.symbol:
            # NQ Asymmetric VPIN Toxic Breakout BUY
            candidates.append(QuantRule(
                rule_id="HYP_NQ_VPIN_BREAKOUT_BUY",
                direction="BUY",
                predicates=[
                    FeaturePredicate('vpin_proxy', '>', 0.45),
                    FeaturePredicate('price_zscore_50', '>=', 1.80),
                    FeaturePredicate('acceleration_convexity', '>', 0.0),
                ],
                tp_atr_mult=4.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))
            # NQ Asymmetric VPIN Toxic Breakdown SELL
            candidates.append(QuantRule(
                rule_id="HYP_NQ_VPIN_BREAKDOWN_SELL",
                direction="SELL",
                predicates=[
                    FeaturePredicate('vpin_proxy', '>', 0.45),
                    FeaturePredicate('price_zscore_50', '<=', -1.80),
                    FeaturePredicate('acceleration_convexity', '<', 0.0),
                ],
                tp_atr_mult=4.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))
            # NQ Yang-Zhang Volatility Compression Coil BUY
            candidates.append(QuantRule(
                rule_id="HYP_NQ_YZ_COIL_BUY",
                direction="BUY",
                predicates=[
                    FeaturePredicate('bb_keltner_squeeze', '<', 0.88),
                    FeaturePredicate('yang_zhang_vol', '<', 0.0018),
                    FeaturePredicate('velocity_8', '>', 0.0008),
                ],
                tp_atr_mult=4.0,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=30,
                cooldown_bars=6
            ))
            # NQ Coiling Z-Score Expansion BUY
            candidates.append(QuantRule(
                rule_id="HYP_NQ_COIL_EXPANSION_BUY",
                direction="BUY",
                predicates=[
                    FeaturePredicate('price_zscore_100', '<', 0.75),
                    FeaturePredicate('price_zscore_50', '>=', 2.15),
                    FeaturePredicate('accel_8', '<=', 0.00015),
                ],
                tp_atr_mult=4.5,
                sl_atr_mult=1.5,
                be_ratchet_r=1.8,
                ttl_bars=24,
                cooldown_bars=6
            ))
            # NQ Low-Volatility Z-Score Thrust BUY
            candidates.append(QuantRule(
                rule_id="HYP_NQ_LOWVOL_THRUST_BUY",
                direction="BUY",
                predicates=[
                    FeaturePredicate('norm_atr', '<', 0.0006),
                    FeaturePredicate('price_zscore_50', '>=', 2.15),
                    FeaturePredicate('price_zscore_100', '<', 1.10),
                ],
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=24,
                cooldown_bars=6
            ))

        elif "GBP" in self.symbol:
            # Cable Flow Toxicity Breakout BUY
            candidates.append(QuantRule(
                rule_id="HYP_GBP_FLOW_TOXICITY_BUY",
                direction="BUY",
                predicates=[
                    FeaturePredicate('vpin_proxy', '>', 0.48),
                    FeaturePredicate('velocity_21', '>', 0.0008),
                    FeaturePredicate('downside_semi_var_ratio_30', '<', 0.35),
                ],
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))
            # Cable Flow Toxicity Breakdown SELL
            candidates.append(QuantRule(
                rule_id="HYP_GBP_FLOW_TOXICITY_SELL",
                direction="SELL",
                predicates=[
                    FeaturePredicate('vpin_proxy', '>', 0.48),
                    FeaturePredicate('velocity_21', '<', -0.0008),
                    FeaturePredicate('downside_semi_var_ratio_30', '>', 0.65),
                ],
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))
            # Cable Velocity-Parkinson Exhaustion Reversion SELL
            candidates.append(QuantRule(
                rule_id="HYP_GBP_VOL_EXHAUSTION_SELL",
                direction="SELL",
                predicates=[
                    FeaturePredicate('velocity_55', 'between', (0.0020, 0.0029)),
                    FeaturePredicate('norm_atr', '>', 0.0003),
                    FeaturePredicate('parkinson_vol', '<', 0.00012),
                ],
                tp_atr_mult=3.0,
                sl_atr_mult=2.5,
                be_ratchet_r=2.0,
                ttl_bars=72,
                cooldown_bars=6
            ))
            # Cable Velocity-Skewness Exhaustion SELL
            candidates.append(QuantRule(
                rule_id="HYP_GBP_SKEW_EXHAUSTION_SELL",
                direction="SELL",
                predicates=[
                    FeaturePredicate('velocity_55', 'between', (0.0020, 0.0029)),
                    FeaturePredicate('skewness_30', '>', -0.90),
                    FeaturePredicate('parkinson_vol', '<', 0.00012),
                ],
                tp_atr_mult=3.0,
                sl_atr_mult=1.8,
                be_ratchet_r=1.5,
                ttl_bars=48,
                cooldown_bars=6
            ))

        elif "BTC" in self.symbol:
            # Bitcoin Asymmetric Left-Tail Skew & Autocorrelation SELL
            candidates.append(QuantRule(
                rule_id="HYP_BTC_ASYM_SKEW_SELL",
                direction="SELL",
                predicates=[
                    FeaturePredicate('skewness_30', '<', -1.40),
                    FeaturePredicate('autocorr_lag1', 'between', (0.02, 0.08)),
                ],
                tp_atr_mult=4.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=48,
                cooldown_bars=6
            ))
            # Bitcoin Volatility-Acceleration Compression BUY
            candidates.append(QuantRule(
                rule_id="HYP_BTC_VOL_COMPRESSION_BUY",
                direction="BUY",
                predicates=[
                    FeaturePredicate('accel_8', 'between', (-0.0003, 0.0)),
                    FeaturePredicate('parkinson_vol', '>', 0.0020),
                ],
                tp_atr_mult=3.5,
                sl_atr_mult=1.2,
                be_ratchet_r=1.8,
                ttl_bars=36,
                cooldown_bars=6
            ))

        return candidates

    def evolve_genetic_candidates(
        self,
        df_is: pd.DataFrame,
        seeds: List[int] = [42, 101, 777, 999]
    ) -> List[QuantRule]:
        """Runs genetic evolution across multiple seeds to discover non-obvious rules."""
        genetic_rules: List[QuantRule] = []
        for seed in seeds:
            cfg = EvolutionConfig(
                population_size=45,
                generations=15,
                min_predicates=2,
                max_predicates=3,
                crossover_prob=0.60,
                mutation_prob=0.45,
                elitism_ratio=0.15,
                min_trades_threshold=25,
                random_seed=seed
            )
            evo_engine = QuantEvolutionEngine(
                symbol=self.symbol,
                state_df=df_is,
                config=cfg,
                spread=self.spread
            )
            scored = evo_engine.run_evolution(verbose=False)
            for rule, res, fit in scored:
                if fit > 0.3 and res.profit_factor >= 1.20 and res.total_fills >= 25:
                    genetic_rules.append(rule)
        return genetic_rules

    def run_discovery_and_audit(self) -> Dict[str, Any]:
        """
        Executes end-to-end quant discovery, walk-forward validation,
        multi-seasonal robustness auditing, and t-statistic verification.
        """
        print(f"\n{'=' * 80}")
        print(f"🔬 RUNNING QUANT ALPHA DISCOVERY & AUDIT: {self.symbol}")
        print(f"{'=' * 80}")

        t0 = time.time()
        raw_df, state_df = self.load_and_transform()
        print(f"  Loaded {len(raw_df):,d} M5 bars (June 2025 -> Nov 2026). State Space transformed in {time.time() - t0:.2f}s")

        # 60/40 Chronological Walk-Forward Split with 100-bar Purge Buffer
        df_is, df_oos = self.validator.split_data(state_df, is_ratio=0.60, purge_bars=100)
        is_t0 = pd.to_datetime(df_is['time'].iloc[0], unit='s').strftime('%Y-%m-%d')
        is_t1 = pd.to_datetime(df_is['time'].iloc[-1], unit='s').strftime('%Y-%m-%d')
        oos_t0 = pd.to_datetime(df_oos['time'].iloc[0], unit='s').strftime('%Y-%m-%d')
        oos_t1 = pd.to_datetime(df_oos['time'].iloc[-1], unit='s').strftime('%Y-%m-%d')
        print(f"  In-Sample Window  : {is_t0} -> {is_t1} ({len(df_is):,d} bars)")
        print(f"  Out-of-Sample Window: {oos_t0} -> {oos_t1} ({len(df_oos):,d} bars)")

        # 1. Synthesize systematic hypothesis candidates
        hyp_candidates = self.synthesize_hypothesis_candidates(state_df)
        print(f"  Synthesized {len(hyp_candidates)} hypothesis-driven mathematical quant rules.")

        # 2. Evolve genetic candidates on In-Sample data
        print("  Running multi-seed genetic evolution on In-Sample window...")
        gen_candidates = self.evolve_genetic_candidates(df_is, seeds=[42, 101, 777])
        print(f"  Evolved {len(gen_candidates)} viable genetic rules from In-Sample evolution.")

        all_candidates = hyp_candidates + gen_candidates
        print(f"  Total candidate pool to audit through 5 Overfitting Gates: {len(all_candidates)}")

        ratified_strategies: List[Dict[str, Any]] = []
        audited_count = 0

        for cand in all_candidates:
            # Step 1: Walk-Forward Cross-Validation
            rep = self.validator.validate_rule(cand, df_is, df_oos)
            audited_count += 1

            if rep.verdict != "RATIFIED":
                continue

            # Additional statistical rigor: OOS Net R > 0, OOS fills >= 12
            if rep.oos_result.net_r <= 0.0 or rep.oos_result.total_fills < 12:
                continue

            # Step 2: Full-Sample 100,000-Bar Backtest
            full_res = self.backtester.run(state_df, cand)
            if full_res.profit_factor < 1.25 or full_res.net_r <= 10.0 or full_res.sharpe_ratio < 1.5:
                continue

            # Step 3: Statistical Significance (Student's t-statistic on R returns)
            r_returns = [t.r_realized for t in full_res.trades]
            t_stat = calculate_t_statistic(r_returns)
            if t_stat < 1.96:  # Less than 95% statistical significance
                continue

            # Step 4: Multi-Seasonal Breakdown across 4 Seasons of 2026
            seasonal_data = compute_seasonal_breakdown(full_res.trades)
            # Count losing seasons in 2026
            losing_seasons = sum(
                1 for s_name in ["Winter_2026", "Spring_2026", "Summer_2026", "Autumn_2026"]
                if seasonal_data[s_name]["trades"] >= 5 and seasonal_data[s_name]["net_r"] < 0
            )
            if losing_seasons >= 2:
                # Disqualify curve-fitted rules that fail across multiple seasons
                continue

            # Calculate month-by-month stability
            monthly_trades: Dict[str, List[TradeRecord]] = {}
            for t in full_res.trades:
                m_key = pd.to_datetime(t.entry_time, unit='s').strftime('%Y-%m')
                monthly_trades.setdefault(m_key, []).append(t)

            monthly_pnl = {
                m: round(sum(x.r_realized for x in trs), 2)
                for m, trs in sorted(monthly_trades.items())
            }

            ratified_entry = {
                "symbol": self.symbol,
                "rule_id": cand.rule_id,
                "direction": cand.direction,
                "formula": cand.to_formula_str(),
                "predicates": [p.to_dict() for p in cand.predicates],
                "tp_atr_mult": cand.tp_atr_mult,
                "sl_atr_mult": cand.sl_atr_mult,
                "be_ratchet_r": cand.be_ratchet_r,
                "ttl_bars": cand.ttl_bars,
                "full_sample": {
                    "total_fills": full_res.total_fills,
                    "wins": full_res.wins,
                    "losses": full_res.losses,
                    "breakevens": full_res.breakevens,
                    "expired": full_res.expired,
                    "win_rate_pct": round(full_res.win_rate, 2),
                    "net_r": round(full_res.net_r, 2),
                    "net_pnl_usd": round(full_res.net_pnl_usd, 2),
                    "profit_factor": round(full_res.profit_factor, 2),
                    "max_drawdown_r": round(full_res.max_drawdown_r, 2),
                    "sharpe_ratio": round(full_res.sharpe_ratio, 2),
                    "t_statistic": round(t_stat, 2),
                },
                "walk_forward": rep.to_dict(),
                "seasonal_breakdown": seasonal_data,
                "monthly_net_r": monthly_pnl,
                "trades": [
                    {
                        "entry_time": int(t.entry_time),
                        "exit_time": int(t.exit_time),
                        "direction": t.direction,
                        "entry_price": float(t.entry_price),
                        "exit_price": float(t.exit_price),
                        "sl_price": float(t.sl_price),
                        "tp_price": float(t.tp_price),
                        "status": t.status,
                        "r_realized": float(t.r_realized),
                        "pnl_usd": float(t.pnl_usd),
                        "bars_held": int(t.bars_held)
                    }
                    for t in full_res.trades
                ]
            }
            ratified_strategies.append(ratified_entry)
            print(f"  ⭐ [RATIFIED QUANT ALPHA] {cand.rule_id} ({cand.direction}):")
            print(f"     Formula: {cand.to_formula_str()[:80]}...")
            print(f"     Full-Sample: {full_res.total_fills} fills | {full_res.win_rate:.1f}% WR | Net: {full_res.net_r:+.2f}R | PF: {full_res.profit_factor:.2f} | Sharpe: {full_res.sharpe_ratio:.2f} | t-stat: {t_stat:.2f}")
            print(f"     In-Sample  : {rep.is_result.total_fills} fills | PF {rep.is_result.profit_factor:.2f} | Net {rep.is_result.net_r:+.2f}R")
            print(f"     Out-Sample : {rep.oos_result.total_fills} fills | PF {rep.oos_result.profit_factor:.2f} | Net {rep.oos_result.net_r:+.2f}R | DegRatio: {rep.degradation_ratio_pf:.2f}")

        # Deduplicate overlapping formulas by keeping the highest Sharpe rule
        deduped: List[Dict[str, Any]] = []
        seen_formulas = set()
        for strat in sorted(ratified_strategies, key=lambda x: x["full_sample"]["sharpe_ratio"], reverse=True):
            f_key = (strat["direction"], tuple(p["feature"] for p in strat["predicates"]))
            if f_key not in seen_formulas:
                seen_formulas.add(f_key)
                deduped.append(strat)

        print(f"\n  Final Ratified Setups for {self.symbol}: {len(deduped)} distinct high-conviction models.")
        return {
            "symbol": self.symbol,
            "total_candidates_audited": audited_count,
            "ratified_count": len(deduped),
            "strategies": deduped
        }


def run_portfolio_quant_mining(symbols: List[str] = ["XAUUSD", "NQ", "BTCUSD", "GBPUSD"]) -> Dict[str, Any]:
    """Runs the full quant alpha discovery across the entire portfolio."""
    start_time = time.time()
    portfolio_results: Dict[str, Any] = {}
    master_trades: List[Dict[str, Any]] = []

    for sym in symbols:
        miner = QuantAlphaMiner(symbol=sym)
        res = miner.run_discovery_and_audit()
        portfolio_results[sym] = res

        # Collect trades for master ledger
        for strat in res["strategies"]:
            for tr in strat["trades"]:
                tr_copy = dict(tr)
                tr_copy["symbol"] = sym
                tr_copy["rule_id"] = strat["rule_id"]
                tr_copy["direction"] = strat["direction"]
                master_trades.append(tr_copy)

    # Save master summary JSON
    summary_path = OUTPUT_DIR / "quant_alpha_discovery_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        # Save without massive trades array in summary
        summary_clean = {}
        for sym, data in portfolio_results.items():
            summary_clean[sym] = {
                "symbol": data["symbol"],
                "total_candidates_audited": data["total_candidates_audited"],
                "ratified_count": data["ratified_count"],
                "strategies": [
                    {k: v for k, v in s.items() if k != "trades"}
                    for s in data["strategies"]
                ]
            }
        json.dump(summary_clean, f, indent=2)

    # Save master trade ledger CSV
    ledger_path = OUTPUT_DIR / "quant_alpha_trade_ledger.csv"
    if master_trades:
        df_ledger = pd.DataFrame(master_trades)
        df_ledger.sort_values(by="entry_time").to_csv(ledger_path, index=False)
        print(f"\n📊 Master trade ledger exported to: {ledger_path} ({len(df_ledger):,d} total executed trades)")

    # Generate Cryptographic Run Manifest
    manifest_path = OUTPUT_DIR / "quant_alpha_run_manifest.json"
    ledger_hash = ""
    if ledger_path.exists():
        ledger_hash = hashlib.sha256(ledger_path.read_bytes()).hexdigest()

    manifest = {
        "execution_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "symbols_audited": symbols,
        "total_runtime_seconds": round(time.time() - start_time, 2),
        "trade_ledger_sha256": ledger_hash,
        "governance": {
            "mandate": "Zero SMC / Zero Human Narrative / Pure Mathematical State Space",
            "overfitting_protocol": "60/40 Walk-Forward Cross-Validation with 100-Bar Purge",
            "statistical_test": "Student's t-statistic >= 1.96 (p < 0.05)",
            "microstructure_realism": "MT5 Spreads + $0.10 Commission + Pessimistic Same-Bar Precedence"
        },
        "portfolio_summary": {
            sym: {
                "ratified_count": portfolio_results[sym]["ratified_count"],
                "top_models": [s["rule_id"] for s in portfolio_results[sym]["strategies"]]
            }
            for sym in symbols
        }
    }
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    print(f"\n🔒 Cryptographic run manifest generated: {manifest_path}")
    print(f"Total Execution Time: {time.time() - start_time:.2f}s")
    return portfolio_results


if __name__ == "__main__":
    run_portfolio_quant_mining()
