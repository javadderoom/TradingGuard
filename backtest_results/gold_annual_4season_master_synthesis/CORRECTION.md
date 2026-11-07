# CORRECTION — XAUUSD (Gold) annual summary metrics

**Date of correction:** 2026-11-07 (TradingGuard Pack 6).
**This file corrects the historical `summary_metrics.json` in this same directory. The original JSON file was NOT edited; it remains as generated. Read this file alongside it.**

## The mislabelling

In the JSON, `seasonal_breakdown`, `archetype_breakdown` and `session_breakdown` are presented as the full-year breakdowns, but they were computed on **calibrated fills only** — the post-hoc filtered subset (bans chosen after seeing the same year). They do not describe the full year.

- Calibrated fills in the breakdowns: **137** (net +17.0R, PF 1.19)
- All fills in the full-year ledger: **414** (net -54.0R, PF 0.81)

## Seasonal breakdown: calibrated (as published) vs all fills (the full year)

| Season | Calibrated fills (JSON) | Calibrated net R | All fills (ledger) | All-fills net R |
| :--- | :---: | :---: | :---: | :---: |
| Winter | 29 | -6.0 | 102 | -33.5 |
| Spring | 26 | -11.0 | 102 | -10.0 |
| Summer | 35 | +8.5 | 107 | -12.0 |
| Autumn | 47 | +25.5 | 103 | +1.5 |

The same applies to `archetype_breakdown` (sums to the calibrated fill count, not the annual one) and `session_breakdown`.

## Fix in code

The synthesis scripts (`hitl/backtest/gold_annual_4season_master_synthesis.py` and `hitl/backtest/gbpusd_annual_4season_master_synthesis.py`, Pack 6) now ship both populations in the JSON: the old keys are kept for compatibility but are explicitly labelled via a new `breakdown_population` field, and `seasonal_breakdown_all_fills` / `archetype_breakdown_all_fills` / `session_breakdown_all_fills` carry the unfiltered full-year breakdowns. Re-running the synthesis regenerates a correctly labelled file; this historical file is left untouched.

## How the corrected figures were obtained

Recomputed directly from this directory's own all-trades ledger CSV (status WIN/LOSS/BREAKEVEN only, grouped by season). No data was re-run and no trade was re-simulated.
