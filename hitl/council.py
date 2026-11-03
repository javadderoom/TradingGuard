"""
TradingGuard HITL - Institutional AI Investment Council Engine
Simulates an elite 5-member proprietary trading & investment committee:
1. Chief ICT & SMC Technical Strategist
2. Chief Macro & Geopolitical Economist
3. Head of Market Sentiment & TradingView Community Intelligence
4. Chief Risk Officer (CRO - Enforces $12 Risk Ceiling & Invalidation)
5. Chief Investment Officer (CIO - Final Executive Consensus Directive)

Executed via native Google Antigravity binary (agy.exe) with zero financial cost.
"""

import os
import sys
import re
import shutil
import subprocess
import datetime
from pathlib import Path
from typing import Optional, Dict, Any

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.macro_calendar import format_fundamental_summary, get_upcoming_events
from hitl.sentiment_feed import format_sentiment_summary
from hitl.mt5_engine import MT5Engine
from hitl.council_memory import get_institutional_memory_prompt
import MetaTrader5 as mt5


def parse_council_decision(report: Optional[str]) -> str:
    """
    Strictly extracts the Council's final consensus decision from the report.
    Returns: 'BUY_LIMIT', 'SELL_LIMIT', or 'STAND_ASIDE'
    """
    if not report:
        return "STAND_ASIDE"

    # 1. Match explicit Council Decision line (e.g. "• **Council Decision:** [BUY LIMIT | SELL LIMIT | STAND ASIDE]")
    m = re.search(r'(?i)Council\s+Decision[:\* ]+\s*\[?\s*(BUY[ _]LIMIT|SELL[ _]LIMIT|STAND[ _]ASIDE)', report)
    if m:
        return m.group(1).upper().replace(' ', '_')

    # 2. Match CIO Executive Consensus line
    m_cio = re.search(r'(?i)(?:Consensus|Directive|Verdict)[:\* ]+\s*\[?\s*(BUY[ _]LIMIT|SELL[ _]LIMIT|STAND[ _]ASIDE)', report)
    if m_cio:
        return m_cio.group(1).upper().replace(' ', '_')

    # 3. If explicit STAND ASIDE is stated in directive section
    if re.search(r'(?i)\bSTAND[ _]ASIDE\b', report):
        return "STAND_ASIDE"

    return "STAND_ASIDE"


def find_agy_binary() -> str:
    """Locates the local Antigravity CLI executable."""
    found = shutil.which("agy")
    if found:
        return found
    
    # Common default paths on Windows
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(local_app_data, "agy", "bin", "agy.exe"),
        r"C:\Users\Javad\AppData\Local\agy\bin\agy.exe"
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
            
    return "agy"


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
            lines.append("⚠️ CRITICAL GOVERNANCE MANDATE (RULE-RISK-010): An active position/order is ALREADY OPEN on this symbol. Do NOT suggest a duplicate trade in the same direction or within the same structural zone. CRO must immediately VETO (STAND ASIDE) duplicate exposure.")
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
        import datetime
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
        "sentiment_brief": sentiment_brief,
        "telemetry_prompt": telemetry_prompt,
        "tools_prompt": tools_prompt,
        "landmarks": landmarks,
        "active_exposure_prompt": active_exposure_prompt,
        "open_positions": open_positions,
        "pending_orders": pending_orders
    }


