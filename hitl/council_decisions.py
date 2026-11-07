"""
TradingGuard HITL - Council Decisions Logger & Retrospective Audit Module
Persists all Council decisions (Approved orders & Stand Asides) and audits their real-world outcomes.
"""

import json
import time
import uuid
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional
import MetaTrader5 as mt5

from hitl.config import BASE_DIR
from hitl.mt5_engine import MT5Engine
from hitl.backtest.data_feed import _convert_records

DECISIONS_LOG_PATH = BASE_DIR / "hitl" / "memory" / "council_decisions_log.json"


def _load_log() -> List[Dict[str, Any]]:
    if not DECISIONS_LOG_PATH.exists():
        DECISIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        return []
    try:
        with open(DECISIONS_LOG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[CouncilDecisions] Error reading log: {e}")
        return []


def _save_log(data: List[Dict[str, Any]]):
    try:
        DECISIONS_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(DECISIONS_LOG_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[CouncilDecisions] Error saving log: {e}")


def log_council_decision(
    symbol: str,
    decision: str,
    reason: str,
    full_report: str,
    plan: Optional[Dict[str, Any]] = None,
    sweep_target: Optional[str] = None,
    sweep_extreme: Optional[float] = None,
    screener: Optional[Dict[str, Any]] = None,
    parse_status: Optional[str] = None
) -> str:
    """
    Appends a structured Council decision to the persistent ledger.
    screener: the passing screen_ict_session() result (Pack 5) — records
        that the council was convened only after the screener gate passed.
    parse_status: from parse_council_decision_detailed() (Pack 5) — records
        whether the decision came from an explicit line or a flagged fallback.
    """
    now = datetime.datetime.now()
    log_data = _load_log()
    # Collision-proof ID: millisecond timestamp + random suffix.
    # The old second-resolution ID (DEC-{symbol}-{int(time.time())})
    # collided in the log (DEC-XAUUSD-1793624797, once STAND_ASIDE and
    # once BUY_LIMIT on 2026-11-02).
    dec_id = f"DEC-{symbol}-{int(time.time() * 1000)}-{uuid.uuid4().hex[:8]}"

    # Query current price if possible
    curr_price = 0.0
    try:
        if mt5.terminal_info():
            engine = MT5Engine()
            res_sym = engine.resolve_symbol(symbol)
            if res_sym:
                tk = mt5.symbol_info_tick(res_sym)
                if tk:
                    curr_price = tk.bid
    except Exception:
        pass

    record = {
        "id": dec_id,
        "timestamp": now.isoformat(),
        "time_str": now.strftime("%H:%M:%S"),
        "date_str": now.strftime("%Y-%m-%d"),
        "symbol": symbol,
        "decision": decision,
        "reason": reason,
        "full_report": full_report,
        "screener": screener,
        "parse_status": parse_status,
        "price_at_decision": curr_price,
        "sweep_target": sweep_target,
        "sweep_extreme": sweep_extreme,
        "plan": plan,
        "reviewed": False,
        "review_verdict": None,
        "review_notes": None
    }

    log_data.append(record)
    _save_log(log_data)
    return dec_id


def get_unreviewed_decisions(symbol: Optional[str] = None, max_count: int = 10) -> List[Dict[str, Any]]:
    """Retrieves unreviewed Council decisions."""
    log_data = _load_log()
    filtered = [d for d in log_data if not d.get("reviewed", False)]
    if symbol:
        filtered = [d for d in filtered if d.get("symbol") == symbol]
    return filtered[-max_count:]


def audit_decision_outcome(decision_record: Dict[str, Any], engine: MT5Engine) -> Dict[str, Any]:
    """
    Evaluates what actually happened in MT5 after the decision was made.
    Determines whether a Stand Aside was protective or missed a winner,
    and whether an order plan succeeded, failed, or was unfilled.
    """
    symbol = decision_record["symbol"]
    dec_type = decision_record["decision"]
    dec_time_str = decision_record["timestamp"]
    dec_time = datetime.datetime.fromisoformat(dec_time_str)

    res_sym = engine.resolve_symbol(symbol)
    if not res_sym or not engine.ensure_connected():
        return {
            "verdict": "DATA_UNAVAILABLE",
            "summary": "MT5 disconnected during audit."
        }

    is_fx = "GBP" in symbol or "EUR" in symbol
    pip_size = 0.00010 if is_fx else 0.10
    unit = "pips" if is_fx else "pts"

    # Fetch 5M rates from decision time to now
    rates = mt5.copy_rates_from(res_sym, mt5.TIMEFRAME_M5, dec_time, 100)
    if rates is None or len(rates) < 2:
        return {
            "verdict": "INSUFFICIENT_FORWARD_BARS",
            "summary": "Recent decision; forward price trajectory still incubating."
        }

    bars = _convert_records(rates)
    # Exclude bars prior to decision time
    dec_ts = dec_time.timestamp()
    forward_bars = [b for b in bars if b['time'] >= dec_ts]
    if not forward_bars:
        forward_bars = bars

    ref_price = decision_record.get("price_at_decision") or forward_bars[0]['open']
    max_high = max(b['high'] for b in forward_bars)
    min_low = min(b['low'] for b in forward_bars)
    latest_close = forward_bars[-1]['close']

    max_gain = (max_high - ref_price) / pip_size
    max_drop = (ref_price - min_low) / pip_size

    # 1. Audit Stand Aside Decisions
    if dec_type == "STAND_ASIDE":
        sweep_tgt = str(decision_record.get("sweep_target", "")).lower()
        # If it was a high sweep (Judas high / Asian High) that we stood aside on selling:
        if "high" in sweep_tgt or "pdh" in sweep_tgt or "bearish" in str(decision_record.get("reason", "")).lower():
            # If price subsequently dropped heavily:
            if max_drop >= (15.0 if not is_fx else 20.0):
                verdict = "❌ MISSED WINNER (Flawed Veto)"
                summary = f"Price dropped -{max_drop:.1f} {unit} to {min_low:.2f} after veto. Macro bias caused execution blindness on clean Judas high."
            elif max_gain >= (15.0 if not is_fx else 20.0):
                verdict = "✅ PROTECTIVE VETO (Accurate Decision)"
                summary = f"Price expanded +{max_gain:.1f} {unit} higher through the peak. Veto successfully prevented taking counter-trend heat."
            else:
                verdict = "⚖️ RANGE CHOP (Neutral Veto)"
                summary = f"Price remained in consolidation ({min_low:.2f} - {max_high:.2f}). No significant expansion occurred."

        # If it was a low sweep (Asian Low / PDL) that we stood aside on buying:
        elif "low" in sweep_tgt or "pdl" in sweep_tgt or "bullish" in str(decision_record.get("reason", "")).lower():
            if max_gain >= (15.0 if not is_fx else 20.0):
                verdict = "❌ MISSED WINNER (Flawed Veto)"
                summary = f"Price surged +{max_gain:.1f} {unit} to {max_high:.2f} after veto. Discount entry was missed."
            elif max_drop >= (15.0 if not is_fx else 20.0):
                verdict = "✅ PROTECTIVE VETO (Accurate Decision)"
                summary = f"Price plunged -{max_drop:.1f} {unit} lower. Veto protected against falling knife."
            else:
                verdict = "⚖️ RANGE CHOP (Neutral Veto)"
                summary = f"Price remained in tight chop range ({min_low:.2f} - {max_high:.2f})."
        else:
            # Generic stand aside: evaluate volatility
            if max(max_gain, max_drop) < (10.0 if not is_fx else 12.0):
                verdict = "✅ ACCURATE VETO"
                summary = f"Market exhibited dead equilibrium chop. Standing aside preserved capital."
            else:
                verdict = "⚖️ SESSION AUDITED"
                summary = f"Range reached {max_high:.2f} high and {min_low:.2f} low."

        return {
            "verdict": verdict,
            "summary": summary,
            "max_gain": round(max_gain, 1),
            "max_drop": round(max_drop, 1),
            "ref_price": ref_price
        }

    # 2. Audit Approved Limit Orders (BUY_LIMIT / SELL_LIMIT)
    plan = decision_record.get("plan")
    if plan and plan.get("entry"):
        entry = plan["entry"]
        sl = plan.get("sl")
        tp = plan.get("tp")

        # Check if price reached entry
        hit_entry = (min_low <= entry) if "BUY" in dec_type else (max_high >= entry)
        if not hit_entry:
            dist_to_entry = (ref_price - entry) / pip_size if "BUY" in dec_type else (entry - ref_price) / pip_size
            verdict = "⚠️ UNFILLED PENDING"
            summary = f"Price did not retrace to limit entry ({entry}). Reached within {abs(dist_to_entry):.1f} {unit}."
            return {"verdict": verdict, "summary": summary}

        # Price hit entry -> Check if it subsequently hit TP or SL
        post_fill_bars = [b for b in forward_bars if (b['low'] <= entry if "BUY" in dec_type else b['high'] >= entry)]
        if post_fill_bars:
            pf_high = max(b['high'] for b in post_fill_bars)
            pf_low = min(b['low'] for b in post_fill_bars)

            if "BUY" in dec_type:
                hit_tp = tp and pf_high >= tp
                hit_sl = sl and pf_low <= sl
            else:
                hit_tp = tp and pf_low <= tp
                hit_sl = sl and pf_high >= sl

            if hit_tp and not hit_sl:
                verdict = "🏆 TARGET HIT (WIN)"
                summary = f"Limit order filled at {entry} and reached Take Profit ({tp}) with full target realization."
            elif hit_sl and not hit_tp:
                verdict = "🛑 STOPPED OUT (LOSS)"
                summary = f"Order filled at {entry} but structural stop ({sl}) was breached."
            else:
                verdict = "🎯 ACTIVE IN-FLIGHT"
                summary = f"Order filled at {entry}. Current price {latest_close:.2f} is in play."

            return {"verdict": verdict, "summary": summary}

    return {
        "verdict": "DECISION RECORDED",
        "summary": "Decision logged successfully."
    }
