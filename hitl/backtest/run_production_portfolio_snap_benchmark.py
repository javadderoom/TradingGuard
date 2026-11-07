"""
TradingGuard HITL - SubQ Snap Benchmark on Curated Production Portfolio
Evaluates Subquadratic SubQ Snap (subq-snap-1.1) on the 149 ratified production trades from 2026.
Covers 7 ratified archetypes (ARCH-001, ARCH-002, ARCH-003, ARCH-004, ARCH-010, ARCH-011, ARCH-014)
across all 4 seasons (Winter, Spring, Summer, Autumn) on Gold and Cable.
"""

import os
import sys
import json
import time
import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from typing import Dict, List, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd
import numpy as np

# Enforce UTF-8 on Windows
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from hitl.snap_decision_engine import SnapDecisionEngine
from hitl.backtest.master_production_portfolio_audit import load_microstructure
from hitl.backtest.mtf_structure import analyze_mtf_state

IN_TRADES_CSV = Path("backtest_results/master_portfolio_audit/master_portfolio_trades_2026.csv")
OUT_DIR = Path("backtest_results/snap_evaluations")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LEDGER_CSV = OUT_DIR / "subq_snap_production_portfolio_ledger_archetype_aware_149.csv"
OUT_SUMMARY_JSON = OUT_DIR / "subq_snap_production_portfolio_summary_archetype_aware.json"


