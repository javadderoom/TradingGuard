"""MainWindow session lifecycle and enforcement mixin."""

import logging
import secrets
from datetime import datetime, timedelta

from PyQt6.QtWidgets import QMessageBox

from app import mt5_controller
from app.config import EA_HEARTBEAT_TIMEOUT_SECONDS, get_session_day_str

log = logging.getLogger(__name__)


class MainWindowSessionMixin:
    @staticmethod
    def _parse_bridge_time(value: str) -> datetime | None:
        text = (value or "").strip()
        if not text:
            return None
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            try:
                return datetime.strptime(text, "%Y.%m.%d %H:%M:%S")
            except ValueError:
                return None

    def _trigger_ea_tamper_lock(self, reason: str, data: dict) -> None:
        if self._shutdown_done:
            return

        mt5_controller.kill_mt5()
        self._session_started = False
        self._shutdown_done = True

        self._bridge.update(
            session_active=False,
            trading_allowed=False,
            shutdown_signal=True,
            tamper_lock=True,
            tamper_reason=reason,
        )

        pnl = float(data.get("daily_profit_usd", 0) or 0) - float(data.get("daily_loss_usd", 0) or 0)
        trades = int(data.get("trades_today", 0) or 0)
        self._db.record_day(pnl=pnl, trades=trades)
        self._record_violation(
            rule_code="EA_TAMPER_OR_OFFLINE",
            severity="critical",
            message=f"EA watchdog triggered: {reason}",
            context={
                "trades_today": trades,
                "pnl": pnl,
                "ea_heartbeat_ts": data.get("ea_heartbeat_ts", ""),
                "app_challenge": data.get("app_challenge", ""),
                "ea_challenge_echo": data.get("ea_challenge_echo", ""),
            },
            dedupe_key=f"ea_tamper:{get_session_day_str()}",
        )
        self._load_history()
        self._status_bar.showMessage(f"EA watchdog lock: {reason}")

        if not self._tamper_alerted:
            self._tamper_alerted = True
            QMessageBox.warning(
                self,
                "EA Watchdog Lock",
                "EA heartbeat/challenge failed.\n"
                "Trading is locked for the rest of this session day.",
            )

    def _update_ea_watchdog(self, data: dict) -> dict:
        if not data.get("session_active") or self._shutdown_done:
            return data

        now = datetime.now()
        timeout = max(int(EA_HEARTBEAT_TIMEOUT_SECONDS), 10)
        challenge_age_limit = timedelta(seconds=timeout)

        challenge = (data.get("app_challenge") or "").strip()
        challenge_ts = self._parse_bridge_time(data.get("app_challenge_ts") or "")
        should_rotate = (
            not challenge
            or challenge_ts is None
            or self._last_watchdog_challenge_at is None
            or (now - self._last_watchdog_challenge_at) >= timedelta(seconds=6)
        )
        if should_rotate:
            challenge = secrets.token_hex(8)
            challenge_ts = now
            self._last_watchdog_challenge_at = now
            data = self._bridge.update(
                app_challenge=challenge,
                app_challenge_ts=now.isoformat(),
            )

        heartbeat_ts = self._parse_bridge_time(data.get("ea_heartbeat_ts") or "")
        heartbeat_stale = (
            heartbeat_ts is None
            or (now - heartbeat_ts) > timedelta(seconds=timeout)
        )

        challenge_echo = (data.get("ea_challenge_echo") or "").strip()
        challenge_mismatch = challenge_echo != challenge
        challenge_stale = (
            challenge_mismatch
            and challenge_ts is not None
            and (now - challenge_ts) > challenge_age_limit
        )

        if mt5_controller.is_mt5_running() and (heartbeat_stale or challenge_stale):
            reason = "EA heartbeat stale" if heartbeat_stale else "EA challenge mismatch"
            self._trigger_ea_tamper_lock(reason=reason, data=data)

        return data

    def _check_recovery_day(self):
        """Evaluate whether trading is allowed today.

        - If the last 2 completed days were red → mandatory recovery day.
        - If there is already a record for today → today's session is finished.
        """
        # Mandatory recovery day after 2 consecutive red days
        if self._db.is_recovery_day():
            self._btn_start_session.setEnabled(False)
            self._timer_widget.setEnabled(False)
            self._shutdown_done = True  # treat as permanently shut down for today
            self._status_bar.showMessage(
                "🛑  RECOVERY DAY — 2 consecutive red days. Trading is blocked."
            )
            QMessageBox.warning(
                self,
                "Recovery Day",
                "You had 2 consecutive losing days.\n"
                "Today is a mandatory recovery day — no trading allowed.",
            )
            # Ensure MT5 is not running on a recovery day.
            mt5_controller.kill_mt5()
            return

        # If we already have a row for today, that means today's session was
        # completed earlier (either manually or via EA shutdown). Do not allow
        # a new session to start after reopening the app.
        today_row = self._db.get_today()
        if today_row is not None:
            self._btn_start_session.setEnabled(False)
            self._timer_widget.setEnabled(False)
            self._shutdown_done = True
            result = today_row.get("result", "completed").upper()
            self._status_bar.showMessage(
                f"🛑  SESSION COMPLETED TODAY ({result}) — no further trading allowed."
            )

        if today_row is not None:
            return

        # No recovery lock and no completed row for current session day.
        self._shutdown_done = False
        self._tamper_alerted = False
        self._btn_start_session.setEnabled(True)
        self._timer_widget.setEnabled(True)
        self._status_bar.showMessage("Ready")

    def _start_session(self):
        """Called when 'Start Trading Session' is clicked."""
        from app.config import is_within_trading_hours, get_tehran_time_str, TRADING_START_HOUR, TRADING_END_HOUR
        
        if not self._timer_widget.is_complete():
            QMessageBox.information(
                self,
                "Analysis Required",
                "Complete the 20-minute analysis timer first.",
            )
            return

        if self._shutdown_done:
            QMessageBox.warning(
                self,
                "Session Ended",
                "Today's session has already been shut down.\n"
                "You cannot restart until tomorrow.",
            )
            return

        # Check trading hours (Tehran time)
        if not is_within_trading_hours():
            tehran_time = get_tehran_time_str()
            QMessageBox.warning(
                self,
                "Outside Trading Hours",
                f"Trading is only allowed between {TRADING_START_HOUR}:00 and {TRADING_END_HOUR}:00 Tehran time.\n"
                f"Current Tehran time: {tehran_time}",
            )
            return

        # Seed today's counters from DB so restarts do not reset daily limits.
        # First prune ambiguous placeholder rows that can appear after stale
        # bridge counters (ghost trades).
        today = get_session_day_str()
        removed = self._db.prune_ambiguous_bridge_trades(trade_day=today)
        if removed:
            log.warning(
                "Pruned %d ambiguous bridge trade row(s) for %s before session start.",
                removed,
                today,
            )
        today_ledger = self._db.get_trade_ledger(trade_day=today, limit=500)
        trades_today = self._db.get_last_trade_index(today)
        daily_profit = 0.0
        daily_loss = 0.0
        for row in today_ledger:
            pnl_val = row.get("pnl")
            if pnl_val in (None, ""):
                continue
            try:
                pnl = float(pnl_val)
            except (TypeError, ValueError):
                continue
            if pnl >= 0:
                daily_profit += pnl
            else:
                daily_loss += abs(pnl)

        consecutive_losses = 0
        today_events = self._db.get_trade_events(trade_day=today, limit=500)
        for evt in today_events:
            if (evt.get("result") or "").lower() == "loss":
                consecutive_losses += 1
            else:
                break

        # Write initial session state
        self._bridge.update(
            session_active=True,
            trading_allowed=True,
            shutdown_signal=False,
            tamper_lock=False,
            tamper_reason="",
            break_active=False,
            break_until="",
            daily_loss_usd=daily_loss,
            daily_profit_usd=daily_profit,
            trades_today=trades_today,
            consecutive_losses=consecutive_losses,
            cooldown_until="",
            last_trade_result="",
            last_trade_pnl=0.0,
            app_challenge=secrets.token_hex(8),
            app_challenge_ts=datetime.now().isoformat(),
            ea_challenge_echo="",
            ea_heartbeat_ts="",
        )
        self._last_watchdog_challenge_at = datetime.now()
        self._tamper_alerted = False

        # Launch MT5
        if mt5_controller.launch_mt5():
            self._session_started = True
            self._status_bar.showMessage("Session active — MT5 launched")
            self._tabs.setCurrentIndex(1)  # Switch to Session tab
        else:
            QMessageBox.critical(
                self,
                "MT5 Error",
                "Could not launch MetaTrader 5.\n"
                "Check that the path in config.py is correct.",
            )

    def _end_session(self):
        """Manually end the session, kill MT5, record daily result."""
        reply = QMessageBox.question(
            self,
            "End Session",
            "Are you sure you want to end today's trading session?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self._shutdown_session()

    def _shutdown_session(self):
        """Shared shutdown logic (manual or triggered by EA limits)."""
        self._bridge.update(
            session_active=False,
            trading_allowed=False,
            shutdown_signal=True,
        )
        mt5_controller.kill_mt5()
        self._session_started = False
        self._shutdown_done = True

        # Record daily result
        data = self._bridge.read()
        pnl = data.get("daily_profit_usd", 0) - data.get("daily_loss_usd", 0)
        trades = data.get("trades_today", 0)
        self._db.record_day(pnl=pnl, trades=trades)
        self._record_violation(
            rule_code="DAILY_SHUTDOWN",
            severity="critical",
            message="Session shut down after daily limit trigger.",
            context={"pnl": pnl, "trades_today": trades},
        )

        self._load_history()
        self._status_bar.showMessage("Session ended — MT5 closed")

    def _handle_consecutive_losses_shutdown(self, data: dict):
        """Handle shutdown triggered by consecutive losses - 1 hour break."""
        mt5_controller.kill_mt5()
        self._session_started = False

        # Start 1-hour break (don't record day - user can resume after break)
        self._break_until = datetime.now() + timedelta(hours=1)
        self._bridge.update(
            session_active=False,
            trading_allowed=False,
            shutdown_signal=False,  # Clear shutdown so new session is possible
            break_until=self._break_until.isoformat(),
        )
        self._record_violation(
            rule_code="CONSECUTIVE_LOSS_BREAK",
            severity="critical",
            message="1-hour break enforced after consecutive losses.",
            context={
                "consecutive_losses": int(data.get("consecutive_losses", 0) or 0),
                "break_until": self._break_until.isoformat(),
            },
        )

        self._status_bar.showMessage(
            "🛑  2 consecutive losses — 1-hour break started"
        )

    def _dev_reset_today(self):
        """Development-only helper to clear today's lock and session state.

        This makes it possible to run multiple test sessions in one day while
        keeping production behavior strict by default.
        """
        reply = QMessageBox.question(
            self,
            "DEV: Reset Today's Lock",
            "This will clear today's result and re-enable trading for testing.\n"
            "Are you sure?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # Stop MT5 first so EA cannot rewrite stale cooldown/break state.
        mt5_controller.kill_mt5()
        self._session_started = False
        self._break_until = None

        # Clear today's DB row and reset in-memory flags
        self._db.clear_today()
        self._shutdown_done = False
        self._btn_start_session.setEnabled(True)
        self._timer_widget.setEnabled(True)
        self._timer_widget.reset()

        # Reset session.json and force-clear cooldown/break fields.
        self._bridge.reset()
        self._bridge.update(
            session_active=False,
            trading_allowed=False,
            shutdown_signal=False,
            break_active=False,
            break_until="",
            cooldown_until="0",
            last_trade_result="",
            last_trade_pnl=0.0,
            trades_today=0,
            daily_loss_usd=0.0,
            daily_profit_usd=0.0,
            consecutive_losses=0,
            losses_since_bias=0,
            app_challenge="",
            app_challenge_ts="",
            ea_challenge_echo="",
            ea_heartbeat_ts="",
            tamper_lock=False,
            tamper_reason="",
        )

        self._prev_trades_today = 0
        self._prev_net_pnl = 0.0
        self._prev_shutdown_signal = False
        self._prev_break_active = False
        self._prev_bias_expired = False
        self._prev_news_lock = False
        self._last_watchdog_challenge_at = None
        self._tamper_alerted = False
        self._violation_dedupe.clear()
        self._load_history()

        self._status_bar.showMessage(
            "DEV: Today's lock reset — cooldown and break state cleared."
        )

    def _guard_mt5_after_shutdown(self):
        """Continuously enforce 'no reopening after shutdown', recovery days, 
        and 1-hour break after consecutive losses."""
        
        break_active = False
        break_reason = ""
        break_until_str = ""
        pre_session_block = False
        try:
            data = self._bridge.read()
            break_until_str = data.get("break_until") or ""
            break_active = data.get("break_active", False)
            pre_session_block = (
                not self._timer_widget.is_complete()
                and not bool(data.get("session_active"))
            )
            if break_until_str:
                try:
                    break_until = datetime.fromisoformat(break_until_str)
                    if datetime.now() < break_until:
                        break_reason = "1-hour break"
                    else:
                        break_active = False
                except ValueError:
                    break_reason = ""
                    break_active = False
        except Exception as exc:
            log.warning("Error reading session in guard_mt5: %s", exc)

        recovery_day = self._db.is_recovery_day()
        
        # Check daily break time
        from app.config import is_daily_break_time, get_tehran_time_str
        daily_break, break_reason = is_daily_break_time()
        
        # Add daily break to the check
        if daily_break and not break_active:
            break_active = True
            break_reason = break_reason or "daily break"
        
        log.debug(
            "MT5 guard check: _shutdown_done=%s, recovery_day=%s, break_active=%s, pre_session_block=%s, break_reason='%s'",
            self._shutdown_done, recovery_day, break_active, pre_session_block, break_reason
        )

        if not self._shutdown_done and not recovery_day and not break_active and not pre_session_block:
            return

        if mt5_controller.is_mt5_running():
            mt5_controller.kill_mt5()
            if break_reason:
                reason = break_reason
            elif pre_session_block:
                reason = "complete pre-session analysis first"
            elif recovery_day:
                reason = "recovery day"
            elif self._shutdown_done:
                reason = "session shutdown"
            else:
                reason = "unknown"
            log.info("MT5 blocked: %s", reason)
            self._record_violation(
                rule_code="MT5_BLOCKED",
                severity="warn",
                message=f"MT5 process terminated: {reason}",
                context={"reason": reason},
            )
            self._status_bar.showMessage(
                f"🛑  MT5 is blocked — {reason}"
            )

    def _poll_session(self):
        """Read session.json and update the Session widget.
        Also auto-shutdown if the EA signals it."""
        current_session_day = get_session_day_str()
        if current_session_day != self._session_day_key:
            self._session_day_key = current_session_day
            self._shutdown_done = False
            self._prev_shutdown_signal = False
            self._prev_break_active = False
            self._prev_bias_expired = False
            self._prev_news_lock = False
            self._violation_dedupe.clear()
            self._check_recovery_day()

        try:
            data = self._bridge.read()
        except Exception as exc:
            log.warning("Failed to read session.json: %s", exc)
            return

        if self._cleanup_carryover_duplicate_day_if_detected(data):
            try:
                data = self._bridge.read()
            except Exception as exc:
                log.warning("Failed to re-read session after carry-over cleanup: %s", exc)
                return

        data = self._sanitize_inactive_bridge_state(data)
        data = self._update_ea_watchdog(data)

        self._session_widget.refresh(data)
        self._sync_live_trade_events(data)
        self._track_rule_state_transitions(data)

        # Enforce long break after consecutive losses (EA sets break_active).
        self._enforce_break(data)

        # Enforce bias expiry (Phase 3): after 2 hours or 3 losses since bias
        # was set, disable trading until the user updates their bias again.
        self._enforce_bias_expiry(data)

        # Auto-shutdown if EA sets shutdown_signal
        shutdown_signal = bool(data.get("shutdown_signal"))
        is_current_session_day = self._is_bridge_data_for_current_session_day(data)
        if shutdown_signal and not self._shutdown_done and is_current_session_day:
            # Check if this is a consecutive losses shutdown (has break_active)
            if data.get("break_active"):
                # Consecutive losses: record result and start 1-hour break
                self._handle_consecutive_losses_shutdown(data)
            else:
                # Full daily shutdown (limits reached)
                self._shutdown_session()
                self._status_bar.showMessage(
                    "🛑  AUTO-SHUTDOWN — daily limit reached"
                )

        elif shutdown_signal and not is_current_session_day:
            log.info("Ignoring stale shutdown_signal from previous session day.")
            try:
                self._bridge.update(shutdown_signal=False)
            except Exception as exc:
                log.warning("Failed to clear stale shutdown_signal: %s", exc)

    def _is_bridge_data_for_current_session_day(self, data: dict) -> bool:
        """True when bridge timestamp belongs to current Tehran session day."""
        ts = (data.get("timestamp") or "").strip()
        if not ts:
            return False
        try:
            dt = datetime.fromisoformat(ts)
        except ValueError:
            try:
                dt = datetime.strptime(ts, "%Y.%m.%d %H:%M:%S")
            except ValueError:
                return False

        start_minutes = 11 * 60
        current_minutes = dt.hour * 60 + dt.minute
        bridge_session_day = (dt - timedelta(days=1)).date() if current_minutes < start_minutes else dt.date()
        return bridge_session_day.isoformat() == get_session_day_str()

    def _sanitize_inactive_bridge_state(self, data: dict) -> dict:
        """Reset stale intraday counters when session is inactive and no day row exists."""
        if bool(data.get("session_active")):
            return data
        if self._is_bridge_data_for_current_session_day(data):
            return data

        trades_today = int(data.get("trades_today", 0) or 0)
        net_pnl = float(data.get("daily_profit_usd", 0) or 0) - float(data.get("daily_loss_usd", 0) or 0)
        has_stale_signal = bool(data.get("shutdown_signal")) or bool(data.get("break_active"))
        today_row = self._db.get_today()

        if today_row is not None:
            return data
        if trades_today == 0 and abs(net_pnl) < 0.0001 and not has_stale_signal:
            return data

        try:
            self._bridge.update(
                session_active=False,
                trading_allowed=False,
                shutdown_signal=False,
                break_active=False,
                break_until="",
                cooldown_until="0",
                last_trade_result="",
                last_trade_pnl=0.0,
                trades_today=0,
                daily_loss_usd=0.0,
                daily_profit_usd=0.0,
                consecutive_losses=0,
                losses_since_bias=0,
            )
            cleaned = self._bridge.read()
            log.warning("Cleared stale inactive bridge counters for new session day.")
            return cleaned
        except Exception as exc:
            log.warning("Failed to clear stale inactive bridge counters: %s", exc)
            return data

    def _cleanup_carryover_duplicate_day_if_detected(self, data: dict) -> bool:
        """Remove duplicated current-day rows that were copied from yesterday."""
        if bool(data.get("session_active")):
            return False

        current_day = get_session_day_str()
        try:
            previous_day = (
                datetime.strptime(current_day, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y-%m-%d")
        except ValueError:
            return False

        today_row = self._db.get_day(current_day)
        prev_row = self._db.get_day(previous_day)
        if not today_row or not prev_row:
            return False

        same_daily = (
            int(today_row.get("trades", 0)) == int(prev_row.get("trades", 0))
            and (today_row.get("result") or "") == (prev_row.get("result") or "")
            and abs(float(today_row.get("pnl", 0.0)) - float(prev_row.get("pnl", 0.0))) < 0.01
        )
        if not same_daily:
            return False

        bridge_trades = int(data.get("trades_today", 0) or 0)
        bridge_net = float(data.get("daily_profit_usd", 0) or 0) - float(data.get("daily_loss_usd", 0) or 0)
        bridge_matches_today = (
            bridge_trades == int(today_row.get("trades", 0))
            and abs(bridge_net - float(today_row.get("pnl", 0.0))) < 0.01
        )
        if not bridge_matches_today:
            return False

        self._db.clear_day(current_day)
        try:
            self._bridge.update(
                session_active=False,
                trading_allowed=False,
                shutdown_signal=False,
                break_active=False,
                break_until="",
                cooldown_until="0",
                last_trade_result="",
                last_trade_pnl=0.0,
                trades_today=0,
                daily_loss_usd=0.0,
                daily_profit_usd=0.0,
                consecutive_losses=0,
                losses_since_bias=0,
            )
        except Exception as exc:
            log.warning("Failed to reset bridge after carry-over cleanup: %s", exc)

        log.warning("Removed carry-over duplicate rows for session day %s", current_day)
        self._status_bar.showMessage("Cleared stale carry-over data for current session day.")
        self._load_history()
        return True

    def _record_violation(
        self,
        rule_code: str,
        severity: str,
        message: str,
        trade_index: int | None = None,
        context: dict | None = None,
        dedupe_key: str | None = None,
    ) -> None:
        """Persist one violation entry; optionally dedupe repeated keys."""
        if dedupe_key and dedupe_key in self._violation_dedupe:
            return
        if dedupe_key:
            self._violation_dedupe.add(dedupe_key)
        try:
            self._db.record_violation(
                rule_code=rule_code,
                severity=severity,
                message=message,
                trade_index=trade_index,
                context=context,
            )
        except Exception as exc:
            log.warning("Failed to record violation: %s", exc)

    def _track_rule_state_transitions(self, data: dict) -> None:
        """Record key session-rule transitions as violation/audit events."""
        shutdown_signal = bool(data.get("shutdown_signal"))
        break_active = bool(data.get("break_active"))
        bias_expired = bool(data.get("bias_expired"))
        news_lock = bool(data.get("news_lock"))
        trade_idx = int(data.get("trades_today", 0) or 0) or None

        if shutdown_signal and not self._prev_shutdown_signal:
            self._record_violation(
                rule_code="SHUTDOWN_SIGNAL",
                severity="critical",
                message="EA signaled session shutdown.",
                trade_index=trade_idx,
                context={"trading_allowed": bool(data.get("trading_allowed"))},
                dedupe_key=f"shutdown:{get_session_day_str()}",
            )
        if break_active and not self._prev_break_active:
            self._record_violation(
                rule_code="BREAK_ACTIVE",
                severity="critical",
                message="Break state became active.",
                trade_index=trade_idx,
                context={"break_until": data.get("break_until", "")},
                dedupe_key=f"break:{get_session_day_str()}",
            )
        if bias_expired and not self._prev_bias_expired:
            self._record_violation(
                rule_code="BIAS_EXPIRED_SIGNAL",
                severity="warn",
                message="Bias expired flag received from session.",
                trade_index=trade_idx,
                context={"losses_since_bias": int(data.get("losses_since_bias", 0) or 0)},
                dedupe_key=f"bias_expired:{get_session_day_str()}",
            )
        if news_lock and not self._prev_news_lock:
            self._record_violation(
                rule_code="NEWS_LOCK_ACTIVE",
                severity="info",
                message="News lock enabled; trade entries should be blocked.",
                trade_index=trade_idx,
                context={},
                dedupe_key=f"news_lock:{get_session_day_str()}",
            )

        self._prev_shutdown_signal = shutdown_signal
        self._prev_break_active = break_active
        self._prev_bias_expired = bias_expired
        self._prev_news_lock = news_lock

    def _enforce_break(self, data: dict) -> None:
        """Keep MT5 closed for one hour after N consecutive losses.

        EA sets break_active=True and trading_allowed=False. Here we:
        - On first detection, set break_until = now + 1 hour.
        - While now < break_until, keep killing MT5.
        - When the hour has passed, clear break_active/break_until and
          re-enable trading (unless other shutdown rules apply).
        """
        if not data.get("break_active"):
            return

        # Initialise break_until if missing
        break_until_str = data.get("break_until") or ""
        now = datetime.now()

        if not break_until_str:
            until = now + timedelta(hours=1)
            self._bridge.update(break_until=until.isoformat())
            self._status_bar.showMessage(
                "🛑  1-hour break started after consecutive losses."
            )
            mt5_controller.kill_mt5()
            return

        try:
            break_until = datetime.fromisoformat(break_until_str)
        except ValueError:
            # If parsing fails, reset the break to be safe.
            until = now + timedelta(hours=1)
            self._bridge.update(break_until=until.isoformat())
            return

        if now < break_until:
            # Still in break window — keep MT5 closed.
            mt5_controller.kill_mt5()
            return

        # Break period finished — clear flags and re-enable trading.
        self._bridge.update(
            break_active=False,
            break_until="",
            trading_allowed=True,
        )
        self._status_bar.showMessage(
            "✅  1-hour break finished — trading re-enabled for this session."
        )

    def _enforce_bias_expiry(self, data: dict) -> None:
        """Disable trading when bias has expired by time or losses.

        Rules:
        - Bias expires after 2 hours OR 3 losses since it was set.
        - After expiry, trading_allowed is set False and bias_expired True.
        - Updating the bias (via BiasWidget) clears bias_expired and
          re-enables trading for the current session.
        """
        if not data.get("session_active"):
            return
        if data.get("shutdown_signal"):
            # Full daily shutdown already in effect; do not interfere.
            return

        bias_set_at = data.get("bias_set_at") or ""
        if not bias_set_at:
            return

        try:
            bias_time = datetime.fromisoformat(bias_set_at)
        except ValueError:
            return

        now = datetime.now()
        age = now - bias_time
        losses_since_bias = int(data.get("losses_since_bias", 0) or 0)
        expired = bool(data.get("bias_expired"))

        if expired:
            return

        if age >= timedelta(hours=2) or losses_since_bias >= 3:
            self._bridge.update(
                trading_allowed=False,
                bias_expired=True,
            )
            self._record_violation(
                rule_code="BIAS_EXPIRED",
                severity="warn",
                message="Bias expired and trading was disabled until bias refresh.",
                context={
                    "age_minutes": int(age.total_seconds() // 60),
                    "losses_since_bias": losses_since_bias,
                },
            )
            self._status_bar.showMessage(
                "🛑  Bias expired — trading disabled until bias is updated."
            )
            QMessageBox.information(
                self,
                "Bias Expired",
                "Your bias has expired (time limit or 3 losses).\n"
                "New trades are now blocked until you refresh bias.",
            )
