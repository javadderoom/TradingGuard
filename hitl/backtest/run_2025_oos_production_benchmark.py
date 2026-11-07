"""
TradingGuard HITL - 2025 Out-of-Sample Production Portfolio Benchmark
Evaluates Subquadratic SubQ Snap (subq-snap-1.1) on authentic broker historical data from 2025 (H2 OOS period).
Tests whether SubQ Snap's discipline and archetype-aware routing hold up in a completely untouched market regime.
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
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.mtf_structure import analyze_mtf_state
from hitl.setup_registry import setup_registry

CACHE_DIR = Path("backtest_results/cache")
OUT_DIR = Path("backtest_results/snap_evaluations")
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_LEDGER_CSV = OUT_DIR / "subq_snap_2025_oos_portfolio_ledger.csv"
OUT_SUMMARY_JSON = OUT_DIR / "subq_snap_2025_oos_portfolio_summary.json"

TZ_UTC = ZoneInfo("UTC")


def get_season_name(dt: datetime.datetime) -> str:
    m = dt.month
    if m in (12, 1, 2): return "Winter"
    elif m in (3, 4, 5): return "Spring"
    elif m in (6, 7, 8): return "Summer"
    elif m in (9, 10, 11): return "Autumn"
    return "Unknown"


def simulate_m5_forward_execution(
    entry: float,
    sl: float,
    direction: str,
    target_rr: float,
    be_rr: float,
    forward_m5: List[Dict[str, Any]],
    spread: float
) -> Dict[str, Any]:
    risk = abs(entry - sl)
    if risk <= 0:
        return {'status': 'EXPIRED', 'net_r': 0.0, 'max_mfe_r': 0.0, 'max_mae_r': 0.0, 'held_minutes': 0}

    target_price = entry + (target_rr * risk) if direction == "LONG" else entry - (target_rr * risk)
    cur_sl = sl
    be_active = False
    max_mfe_r = 0.0
    max_mae_r = 0.0
    held_minutes = 0

    status = "EXPIRED"
    net_r = 0.0

    for idx, b in enumerate(forward_m5):
        held_minutes = (idx + 1) * 5
        h = b['high']
        l = b['low']

        if direction == "LONG":
            cur_mfe = (h - entry - spread) / risk
            cur_mae = (entry - l + spread) / risk
        else:
            cur_mfe = (entry - l - spread) / risk
            cur_mae = (h - entry + spread) / risk

        if cur_mfe > max_mfe_r: max_mfe_r = cur_mfe
        if cur_mae > max_mae_r: max_mae_r = cur_mae

        # Breakeven ratchet
        if be_rr is not None and not be_active and max_mfe_r >= be_rr:
            be_active = True
            cur_sl = entry + (spread if direction == "LONG" else -spread)

        # Conservative SL-first collision check
        if direction == "LONG":
            hit_sl = l <= cur_sl
            hit_tp = h >= target_price
            if hit_sl and hit_tp:
                # Conservative SL-first priority
                status = "BREAKEVEN" if be_active else "LOSS"
                net_r = 0.0 if be_active else -1.0
                break
            elif hit_sl:
                status = "BREAKEVEN" if be_active else "LOSS"
                net_r = 0.0 if be_active else -1.0
                break
            elif hit_tp:
                status = "WIN"
                net_r = target_rr
                break
        else:
            hit_sl = h >= cur_sl
            hit_tp = l <= target_price
            if hit_sl and hit_tp:
                status = "BREAKEVEN" if be_active else "LOSS"
                net_r = 0.0 if be_active else -1.0
                break
            elif hit_sl:
                status = "BREAKEVEN" if be_active else "LOSS"
                net_r = 0.0 if be_active else -1.0
                break
            elif hit_tp:
                status = "WIN"
                net_r = target_rr
                break

        if held_minutes >= 480: # 8 hour session expiry
            if be_active:
                status = "BREAKEVEN"
                net_r = 0.0
            else:
                status = "LOSS" if (cur_mae >= 1.0) else "EXPIRED"
                net_r = -1.0 if status == "LOSS" else 0.0
            break

    return {
        'status': status,
        'net_r': round(net_r, 2),
        'max_mfe_r': round(max_mfe_r, 2),
        'max_mae_r': round(max_mae_r, 2),
        'held_minutes': held_minutes
    }


def run_2025_oos_benchmark():
    print("=" * 110)
    print("🚀 TRADINGGUARD - 2025 OUT-OF-SAMPLE (OOS) SUBQ SNAP BENCHMARK")
    print("Evaluating genuine generalization on completely untouched 2025 historical broker bars.")
    print("=" * 110)

    snap_engine = SnapDecisionEngine()
    if not snap_engine.api_key:
        raise ValueError("SNAP_API_KEY is not set!")

    symbols = ["XAUUSD_o", "GBPUSD_o"]
    all_trade_records = []
    sessions = [
        ("London_Post_Open", 10),
        ("NY_Pre_Open", 11),
        ("NY_Post_Open", 14),
        ("NY_Silver_Bullet", 15)
    ]

    # Check for existing ledger to resume
    existing_ledger = {}
    if OUT_LEDGER_CSV.exists():
        try:
            df_old = pd.read_csv(OUT_LEDGER_CSV)
            for _, r in df_old.iterrows():
                key = (str(r['date']), str(r['symbol']), str(r['session_hour']), str(r['archetype_id']))
                existing_ledger[key] = r.to_dict()
            print(f"🔄 Resuming from existing ledger: {len(existing_ledger)} trades already evaluated.")
        except Exception as e:
            pass

    for sym in symbols:
        clean_sym = "XAUUSD" if "XAU" in sym else "GBPUSD"
        is_fx = "GBP" in sym

        m5_file = CACHE_DIR / f"M5_{sym}_2025.parquet"
        h1_file = CACHE_DIR / f"H1_{sym}_2025.parquet"
        d1_file = CACHE_DIR / f"D1_{sym}_2025.parquet"

        if not m5_file.exists() or not h1_file.exists() or not d1_file.exists():
            print(f"Missing cache files for {sym}")
            continue

        print(f"\n📂 Loading 2025 data for {sym}...")
        df_m5 = pd.read_parquet(m5_file)
        df_h1 = pd.read_parquet(h1_file)
        df_d1 = pd.read_parquet(d1_file)

        bars_m5 = []
        for dt, row in df_m5.iterrows():
            bars_m5.append({'time': int(row['time']), 'dt': dt.to_pydatetime(), 'open': float(row['open']), 'high': float(row['high']), 'low': float(row['low']), 'close': float(row['close']), 'tick_volume': int(row['tick_volume'])})
        bars_h1 = []
        for dt, row in df_h1.iterrows():
            bars_h1.append({'time': int(row['time']), 'dt': dt.to_pydatetime(), 'open': float(row['open']), 'high': float(row['high']), 'low': float(row['low']), 'close': float(row['close']), 'tick_volume': int(row['tick_volume'])})
        bars_d1 = []
        for dt, row in df_d1.iterrows():
            bars_d1.append({'time': int(row['time']), 'dt': dt.to_pydatetime(), 'open': float(row['open']), 'high': float(row['high']), 'low': float(row['low']), 'close': float(row['close']), 'tick_volume': int(row['tick_volume'])})

        dates = sorted(list(set(b['dt'].date() for b in bars_m5)))
        print(f"🔍 Screening 2025 sessions for {sym} across {len(dates)} trading days...")

        for day_idx in range(10, len(dates)):
            day_date = dates[day_idx]
            if day_date.weekday() in (5, 6): continue

            for sess_label, sess_hour in sessions:
                if is_fx and sess_label != "London_Post_Open":
                    continue # Cable trades London only

                m5_candidates = [i for i, b in enumerate(bars_m5) if b['dt'].date() == day_date and b['dt'].hour == sess_hour]
                if not m5_candidates: continue
                m5_idx = m5_candidates[0]
                curr_b = bars_m5[m5_idx]

                hist_m5 = bars_m5[max(0, m5_idx - 120) : m5_idx + 1]
                hist_h1 = [b for b in bars_h1 if b['time'] <= curr_b['time']][-60:]
                hist_d1 = [b for b in bars_d1 if b['time'] <= curr_b['time']][-30:]

                # Screen ICT candidate
                res = screen_ict_session(hist_m5, hist_h1, clean_sym, sess_hour, bars_1d=hist_d1)
                if not res.get("has_setup") or res.get("setup_type") == "NONE":
                    continue

                arch_id = res.get("archetype_id")
                if not setup_registry.is_archetype_ratified(arch_id):
                    continue

                # Asset specific bans
                if is_fx and arch_id in ("SETUP-ARCH-009", "SETUP-ARCH-012", "SETUP-ARCH-014"):
                    continue
                if not is_fx and arch_id in ("SETUP-ARCH-002", "SETUP-ARCH-009", "SETUP-ARCH-013"):
                    continue

                trade_key = (str(day_date), sym, str(sess_hour), str(arch_id))
                if trade_key in existing_ledger:
                    all_trade_records.append(existing_ledger[trade_key])
                    continue

                setup_type = res.get("setup_type", "")
                direction = "LONG" if "BULLISH" in setup_type else ("SHORT" if "BEARISH" in setup_type else res.get("direction", "LONG"))
                entry_p = float(res.get("entry_ref", res.get("entry_price", curr_b['close'])))
                sl_p = float(res.get("sl_ref", res.get("stop_loss", curr_b['close'])))
                risk_pts = abs(entry_p - sl_p)
                if risk_pts <= 0: continue

                target_rr = 3.5 if not is_fx else 2.5
                be_rr = 1.8 if not is_fx else 1.5
                spread = 0.00015 if is_fx else 0.20

                tp_p = (entry_p + target_rr * risk_pts) if direction == "LONG" else (entry_p - target_rr * risk_pts)

                # Simulate baseline execution forward
                forward_window = bars_m5[m5_idx + 1 : m5_idx + 96]
                if len(forward_window) < 12:
                    continue

                sim = simulate_m5_forward_execution(
                    entry=entry_p,
                    sl=sl_p,
                    direction=direction,
                    target_rr=target_rr,
                    be_rr=be_rr,
                    forward_m5=forward_window,
                    spread=spread
                )

                base_status = sim['status']
                base_net_r = sim['net_r']

                # MTF State
                mtf_state = analyze_mtf_state(hist_d1, hist_h1, hist_m5, symbol=clean_sym)
                quote = {
                    "bid": curr_b['close'],
                    "ask": curr_b['close'] + spread,
                    "spread": spread
                }

                session_lbl = f"{clean_sym}_{sess_label}_{day_date}"
                setup_payload = {
                    "archetype_id": str(arch_id),
                    "setup_type": str(setup_type),
                    "direction": direction,
                    "entry_price": entry_p,
                    "sl_price": sl_p,
                    "target_price": tp_p
                }

                # Evaluate with SubQ Snap
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

                expected_act = "BUY_LIMIT" if direction == "LONG" else "SELL_LIMIT"
                if snap_dec == expected_act:
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

                rec = {
                    'date': str(day_date),
                    'season': get_season_name(curr_b['dt']),
                    'symbol': sym,
                    'clean_symbol': clean_sym,
                    'session': sess_label,
                    'session_hour': sess_hour,
                    'archetype_id': str(arch_id),
                    'direction': direction,
                    'setup_name': str(setup_type),
                    'entry_price': entry_p,
                    'stop_loss': sl_p,
                    'risk_pts': round(risk_pts, 4),
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
                all_trade_records.append(rec)

                print(f"[{len(all_trade_records):03d}] {day_date} | {clean_sym:<8} | {arch_id:<14} | {direction:<5} | Base: {base_status:<8} ({base_net_r:+5.1f}R) | Snap: {snap_dec:<11} ({lat_ms:4.0f}ms) ➔ Gated: {gated_status:<10} ({gated_net_r:+5.1f}R) | {role}")

                if len(all_trade_records) % 10 == 0:
                    pd.DataFrame(all_trade_records).to_csv(OUT_LEDGER_CSV, index=False)

    df_all = pd.DataFrame(all_trade_records)
    df_all.to_csv(OUT_LEDGER_CSV, index=False)
    print(f"\n💾 Saved 2025 OOS benchmark ledger ({len(df_all)} trades) to {OUT_LEDGER_CSV}")

    # Calculate Scorecard
    def _calc_stats(df_sub, prefix='baseline'):
        st_col = f'{prefix}_status'
        r_col = f'{prefix}_net_r'
        total = len(df_sub)
        if total == 0:
            return {'total': 0, 'fills': 0, 'wins': 0, 'losses': 0, 'be': 0, 'expired': 0, 'wr': 0.0, 'net_r': 0.0, 'pf': 0.0}

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
        'total_evaluated': len(df_all),
        'baseline_overall': _calc_stats(df_all, 'baseline'),
        'gated_overall': _calc_stats(df_all, 'gated'),
        'counterfactual_summary': df_all['counterfactual_role'].value_counts().to_dict(),
        'latency_stats': {
            'mean_ms': round(float(df_all['snap_latency_ms'].mean()), 1),
            'median_ms': round(float(df_all['snap_latency_ms'].median()), 1),
            'p90_ms': round(float(df_all['snap_latency_ms'].quantile(0.90)), 1)
        },
        'seasons': {},
        'archetypes': {}
    }

    for s in df_all['season'].unique():
        sub = df_all[df_all['season'] == s]
        summary['seasons'][s] = {
            'baseline': _calc_stats(sub, 'baseline'),
            'gated': _calc_stats(sub, 'gated'),
            'roles': sub['counterfactual_role'].value_counts().to_dict()
        }

    for arch in sorted(df_all['archetype_id'].unique()):
        sub = df_all[df_all['archetype_id'] == arch]
        summary['archetypes'][arch] = {
            'baseline': _calc_stats(sub, 'baseline'),
            'gated': _calc_stats(sub, 'gated'),
            'roles': sub['counterfactual_role'].value_counts().to_dict()
        }

    base_net = summary['baseline_overall']['net_r']
    gated_net = summary['gated_overall']['net_r']
    summary['net_value_added_r'] = round(gated_net - base_net, 2)

    with open(OUT_SUMMARY_JSON, 'w', encoding='utf-8') as f:
        json.dump(summary, f, indent=2)

    print("\n" + "=" * 110)
    print("📊 2025 OUT-OF-SAMPLE SCORECARD:")
    print("=" * 110)
    b_all = summary['baseline_overall']
    g_all = summary['gated_overall']
    print(f"  • 2025 Baseline Screener: {b_all['fills']} fills | {b_all['wins']}W / {b_all['losses']}L / {b_all['be']}BE | WR: {b_all['wr']}% | Net: {b_all['net_r']:+6.1f}R | PF: {b_all['pf']:.2f}")
    print(f"  • 2025 SubQ Snap Gated:   {g_all['fills']} fills | {g_all['wins']}W / {g_all['losses']}L / {g_all['be']}BE | WR: {g_all['wr']}% | Net: {g_all['net_r']:+6.1f}R | PF: {g_all['pf']:.2f}")
    print(f"  • Net Value Added:        {summary['net_value_added_r']:+6.1f}R")


if __name__ == "__main__":
    run_2025_oos_benchmark()
