"""
TradingGuard HITL - Consolidated 1-Year Multi-Season Portfolio Backtest
Evaluates the ratified multi-season quant strategies across all 4 asset classes:
BTCUSD, NQ, GBPUSD, and XAUUSD on 100,000 M5 bars with full calendar monthly breakdown.
"""

import sys
import json
import time
import datetime
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd
import numpy as np

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.quant_engine.state_space import MathematicalStateSpace
from hitl.quant_engine.rule_engine import QuantRule
from hitl.quant_engine.vectorized_backtester import VectorizedBacktester
from hitl.quant_engine.annual_backtest_runner import load_1year_data

OUTPUT_DIR = BASE_DIR / "backtest_results" / "quant_discovery" / "annual_1year"

SPREADS = {
    "XAUUSD": 0.22,
    "BTCUSD": 0.20,
    "NQ":     1.00,
    "GBPUSD": 0.00006
}

# 1. Load curated top ratified rules for each asset from annual discovery
with open(OUTPUT_DIR / "btcusd" / "annual_ratified_strategies.json") as f:
    btc_data = json.load(f)
with open(OUTPUT_DIR / "nq" / "annual_ratified_strategies.json") as f:
    nq_data = json.load(f)
with open(OUTPUT_DIR / "gbpusd" / "annual_ratified_strategies.json") as f:
    gbp_data = json.load(f)
with open(OUTPUT_DIR / "xauusd" / "annual_ratified_strategies.json") as f:
    xau_data = json.load(f)

def get_rule_by_id(data_list, rule_id):
    for item in data_list:
        if item["rule"]["rule_id"] == rule_id:
            return QuantRule.from_dict(item["rule"])
    raise ValueError(f"Rule {rule_id} not found")

# Curated High-Expectancy Institutional Quant Portfolio (11 Rules)
selected_rules = [
    # BTCUSD (High Alpha Momentum Sellers)
    ("BTCUSD", get_rule_by_id(btc_data, "R14_015")),  # PF 1.68, Net +173.28R
    ("BTCUSD", get_rule_by_id(btc_data, "R14_024")),  # PF 1.56, Net +167.07R
    ("BTCUSD", get_rule_by_id(btc_data, "R14_010")),  # PF 1.55, Net +110.67R
    
    # NQ (Mean Reversion & Volatility Breakout Buyers)
    ("NQ",     get_rule_by_id(nq_data, "R14_011")),   # PF 2.12, Net +35.69R
    ("NQ",     get_rule_by_id(nq_data, "R14_025")),   # PF 1.76, Net +34.55R, WR 42.9%
    ("NQ",     get_rule_by_id(nq_data, "R14_009")),   # PF 1.51, Net +33.22R
    
    # GBPUSD (Microstructure Volatility Squeeze Sellers)
    ("GBPUSD", get_rule_by_id(gbp_data, "R14_027")),  # PF 1.29, Net +44.96R
    ("GBPUSD", get_rule_by_id(gbp_data, "R12_019")),  # PF 1.59, Net +17.16R, WR 52.2%
    
    # XAUUSD (Newly Discovered Dual-Direction Momentum & Flow)
    ("XAUUSD", get_rule_by_id(xau_data, "R15_048")),  # BUY:  PF 1.75, Net +55.43R, WR 30.3%
    ("XAUUSD", get_rule_by_id(xau_data, "R14_058")),  # SELL: PF 1.62, Net +59.56R, WR 35.8%
    ("XAUUSD", get_rule_by_id(xau_data, "R11_022")),  # BUY:  PF 1.86, Net +42.47R, WR 25.5%
]

print("==========================================================================================")
print("🏛️ EVALUATING CONSOLIDATED MULTI-SEASON 1-YEAR QUANT PORTFOLIO (100,000 BARS)")
print("==========================================================================================")

all_trades = []
symbol_metrics = {}

for sym, rule in selected_rules:
    raw_df = load_1year_data(sym)
    ss = MathematicalStateSpace()
    st_df = ss.transform(raw_df)
    
    bt = VectorizedBacktester(symbol=sym, spread=SPREADS[sym], commission_usd=0.10)
    res = bt.run(st_df, rule)
    
    print(f"[{sym:6s}] Rule {rule.rule_id:8s}: {rule.direction:4s} | Fills: {res.total_fills:4d} | WR: {res.win_rate:4.1f}% | PF: {res.profit_factor:4.2f} | Net R: {res.net_r:+6.2f}R | Net PnL: ${res.net_pnl_usd:+8.2f} | Max DD: {res.max_drawdown_r:4.2f}R")
    
    for tr in res.trades:
        entry_dt = pd.to_datetime(tr.entry_time, unit='s')
        exit_dt = pd.to_datetime(tr.exit_time, unit='s')
        all_trades.append({
            "symbol": sym,
            "rule_id": rule.rule_id,
            "direction": rule.direction,
            "entry_time": tr.entry_time,
            "entry_datetime": entry_dt.strftime('%Y-%m-%d %H:%M:%S'),
            "exit_time": tr.exit_time,
            "exit_datetime": exit_dt.strftime('%Y-%m-%d %H:%M:%S'),
            "month": entry_dt.strftime('%Y-%m'),
            "year": entry_dt.strftime('%Y'),
            "entry_price": tr.entry_price,
            "exit_price": tr.exit_price,
            "sl_price": tr.sl_price,
            "tp_price": tr.tp_price,
            "status": tr.status,
            "realized_r": round(tr.r_realized, 2),
            "realized_pnl_usd": round(tr.pnl_usd, 2),
            "bars_held": tr.bars_held
        })

