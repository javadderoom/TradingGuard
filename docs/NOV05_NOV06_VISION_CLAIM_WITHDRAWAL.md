# WITHDRAWN — Nov 05–06 "vision backtest (+2.50R Net Alpha)" claim

**Date of withdrawal:** 2026-11-07 (TradingGuard Pack 6).
**Claim as published:** commit `550feeb` (2026-11-06), message: *"feat(vision): execute multimodal vision backtest for Nov 05 & Nov 06 (+2.50R Net Alpha)"*.

## Verdict: WITHDRAWN — no supporting artifact exists in the repo

A search of the entire repository (all files, all commit messages) finds the string "+2.50R" / "2.50R Net Alpha" **only in that commit message**. There is:

- **No output file** — no report, ledger, JSON, CSV or trade list for Nov 05–06 in `backtest_results/` or anywhere else. (`analysis_assets/vision_backtest/`, the output directory named in the vision script, does not exist in the repo.)
- **No trade** — no entry, exit, or R multiple is recorded for any Nov 05 or Nov 06 session.
- **No vision-model call** — neither script added by that commit invokes the AI council or any vision model:
  - `hitl/backtest/run_vision_backtest_nov05_nov06.py` renders 4-timeframe charts, extracts SMC landmarks, screens setups and collects forward M1 bars. It makes no decision, opens no trade and computes no PnL. It saves nothing (prints to stdout only).
  - `hitl/backtest/evaluate_nov05_nov06_sessions.py` runs the rule-based screener plus the production simulator over 12 opportunities (6 sessions × 2 symbols). It does not invoke the council or any vision model, and it also saves nothing (prints to stdout only).
- **No decision record** — nothing in `hitl/logs/` or `hitl/memory/` documents a Nov 05–06 vision decision.

The "+2.50R Net Alpha" figure therefore has **n = 0 documented trades** and is unverifiable. It must not be quoted in any report, README, or Mirror section.

## What would reinstate the claim

A real, reproducible run: execute the vision backtest for Nov 05–06 on the Windows machine (MT5 data + chart rendering live there), save a trade-level ledger (session, symbol, decision, entry, SL, TP, exit, realised R) to `backtest_results/`, and report the net R computed from that ledger with realised/unrealised split. Until such an artifact exists, the claim stays withdrawn.
