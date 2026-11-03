# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261102_234917` | **Generated**: 2026-11-02 23:54:58 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **24** | All market open milestones evaluated |
| **Stand-Aside Directives** | **17 (70.8%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **7** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **0** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **7** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **28.6%** | Won / Total Filled |
| **Gross Profit** | **+$21.53** | Cumulative winning trades |
| **Gross Loss** | **-$56.55** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$-35.02** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **0.38** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 4 | 4 | 1 | 3 | 25.0% | $-10.02 | 0.68 |
| **Silver (XAGUSD)** | 3 | 3 | 1 | 2 | 33.3% | $-25.00 | 0.02 |
| **Intermarket SMT Setups** | 4 | 4 | 0 | 4 | 0.0% | $-40.05 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **24** | **24** | 100% of candidate opportunities |
| **Filled Trades** | **7** | **21** | Filtered 17 questionable sessions |
| **Win / Loss Record** | **2 W / 5 L** | **2 W / 19 L** | Prevented 14 direct stop-outs |
| **Win Rate on Fills** | **28.6%** | **9.5%** | Council delta: +19.1% |
| **Gross Losses Incurred** | **-$65.02** | **-$177.60** | **Saved +$121.05 from bad entries** |
| **Gross Profits Captured** | **+$14.98** | **+$21.53** | Missed -$0.00 in passed winners |
| **Net Realized PnL** | **$-35.02** | **$-156.07** | **Net Council Value: +$121.05** |
| **Profit Factor** | **0.38** | **0.12** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-09-21 10:00 (London Pre-Open) | 4365.34 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4383.30) into London Open and prints a bearish M1/M5 displacement MSS body close below 4375.00, THEN stage a SELL LIMIT at the resulting Bearish FVG proximal edge. |
| 2 | 2026-09-21 10:30 (London Open) | 4358.00 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 body close above `4364.08`, THEN issue BUY LIMIT at `4364.08` with SL at `4357.71` targeting PDH `4399.58` (R:R > 1:5.0). |
| 3 | 2026-09-21 11:00 (London Post-Open) | 4361.47 | `BUY_LIMIT` | **LOSS** | $-5.21 | IF price retraces to test `4361.06` before breaking 4368.00, THEN order fills and activates target run to 4383.30. |
| 4 | 2026-09-21 11:00 (London Post-Open) | 66.414 | `BUY_LIMIT` | **LOSS** | $-9.00 | IF price pierces below `66.270` without tagging `66.349`, THEN cancel pending limit and re-evaluate for deeper breaker block retest at `66.180`. |
| 5 | 2026-09-21 15:00 (NY Pre-Open) | G:4354.88 S:66.227 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 6 | 2026-09-21 15:30 (NY Open) | 4350.19 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4365.22) or taps Breaker Block [4360.82–4365.22] during NY session and prints an M5 displacement MSS with SL >= 5.28 pts, THEN issue [SELL LIMIT] targeting External SSL (4235.17). |
| 7 | 2026-09-21 15:30 (NY Open) | 66.117 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High `66.451` into the Breaker Block `[66.34 - 66.45]` and prints an energetic M1/M5 bearish displacement MSS, THEN issue SELL LIMIT at the resulting proximal FVG edge. |
| 8 | 2026-09-21 16:00 (NY Post-Open) | 4342.20 | `SELL_LIMIT` | **LOSS** | $-11.11 | IF price retraces to fill `4346.52` during the active NY session without exceeding `4357.63`, THEN the limit order engages for pro-trend delivery toward `4218.30`. |
| 9 | 2026-09-21 16:00 (NY Post-Open) | 66.031 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (66.451) and prints an energetic M5 Bearish MSS back below 66.30 with displacement, THEN re-evaluate for SELL LIMIT at proximal FVG. |
| 10 | 2026-09-21 17:30 (NY Silver Bullet Open) | 65.855 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back to the OTE/Breaker zone at 66.14–66.23 and prints a localized M1 bearish displacement rejection, THEN re-evaluate with a compressed <= 0.25 pt stop. |
| 11 | 2026-09-21 18:00 (NY Silver Bullet Mid) | 66.264 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M1/M5 displacement body closes firmly below the 66.06 micro-pivot, THEN queue a SELL LIMIT at the resulting Bearish FVG proximal edge targeting 63.35 (SSL). |
| 12 | 2026-09-22 10:00 (London Pre-Open) | 4346.90 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4376.03) or PDH (4383.30) and produces an energetic M1/M5 bearish displacement MSS below 4362.00, THEN anchor a SELL LIMIT at the proximal edge of the resulting Bearish FVG. |
| 13 | 2026-09-22 10:30 (London Open) | 4336.77 | `SELL_LIMIT` | **WIN** | $+21.03 | IF price retraces into the Bearish FVG Proximal Edge at `4343.72`, THEN execute the Sell Limit targeting External Structural Liquidity at `4215.60`. |
| 14 | 2026-09-22 10:30 (London Open) | 65.909 | `SELL_LIMIT` | **WIN** | $+0.50 | IF price pulls back to test `66.038` within the London open session, THEN execute the pending SELL LIMIT for external structural continuation. |
| 15 | 2026-09-22 15:00 (NY Pre-Open) | 4297.22 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price retraces into the FVG (4303.82–4309.20) and forms a tighter sub-interval micro-MSS allowing an SL distance under 17.00 points (ideally <= 2.00 pts), THEN evaluate a calibrated SELL LIMIT. |
| 16 | 2026-09-22 15:00 (NY Pre-Open) | 64.673 | `SELL_LIMIT` | **LOSS** | $-16.50 | IF price pulls back to tap `64.76` while remaining below `65.33`, THEN execute pro-trend sell limit targeting `62.30`. |
| 17 | 2026-09-22 15:30 (NY Open) | 4318.06 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price rallies into Premium OTE/FVG resistance (4332.65–4335.92) and prints an M1/M5 Bearish MSS with stop distance <= 17.00 points, THEN evaluate SELL LIMIT targeting 4196.89. |
| 18 | 2026-09-22 17:30 (NY Silver Bullet Open) | 4318.92 | `SELL_LIMIT` | **LOSS** | $-14.73 | IF price pulls back into 4323.33 without breaching 4338.06, THEN execute limit short targeting external structural liquidity at 4197.75. |
| 19 | 2026-09-23 10:00 (London Pre-Open) | 4339.05 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF London session expands to sweep Asian High (4369.26) or Asian Low (4333.20) followed by a confirmed M5 displacement MSS closing back inside the range, THEN anchor pending limit orders per [RULE-CORE-005]. |
| 20 | 2026-09-23 10:00 (London Pre-Open) | 66.511 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF London open drives price upward to sweep Asian High (67.507) / PDH (67.532) and produces an M1/M5 bearish displacement MSS close below the micro-swing low, THEN prepare a `SELL LIMIT` at the proximal edge of the resulting bearish FVG. |
| 21 | 2026-09-23 10:30 (London Open) | 4344.51 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4369.26) or PDH (4376.03) and prints an M5 bearish displacement MSS with Intermarket SMT divergence against XAGUSD, THEN prepare [SELL LIMIT] at the newly formed Bearish FVG proximal edge. |
| 22 | 2026-09-23 11:00 (London Post-Open) | 4345.37 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4369.26) / OTE Premium (4358.62) followed by a confirmed 5M/M1 bearish displacement MSS body close, THEN evaluate a pending SELL LIMIT at the resulting proximal FVG edge. |
| 23 | 2026-09-23 11:00 (London Post-Open) | 66.689 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (67.507) or PDH (67.532) and prints an energetic M5/M1 Bearish MSS displacement close below 66.60, THEN evaluate a SELL LIMIT at the proximal FVG edge. |
| 24 | 2026-09-23 15:00 (NY Pre-Open) | 4318.56 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF a clear M1/M5 displacement MSS forms with a verified body close below 4316.46, THEN anchor a SELL LIMIT at the newly formed M5 FVG Proximal Edge targeting External Structural Swing Low at 4235.17. |
| 25 | 2026-09-23 15:00 (NY Pre-Open) | 65.383 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price retraces into the premium discount zone (66.588–66.609) and prints an energetic M1/M5 bearish displacement MSS with a fresh FVG, THEN issue a SELL LIMIT at the FVG proximal edge. |
| 26 | 2026-09-23 17:30 (NY Silver Bullet Open) | G:4314.84 S:65.167 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 27 | 2026-09-25 10:00 (London Pre-Open) | G:4276.57 S:63.779 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*