# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261103_150513` | **Generated**: 2026-11-03 15:10:03 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **10** | All market open milestones evaluated |
| **Stand-Aside Directives** | **2 (20.0%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **8** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **3** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **4** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **50.0%** | Won / Total Filled |
| **Gross Profit** | **+$107.26** | Cumulative winning trades |
| **Gross Loss** | **-$12.77** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+94.49** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **8.40** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 8 | 4 | 2 | 2 | 50.0% | $+94.49 | 8.40 |
| **Silver (XAGUSD)** | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 3 | 2 | 2 | 0 | 100.0% | $+107.17 | 99.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **10** | **10** | 100% of candidate opportunities |
| **Filled Trades** | **4** | **6** | Filtered 2 questionable sessions |
| **Win / Loss Record** | **2 W / 2 L** | **2 W / 4 L** | Prevented 2 direct stop-outs |
| **Win Rate on Fills** | **50.0%** | **33.3%** | Council delta: +16.7% |
| **Gross Losses Incurred** | **-$64.49** | **-$30.55** | **Saved +$17.78 from bad entries** |
| **Gross Profits Captured** | **+$114.49** | **+$107.17** | Missed -$0.00 in passed winners |
| **Net Realized PnL** | **$+94.49** | **$+76.62** | **Net Council Value: +$17.78** |
| **Profit Factor** | **8.39** | **3.51** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-09-07 10:00 (London Pre-Open) | G:4407.94 S:65.878 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 2 | 2026-09-07 10:30 (London Open) | G:4401.61 S:65.759 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 3 | 2026-09-07 11:00 (London Post-Open) | G:4398.04 S:65.644 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 4 | 2026-09-07 15:00 (NY Pre-Open) | 4421.14 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement MSS breaking below 4414.00 to confirm SMT distribution, THEN evaluate short limit orders at the resulting bearish FVG. |
| 5 | 2026-09-07 15:30 (NY Open) | 4412.20 | `SELL_LIMIT` | **OPEN_AT_END** | $0.00 | IF price pulls back into 4411.61 before breaking below 4402.57, THEN fill pending SELL LIMIT. |
| 6 | 2026-09-07 16:00 (NY Post-Open) | G:4405.84 S:65.780 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 7 | 2026-09-08 10:00 (London Pre-Open) | G:4431.77 S:66.888 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 8 | 2026-09-08 10:30 (London Open) | G:4441.57 S:67.098 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 9 | 2026-09-08 11:00 (London Post-Open) | 4433.68 | `SELL_LIMIT` | **WIN** | $+52.91 | IF price pulls back to tap 4434.04 before taking out the session sweep extreme, THEN execute SELL LIMIT targeting 4381.13; trail stops per [RULE-MGMT-022] at $\ge 1:3.0$ R:R. |
| 10 | 2026-09-08 15:00 (NY Pre-Open) | 4398.31 | `BUY_LIMIT` | **LOSS** | $-5.27 | IF limit fills at 4394.25 and excursion achieves $\ge 1:2.50$ R:R with M5 close beyond 4398.50, THEN advance stop to breakeven per [RULE-MGMT-028]. |
| 11 | 2026-09-08 15:30 (NY Open) | G:4395.89 S:65.903 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 12 | 2026-09-08 16:00 (NY Post-Open) | G:4395.75 S:65.916 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 13 | 2026-09-09 10:00 (London Pre-Open) | G:4376.47 S:66.237 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 14 | 2026-09-09 10:30 (London Open) | G:4374.65 S:66.195 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 15 | 2026-09-09 11:00 (London Post-Open) | G:4378.67 S:66.208 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 16 | 2026-09-09 15:30 (NY Open) | G:4400.94 S:66.645 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 17 | 2026-09-09 16:00 (NY Post-Open) | G:4397.97 S:66.532 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 18 | 2026-09-09 17:30 (NY Silver Bullet Open) | 4403.54 | `BUY_LIMIT` | **EXPIRED** | $0.00 | IF price retraces to fill `4396.14` before breaching 4412.70, THEN execute Buy Limit to target 4442.94. |
| 19 | 2026-09-10 10:00 (London Pre-Open) | 4411.34 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price retraces to fill the Breaker Block at `4416.83` before 11:30 Tehran time, THEN execute Sell Limit with TP1 at `4389.79`. |
| 20 | 2026-09-10 10:30 (London Open) | G:4412.92 S:67.464 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 21 | 2026-09-10 11:00 (London Post-Open) | G:4411.01 S:67.481 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 22 | 2026-09-10 15:00 (NY Pre-Open) | 4399.92 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price pulls back to tap `4408.99` prior to any fresh breakdown below `4395.00`, THEN fill SELL LIMIT for target expansion toward `4282.52`. |
| 23 | 2026-09-10 15:30 (NY Open) | G:4395.62 S:66.767 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 24 | 2026-09-10 16:00 (NY Post-Open) | G:4392.00 S:66.639 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 25 | 2026-09-10 17:30 (NY Silver Bullet Open) | G:4383.81 S:65.789 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 26 | 2026-09-11 10:00 (London Pre-Open) | 4308.64 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range Low at 4304.16 and prints a bullish M1/M5 displacement MSS closing back above 4310.00, THEN evaluate Long Limit orders targeting Asian High (4340.34). |
| 27 | 2026-09-11 10:30 (London Open) | G:4308.71 S:63.126 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 28 | 2026-09-11 11:00 (London Post-Open) | 4326.70 | `BUY_LIMIT` | **LOSS** | $-7.50 | IF price pulls back to tap 4325.89 without breaking below 4319.50, THEN fill order and monitor displacement toward 4340.34 and 4350.34. |
| 29 | 2026-09-11 15:00 (NY Pre-Open) | 4352.70 | `SELL_LIMIT` | **WIN** | $+54.26 | IF price retraces to tap `4343.10` before 17:00 UTC, THEN execute the pending short toward `4300.71`. |
| 30 | 2026-09-11 16:00 (NY Post-Open) | G:4342.26 S:63.956 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*