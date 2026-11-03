# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261103_234729` | **Generated**: 2026-11-03 23:49:52 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **8** | All market open milestones evaluated |
| **Stand-Aside Directives** | **4 (50.0%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **4** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **0** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **3 (0W / 2L / 1BE)** | Executed with dynamic BE & target cap |
| **Win Rate on Fills** | **0.0%** | Won / Total Filled |
| **Gross Profit** | **+$8.89** | Cumulative winning trades |
| **Gross Loss** | **-$8.28** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+0.61** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **1.07** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Breakeven | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 4 | 3 | 0 | 2 | 1 | 0.0% | $+0.61 | 1.07 |
| **Silver (XAGUSD)** | 0 | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 1 | 1 | 0 | 1 | 0 | 0.0% | $-2.40 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **8** | **8** | 100% of candidate opportunities |
| **Filled Trades** | **2** | **6** | Filtered 4 questionable sessions |
| **Win / Loss Record** | **0 W / 2 L** | **0 W / 6 L** | Prevented 4 direct stop-outs |
| **Win Rate on Fills** | **0.0%** | **0.0%** | Council delta: +0.0% |
| **Gross Losses Incurred** | **-$0.61** | **-$34.46** | **Saved +$26.18 from bad entries** |
| **Gross Profits Captured** | **+$20.61** | **+$0.00** | Missed -$0.00 in passed winners |
| **Net Realized PnL** | **$+0.61** | **$-34.46** | **Net Council Value: +$26.18** |
| **Profit Factor** | **0.00** | **0.00** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-07-27 10:30 (London Open) | G:4091.22 S:59.246 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 2 | 2026-07-27 11:00 (London Post-Open) | G:4090.57 S:59.276 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 3 | 2026-07-27 15:30 (NY Open) | G:4096.08 S:59.419 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 4 | 2026-07-27 16:00 (NY Post-Open) | 4091.77 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4105.98) or NY AM High by >= 1.50 pts and forms an M5 displacement MSS closing back inside range with bearish FVG, THEN evaluate a high-conviction pro-macro SELL LIMIT. |
| 5 | 2026-07-27 17:30 (NY Silver Bullet Open) | 4097.57 | `SELL_LIMIT` | **LOSS** | $-2.40 | IF price taps `4100.36` before 18:30 UTC, THEN execute 0.01 lot SELL LIMIT; step to Breakeven at 1:2.5R per RULE-MGMT-034. |
| 6 | 2026-07-28 10:30 (London Open) | G:4047.79 S:57.342 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 7 | 2026-07-28 11:00 (London Post-Open) | G:4046.63 S:57.279 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 8 | 2026-07-28 15:30 (NY Open) | G:4042.93 S:57.516 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 9 | 2026-07-28 16:00 (NY Post-Open) | G:4037.83 S:57.410 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 10 | 2026-07-28 17:30 (NY Silver Bullet Open) | 4026.52 | `BUY_LIMIT` | **BREAKEVEN** | $0.00 | IF price pulls back to tap the proximal FVG edge at 4023.74, THEN the Buy Limit fills with immediate breakeven ratchet scheduled at $\ge 1:2.5$ R:R. |
| 11 | 2026-07-28 18:00 (NY Silver Bullet Mid) | G:4027.20 S:57.288 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 12 | 2026-07-29 10:30 (London Open) | G:4022.51 S:57.361 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 13 | 2026-07-29 11:00 (London Post-Open) | 4026.66 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price delivers a Judas purge sweeping Asian Low (4010.28) into discount with an energetic M5 displacement close and Bullish FVG creation, THEN route BUY LIMIT at the proximal FVG edge. |
| 14 | 2026-07-29 15:30 (NY Open) | G:4037.21 S:57.864 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 15 | 2026-07-29 16:00 (NY Post-Open) | G:4033.89 S:57.844 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 16 | 2026-07-29 17:30 (NY Silver Bullet Open) | G:4027.96 S:57.479 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 17 | 2026-07-29 18:00 (NY Silver Bullet Mid) | 4031.76 | `BUY_LIMIT` | **LOSS** | $-5.88 | IF price pulls back to tap 4031.44–4031.88 before taking out 4035.00, THEN order fills and activates runner targeting 4059.20. |
| 18 | 2026-07-30 10:30 (London Open) | G:4056.65 S:57.508 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 19 | 2026-07-30 11:00 (London Post-Open) | 4051.69 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF Gold prints a clean run below Asian Low (4050.72) by $\ge 1.0\times\text{M5 ATR}$ followed by an energetic M5 MSS displacement close back above 4054.00, THEN calibrate Buy Limit at the newly formed proximal FVG. |
| 20 | 2026-07-30 15:30 (NY Open) | 4066.39 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement candle body closing back inside the session boundary below 4057.00 with a confirmed bearish MSS, THEN stage a SELL LIMIT at the newly formed proximal M5 FVG. |
| 21 | 2026-07-30 16:00 (NY Post-Open) | G:4066.22 S:57.796 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 22 | 2026-07-30 17:30 (NY Silver Bullet Open) | G:4078.92 S:58.011 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 23 | 2026-07-30 18:00 (NY Silver Bullet Mid) | G:4077.21 S:58.020 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 24 | 2026-07-31 10:30 (London Open) | G:4074.64 S:58.378 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 25 | 2026-07-31 11:00 (London Post-Open) | G:4079.85 S:58.518 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 26 | 2026-07-31 15:30 (NY Open) | G:4060.55 S:58.034 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 27 | 2026-07-31 16:00 (NY Post-Open) | 4051.14 | `SELL_LIMIT` | **OPEN_AT_END** | $0.00 | IF price pulls back to 4053.27 without first violating 4056.77, THEN execute SELL LIMIT targeting 4028.43. |
| 28 | 2026-07-31 17:30 (NY Silver Bullet Open) | G:4055.54 S:57.814 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*