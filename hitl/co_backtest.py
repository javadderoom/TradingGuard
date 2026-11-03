"""
TradingGuard HITL - Co-Backtest Engine (Collaborative Human + AI Council Replay)
Allows the Human Trader (Lead Partner) to participate as an active voting seat
alongside the 6 AI personas, discussing setups milestone-by-milestone.
"""

import sys
import datetime
from pathlib import Path
from typing import Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.data_feed import HistoricalDataFeed
from hitl.backtest.fast_screener import screen_ict_session
from hitl.backtest.forex_cross_pair import detect_forex_smt_divergence, analyze_cross_pair_symbiosis, format_symbiotic_prompt
from hitl.backtest.council_replay import convene_council_on_historical_dossier
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread


class CoBacktestSession:
    def __init__(self, symbol: str = "GBPUSD", helper_symbol: str = "EURUSD"):
        self.symbol = symbol
        self.helper_symbol = helper_symbol
        self.feed = HistoricalDataFeed()
        self.history = []

    def load_milestone(self, dt: datetime.datetime) -> Dict[str, Any]:
        """Loads all technical, symbiotic, and macro telemetry for a specific historical checkpoint."""
        import MetaTrader5 as mt5
        from hitl.backtest.data_feed import _convert_records
        
        sym_res = self.feed.engine.resolve_symbol(self.symbol)
        helper_res = self.feed.engine.resolve_symbol(self.helper_symbol)

        # 1. Fetch 5M & 1H bars for both pairs
        rates_5m_target = _convert_records(mt5.copy_rates_from(sym_res, mt5.TIMEFRAME_M5, dt, 85))
        rates_1h_target = _convert_records(mt5.copy_rates_from(sym_res, mt5.TIMEFRAME_H1, dt, 20))
        rates_5m_helper = _convert_records(mt5.copy_rates_from(helper_res, mt5.TIMEFRAME_M5, dt, 85))
        rates_1h_helper = _convert_records(mt5.copy_rates_from(helper_res, mt5.TIMEFRAME_H1, dt, 20))

        if not (rates_5m_target and rates_1h_target and rates_5m_helper and rates_1h_helper):
            return None

        # 2. Intermarket SMT & Cross-Pair Symbiosis
        smt_info = detect_forex_smt_divergence(
            rates_5m_target if "EUR" in self.symbol else rates_5m_helper,
            rates_5m_helper if "EUR" in self.symbol else rates_5m_target,
            dt.hour
        )
        symbiosis_info = analyze_cross_pair_symbiosis(rates_5m_target, rates_5m_helper, self.symbol, self.helper_symbol, smt_info)
        symbiosis_prompt = format_symbiotic_prompt(symbiosis_info)

        # 3. Screen technical setup
        screener_res = screen_ict_session(rates_5m_target, rates_1h_target, self.symbol, dt.hour, smt_info=smt_info)

        # 4. Assemble full dossier
        dossier = self.feed.prepare_session_dossier(self.symbol, dt)

        return {
            "datetime": dt,
            "symbol": self.symbol,
            "helper_symbol": self.helper_symbol,
            "current_price": rates_5m_target[-1]['close'],
            "screener_res": screener_res,
            "smt_info": smt_info,
            "symbiosis_info": symbiosis_info,
            "symbiosis_prompt": symbiosis_prompt,
            "dossier": dossier
        }

    def get_ai_council_deliberation(self, milestone_data: Dict[str, Any]) -> Dict[str, Any]:
        """Convenes the 6-Seat AI Council to hear their debate and preliminary directive."""
        dossier = milestone_data["dossier"]
        symbiosis_prompt = milestone_data["symbiosis_prompt"]
        dossier["telemetry_prompt"] = symbiosis_prompt + "\n\n" + dossier.get("telemetry_prompt", "")
        return convene_council_on_historical_dossier(dossier)

    def replay_order(
        self,
        dt: datetime.datetime,
        order: Dict[str, Any],
        hours_forward: int = 12
    ) -> Dict[str, Any]:
        """Replays an order forward through M1 bars with spread dynamics and Target Optimization."""
        forward_m1 = self.feed.get_forward_m1_bars(self.symbol, dt, hours_forward=hours_forward)
        return evaluate_council_decision(order, forward_m1, self.symbol)


co_engine = CoBacktestSession()
