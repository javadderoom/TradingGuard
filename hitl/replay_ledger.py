"""
TradingGuard HITL - Visual Co-Backtesting Shared Ledger & Agentify Feedback Store
Provides:
- CoBacktestLedger: Persistent, atomic JSON CRUD over hitl/memory/visual_co_backtest_ledger.json
  tracking BOT, HUMAN_PROPOSED, and HUMAN_EDITED_BOT trades with $20 risk compliance badges.
- AgentifyFeedbackStore: Persistent, atomic JSON store over hitl/memory/visual_feedback_cases.json
  capturing forensic chart snapshots, screener telemetry, and copy-ready Antigravity prompts.
- build_agentify_prompt: Formats comprehensive markdown analysis bundles for Antigravity alignment.
"""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from hitl.replay_data import server_epoch_to_zones

DEFAULT_LEDGER_PATH = Path(__file__).resolve().parent / "memory" / "visual_co_backtest_ledger.json"
DEFAULT_FEEDBACK_PATH = Path(__file__).resolve().parent / "memory" / "visual_feedback_cases.json"

VALID_ORIGINS = ("BOT", "HUMAN_PROPOSED", "HUMAN_EDITED_BOT")


def get_symbol_pip_value(symbol: str) -> float:
    """Returns USD point/pip value per 0.01 lot for risk calculation."""
    sym = symbol.upper()
    if "XAU" in sym:
        return 1.0      # $1.00/point ($1/dollar)
    elif "XAG" in sym:
        return 50.0     # $50.00/point ($0.50/cent)
    elif "EUR" in sym or "GBP" in sym:
        return 1000.0   # $0.10/pip (1000x on 0.01 lot)
    elif "BTC" in sym:
        return 0.01     # $0.01/dollar
    elif any(k in sym for k in ("NQ", "NAS", "US100", "SPX", "US500", "YM", "US30", "DJ")):
        return 0.10     # $0.10/point
    return 1.0


def calculate_trade_risk_usd(symbol: str, entry: float, sl: float, lot: float = 0.01) -> float:
    """Calculates risk in USD for a given trade geometry at reference lot (0.01)."""
    pip_val = get_symbol_pip_value(symbol)
    risk_pts = abs(entry - sl)
    return round(risk_pts * pip_val * (lot / 0.01), 2)


