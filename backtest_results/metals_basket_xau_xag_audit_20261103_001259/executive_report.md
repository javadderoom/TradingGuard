# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261103_001259` | **Generated**: 2026-11-03 00:17:51 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **21** | All market open milestones evaluated |
| **Stand-Aside Directives** | **18 (85.7%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **3** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **0** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **3** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **33.3%** | Won / Total Filled |
| **Gross Profit** | **+$21.03** | Cumulative winning trades |
| **Gross Loss** | **-$12.53** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+8.50** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **1.68** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 3 | 3 | 1 | 2 | 33.3% | $+8.50 | 1.68 |
| **Silver (XAGUSD)** | 0 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 2 | 2 | 0 | 2 | 0.0% | $-12.53 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **21** | **21** | 100% of candidate opportunities |
| **Filled Trades** | **3** | **20** | Filtered 18 questionable sessions |
| **Win / Loss Record** | **1 W / 2 L** | **6 W / 14 L** | Prevented 12 direct stop-outs |
| **Win Rate on Fills** | **33.3%** | **30.0%** | Council delta: +3.3% |
| **Gross Losses Incurred** | **-$6.50** | **-$101.33** | **Saved +$88.80 from bad entries** |
| **Gross Profits Captured** | **+$28.50** | **+$84.42** | Missed -$63.39 in passed winners |
| **Net Realized PnL** | **$+8.50** | **$-16.91** | **Net Council Value: +$25.41** |
| **Profit Factor** | **1.68** | **0.83** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-09-21 10:00 (London Pre-Open) | 4365.34 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4383.30) during London open and prints an M1/M5 bearish displacement MSS close below the swing pivot, THEN prepare a `SELL LIMIT` at the proximal FVG edge targeting SSL at 4235.17. |
| 2 | 2026-09-21 10:30 (London Open) | G:4358.00 S:66.136 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 3 | 2026-09-21 11:00 (London Post-Open) | 4361.47 | `BUY_LIMIT` | **LOSS** | $-5.21 | IF price pulls back to fill 4361.06 without violating 4355.85, THEN execute long runner targeting Asian High (4383.30) and external BSL (4402.44). |
| 4 | 2026-09-21 15:00 (NY Pre-Open) | G:4354.88 S:66.227 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 5 | 2026-09-21 15:30 (NY Open) | G:4350.19 S:66.117 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 6 | 2026-09-21 16:00 (NY Post-Open) | 4342.20 | `SELL_LIMIT` | **LOSS** | $-7.32 | IF price retraces to touch `4346.52` during the active NY Killzone, THEN order fills with invalidation strictly anchored at `4357.63`. |
| 7 | 2026-09-22 10:00 (London Pre-Open) | G:4346.90 S:66.105 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 8 | 2026-09-22 10:30 (London Open) | 4336.77 | `SELL_LIMIT` | **WIN** | $+21.03 | IF price retraces into the Bearish FVG proximal boundary at `4343.72` prior to 17:00 UTC, THEN execute 0.01 lot short. |
| 9 | 2026-09-22 15:00 (NY Pre-Open) | G:4297.22 S:64.673 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 10 | 2026-09-22 15:30 (NY Open) | 4318.06 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price expands into Premium OTE (`4332.65`–`4339.18`) or sweeps PDH (`4383.30`) with a confirmed M1/M5 Bearish MSS, THEN evaluate a SELL LIMIT targeting SSL `4235.17` with SL $\le$ 17.00 pts. |
| 11 | 2026-09-22 16:00 (NY Post-Open) | G:4314.38 S:65.250 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 12 | 2026-09-22 17:30 (NY Silver Bullet Open) | 4318.92 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price compresses and prints an intraday low-risk Bearish M1 FVG with SL distance $\le$ 2.00 points during active killzones, THEN reassess for SELL LIMIT entry. |
| 13 | 2026-09-22 18:00 (NY Silver Bullet Mid) | 4313.96 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 displacement body close breaking 4310.00 with a compressed sub-1.70 pt FVG invalidation, THEN re-evaluate a Sell Limit. |
| 14 | 2026-09-23 10:00 (London Pre-Open) | 4339.05 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF London/NY Open sweeps Asian High (4369.26) and prints an energetic M1/M5 bearish displacement MSS close breaking internal support, THEN queue a [SELL LIMIT] at the displacement FVG proximal edge targeting PDL (4291.52) / External SSL (4235.17). |
| 15 | 2026-09-23 10:30 (London Open) | G:4344.51 S:66.618 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 16 | 2026-09-23 11:00 (London Post-Open) | G:4345.37 S:66.689 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 17 | 2026-09-23 15:00 (NY Pre-Open) | G:4318.56 S:65.383 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 18 | 2026-09-23 15:30 (NY Open) | 4318.04 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement candle closing above 4321.60 with a valid bullish FVG, THEN evaluate a BUY LIMIT at the FVG proximal edge targeting 4347.20. |
| 19 | 2026-09-23 16:00 (NY Post-Open) | G:4313.87 S:65.367 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 20 | 2026-09-23 17:30 (NY Silver Bullet Open) | G:4314.84 S:65.167 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 21 | 2026-09-23 18:00 (NY Silver Bullet Mid) | 4302.14 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price retraces into the Bearish FVG at 4308.67 and forms a local sub-2.0 pt M1 displacement MSS with tight sweep invalidation, THEN evaluate micro-scaled short execution. |
| 22 | 2026-09-24 10:00 (London Pre-Open) | 4284.46 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4303.58) or PDH (4369.26) followed by an energetic M1/M5 Bearish MSS close, THEN issue a [SELL LIMIT] at the displacement FVG proximal boundary. |
| 23 | 2026-09-24 10:30 (London Open) | 4284.09 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4303.58) or PDL (4274.81) and prints an energetic M1/M5 MSS body close back in trend direction, THEN stage a limit order at the displacement FVG proximal boundary. |
| 24 | 2026-09-24 11:00 (London Post-Open) | 4288.75 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4303.58) or PDH (4369.26) and delivers an energetic M1/M5 bearish displacement MSS close, THEN prepare a SELL LIMIT order at the Bearish FVG proximal edge. |
| 25 | 2026-09-24 15:00 (NY Pre-Open) | G:4267.39 S:63.691 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 26 | 2026-09-24 15:30 (NY Open) | 4259.38 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price retraces into the [4263.38 - 4266.82] Bearish FVG AND prints a localized M1 micro-MSS with an invalidation anchor $\le$ 2.00 points, THEN evaluate a compressed SELL LIMIT toward SSL (4235.17). |
| 27 | 2026-09-24 16:00 (NY Post-Open) | G:4257.73 S:63.586 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 28 | 2026-09-24 17:30 (NY Silver Bullet Open) | 4255.93 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price rallies into Bearish POI (4260.37–4260.65) and prints an M1/M5 bearish displacement MSS breaking below 4254.00 before 17:00 UTC, THEN queue SELL LIMIT at 4260.37 targeting External SSL 4235.17 with SL at 4265.50. |
| 29 | 2026-09-24 18:00 (NY Silver Bullet Mid) | 4261.37 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price expands into OTE premium (4273.81–4280.11) and prints an M5 Bearish MSS, THEN route a pro-trend SELL LIMIT targeting SSL at 4235.17. |
| 30 | 2026-09-25 10:00 (London Pre-Open) | G:4276.57 S:63.779 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 31 | 2026-09-25 10:30 (London Open) | 4271.00 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4295.78) or PDH (4303.58) and prints an M1/M5 bearish displacement MSS back below 4293.14, THEN anchor a SELL LIMIT at the resulting Bearish FVG proximal edge targeting 4244.14 (PDL). |
| 32 | 2026-09-25 11:00 (London Post-Open) | 4271.42 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Low (4264.14) and prints an energetic M5 displacement close above 4274.00, THEN stage BUY LIMIT at FVG retest targeting 4295.78. |
| 33 | 2026-09-25 15:00 (NY Pre-Open) | 4287.71 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 bearish displacement candle closing below 4281.80 (sweeping internal FVG support), THEN evaluate a `SELL LIMIT` on the resulting bearish breaker/FVG targeting PDL at 4244.14. |
| 34 | 2026-09-25 15:30 (NY Open) | 4295.38 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M1/M5 bearish displacement candle closes below the 4289.00 swing pivot with a newly printed Bearish FVG, THEN queue a `SELL LIMIT` at the FVG proximal edge targeting 4244.14 (PDL/SSL). |
| 35 | 2026-09-25 16:00 (NY Post-Open) | G:4296.63 S:64.655 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 36 | 2026-09-25 17:30 (NY Silver Bullet Open) | G:4310.34 S:64.965 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 37 | 2026-09-25 18:00 (NY Silver Bullet Mid) | 4304.21 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M1/M5 displacement candle closes decisively below 4302.27 confirming an energetic MSS, THEN place a [SELL LIMIT] at 4306.44 (Proximal FVG Edge), targeting 4244.14 (External SSL / PDL) with SL at 4315.77. |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*