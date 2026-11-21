"""
TradingGuard Fundamental Engine - Telegram & Institutional Prompt Formatters
"""

from typing import Any, Dict, List, Optional, Tuple

from hitl.fundamental.governor import get_enforcement_mode, normalize_fundamental_symbol

_ASSET_ICONS = {
    "XAUUSD": "🥇",
    "XAGUSD": "🥈",
    "EURUSD": "💶",
    "GBPUSD": "💷",
    "USDJPY": "💴",
    "NQ": "💻",
    "SPX": "📈",
    "HK50": "🇭🇰",
    "BTCUSD": "🪙",
    "ETHUSD": "🔷",
    "USCRUDE": "🛢️",
}


def _bias_icon(bias: str, score: int = 0) -> str:
    b = (bias or "").upper()
    if "BULLISH" in b or score >= 20:
        return "🟢"
    if "BEARISH" in b or score <= -20:
        return "🔴"
    return "🟡"


def _tape_badge(tag: str) -> str:
    t = (tag or "").upper()
    if t == "CONFIRMED_BY_TAPE":
        return "✅ Tape Confirmed"
    if t == "CONTRADICTED_BY_TAPE":
        return "❌ Contradicted by Tape"
    return "⚠️ Partial Tape Evidence"


def _fmt_val(v: Optional[float], suffix: str = "", signed: bool = False) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.2f}{suffix}" if signed else f"{v:.2f}{suffix}"


def _fmt_bps(v: Optional[float]) -> str:
    if v is None:
        return "N/A"
    return f"{v:+.1f}bps"


def _build_macro_tape_lines(dossier: Dict[str, Any]) -> List[str]:
    d = dossier.get("diagnostics", {})
    return [
        f"• *Rates:* Nom10Y `{_fmt_val(d.get('nom_10y_level'), '%')}` (`{_fmt_bps(d.get('nom_10y_5d_bps'))}` 5D) | "
        f"*Real 10Y:* `{_fmt_val(d.get('real_10y_level'), '%')}` (`{_fmt_bps(d.get('real_10y_5d_bps'))}` 5D)",
        f"• *Breakeven/Curve:* 10Y BE `{_fmt_val(d.get('breakeven_10y_level'), '%')}` (`{_fmt_bps(d.get('breakeven_5d_bps'))}`) | "
        f"2s10s `{_fmt_val(d.get('slope_2s10s'), '%')}`",
        f"• *Dollar/Vol/Credit:* DXY `{_fmt_val(d.get('dxy_level'))}` (`{_fmt_val(d.get('dxy_5d_pct'), '%', True)}` 5D) | "
        f"VIX `{_fmt_val(d.get('vix_level'))}` | HYG-SHY `{_fmt_val(d.get('credit_stress_5d_pct'), '%', True)}`",
        f"• *Cross-Asset:* SPX `{_fmt_val(d.get('spx_5d_pct'), '%', True)}` | TLT `{_fmt_val(d.get('tlt_5d_pct'), '%', True)}` | "
        f"HK50 `{_fmt_val(d.get('hk50_5d_pct'), '%', True)}` | Oil `{_fmt_val(d.get('oil_5d_pct'), '%', True)}`",
    ]