def run_production_snap_benchmark(max_evals: Optional[int] = None):
    print("=" * 110)
    print("🚀 TRADINGGUARD - SUBQ SNAP BENCHMARK ON RATIFIED PRODUCTION PORTFOLIO (149 TRADES)")
    print("Evaluates SubQ Snap (subq-snap-1.1) as the intelligent gatekeeper on curated, high-R:R production setups.")
    print("=" * 110)

    if not IN_TRADES_CSV.exists():
        raise FileNotFoundError(f"Input trades file not found: {IN_TRADES_CSV}")

    df_trades = pd.read_csv(IN_TRADES_CSV)
    total_trades = len(df_trades)
    print(f"Loaded {total_trades} production trade records from {IN_TRADES_CSV}")

    snap_engine = SnapDecisionEngine()
    if not snap_engine.api_key:
        raise ValueError("SNAP_API_KEY is not set in environment or .env file!")

    # Check for existing results to resume if interrupted
    existing_ledger = {}
    if OUT_LEDGER_CSV.exists():
        try:
            df_existing = pd.read_csv(OUT_LEDGER_CSV)
            for _, r in df_existing.iterrows():
                key = (str(r['date']), str(r['symbol']), str(r['session_hour']), str(r['archetype_id']))
                existing_ledger[key] = r.to_dict()
            print(f"🔄 Resuming from existing ledger: {len(existing_ledger)} trades already evaluated.")
        except Exception as e:
            print(f"Could not read existing ledger: {e}, starting fresh.")

    # Preload microstructure for both symbols
    micro_cache = {}
    for sym in df_trades['symbol'].unique():
        print(f"\n📂 Preloading microstructure for {sym}...")
        micro_cache[sym] = load_microstructure(sym)

    results = []
    eval_count = 0

    print("\n" + "-" * 110)
    print(f"{'#':<4} | {'Date':<10} | {'Sym':<8} | {'Season':<6} | {'Archetype':<14} | {'Dir':<5} | {'Base Status':<10} | {'Base R':<6} | {'Snap Decision':<12} | {'Lat':<6} | {'Gated Status':<12} | {'Gated R':<7} | {'Role'}")
    print("-" * 110)

    for idx, row in df_trades.iterrows():
        trade_key = (str(row['date']), str(row['symbol']), str(row['session_hour']), str(row['archetype_id']))
        if trade_key in existing_ledger:
            results.append(existing_ledger[trade_key])
            continue

        if max_evals and eval_count >= max_evals:
            print(f"\n[Limit] Reached max evaluations cap ({max_evals}).")
            break

        sym = row['symbol']
        clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
        is_fx = "GBP" in sym or "EUR" in sym

        data = micro_cache[sym]
        bars_m5 = data['m5']
        bars_h1 = data['h1']
        bars_d1 = data['d1']

        row_date = pd.to_datetime(row['date']).date()
        row_hour = int(row['session_hour'])

        # Locate checkpoint M5 bar
        m5_candidates = [i for i, b in enumerate(bars_m5) if b['dt'].date() == row_date and b['dt'].hour == row_hour]
        if not m5_candidates:
            print(f"Warning: could not locate M5 bar for {sym} on {row_date} at hour {row_hour}")
            continue

        m5_idx = m5_candidates[0]
        curr_b = bars_m5[m5_idx]

        # Extract strictly historical bars (zero lookahead)
        hist_m5 = bars_m5[max(0, m5_idx - 120) : m5_idx + 1]
        hist_h1 = [b for b in bars_h1 if b['time'] <= curr_b['time']][-60:]
        hist_d1 = [b for b in bars_d1 if b['time'] <= curr_b['time']][-30:]

        mtf_state = analyze_mtf_state(hist_d1, hist_h1, hist_m5, symbol=clean_sym)

        quote = {
            "bid": curr_b['close'],
            "ask": curr_b['close'] + (0.00015 if is_fx else 0.20),
            "spread": 0.00015 if is_fx else 0.20
        }

        entry_p = float(row['entry_price'])
        sl_p = float(row['stop_loss'])
        risk_pts = float(row['risk_pts'])
        target_rr = float(row['target_rr'])
        direction = str(row['direction'])

        tp_p = (entry_p + target_rr * risk_pts) if direction == "LONG" else (entry_p - target_rr * risk_pts)

        session_lbl = f"{clean_sym}_{row['session']}_{row['date']}"

        setup_payload = {
            "archetype_id": str(row['archetype_id']),
            "setup_type": str(row['setup_name']),
            "direction": direction,
            "entry_price": entry_p,
            "sl_price": sl_p,
            "target_price": tp_p
        }

        t0 = time.perf_counter()
        snap_res = snap_engine.evaluate_candidate(
            symbol=clean_sym,
            session_label=session_lbl,
            screener_setup=setup_payload,
            mtf_state=mtf_state,
            current_quote=quote
        )
        lat_ms = (time.perf_counter() - t0) * 1000.0

        snap_dec = snap_res.get("decision", "STAND_ASIDE")
        snap_conf = snap_res.get("confidence", 0.0)
        probs = snap_res.get("probabilities", {})
        snap_driver = snap_res.get("primary_driver", "NONE")
        snap_tier = snap_res.get("conviction_tier", "NONE")

        base_status = str(row['status'])
        base_net_r = float(row['net_r'])

        # Determine Gated Outcome
        expected_action = "BUY_LIMIT" if direction == "LONG" else "SELL_LIMIT"
        if snap_dec == expected_action:
            gated_status = base_status
            gated_net_r = base_net_r
        else:
            gated_status = "STAND_ASIDE"
            gated_net_r = 0.0

        # Counterfactual role
        if snap_dec == "STAND_ASIDE":
            if base_status == "LOSS":
                role = "PROTECTIVE_VETO"
            elif base_status == "WIN":
                role = "DAMAGING_STAND_ASIDE"
            elif base_status == "BREAKEVEN":
                role = "NEUTRAL_SCRATCH_VETO"
            else:
                role = "AVOIDED_EXPIRED"
        else:
            if base_status == "WIN":
                role = "APPROVED_WIN"
            elif base_status == "LOSS":
                role = "APPROVED_LOSS"
            elif base_status == "BREAKEVEN":
                role = "APPROVED_BREAKEVEN"
            else:
                role = "APPROVED_EXPIRED"

        eval_count += 1
        rec = {
            'date': str(row['date']),
            'season': str(row['season']),
            'symbol': sym,
            'clean_symbol': clean_sym,
            'session': str(row['session']),
            'session_hour': row_hour,
            'archetype_id': str(row['archetype_id']),
            'direction': direction,
            'setup_name': str(row['setup_name']),
            'entry_price': entry_p,
            'stop_loss': sl_p,
            'risk_pts': risk_pts,
            'target_rr': target_rr,
            'baseline_status': base_status,
            'baseline_net_r': base_net_r,
            'snap_decision': snap_dec,
            'snap_confidence': snap_conf,
            'snap_prob_buy': probs.get('BUY_LIMIT', 0.0),
            'snap_prob_sell': probs.get('SELL_LIMIT', 0.0),
            'snap_prob_stand': probs.get('STAND_ASIDE', 0.0),
            'snap_driver': snap_driver,
            'snap_tier': snap_tier,
            'snap_latency_ms': round(lat_ms, 1),
            'gated_status': gated_status,
            'gated_net_r': gated_net_r,
            'counterfactual_role': role
        }
        results.append(rec)

        print(f"[{eval_count:03d}] | {row['date']} | {clean_sym:<8} | {row['season']:<6} | {row['archetype_id']:<14} | {direction:<5} | {base_status:<10} | {base_net_r:+5.1f}R | {snap_dec:<12} | {lat_ms:4.0f}ms | {gated_status:<12} | {gated_net_r:+6.1f}R | {role}")

        # Periodically flush to disk
        if eval_count % 10 == 0 or idx == len(df_trades) - 1:
            pd.DataFrame(results).to_csv(OUT_LEDGER_CSV, index=False)

    df_res = pd.DataFrame(results)
    df_res.to_csv(OUT_LEDGER_CSV, index=False)
    print(f"\n💾 Saved full production benchmark ledger to {OUT_LEDGER_CSV}")

    # =========================================================================
    # MULTI-SEASONAL SYNTHESIS & METRICS
    # =========================================================================
    print("\n" + "=" * 110)
    print("📊 MASTER SCORECARD: BASELINE PORTFOLIO VS. SUBQ SNAP GATED PORTFOLIO")
    print("=" * 110)

    def _calc_metrics(df_sub, prefix='baseline'):
        st_col = f'{prefix}_status'
        r_col = f'{prefix}_net_r'
        total = len(df_sub)
        if total == 0:
            return {'fills': 0, 'wins': 0, 'losses': 0, 'be': 0, 'expired': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}

        # Filter to active trades (exclude STAND_ASIDE if evaluating gated)
        active = df_sub[df_sub[st_col] != 'STAND_ASIDE'] if prefix == 'gated' else df_sub
        fills = len(active)
        wins = len(active[active[st_col] == 'WIN'])
        losses = len(active[active[st_col] == 'LOSS'])
        be = len(active[active[st_col] == 'BREAKEVEN'])
        exp = len(active[active[st_col] == 'EXPIRED'])
        closed = wins + losses + be

        wr = (wins / closed * 100.0) if closed > 0 else 0.0
        gw = active[active[r_col] > 0][r_col].sum()
        gl = abs(active[active[r_col] < 0][r_col].sum())
        pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
        net_r = active[r_col].sum()

        return {
            'total_evaluated': total,
            'fills': fills,
            'wins': wins,
            'losses': losses,
            'be': be,
            'expired': exp,
            'closed': closed,
            'wr': round(wr, 1),
            'gross_win_r': round(gw, 2),
            'gross_loss_r': round(gl, 2),
            'net_r': round(net_r, 2),
            'pf': round(pf, 2)
        }

    summary = {
        'total_evaluated': len(df_res),
        'baseline_overall': _calc_metrics(df_res, 'baseline'),
        'gated_overall': _calc_metrics(df_res, 'gated'),
        'counterfactual_summary': df_res['counterfactual_role'].value_counts().to_dict(),
        'latency_stats': {
            'mean_ms': round(float(df_res['snap_latency_ms'].mean()), 1),
            'median_ms': round(float(df_res['snap_latency_ms'].median()), 1),
            'p90_ms': round(float(df_res['snap_latency_ms'].quantile(0.90)), 1),
            'p99_ms': round(float(df_res['snap_latency_ms'].quantile(0.99)), 1)
        },
        'seasons': {},
        'archetypes': {}
    }

    # Seasonal breakdown
    for s in ["Winter", "Spring", "Summer", "Autumn"]:
        sub = df_res[df_res['season'] == s]
        summary['seasons'][s] = {
            'baseline': _calc_metrics(sub, 'baseline'),
            'gated': _calc_metrics(sub, 'gated'),
            'roles': sub['counterfactual_role'].value_counts().to_dict()
        }

    # Archetype breakdown
    for arch in sorted(df_res['archetype_id'].unique()):
        sub = df_res[df_res['archetype_id'] == arch]
        summary['archetypes'][arch] = {
            'baseline': _calc_metrics(sub, 'baseline'),
            'gated': _calc_metrics(sub, 'gated'),
            'roles': sub['counterfactual_role'].value_counts().to_dict()
        }

    # Net Value Added by SubQ Snap
    base_net = summary['baseline_overall']['net_r']
    gated_net = summary['gated_overall']['net_r']
    net_value_r = gated_net - base_net
    summary['net_value_added_r'] = round(net_value_r, 2)

    with open(OUT_SUMMARY_JSON, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)
    print(f"🎉 Summary JSON saved to: {OUT_SUMMARY_JSON}")

    # Console display
    b_all = summary['baseline_overall']
    g_all = summary['gated_overall']
    print(f"\nTOTAL PORTFOLIO COMPARISON ({len(df_res)} TRADES):")
    print(f"  • Baseline Screener: {b_all['fills']} fills | {b_all['wins']}W / {b_all['losses']}L / {b_all['be']}BE | WR: {b_all['wr']}% | Net: {b_all['net_r']:+6.1f}R | PF: {b_all['pf']:.2f}")
    print(f"  • SubQ Snap Gated:   {g_all['fills']} fills | {g_all['wins']}W / {g_all['losses']}L / {g_all['be']}BE | WR: {g_all['wr']}% | Net: {g_all['net_r']:+6.1f}R | PF: {g_all['pf']:.2f}")
    print(f"  • Net Value Added:   {net_value_r:+6.1f}R by SubQ Snap filtering")

    print("\nCOUNTERFACTUAL ROLES:")
    for role, cnt in summary['counterfactual_summary'].items():
        print(f"  - {role:<24}: {cnt:3d} ({cnt/len(df_res)*100:.1f}%)")

    print("\nSEASONAL PROGRESSION (Net R):")
    for s in ["Winter", "Spring", "Summer", "Autumn"]:
        b_s = summary['seasons'][s]['baseline']
        g_s = summary['seasons'][s]['gated']
        diff = g_s['net_r'] - b_s['net_r']
        print(f"  - {s:<6}: Baseline {b_s['net_r']:+5.1f}R ({b_s['wr']}%) ➔ Gated {g_s['net_r']:+5.1f}R ({g_s['wr']}%) | Diff: {diff:+5.1f}R")

    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-evals", type=int, default=None)
    args = parser.parse_args()
    run_production_snap_benchmark(max_evals=args.max_evals)
