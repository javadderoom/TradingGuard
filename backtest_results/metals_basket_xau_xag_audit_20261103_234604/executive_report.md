# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261103_234604` | **Generated**: 2026-11-03 23:46:57 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **3** | All market open milestones evaluated |
| **Stand-Aside Directives** | **2 (66.7%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **1** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **1** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **0 (0W / 0L / 0BE)** | Executed with dynamic BE & target cap |
| **Win Rate on Fills** | **0.0%** | Won / Total Filled |
| **Gross Profit** | **+$0.00** | Cumulative winning trades |
| **Gross Loss** | **-$0.00** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+0.00** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **0.00** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Breakeven | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 1 | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Silver (XAGUSD)** | 0 | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 1 | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **3** | **3** | 100% of candidate opportunities |
| **Filled Trades** | **0** | **2** | Filtered 2 questionable sessions |
| **Win / Loss Record** | **0 W / 0 L** | **1 W / 1 L** | Prevented 1 direct stop-outs |
| **Win Rate on Fills** | **0.0%** | **50.0%** | Council delta: -50.0% |
| **Gross Losses Incurred** | **-$0.00** | **-$5.50** | **Saved +$5.50 from bad entries** |
| **Gross Profits Captured** | **+$0.00** | **+$13.75** | Missed -$13.75 in passed winners |
| **Net Realized PnL** | **$+0.00** | **$+8.25** | **Net Council Value: -$8.25** |
| **Profit Factor** | **0.00** | **2.50** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-07-27 10:30 (London Open) | G:4091.22 S:59.246 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 2 | 2026-07-27 11:00 (London Post-Open) | G:4090.57 S:59.276 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 3 | 2026-07-27 15:30 (NY Open) | G:4096.08 S:59.419 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 4 | 2026-07-27 16:00 (NY Post-Open) | 4091.77 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4105.98) by $\ge 1.50$ pts with Bearish SMT vs XAGUSD and prints an M5 MSS displacement close back into range, THEN compile a Tier-1 SELL LIMIT at the proximal FVG edge. |
| 5 | 2026-07-27 17:30 (NY Silver Bullet Open) | 4097.57 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M5 candle closes decisively below 4096.00 with displacement into range value, THEN post a SELL LIMIT at the newly formed M5 FVG proximal edge targeting 4082.00. |
| 6 | 2026-07-27 18:00 (NY Silver Bullet Mid) | 4097.66 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price retraces to `4101.55` before tapping `4087.07`, THEN execute short limit order; IF filled, step to BE at $\ge 1:2.50\text{ R:R}$. |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*