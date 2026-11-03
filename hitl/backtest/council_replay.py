"""
TradingGuard HITL - Backtest Council Replay Engine
Invokes the Antigravity AI Investment Council on historical session dossiers
and extracts structured execution parameters from the CIO Directive.
"""

import re
import sys
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.council import find_agy_binary
from hitl.council_memory import get_institutional_memory_prompt


def convene_council_on_historical_dossier(dossier: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Feeds the historical MTF chart PNGs and market context at timestamp T to agy.exe.
    Returns structured CIO decision dict:
    {
        'decision': 'BUY_LIMIT' | 'SELL_LIMIT' | 'STAND_ASIDE',
        'entry': float or None,
        'sl': float or None,
        'tp': float or None,
        'lot': 0.01,
        'rr': float or None,
        'full_report': str
    }
    """
    sym = dossier["symbol"]
    p_1d, p_1h, p_15m, p_5m = dossier["chart_paths"]
    price_at_t = dossier["price_at_t"]
    usdx_at_t = dossier.get("usdx_at_t", 101.75)
    target_time = dossier["target_time"]
    t_str = target_time.strftime("%Y-%m-%d %H:%M Tehran Time")

    agy_bin = find_agy_binary()

    price_str = f"{price_at_t:.5f}" if ("EUR" in sym.upper() or "GBP" in sym.upper()) else f"{price_at_t:.2f}"

    telemetry_str = dossier.get("telemetry_prompt", "")
    memory_prompt = get_institutional_memory_prompt(sym)

    prompt = (
        f"You are the Antigravity Trading & Investment Council, an elite proprietary trading committee.\n"
        f"Conduct an institutional committee review for {sym} at historical session milestone: {t_str}.\n\n"
        f"{memory_prompt}\n\n"
        f"{telemetry_str}\n\n"
        f"=== MULTI-TIMEFRAME CHART DOSSIER (STRICTLY HISTORICAL UP TO {t_str}) ===\n"
        f"- 1D Daily Chart: '{p_1d.as_posix()}'\n"
        f"- 1H Trend Chart: '{p_1h.as_posix()}'\n"
        f"- 15M Structure Chart: '{p_15m.as_posix()}'\n"
        f"- 5M Execution Chart: '{p_5m.as_posix()}'\n\n"
        f"=== ADVANCED SMC & FIRM GOVERNANCE RULES ===\n"
        f"1. Alpha Execution Mandate: The quantitative ICT screener has pre-screened this session and flagged a candidate setup with confirmed displacement, liquidity sweep, or SMT divergence. The Council's primary duty is ALPHA CAPTURE WITH STRICT CAPITAL PRESERVATION. If the candidate setup satisfies structural invalidation (SL <= $17.00) and targets a minimum 1:3.0 R:R, the Council MUST APPROVE the limit order ([BUY LIMIT] or [SELL LIMIT]). Do NOT act as a fearful bureaucrat seeking theoretical excuses to declare STAND ASIDE when a valid edge is present. STAND ASIDE is strictly reserved for dead consolidation without displacement, high-impact red-folder news within 15 minutes, or negative R:R (< 1:3.0).\n"
        f"2. Proximal Entry Enforcement: Limit orders MUST be anchored at the PROXIMAL EDGE of the displacement FVG or Breaker Block (the nearest boundary price can tap on a pullback). NEVER demand an excessive, deep retracement (e.g. 50% CE or distal edge during active sessions) because that causes the order to expire unfilled after 75 minutes, resulting in severe alpha leakage.\n"
        f"3. Strict $17.00 Max Risk per Trade (0.01 lot base). Stop loss must never exceed $17.00. For Gold (XAUUSD), anchor SL behind the recent structural swing/sweep wick (typically 5.0 to 7.5 points).\n"
        f"4. Realistic Structural Target Anchoring (Strict 1:3.0 to 1:4.0 R:R): Take Profit MUST anchor to the realistic opposing session landmark (e.g. Asian Range High/Low or London High/Low), targeting between 1:3.0 and 1:4.0 R:R. NEVER set fantasy swing targets exceeding 1:4.5 R:R on intraday session setups, as intraday liquidity cycles mean price will retrace before reaching 100+ point targets.\n"
        f"5. SMT & Macro Alignment: Confirm correlation alignment or SMT divergence against Silver (XAGUSD) and USDX.\n"
        f"6. Directional Confluence Mandate: In pro-trend regimes, execute with pro-trend momentum. Counter-trend trades are only allowed if a prominent liquidity sweep (Asian Range High/Low or PDH/PDL) has formed with confirmed MSS displacement or intermarket SMT divergence (SETUP-ARCH-007).\n\n"
        f"Deliver the Tactical Execution findings strictly in the following format:\n\n"
        f"🏛️ **TRADINGGUARD TACTICAL EXECUTION COUNCIL: {sym}**\n\n"
        f"👨‍💻 **1. Chief ICT & Technical Strategist (Advanced SMC & Order Flow)**\n"
        f"• Liquidity Sweep & Judas Swing Validation:\n"
        f"• Active POI & Displacement FVG Retracement:\n"
        f"• Market Structure Shift (MSS) Confirmation:\n\n"
        f"🛡️ **2. Chief Risk Officer (CRO - Capital Defense & Invalidation)**\n"
        f"• Structural Invalidation Level (Pinned SL per RULE-CORE-005):\n"
        f"• Risk Geometry & Cap Verification (Strict $17 cap, R:R >= 1:3.0):\n\n"
        f"⚖️ **3. CIO Executive Consensus Directive**\n"
        f"• **Council Decision:** [BUY LIMIT | SELL LIMIT | STAND ASIDE]\n"
        f"• **Actionable Execution Plan (if applicable):** Entry: `X.XX` | SL: `X.XX` | TP: `X.XX` | Lot: `0.01` | R:R: `1:X.X` (Mandatory >= 1:3.0)\n"
        f"• **Playbook Alignment:** (Confirm alignment with Active Institutional Rules e.g. entry anchor / stop buffer).\n"
        f"• **Executive Summary & Critical Trigger:** (Clear 2-sentence institutional synthesis).\n\n"
        f"📋 **4. Chief Watchlist Officer (CDO - Tactical Reconnaissance)**\n"
        f"• **Actionable 'IF-THEN' Re-Activation Trigger:**\n"
        f"• **Setup Invalidation Anchor:**\n\n"
        f"Maintain institutional discipline, precise numbers, and strict adherence to the $17 risk cap.\n"
        f"Keep the entire tactical report punchy, concise, and under 300 words total."
    )

    import tempfile
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
        tf.write(prompt)
        prompt_file = Path(tf.name)

    cmd = [
        agy_bin,
        "--dangerously-skip-permissions",
        "--model", "gemini-3.8-flash-low",
        "-p", f"@{prompt_file.as_posix()}"
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=90
        )
        try:
            if prompt_file.exists():
                prompt_file.unlink()
        except Exception:
            pass

        if proc.returncode != 0:
            print(f"[CouncilReplay] agy failed: {proc.stderr}")
            return None

        output = proc.stdout.strip()
        lines = [line for line in output.splitlines() if not line.startswith("jetski:")]
        clean_text = "\n".join(lines).strip()

        # Parse CIO Directive
        decision = "STAND_ASIDE"
        m_dec = re.search(r'Council Decision:?\*{0,2}\s*[\*\[`]*(BUY LIMIT|SELL LIMIT|STAND ASIDE)[\*\]`]*', clean_text, re.IGNORECASE)
        if m_dec:
            raw_dec = m_dec.group(1).upper()
            if "BUY" in raw_dec:
                decision = "BUY_LIMIT"
            elif "SELL" in raw_dec:
                decision = "SELL_LIMIT"
            else:
                decision = "STAND_ASIDE"

        entry, sl, tp, rr = None, None, None, None
        landmarks = dossier.get("landmarks")
        macro_filter = dossier.get("macro_bias_data", {}).get("execution_filter", "")

        if decision != "STAND_ASIDE" and landmarks:
            # Deterministic Tool-Grounded SMC Execution Protocol
            from hitl.tools.smc_tools import build_validated_order_plan

            cio_marker = clean_text.find("CIO Executive Consensus Directive")
            if cio_marker == -1:
                cio_marker = clean_text.find("Actionable Execution Plan")
            cio_text = clean_text[cio_marker:] if cio_marker != -1 else clean_text

            poi_choice = "PROXIMAL_EDGE"
            if "DISTAL" in cio_text.upper():
                poi_choice = "DISTAL_EDGE"
            elif "CONSEQUENT" in cio_text.upper() or "50%" in cio_text:
                poi_choice = "CONSEQUENT_ENCROACHMENT"

            plan, reason = build_validated_order_plan(
                decision=decision,
                poi_selection=poi_choice,
                landmarks=landmarks,
                macro_filter=macro_filter
            )

            if plan:
                entry = plan["entry"]
                sl = plan["sl"]
                tp = plan["tp"]
                rr = plan["rr"]
                print(f"  [ToolEngine] {reason}")
            else:
                print(f"  [ToolEngine Pre-Flight Rejection] {reason} -> Overriding to STAND_ASIDE.")
                decision = "STAND_ASIDE"

        elif decision != "STAND_ASIDE":
            # Legacy regex fallback if landmarks not provided
            cio_marker = clean_text.find("CIO Executive Consensus Directive")
            if cio_marker == -1:
                cio_marker = clean_text.find("Actionable Execution Plan")
            target_text = clean_text[cio_marker:] if cio_marker != -1 else clean_text

            m_entry = re.search(r'\b(?:Entry|Entry Price)\b[^0-9\n\r]*([0-9]+\.[0-9]+)', target_text, re.IGNORECASE)
            m_sl = re.search(r'(?:\bStop\s*Loss\b|\bSL\b)[^0-9\n\r]*([0-9]+\.[0-9]+)', target_text, re.IGNORECASE)
            m_tp = re.search(r'(?:\bTake\s*Profit\b|\bTP\b)[^0-9\n\r]*([0-9]+\.[0-9]+)', target_text, re.IGNORECASE)
            m_rr = re.search(r'\bR:?R\b[^0-9\n\r]*1:([0-9.]+)', target_text, re.IGNORECASE)

            if m_entry and m_sl and m_tp:
                try:
                    entry = float(m_entry.group(1))
                    sl = float(m_sl.group(1))
                    tp = float(m_tp.group(1))
                    rr = float(m_rr.group(1)) if m_rr else None

                    # Programmatic Enforcement of RULE-EXEC-021:
                    # For Forex pairs (rates ~ 1.0 to 1.5), detect if SL was passed as a relative pip offset (e.g. 9.0)
                    if entry < 2.5:
                        if sl > 5.0 or abs(entry - sl) > 0.05:
                            # Relative pip offset passed instead of absolute price
                            pip_offset = sl * 0.0001 if sl > 1.0 else sl
                            sl = round(entry - pip_offset if "BUY" in decision else entry + pip_offset, 5)
                        if tp > 5.0 or abs(entry - tp) > 0.10:
                            pip_offset = tp * 0.0001 if tp > 1.0 else tp
                            tp = round(entry + pip_offset if "BUY" in decision else entry - pip_offset, 5)
                        rr = round(abs(tp - entry) / max(0.0001, abs(entry - sl)), 2)

                    # Programmatic Enforcement of RULE-CORE-006 (External Structural Swing Targeting):
                    # If the Council approved a pro-trend limit order but anchored TP prematurely at internal minor support (yielding RR < 3.0),
                    # expand Take Profit to the mandatory external structural liquidity pool (minimum 1:3.2R) per RULE-CORE-006.
                    if rr is not None and rr < 2.95:
                        risk_dist = max(0.0001, abs(entry - sl))
                        if "SELL" in decision:
                            tp = round(entry - 3.2 * risk_dist, 5)
                            rr = round(abs(tp - entry) / risk_dist, 2)
                        elif "BUY" in decision:
                            tp = round(entry + 3.2 * risk_dist, 5)
                            rr = round(abs(tp - entry) / risk_dist, 2)
                except ValueError:
                    decision = "STAND_ASIDE"
            else:
                # Fallback extraction from prose / summary
                fb_entry = re.search(r'(?:entry|proximal edge|fill at)\s*[:\w\s]*`?([0-9]+\.[0-9]+)', clean_text, re.IGNORECASE)
                fb_sl = re.search(r'(?:invalidation|\bsl\b|\bstop loss\b)\s*[:\w\s]*`?([0-9]+\.[0-9]+)', clean_text, re.IGNORECASE)
                fb_tp = re.search(r'(?:tp|target|targeting)\s*[:\w\s]*`?([0-9]+\.[0-9]+)', clean_text, re.IGNORECASE)
                if fb_entry and fb_sl:
                    try:
                        entry = float(fb_entry.group(1))
                        sl = float(fb_sl.group(1))
                        # Default 1:3.0 TP if missing
                        tp = float(fb_tp.group(1)) if fb_tp else (entry + 3.0 * abs(entry - sl) if "BUY" in decision else entry - 3.0 * abs(entry - sl))
                        rr = abs(tp - entry) / max(0.1, abs(entry - sl))
                        if rr < 2.95:
                            decision = "STAND_ASIDE"
                    except ValueError:
                        decision = "STAND_ASIDE"

        return {
            "decision": decision,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lot": 0.01,
            "rr": rr,
            "full_report": clean_text
        }

    except Exception as e:
        try:
            if prompt_file.exists():
                prompt_file.unlink()
        except Exception:
            pass
        print(f"[CouncilReplay] Error invoking agy: {e}")
        return None
