"""
Unit tests for Account Profile & Risk Governor (AccountRiskManager).
Verifies Prop Firm vs Personal account rules, concurrent risk constraints,
daily and overall drawdown ceilings, and circuit breakers.
"""

import pytest
import tempfile
import json
from pathlib import Path
from hitl.account_risk_manager import AccountRiskManager


class MockMT5Engine:
    """Mock MT5Engine for isolated risk testing without live broker."""
    def __init__(self, balance=10000.0, equity=10000.0, open_positions=None, pending_orders=None, realized_pnl=0.0):
        self._balance = balance
        self._equity = equity
        self._open_positions = open_positions or []
        self._pending_orders = pending_orders or []
        self._realized_pnl = realized_pnl

    def ensure_connected(self):
        return True

    def get_account_summary(self):
        return {
            "login": 99999,
            "server": "MockBroker",
            "trade_mode": "DEMO",
            "currency": "USD",
            "balance": self._balance,
            "equity": self._equity,
            "margin_free": self._equity,
            "profit": self._equity - self._balance
        }

    def get_daily_performance(self):
        return {
            "realized_pnl": self._realized_pnl,
            "daily_loss": abs(self._realized_pnl) if self._realized_pnl < 0 else 0.0,
            "consecutive_losses": 1 if self._realized_pnl < 0 else 0,
            "circuit_tripped": False,
            "reason": ""
        }

    def get_open_positions(self):
        return self._open_positions

    def get_pending_orders(self):
        return self._pending_orders

    def calculate_risk_usd(self, symbol, order_type, price, sl, lot):
        # Mock calculation: 100 points = $10 per 0.01 lot
        return abs(price - sl) * 100.0 * (lot / 0.01)


