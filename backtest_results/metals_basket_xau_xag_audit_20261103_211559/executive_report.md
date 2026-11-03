# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261103_211559` | **Generated**: 2026-11-03 21:19:07 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **13** | All market open milestones evaluated |
| **Stand-Aside Directives** | **11 (84.6%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **2** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **0** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **2 (1W / 1L / 0BE)** | Executed with dynamic BE & target cap |
| **Win Rate on Fills** | **50.0%** | Won / Total Filled |
| **Gross Profit** | **+$30.77** | Cumulative winning trades |
| **Gross Loss** | **-$4.88** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+25.89** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **6.31** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Breakeven | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 2 | 2 | 1 | 1 | 0 | 50.0% | $+25.89 | 6.31 |
| **Silver (XAGUSD)** | 0 | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 0 | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **13** | **13** | 100% of candidate opportunities |
| **Filled Trades** | **2** | **8** | Filtered 11 questionable sessions |
| **Win / Loss Record** | **1 W / 1 L** | **1 W / 7 L** | Prevented 6 direct stop-outs |
| **Win Rate on Fills** | **50.0%** | **12.5%** | Council delta: +37.5% |
| **Gross Losses Incurred** | **-$10.89** | **-$40.61** | **Saved +$35.73 from bad entries** |
| **Gross Profits Captured** | **+$35.89** | **+$30.77** | Missed -$0.00 in passed winners |
| **Net Realized PnL** | **$+25.89** | **$-9.84** | **Net Council Value: +$35.73** |
| **Profit Factor** | **6.31** | **0.76** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-08-17 10:30 (London Open) | G:4397.73 S:65.534 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 2 | 2026-08-17 11:00 (London Post-Open) | G:4391.85 S:65.426 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 3 | 2026-08-17 15:30 (NY Open) | 4396.23 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range Low (4386.95) by $\ge 1.2\times$ M5 ATR and prints an M1/M5 Bullish MSS displacement candle close above 4398.00, THEN submit a [BUY LIMIT] at the newly formed Bullish FVG proximal edge targeting 4411.30 / 4449.73. |
| 4 | 2026-08-17 16:00 (NY Post-Open) | G:4396.53 S:65.528 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 5 | 2026-08-17 18:00 (NY Silver Bullet Mid) | G:4404.06 S:65.811 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 6 | 2026-08-18 10:30 (London Open) | 4390.71 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price reclaims 4394.34 with an energetic M5 bullish displacement candle following the Asian Low purge, THEN evaluate a Long entry targeting Asian High (4436.19). |
| 7 | 2026-08-18 11:00 (London Post-Open) | 4391.97 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic bullish M5 Market Structure Shift closing firmly above 4398.00 with displacement, THEN evaluate long entries at the newly formed bullish FVG targeting Asian High (4436.19). |
| 8 | 2026-08-18 15:30 (NY Open) | G:4392.29 S:65.006 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 9 | 2026-08-18 16:00 (NY Post-Open) | 4393.60 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Low (4386.07) by $\ge 1.2\times$ M5 ATR (~3.5 pts down to $\le 4382.50$) and prints an energetic M5 displacement MSS back above 4388.00, THEN route BUY LIMIT at proximal FVG edge targeting Asian High (4403.65). |
| 10 | 2026-08-18 17:30 (NY Silver Bullet Open) | 4393.92 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps London Range Low (4386.86) and prints an energetic M5 Bullish MSS displacement with an FVG close above 4395.00, THEN route a [BUY LIMIT] at the proximal FVG edge. |
| 11 | 2026-08-18 18:00 (NY Silver Bullet Mid) | 4389.47 | `SELL_LIMIT` | **LOSS** | $-4.88 | IF price retraces to tap `4391.79` within 75 minutes without taking out `4399.55`, THEN fill SELL LIMIT; execute 33% de-risking at 1:2.0 R:R (`4376.27`). |
| 12 | 2026-08-19 10:30 (London Open) | G:4353.73 S:63.002 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 13 | 2026-08-19 11:00 (London Post-Open) | G:4349.64 S:62.813 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 14 | 2026-08-19 15:30 (NY Open) | 4359.00 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement close breaking below `4351.08` with confirmed bearish SMT, THEN re-evaluate short limit orders at the newly formed discount FVG boundary. |
| 15 | 2026-08-19 16:00 (NY Post-Open) | 4356.48 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement candle closing below 4353.40 (confirming Bearish MSS with Silver SMT confirmation), THEN route a limit sell at the newly minted FVG proximal edge. |
| 16 | 2026-08-19 17:30 (NY Silver Bullet Open) | 4370.83 | `BUY_LIMIT` | **WIN** | $+30.77 | IF price pulls back to 4366.80 before 18:45 Tehran Time (75m TTL), THEN fill Buy Limit and enforce trailing ratchet at 1:2.5 R:R excursion. |
| 17 | 2026-08-19 18:00 (NY Silver Bullet Mid) | G:4369.33 S:63.558 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 18 | 2026-08-20 10:30 (London Open) | 4495.75 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Low at 4484.42 into London Open and delivers a bullish M5 displacement MSS closing with a verified FVG, THEN approve BUY LIMIT at the FVG proximal edge targeting PDH 4524.29. |
| 19 | 2026-08-20 11:00 (London Post-Open) | G:4488.23 S:66.847 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 20 | 2026-08-20 15:30 (NY Open) | 4490.75 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement close below 4487.00 confirming a bearish MSS, THEN evaluate limit entries at the newly formed FVG; OR IF price sweeps Asian Low (4477.91) with bullish SMT, prepare pro-trend BUY LIMIT. |
| 21 | 2026-08-20 16:00 (NY Post-Open) | G:4487.51 S:66.638 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 22 | 2026-08-20 18:00 (NY Silver Bullet Mid) | G:4484.89 S:66.672 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 23 | 2026-08-21 10:30 (London Open) | G:4538.62 S:68.946 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 24 | 2026-08-21 11:00 (London Post-Open) | G:4544.05 S:69.051 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 25 | 2026-08-21 15:30 (NY Open) | 4586.00 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back into the Bullish FVG and forms a refined M1/M5 internal micro-swing low with a valid invalidation anchor $\le 17.00$ points from entry, THEN recalculate risk parameters for a compliant long re-entry. |
| 26 | 2026-08-21 16:00 (NY Post-Open) | 4582.76 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an M5 body close below micro-structure (4571.68) creating a tight internal FVG with structural SL $\le$ 17.00 pts, THEN evaluate a secondary sell limit. |
| 27 | 2026-08-21 17:30 (NY Silver Bullet Open) | G:4593.84 S:69.619 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 28 | 2026-08-21 18:00 (NY Silver Bullet Mid) | G:4594.94 S:69.861 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*