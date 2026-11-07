"""
TradingGuard HITL - Institutional AI Investment Council Engine
Authentic 3-Round Adversarial Multi-Agent Deliberation Architecture:
  Round 1 (Parallel):
    - Seat 1: Chief ICT & Order Flow Strategist (Technical edge, FVG/MSS, Order Plan)
    - Seat 2: Chief Macro & Exposure Officer (Macro calendar, USDX, Broker Exposure RULE-RISK-010)
  Round 2 (Adversarial):
    - Seat 3: Adversarial Invalidation Auditor (Stress-tests Stop Loss, detects Inducement Traps)
  Round 3 (Arbitration):
    - Seat 4: Chief Investment Officer (CIO / Final Consensus Directive & Risk Sizing)

Executed via native Google Antigravity binary (agy.exe) with zero financial cost.
"""

import os
import sys
import re
import time
import shutil
import tempfile
import subprocess
import datetime
import concurrent.futures
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.macro_calendar import format_fundamental_summary, get_upcoming_events
from hitl.sentiment_feed import format_sentiment_summary
from hitl.mt5_engine import MT5Engine
from hitl.council_memory import get_institutional_memory_prompt
import MetaTrader5 as mt5


def parse_council_decision_detailed(report: Optional[str]) -> Tuple[str, str]:
    """
    Extracts the Council's final consensus decision and reports *how* it
    was found, so a silent fallback can never be mistaken for a real
    decision. Returns (decision, parse_status) where parse_status is one of:
      EXPLICIT_DECISION        — a "Council Decision: [BUY/SELL/STAND ASIDE]" line
      CIO_CONSENSUS            — a Consensus/Directive/Verdict line
      AMBIGUOUS_STAND_ASIDE    — no decision line; "STAND ASIDE" merely appears
                                 somewhere in the report (e.g. a veto discussion)
      PARSE_FAILURE_EMPTY      — report is None/empty (agy timeout, crash, empty output)
      PARSE_FAILURE            — no decision line and no STAND ASIDE mention at all
    """
    if not report:
        return "STAND_ASIDE", "PARSE_FAILURE_EMPTY"

    # 1. Match explicit Council Decision line (e.g. "• **Council Decision:** [BUY LIMIT | SELL LIMIT | STAND ASIDE]")
    m = re.search(r'(?i)Council\s+Decision[:\* ]+\s*\[?\s*(BUY[ _]LIMIT|SELL[ _]LIMIT|STAND[ _]ASIDE)', report)
    if m:
        return m.group(1).upper().replace(' ', '_'), "EXPLICIT_DECISION"

    # 2. Match CIO Executive Consensus line
    m_cio = re.search(r'(?i)(?:Consensus|Directive|Verdict)[:\* ]+\s*\[?\s*(BUY[ _]LIMIT|SELL[ _]LIMIT|STAND[ _]ASIDE)', report)
    if m_cio:
        return m_cio.group(1).upper().replace(' ', '_'), "CIO_CONSENSUS"

    # 3. If explicit STAND ASIDE is stated in directive section
    if re.search(r'(?i)\bSTAND[ _]ASIDE\b', report):
        return "STAND_ASIDE", "AMBIGUOUS_STAND_ASIDE"

    return "STAND_ASIDE", "PARSE_FAILURE"


def parse_council_decision(report: Optional[str]) -> str:
    """
    Strictly extracts the Council's final consensus decision from the report.
    Returns: 'BUY_LIMIT', 'SELL_LIMIT', or 'STAND_ASIDE'
    """
    decision, status = parse_council_decision_detailed(report)
    if status in ("PARSE_FAILURE", "PARSE_FAILURE_EMPTY", "AMBIGUOUS_STAND_ASIDE"):
        print(
            f"[Council] PARSE {status}: no explicit Council Decision line found; "
            f"defaulting to STAND_ASIDE (safe default). Raw report retained in "
            f"the decision log for audit."
        )
    return decision


def find_agy_binary() -> str:
    """Locates the local Antigravity CLI executable."""
    found = shutil.which("agy")
    if found:
        return found
    
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "agy", "bin", "agy.exe"),
        r"C:\Users\Javad\AppData\Local\agy\bin\agy.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    return "agy"