def format_global_macro_card(dossier: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Formats the multi-asset Global Causal Macro Scoreboard card + Telegram inline keyboard."""
    reg = dossier.get("global_macro_regime", {})
    mode = get_enforcement_mode()
    mode_badge = "🛡️ *Advisory* (Info Only)" if mode == "advisory" else "⛔ *Hard Veto* (High-Conviction Block)"
    source_lbl = str(dossier.get("analysis_source", "unknown")).replace("_", " ")

    lines: List[str] = [
        "🌐 *TradingGuard Causal Macro Intelligence*",
        f"⏱ *Updated:* `{dossier.get('generated_at_utc', 'N/A')}` | Engine: `{source_lbl}`",
        f"⚙️ *Execution Gate:* {mode_badge}",
        "",
        f"🧭 *Global Regime:* `{reg.get('label', 'N/A')}`",
        f"📌 *Theme:* _{reg.get('dominant_theme', 'N/A')}_",
        f"💬 {reg.get('summary', '')}",
        "",
        "📊 *LIVE MACRO TAPE (5D Impulse):*",
        *_build_macro_tape_lines(dossier),
        "",
        "🔗 *ACTIVE CAUSAL TRANSMISSION CHAINS:*",
    ]

    for ch in (dossier.get("causal_chains") or [])[:3]:
        lines.append(f"• *[{_tape_badge(ch.get('tape_verification', ''))}]* {ch.get('event', '')}")
        steps = ch.get("transmission_steps") or []
        if steps:
            lines.append("  " + " → ".join(str(s) for s in steps[:3]))
        ev_str = ch.get("tape_evidence")
        if ev_str:
            lines.append(f"  _Proof:_ `{ev_str}`")

    lines.append("")
    lines.append("🎯 *MULTI-ASSET SCOREBOARD (-100 to +100):*")
    assets = dossier.get("assets", {})
    for sym, a in assets.items():
        icon = _ASSET_ICONS.get(sym, "🔹")
        b_ic = _bias_icon(a.get("bias", ""), a.get("score", 0))
        bias_clean = str(a.get("bias", "NEUTRAL")).replace("_", " ")
        conf_pct = int(float(a.get("confidence", 0.0)) * 100)
        lines.append(f"{icon} *{sym}:* {b_ic} `{bias_clean}` (`{int(a.get('score', 0)):+d}` | {conf_pct}%)")

    toggle_lbl = "⛔ Switch to Hard Veto" if mode == "advisory" else "🛡️ Switch to Advisory"
    keyboard = {
        "inline_keyboard": [
            [
                {"text": "🥇 XAUUSD", "callback_data": "macro_asset_XAUUSD"},
                {"text": "🥈 XAGUSD", "callback_data": "macro_asset_XAGUSD"},
                {"text": "💻 NQ", "callback_data": "macro_asset_NQ"},
                {"text": "📈 SPX", "callback_data": "macro_asset_SPX"},
            ],
            [
                {"text": "💶 EURUSD", "callback_data": "macro_asset_EURUSD"},
                {"text": "💷 GBPUSD", "callback_data": "macro_asset_GBPUSD"},
                {"text": "💴 USDJPY", "callback_data": "macro_asset_USDJPY"},
                {"text": "🪙 BTCUSD", "callback_data": "macro_asset_BTCUSD"},
            ],
            [
                {"text": "🇭🇰 HK50", "callback_data": "macro_asset_HK50"},
                {"text": "🔷 ETHUSD", "callback_data": "macro_asset_ETHUSD"},
                {"text": "🛢️ USCRUDE", "callback_data": "macro_asset_USCRUDE"},
            ],
            [
                {"text": "🔄 Refresh Macro", "callback_data": "macro_refresh"},
                {"text": toggle_lbl, "callback_data": "macro_toggle_mode"},
            ],
        ]
    }
    return "\n".join(lines), keyboard


def format_asset_macro_card(dossier_or_view: Dict[str, Any], symbol: str = "XAUUSD") -> Tuple[str, Dict[str, Any]]:
    """Formats a single-asset causal deep-dive card + inline keyboard."""
    norm_sym = normalize_fundamental_symbol(symbol)
    if "assets" in dossier_or_view and isinstance(dossier_or_view["assets"], dict):
        asset = dossier_or_view["assets"].get(norm_sym, {})
        reg = dossier_or_view.get("global_macro_regime", {})
        chains = dossier_or_view.get("causal_chains", [])
        cot = (dossier_or_view.get("cot_positioning") or {}).get(norm_sym)
        gen_utc = dossier_or_view.get("generated_at_utc", "N/A")
        tape_src = dossier_or_view
    else:
        asset = dossier_or_view
        reg = dossier_or_view.get("global_macro_regime", {})
        chains = dossier_or_view.get("causal_chains", [])
        cot = dossier_or_view.get("cot")
        gen_utc = dossier_or_view.get("generated_at_utc", "N/A")
        tape_src = dossier_or_view

    score = int(asset.get("score", 0) or 0)
    bias = str(asset.get("bias", "NEUTRAL")).replace("_", " ")
    conf_pct = int(float(asset.get("confidence", 0.0) or 0.0) * 100)
    b_ic = _bias_icon(bias, score)
    icon = _ASSET_ICONS.get(norm_sym, "🌐")
    hb = asset.get("horizon_bias", {})

    lines: List[str] = [
        f"{icon} *{norm_sym} — Causal Fundamental Deep Dive*",
        f"⏱ *Generated:* `{gen_utc}` | *Global Regime:* `{reg.get('label', 'N/A')}`",
        "",
        f"⚖️ *Directional Bias:* {b_ic} *{bias}* (Score: `{score:+d}` | Conf: `{conf_pct}%`)",
        f"• *Intraday:* `{hb.get('intraday', 'N/A')}` | *Swing 1-5D:* `{hb.get('swing_1_5d', 'N/A')}` | *Macro 1-4W:* `{hb.get('macro_1_4w', 'N/A')}`",
        f"• *Posture:* `{str(asset.get('execution_posture', 'TWO_WAY_SELECTIVE')).replace('_', ' ')}`",
        "",
        f"⚙️ *Dominant Mechanism:*",
        f"_{asset.get('dominant_mechanism', 'Balanced macro drivers')}_",
        "",
        "🟢 *Bullish Tailwinds:*",
    ]
    for bf in (asset.get("bullish_forces") or ["None dominant"])[:3]:
        lines.append(f"  + {bf}")

    lines.append("")
    lines.append("🔴 *Bearish Headwinds:*")
    for sf in (asset.get("bearish_forces") or ["None dominant"])[:3]:
        lines.append(f"  - {sf}")

    # Relevant causal chains
    rel_chains = []
    for ch in chains:
        aff = ch.get("affected_assets") or {}
        if norm_sym in aff or not aff:
            rel_chains.append(ch)
    if not rel_chains:
        rel_chains = chains[:2]

    if rel_chains:
        lines.append("")
        lines.append("🔗 *Transmission Chains:*")
        for ch in rel_chains[:2]:
            lines.append(f"• *[{_tape_badge(ch.get('tape_verification', ''))}]* {ch.get('event', '')}")
            if ch.get("transmission_steps"):
                lines.append("  " + " → ".join(str(s) for s in ch["transmission_steps"][:3]))

    lines.append("")
    lines.append("📊 *Live Tape Snapshot:*")
    lines.extend(_build_macro_tape_lines(tape_src))

    if cot:
        lines.append(
            f"• *CFTC COT ({cot.get('report_date')}):* Net `{cot.get('net_contracts', 0):+,}` "
            f"(WoW `{cot.get('net_change_wow', 0):+,}` | Long `{cot.get('long_pct', 50)}%` | `{cot.get('crowding_flag')}`)"
        )

    lines.append("")
    lines.append(f"⛔ *Macro Invalidation:* `{asset.get('invalidation_trigger', 'Yield/DXY trend flip')}`")

    kb = {
        "inline_keyboard": [
            [
                {"text": "🔙 Global Macro Scoreboard", "callback_data": "macro_global"},
                {"text": "🔄 Refresh Macro", "callback_data": "macro_refresh"},
            ]
        ]
    }
    return "\n".join(lines), kb


def format_council_macro_block(asset_view: Dict[str, Any], symbol: Optional[str] = None) -> str:
    """
    Renders a clean, non-contradictory institutional fundamental dossier block
    for Council Seat #2 (Macro Officer) and SubQ Snap Decision prompts.
    """
    sym = normalize_fundamental_symbol(symbol or asset_view.get("symbol", "XAUUSD"))
    # Handle either single asset_view dict or full dossier dict gracefully
    if "assets" in asset_view and isinstance(asset_view["assets"], dict):
        asset = asset_view["assets"].get(sym, {})
        reg = asset_view.get("global_macro_regime", {})
        chains = asset_view.get("causal_chains", [])
        diag = asset_view.get("diagnostics", {})
        cot = (asset_view.get("cot_positioning") or {}).get(sym)
        src = asset_view.get("analysis_source", "fundamental_engine")
    else:
        asset = asset_view
        reg = asset_view.get("global_macro_regime", {})
        chains = asset_view.get("causal_chains", [])
        diag = asset_view.get("diagnostics", {})
        cot = asset_view.get("cot")
        src = asset_view.get("analysis_source", "fundamental_engine")

    score = int(asset.get("score", asset_view.get("score", 0)) or 0)
    bias = str(asset.get("bias", asset_view.get("htf_fundamental_bias", "NEUTRAL"))).upper()
    conf = float(asset.get("confidence", asset_view.get("confidence", 0.5)) or 0.5)
    mode = get_enforcement_mode()

    lines = [
        f"=== CAUSAL FUNDAMENTAL & OFF-CHART INTELLIGENCE: {sym} ===",
        f"• Engine Source: {src} | Enforcement Mode: {mode.upper()}",
        f"• Global Regime: [{reg.get('label', 'N/A')}] — {reg.get('dominant_theme', '')}",
        f"• {sym} Fundamental Bias: [{bias}] (Score: {score:+d}/100 | Confidence: {int(conf * 100)}%)",
        f"• Dominant Mechanism: {asset.get('dominant_mechanism', asset_view.get('macro_narrative', 'N/A'))}",
        f"• Bullish Forces: {'; '.join(asset.get('bullish_forces') or ['None dominant'])}",
        f"• Bearish Forces: {'; '.join(asset.get('bearish_forces') or ['None dominant'])}",
        f"• Sovereign Tape: US10Y Nom={diag.get('nom_10y_level', 'N/A')}% ({diag.get('nom_10y_5d_bps', 'N/A')} bps 5D), "
        f"US10Y Real={diag.get('real_10y_level', 'N/A')}% ({diag.get('real_10y_5d_bps', 'N/A')} bps 5D), "
        f"DXY={diag.get('dxy_level', 'N/A')} ({diag.get('dxy_5d_pct', 'N/A')}% 5D), VIX={diag.get('vix_level', 'N/A')}, "
        f"Bond-Eq Co-Selloff={diag.get('bond_equity_co_selloff')}, Asia Stress={diag.get('asia_china_stress')}",
    ]
    if cot:
        lines.append(
            f"• Official CFTC COT ({cot.get('report_date')}): Net {cot.get('net_contracts', 0):+,} "
            f"(WoW {cot.get('net_change_wow', 0):+,}, Long {cot.get('long_pct', 50)}%, {cot.get('crowding_flag')})"
        )
    if chains:
        lines.append("• Active Verified Causal Chains:")
        for ch in chains[:3]:
            steps_s = " -> ".join(ch.get("transmission_steps") or [])
            lines.append(f"  - [{ch.get('tape_verification')}] {ch.get('event')}: {steps_s} (Proof: {ch.get('tape_evidence')})")
    lines.append(f"• Macro Invalidation Trigger: {asset.get('invalidation_trigger', 'N/A')}")
    lines.append("==================================================================")
    return "\n".join(lines)