class CoBacktestLedger:
    """Atomic JSON storage manager for shared Bot and Human co-backtest trades."""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = Path(file_path) if file_path else DEFAULT_LEDGER_PATH
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict[str, Any] = {"version": "1.0", "last_updated": None, "trades": []}
        self._load()

    def _load(self) -> None:
        """Loads state from JSON file if present."""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "trades" in data:
                        self.state = data
            except Exception as e:
                print(f"[CoBacktestLedger] Warning: Failed to load {self.file_path}: {e}")

    def _save(self) -> None:
        """Persists state to disk atomically using temporary file replace."""
        self.state["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        temp_path = self.file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            if temp_path.exists():
                temp_path.replace(self.file_path)
        except Exception as e:
            print(f"[CoBacktestLedger] Error saving ledger: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def list_trades(self, symbol: Optional[str] = None) -> List[Dict[str, Any]]:
        """Returns all trades, optionally filtered by symbol."""
        trades = self.state.get("trades", [])
        if symbol is not None:
            sym_clean = symbol.upper()
            return [t for t in trades if t.get("symbol", "").upper() == sym_clean]
        return list(trades)

    def add_trade(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Validates, completes, and persists a trade record."""
        origin = payload.get("origin")
        if origin not in VALID_ORIGINS:
            raise ValueError(f"Invalid trade origin '{origin}'. Must be one of {VALID_ORIGINS}")

        trade = dict(payload)
        symbol = trade.get("symbol", "UNKNOWN")

        # Generate unique trade_id if missing
        if "trade_id" not in trade or not trade["trade_id"]:
            prefix = origin[:3].upper()
            trade["trade_id"] = f"{prefix}-{symbol}-{uuid.uuid4().hex[:8]}"

        # Compute risk metrics if missing
        entry = float(trade.get("entry", 0.0))
        sl = float(trade.get("sl", 0.0))
        lot = float(trade.get("lot", 0.01))

        if "risk_usd_001" not in trade or trade["risk_usd_001"] is None:
            if entry and sl:
                trade["risk_usd_001"] = calculate_trade_risk_usd(symbol, entry, sl, lot=0.01)
            else:
                trade["risk_usd_001"] = 0.0

        if "exceeds_risk_cap" not in trade or trade["exceeds_risk_cap"] is None:
            trade["exceeds_risk_cap"] = trade["risk_usd_001"] > 20.0

        if "parent_bot_ref" not in trade:
            trade["parent_bot_ref"] = None

        if "created_at" not in trade:
            trade["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Append and save
        self.state.setdefault("trades", []).append(trade)
        self._save()
        return trade

    def update_trade(self, trade_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Applies patch to existing trade record by trade_id and persists."""
        trades = self.state.get("trades", [])
        for idx, t in enumerate(trades):
            if t.get("trade_id") == trade_id:
                updated = dict(t)
                updated.update(patch)

                # Recompute risk if entry or sl changed
                if "entry" in patch or "sl" in patch:
                    entry = float(updated.get("entry", 0.0))
                    sl = float(updated.get("sl", 0.0))
                    symbol = updated.get("symbol", "UNKNOWN")
                    if entry and sl:
                        updated["risk_usd_001"] = calculate_trade_risk_usd(symbol, entry, sl, lot=0.01)
                        updated["exceeds_risk_cap"] = updated["risk_usd_001"] > 20.0

                trades[idx] = updated
                self._save()
                return updated
        return None

    def delete_trade(self, trade_id: str) -> bool:
        """Deletes trade record by trade_id and persists."""
        trades = self.state.get("trades", [])
        initial_len = len(trades)
        self.state["trades"] = [t for t in trades if t.get("trade_id") != trade_id]
        if len(self.state["trades"]) < initial_len:
            self._save()
            return True
        return False

    def get_scorecard(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """Computes side-by-side performance scorecard grouped by origin."""
        trades = self.list_trades(symbol=symbol)

        def _calc_stats(trade_list: List[Dict[str, Any]]) -> Dict[str, Any]:
            total = len(trade_list)
            if total == 0:
                return {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "breakevens": 0,
                    "win_rate_pct": 0.0,
                    "net_pnl_usd": 0.0,
                    "net_rr": 0.0,
                    "profit_factor": 0.0,
                    "max_drawdown_usd": 0.0,
                }
            wins = [t for t in trade_list if t.get("status") == "WIN"]
            losses = [t for t in trade_list if t.get("status") == "LOSS"]
            bes = [t for t in trade_list if t.get("status") == "BREAKEVEN"]

            gross_win = sum(float(t.get("realized_pnl_usd", 0.0)) for t in wins)
            gross_loss = abs(sum(float(t.get("realized_pnl_usd", 0.0)) for t in losses))
            net_pnl = round(sum(float(t.get("realized_pnl_usd", 0.0)) for t in trade_list), 2)
            net_rr = round(sum(float(t.get("rr_realized", 0.0)) for t in trade_list if t.get("rr_realized") is not None), 2)

            pf = round(gross_win / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_win > 0 else 0.0)
            wr = round((len(wins) / total) * 100.0, 1)

            # Max drawdown tracking (strictly sorted by cash realization exit_time order)
            running = 0.0
            peak = 0.0
            max_dd = 0.0
            for t in sorted(trade_list, key=lambda x: (x.get("exit_time") or x.get("decision_time") or 0)):
                running += float(t.get("realized_pnl_usd", 0.0))
                if running > peak:
                    peak = running
                dd = peak - running
                if dd > max_dd:
                    max_dd = dd

            return {
                "total_trades": total,
                "wins": len(wins),
                "losses": len(losses),
                "breakevens": len(bes),
                "win_rate_pct": wr,
                "net_pnl_usd": net_pnl,
                "net_rr": net_rr,
                "profit_factor": pf,
                "max_drawdown_usd": round(max_dd, 2),
            }

        bot_trades = [t for t in trades if t.get("origin") == "BOT"]
        human_prop = [t for t in trades if t.get("origin") == "HUMAN_PROPOSED"]
        human_edit = [t for t in trades if t.get("origin") == "HUMAN_EDITED_BOT"]

        return {
            "BOT": _calc_stats(bot_trades),
            "HUMAN_PROPOSED": _calc_stats(human_prop),
            "HUMAN_EDITED_BOT": _calc_stats(human_edit),
            "ALL": _calc_stats(trades),
        }


def build_agentify_prompt(case: Dict[str, Any]) -> str:
    """Builds a copy-ready, structured Markdown prompt for Antigravity strategic alignment."""
    case_id = case.get("case_id", "CASE-UNKNOWN")
    symbol = case.get("symbol", "UNKNOWN")
    ts = case.get("timestamp", 0)
    zones = server_epoch_to_zones(ts) if ts else {}

    srv_str = zones.get("srv_str", "N/A")
    utc_str = zones.get("utc_str", "N/A")
    tehran_str = zones.get("tehran_str", "N/A")
    date_str = zones.get("date_str", "N/A")

    user_note = case.get("user_note") or "No notes provided."

    user_setup = case.get("user_setup")
    if not isinstance(user_setup, dict):
        user_setup = {}

    bot_trade = case.get("bot_trade")
    if not isinstance(bot_trade, dict):
        bot_trade = None

    diag = case.get("screener_diagnostics")
    if not isinstance(diag, dict):
        diag = {}

    # Extract user geometry
    u_dir = user_setup.get("direction", "N/A")
    u_entry = user_setup.get("entry", "N/A")
    u_sl = user_setup.get("sl", "N/A")
    u_tp = user_setup.get("tp", "N/A")

    # Extract bot geometry
    if bot_trade:
        b_dir = bot_trade.get("direction", "N/A")
        b_entry = bot_trade.get("entry", "N/A")
        b_sl = bot_trade.get("sl", "N/A")
        b_tp = bot_trade.get("tp", "N/A")
        b_status = bot_trade.get("status", "N/A")
        b_pnl = f"${bot_trade.get('realized_pnl_usd', 0.0):+.2f}"
    else:
        b_dir = "NO_BOT_TRADE"
        b_entry = "-"
        b_sl = "-"
        b_tp = "-"
        b_status = "NO_SETUP"
        b_pnl = "$0.00"

    sess_hr = diag.get("session_hour", "N/A")
    has_setup = diag.get("has_setup", False)
    reason = diag.get("reason", "No screener output recorded.")
    phase = diag.get("phase", "N/A")
    arch = diag.get("archetype_id", "None")

    lines = [
        f"### 🔬 Agentify Forensic Snapshot: {case_id}",
        f"**Instrument:** `{symbol}` | **Date:** `{date_str}` | **Server:** `{srv_str}` | **Tehran:** `{tehran_str}` | **UTC:** `{utc_str}`",
        "",
        "#### 📊 Trade Geometry Comparison",
        "| Attribute | Human Setup / Adjustment | Bot Verdict / Execution |",
        "| :--- | :--- | :--- |",
        f"| **Direction** | `{u_dir}` | `{b_dir}` |",
        f"| **Entry Price** | `{u_entry}` | `{b_entry}` |",
        f"| **Stop Loss** | `{u_sl}` | `{b_sl}` |",
        f"| **Take Profit** | `{u_tp}` | `{b_tp}` |",
        f"| **Outcome / PnL** | (Proposed / Evaluated) | `{b_status}` ({b_pnl}) |",
        "",
        "#### ⚙️ Screener Telemetry & Algorithm Brain State",
        f"- **Session Hour:** `{sess_hr}`",
        f"- **Algorithm Decision:** `{'SETUP FIRED' if has_setup else 'VETO / STAND ASIDE'}`",
        f"- **Archetype ID:** `{arch}`",
        f"- **Exact Screener Veto / Reason:** `{reason}`",
        f"- **Market Phase:** `{phase}`",
        "",
        "#### 📝 Trader Rationale & Forensic Notes",
        f"> {user_note}",
        "",
        "#### 🎯 Antigravity Optimization Directives",
        "1. **Audit Veto Authenticity**: Check if the veto reason above reflects a genuine institutional safeguard or an edge-case miscalibration (e.g., timezone skew, tight buffer, or over-filtering).",
        "2. **Zero Reality Distortion**: Do not fabricate a setup if contract physics or macro phase invalidate it. Maintain strict mathematical rigor.",
        "3. **SSOT Rule Synchronization**: If an algorithmic calibration or parameter adjustment is verified, ensure `docs/SYSTEM_EXECUTION_MIRROR.md` is synchronized in the exact same turn.",
    ]
    return "\n".join(lines)


class AgentifyFeedbackStore:
    """Atomic JSON storage manager for forensic cases and Antigravity feedback bundles."""

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = Path(file_path) if file_path else DEFAULT_FEEDBACK_PATH
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict[str, Any] = {"version": "1.0", "last_updated": None, "cases": []}
        self._load()

    def _load(self) -> None:
        """Loads cases from JSON file if present."""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and "cases" in data:
                        self.state = data
            except Exception as e:
                print(f"[AgentifyFeedbackStore] Warning: Failed to load {self.file_path}: {e}")

    def _save(self) -> None:
        """Persists state to disk atomically using temporary file replace."""
        self.state["last_updated"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        temp_path = self.file_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            if temp_path.exists():
                temp_path.replace(self.file_path)
        except Exception as e:
            print(f"[AgentifyFeedbackStore] Error saving feedback store: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass
            raise

    def list_cases(self) -> List[Dict[str, Any]]:
        """Returns all stored feedback cases."""
        return list(self.state.get("cases", []))

    def add_case(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Creates and stores an Agentify forensic snapshot with generated prompt markdown."""
        case = dict(payload)
        symbol = case.get("symbol", "UNKNOWN")

        if "case_id" not in case or not case["case_id"]:
            case["case_id"] = f"CASE-{symbol}-{uuid.uuid4().hex[:8]}"

        if "created_at" not in case:
            case["created_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()

        # Build prompt markdown
        case["prompt_markdown"] = build_agentify_prompt(case)

        self.state.setdefault("cases", []).append(case)
        self._save()
        return case

    def delete_case(self, case_id: str) -> bool:
        """Deletes feedback case by case_id and persists."""
        cases = self.state.get("cases", [])
        initial_len = len(cases)
        self.state["cases"] = [c for c in cases if c.get("case_id") != case_id]
        if len(self.state["cases"]) < initial_len:
            self._save()
            return True
        return False