def _execute_agent_prompt(
    agy_bin: str,
    seat_name: str,
    system_role: str,
    task_payload: str,
    model: str = "gemini-3.8-flash-low",
    timeout: int = 50
) -> Tuple[str, float, str]:
    """
    Executes a single institutional seat via agy CLI using file-based prompt piping.
    Avoids Windows CLI character limits and ensures clean execution.
    Returns: (seat_name, elapsed_seconds, response_text)
    """
    t0 = time.time()
    full_prompt = (
        f"You are operating as a dedicated, specialized institutional agent in TradingGuard.\n\n"
        f"=== SYSTEM IDENTITY & MANDATE ===\n{system_role}\n\n"
        f"=== TASK CONTEXT & MARKET DATA ===\n{task_payload}\n\n"
        f"Deliver your findings strictly in clear, professional English. Be quantitative, precise, and concise."
    )

    temp_name = ""
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, suffix=".txt") as tf:
            tf.write(full_prompt)
            temp_name = tf.name

        cmd = [
            agy_bin,
            "--dangerously-skip-permissions",
            "--model", model,
            "-p", f"@{temp_name}"
        ]

        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout
        )

        try:
            if os.path.exists(temp_name):
                os.remove(temp_name)
        except Exception:
            pass

        dt = time.time() - t0
        if proc.returncode != 0:
            err_msg = f"[ERROR: Seat {seat_name} returned exit code {proc.returncode}: {proc.stderr.strip()}]"
            return seat_name, dt, err_msg

        lines = [line for line in proc.stdout.splitlines() if not line.startswith("jetski:")]
        clean_text = "\n".join(lines).strip()
        return seat_name, dt, clean_text if clean_text else f"[ERROR: Seat {seat_name} returned empty output]"

    except subprocess.TimeoutExpired:
        try:
            if temp_name and os.path.exists(temp_name):
                os.remove(temp_name)
        except Exception:
            pass
        return seat_name, time.time() - t0, f"[ERROR: Seat {seat_name} timed out after {timeout}s]"
    except Exception as e:
        try:
            if temp_name and os.path.exists(temp_name):
                os.remove(temp_name)
        except Exception:
            pass
        return seat_name, time.time() - t0, f"[ERROR: Seat {seat_name} encountered exception: {e}]"


