import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

from hitl.review_engine import (
    _previous_trading_date,
    analyze_previous_trading_day,
    run_morning_briefing,
)


def test_previous_trading_date_skips_weekend():
    # Monday Nov 9 -> Friday Nov 6
    assert _previous_trading_date(datetime.date(2026, 11, 9)) == datetime.date(2026, 11, 6)
    # Thursday Nov 12 -> Wednesday Nov 11
    assert _previous_trading_date(datetime.date(2026, 11, 12)) == datetime.date(2026, 11, 11)


def test_morning_briefing_never_recycles_stale_lesson_and_uses_dynamic_clock(monkeypatch):
    # Force reference date = Thursday Nov 12, 2026 10:30 Tehran
    class FixedDateTime(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            base = datetime.datetime(2026, 11, 12, 10, 30, 0, tzinfo=ZoneInfo("Asia/Tehran"))
            return base if tz is not None else base.replace(tzinfo=None)

    monkeypatch.setattr("hitl.review_engine.datetime.datetime", FixedDateTime)
    monkeypatch.setattr(
        "hitl.review_engine.analyze_previous_trading_day",
        lambda engine, prev_date, symbols=None: {
            "date_str": "2026-11-11",
            "market_recap": [
                {
                    "symbol": "XAUUSD",
                    "open": 4050.00,
                    "high": 4066.87,
                    "low": 4000.67,
                    "close": 4010.00,
                    "range_pts": 66.20,
                    "direction": "BEARISH",
                    "change_pts": -40.00,
                    "smc_signals": [
                        {
                            "archetype": "SETUP-ARCH-001",
                            "direction": "SHORT",
                            "time_tehran": "11:35",
                            "entry": 4060.37,
                            "outcome": "WIN (+2.00R)",
                        }
                    ],
                }
            ],
            "live_decisions": {
                "total": 12,
                "approved": 0,
                "stand_aside": 12,
                "missed_winners": 0,
                "protective_vetoes": 5,
            },
        },
    )
    monkeypatch.setattr(
        "hitl.review_engine.calculate_htf_fundamental_bias",
        lambda sym: {"execution_filter": "BEARISH_FAVORED", "usdx_metrics": {"momentum_5d_pct": 0.42}},
    )
    monkeypatch.setattr("hitl.review_engine.get_upcoming_events", lambda sym, hours_ahead=12: [])

    sent_messages = []
    mock_client = MagicMock()
    mock_client.send_message.side_effect = lambda chat_id, text: sent_messages.append(text)

    mock_engine = MagicMock()
    mock_engine.ensure_connected.return_value = False

    res = run_morning_briefing(mock_engine, mock_client, chat_id="123")
    assert res["status"] == "COMPLETED"
    assert len(sent_messages) == 1
    msg = sent_messages[0]

    # Must NEVER contain the stale Nov 10 boilerplate
    assert "Detected 12 missed winning setup(s)" not in msg
    assert "Authorize selective counter-trend entries" not in msg

    # Must include actual past-day Nov 11 analysis & dynamic Winter 11:30 London open
    assert "2026-11-11" in msg
    assert "4066.87" in msg
    assert "SETUP-ARCH-001" in msg
    assert "11:30 Tehran" in msg


def test_analyze_previous_trading_day_offline_graceful(monkeypatch):
    monkeypatch.setattr("hitl.review_engine._load_log", lambda: [
        {"date_str": "2026-11-10", "decision": "STAND_ASIDE", "review_verdict": "MISSED WINNER"},
        {"date_str": "2026-11-11", "decision": "STAND_ASIDE", "review_verdict": "PROTECTIVE VETO"},
        {"date_str": "2026-11-11", "decision": "SELL_LIMIT", "review_verdict": "WIN"},
    ])
    mock_engine = MagicMock()
    mock_engine.ensure_connected.return_value = False

    recap = analyze_previous_trading_day(mock_engine, datetime.date(2026, 11, 11))
    assert recap["date_str"] == "2026-11-11"
    # Strictly counts ONLY Nov 11 decisions, ignoring Nov 10
    assert recap["live_decisions"]["total"] == 2
    assert recap["live_decisions"]["stand_aside"] == 1
    assert recap["live_decisions"]["approved"] == 1
    assert recap["live_decisions"]["missed_winners"] == 0
    assert recap["live_decisions"]["protective_vetoes"] == 1
