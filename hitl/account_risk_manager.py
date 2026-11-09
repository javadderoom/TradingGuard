"""
TradingGuard HITL - Account Profile & Risk Governor
Institutional Prop Firm & Personal Account Exposure Controller.

Enforces:
1. Account Mode Switch: PROP_FIRM vs PERSONAL.
2. Max Open / Concurrent Trades (Positions + Pending Orders).
3. Max Concurrent Risk % (Total active capital exposure at any single moment).
4. Max Daily Drawdown % (Safe buffer and hard circuit breaker).
5. Max Overall / Trailing Drawdown % (Safe buffer and hard circuit breaker from HWM).
6. Centralized JSON persistence & Telegram interactive controls.
"""

import os
import json
import time
import datetime
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List


MEMORY_DIR = Path(__file__).resolve().parent / "memory"
PROFILE_FILE = MEMORY_DIR / "account_risk_profile.json"


DEFAULT_PROFILES = {
    "account_mode": "PROP_FIRM",
    "account_size_usd": 10000.0,
    "use_auto_account_size": True,
    "profiles": {
        "PROP_FIRM": {
            "name": "Prop Firm Challenge / Funded",
            "max_open_trades": 2,
            "max_concurrent_risk_pct": 1.5,
            "hard_concurrent_risk_pct": 2.0,
            "max_daily_drawdown_pct": 4.0,
            "hard_daily_drawdown_pct": 5.0,
            "max_overall_drawdown_pct": 10.0,
            "hard_overall_drawdown_pct": 12.0
        },
        "PERSONAL": {
            "name": "Personal Trading Account",
            "max_open_trades": 3,
            "max_concurrent_risk_pct": 3.0,
            "hard_concurrent_risk_pct": 5.0,
            "max_daily_drawdown_pct": 6.0,
            "hard_daily_drawdown_pct": 8.0,
            "max_overall_drawdown_pct": 15.0,
            "hard_overall_drawdown_pct": 20.0
        }
    },
    "daily_reference_equity": None,
    "daily_reference_date": None,
    "high_water_mark_equity": None,
    "circuit_breaker_active": False,
    "circuit_breaker_reason": "",
    "last_updated": None
}