def convene_investment_council(symbol: str = "XAUUSD", mode: str = "tactical") -> Optional[str]:
    """
    Convenes the Antigravity AI Investment Council.
    mode='tactical': High-speed 4-seat execution strike team (ICT, CRO, CIO, CDO)
                     with pre-locked Tier 1 Macro & Sentiment directives.
    mode='full': Deep strategic 6-seat committee review with full macro/sentiment debates.
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

    if mode == "tactical":
        prompt = (
            f"You are the Antigravity Tactical Execution Strike Team, an elite proprietary trading committee.\n"
            f"Execute an institutional tactical review for {sym}.\n\n"
            f"{memory_prompt}\n\n"
            f"=== TIER 1: PRE-LOCKED SESSION MACRO & SENTIMENT DIRECTIVE ===\n"
            f"• Mandatory Directional Filter: {intel.get('macro_bias_prompt', '')}\n"
            f"• Macro & Calendar Catalysts: {intel['macro_brief']}\n"
            f"• Retail Sentiment Baseline: {intel['sentiment_brief']}\n"
            f"⚠️ Operational Mandate: Macro bias is PRE-LOCKED. You are the real-time Execution Team (ICT, CRO, CIO, CDO). Do NOT debate macroeconomics. Focus 100% on sweep validation, displacement MSS, structural stop pinning, and risk asymmetry.\n\n"
            f"{tools_str}\n\n"
            f"{tel_prompt}\n\n"
            f"=== MULTI-TIMEFRAME CHART DOSSIER ===\n"
            f"- 1D Daily Chart: '{p_1d.as_posix()}'\n"
            f"- 1H Trend Chart: '{p_1h.as_posix()}'\n"
            f"- 15M Structure Chart: '{p_15m.as_posix()}'\n"
            f"- 5M Execution Chart: '{p_5m.as_posix()}'\n\n"
            f"=== LIVE MARKET DATA & BROKER METRICS ===\n"
            f"- Current Bid: {bid_str} | Ask: {ask_str} (Spread: {intel['spread_pts']} pts)\n"
            f"- US Dollar Index (USDX): {intel['usdx_bid']:.2f} / {intel['usdx_ask']:.2f}\n\n"
            f"{intel.get('active_exposure_prompt', '')}\n\n"
            f"=== ADVANCED SMC & FIRM GOVERNANCE RULES ===\n"
            f"1. Limit Orders ONLY. Market orders are strictly prohibited.\n"
            f"2. Strict $17.00 max risk per trade (0.01 lot base). Stop loss must never exceed this ceiling.\n"
            f"3. Anchor limit entry at the Proximal Edge of a Fair Value Gap (FVG) or Breaker Block following MSS. On pro-trend sweeps, enter at FVG proximal edge.\n"
            f"4. Objective Structural Targets: Aim Take Profit at major Targeted Weak Swings (BSL/SSL) or HTF ATR expansion pool (RULE-TARGET-041).\n"
            f"5. SMT Alignment: Confirm correlation alignment or SMT divergence against USDX / sister FX pair.\n"
            f"6. Minimum Risk-to-Reward (R:R) must be 1:3.0 or higher. Veto any setup below 1:3.0.\n"
            f"7. Directional Confluence & Session Sweep Rule:\n"
            f"   - Pro-trend setups aligning with Tier 1 Macro Filter aim for External Liquidity Pools / Daily High-Low expansions.\n"
            f"   - SELECTIVE COUNTER-TREND IS FULLY AUTHORIZED: If price sweeps a prominent session benchmark (Asian High/Low or Prior Day High/Low) and confirms a Market Structure Shift (MSS) with displacement FVG on M1/M5, the Council is explicitly AUTHORIZED to trade the counter-trend retracement.\n"
            f"   - Counter-trend setups must strictly target Internal Liquidity (opposing session FVG / Equilibrium / Asian Range midpoint) with R:R >= 1:3.0.\n"
            f"8. Zero Duplicate Exposure Defense (RULE-RISK-010): If an active position or pending order is already open for this symbol in the same direction or within the same structural zone, the Chief Risk Officer (CRO) must immediately issue a MANDATORY VETO (STAND ASIDE). The Council is strictly prohibited from proposing duplicate trades or stacking risk into an already-active trade zone.\n"
            f"9. Internal vs External Sweep Nuance: When HTF Macro is strongly locked pro-trend (e.g. BUY ONLY on Gold), a confirmed raid of Internal Liquidity (e.g. New York opening range micro-lows, session equal lows, or 15M discount swing lows) followed by M5 displacement MSS is an authentic, valid entry trigger. Do not demand that price completely sweep the outer London Low if institutional accumulation in discount is already confirmed by displacement body candle closes.\n\n"
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
            f"• **Developing Setup Context:**\n"
            f"• **Actionable 'IF-THEN' Re-Activation Trigger:**\n"
            f"• **Setup Invalidation Anchor:**\n\n"
            f"Maintain institutional discipline, precise numbers, and strict adherence to the $17 risk cap.\n"
            f"Keep the entire tactical report punchy, concise, and under 300 words total."
        )
    else:
        prompt = (
            f"You are the Antigravity Trading & Investment Council, an elite proprietary trading committee.\n"
            f"Conduct an institutional committee review for {sym}.\n\n"
            f"{memory_prompt}\n\n"
            f"{intel.get('macro_bias_prompt', '')}\n\n"
            f"{tools_str}\n\n"
            f"{tel_prompt}\n\n"
            f"=== MULTI-TIMEFRAME CHART DOSSIER ===\n"
            f"- 1D Daily Chart: '{p_1d.as_posix()}'\n"
            f"- 1H Trend Chart: '{p_1h.as_posix()}'\n"
            f"- 15M Structure Chart: '{p_15m.as_posix()}'\n"
            f"- 5M Execution Chart: '{p_5m.as_posix()}'\n\n"
            f"=== LIVE MARKET DATA & BROKER METRICS ===\n"
            f"- Current Bid: {bid_str} | Ask: {ask_str} (Spread: {intel['spread_pts']} pts)\n"
            f"- US Dollar Index (USDX): {intel['usdx_bid']:.2f} / {intel['usdx_ask']:.2f}\n\n"
            f"=== MACROECONOMIC & GEOPOLITICAL ENVIRONMENT ===\n"
            f"{intel['macro_brief']}\n\n"
            f"=== TRADINGVIEW COMMUNITY & SENTIMENT RECONNAISSANCE ===\n"
            f"{intel['sentiment_brief']}\n\n"
            f"=== ADVANCED SMC & FIRM GOVERNANCE RULES ===\n"
            f"1. Limit Orders ONLY. Market orders are strictly prohibited.\n"
            f"2. Strict $17.00 max risk per trade (0.01 lot base). Stop loss must never exceed this ceiling including spread/commission.\n"
            f"3. Advanced SMC Execution Models: Anchor limit entry at the Proximal Edge of a Fair Value Gap (FVG), a confirmed Breaker Block (BB), or an Optimal Trade Entry (OTE 62%-79% Fibonacci discount/premium zone) following a Market Structure Shift (MSS).\n"
            f"   - [RULE-EXEC-036 POI Depth Scaling]: If the POI or zone width exceeds 6.0 pips (FX) or $2.00 (Gold), outer proximal edge entry (0%) is strictly prohibited. Scale entry deeper to the 50% Mean Threshold (MT) or 70%-75% Deep Retracement (OTE) to compress SL and guarantee R:R >= 1:3.0.\n"
            f"4. Inducement & Liquidity Targets: Identify internal liquidity inducement (IDM) and aim Take Profit at major Buy-Side (BSL), Sell-Side (SSL), or Equal Highs/Lows (EQH/EQL).\n"
            f"5. SMT Alignment: Confirm correlation alignment or SMT divergence against USDX.\n"
            f"6. Minimum Risk-to-Reward (R:R) must be 1:3.0 or higher. Any setup targeting an opposing liquidity pool that yields less than 1:3.0 must be strictly vetoed (STAND ASIDE).\n"
            f"7. Directional Confluence & Session Sweep Rule: Pro-trend setups align with HTF Macro Bias targeting external pools. Selective counter-trend mean-reversion is authorized if price sweeps prominent session liquidity (Asian High/Low or PDH/PDL) with confirmed M5 displacement MSS, targeting internal liquidity (opposing FVG or Asian range equilibrium) with R:R >= 1:3.0.\n"
            f"8. If technical, macro, or sentiment factors are conflicting or risk is asymmetric against us, order STAND ASIDE.\n\n"
            f"Deliver the Council's deliberative findings strictly in the following format:\n\n"
            f"🏛️ **ANTIGRAVITY AI INVESTMENT COUNCIL: {sym}**\n\n"
            f"👨‍💻 **1. Chief ICT & Technical Strategist (Advanced SMC & Order Flow)**\n"
            f"• 1D Macro Order Flow & Institutional Bias:\n"
            f"• SMC POIs (FVGs, Breaker Blocks, OTE 62-79% Discount/Premium):\n"
            f"• Liquidity Sweeps (Judas Swings) & Market Structure Shift (MSS):\n\n"
            f"🌐 **2. Chief Macro & Geopolitical Economist**\n"
            f"• Central Bank Policy & USDX / SMT Divergence Alignment:\n"
            f"• HTF Fundamental Bias & Mandatory Directional Filter [BUY ONLY / SELL ONLY / SELECTIVE]:\n"
            f"• Scheduled Economic Events & Volatility Window Risk:\n\n"
            f"👥 **3. Head of Sentiment & TradingView Community Intelligence**\n"
            f"• Retail Crowd Positioning & Consensus Assessment:\n"
            f"• Retail Trap / Liquidity Engineering Analysis (Where are retail stops clustered?):\n\n"
            f"🛡️ **4. Chief Risk Officer (CRO - Capital Defense & Invalidation)**\n"
            f"• Structural Invalidation Level (Where is the setup objectively dead?):\n"
            f"• Playbook Calibration & Risk Check (Mandate min 4.0-7.0 pt SL buffer on Gold, no micro-stops, strict $17 cap, verify R:R >= 1:3.0):\n\n"
            f"⚖️ **5. CIO Executive Consensus Directive**\n"
            f"• **Council Decision:** [BUY LIMIT | SELL LIMIT | STAND ASIDE]\n"
            f"• **Actionable Execution Plan (if applicable):** Entry: `X.XX` | SL: `X.XX` | TP: `X.XX` | Lot: `0.01` | R:R: `1:X.X` (Mandatory >= 1:3.0)\n"
            f"• **Playbook Alignment:** (Confirm alignment with Active Institutional Rules e.g. entry anchor / stop buffer).\n"
            f"• **Executive Summary & Critical Trigger:** (Clear 2-sentence institutional synthesis on why this decision was reached and what condition triggers immediate stand-down).\n\n"
            f"📋 **6. Chief Watchlist & Developing Opportunities Officer (CDO - Tactical Reconnaissance)**\n"
            f"• **Developing Setup Context:** (What setup is currently incubating or incomplete? e.g. Unswept Asian high/low, shallow retracement, pending CPI/NFP news).\n"
            f"• **Actionable 'IF-THEN' Re-Activation Trigger:** (Exact conditional trigger: e.g. 'IF price sweeps X.XX and prints a 5M bullish displacement candle, THEN re-evaluate for a BUY LIMIT at Y.YY').\n"
            f"• **Setup Invalidation Anchor:** (Price level where this potential watchlist idea is completely invalidated).\n\n"
            f"Maintain institutional discipline, precise numbers, and strict adherence to the $17 risk cap.\n"
            f"Keep the entire council report concise, punchy, and under 500 words total. Avoid excessive fluff or boilerplate."
        )

    cmd = [
        agy_bin,
        "--dangerously-skip-permissions",
        "--model", "gemini-3.8-flash-low",
        "-p", prompt
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60
        )

        if proc.returncode != 0:
            print(f"[Council] agy execution failed ({proc.returncode}): {proc.stderr}")
            return None

        output = proc.stdout.strip()
        lines = [line for line in output.splitlines() if not line.startswith("jetski:")]
        clean_text = "\n".join(lines).strip()
        return clean_text if clean_text else None

    except subprocess.TimeoutExpired:
        print("[Council] Council deliberation timed out after 60 seconds.")
        return None
    except Exception as e:
        print(f"[Council] Exception during council invocation: {e}")
        return None


if __name__ == "__main__":
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    print("=" * 60)
    print("Convening Antigravity AI Trading Council for Gold (XAUUSD)...")
    print("=" * 60)
    result = convene_investment_council("XAUUSD")
    if result:
        print(result)
    else:
        print("Failed to convene council or missing assets.")
