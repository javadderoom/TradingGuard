"""
TradingGuard HITL - Institutional Council Memory & Continuous Learning Engine
Maintains an evolving, self-calibrating Institutional Playbook across sessions:
1. Executed Trade Post-Mortems (Wins vs. Losses & Root Causes).
2. Counterfactual Stand-Aside Audits (Forward MFE/MAE on passed setups).
3. Active Institutional Playbook Calibration Rules (Injected dynamically into Council prompts).
4. Persists to `hitl/memory/council_playbook.json` and human-readable `institutional_playbook.md`.
"""

import json
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

MEMORY_DIR = Path(__file__).resolve().parent / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

PLAYBOOK_JSON_PATH = MEMORY_DIR / "council_playbook.json"
PLAYBOOK_MD_PATH = MEMORY_DIR / "institutional_playbook.md"


DEFAULT_PLAYBOOK: Dict[str, Any] = {
    "version": "1.0.0",
    "last_updated": datetime.datetime.now().isoformat(),
    "active_rules": [
        {
            "id": "RULE-EXEC-001",
            "category": "Risk & Execution Calibration",
            "symbol": "XAUUSD",
            "rule": "Mandate Minimum 4.0 to 7.0 Point Structural Stop Buffer on Gold (Risk $4.00 - $7.00, well below $17 ceiling).",
            "rationale": "Empirical data shows Gold 5M ATR fluctuates between 3.5 and 5.0 points. Stops tighter than 3.0 points (e.g., 1.64 pt and 2.65 pt stops in October) are choked by broker spread expansion and normal volatility noise before the thesis can mature.",
            "status": "ACTIVE"
        },
        {
            "id": "RULE-ENTRY-002",
            "category": "Setup Selection & Entry Calibration",
            "symbol": "XAUUSD",
            "rule": "Anchor Directly at Breaker Block Proximal Edge Following Clean Judas Liquidity Sweeps.",
            "rationale": "In high-conviction NY Open expansions (e.g., Oct 1 Session 2), the Council stood aside waiting for deeper PDL mitigation (4147.47) and missed a +34.44 point expansion from 4153 to 4187. When a 5M Breaker Block is established with liquidity sweep, enter at the proximal edge without demanding excessive discount.",
            "status": "ACTIVE"
        },
        {
            "id": "RULE-VETO-003",
            "category": "Capital Preservation & Veto Governance",
            "symbol": "ALL",
            "rule": "Strict Veto on Range Low/High Sweeps Lacking Immediate 5M Counter-Displacement.",
            "rationale": "Counterfactual audit confirms that standing aside on sweeps lacking immediate 5M displacement (e.g., Oct 7 London Open) prevented a catastrophic -16.46 point falling-knife loss. Capital preservation vetoes have demonstrated 100% protective efficacy.",
            "status": "ACTIVE"
        },
        {
            "id": "RULE-TREND-004",
            "category": "Macro & Higher-Timeframe Alignment",
            "symbol": "XAUUSD",
            "rule": "Exercise Extreme Caution on Intraday Shorts During Pro-Trend Daily Bullish Expansions.",
            "rationale": "Short setups taken against strong 1D bullish order flow (e.g., Oct 15 London Open) suffer from aggressive dip-buying by institutional participants. Require explicit 15M MSS before authorizing counter-trend short entries.",
            "status": "ACTIVE"
        }
    ],
    "trade_post_mortems": [],
    "counterfactual_audits": []
}


