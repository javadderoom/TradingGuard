"""
TradingGuard HITL - Full-Year Multi-Season Genetic Strategy Discovery
Evolves quantitative strategies across 100,000 M5 bars (June 2025 to November 2026)
using strict 60/40 Walk-Forward cross-validation with 5 institutional overfitting gates.
"""

import sys
import json
import time
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.quant_engine.state_space import MathematicalStateSpace
from hitl.quant_engine.rule_engine import QuantRule
from hitl.quant_engine.vectorized_backtester import VectorizedBacktester
from hitl.quant_engine.walk_forward_validator import WalkForwardValidator, WalkForwardReport
from hitl.quant_engine.evolution import QuantEvolutionEngine, EvolutionConfig
from hitl.quant_engine.annual_backtest_runner import load_1year_data

OUTPUT_DIR = BASE_DIR / "backtest_results" / "quant_discovery" / "annual_1year"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

SPREADS = {
    "XAUUSD": 0.22,
    "BTCUSD": 0.20,
    "NQ":     1.00,
    "GBPUSD": 0.00006
}

def discover_annual_strategies_for_symbol(symbol: str) -> Dict[str, Any]:
    print(f"\n=======================================================")
    print(f"🚀 Running 1-Year Multi-Season Discovery: {symbol}")
    print(f"=======================================================")
    
    raw_df = load_1year_data(symbol)
    min_dt = pd.to_datetime(raw_df['time'].iloc[0], unit='s')
    max_dt = pd.to_datetime(raw_df['time'].iloc[-1], unit='s')
    days = (max_dt - min_dt).days
    print(f"  Bars: {len(raw_df):,d} | Range: {min_dt.strftime('%Y-%m-%d')} -> {max_dt.strftime('%Y-%m-%d')} ({days} days)")
    
    # Transform State Space
    t0 = time.time()
    ss = MathematicalStateSpace()
    state_df = ss.transform(raw_df)
    print(f"  Calculated State Space in {time.time() - t0:.2f}s")
    
    spread = SPREADS.get(symbol, 1.0)
    validator = WalkForwardValidator(
        symbol=symbol,
        spread=spread,
        min_oos_profit_factor=1.15,
        min_oos_trades=15,  # Higher hurdle for 1-year data
        min_degradation_ratio=0.45,
        max_drawdown_expansion=2.50
    )
    
    # Chronological Split: 60% IS (~10 months) vs 40% OOS (~7 months)
    df_is, df_oos = validator.split_data(state_df, is_ratio=0.60, purge_bars=100)
    is_start = pd.to_datetime(df_is['time'].iloc[0], unit='s')
    is_end = pd.to_datetime(df_is['time'].iloc[-1], unit='s')
    oos_start = pd.to_datetime(df_oos['time'].iloc[0], unit='s')
    oos_end = pd.to_datetime(df_oos['time'].iloc[-1], unit='s')
    print(f"  In-Sample Window  : {is_start.strftime('%Y-%m-%d')} -> {is_end.strftime('%Y-%m-%d')} ({len(df_is):,d} bars)")
    print(f"  Out-of-Sample Window: {oos_start.strftime('%Y-%m-%d')} -> {oos_end.strftime('%Y-%m-%d')} ({len(df_oos):,d} bars)")
    
    # Evolution Config: 15 generations, population 50
    evo_cfg = EvolutionConfig(
        population_size=50,
        generations=15,
        min_predicates=2,
        max_predicates=3,
        crossover_prob=0.60,
        mutation_prob=0.35,
        elitism_ratio=0.15,
        min_trades_threshold=30,
        random_seed=42
    )
    
    engine = QuantEvolutionEngine(
        symbol=symbol,
        state_df=df_is,
        config=evo_cfg,
        spread=spread
    )
    
    t_evo = time.time()
    scored_candidates = engine.run_evolution(verbose=True)
    candidates = [item[0] for item in scored_candidates]
    print(f"  Evolved {len(candidates)} candidate rules across 15 generations in {time.time() - t_evo:.2f}s")
    
    # Walk-forward validation
    ratified_rules = []
    print("\n  Auditing top candidates through 5 Walk-Forward Rejection Gates...")
    for idx, cand in enumerate(candidates[:15]):
        rep = validator.validate_rule(cand, df_is, df_oos)
        if rep.verdict == "RATIFIED":
            print(f"    ✅ [RATIFIED] Rule {cand.rule_id}: {cand.to_formula_str()[:60]}...")
            print(f"       IS: PF {rep.is_result.profit_factor:.2f} ({rep.is_result.total_fills} tr, {rep.is_result.net_r:.2f}R) | OOS: PF {rep.oos_result.profit_factor:.2f} ({rep.oos_result.total_fills} tr, {rep.oos_result.net_r:.2f}R, {rep.oos_result.win_rate:.1f}% WR)")
            ratified_rules.append((cand, rep))
        else:
            print(f"    ❌ [REJECTED] Rule {cand.rule_id}: {rep.rejection_reasons}")
            
    # Save symbol ratified rules
    sym_dir = OUTPUT_DIR / symbol.lower()
    sym_dir.mkdir(parents=True, exist_ok=True)
    
    data_to_save = []
    for rule, rep in ratified_rules:
        data_to_save.append({
            "rule": rule.to_dict(),
            "walk_forward_report": rep.to_dict()
        })
        
    with open(sym_dir / "annual_ratified_strategies.json", "w", encoding="utf-8") as f:
        json.dump(data_to_save, f, indent=2)
        
    print(f"\n  Symbol {symbol}: {len(ratified_rules)} strategies passed all 5 multi-season gates.")
    return {
        "symbol": symbol,
        "total_bars": len(raw_df),
        "is_bars": len(df_is),
        "oos_bars": len(df_oos),
        "candidates_tested": min(15, len(candidates)),
        "ratified_count": len(ratified_rules),
        "ratified_rules": [r[0].to_formula_str() for r in ratified_rules]
    }


def main():
    start_total = time.time()
    symbols = ["BTCUSD", "XAUUSD", "NQ", "GBPUSD"]
    all_summaries = {}
    
    for sym in symbols:
        all_summaries[sym] = discover_annual_strategies_for_symbol(sym)
        
    summary_path = OUTPUT_DIR / "annual_discovery_summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(all_summaries, f, indent=2)
        
    print("\n==========================================================================================")
    print("🏆 FULL-YEAR MULTI-SEASON QUANT DISCOVERY RUN COMPLETE!")
    print(f"Total Run Time: {time.time() - start_total:.2f}s")
    print("==========================================================================================")
    for sym, res in all_summaries.items():
        print(f"  {sym:8s} | Tested: {res['candidates_tested']:2d} | Ratified (1-Year Robust): {res['ratified_count']:2d}")

if __name__ == "__main__":
    main()
