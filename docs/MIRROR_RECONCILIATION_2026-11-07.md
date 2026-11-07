# Mirror Reconciliation — 2026-11-07 (TradingGuard Pack 6)

**Status:** reconciliation note. The Mirror itself (`docs/SYSTEM_EXECUTION_MIRROR.md`) was NOT edited; its numbers stand as published. This note states what each headline figure actually is, because they cannot be read as one system.

## The three irreconcilable headline figures

| Figure as published | Where | What it actually is | Source |
| :--- | :--- | :--- | :--- |
| **47 fills, +25.5R, PF 1.94** | Mirror §9.1 "Calibrated Profile 1"; §9.6 Autumn row | **Gold, Autumn only (Sep 1 – Nov 4, 2026), calibrated subset** — 47 fills after post-hoc bans (no Silver Bullet, no ARCH-002/009), target 3.5R / BE 1.8R. One season, one asset, filtered. | `backtest_results/gold_annual_4season_master_synthesis/annual_master_summary_metrics.json` → `seasonal_breakdown.Autumn` (calibrated). Underlying ledger: `gold_2month_quant_audit` autumn trades. |
| **137 fills, +17.0R, PF 1.19** | Mirror §9.6 "FULL-YEAR 2026" row | **Gold, full year 2026, calibrated subset** — 137 fills after the same post-hoc bans, across all four seasons. The unfiltered full-year ledger is 414 fills, **−54.0R, PF 0.81**. | Same JSON → `calibrated_annual` vs `baseline_annual`. |
| **149 fills, +116.5R, PF 2.97** | Mirror §14.2 "Combined Portfolio (Gold + Cable)" | **A different simulation entirely** — the Master Production Portfolio (`hitl/backtest/master_production_portfolio_audit.py`): different session set, different archetype set (incl. ARCH-012/013/014, which do not exist in the annual ledgers), different execution sim (15M trailing / snapback vs the annual audits' fixed-target sim). It shares **zero exact trades** (date + archetype + entry) with the annual ledgers. | `backtest_results/master_portfolio_audit/` |

These three numbers come from **different rule sets, different sessions, different simulators and different data**. They must not be added, averaged, or presented as successive refinements of one system. In particular, +116.5R is not the "production" version of +17.0R: the master portfolio's Gold standalone leg alone claims +103.0R on 89 fills, while the Gold annual ledger's best calibrated slice is +25.5R on 47 fills (Autumn) — and the same archetype, XAU ARCH-004, is +43.5R (13W/2L) in the master portfolio vs −2.5R (17W/62L) in the Gold annual ledger.

## Other figures in the Mirror that need the same care

- **§9.5 "6-MONTH COMBINED MASTER TOTAL" (+28.0R on 111 fills, PF 1.40)** is the sum of three calibrated seasonal slices (Winter −6.0R + Summer +8.5R + Autumn +25.5R), not a single run. The unfiltered baseline over the same span is −44.0R.
- **§9.6 archetype ranking mixes populations.** SETUP-ARCH-011 is listed at "128 Fills" inside a ranking of the 137-fill calibrated suite, but 128 is the annual **nested-double-MSS** fill count across all fills (40 Winter + 41 Spring + 47 Summer; the Autumn nested file is missing from the repo, so even 128 is partial). The five ranked archetypes sum to 261 fills — more than the 137-fill suite they purport to partition. The ranking is not a partition of the calibrated suite and should not be read as one.
- **"Net Alpha Advantage" (+71.0R full-year, +72.0R six-month)** is calibrated-minus-baseline (e.g. +17.0R − (−54.0R) = +71.0R). It measures how much the post-hoc bans improved the *same year's* numbers, not out-of-sample alpha: the bans were picked after seeing that year.
- **GBP §10.2 full-year** (not in the table above): calibrated 123 fills +17.0R PF 1.25 vs unfiltered 255 fills −7.0R PF 0.95. Same post-hoc caveat as Gold.
- **Pooled council ledgers** (38 council audit files): closed-trade net **+$38.83** (35W/63L on 98 closed fills); the reports' headline nets sum to **+$127.48** because 12 still-open (`OPEN_AT_END`) trades' floating PnL was counted as realised. See the `CORRECTION.md` files in each of the 9 affected run directories (Pack 6).

## What would reconcile these

A single defined universe and denominator: one rule set, frozen before the test period; one simulator (the canonical `evaluator.py`); one ledger with realised/unrealised split; and a genuinely held-out test period. That is Pack 7 (true holdout test). Until then, each figure above should be quoted only with its population attached.
