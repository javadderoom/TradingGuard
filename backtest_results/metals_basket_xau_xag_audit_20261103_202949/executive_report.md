# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261103_202949` | **Generated**: 2026-11-03 20:33:43 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **15** | All market open milestones evaluated |
| **Stand-Aside Directives** | **8 (53.3%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **7** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **1** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **6** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **0.0%** | Won / Total Filled |
| **Gross Profit** | **+$0.00** | Cumulative winning trades |
| **Gross Loss** | **-$36.74** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$-36.74** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **0.00** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 7 | 6 | 0 | 6 | 0.0% | $-36.74 | 0.00 |
| **Silver (XAGUSD)** | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 4 | 3 | 0 | 3 | 0.0% | $-17.11 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **15** | **15** | 100% of candidate opportunities |
| **Filled Trades** | **6** | **14** | Filtered 8 questionable sessions |
| **Win / Loss Record** | **0 W / 6 L** | **2 W / 12 L** | Prevented 6 direct stop-outs |
| **Win Rate on Fills** | **0.0%** | **14.3%** | Council delta: -14.3% |
| **Gross Losses Incurred** | **-$36.74** | **-$80.89** | **Saved +$44.15 from bad entries** |
| **Gross Profits Captured** | **+$23.26** | **+$73.71** | Missed -$73.71 in passed winners |
| **Net Realized PnL** | **$-36.74** | **$-7.18** | **Net Council Value: -$29.56** |
| **Profit Factor** | **0.00** | **0.91** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-08-31 10:00 (London Pre-Open) | 4423.53 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4472.05) or PDL retest and prints an M5 bearish displacement body close with Bearish Metals SMT, THEN seek short execution targeting 4292.95. |
| 2 | 2026-08-31 10:30 (London Open) | G:4418.53 S:66.125 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 3 | 2026-08-31 11:00 (London Post-Open) | G:4416.43 S:66.195 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 4 | 2026-08-31 15:00 (NY Pre-Open) | 4435.92 | `SELL_LIMIT` | **LOSS** | $-9.08 | IF price retraces to fill the proximal edge at `4440.38`, THEN execute Sell Limit targeting HTF pool `4305.35`. |
| 5 | 2026-08-31 15:30 (NY Open) | G:4438.83 S:67.008 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 6 | 2026-08-31 18:00 (NY Silver Bullet Mid) | G:4458.57 S:67.292 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 7 | 2026-09-01 10:00 (London Pre-Open) | 4436.36 | `BUY_LIMIT` | **LOSS** | $-8.28 | IF price pulls back to tap `4438.62` prior to taking out PDH, THEN fill order and advance SL to Breakeven upon achieving 1:2.50 R:R excursion per [RULE-MGMT-029]. |
| 8 | 2026-09-01 10:30 (London Open) | G:4436.92 S:66.724 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 9 | 2026-09-01 11:00 (London Post-Open) | G:4430.03 S:66.466 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 10 | 2026-09-01 15:00 (NY Pre-Open) | 4374.60 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back to the Bearish FVG at `4383.74` and prints a fresh M1/M5 bearish rejection wick with a tight swing high <= 6.50 pts ($6.50 risk), THEN route [SELL LIMIT] targeting External SSL at `4238.71`. |
| 11 | 2026-09-01 15:30 (NY Open) | G:4374.10 S:64.743 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 12 | 2026-09-01 16:00 (NY Post-Open) | G:4370.82 S:64.718 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 13 | 2026-09-01 17:30 (NY Silver Bullet Open) | G:4380.20 S:64.821 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 14 | 2026-09-01 18:00 (NY Silver Bullet Mid) | 4380.48 | `SELL_LIMIT` | **LOSS** | $-4.41 | IF price fails to fill limit and breaches below 4374.00, THEN cancel pending order and await fresh M5 pullback into newly established FVG. |
| 15 | 2026-09-02 10:00 (London Pre-Open) | 4285.10 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an M5 displacement body close above 4296.92 validating the Bullish SMT Judas Purge, THEN execute BUY LIMIT at the newly formed Bullish FVG proximal edge targeting 4335.50 / 4421.80 with SL pinned at 4283.95 (Risk <= $17). |
| 16 | 2026-09-02 10:30 (London Open) | 4303.85 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back deeper into FVG distal edge/Breaker zone (`4288.62 - 4292.00`) printing a fresh M1 micro-MSS with structural SL $\le$ 17.00 pts, THEN route [BUY LIMIT] targeting `4440.55`. |
| 17 | 2026-09-02 11:00 (London Post-Open) | G:4305.34 S:63.692 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 18 | 2026-09-02 15:00 (NY Pre-Open) | 4321.67 | `SELL_LIMIT` | **LOSS** | $-6.51 | IF price retraces to 4325.05 during the active NY session window, THEN limit order fills for pro-trend distribution toward external liquidity pools. |
| 19 | 2026-09-02 15:30 (NY Open) | G:4315.83 S:63.875 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 20 | 2026-09-02 16:00 (NY Post-Open) | G:4309.83 S:63.655 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 21 | 2026-09-02 17:30 (NY Silver Bullet Open) | G:4312.68 S:63.827 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 22 | 2026-09-03 10:00 (London Pre-Open) | 4431.66 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range Low at `4381.02` with an energetic M5 MSS and FVG during early London, THEN evaluate a Long Limit anchored at the proximal discount edge. |
| 23 | 2026-09-03 10:30 (London Open) | G:4427.09 S:65.990 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 24 | 2026-09-03 11:00 (London Post-Open) | 4437.08 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back to sweep the internal Asian liquidity pool below 4390.00 followed by an M5 bullish displacement MSS, THEN authorize a BUY LIMIT at the newly formed proximal FVG. |
| 25 | 2026-09-03 15:00 (NY Pre-Open) | 4438.99 | `SELL_LIMIT` | **LOSS** | $-2.32 | IF limit fills at `4440.16`, THEN monitor M5 candle closes; per [RULE-MGMT-029], once favorable excursion reaches $\ge 1:2.50\text{ R:R}$ (+8.68 pts to 4431.48), lock SL to Breakeven (+ spread buffer). |
| 26 | 2026-09-03 15:30 (NY Open) | G:4437.18 S:65.933 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 27 | 2026-09-03 16:00 (NY Post-Open) | G:4437.03 S:65.797 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 28 | 2026-09-04 10:00 (London Pre-Open) | 4474.75 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Low at 4466.82 by $\ge 1.2\times$ M5 ATR (down to $\le 4461.50$) and prints an energetic M1/M5 bullish displacement close breaking minor swing structure, THEN re-engage for [BUY LIMIT] targeting external BSL at 4621.06. |
| 29 | 2026-09-04 10:30 (London Open) | 4468.85 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price reclaims and prints an M5 body close above `4472.52` (Bearish FVG distal edge) creating a confirmed Bullish MSS + FVG, THEN evaluate a Long Limit anchored at the new discount proximal edge. |
| 30 | 2026-09-04 11:00 (London Post-Open) | 4472.25 | `BUY_LIMIT` | **LOSS** | $-6.14 | IF price fails to fill limit and expands past 4487.33, THEN cancel pending limit and await fresh NY session FVG pullback. |
| 31 | 2026-09-04 15:00 (NY Pre-Open) | G:4480.66 S:67.120 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 32 | 2026-09-04 15:30 (NY Open) | 4478.26 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price retraces into `4477.33` prior to taking out `4460.19`, THEN order fills; bank 50% partial at 1:3.0 R:R and trail remaining runner behind M5 swing highs. |
| 33 | 2026-09-04 17:30 (NY Silver Bullet Open) | G:4471.92 S:66.833 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 34 | 2026-09-04 18:00 (NY Silver Bullet Mid) | G:4465.92 S:66.732 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*