"""
TradingGuard HITL - Autonomous Quant Engine Runner & Discovery CLI
Executes the full pipeline:
1. Ingests raw cached market data across broker instruments.
2. Constructs pure mathematical state space.
3. Splits into strict In-Sample (IS) and Out-of-Sample (OOS) with purged gap.
4. Autonomously evolves, mutates, and discovers quantitative trading rules.
5. Enforces Walk-Forward cross-validation and penalizes overfitting.
6. Cross-asset stress tests ratified rules.
7. Registers ratified archetypes and exports audit reports.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
import os
import json
import time
import argparse
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.quant_engine.state_space import MathematicalStateSpace
from hitl.quant_engine.rule_engine import QuantRule, RuleSet
from hitl.quant_engine.vectorized_backtester import VectorizedBacktester
from hitl.quant_engine.evolution import QuantEvolutionEngine, EvolutionConfig
from hitl.quant_engine.walk_forward_validator import WalkForwardValidator, WalkForwardReport
from hitl.setup_registry import setup_registry

CACHE_DIR = BASE_DIR / "backtest_results" / "cache"
OUTPUT_DIR = BASE_DIR / "backtest_results" / "quant_discovery"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


DATA_FILE_MAP = {
    "NQ": "NQ_M5_2026.parquet",
    "BTCUSD": "BTCUSD_M5_2026.parquet",
    "XAUUSD": "XAUUSD_M5_2026.parquet",
    "GBPUSD": "GBPUSD_M5_2026.parquet",
    "SPX": "SPX_M5_2026.parquet",
    "YM": "YM_M5_2026.parquet",
}


def load_cached_data(symbol: str) -> pd.DataFrame:
    sym = symbol.upper()
    filename = DATA_FILE_MAP.get(sym)
    if not filename:
        # Try generic search
        for k, f in DATA_FILE_MAP.items():
            if k in sym:
                filename = f
                break
    if not filename:
        raise FileNotFoundError(f"No cached parquet file found for symbol {symbol}")

    filepath = CACHE_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"Parquet file not found at {filepath}")

    df = pd.read_parquet(filepath)
    # Sort chronologically and drop duplicates
    df = df.sort_values("time").drop_duplicates(subset=["time"]).reset_index(drop=True)
    return df


def run_discovery_pipeline(
    symbols: List[str],
    population_size: int = 50,
    generations: int = 10,
    is_ratio: float = 0.60,
    purge_bars: int = 50,
    export_schedule: bool = False
) -> Dict[str, Any]:
    """
    Runs the complete autonomous machine-discovery quant generation pipeline.
    """
    print("=" * 100)
    print("🤖 TRADINGGUARD AUTONOMOUS MACHINE-DISCOVERED QUANT ALPHA GENERATION ENGINE")
    print("Zero Human Narrative | Pure Mathematical State Space | Strict Walk-Forward Validation")
    print("=" * 100)

    total_start = time.time()
    state_space_engine = MathematicalStateSpace()
    discovery_summary = {}
    all_ratified_rules = []

    for sym in symbols:
        print(f"\n[{sym}] Step 1: Loading raw broker bar series...")
        raw_df = load_cached_data(sym)
        print(f"   Loaded {len(raw_df)} bars. Timespan: {raw_df['time'].iloc[0]} -> {raw_df['time'].iloc[-1]}")

        print(f"[{sym}] Step 2: Transforming into pure mathematical state space (zero narrative bias)...")
        t0 = time.time()
        state_df = state_space_engine.transform(raw_df)
        print(f"   State space generated in {time.time() - t0:.3f}s. Columns: {len(state_df.columns)}")

        print(f"[{sym}] Step 3: Enforcing chronological In-Sample vs. Out-of-Sample split...")
        validator = WalkForwardValidator(symbol=sym)
        df_is, df_oos = validator.split_data(state_df, is_ratio=is_ratio, purge_bars=purge_bars)
        print(f"   In-Sample (IS)  : {len(df_is)} bars ({is_ratio*100:.0f}%)")
        print(f"   Purge Buffer    : {purge_bars} bars")
        print(f"   Out-of-Sample   : {len(df_oos)} bars ({(1.0 - is_ratio)*100:.0f}%)")

        print(f"[{sym}] Step 4: Executing autonomous genetic rule induction on In-Sample space...")
        evo_cfg = EvolutionConfig(
            population_size=population_size,
            generations=generations,
            min_trades_threshold=12,
            random_seed=42 + len(sym)
        )
        evo_engine = QuantEvolutionEngine(symbol=sym, state_df=df_is, config=evo_cfg)
        discovered_candidates = evo_engine.run_evolution(verbose=True)

        print(f"\n[{sym}] Step 5: Applying strict Walk-Forward Out-of-Sample cross-validation gates...")
        ratified_rules = []
        rejected_reports = []

        # Evaluate top 10 unique candidates on Out-of-Sample
        for rank, (cand_rule, is_res, fitness) in enumerate(discovered_candidates[:10]):
            report = validator.validate_rule(cand_rule, df_is, df_oos)

            status_icon = "✅ RATIFIED" if report.verdict == "RATIFIED" else "❌ REJECTED"
            print(f"   Candidate #{rank+1} [{cand_rule.rule_id}]: {status_icon}")
            print(f"      Formula : {cand_rule.to_formula_str()}")
            print(
                f"      IS  Perf: Trades {report.is_result.total_fills:2d} | "
                f"WR {report.is_result.win_rate:4.1f}% | "
                f"Net {report.is_result.net_r:+5.1f}R | "
                f"PF {report.is_result.profit_factor:4.2f} | "
                f"Sharpe {report.is_result.sharpe_ratio:4.2f}"
            )
            print(
                f"      OOS Perf: Trades {report.oos_result.total_fills:2d} | "
                f"WR {report.oos_result.win_rate:4.1f}% | "
                f"Net {report.oos_result.net_r:+5.1f}R | "
                f"PF {report.oos_result.profit_factor:4.2f} | "
                f"Sharpe {report.oos_result.sharpe_ratio:4.2f}"
            )
            print(
                f"      Degradation Ratio: {report.degradation_ratio_pf:.2f} | "
                f"Drawdown Expansion: {report.drawdown_expansion_ratio:.2f}x"
            )

            if report.verdict == "RATIFIED":
                ratified_rules.append((cand_rule, report))
            else:
                print(f"      Rejection Causes: {'; '.join(report.rejection_reasons)}")
                rejected_reports.append(report)

        print(f"\n[{sym}] Results: {len(ratified_rules)} Ratified | {len(rejected_reports)} Rejected for Overfitting")

        # Step 6: Cross-Asset Stress Testing & Transferability
        cross_asset_targets = {
            "NQ": ["SPX", "YM"],
            "BTCUSD": ["NQ"],
            "XAUUSD": ["GBPUSD"],
            "GBPUSD": ["XAUUSD"],
        }.get(sym, [])

        cross_asset_audits = {}
        if ratified_rules and cross_asset_targets:
            print(f"\n[{sym}] Step 6: Executing cross-asset structural transferability audit...")
            for target_sym in cross_asset_targets:
                try:
                    target_raw = load_cached_data(target_sym)
                    target_state = state_space_engine.transform(target_raw)
                    for rule, _ in ratified_rules:
                        target_res = validator.evaluate_cross_asset(rule, target_sym, target_state)
                        status_str = "PASS (+Alpha)" if target_res.net_r > 0 else "FAIL (-Alpha)"
                        print(
                            f"   Transfer {rule.rule_id} -> {target_sym}: {status_str} | "
                            f"Trades: {target_res.total_fills} | "
                            f"WR: {target_res.win_rate:.1f}% | "
                            f"PF: {target_res.profit_factor:.2f} | "
                            f"Net R: {target_res.net_r:+.2f}R"
                        )
                        cross_asset_audits.setdefault(rule.rule_id, {})[target_sym] = {
                            "trades": target_res.total_fills,
                            "win_rate": target_res.win_rate,
                            "profit_factor": target_res.profit_factor,
                            "net_r": target_res.net_r,
                            "sharpe": target_res.sharpe_ratio
                        }
                except Exception as e:
                    print(f"   Cross-asset evaluation on {target_sym} skipped: {e}")

        # Save symbol results
        sym_dir = OUTPUT_DIR / sym.lower()
        sym_dir.mkdir(parents=True, exist_ok=True)

        ratified_data = []
        for rule, rep in ratified_rules:
            all_ratified_rules.append((sym, rule, rep))
            # Register in TradingGuard Setup Registry
            archetype_id = f"SETUP-QUANT-{sym}-{rule.rule_id}"
            transfer_info = cross_asset_audits.get(rule.rule_id, {})
            setup_registry.ratify_archetype(
                archetype_id=archetype_id,
                vetting_verdict="PASSED_WALK_FORWARD_CROSS_VALIDATION",
                ratified_criteria={
                    "name": f"Autonomous Machine Quant Rule ({sym} {rule.direction})",
                    "category": "Machine-Discovered Quant",
                    "description": f"Autonomous pure mathematical state-space model: {rule.to_formula_str()}",
                    "entry_trigger": rule.to_formula_str(),
                    "invalidation_anchor": f"{rule.sl_atr_mult}x ATR dynamic trailing/stop",
                    "min_rr": f"1:{rule.tp_atr_mult / rule.sl_atr_mult:.1f}",
                    "is_profit_factor": rep.is_result.profit_factor,
                    "oos_profit_factor": rep.oos_result.profit_factor,
                    "oos_sharpe": rep.oos_result.sharpe_ratio,
                    "degradation_ratio": rep.degradation_ratio_pf,
                    "cross_asset_stress": transfer_info
                },
                auditor_notes=f"Walk-forward verified on {len(df_oos)} OOS bars with zero narrative bias."
            )

            ratified_data.append({
                "rule": rule.to_dict(),
                "walk_forward_report": rep.to_dict(),
                "cross_asset_stress": transfer_info
            })

        with open(sym_dir / "ratified_quant_strategies.json", "w", encoding="utf-8") as f:
            json.dump(ratified_data, f, indent=2)

        discovery_summary[sym] = {
            "total_bars": len(raw_df),
            "is_bars": len(df_is),
            "oos_bars": len(df_oos),
            "candidates_tested": min(10, len(discovered_candidates)),
            "ratified_count": len(ratified_rules),
            "ratified_rules": [r[0].to_formula_str() for r in ratified_rules],
            "cross_asset_audits": cross_asset_audits
        }

    # Step 7: Export execution schedule to orders_schedule.csv
    if export_schedule and all_ratified_rules:
        print("\nStep 7: Exporting ratified out-of-sample trades to orders_schedule.csv...")
        schedule_trades = []
        for s_sym, rule, rep in all_ratified_rules:
            for tr in rep.oos_result.trades:
                schedule_trades.append({
                    "symbol": s_sym,
                    "entry_time": tr.entry_time,
                    "direction": tr.direction,
                    "entry_price": tr.entry_price,
                    "sl_price": tr.sl_price,
                    "tp_price": tr.tp_price,
                    "ttl_bars": rule.ttl_bars
                })

        if schedule_trades:
            lines = ["ID,Symbol,Type,TriggerTime,Entry,SL,TP,Lot,TTL\n"]
            for idx, t in enumerate(schedule_trades):
                s_name = t["symbol"]
                is_fx = "EUR" in s_name or "GBP" in s_name
                d = 5 if is_fx else 2
                e_p = round(float(t["entry_price"]), d)
                sl_p = round(float(t["sl_price"]), d)
                tp_p = round(float(t["tp_price"]), d)
                o_type = "BUY" if t["direction"].upper() == "BUY" else "SELL"
                import datetime
                dt = datetime.datetime.fromtimestamp(t["entry_time"], tz=datetime.timezone.utc)
                t_str = dt.strftime("%Y.%m.%d %H:%M:%S")
                o_id = f"ORD-QUANT-{s_name[:3]}-{t['entry_time']}-{idx+1:03d}"
                lines.append(f"{o_id},{s_name},{o_type},{t_str},{e_p},{sl_p},{tp_p},0.01,{t['ttl_bars']}\n")

            out_csv = OUTPUT_DIR / "orders_schedule.csv"
            with open(out_csv, "w", encoding="utf-8") as f:
                f.writelines(lines)
            print(f"   Exported {len(schedule_trades)} trades to {out_csv}")

            # Also mirror to MT5 Files directories if available
            common_dir = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\Common\Files")
            terminal_dir = Path(r"C:\Users\Javad\AppData\Roaming\MetaQuotes\Terminal\065434634B76DD288A1DDF20131E8DDB\MQL5\Files")
            for m_dir in [common_dir, terminal_dir]:
                if m_dir.exists():
                    try:
                        with open(m_dir / "orders_schedule.csv", "w", encoding="utf-8") as f:
                            f.writelines(lines)
                        print(f"   Mirrored to MT5 directory: {m_dir / 'orders_schedule.csv'}")
                    except Exception as e:
                        print(f"   Note: Could not mirror to {m_dir}: {e}")

    elapsed = time.time() - total_start
    print("\n" + "=" * 100)
    print(f"🏁 AUTONOMOUS QUANT ALPHA DISCOVERY COMPLETE in {elapsed:.2f}s")
    print(json.dumps(discovery_summary, indent=2))
    print("=" * 100)

    summary_file = OUTPUT_DIR / "quant_discovery_master_summary.json"
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump(discovery_summary, f, indent=2)

    return discovery_summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradingGuard Autonomous Quant Engine")
    parser.add_argument("--symbols", nargs="+", default=["NQ", "BTCUSD", "XAUUSD", "GBPUSD"], help="Symbols to mine")
    parser.add_argument("--population", type=int, default=40, help="Genetic population size")
    parser.add_argument("--generations", type=int, default=8, help="Number of genetic generations")
    parser.add_argument("--is-ratio", type=float, default=0.60, help="In-Sample ratio")
    parser.add_argument("--export-schedule", action="store_true", default=True, help="Export trades to orders_schedule.csv")
    args = parser.parse_args()

    run_discovery_pipeline(
        symbols=args.symbols,
        population_size=args.population,
        generations=args.generations,
        is_ratio=args.is_ratio,
        export_schedule=args.export_schedule
    )
