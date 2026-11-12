"""
TradingGuard HITL - Visual Backtest Replay Data Compiler
Generates complete bar-by-bar M5 & M1 candlesticks, true UTC/Tehran/MT5 timestamps,
institutional ICT session bounds, structural detections, screener diagnostics ("Thoughts"),
and trade execution simulation into a self-contained interactive HTML viewer.
"""

import sys
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from zoneinfo import ZoneInfo
from bisect import bisect_right
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from hitl.backtest.fast_screener import (
    screen_ict_session,
    detect_breaker_and_mss,
    detect_fvg_5m,
    get_session_times_for_date,
)
from hitl.backtest.mtf_structure import analyze_mtf_state
from hitl.screener_gate import tehran_hour_from_bar_time

CACHE_FILE = PROJECT_ROOT / "backtest_results" / "cache" / "M1_XAUUSD_o_2026.parquet"
TEMPLATE_FILE = PROJECT_ROOT / "hitl" / "backtest" / "templates" / "visual_replayer_template.html"
OUT_DIR = PROJECT_ROOT / "backtest_results" / "visual_replay"
OUT_DIR.mkdir(parents=True, exist_ok=True)
ARTIFACT_HTML = Path(r"C:\Users\Javad\.gemini\antigravity\brain\9458aaca-f0fa-43e6-95ae-d440f3eb9e63\visual_backtest_replayer.html")

TZ_EU_ATHENS = ZoneInfo("Europe/Athens")  # Standard MT5 EET/EEST DST rules (UTC+2 winter, UTC+3 summer)
TZ_TEHRAN = ZoneInfo("Asia/Tehran")
TZ_UTC = datetime.timezone.utc


def server_epoch_to_zones(srv_epoch: int) -> Dict[str, Any]:
    """
    MT5 broker timestamps represent EET (UTC+2) / EEST (UTC+3) clock time encoded as integer epoch.
    Convert cleanly to Server String, True UTC Epoch/String, and True Tehran String.
    """
    srv_naive = datetime.datetime.fromtimestamp(int(srv_epoch), tz=TZ_UTC).replace(tzinfo=None)
    # Determine EET/EEST offset for that server wall-clock date
    srv_aware = srv_naive.replace(tzinfo=TZ_EU_ATHENS)
    offset_sec = int(srv_aware.utcoffset().total_seconds())
    utc_dt = srv_aware.astimezone(TZ_UTC)
    teh_dt = srv_aware.astimezone(TZ_TEHRAN)
    return {
        "srv_str": srv_naive.strftime("%H:%M"),
        "utc_str": utc_dt.strftime("%H:%M"),
        "tehran_str": teh_dt.strftime("%H:%M"),
        "utc_epoch": int(utc_dt.timestamp()),
        "utc_dt": utc_dt,
        "teh_dt": teh_dt,
        "offset_sec": offset_sec,
    }


