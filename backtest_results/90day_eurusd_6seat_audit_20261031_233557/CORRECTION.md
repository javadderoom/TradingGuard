# CORRECTION — 90day_eurusd_6seat_audit_20261031_233557

**Date of correction:** 2026-11-07 (TradingGuard Pack 6).
**This file corrects the historical `executive_report.md` in this same directory. The original report file was NOT edited; it remains as generated. Read this file alongside it.**

## 1. Unrealised PnL was counted as realised profit

The report's headline **Net Realized PnL of $+0.00** includes floating mark-to-market on 2 trade(s) still open at the end of the evaluation window (`OPEN_AT_END`). That floating PnL is not cash and must not be summed as realised profit.

- **Correct realised net (closed trades only): $+1.33**
- **Unrealised floating PnL (excluded from the realised total): $+0.93**
- **Open trade(s):** 2026-08-17 15:30 EURUSD SELL_LIMIT floating $+1.53; 2026-09-07 15:30 EURUSD SELL_LIMIT floating $-0.60

## 2. The report header was zeroed (scorecard/generator mismatch)

The header of `executive_report.md` shows **0 approved orders, 0 filled trades, $0.00 net, 0.0% win rate** (and 0.0% stand-aside rate), while the run's own `full_dataset.json` — the dataset the report was generated from — records:

- Approved orders: **4**; filled trades: **2** (1W / 1L); total sessions: **130**; stand-asides: **126**
- Gross profit: **$+3.46**; gross loss: **$+1.20**; profit factor: **2.88**
- The generator that wrote this header read scorecard keys that did not match what the runner passed, so it fell back to zeros while the profit-factor key happened to match. The committed generator (`hitl/backtest/logger.py`, Pack 6) now derives the header from the session dataset itself and cross-checks it against the scorecard, so this class of error cannot recur silently.

## How the corrected figures were obtained

Recomputed directly from this directory's own `full_dataset.json`: realised net = sum of `realized_pnl_usd` over all sessions whose `status` is not `OPEN_AT_END`; unrealised net = sum over `OPEN_AT_END` sessions only. No data was re-run and no trade was re-simulated; the underlying ledger is unchanged.
