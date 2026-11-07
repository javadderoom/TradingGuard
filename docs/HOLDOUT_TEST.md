# TradingGuard True Holdout Test (Pack 7)

## Why this exists

The reported **+17.0R was post-hoc**: its bans (ARCH-002, ARCH-009, Silver
Bullet) were picked after seeing Jan–Nov 2026. That year is the **tuning
period** and can never be a holdout again. This test measures the frozen
rule set on genuinely unseen data — Nov–Dec 2026 (default), or 2025.

## What it measures

The **rule-based screener + canonical simulator only** (deterministic,
reproducible). The LLM council is NOT in this loop: one `agy.exe` call per
setup is slow and non-deterministic (no temperature/seed flag exists), so a
council holdout would not be reproducible. A council holdout needs a
separate protocol and is not claimed here.

## Run it (Windows, MT5 running)

```bat
cd G:\Code\TradingGuard
git pull
python -m hitl.backtest.run_holdout_test --dry-run
python -m hitl.backtest.run_holdout_test
```

Defaults: `--start 2026-11-07 --end 2026-12-31`,
`--symbols XAUUSD,XAGUSD,EURUSD,GBPUSD`, live MT5 data. Expect it to take
a while (8 checkpoints x trading days x 4 symbols; each checkpoint is one
fast screener call, only passing setups run the simulator).

Other periods:

```bat
python -m hitl.backtest.run_holdout_test --start 2025-01-06 --end 2025-03-31
python -m hitl.backtest.run_holdout_test --start 2026-11-07 --end 2026-11-30 --symbols XAUUSD,GBPUSD
```

### Data prerequisite

- **Live MT5 (default):** the terminal must be running and logged in, with
  M1/M5/H1 history for the symbols and period. If MT5 is not available the
  run fails loudly (exit 3) instead of silently running on partial data.
- **Or a cache:** `--data-dir backtest_results\cache` with
  `M1_<SYMBOL>_<YEAR>.parquet` (same layout `htf_macro_runner_backtest.py`
  writes) or `M1_<SYMBOL>_<YEAR>.csv` with columns
  `time,open,high,low,close,tick_volume` (time = unix epoch seconds).
  To build the cache from MT5 first, run the fetch step in
  `hitl/backtest/htf_macro_runner_backtest.py` (`load_or_fetch_m1_bars`).
- **Missing-data rule:** if >10% of checkpoints have no bars the run aborts
  (exit 3) and reports no result.

## Outputs

`backtest_results/holdout_<start>_<end>/`:

- `trade_ledger.csv` — one row per checkpoint: session, symbol, archetype,
  decision, entry/SL/TP, target RR, risk $, status, fill/exit minute,
  realised R, realised $ (closed trades only), floating $ (OPEN_AT_END only).
- `summary.json` / `summary.md` — fills, W/L/BE/open, win rate, realised
  net $ and net R, profit factor, expectancy, max drawdown, unrealised $.
- `frozen_rules_used.json` — the exact frozen rule file the run used.

## Frozen rules — read before touching anything

- `hitl/backtest/holdout_frozen_rules_2026-11-07.json` — 49 ACTIVE playbook
  rules (RULE-CORE-001 $12/trade; $34/day loss; $35/day profit; max 3
  trades/day/symbol), 14 ratified archetypes, simulator settings
  (closed-bars only, SL-first, $0.10 commission / 0.01 lot, 75-min TTL),
  plus SHA-256 hashes of the six source files the rules live in.
- The runner **loads the frozen file, never the live playbook**, and
  **refuses to run if any frozen source hash differs**. To change a rule,
  re-freeze: `python -m hitl.backtest.run_holdout_test --freeze`, then
  commit the file with a note saying what changed and why.
- **Re-freezing after seeing holdout results is itself tuning on the
  holdout and must be disclosed as such.** One freeze, one run, report
  what it says.
- Honest scope note: ARCH-002 and ARCH-009 are RATIFIED in the registry at
  freeze time, so the holdout tests the rules as they stand — including
  those two — not a re-tuned subset. The Silver Bullet session ban for
  XAU/GBP is hard-coded in the screener and covered by its frozen hash.

## Tuning-period guard

Any period overlapping 2026-01-01..2026-11-06 is **refused** (exit 2)
unless `--allow-tuning-period` is passed — and then the output directory
and summary are labelled `TUNING-PERIOD`, never `HOLDOUT`.

## What pass / fail looks like

There is no pass threshold baked in — the holdout reports the numbers and
you judge them. What to look at first:

- **Realised net R and profit factor** (the headline; OPEN_AT_END floating
  PnL is shown separately and never summed in).
- **Win rate vs breakeven** (~22% Gold / ~29% GBP at these R targets —
  the annual ledgers showed 18.8% / 27.6%).
- **Expectancy $/trade and max drawdown** — a positive net R with a
  drawdown that would breach the $34/day loss cap repeatedly is not a
  tradeable system.
- **Trades filled** — if the screener fires on <1% of checkpoints the
  sample is too small to conclude anything; widen the period, do not
  loosen the rules.

## Exit codes

- `0` — holdout completed, outputs written.
- `2` — config error, tuning-period refusal, or frozen source files changed.
- `3` — data failure (no MT5 / no cache file / >10% checkpoints without bars).
