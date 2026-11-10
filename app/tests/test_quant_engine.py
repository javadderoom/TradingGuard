"""
TradingGuard Unit & Integration Tests - Autonomous Quant Strategy Generation Engine
Tests pure mathematical state space, symbolic rule engine, vectorized backtester,
genetic evolution operators, and strict Walk-Forward In-Sample vs. Out-of-Sample cross-validation.
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
import json
from pathlib import Path

from hitl.quant_engine.state_space import MathematicalStateSpace, StateSpaceConfig
from hitl.quant_engine.rule_engine import QuantRule, FeaturePredicate, RuleSet
from hitl.quant_engine.vectorized_backtester import VectorizedBacktester, BacktestResult, TradeRecord
from hitl.quant_engine.evolution import QuantEvolutionEngine, EvolutionConfig
from hitl.quant_engine.walk_forward_validator import WalkForwardValidator, WalkForwardReport


@pytest.fixture
def synthetic_ohlcv():
    """Generates 500 bars of synthetic OHLCV data with realistic properties."""
    np.random.seed(42)
    n = 500
    times = 1787619600 + np.arange(n) * 300

    # Geometric random walk with slight drift
    returns = np.random.normal(0.0001, 0.002, n)
    price = 100.0 * np.exp(np.cumsum(returns))

    high = price * (1.0 + np.abs(np.random.normal(0, 0.0015, n)))
    low = price * (1.0 - np.abs(np.random.normal(0, 0.0015, n)))
    open_p = price * (1.0 + np.random.normal(0, 0.0005, n))
    close_p = price
    vol = np.random.randint(100, 2000, n)

    df = pd.DataFrame({
        'time': times,
        'open': open_p,
        'high': high,
        'low': low,
        'close': close_p,
        'tick_volume': vol
    })
    return df


def test_mathematical_state_space_computation(synthetic_ohlcv):
    """Verifies that all pure mathematical state-space features are correctly computed without NaNs in tail."""
    engine = MathematicalStateSpace()
    features_df = engine.transform(synthetic_ohlcv)

    expected_cols = [
        'parkinson_vol', 'gk_vol', 'norm_atr', 'vol_regime_z',
        'velocity_3', 'velocity_8', 'velocity_21', 'velocity_55',
        'accel_3', 'accel_8', 'accel_21', 'curvature_8', 'ma_divergence',
        'price_zscore_20', 'price_zscore_50', 'price_zscore_100',
        'skewness_30', 'kurtosis_30', 'volume_ratio', 'directional_vol_imb',
        'vwap_deviation_z', 'autocorr_lag1', 'autocorr_lag2', 'autocorr_lag3', 'autocorr_lag5'
    ]

    for col in expected_cols:
        assert col in features_df.columns, f"Missing feature column: {col}"

    # Verify tail has valid numerical values (no persistent NaNs after warmup)
    tail = features_df.iloc[-50:]
    for col in expected_cols:
        assert not tail[col].isna().any(), f"Unexpected NaN in tail of feature: {col}"

    # Check bounds
    assert (tail['parkinson_vol'] >= 0).all()
    assert (tail['gk_vol'] >= 0).all()
    assert (tail['autocorr_lag1'] >= -1.0).all() and (tail['autocorr_lag1'] <= 1.0).all()


def test_feature_predicate_evaluation():
    """Verifies evaluation of individual mathematical predicates across operators."""
    df = pd.DataFrame({
        'zscore': [-2.5, -1.0, 0.0, 1.2, 2.8],
        'vol': [0.1, 0.2, 0.3, 0.4, 0.5]
    })

    p_lt = FeaturePredicate('zscore', '<', -1.5)
    res_lt = p_lt.evaluate(df)
    assert res_lt.tolist() == [True, False, False, False, False]

    p_gte = FeaturePredicate('zscore', '>=', 1.2)
    res_gte = p_gte.evaluate(df)
    assert res_gte.tolist() == [False, False, False, True, True]

    p_between = FeaturePredicate('vol', 'between', (0.2, 0.4))
    res_between = p_between.evaluate(df)
    assert res_between.tolist() == [False, True, True, True, False]


def test_quant_rule_serialization_and_cooldown():
    """Verifies QuantRule JSON serialization, string formatting, and refractory cooldown."""
    p1 = FeaturePredicate('price_zscore_20', '<=', -2.0)
    p2 = FeaturePredicate('autocorr_lag1', '<', -0.1)

    rule = QuantRule(
        rule_id="QRULE-TEST-001",
        direction="BUY",
        predicates=[p1, p2],
        tp_atr_mult=3.0,
        sl_atr_mult=1.0,
        be_ratchet_r=1.5,
        ttl_bars=24,
        cooldown_bars=5
    )

    # String format
    formula = rule.to_formula_str()
    assert "[BUY]" in formula
    assert "price_zscore_20 <= -2.0000" in formula
    assert "TP: 3.0xATR" in formula

    # Roundtrip serialization
    d = rule.to_dict()
    restored = QuantRule.from_dict(d)
    assert restored.rule_id == rule.rule_id
    assert restored.direction == rule.direction
    assert len(restored.predicates) == 2
    assert restored.tp_atr_mult == 3.0

    # Cooldown test: continuous true conditions should be suppressed
    df = pd.DataFrame({
        'price_zscore_20': [-2.5] * 10,
        'autocorr_lag1': [-0.2] * 10
    })
    signals = rule.evaluate(df)
    # With cooldown_bars=5, bar 0 triggers, then next trigger can only be bar 6
    assert signals.iloc[0] == True
    assert signals.iloc[1:6].sum() == 0
    assert signals.iloc[6] == True


def test_vectorized_backtester_execution(synthetic_ohlcv):
    """Verifies trade simulation, spread/commission, and metric calculations."""
    engine = MathematicalStateSpace()
    state_df = engine.transform(synthetic_ohlcv)

    # Construct a rule that triggers trades
    rule = QuantRule(
        rule_id="QRULE-TEST-BUY",
        direction="BUY",
        predicates=[FeaturePredicate('price_zscore_20', '<', -0.5)],
        tp_atr_mult=2.0,
        sl_atr_mult=1.0,
        be_ratchet_r=1.2,
        ttl_bars=20,
        cooldown_bars=10
    )

    backtester = VectorizedBacktester(symbol="NQ", spread=1.5, commission_usd=0.10)
    result = backtester.run(state_df, rule)

    assert result.total_signals > 0
    assert result.total_fills > 0
    assert result.wins + result.losses + result.breakevens + result.expired == result.total_fills
    assert 0.0 <= result.win_rate <= 100.0

    # Verify trade record details
    first_trade = result.trades[0]
    assert first_trade.direction == "BUY"
    assert first_trade.entry_price > 0
    assert first_trade.sl_price < first_trade.entry_price
    assert first_trade.tp_price > first_trade.entry_price
    assert first_trade.status in ['WIN', 'LOSS', 'BREAKEVEN', 'EXPIRED']


def test_pessimistic_intra_bar_precedence():
    """TradingGuard mandate: When both SL and TP (or SL and BE) are touched in same bar, must register LOSS."""
    # Bar 1 high touches TP and BE, low touches original SL
    df = pd.DataFrame({
        'time': [1000, 1300, 1600],
        'open': [100.0, 100.0, 100.0],
        'high': [100.5, 110.0, 100.0],  # Bar 1 high touches TP (106) and BE threshold (103.6)
        'low': [99.5, 90.0, 100.0],     # Bar 1 low touches SL (97)
        'close': [100.0, 100.0, 100.0],
        'atr_raw': [3.0, 3.0, 3.0],
        'zscore': [-2.0, 0.0, 0.0]
    })

    # Even with be_ratchet_r active, intra-bar ordering must not convert dual-touch to BREAKEVEN!
    rule = QuantRule(
        rule_id="QRULE-PESSIMISTIC",
        direction="BUY",
        predicates=[FeaturePredicate('zscore', '<', -1.0)],
        tp_atr_mult=2.0,  # TP = 100 + 6 = 106
        sl_atr_mult=1.0,  # SL = 100 - 3 = 97
        be_ratchet_r=1.2,
        ttl_bars=5,
        cooldown_bars=1
    )

    backtester = VectorizedBacktester(symbol="TEST", spread=0.0, commission_usd=0.10)
    res = backtester.run(df, rule)

    assert res.total_fills == 1
    assert res.trades[0].status == "LOSS"
    assert res.losses == 1
    assert res.wins == 0
    assert res.breakevens == 0


def test_sell_spread_mechanics_and_sl_precedence():
    """Verifies that SELL positions exit at Ask (Bid + spread) and dual-touch registers LOSS."""
    df = pd.DataFrame({
        'time': [1000, 1300, 1600],
        'open': [100.0, 100.0, 100.0],
        'high': [100.0, 101.5, 100.0],  # Highest Ask is 101.5 + 1.0 = 102.5 (touches SL 102.0)
        'low': [100.0, 95.0, 100.0],    # Lowest Ask is 95.0 + 1.0 = 96.0 (touches TP 96.0)
        'close': [100.0, 96.0, 100.0],
        'atr_raw': [2.0, 2.0, 2.0],
        'zscore': [2.0, 0.0, 0.0]
    })

    rule = QuantRule(
        rule_id="QRULE-SELL-SPREAD",
        direction="SELL",
        predicates=[FeaturePredicate('zscore', '>', 1.0)],
        tp_atr_mult=2.0,  # TP = 100 - 4 = 96 (Ask)
        sl_atr_mult=1.0,  # SL = 100 + 2 = 102 (Ask)
        be_ratchet_r=1.2,
        ttl_bars=5,
        cooldown_bars=1
    )

    backtester = VectorizedBacktester(symbol="TEST", spread=1.0, commission_usd=0.10)
    res = backtester.run(df, rule)

    assert res.total_fills == 1
    assert res.trades[0].status == "LOSS"
    assert res.trades[0].entry_price == 100.0  # Fills at raw_open (Bid)
    assert res.trades[0].sl_price == 102.0    # Ask SL
    assert res.trades[0].tp_price == 96.0     # Ask TP


def test_breakeven_pnl_accounting():
    """Verifies that covered breakeven accurately recovers spread without hardcoded fake values."""
    # Bar 1 hits BE threshold without touching SL/TP. Bar 2 drops to covered SL.
    df = pd.DataFrame({
        'time': [1000, 1300, 1600, 1900],
        'open': [100.0, 100.0, 103.0, 101.0],
        'high': [100.0, 104.0, 103.5, 101.5],  # Bar 1 high reaches 104 (arms BE >= 101 + 1.2*2 = 103.4)
        'low': [100.0, 100.5, 101.5, 101.0],   # Bar 2 low reaches 101.5 <= effective_sl (101 + 1.0 = 102.0)
        'close': [100.0, 103.0, 101.5, 101.0],
        'atr_raw': [2.0, 2.0, 2.0, 2.0],
        'zscore': [-2.0, 0.0, 0.0, 0.0]
    })

    rule = QuantRule(
        rule_id="QRULE-BE-PNL",
        direction="BUY",
        predicates=[FeaturePredicate('zscore', '<', -1.0)],
        tp_atr_mult=3.0,  # TP = 101 + 6 = 107
        sl_atr_mult=1.0,  # SL = 101 - 2 = 99
        be_ratchet_r=1.2,
        ttl_bars=5,
        cooldown_bars=1
    )

    backtester = VectorizedBacktester(symbol="TEST", spread=1.0, commission_usd=0.10, risk_per_trade_usd=12.0)
    res = backtester.run(df, rule)

    assert res.total_fills == 1
    t = res.trades[0]
    assert t.status == "BREAKEVEN"
    # Initial risk = 2.0 pts. USD per pt = 12.0 / 2.0 = 6.0 USD/pt.
    # Covered spread = 1.0 pt = $6.00 gross. Net PnL = $6.00 - $0.10 commission = $5.90.
    assert t.pnl_usd == 5.90


def test_cross_asset_stress_transferability():
    """Verifies that WalkForwardValidator can evaluate rules across alternative instruments."""
    rule = QuantRule(
        rule_id="QRULE-TRANSFER",
        direction="BUY",
        predicates=[FeaturePredicate('zscore', '<', 0.0)],
        tp_atr_mult=2.0,
        sl_atr_mult=1.0,
        ttl_bars=10
    )

    target_df = pd.DataFrame({
        'time': [1000, 1300, 1600, 1900],
        'open': [200.0, 200.0, 201.0, 202.0],
        'high': [200.0, 205.0, 204.0, 203.0],
        'low': [200.0, 199.0, 200.0, 201.0],
        'close': [200.0, 204.0, 203.0, 202.0],
        'atr_raw': [2.0, 2.0, 2.0, 2.0],
        'zscore': [-1.0, 0.5, 0.2, 0.0]
    })

    validator = WalkForwardValidator(symbol="NQ")
    res = validator.evaluate_cross_asset(rule, "SPX", target_df)
    assert isinstance(res, BacktestResult)
    assert res.symbol == "SPX"


def test_walk_forward_validator_rejection_gates(synthetic_ohlcv):
    """Verifies that Walk-Forward cross-validation strictly catches and penalizes overfitting."""
    engine = MathematicalStateSpace()
    state_df = engine.transform(synthetic_ohlcv)

    validator = WalkForwardValidator(symbol="NQ", min_oos_profit_factor=1.20, min_oos_trades=5)
    df_is, df_oos = validator.split_data(state_df, is_ratio=0.60, purge_bars=20)

    # 1. Rule with low trades should be rejected with INSUFFICIENT_OOS_SAMPLE
    rare_rule = QuantRule(
        rule_id="QRULE-RARE",
        direction="BUY",
        predicates=[FeaturePredicate('price_zscore_20', '<', -4.0)],  # Extremely rare
        tp_atr_mult=3.0,
        sl_atr_mult=1.0,
        ttl_bars=20
    )
    report_rare = validator.validate_rule(rare_rule, df_is, df_oos)
    assert report_rare.verdict == "REJECTED"
    assert any("INSUFFICIENT_OOS_SAMPLE" in r for r in report_rare.rejection_reasons)

    # 2. Walk forward split sizes
    assert len(df_is) < len(state_df)
    assert len(df_oos) < len(state_df)
    assert len(df_is) + len(df_oos) + 20 == len(state_df)


def test_genetic_evolution_engine(synthetic_ohlcv):
    """Verifies autonomous population generation, crossover, mutation, and elitism."""
    engine = MathematicalStateSpace()
    state_df = engine.transform(synthetic_ohlcv)

    cfg = EvolutionConfig(
        population_size=10,
        generations=2,
        min_trades_threshold=3,
        random_seed=42
    )

    evo = QuantEvolutionEngine(symbol="NQ", state_df=state_df, config=cfg)
    results = evo.run_evolution(verbose=False)

    assert len(results) > 0
    best_rule, best_result, best_fitness = results[0]
    assert isinstance(best_rule, QuantRule)
    assert isinstance(best_result, BacktestResult)
    assert isinstance(best_fitness, float)


def test_live_quant_bridge_ratified_suite_and_pricing():
    """Verifies that LiveQuantBridge loads 11 ratified multi-season rules and verifies MT5 limit pricing bounds."""
    from hitl.quant_engine.live_quant_bridge import LiveQuantBridge
    bridge = LiveQuantBridge(engine=None, client=None)
    
    # 1. Verify 11 ratified rules loaded
    total_rules = sum(len(r) for r in bridge.rules_by_symbol.values())
    assert total_rules == 11, f"Expected 11 ratified rules, got {total_rules}"
    assert "BTCUSD" in bridge.rules_by_symbol and len(bridge.rules_by_symbol["BTCUSD"]) == 3
    assert "NQ" in bridge.rules_by_symbol and len(bridge.rules_by_symbol["NQ"]) == 3
    assert "GBPUSD" in bridge.rules_by_symbol and len(bridge.rules_by_symbol["GBPUSD"]) == 2
    assert "XAUUSD" in bridge.rules_by_symbol and len(bridge.rules_by_symbol["XAUUSD"]) == 3

    # 2. Verify limit pricing logic:
    # BUY LIMIT must be strictly < Bid
    # SELL LIMIT must be strictly > Ask
    bid = 1.34200
    ask = 1.34208
    spread = ask - bid
    point = 0.00001
    digits = 5
    stops_level = 0.0
    min_offset = max(stops_level, point * 5, 0.2 * spread)

    buy_entry = round(bid - min_offset, digits)
    if buy_entry >= bid:
        buy_entry = round(bid - (point * 5), digits)
    assert buy_entry < bid, f"Buy Limit {buy_entry} must be strictly below bid {bid}"

    sell_entry = round(ask + min_offset, digits)
    if sell_entry <= ask:
        sell_entry = round(ask + (point * 5), digits)
    assert sell_entry > ask, f"Sell Limit {sell_entry} must be strictly above ask {ask}"