df_trades = pd.DataFrame(all_trades).sort_values("entry_time").reset_index(drop=True)

# Export consolidated orders schedule
sched_path = OUTPUT_DIR / "consolidated_annual_orders_schedule.csv"
df_trades.to_csv(sched_path, index=False)
print(f"\n✅ Exported {len(df_trades):,d} authentic trades to {sched_path.name}")

# Generate Monthly Breakdown Table
monthly_summary = []
for m, g in df_trades.groupby("month"):
    wins = len(g[g['status'] == 'WIN'])
    losses = len(g[g['status'] == 'LOSS'])
    total = len(g)
    wr = (wins / total * 100) if total > 0 else 0
    pnl = g['realized_pnl_usd'].sum()
    net_r = g['realized_r'].sum()
    
    gw = g[g['status'] == 'WIN']['realized_pnl_usd'].sum()
    gl = abs(g[g['status'] == 'LOSS']['realized_pnl_usd'].sum())
    pf = (gw / gl) if gl > 0 else (99.0 if gw > 0 else 0.0)
    
    cum_pnl = g['realized_pnl_usd'].cumsum()
    peak = cum_pnl.cummax()
    dd_usd = float((peak - cum_pnl).max()) if len(cum_pnl) > 0 else 0.0
    
    cum_r = g['realized_r'].cumsum()
    peak_r = cum_r.cummax()
    dd_r = float((peak_r - cum_r).max()) if len(cum_r) > 0 else 0.0
    
    monthly_summary.append({
        "month": m,
        "trades": total,
        "wins": wins,
        "losses": losses,
        "win_rate": round(wr, 1),
        "profit_factor": round(pf, 2),
        "net_r": round(net_r, 2),
        "realized_pnl_usd": round(pnl, 2),
        "max_dd_r": round(dd_r, 2),
        "max_dd_usd": round(dd_usd, 2)
    })

df_monthly = pd.DataFrame(monthly_summary)
print("\n=== CONSOLIDATED CALENDAR MONTH BREAKDOWN ===")
print(df_monthly.to_string(index=False))

# Overall Annual Metrics
tot_w = len(df_trades[df_trades['status'] == 'WIN'])
tot_l = len(df_trades[df_trades['status'] == 'LOSS'])
tot_n = len(df_trades)
tot_wr = (tot_w / tot_n * 100) if tot_n > 0 else 0
tot_pnl = df_trades['realized_pnl_usd'].sum()
tot_r = df_trades['realized_r'].sum()
gw = df_trades[df_trades['status'] == 'WIN']['realized_pnl_usd'].sum()
gl = abs(df_trades[df_trades['status'] == 'LOSS']['realized_pnl_usd'].sum())
tot_pf = (gw / gl) if gl > 0 else 0.0

cum_pnl = df_trades['realized_pnl_usd'].cumsum()
peak = cum_pnl.cummax()
tot_dd_usd = float((peak - cum_pnl).max())

cum_r = df_trades['realized_r'].cumsum()
peak_r = cum_r.cummax()
tot_dd_r = float((peak_r - cum_r).max())

r_vals = df_trades['realized_r'].values
sharpe = (np.mean(r_vals) / np.std(r_vals, ddof=1) * np.sqrt(252)) if len(r_vals) > 1 and np.std(r_vals, ddof=1) > 0 else 0.0

print("\n=== FULL-YEAR CONSOLIDATED PORTFOLIO METRICS ===")
print(f"Total Calendar Span : {pd.to_datetime(df_trades['entry_time'].min(), unit='s').strftime('%Y-%m-%d')} to {pd.to_datetime(df_trades['entry_time'].max(), unit='s').strftime('%Y-%m-%d')} ({(pd.to_datetime(df_trades['entry_time'].max(), unit='s') - pd.to_datetime(df_trades['entry_time'].min(), unit='s')).days} days)")
print(f"Total Executed Trades: {tot_n:,d}")
print(f"Win / Loss Record   : {tot_w} W / {tot_l} L")
print(f"Win Rate            : {tot_wr:.1f}%")
print(f"Annual Profit Factor: {tot_pf:.2f}")
print(f"Annual Net Realized : {tot_r:+.2f}R (${tot_pnl:+,.2f} USD)")
print(f"Annual Max Drawdown : {tot_dd_r:.2f}R (${tot_dd_usd:,.2f} USD)")
print(f"Annualized Sharpe   : {sharpe:.2f}")

summary_obj = {
    "audit_period": f"{pd.to_datetime(df_trades['entry_time'].min(), unit='s').strftime('%Y-%m-%d')} to {pd.to_datetime(df_trades['entry_time'].max(), unit='s').strftime('%Y-%m-%d')}",
    "total_calendar_days": (pd.to_datetime(df_trades['entry_time'].max(), unit='s') - pd.to_datetime(df_trades['entry_time'].min(), unit='s')).days,
    "total_trades": tot_n,
    "win_rate_pct": round(tot_wr, 2),
    "profit_factor": round(tot_pf, 2),
    "net_r": round(tot_r, 2),
    "net_pnl_usd": round(tot_pnl, 2),
    "max_drawdown_r": round(tot_dd_r, 2),
    "max_drawdown_usd": round(tot_dd_usd, 2),
    "sharpe_ratio": round(sharpe, 2),
    "monthly_table": monthly_summary
}

with open(OUTPUT_DIR / "consolidated_annual_summary.json", "w", encoding="utf-8") as f:
    json.dump(summary_obj, f, indent=2)
