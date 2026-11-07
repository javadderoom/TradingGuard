# CORRECTION — metals_basket_xau_xag_audit_20261101_075029

**Date of correction:** 2026-11-07 (TradingGuard Pack 6).
**This file corrects the historical `executive_report.md` in this same directory. The original report file was NOT edited; it remains as generated. Read this file alongside it.**

## 1. Unrealised PnL was counted as realised profit

The report's headline **Net Realized PnL of $+8.05** includes floating mark-to-market on 1 trade(s) still open at the end of the evaluation window (`OPEN_AT_END`). That floating PnL is not cash and must not be summed as realised profit.

- **Correct realised net (closed trades only): $-37.60**
- **Unrealised floating PnL (excluded from the realised total): $+45.65**
- **Open trade(s):** 2026-09-18 16:00 XAGUSD SELL_LIMIT floating $+45.65

## How the corrected figures were obtained

Recomputed directly from this directory's own `full_dataset.json`: realised net = sum of `realized_pnl_usd` over all sessions whose `status` is not `OPEN_AT_END`; unrealised net = sum over `OPEN_AT_END` sessions only. No data was re-run and no trade was re-simulated; the underlying ledger is unchanged.