class CouncilMemory:
    def __init__(self):
        self.playbook_file = PLAYBOOK_JSON_PATH
        self.md_file = PLAYBOOK_MD_PATH
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.playbook_file.exists():
            self._save_raw(DEFAULT_PLAYBOOK)
            return DEFAULT_PLAYBOOK
        try:
            with open(self.playbook_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[CouncilMemory] Error loading playbook: {e}. Reverting to defaults.")
            return DEFAULT_PLAYBOOK

    def _save_raw(self, data: Dict[str, Any]):
        data["last_updated"] = datetime.datetime.now().isoformat()
        with open(self.playbook_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._export_markdown(data)

    def save(self):
        self._save_raw(self.data)

    def record_trade_post_mortem(
        self,
        symbol: str,
        session_time: str,
        decision: str,
        entry: float,
        sl: float,
        tp: float,
        status: str,
        realized_pnl: float,
        root_cause: str,
        lesson: str
    ):
        """Logs an executed trade post-mortem."""
        entry_record = {
            "timestamp": session_time,
            "symbol": symbol,
            "decision": decision,
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "status": status,
            "realized_pnl": realized_pnl,
            "root_cause": root_cause,
            "lesson": lesson,
            "logged_at": datetime.datetime.now().isoformat()
        }
        self.data.setdefault("trade_post_mortems", []).append(entry_record)
        self.save()

    def record_counterfactual_audit(
        self,
        symbol: str,
        session_time: str,
        discussed_setup: str,
        cio_decision: str,
        forward_4h_max_gain: float,
        forward_4h_max_dd: float,
        forward_4h_close_change: float,
        verdict: str,
        lesson: str
    ):
        """Logs a counterfactual audit of a debated Stand-Aside setup."""
        audit_record = {
            "timestamp": session_time,
            "symbol": symbol,
            "discussed_setup": discussed_setup,
            "cio_decision": cio_decision,
            "forward_4h_mfe": forward_4h_max_gain,
            "forward_4h_mae": forward_4h_max_dd,
            "forward_4h_close_delta": forward_4h_close_change,
            "verdict": verdict,  # e.g. "MISSED_WINNER", "PROTECTIVE_VETO", "CHOP"
            "lesson": lesson,
            "logged_at": datetime.datetime.now().isoformat()
        }
        self.data.setdefault("counterfactual_audits", []).append(audit_record)
        self.save()

    def add_active_rule(self, rule_id: str, category: str, symbol: str, rule: str, rationale: str):
        """Adds or updates an active institutional playbook rule."""
        rules = self.data.setdefault("active_rules", [])
        # Check if exists
        for r in rules:
            if r["id"] == rule_id:
                r["category"] = category
                r["symbol"] = symbol
                r["rule"] = rule
                r["rationale"] = rationale
                r["status"] = "ACTIVE"
                self.save()
                return
        rules.append({
            "id": rule_id,
            "category": category,
            "symbol": symbol,
            "rule": rule,
            "rationale": rationale,
            "status": "ACTIVE"
        })
        self.save()

    def get_playbook_prompt_section(self, symbol: str = "XAUUSD") -> str:
        """
        Generates the institutional memory prompt injection for the Council.
        Dynamically arms the 6 seats with the lessons learned and calibration rules.
        """
        rules = self.data.get("active_rules", [])
        sym_clean = symbol.upper()
        relevant_rules = []
        for r in rules:
            if r.get("status") != "ACTIVE":
                continue
            r_sym = r.get("symbol", "").upper()
            if r_sym == "ALL":
                relevant_rules.append(r)
            elif sym_clean in r_sym:
                relevant_rules.append(r)
            elif ("XAU" in sym_clean or "XAG" in sym_clean) and ("METALS" in r_sym or "XAU" in r_sym and "XAG" in r_sym):
                relevant_rules.append(r)

        if not relevant_rules:
            return ""

        lines = [
            "=== INSTITUTIONAL MEMORY & PLAYBOOK CALIBRATION (LEARNED LESSONS) ===",
            "The Council must strictly honor the following empirical rules synthesized from past trading sessions and counterfactual post-mortems:"
        ]
        for idx, r in enumerate(relevant_rules, 1):
            lines.append(f"{idx}. [{r.get('id', 'RULE')} | {r['category'].upper()}]: {r['rule']}")
            lines.append(f"   • Rationale/Evidence: {r['rationale']}")

        # Add recent post-mortem warnings if any
        recent_audits = self.data.get("counterfactual_audits", [])[-3:]
        if recent_audits:
            lines.append("\nRecent Counterfactual Post-Mortem Highlights:")
            for a in recent_audits:
                lines.append(
                    f"• {a['timestamp']} ({a['symbol']}): Verdict [{a['verdict']}] -> {a['lesson']}"
                )

        lines.append("=" * 65)
        return "\n".join(lines)

    def _export_markdown(self, data: Dict[str, Any]):
        """Generates a human-readable institutional playbook markdown document."""
        md_lines = [
            "# 🏛️ TradingGuard Institutional AI Playbook & Memory Ledger",
            f"**Last Calibration:** `{data.get('last_updated', 'N/A')}` | **Version:** `{data.get('version', '1.0.0')}`\n",
            "This playbook represents the continuous learning feedback loop of the Antigravity 6-Seat Investment Council.",
            "It is updated dynamically after every executed trade and every counterfactual audit of debated stand-asides.\n",
            "---",
            "## 📌 Active Rules of Engagement & Calibration Directives\n"
        ]

        for r in data.get("active_rules", []):
            status_icon = "🟢" if r.get("status") == "ACTIVE" else "⚪"
            md_lines.append(f"### {status_icon} [{r.get('id')}] {r.get('category')} ({r.get('symbol')})")
            md_lines.append(f"**Directive:** {r.get('rule')}")
            md_lines.append(f"> **Empirical Rationale:** {r.get('rationale')}\n")

        # Counterfactual Audits
        md_lines.append("---\n## 🔍 Recent Counterfactual Stand-Aside Audits\n")
        audits = data.get("counterfactual_audits", [])
        if not audits:
            md_lines.append("*No counterfactual audits logged yet.*\n")
        else:
            md_lines.append("| Timestamp | Symbol | Debated Setup | 4h Max Excursion | Outcome / Verdict | Playbook Lesson |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for a in audits:
                verdict_badge = f"**{a.get('verdict')}**"
                excursion = f"+{a.get('forward_4h_mfe', 0.0):.2f} / -{a.get('forward_4h_mae', 0.0):.2f} pts"
                md_lines.append(
                    f"| {a.get('timestamp')} | {a.get('symbol')} | {a.get('discussed_setup')[:35]}... | {excursion} | {verdict_badge} | {a.get('lesson')} |"
                )

        # Trade Post-Mortems
        md_lines.append("\n---\n## 🎯 Executed Trade Post-Mortems\n")
        pm = data.get("trade_post_mortems", [])
        if not pm:
            md_lines.append("*No executed trade post-mortems logged yet.*\n")
        else:
            md_lines.append("| Timestamp | Symbol | Decision | Realized PnL | Root Cause Diagnosis | Permanent Lesson |")
            md_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- |")
            for p in pm:
                md_lines.append(
                    f"| {p.get('timestamp')} | {p.get('symbol')} | {p.get('decision')} | ${p.get('realized_pnl', 0.0):+.2f} | {p.get('root_cause')} | {p.get('lesson')} |"
                )

        with open(self.md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_lines))


# Global singleton instance
memory_engine = CouncilMemory()


def get_institutional_memory_prompt(symbol: str = "XAUUSD") -> str:
    """Helper for injecting into Council prompts."""
    return memory_engine.get_playbook_prompt_section(symbol)