def assemble_council_intelligence(symbol: str = "XAUUSD") -> Dict[str, Any]:
    """
    Gathers multi-source market intelligence for the AI Council:
    1. Multi-timeframe chart image paths (1D, 1H, 15M, 5M)
    2. Live MT5 quotes, bid/ask, and broker spread
    3. Live US Dollar Index (USDX) quote and trend
    4. Scheduled macroeconomic catalysts & calendar
    5. Live TradingView analyst community positioning & ideas
    """
    if "GBP" in symbol.upper():
        sym = "GBPUSD"
    elif "EUR" in symbol.upper():
        sym = "EURUSD"
    else:
        sym = "XAUUSD"
    mtf_dir = BASE_DIR / "analysis_assets" / "mtf"
    
    p_1d = mtf_dir / f"{sym}_1D.png"
    p_1h = mtf_dir / f"{sym}_1H.png"
    p_15m = mtf_dir / f"{sym}_15M.png"
    p_5m = mtf_dir / f"{sym}_5M.png"
    
    charts_ready = all(p.exists() for p in [p_1d, p_1h, p_15m, p_5m])
    if not charts_ready:
        try:
            from hitl.backtest.chart_renderer import render_candlestick_chart, extract_chart_landmarks
            from hitl.backtest.data_feed import _convert_records
            temp_engine = MT5Engine()
            temp_res = temp_engine.resolve_symbol(sym)
            if temp_engine.ensure_connected() and temp_res:
                r1d = _convert_records(mt5.copy_rates_from_pos(temp_res, mt5.TIMEFRAME_D1, 0, 90))
                r1h = _convert_records(mt5.copy_rates_from_pos(temp_res, mt5.TIMEFRAME_H1, 0, 80))
                r15m = _convert_records(mt5.copy_rates_from_pos(temp_res, mt5.TIMEFRAME_M15, 0, 60))
                r5m = _convert_records(mt5.copy_rates_from_pos(temp_res, mt5.TIMEFRAME_M5, 0, 60))
                r5m_full = _convert_records(mt5.copy_rates_from_pos(temp_res, mt5.TIMEFRAME_M5, 0, 200))
                landmarks = extract_chart_landmarks(sym, r1d, r5m_full)
                if r1d and r1h and r15m and r5m:
                    mtf_dir.mkdir(parents=True, exist_ok=True)
                    render_candlestick_chart(r1d, sym, "1D", p_1d)
                    render_candlestick_chart(r1h, sym, "1H", p_1h, horizontal_levels=landmarks)
                    render_candlestick_chart(r15m, sym, "15M", p_15m, horizontal_levels=landmarks)
                    render_candlestick_chart(r5m, sym, "5M", p_5m, horizontal_levels=landmarks)
                    charts_ready = True
        except Exception as e:
            print(f"[Council] Error generating chart fallback: {e}")
    
    # Live MT5 Market Data
    engine = MT5Engine()
    resolved_sym = engine.resolve_symbol(sym)
    
    bid, ask, spread_pts = 0.0, 0.0, 0.0
    usdx_bid, usdx_ask = 0.0, 0.0
    
    if engine.ensure_connected():
        if resolved_sym:
            tk = mt5.symbol_info_tick(resolved_sym)
            info = mt5.symbol_info(resolved_sym)
            if tk:
                bid = tk.bid
                ask = tk.ask
            if info:
                spread_pts = info.spread

        usdx_sym = engine.resolve_symbol("USDX")
        if usdx_sym:
            u_tk = mt5.symbol_info_tick(usdx_sym)
            if u_tk:
                usdx_bid = u_tk.bid
                usdx_ask = u_tk.ask

    # Live Broker Exposure & Open Positions Check (RULE-RISK-010)
    active_exposure_prompt = ""
    open_positions = []
    pending_orders = []
    try:
        if resolved_sym:
            raw_pos = mt5.positions_get(symbol=resolved_sym)
            if raw_pos:
                for p in raw_pos:
                    side_str = "BUY" if p.type == mt5.ORDER_TYPE_BUY else "SELL"
                    open_positions.append({
                        "ticket": p.ticket,
                        "side": side_str,
                        "volume": p.volume,
                        "price_open": p.price_open,
                        "sl": p.sl,
                        "tp": p.tp,
                        "profit": p.profit,
                        "time": datetime.datetime.fromtimestamp(p.time).strftime("%H:%M:%S")
                    })
            raw_ord = mt5.orders_get(symbol=resolved_sym)
            if raw_ord:
                for o in raw_ord:
                    type_str = "BUY LIMIT" if o.type == mt5.ORDER_TYPE_BUY_LIMIT else ("SELL LIMIT" if o.type == mt5.ORDER_TYPE_SELL_LIMIT else str(o.type))
                    pending_orders.append({
                        "ticket": o.ticket,
                        "type": type_str,
                        "volume": o.volume_current,
                        "price_open": o.price_open,
                        "sl": o.sl,
                        "tp": o.tp,
                        "time": datetime.datetime.fromtimestamp(o.time_setup).strftime("%H:%M:%S")
                    })
        if open_positions or pending_orders:
            lines = ["=== ACTIVE BROKER EXPOSURE & LIVE ACCOUNT ORDERS ==="]
            for p in open_positions:
                lines.append(f"• ACTIVE POSITION #{p['ticket']}: {p['side']} {p['volume']} lot @ {p['price_open']} (SL: {p['sl']}, TP: {p['tp']}, PnL: ${p['profit']:.2f}, Opened: {p['time']})")
            for o in pending_orders:
                lines.append(f"• PENDING ORDER #{o['ticket']}: {o['type']} {o['volume']} lot @ {o['price_open']} (SL: {o['sl']}, TP: {o['tp']}, Placed: {o['time']})")
            lines.append("⚠️ CRITICAL GOVERNANCE MANDATE (RULE-RISK-010): An active position/order is ALREADY OPEN on this symbol. Do NOT suggest a duplicate trade in the same direction or within the same structural zone. Risk Officer must immediately VETO (STAND ASIDE) duplicate exposure.")
            active_exposure_prompt = "\n".join(lines)
        else:
            active_exposure_prompt = "=== ACTIVE BROKER EXPOSURE ===\n• Zero open positions or pending orders on this symbol. Account is flat."
    except Exception as e:
        print(f"[Council] Error fetching active broker positions: {e}")
        active_exposure_prompt = "=== ACTIVE BROKER EXPOSURE ===\n• Status unavailable."

    # Fundamental Calendar Brief
    macro_brief = format_fundamental_summary(sym)
    
    # Active HTF Fundamental Directional Bias Engine
    macro_bias_prompt = ""
    bias_data = {}
    try:
        from hitl.macro_bias import calculate_htf_fundamental_bias, format_fundamental_bias_prompt
        bias_data = calculate_htf_fundamental_bias(sym)
        macro_bias_prompt = format_fundamental_bias_prompt(bias_data)
    except Exception as e:
        print(f"[Council] Error computing HTF fundamental bias: {e}")

    # TradingView Community Sentiment Brief
    sentiment_brief = format_sentiment_summary(sym)

    # Mathematical SMC Telemetry & Deterministic Tools
    telemetry_prompt = ""
    tools_prompt = ""
    landmarks = None
    try:
        from hitl.backtest.data_feed import _convert_records
        from hitl.backtest.hybrid_telemetry import extract_hybrid_telemetry, format_telemetry_prompt
        from hitl.tools.smc_tools import get_smc_landmarks, format_smc_tools_block
        now = datetime.datetime.now()
        r_1d = mt5.copy_rates_from_pos(resolved_sym, mt5.TIMEFRAME_D1, 0, 30)
        r_1h = mt5.copy_rates_from_pos(resolved_sym, mt5.TIMEFRAME_H1, 0, 30)
        r_15m = mt5.copy_rates_from_pos(resolved_sym, mt5.TIMEFRAME_M15, 0, 30)
        r_5m = mt5.copy_rates_from_pos(resolved_sym, mt5.TIMEFRAME_M5, 0, 90)

        list_1d = _convert_records(r_1d)
        list_1h = _convert_records(r_1h)
        list_15m = _convert_records(r_15m)
        list_5m = _convert_records(r_5m)

        landmarks = get_smc_landmarks(
            list_1d, list_1h, list_15m, list_5m,
            symbol=sym,
            current_bid=bid,
            current_ask=ask,
            broker_time=now
        )
        tools_prompt = format_smc_tools_block(landmarks)

        t_data = extract_hybrid_telemetry(
            list_1d, list_1h, list_15m, list_5m,
            symbol=sym,
            session_hour=now.hour,
            usdx_quote=usdx_bid
        )
        telemetry_prompt = format_telemetry_prompt(t_data, sym)
    except Exception as e:
        print(f"[Council] Error generating live telemetry: {e}")
    
    return {
        "symbol": sym,
        "resolved_symbol": resolved_sym or sym,
        "charts_ready": charts_ready,
        "chart_paths": [p_1d, p_1h, p_15m, p_5m],
        "bid": bid,
        "ask": ask,
        "spread_pts": spread_pts,
        "usdx_bid": usdx_bid,
        "usdx_ask": usdx_ask,
        "macro_brief": macro_brief,
        "macro_bias_prompt": macro_bias_prompt,
        "macro_bias_data": bias_data,
        "sentiment_brief": sentiment_brief,
        "telemetry_prompt": telemetry_prompt,
        "tools_prompt": tools_prompt,
        "landmarks": landmarks,
        "active_exposure_prompt": active_exposure_prompt,
        "open_positions": open_positions,
        "pending_orders": pending_orders
    }


