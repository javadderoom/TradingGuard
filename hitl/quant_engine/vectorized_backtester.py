"""
TradingGuard HITL - Vectorized Historical Backtester
High-throughput, array-accelerated trade simulation engine.
Strict broker realism: spreads, commissions, SL-first intra-bar precedence,
dynamic ATR target/stop anchors, and TTL expiration.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
import numpy as np
import pandas as pd

from .rule_engine import QuantRule


@dataclass
class TradeRecord:
    entry_idx: int
    exit_idx: int
    entry_time: int
    exit_time: int
    direction: str
    entry_price: float
    exit_price: float
    sl_price: float
    tp_price: float
    status: str  # 'WIN', 'LOSS', 'BREAKEVEN', 'EXPIRED'
    r_realized: float
    pnl_usd: float
    bars_held: int


@dataclass
class BacktestResult:
    symbol: str
    rule_id: str
    total_signals: int
    total_fills: int
    wins: int
    losses: int
    breakevens: int
    expired: int
    win_rate: float
    net_r: float
    net_pnl_usd: float
    profit_factor: float
    max_drawdown_r: float
    sharpe_ratio: float
    trades: List[TradeRecord] = field(default_factory=list)

    def summary(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "rule_id": self.rule_id,
            "signals": self.total_signals,
            "fills": self.total_fills,
            "wins": self.wins,
            "losses": self.losses,
            "breakevens": self.breakevens,
            "expired": self.expired,
            "win_rate_pct": round(self.win_rate, 2),
            "net_r": round(self.net_r, 2),
            "net_pnl_usd": round(self.net_pnl_usd, 2),
            "profit_factor": round(self.profit_factor, 2),
            "max_drawdown_r": round(self.max_drawdown_r, 2),
            "sharpe_ratio": round(self.sharpe_ratio, 2)
        }


class VectorizedBacktester:
    """
    Simulates quantitative rule executions across time-series bar arrays.
    """

    # Realistic institutional broker spread standards synchronized with evaluator.py
    DEFAULT_SPREADS = {
        "XAUUSD": 0.15,
        "GOLD": 0.15,
        "NQ": 1.0,
        "US100": 1.0,
        "BTCUSD": 1.50,
        "GBPUSD": 0.00025,
        "EURUSD": 0.00018,
        "SPX": 0.50,
        "YM": 2.00,
        "XAGUSD": 0.030,
    }

    def __init__(
        self,
        symbol: str = "NQ",
        spread: Optional[float] = None,
        commission_usd: float = 0.10,
        risk_per_trade_usd: float = 12.0
    ):
        self.symbol = symbol.upper()
        if spread is not None:
            self.spread = spread
        else:
            self.spread = self._resolve_spread(self.symbol)
        self.commission_usd = commission_usd
        self.risk_per_trade_usd = risk_per_trade_usd

    def _resolve_spread(self, sym: str) -> float:
        try:
            from hitl.backtest.evaluator import get_default_broker_spread
            return get_default_broker_spread(sym)
        except Exception:
            for k, v in self.DEFAULT_SPREADS.items():
                if k in sym.upper():
                    return v
            return 1.0  # Generic default

    def run(self, state_df: pd.DataFrame, rule: QuantRule) -> BacktestResult:
        """
        Executes a vectorized backtest for the specified rule on state_df.
        state_df must contain ['time', 'open', 'high', 'low', 'close', 'atr_raw'].
        """
        signals = rule.evaluate(state_df).values
        n_bars = len(state_df)
        sig_indices = np.where(signals)[0]

        total_signals = len(sig_indices)
        if total_signals == 0:
            return BacktestResult(
                symbol=self.symbol,
                rule_id=rule.rule_id,
                total_signals=0,
                total_fills=0,
                wins=0,
                losses=0,
                breakevens=0,
                expired=0,
                win_rate=0.0,
                net_r=0.0,
                net_pnl_usd=0.0,
                profit_factor=0.0,
                max_drawdown_r=0.0,
                sharpe_ratio=0.0,
                trades=[]
            )

        times = state_df['time'].values
        opens = state_df['open'].values
        highs = state_df['high'].values
        lows = state_df['low'].values
        closes = state_df['close'].values
        atrs = state_df['atr_raw'].values

        trades: List[TradeRecord] = []
        is_buy = (rule.direction.upper() == 'BUY')

        current_active_exit = -1

        for idx in sig_indices:
            # Cannot enter new trade if previous trade is still running
            if idx <= current_active_exit:
                continue

            # Need at least one bar forward for entry
            if idx + 1 >= n_bars:
                continue

            entry_idx = idx + 1
            atr_val = atrs[idx]
            if np.isnan(atr_val) or atr_val <= 0:
                continue

            raw_open = opens[entry_idx]

            # Price levels with authentic MT5 broker spread accounting:
            # Bar prices are Bid. BUY fills at Ask = Bid + spread. SELL fills at Bid.
            if is_buy:
                entry_price = raw_open + self.spread
                sl_dist = rule.sl_atr_mult * atr_val
                tp_dist = rule.tp_atr_mult * atr_val
                sl_price = entry_price - sl_dist  # Bid level
                tp_price = entry_price + tp_dist  # Bid level
            else:
                entry_price = raw_open  # Bid level
                sl_dist = rule.sl_atr_mult * atr_val
                tp_dist = rule.tp_atr_mult * atr_val
                sl_price = entry_price + sl_dist  # Ask level
                tp_price = entry_price - tp_dist  # Ask level

            initial_risk_pts = sl_dist
            if initial_risk_pts <= 1e-9:
                continue

            # Scan forward bars up to TTL
            max_forward = min(n_bars, entry_idx + rule.ttl_bars + 1)
            trade_status = 'EXPIRED'
            # Expired exit price: BUY exits at Bid (close); SELL exits at Ask (close + spread)
            exit_price = closes[max_forward - 1] if is_buy else (closes[max_forward - 1] + self.spread)
            exit_idx = max_forward - 1
            be_active = False

            for f_idx in range(entry_idx, max_forward):
                f_high = highs[f_idx]
                f_low = lows[f_idx]

                if is_buy:
                    # 1. Evaluate exits against levels in force at the START of this bar
                    effective_sl = (entry_price + self.spread) if be_active else sl_price
                    sl_hit = (f_low <= effective_sl)
                    tp_hit = (f_high >= tp_price)

                    # TradingGuard Pessimistic Mandate: Both hit in same bar -> LOSS (or BREAKEVEN if armed prior)
                    if sl_hit and tp_hit:
                        trade_status = 'BREAKEVEN' if be_active else 'LOSS'
                        exit_price = effective_sl
                        exit_idx = f_idx
                        break
                    elif sl_hit:
                        trade_status = 'BREAKEVEN' if be_active else 'LOSS'
                        exit_price = effective_sl
                        exit_idx = f_idx
                        break
                    elif tp_hit:
                        trade_status = 'WIN'
                        exit_price = tp_price
                        exit_idx = f_idx
                        break

                    # 2. Breakeven ratchet update at END of bar, for subsequent bars
                    # Only reached if this bar hit neither SL nor TP
                    if rule.be_ratchet_r is not None and not be_active:
                        mfe_fav = f_high - entry_price
                        if mfe_fav >= (rule.be_ratchet_r * initial_risk_pts):
                            be_active = True

                else:  # SELL (Exits at Ask = Bid + spread)
                    effective_sl = (entry_price - self.spread) if be_active else sl_price
                    sl_hit = (f_high + self.spread >= effective_sl)
                    tp_hit = (f_low + self.spread <= tp_price)

                    if sl_hit and tp_hit:
                        trade_status = 'BREAKEVEN' if be_active else 'LOSS'
                        exit_price = effective_sl
                        exit_idx = f_idx
                        break
                    elif sl_hit:
                        trade_status = 'BREAKEVEN' if be_active else 'LOSS'
                        exit_price = effective_sl
                        exit_idx = f_idx
                        break
                    elif tp_hit:
                        trade_status = 'WIN'
                        exit_price = tp_price
                        exit_idx = f_idx
                        break

                    # Breakeven ratchet update at END of bar, for subsequent bars
                    if rule.be_ratchet_r is not None and not be_active:
                        mfe_fav = entry_price - (f_low + self.spread)
                        if mfe_fav >= (rule.be_ratchet_r * initial_risk_pts):
                            be_active = True

            # Calculate realized R and PnL
            usd_per_pt = self.risk_per_trade_usd / initial_risk_pts
            if trade_status == 'WIN':
                r_realized = rule.tp_atr_mult / rule.sl_atr_mult
                pnl_usd = (r_realized * self.risk_per_trade_usd) - self.commission_usd
            elif trade_status == 'LOSS':
                r_realized = -1.0
                pnl_usd = -self.risk_per_trade_usd - self.commission_usd
            elif trade_status == 'BREAKEVEN':
                # BE covers broker spread: gross profit is spread points
                gross_usd = self.spread * usd_per_pt
                pnl_usd = gross_usd - self.commission_usd
                r_realized = pnl_usd / self.risk_per_trade_usd
            else:  # EXPIRED
                if is_buy:
                    pts_diff = exit_price - entry_price
                else:
                    pts_diff = entry_price - exit_price
                r_realized = pts_diff / initial_risk_pts
                pnl_usd = (r_realized * self.risk_per_trade_usd) - self.commission_usd

            trades.append(
                TradeRecord(
                    entry_idx=entry_idx,
                    exit_idx=exit_idx,
                    entry_time=int(times[entry_idx]),
                    exit_time=int(times[exit_idx]),
                    direction=rule.direction.upper(),
                    entry_price=round(float(entry_price), 5),
                    exit_price=round(float(exit_price), 5),
                    sl_price=round(float(sl_price), 5),
                    tp_price=round(float(tp_price), 5),
                    status=trade_status,
                    r_realized=round(float(r_realized), 3),
                    pnl_usd=round(float(pnl_usd), 2),
                    bars_held=int(exit_idx - entry_idx + 1)
                )
            )
            current_active_exit = exit_idx

        # Compute aggregate statistics
        fills = len(trades)
        wins = sum(1 for t in trades if t.status == 'WIN')
        losses = sum(1 for t in trades if t.status == 'LOSS')
        breakevens = sum(1 for t in trades if t.status == 'BREAKEVEN')
        expired = sum(1 for t in trades if t.status == 'EXPIRED')

        win_rate = (wins / fills * 100.0) if fills > 0 else 0.0
        net_r = sum(t.r_realized for t in trades)
        net_pnl = sum(t.pnl_usd for t in trades)

        gross_profit = sum(t.pnl_usd for t in trades if t.pnl_usd > 0)
        gross_loss = abs(sum(t.pnl_usd for t in trades if t.pnl_usd < 0))

        if gross_loss > 0:
            pf = gross_profit / gross_loss
        else:
            pf = min(50.0, gross_profit / max(0.01, self.commission_usd)) if gross_profit > 0 else 0.0

        # Maximum Drawdown in R
        cum_r = np.cumsum([t.r_realized for t in trades]) if trades else np.array([0.0])
        peak_r = np.maximum.accumulate(cum_r)
        drawdown_r = peak_r - cum_r
        max_dd_r = float(np.max(drawdown_r)) if len(drawdown_r) > 0 else 0.0

        # Annualized Sharpe ratio (assuming ~252 trading days, ~200 trades/year baseline)
        r_series = np.array([t.r_realized for t in trades])
        if len(r_series) > 1:
            std_r = np.std(r_series)
            mean_r = np.mean(r_series)
            if std_r > 1e-9:
                sharpe = float((mean_r / std_r) * np.sqrt(min(252, fills)))
            else:
                sharpe = 10.0 if mean_r > 0 else 0.0
        else:
            sharpe = 0.0

        return BacktestResult(
            symbol=self.symbol,
            rule_id=rule.rule_id,
            total_signals=total_signals,
            total_fills=fills,
            wins=wins,
            losses=losses,
            breakevens=breakevens,
            expired=expired,
            win_rate=win_rate,
            net_r=net_r,
            net_pnl_usd=net_pnl,
            profit_factor=pf,
            max_drawdown_r=max_dd_r,
            sharpe_ratio=sharpe,
            trades=trades
        )