@pytest.fixture
def temp_governor():
    """Provides an isolated AccountRiskManager instance backed by a temporary file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_file = Path(tmp_dir) / "test_account_risk_profile.json"
        gov = AccountRiskManager(config_path=tmp_file)
        yield gov


def test_initial_defaults(temp_governor):
    """Verifies default initialization to PROP_FIRM with institutional safe buffers."""
    assert temp_governor.mode == "PROP_FIRM"
    prof = temp_governor.active_profile
    assert prof["max_open_trades"] == 2
    assert prof["max_concurrent_risk_pct"] == 1.5
    assert prof["hard_concurrent_risk_pct"] == 2.0
    assert prof["max_daily_drawdown_pct"] == 4.0
    assert prof["hard_daily_drawdown_pct"] == 5.0
    assert prof["max_overall_drawdown_pct"] == 10.0
    assert prof["hard_overall_drawdown_pct"] == 12.0


def test_mode_switch(temp_governor):
    """Verifies mode toggling between PROP_FIRM and PERSONAL."""
    assert temp_governor.set_account_mode("PERSONAL") is True
    assert temp_governor.mode == "PERSONAL"
    assert temp_governor.active_profile["max_open_trades"] == 3
    assert temp_governor.active_profile["max_concurrent_risk_pct"] == 3.0

    assert temp_governor.set_account_mode("PROP_FIRM") is True
    assert temp_governor.mode == "PROP_FIRM"
    assert temp_governor.active_profile["max_open_trades"] == 2

    # Reject invalid modes
    assert temp_governor.set_account_mode("INVALID_MODE") is False


def test_update_limits(temp_governor):
    """Verifies parameter calibration updates."""
    assert temp_governor.update_limit("max_open_trades", 4) is True
    assert temp_governor.active_profile["max_open_trades"] == 4

    assert temp_governor.update_limit("max_concurrent_risk_pct", 1.8) is True
    assert temp_governor.active_profile["max_concurrent_risk_pct"] == 1.8

    assert temp_governor.update_limit("non_existent_key", 10) is False


def test_trade_feasibility_approved_under_limits(temp_governor):
    """Verifies an order within all prop firm boundaries is approved."""
    engine = MockMT5Engine(balance=10000.0, equity=10000.0)
    # Order risking $10 on $10,000 capital = 0.1% risk
    ok, msg, m = temp_governor.evaluate_order_feasibility(
        symbol="XAUUSD_o",
        order_type_str="BUY_LIMIT",
        price=2700.0,
        sl=2699.0,
        tp=2720.0,
        lot=0.01,
        risk_usd=10.0,
        engine=engine
    )
    assert ok is True
    assert "Approved" in msg
    assert m["open_trades"] == 0
    assert m["projected_risk_pct"] == 0.1


def test_rejection_on_max_open_trades(temp_governor):
    """Verifies rejection when concurrent active trades reach max limit."""
    mock_positions = [
        {"symbol": "XAUUSD_o", "type": "BUY", "price_open": 2700.0, "sl": 2690.0, "volume": 0.01}
    ]
    mock_orders = [
        {"symbol": "GBPUSD_o", "type": "BUY_LIMIT", "price_open": 1.3000, "sl": 1.2980, "volume": 0.01}
    ]
    engine = MockMT5Engine(balance=10000.0, equity=10000.0, open_positions=mock_positions, pending_orders=mock_orders)

    # Currently 2 active trades. Limit is 2. Proposing a 3rd should fail.
    ok, msg, m = temp_governor.evaluate_order_feasibility(
        symbol="EURUSD_o",
        order_type_str="BUY_LIMIT",
        price=1.0900,
        sl=1.0880,
        tp=1.0950,
        lot=0.01,
        risk_usd=10.0,
        engine=engine
    )
    assert ok is False
    assert "Max Concurrent Trades Reached" in msg
    assert m["open_trades"] == 2


def test_rejection_on_excessive_concurrent_risk(temp_governor):
    """Verifies rejection when total open risk exceeds the configured safe ceiling."""
    engine = MockMT5Engine(balance=10000.0, equity=10000.0)
    # Propose an order risking $160 on $10,000 capital = 1.6% (exceeds 1.5% safe cap)
    ok, msg, m = temp_governor.evaluate_order_feasibility(
        symbol="XAUUSD_o",
        order_type_str="BUY_LIMIT",
        price=2700.0,
        sl=2684.0,
        tp=2750.0,
        lot=0.01,
        risk_usd=160.0,
        engine=engine
    )
    assert ok is False
    assert "Concurrent Risk Cap Exceeded" in msg
    assert m["projected_risk_pct"] == 1.6


def test_rejection_on_daily_drawdown_limit(temp_governor):
    """Verifies trade rejection when existing loss + trade risk breaches safe daily DD."""
    # Account has already lost $380 today on $10,000 capital (3.8% DD)
    engine = MockMT5Engine(balance=9620.0, equity=9620.0, realized_pnl=-380.0)

    # Adding a $30 risk trade would push projected daily loss to $410 (4.1% > 4.0% safe limit)
    ok, msg, m = temp_governor.evaluate_order_feasibility(
        symbol="XAUUSD_o",
        order_type_str="BUY_LIMIT",
        price=2700.0,
        sl=2697.0,
        tp=2720.0,
        lot=0.01,
        risk_usd=30.0,
        engine=engine
    )
    assert ok is False
    assert "Daily Drawdown Danger Zone" in msg


def test_circuit_breaker_trip_and_reset(temp_governor):
    """Verifies that an active circuit breaker blocks all order placement until reset."""
    engine = MockMT5Engine(balance=10000.0, equity=10000.0)
    temp_governor.trip_circuit_breaker("Emergency Halt Triggered")
    assert temp_governor.state["circuit_breaker_active"] is True

    ok, msg, _ = temp_governor.evaluate_order_feasibility(
        symbol="XAUUSD_o",
        order_type_str="BUY_LIMIT",
        price=2700.0,
        sl=2699.0,
        tp=2720.0,
        lot=0.01,
        risk_usd=10.0,
        engine=engine
    )
    assert ok is False
    assert "Circuit Breaker Active" in msg

    # Manual reset
    assert temp_governor.reset_circuit_breaker() is True
    assert temp_governor.state["circuit_breaker_active"] is False

    # Should be approved again
    ok, msg, _ = temp_governor.evaluate_order_feasibility(
        symbol="XAUUSD_o",
        order_type_str="BUY_LIMIT",
        price=2700.0,
        sl=2699.0,
        tp=2720.0,
        lot=0.01,
        risk_usd=10.0,
        engine=engine
    )
    assert ok is True