def refresh_today_mt5_cache(df_cache: pd.DataFrame) -> pd.DataFrame:
    """Pulls any newer M1 bars from MT5 if running live and appends them cleanly."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return df_cache
        sym = "XAUUSD_o" if mt5.symbol_info("XAUUSD_o") else "XAUUSD"
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M1, 0, 2000)
        mt5.shutdown()
        if rates is None or len(rates) == 0:
            return df_cache
        df_new = pd.DataFrame(rates)[["time", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]]
        df_merged = pd.concat([df_cache, df_new], ignore_index=True)
        df_merged = df_merged.drop_duplicates(subset=["time"]).sort_values("time").reset_index(drop=True)
        return df_merged
    except Exception as e:
        print(f"⚠️ MT5 live pull skipped: {e}")
        return df_cache


def compile_visual_replay(target_dates: List[str], symbol: str = "XAUUSD_o", refresh_live: bool = True) -> Path:
    print("=" * 85)
    print(f"🎬 COMPILING VISUAL BACKTEST REPLAYER FOR {len(target_dates)} DATES: {', '.join(target_dates)}")
    print("=" * 85)

    df_raw = pd.read_parquet(CACHE_FILE)
    if refresh_live:
        df_raw = refresh_today_mt5_cache(df_raw)

    df_raw["dt"] = pd.to_datetime(df_raw["time"], unit="s", utc=True)
    df_bars = df_raw.set_index("dt").sort_index()

    def _resample(rule: str):
        r = df_bars["close"].resample(rule).ohlc().dropna()
        r["open"] = df_bars["open"].resample(rule).first()
        r["high"] = df_bars["high"].resample(rule).max()
        r["low"] = df_bars["low"].resample(rule).min()
        r["close"] = df_bars["close"].resample(rule).last()
        out = []
        for idx, row in r.iterrows():
            ep = int(idx.timestamp())
            out.append({
                "time": ep,
                "dt": idx.to_pydatetime(),
                "open": round(float(row["open"]), 2),
                "high": round(float(row["high"]), 2),
                "low": round(float(row["low"]), 2),
                "close": round(float(row["close"]), 2),
            })
        out.sort(key=lambda x: x["time"])
        return out

    bars_m1_all = [
        {
            "time": int(idx.timestamp()),
            "dt": idx.to_pydatetime(),
            "open": round(float(row["open"]), 2),
            "high": round(float(row["high"]), 2),
            "low": round(float(row["low"]), 2),
            "close": round(float(row["close"]), 2),
        }
        for idx, row in df_bars.iterrows()
    ]
    bars_m5_all = _resample("5min")
    bars_h1_all = _resample("60min")
    bars_d1_all = _resample("1D")

    m5_times = [b["time"] for b in bars_m5_all]
    h1_times = [b["time"] for b in bars_h1_all]
    d1_times = [b["time"] for b in bars_d1_all]
    m1_map = {b["time"]: i for i, b in enumerate(bars_m1_all)}

    replay_dataset: Dict[str, Any] = {}
    spread = 0.20

    for d_str in target_dates:
        d_date = datetime.date.fromisoformat(d_str)
        # Include M5 bars for this date (in server time)
        day_m5_indices = [i for i, b in enumerate(bars_m5_all) if b["dt"].date() == d_date]
        day_m1_indices = [i for i, b in enumerate(bars_m1_all) if b["dt"].date() == d_date]

        if len(day_m5_indices) < 20:
            print(f"⚠️ Skipping {d_str}: insufficient bars ({len(day_m5_indices)})")
            continue

        # Format bars with full multi-timezone labels
        day_m5_formatted = []
        for idx in day_m5_indices:
            b = bars_m5_all[idx]
            z = server_epoch_to_zones(b["time"])
            day_m5_formatted.append({
                "time": b["time"],
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "srv_str": z["srv_str"],
                "utc_str": z["utc_str"],
                "tehran_str": z["tehran_str"],
            })

        day_m1_formatted = []
        for idx in day_m1_indices:
            b = bars_m1_all[idx]
            z = server_epoch_to_zones(b["time"])
            day_m1_formatted.append({
                "time": b["time"],
                "open": b["open"],
                "high": b["high"],
                "low": b["low"],
                "close": b["close"],
                "srv_str": z["srv_str"],
                "utc_str": z["utc_str"],
                "tehran_str": z["tehran_str"],
            })

        # Compute dynamic session killzones (convert true UTC killzones back into server-epoch boundaries for chart alignment)
        stimes = get_session_times_for_date(d_date)
        sample_z = server_epoch_to_zones(day_m5_formatted[0]["time"])
        srv_off = sample_z["offset_sec"]

        # True UTC sessions mapped to MT5 server epochs
        asian_start_srv = int(datetime.datetime(d_date.year, d_date.month, d_date.day, 0, 0, tzinfo=TZ_UTC).timestamp()) + srv_off
        asian_end_srv = int(datetime.datetime(d_date.year, d_date.month, d_date.day, 7, 0, tzinfo=TZ_UTC).timestamp()) + srv_off

        lon_start_srv = int(stimes["london"]["utc_time"].timestamp()) + srv_off
        lon_end_srv = lon_start_srv + (3 * 3600)

        ny_start_srv = int(stimes["new_york"]["utc_time"].timestamp()) + srv_off
        ny_end_srv = ny_start_srv + (3 * 3600)

        asian_bars = [b for b in day_m5_formatted if asian_start_srv <= b["time"] < asian_end_srv]
        asian_high = max(b["high"] for b in asian_bars) if asian_bars else None
        asian_low = min(b["low"] for b in asian_bars) if asian_bars else None

        diagnostics = []
        events = []
        trades = []
        last_reason = None
        lon_trade_taken = False
        ny_trade_taken = False

        # Walk every M5 bar across the day
        for idx in day_m5_indices:
            curr_b = bars_m5_all[idx]
            bar_time = curr_b["time"]
            z = server_epoch_to_zones(bar_time)

            hist_m5 = bars_m5_all[max(0, idx - 120) : idx + 1]
            h1_idx = bisect_right(h1_times, bar_time)
            hist_h1 = bars_h1_all[max(0, h1_idx - 60) : h1_idx]
            d1_idx = bisect_right(d1_times, bar_time)
            hist_d1 = bars_d1_all[max(0, d1_idx - 15) : d1_idx]

            # Determine true session label from UTC/SessionClock boundaries
            sess_lbl = "Off-Hours / Pre-Market"
            is_active_kz = False
            if asian_start_srv <= bar_time < asian_end_srv:
                sess_lbl = "Asian Range"
            elif lon_start_srv <= bar_time < lon_end_srv:
                sess_lbl = "London Open"
                is_active_kz = True
            elif ny_start_srv <= bar_time < ny_end_srv:
                sess_lbl = "NY Open"
                is_active_kz = True
            elif bar_time >= lon_end_srv and bar_time < ny_start_srv:
                sess_lbl = "London Continuation / NY Pre"

            # Inspect sub-detectors on closed bars for diagnostics panel
            closed_m5 = hist_m5[:-1]
            has_brk, brk_type, brk_price = detect_breaker_and_mss(closed_m5, lookback=24, symbol=symbol) if len(closed_m5) >= 30 else (False, "NONE", 0.0)
            has_fvg, fvg_dir, _, _ = detect_fvg_5m(closed_m5, lookback=12, symbol=symbol) if len(closed_m5) >= 15 else (False, "NONE", 0.0, 0.0)

            recent_closed = closed_m5[-10:] if len(closed_m5) >= 10 else closed_m5
            rec_high = max(b["high"] for b in recent_closed) if recent_closed else 0.0
            rec_low = min(b["low"] for b in recent_closed) if recent_closed else 0.0
            p_high = bool(asian_high and rec_high >= asian_high)
            p_low = bool(asian_low and rec_low <= asian_low)

            mtf_info = {}
            if len(closed_m5) >= 40 and len(hist_h1) >= 10:
                mtf_info = analyze_mtf_state(bars_1d=hist_d1[:-1] if hist_d1 else None, bars_1h=hist_h1[:-1], bars_5m=closed_m5, symbol=symbol)

            if not is_active_kz:
                res = {
                    "has_setup": False,
                    "reason": f"Outside Killzone ({sess_lbl}) — Monitoring liquidity boundaries only.",
                    "setup_type": "STANDBY",
                    "archetype_id": None,
                    "phase": "STANDBY",
                    "mtf_info": mtf_info,
                }
            else:
                # Pass true Tehran hour cleanly to screener
                true_th_hour = z["teh_dt"].hour
                res = screen_ict_session(
                    bars_5m=hist_m5,
                    bars_1h=hist_h1,
                    symbol=symbol,
                    session_hour=true_th_hour,
                    bars_1m=None,
                    bars_1d=hist_d1,
                    closed_bars_only=True,
                )

            has_setup = bool(res.get("has_setup"))
            reason = res.get("reason", "Monitoring")

            diag_entry = {
                "time": bar_time,
                "srv_str": z["srv_str"],
                "utc_str": z["utc_str"],
                "tehran_str": z["tehran_str"],
                "has_setup": has_setup,
                "reason": reason,
                "setup_type": res.get("setup_type", "NONE"),
                "archetype_id": res.get("archetype_id"),
                "session_label": sess_lbl,
                "range_high": asian_high,
                "range_low": asian_low,
                "pierced_high": p_high,
                "pierced_low": p_low,
                "swept_high": has_setup and "BEARISH" in res.get("setup_type", ""),
                "swept_low": has_setup and "BULLISH" in res.get("setup_type", ""),
                "breaker_type": brk_type if has_brk else "NONE",
                "breaker_price": float(brk_price) if has_brk else 0.0,
                "fvg_dir": fvg_dir if has_fvg else "NONE",
                "h1_state": mtf_info.get("h1_state", "NEUTRAL"),
                "phase": res.get("phase") or "BALANCED_RANGE",
            }
            diagnostics.append(diag_entry)

            # Capture significant timeline events
            if has_setup:
                already_session_taken = (sess_lbl == "London Open" and lon_trade_taken) or (sess_lbl == "NY Open" and ny_trade_taken)
                if not already_session_taken:
                    events.append({
                        "time": bar_time,
                        "tehran_str": z["tehran_str"],
                        "utc_str": z["utc_str"],
                        "kind": "SIGNAL",
                        "msg": f"[{sess_lbl}] {reason}",
                    })
                if not already_session_taken and res.get("entry_ref") and res.get("sl_ref"):
                    if sess_lbl == "London Open": lon_trade_taken = True
                    if sess_lbl == "NY Open": ny_trade_taken = True
                    entry_p = float(res["entry_ref"])
                    sl_p = float(res["sl_ref"])
                    target_rr = float(res.get("recommended_target_rr", 2.0))
                    be_rr = float(res.get("recommended_be_rr", 1.2))
                    direction = "SHORT" if "BEARISH" in res.get("setup_type", "") else "LONG"
                    risk = abs(entry_p - sl_p)
                    tp_p = entry_p - (target_rr * risk) if direction == "SHORT" else entry_p + (target_rr * risk)

                    # Simulate forward execution on M1 bars
                    m1_idx = m1_map.get(bar_time)
                    outcome = "UNFILLED"
                    net_r = 0.0
                    fill_time = None
                    exit_time = None
                    max_mfe = 0.0
                    max_mae = 0.0

                    if m1_idx is not None and risk >= 1.0:
                        fwd = bars_m1_all[m1_idx + 1 : m1_idx + 481]
                        filled = False
                        f_start = 0
                        for fi, fb in enumerate(fwd):
                            if direction == "SHORT" and fb["high"] >= entry_p:
                                filled = True; f_start = fi; fill_time = fb["time"]; break
                            elif direction == "LONG" and fb["low"] <= entry_p:
                                filled = True; f_start = fi; fill_time = fb["time"]; break
                            if direction == "SHORT" and fb["high"] >= sl_p: break
                            elif direction == "LONG" and fb["low"] <= sl_p: break

                        if filled:
                            fz = server_epoch_to_zones(fill_time)
                            events.append({
                                "time": fill_time,
                                "tehran_str": fz["tehran_str"],
                                "utc_str": fz["utc_str"],
                                "kind": "FILL",
                                "msg": f"Limit Order FILLED @ {entry_p:.2f} (SL: {sl_p:.2f} | TP: {tp_p:.2f} [{target_rr}R])",
                            })
                            cur_sl = sl_p
                            be_active = False
                            outcome = "EXPIRED"
                            for tb in fwd[f_start:]:
                                if direction == "SHORT":
                                    mfe = (entry_p - tb["low"] - spread) / risk
                                    mae = (tb["high"] - entry_p + spread) / risk
                                else:
                                    mfe = (tb["high"] - entry_p - spread) / risk
                                    mae = (entry_p - tb["low"] + spread) / risk
                                if mfe > max_mfe: max_mfe = mfe
                                if mae > max_mae: max_mae = mae

                                if not be_active and max_mfe >= be_rr:
                                    be_active = True
                                    cur_sl = entry_p - spread if direction == "SHORT" else entry_p + spread

                                hit_sl = (tb["high"] >= cur_sl) if direction == "SHORT" else (tb["low"] <= cur_sl)
                                hit_tp = (tb["low"] <= tp_p) if direction == "SHORT" else (tb["high"] >= tp_p)

                                if hit_tp:
                                    outcome = "WIN"
                                    net_r = target_rr
                                    exit_time = tb["time"]
                                    break
                                elif hit_sl:
                                    outcome = "BE" if be_active else "LOSS"
                                    net_r = 0.0 if be_active else -1.0
                                    exit_time = tb["time"]
                                    break

                            if exit_time:
                                ez = server_epoch_to_zones(exit_time)
                                events.append({
                                    "time": exit_time,
                                    "tehran_str": ez["tehran_str"],
                                    "utc_str": ez["utc_str"],
                                    "kind": "WIN" if net_r > 0 else ("LOSS" if net_r < 0 else "SWEEP"),
                                    "msg": f"Trade Closed: {outcome} ({'+' if net_r >= 0 else ''}{net_r:.2f}R) | Max MFE: +{max_mfe:.2f}R",
                                })

                    trades.append({
                        "archetype": res.get("archetype_id", "SETUP-ARCH-001"),
                        "direction": direction,
                        "signal_time": bar_time,
                        "fill_time": fill_time,
                        "exit_time": exit_time,
                        "entry": round(entry_p, 2),
                        "sl": round(sl_p, 2),
                        "tp": round(tp_p, 2),
                        "risk": round(risk, 2),
                        "outcome": outcome,
                        "net_r": round(net_r, 2),
                        "mfe_r": round(max_mfe, 2),
                        "mae_r": round(max_mae, 2),
                    })
            elif reason != last_reason and ("Veto" in reason or "Dead" in reason):
                # Log transition into important vetoes during active London/NY hours
                if is_active_kz:
                    events.append({
                        "time": bar_time,
                        "tehran_str": z["tehran_str"],
                        "utc_str": z["utc_str"],
                        "kind": "VETO",
                        "msg": f"[{sess_lbl}] {reason}",
                    })
            elif (p_high or p_low) and is_active_kz:
                if not any(e["kind"] == "SWEEP" and abs(e["time"] - bar_time) < 1800 for e in events):
                    side = "High" if p_high else "Low"
                    events.append({
                        "time": bar_time,
                        "tehran_str": z["tehran_str"],
                        "utc_str": z["utc_str"],
                        "kind": "SWEEP",
                        "msg": f"Asian {side} ({asian_high if p_high else asian_low:.2f}) pierced during {sess_lbl}. Breaker={diag_entry['breaker_type']} | H1={diag_entry['h1_state']}",
                    })

            last_reason = reason

        replay_dataset[d_str] = {
            "date": d_str,
            "weekday": d_date.strftime("%a"),
            "bars_m5": day_m5_formatted,
            "bars_m1": day_m1_formatted,
            "asian_range": {"high": asian_high, "low": asian_low} if asian_high else None,
            "killzones": [
                {"name": "ASIAN", "start": asian_start_srv, "end": asian_end_srv},
                {"name": "LONDON", "start": lon_start_srv, "end": lon_end_srv},
                {"name": "NEW_YORK", "start": ny_start_srv, "end": ny_end_srv},
            ],
            "diagnostics": diagnostics,
            "events": sorted(events, key=lambda x: x["time"]),
            "trades": trades,
        }
        print(f"   ✅ Compiled {d_str} ({d_date.strftime('%a')}): {len(day_m5_formatted)} M5 bars | {len(events)} events | {len(trades)} trade(s)")

    # Inject JSON into HTML template
    template_html = TEMPLATE_FILE.read_text(encoding="utf-8")
    payload_js = f"window.REPLAY_DATASET = {json.dumps(replay_dataset)};"
    final_html = template_html.replace("// INJECTED_REPLAY_DATA_PLACEHOLDER", payload_js)

    out_html = OUT_DIR / "visual_backtest_replayer.html"
    out_html.write_text(final_html, encoding="utf-8")
    ARTIFACT_HTML.write_text(final_html, encoding="utf-8")

    print("=" * 85)
    print(f"🚀 VISUAL REPLAYER GENERATED SUCCESSFULLY:")
    print(f"   -> Workspace Copy: {out_html}")
    print(f"   -> Artifact Viewer: {ARTIFACT_HTML}")
    print("=" * 85)
    return ARTIFACT_HTML


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Compile TradingGuard Visual Backtest Replayer")
    parser.add_argument("--dates", nargs="+", default=["2026-11-11", "2026-11-10", "2026-11-09", "2026-11-06", "2026-11-05", "2026-11-04", "2026-11-03", "2026-11-02"], help="Dates to include in visual replayer (YYYY-MM-DD)")
    args = parser.parse_args()
    compile_visual_replay(args.dates)