def convene_investment_council(
    symbol: str = "XAUUSD",
    mode: str = "tactical",
    screener_result: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """
    Convenes the TradingGuard Institutional Multi-Agent Investment Council.
    Implements an authentic 3-Round Adversarial Deliberation Protocol:
      - Round 1 (Parallel): Seat 1 (ICT Strategist) & Seat 2 (Macro & Exposure Officer)
      - Round 2 (Adversarial): Seat 3 (Adversarial Invalidation Auditor) stress-tests setup
      - Round 3 (Consensus Directive): Seat 4 (CIO Consensus Arbitrator) issues binding order
    """
    if "GBP" in symbol.upper():
        sym = "GBPUSD"
    elif "EUR" in symbol.upper():
        sym = "EURUSD"
    else:
        sym = "XAUUSD"
        
    intel = assemble_council_intelligence(sym)
    if not intel["charts_ready"]:
        missing = [str(p) for p in intel["chart_paths"] if not p.exists()]
        print(f"[Council] Incomplete multi-timeframe chart package: {missing}")
        return None

    p_1d, p_1h, p_15m, p_5m = intel["chart_paths"]
    agy_bin = find_agy_binary()

    tel_prompt = intel.get('telemetry_prompt', '')
    memory_prompt = get_institutional_memory_prompt(sym)

    is_fx = "GBP" in sym or "EUR" in sym
    fmt = ".5f" if is_fx else ".2f"
    bid_str = f"{intel['bid']:{fmt}}"
    ask_str = f"{intel['ask']:{fmt}}"
    tools_str = intel.get('tools_prompt', '')

    screener_section = ""
    if screener_result:
        screener_section = (
            f"=== SCREENER PRE-SCREENING (CLOSED BARS ONLY) ===\n"
            f"The quantitative ICT screener HAS pre-screened this session on closed "
            f"bars and flagged candidate setup: {screener_result.get('setup_type')} "
            f"({screener_result.get('archetype_id', 'n/a')}).\n"
            f"• Screener reason: {screener_result.get('reason')}\n"
            f"• Signal bar: {screener_result.get('signal_bar_time')} | "
            f"Entry ref: {screener_result.get('entry_ref')} | "
            f"SL ref: {screener_result.get('sl_ref')}\n"
            f"• Phase: {screener_result.get('phase')} | "
            f"Recommended target: {screener_result.get('recommended_target_rr')}R\n"
            f"Evaluate this specific flagged setup — do not invent an imaginary setup.\n"
        )

    market_dossier = (
        f"=== MULTI-TIMEFRAME ASSET DOSSIER ===\n"
        f"• Asset: {sym} | Current Bid: {bid_str} | Ask: {ask_str} (Spread: {intel['spread_pts']} pts)\n"
        f"• US Dollar Index (USDX): {intel['usdx_bid']:.2f} / {intel['usdx_ask']:.2f}\n"
        f"• Charts: 1D: '{p_1d.as_posix()}', 1H: '{p_1h.as_posix()}', 15M: '{p_15m.as_posix()}', 5M: '{p_5m.as_posix()}'\n\n"
        f"{screener_section}\n"
        f"{tools_str}\n\n"
        f"{tel_prompt}\n\n"
        f"{intel.get('active_exposure_prompt', '')}"
    )

    t_start = time.time()
    print(f"[Council] Convening authentic 3-Round Multi-Agent Council for {sym}...")

    # -------------------------------------------------------------
    # ROUND 1: Isolated Independent Evaluations (Parallel)
    # -------------------------------------------------------------
    ict_role = (
        "You are the Chief ICT & Order Flow Strategist for TradingGuard.\n"
        "Your exclusive mandate is technical order flow analysis based strictly on ICT/SMC principles.\n"
        "Focus on: Liquidity sweeps (Judas Swings), Market Structure Shifts (MSS), displacement candles, "
        "and anchoring limit entries at the Proximal Edge of confirmed Fair Value Gaps (FVG) or Breakers.\n"
        "Strict rules: Limit orders ONLY. Stop loss must be structurally pinned behind the sweep wick. "
        "Minimum R:R must be 1:3.0 or higher. Max risk $12.00 (0.01 lot)."
    )
    ict_task = (
        f"{memory_prompt}\n\n"
        f"{market_dossier}\n\n"
        f"Deliver your technical findings strictly in the following structure:\n"
        f"• Liquidity Sweep & Judas Swing Validation:\n"
        f"• Active POI & Displacement FVG Retracement:\n"
        f"• Market Structure Shift (MSS) Confirmation:\n"
        f"• Proposed Technical Execution Plan (or NO_SETUP):\n"
        f"  - Order Type: [BUY LIMIT | SELL LIMIT | NO_SETUP]\n"
        f"  - Entry Price: `X.XX` (Proximal FVG edge)\n"
        f"  - Stop Loss: `X.XX` (Structural invalidation)\n"
        f"  - Take Profit: `X.XX` (Major BSL/SSL pool)\n"
        f"  - Risk:Reward Ratio: `1:X.X` (Must be >= 1:3.0)\n"
        f"Keep under 200 words. Be precise with exact price numbers."
    )

    macro_role = (
        "You are the Chief Macro & Exposure Risk Officer for TradingGuard.\n"
        "You do NOT analyze 5-minute candlestick patterns. Your sole mandate is macro catalysts, "
        "economic news calendar volatility, USDX correlation alignment, and enforcing account exposure limits.\n"
        "Critical Rules:\n"
        "1. High-Impact News Embargo: Strict trading embargo if CPI, NFP, FOMC or high-impact catalyst is within +-15 minutes.\n"
        "2. RULE-RISK-010 Zero Duplicate Exposure: VETO any trade if an active position or pending order is already open on this symbol.\n"
        "3. USDX Correlation: Confirm dollar trend alignment."
    )
    macro_task = (
        f"{memory_prompt}\n\n"
        f"Asset: {sym} | USDX: {intel['usdx_bid']:.2f} / {intel['usdx_ask']:.2f}\n"
        f"Directional Macro Filter: {intel.get('macro_bias_prompt', '')}\n\n"
        f"=== MACROECONOMIC & GEOPOLITICAL ENVIRONMENT ===\n"
        f"{intel['macro_brief']}\n\n"
        f"=== RETAIL SENTIMENT RECONNAISSANCE ===\n"
        f"{intel['sentiment_brief']}\n\n"
        f"{intel.get('active_exposure_prompt', '')}\n\n"
        f"Deliver your macro assessment strictly in the following structure:\n"
        f"• Central Bank Policy & USDX Correlation Alignment:\n"
        f"• Scheduled Economic Events & High-Volatility Embargo Status:\n"
        f"• Broker Exposure & RULE-RISK-010 Compliance:\n"
        f"• Macro Recommendation: [PERMIT_FULL | PERMIT_HALF_RISK | VETO_MACRO_NEWS | VETO_DUPLICATE_EXPOSURE]\n"
        f"Keep under 150 words."
    )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_ict = executor.submit(_execute_agent_prompt, agy_bin, "ICT Strategist", ict_role, ict_task, "gemini-3.8-flash-low")
        f_macro = executor.submit(_execute_agent_prompt, agy_bin, "Macro Officer", macro_role, macro_task, "gemini-3.8-flash-low")
        _, dt_ict, out_ict = f_ict.result()
        _, dt_macro, out_macro = f_macro.result()

    print(f"[Council] Round 1 complete: ICT ({dt_ict:.1f}s), Macro ({dt_macro:.1f}s)")

    # -------------------------------------------------------------
    # ROUND 2: Adversarial Invalidation & Trap Audit (Skeptic)
    # -------------------------------------------------------------
    skeptic_role = (
        "You are the Adversarial Invalidation Auditor for TradingGuard.\n"
        "Your sole duty is CAPITAL DEFENSE, TRAP EXPOSURE, and PREVENTING THE 3.5R ASYMMETRY TRAP.\n"
        "You are explicitly incentivized to destroy the trade thesis and find why it is a false breakout or retail trap.\n"
        "Stress-test against:\n"
        "1. Shallow Sweeps: On Gold, sweeps under 2.0 pts are often retail inducement fakeouts.\n"
        "2. Micro-Stops: Stop losses placed too tight (< 4.0 pts on Gold or < 6.0 pips on FX) get hunted by broker spreads.\n"
        "3. Inducement Traps: Is the trade buying into higher timeframe resistance or selling into discount support?\n"
        "4. Macro / Exposure Violations: Did the Macro Officer report an embargo or duplicate exposure?"
    )
    skeptic_task = (
        f"{market_dossier}\n\n"
        f"=== PROPOSED ICT STRATEGIST TRADE ===\n{out_ict}\n\n"
        f"=== MACRO & EXPOSURE REPORT ===\n{out_macro}\n\n"
        f"Deliver your adversarial stress-test strictly in the following structure:\n"
        f"• Structural Invalidation Level & Stop Vulnerability (Is SL pinned safely per RULE-CORE-005?):\n"
        f"• Retail Inducement & Liquidity Trap Exposure:\n"
        f"• Risk Geometry & Cap Verification (Strict $12 cap, R:R >= 1:3.0):\n"
        f"• Adversarial Invalidation Verdict: [CHALLENGE_ACCEPTED | ADVISE_HALF_RISK | VETO_STRUCTURAL_TRAP]\n"
        f"Keep under 180 words."
    )

    _, dt_skeptic, out_skeptic = _execute_agent_prompt(
        agy_bin, "Adversarial Auditor", skeptic_role, skeptic_task, "gemini-3.8-flash-low"
    )
    print(f"[Council] Round 2 complete: Adversarial Auditor ({dt_skeptic:.1f}s)")

    # -------------------------------------------------------------
    # ROUND 3: CIO Consensus Arbitration & Executive Directive
    # -------------------------------------------------------------
    cio_role = (
        "You are the Chief Investment Officer (CIO) and Final Arbitrator of TradingGuard.\n"
        "You evaluate the three independent, adversarial committee briefs:\n"
        "1. Chief ICT & Technical Strategist (Proposes technical edge)\n"
        "2. Chief Macro & Exposure Officer (Macro catalysts, news embargo, RULE-RISK-010 duplicate check)\n"
        "3. Adversarial Invalidation Auditor (Stress-tests stops, exposes traps, prevents Asymmetry Trap)\n\n"
        "Institutional Mandates:\n"
        "1. If Macro Officer or Adversarial Auditor vetoed the setup, order STAND ASIDE.\n"
        "2. If R:R is below 1:3.0, order STAND ASIDE.\n"
        "3. If setup is confirmed with sound invalidation and R:R >= 1:3.0, approve BUY LIMIT or SELL LIMIT.\n"
        "4. Strict $12.00 max risk per trade (0.01 lot base). Stop loss must never exceed this ceiling."
    )
    cio_task = (
        f"Asset: {sym} | Current Bid: {bid_str} | Ask: {ask_str}\n\n"
        f"=== 1. ICT STRATEGIST BRIEF ===\n{out_ict}\n\n"
        f"=== 2. MACRO & EXPOSURE OFFICER BRIEF ===\n{out_macro}\n\n"
        f"=== 3. ADVERSARIAL AUDITOR BRIEF ===\n{out_skeptic}\n\n"
        f"Render the final executive consensus directive strictly formatted as follows:\n\n"
        f"⚖️ **CIO Executive Consensus Directive**\n"
        f"• **Council Decision:** [BUY LIMIT | SELL LIMIT | STAND ASIDE]\n"
        f"• **Actionable Execution Plan (if applicable):** Entry: `X.XX` | SL: `X.XX` | TP: `X.XX` | Lot: `0.01` | R:R: `1:X.X` (Mandatory >= 1:3.0)\n"
        f"• **Playbook Alignment:** (Confirm alignment with Active Institutional Rules e.g. entry anchor / stop buffer).\n"
        f"• **Executive Summary & Critical Trigger:** (Clear 2-sentence institutional synthesis on why this decision was reached and what condition triggers immediate stand-down).\n\n"
        f"📋 **Chief Watchlist Officer (CDO - Tactical Reconnaissance)**\n"
        f"• **Developing Setup Context:** (What setup is currently incubating?)\n"
        f"• **Actionable 'IF-THEN' Re-Activation Trigger:** (Exact conditional trigger)\n"
        f"• **Setup Invalidation Anchor:** (Price level where watchlist idea is invalidated)"
    )

    _, dt_cio, out_cio = _execute_agent_prompt(
        agy_bin, "CIO Arbitrator", cio_role, cio_task, "gemini-3.8-flash-low"
    )
    total_time = time.time() - t_start
    print(f"[Council] Round 3 complete: CIO Arbitrator ({dt_cio:.1f}s) | Total Deliberation: {total_time:.1f}s")

    # -------------------------------------------------------------
    # ASSEMBLE COMPLETE MULTI-AGENT REPORT
    # -------------------------------------------------------------
    full_report = (
        f"🏛️ **TRADINGGUARD MULTI-AGENT INVESTMENT COUNCIL: {sym}**\n"
        f"Deliberation Protocol: 3-Round Adversarial (Completed in {total_time:.1f}s)\n\n"
        f"👨‍💻 **1. Chief ICT & Technical Strategist (Advanced SMC & Order Flow)**\n"
        f"{out_ict}\n\n"
        f"🌐 **2. Chief Macro & Exposure Risk Officer**\n"
        f"{out_macro}\n\n"
        f"🛡️ **3. Adversarial Invalidation Auditor (Capital Defense & Trap Detection)**\n"
        f"{out_skeptic}\n\n"
        f"{out_cio}"
    )

    decision, parse_status = parse_council_decision_detailed(full_report)
    print(f"[Council] Deliberation finished: Decision={decision} (Parse={parse_status})")
    return full_report


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 60)
    print("Convening TradingGuard Multi-Agent Investment Council for Gold (XAUUSD)...")
    print("=" * 60)
    result = convene_investment_council("XAUUSD")
    if result:
        print("\n" + "=" * 60)
        print("FINAL DELIBERATION REPORT:")
        print("=" * 60)
        print(result)
    else:
        print("Failed to convene council or missing assets.")
