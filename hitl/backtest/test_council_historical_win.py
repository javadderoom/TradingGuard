"""
TradingGuard HITL - Historical Council Replay on Winning Trade (Trade 86 - Nov 03, 2026 at Actual Trigger Bar)
"""

import sys
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.test_council_historical_session import test_historical_trade

if __name__ == "__main__":
    # Trade 86 (Nov 03, 2026 - Gold London/NY Overlap - Actual WIN +3.5R)
    # The actual signal bar closed at 13:25:00 at price 3906.72, and the limit entry filled at 13:30:00 @ 3908.48!
    trade_86 = {
        "date": "2026-11-03",
        "target_time": datetime.datetime(2026, 11, 3, 13, 25),
        "symbol": "XAUUSD_o",
        "session": "London_Post_Open",
        "archetype_id": "SETUP-ARCH-004",
        "direction": "SHORT",
        "setup_name": "BEARISH_EXPANSION",
        "entry_price": 3908.48,
        "stop_loss": 3911.70,
        "risk_pts": 3.22,
        "target_rr": 3.5,
        "status": "WIN",
        "net_r": 3.5
    }
    test_historical_trade(trade_86)