class AccountRiskManager:
    """
    Central Risk Governor enforcing account-level risk and drawdown constraints.
    """

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or PROFILE_FILE
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.state: Dict[str, Any] = {}
        self.load()

    def load(self) -> Dict[str, Any]:
        """Loads configuration from JSON file or initializes defaults."""
        if not self.config_path.exists():
            self.state = json.loads(json.dumps(DEFAULT_PROFILES))
            self.state["last_updated"] = datetime.datetime.now().isoformat()
            self.save()
            return self.state

        try:
            with open(self.config_path, "r", encoding="utf-8") as f:
                loaded = json.load(f)
            # Ensure all default keys exist
            merged = json.loads(json.dumps(DEFAULT_PROFILES))
            merged.update(loaded)
            # Merge sub-profiles
            for mode, pdata in DEFAULT_PROFILES["profiles"].items():
                if mode not in merged["profiles"]:
                    merged["profiles"][mode] = pdata
                else:
                    for k, v in pdata.items():
                        merged["profiles"][mode].setdefault(k, v)
            self.state = merged
        except Exception as e:
            print(f"[AccountRiskManager] Error loading config: {e}. Falling back to defaults.")
            self.state = json.loads(json.dumps(DEFAULT_PROFILES))
            self.save()

        return self.state

    def save(self) -> None:
        """Persists configuration to JSON file atomically."""
        self.state["last_updated"] = datetime.datetime.now().isoformat()
        temp_path = self.config_path.with_suffix(".tmp")
        try:
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(self.state, f, indent=2, ensure_ascii=False)
            if temp_path.exists():
                temp_path.replace(self.config_path)
        except Exception as e:
            print(f"[AccountRiskManager] Error saving config: {e}")
            if temp_path.exists():
                try:
                    temp_path.unlink()
                except Exception:
                    pass

    @property
    def mode(self) -> str:
        return self.state.get("account_mode", "PROP_FIRM")

    @property
    def active_profile(self) -> Dict[str, Any]:
        curr_mode = self.mode
        return self.state.get("profiles", {}).get(curr_mode, DEFAULT_PROFILES["profiles"]["PROP_FIRM"])

    def set_account_mode(self, mode: str) -> bool:
        """Switches account mode between PROP_FIRM and PERSONAL."""
        mode_upper = mode.upper().strip()
        if mode_upper not in ["PROP_FIRM", "PERSONAL"]:
            return False
        self.state["account_mode"] = mode_upper
        self.save()
        return True

    def set_account_size(self, size_usd: float, use_auto: bool = False) -> bool:
        """Sets reference account capital or toggles MT5 auto-equity detection."""
        if size_usd <= 0 and not use_auto:
            return False
        self.state["account_size_usd"] = float(size_usd)
        self.state["use_auto_account_size"] = bool(use_auto)
        self.save()
        return True

    def update_limit(self, key: str, value: Any, mode: Optional[str] = None) -> bool:
        """Updates a specific limit parameter in the target profile."""
        target_mode = (mode or self.mode).upper().strip()
        if target_mode not in self.state.get("profiles", {}):
            return False
        profile = self.state["profiles"][target_mode]
        if key in profile:
            profile[key] = type(profile[key])(value)
            self.save()
            return True
        return False

    def reset_circuit_breaker(self, engine: Optional[Any] = None) -> bool:
        """Manually resets active circuit breaker and re-anchors baselines to live equity."""
        self.state["circuit_breaker_active"] = False
        self.state["circuit_breaker_reason"] = ""
        if engine:
            try:
                acc = engine.get_account_summary()
                if acc and acc.get("equity", 0) > 0:
                    eq = round(float(acc["equity"]), 2)
                    self.state["high_water_mark_equity"] = eq
                    self.state["daily_reference_equity"] = eq
                    if self.state.get("use_auto_account_size", True):
                        self.state["account_size_usd"] = eq
            except Exception:
                pass
        self.save()
        return True

    def trip_circuit_breaker(self, reason: str) -> None:
        """Engages circuit breaker and locks new trading."""
        self.state["circuit_breaker_active"] = True
        self.state["circuit_breaker_reason"] = reason
        self.save()

    def get_reference_capital(self, engine: Any) -> float:
        """
        Resolves reference account capital.
        If use_auto_account_size is True and MT5 is connected, returns current balance/equity.
        Otherwise returns configured account_size_usd.
        """
        if self.state.get("use_auto_account_size", False) and engine:
            try:
                acc = engine.get_account_summary()
                if acc and acc.get("equity", 0) > 0:
                    return float(acc["equity"])
            except Exception:
                pass
        return float(self.state.get("account_size_usd", 10000.0))

    def sync_state(self, engine: Any) -> Dict[str, Any]:
        """
        Synchronizes daily equity baseline and high water mark with live MT5 account.
        Checks for drawdown limit breaches and trips circuit breaker if needed.
        """
        now = datetime.datetime.now()
        today_str = now.strftime("%Y-%m-%d")

        acc = engine.get_account_summary() if engine else None
        current_equity = float(acc["equity"]) if acc else self.get_reference_capital(engine)
        current_balance = float(acc["balance"]) if acc else current_equity

        # 1. Daily Reference Baseline
        stored_date = self.state.get("daily_reference_date")
        if stored_date != today_str or self.state.get("daily_reference_equity") is None:
            # New calendar day: baseline is starting equity
            perf = engine.get_daily_performance() if engine else {"realized_pnl": 0.0}
            realized_today = float(perf.get("realized_pnl", 0.0))
            # Starting day equity = current_balance - realized_pnl today
            day_starting_eq = max(100.0, current_balance - realized_today)
            self.state["daily_reference_equity"] = round(day_starting_eq, 2)
            self.state["daily_reference_date"] = today_str
            # Auto-clear day-specific circuit breaker on new trading day
            if "Daily" in self.state.get("circuit_breaker_reason", ""):
                self.state["circuit_breaker_active"] = False
                self.state["circuit_breaker_reason"] = ""
            self.save()

        daily_ref_equity = float(self.state.get("daily_reference_equity", current_equity))

        # 2. High Water Mark (HWM) Tracking
        hwm = self.state.get("high_water_mark_equity")
        # Re-anchor HWM if uninitialized, or if new equity peak, or if unlinked placeholder far above live equity
        if hwm is None or current_equity > hwm or (self.state.get("use_auto_account_size", True) and hwm > current_equity * 1.5):
            self.state["high_water_mark_equity"] = round(current_equity, 2)
            hwm = current_equity
            self.save()

        # 3. Compute Live Drawdowns
        # Daily Drawdown: loss relative to daily starting equity
        daily_loss_usd = max(0.0, daily_ref_equity - current_equity)
        daily_dd_pct = (daily_loss_usd / daily_ref_equity * 100.0) if daily_ref_equity > 0 else 0.0

        # Overall Drawdown: loss relative to High Water Mark
        overall_loss_usd = max(0.0, float(hwm) - current_equity)
        overall_dd_pct = (overall_loss_usd / float(hwm) * 100.0) if float(hwm) > 0 else 0.0

        profile = self.active_profile

        # 4. Check Hard Drawdown Thresholds
        if not self.state.get("circuit_breaker_active", False):
            if daily_dd_pct >= profile.get("max_daily_drawdown_pct", 4.0):
                reason = (
                    f"Daily Drawdown breach: {daily_dd_pct:.2f}% (${daily_loss_usd:.2f}) "
                    f"reached safe threshold {profile.get('max_daily_drawdown_pct', 4.0):.2f}% "
                    f"(Hard limit: {profile.get('hard_daily_drawdown_pct', 5.0):.2f}%)."
                )
                self.trip_circuit_breaker(reason)
            elif overall_dd_pct >= profile.get("max_overall_drawdown_pct", 10.0):
                reason = (
                    f"Overall Drawdown breach: {overall_dd_pct:.2f}% (${overall_loss_usd:.2f}) "
                    f"reached safe threshold {profile.get('max_overall_drawdown_pct', 10.0):.2f}% "
                    f"(Hard limit: {profile.get('hard_overall_drawdown_pct', 12.0):.2f}%)."
                )
                self.trip_circuit_breaker(reason)

        return {
            "account_mode": self.mode,
            "current_equity": current_equity,
            "current_balance": current_balance,
            "daily_reference_equity": daily_ref_equity,
            "daily_loss_usd": round(daily_loss_usd, 2),
            "daily_dd_pct": round(daily_dd_pct, 2),
            "high_water_mark": float(hwm),
            "overall_loss_usd": round(overall_loss_usd, 2),
            "overall_dd_pct": round(overall_dd_pct, 2),
            "circuit_breaker_active": self.state.get("circuit_breaker_active", False),
            "circuit_breaker_reason": self.state.get("circuit_breaker_reason", "")
        }

    def get_open_exposure(self, engine: Any) -> Dict[str, Any]:
        """
        Calculates total open positions, pending orders, and cumulative USD risk.
        """
        if not engine:
            return {"open_trades_count": 0, "concurrent_risk_usd": 0.0, "positions": 0, "orders": 0}

        positions = engine.get_open_positions()
        pending = engine.get_pending_orders()
        open_trades_count = len(positions) + len(pending)

        total_risk_usd = 0.0

        # Calculate risk on active open positions
        for p in positions:
            sl = float(p.get("sl", 0.0))
            if sl > 0:
                is_buy = (p.get("type") == "BUY")
                price_open = float(p.get("price_open", 0.0))
                # If trade is secured past entry, risk is $0.00
                if (is_buy and sl >= price_open) or (not is_buy and sl <= price_open):
                    trade_risk = 0.0
                else:
                    risk_val = engine.calculate_risk_usd(p["symbol"], p["type"], price_open, sl, float(p["volume"]))
                    trade_risk = risk_val if risk_val is not None else 0.0
            else:
                trade_risk = 12.0  # Uncapped fallback default
            total_risk_usd += trade_risk

        # Calculate risk on pending limit orders
        for o in pending:
            sl = float(o.get("sl", 0.0))
            price_open = float(o.get("price_open", 0.0))
            order_type = o.get("type", "BUY_LIMIT")
            if sl > 0:
                risk_val = engine.calculate_risk_usd(o["symbol"], order_type, price_open, sl, float(o["volume"]))
                trade_risk = risk_val if risk_val is not None else 0.0
            else:
                trade_risk = 12.0
            total_risk_usd += trade_risk

        return {
            "open_trades_count": open_trades_count,
            "positions_count": len(positions),
            "pending_count": len(pending),
            "concurrent_risk_usd": round(total_risk_usd, 2)
        }

    def evaluate_order_feasibility(
        self,
        symbol: str,
        order_type_str: str,
        price: float,
        sl: float,
        tp: float,
        lot: float,
        risk_usd: float,
        engine: Any
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validates proposed trade against Prop Firm and Account Risk Governor constraints.
        Returns (is_approved, reason_message, metrics_dict).
        """
        sync_data = self.sync_state(engine)
        exposure_data = self.get_open_exposure(engine)
        profile = self.active_profile
        ref_capital = self.get_reference_capital(engine)

        metrics = {
            "mode": self.mode,
            "ref_capital": ref_capital,
            "open_trades": exposure_data["open_trades_count"],
            "max_open_trades": profile["max_open_trades"],
            "current_risk_usd": exposure_data["concurrent_risk_usd"],
            "projected_risk_usd": round(exposure_data["concurrent_risk_usd"] + risk_usd, 2),
            "current_risk_pct": round((exposure_data["concurrent_risk_usd"] / ref_capital) * 100.0, 2),
            "projected_risk_pct": round(((exposure_data["concurrent_risk_usd"] + risk_usd) / ref_capital) * 100.0, 2),
            "max_concurrent_risk_pct": profile["max_concurrent_risk_pct"],
            "hard_concurrent_risk_pct": profile["hard_concurrent_risk_pct"],
            "daily_dd_pct": sync_data["daily_dd_pct"],
            "projected_daily_dd_pct": round(((sync_data["daily_loss_usd"] + risk_usd) / sync_data["daily_reference_equity"]) * 100.0, 2),
            "max_daily_drawdown_pct": profile["max_daily_drawdown_pct"],
            "overall_dd_pct": sync_data["overall_dd_pct"],
            "max_overall_drawdown_pct": profile["max_overall_drawdown_pct"]
        }

        # Check 1: Circuit Breaker Engagement
        if sync_data["circuit_breaker_active"]:
            reason = (
                f"🚫 *[Account Risk Governor Circuit Breaker Active]*\n"
                f"Mode: `{self.mode}`\n"
                f"Reason: {sync_data['circuit_breaker_reason']}\n"
                f"All new order entries are strictly prohibited to safeguard account capital."
            )
            return False, reason, metrics

        # Check 2: Max Open Trades Count
        max_trades = profile.get("max_open_trades", 2)
        if (exposure_data["open_trades_count"] + 1) > max_trades:
            reason = (
                f"🚫 *[Trade Placement Blocked · Max Concurrent Trades Reached]*\n"
                f"Account Mode: `{self.mode}`\n"
                f"Active Open Positions & Orders: *{exposure_data['open_trades_count']}* / *{max_trades} max*\n"
                f"📌 Position limit protects against simultaneous market shock across correlated pairs.\n"
                f"💡 Close an active position or cancel a pending limit order to free an execution slot."
            )
            return False, reason, metrics

        # Check 3: Max Concurrent Risk % (Total Open Risk)
        projected_risk_pct = metrics["projected_risk_pct"]
        safe_risk_cap_pct = profile.get("max_concurrent_risk_pct", 1.5)
        hard_risk_cap_pct = profile.get("hard_concurrent_risk_pct", 2.0)

        if projected_risk_pct > safe_risk_cap_pct:
            reason = (
                f"🚫 *[Trade Placement Blocked · Concurrent Risk Cap Exceeded]*\n"
                f"Account Mode: `{self.mode}`\n"
                f"Existing Open Risk: *${exposure_data['concurrent_risk_usd']:.2f}* ({metrics['current_risk_pct']}%\n"
                f"New Order Risk: *${risk_usd:.2f}*\n"
                f"Projected Total Exposure: *${metrics['projected_risk_usd']:.2f}* (*{projected_risk_pct:.2f}%*)\n"
                f"Configured Safe Ceiling: *{safe_risk_cap_pct:.2f}%* (Prop Hard Limit: *{hard_risk_cap_pct:.2f}%*)\n"
                f"💡 Capital preservation rule prohibits risking >{safe_risk_cap_pct:.2f}% of account simultaneously."
            )
            return False, reason, metrics

        # Check 4: Daily Drawdown Ceiling Protection
        projected_daily_dd = metrics["projected_daily_dd_pct"]
        safe_daily_dd_pct = profile.get("max_daily_drawdown_pct", 4.0)
        hard_daily_dd_pct = profile.get("hard_daily_drawdown_pct", 5.0)

        if projected_daily_dd > safe_daily_dd_pct:
            reason = (
                f"🚫 *[Trade Placement Blocked · Daily Drawdown Danger Zone]*\n"
                f"Account Mode: `{self.mode}`\n"
                f"Current Daily Loss: *${sync_data['daily_loss_usd']:.2f}* ({sync_data['daily_dd_pct']}%\n"
                f"Projected Daily Drawdown with Trade SL: *{projected_daily_dd:.2f}%*\n"
                f"Configured Daily Safe Buffer: *{safe_daily_dd_pct:.2f}%* (Prop Hard Rule: *{hard_daily_dd_pct:.2f}%*)\n"
                f"🛑 Trade blocked to ensure daily losses cannot breach prop firm challenge rules."
            )
            return False, reason, metrics

        # Check 5: Overall Drawdown Ceiling Protection
        safe_overall_dd_pct = profile.get("max_overall_drawdown_pct", 10.0)
        hard_overall_dd_pct = profile.get("hard_overall_drawdown_pct", 12.0)
        projected_overall_loss = sync_data["overall_loss_usd"] + risk_usd
        projected_overall_dd = (projected_overall_loss / sync_data["high_water_mark"] * 100.0) if sync_data["high_water_mark"] > 0 else 0.0

        if projected_overall_dd > safe_overall_dd_pct:
            reason = (
                f"🚫 *[Trade Placement Blocked · Overall Drawdown Danger Zone]*\n"
                f"Account Mode: `{self.mode}`\n"
                f"Current Drawdown from HWM: *${sync_data['overall_loss_usd']:.2f}* ({sync_data['overall_dd_pct']}%\n"
                f"Projected Drawdown with Trade SL: *{projected_overall_dd:.2f}%*\n"
                f"Configured Overall Safe Buffer: *{safe_overall_dd_pct:.2f}%* (Prop Hard Rule: *{hard_overall_dd_pct:.2f}%*)\n"
                f"🛑 Trade blocked to prevent account termination."
            )
            return False, reason, metrics

        return True, "Approved by Account Risk Governor", metrics

    def format_status_card(self, engine: Any) -> str:
        """Generates a comprehensive Telegram markdown status card."""
        sync_data = self.sync_state(engine)
        exposure_data = self.get_open_exposure(engine)
        profile = self.active_profile
        ref_capital = self.get_reference_capital(engine)

        curr_risk_pct = (exposure_data["concurrent_risk_usd"] / ref_capital * 100.0) if ref_capital > 0 else 0.0

        mode_badge = "🏢 *PROP FIRM CHALLENGE / FUNDED*" if self.mode == "PROP_FIRM" else "👤 *PERSONAL ACCOUNT*"
        breaker_badge = "🟢 *NORMAL (Safe)*" if not sync_data["circuit_breaker_active"] else f"⛔ *TRIPPED: {sync_data['circuit_breaker_reason']}*"

        auto_mode_lbl = "Auto (MT5 Live Equity)" if self.state.get("use_auto_account_size") else "Manual Override"

        lines = [
            f"🛡️ *TradingGuard Account Profile & Risk Governor*",
            f"",
            f"📌 *Mode:* {mode_badge}",
            f"💵 *Reference Capital:* `${ref_capital:,.2f}` _({auto_mode_lbl})_",
            f"📈 *Live MT5 Equity:* `${sync_data['current_equity']:,.2f}` | Balance: `${sync_data['current_balance']:,.2f}`",
            f"",
            f"📊 *Live Risk & Exposure Limits:*",
            f"• *Open Trades:* `{exposure_data['open_trades_count']} / {profile['max_open_trades']}` max "
            f"_(Positions: {exposure_data['positions_count']}, Pending: {exposure_data['pending_count']})_",
            f"• *Concurrent Risk:* `${exposure_data['concurrent_risk_usd']:.2f}` (`{curr_risk_pct:.2f}%`) / "
            f"Safe: `{profile['max_concurrent_risk_pct']:.1f}%` (Hard: `{profile['hard_concurrent_risk_pct']:.1f}%`)",
            f"• *Daily Drawdown:* `${sync_data['daily_loss_usd']:.2f}` (`{sync_data['daily_dd_pct']:.2f}%`) / "
            f"Safe: `{profile['max_daily_drawdown_pct']:.1f}%` (Hard: `{profile['hard_daily_drawdown_pct']:.1f}%`)",
            f"• *Overall Drawdown:* `${sync_data['overall_loss_usd']:.2f}` (`{sync_data['overall_dd_pct']:.2f}%`) / "
            f"Safe: `{profile['max_overall_drawdown_pct']:.1f}%` (Hard: `{profile['hard_overall_drawdown_pct']:.1f}%`)",
            f"   _HWM Peak: ${sync_data['high_water_mark']:,.2f}_",
            f"",
            f"⚡ *Circuit Breaker Status:* {breaker_badge}",
            f"",
            f"⚙️ *Use the buttons below to switch mode or calibrate limits:*"
        ]
        return "\n".join(lines)

    def get_telegram_inline_keyboard(self) -> Dict[str, Any]:
        """Provides interactive inline keyboard buttons for Telegram UI."""
        toggle_target = "PERSONAL" if self.mode == "PROP_FIRM" else "PROP_FIRM"
        toggle_label = "👤 Switch to PERSONAL" if self.mode == "PROP_FIRM" else "🏢 Switch to PROP FIRM"

        profile = self.active_profile
        t_limit = profile.get("max_open_trades", 2)
        r_limit = profile.get("max_concurrent_risk_pct", 1.5)
        d_limit = profile.get("max_daily_drawdown_pct", 4.0)

        buttons = [
            [
                {"text": toggle_label, "callback_data": f"prop_set_mode_{toggle_target}"}
            ],
            [
                {"text": f"🔢 Trades: {t_limit}", "callback_data": "prop_menu_trades"},
                {"text": f"⚡ Risk: {r_limit}%", "callback_data": "prop_menu_risk"},
                {"text": f"📉 Daily DD: {d_limit}%", "callback_data": "prop_menu_daily"}
            ],
            [
                {"text": "🔄 Reset Breaker", "callback_data": "prop_reset_breaker"},
                {"text": "💵 Sync MT5 Capital", "callback_data": "prop_sync_capital"}
            ]
        ]
        return {"inline_keyboard": buttons}


# Global Singleton Instance
risk_governor = AccountRiskManager()
