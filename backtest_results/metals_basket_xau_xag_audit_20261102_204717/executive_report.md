# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261102_204717` | **Generated**: 2026-11-02 20:53:06 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **24** | All market open milestones evaluated |
| **Stand-Aside Directives** | **21 (87.5%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **3** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **2** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **1** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **100.0%** | Won / Total Filled |
| **Gross Profit** | **+$0.10** | Cumulative winning trades |
| **Gross Loss** | **-$0.00** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+0.10** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **99.00** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 2 | 1 | 1 | 0 | 100.0% | $+0.10 | 99.00 |
| **Silver (XAGUSD)** | 1 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |
| **Intermarket SMT Setups** | 2 | 1 | 1 | 0 | 100.0% | $+0.10 | 99.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **24** | **24** | 100% of candidate opportunities |
| **Filled Trades** | **1** | **18** | Filtered 21 questionable sessions |
| **Win / Loss Record** | **1 W / 0 L** | **2 W / 16 L** | Prevented 16 direct stop-outs |
| **Win Rate on Fills** | **100.0%** | **11.1%** | Council delta: +88.9% |
| **Gross Losses Incurred** | **-$14.90** | **-$126.54** | **Saved +$126.54 from bad entries** |
| **Gross Profits Captured** | **+$0.10** | **+$19.93** | Missed -$19.83 in passed winners |
| **Net Realized PnL** | **$+0.10** | **$-106.61** | **Net Council Value: +$106.71** |
| **Profit Factor** | **99.00** | **0.16** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-10-05 10:00 (London Pre-Open) | 4144.78 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (4163.07) or PDH into London Open and prints an energetic M1/M5 bearish displacement MSS close below 4152.90, THEN stage a [SELL LIMIT] at the proximal FVG edge targeting External SSL at 4110.83. |
| 2 | 2026-10-05 10:00 (London Pre-Open) | 61.175 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (61.665) or PDH (62.073) and delivers an M1/M5 bearish displacement MSS with body close below 61.50, THEN anchor a SELL LIMIT at the resulting Bearish FVG proximal edge targeting External SSL (59.671). |
| 3 | 2026-10-05 10:30 (London Open) | 4139.69 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price rallies to sweep Asian High (4163.07) or Breaker Zone (4159.44–4163.07) and prints a fresh M1/M5 bearish displacement MSS close, THEN issue a [SELL LIMIT] at the newly formed FVG proximal boundary targeting SSL `4110.83`. |
| 4 | 2026-10-05 11:00 (London Post-Open) | 4129.48 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 bullish displacement body close above `4135.00` leaving an unmitigated Bullish FVG with SL distance <= 17.00 pts, THEN evaluate BUY LIMIT per [RULE-METALS-010]. |
| 5 | 2026-10-05 11:00 (London Post-Open) | 60.906 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M5 displacement close breaking above `61.18` (confirming Bullish MSS with SMT backing), THEN prepare Buy Limit orders anchored at the resulting FVG proximal edge targeting `62.07` PDH. |
| 6 | 2026-10-05 15:00 (NY Pre-Open) | 4162.94 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 displacement body close breaking recent swing low support with a valid Bearish FVG, THEN queue a SELL LIMIT at the proximal edge targeting external SSL 4110.83. |
| 7 | 2026-10-05 15:00 (NY Pre-Open) | 61.607 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M1/M5 displacement body closes cleanly below the micro-swing low (61.450) confirming Bearish MSS, THEN place [SELL LIMIT] at the proximal FVG retest edge (61.55) targeting External SSL 59.671 with SL pinned at 61.86. |
| 8 | 2026-10-05 15:30 (NY Open) | 4168.02 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 displacement body close below 4165.00 forming a Bearish FVG, THEN stage a SELL LIMIT at the FVG proximal edge targeting External SSL 4110.83. |
| 9 | 2026-10-05 15:30 (NY Open) | 61.783 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M1/M5 displacement candle closes below 61.620 confirming a clear MSS, THEN anchor a SELL LIMIT at the FVG Proximal Edge (61.660) with SL at 61.864 targeting External SSL at 59.671. |
| 10 | 2026-10-05 16:00 (NY Post-Open) | 4161.57 | `SELL_LIMIT` | **WIN** | $+0.10 | IF price retraces to test `4166.58` without taking out 4169.95 first, THEN fill SELL LIMIT for immediate trend continuation. |
| 11 | 2026-10-05 16:00 (NY Post-Open) | 61.626 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price retraces into the Bearish FVG Proximal Edge at `61.704` during active session hours, THEN the limit order fills toward `59.671`. |
| 12 | 2026-10-06 10:00 (London Pre-Open) | G:4124.75 S:60.700 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 13 | 2026-10-06 10:30 (London Open) | G:4130.52 S:60.735 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 14 | 2026-10-06 11:00 (London Post-Open) | G:4125.63 S:60.639 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 15 | 2026-10-06 15:00 (NY Pre-Open) | 4146.34 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 displacement body close below 4143.80 (confirming Bearish MSS), THEN evaluate a SELL LIMIT at the newly formed Bearish FVG proximal edge targeting SSL at 4110.83. |
| 16 | 2026-10-06 15:30 (NY Open) | 4153.44 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price delivers an energetic 5M displacement body close below the 4143.00 pivot and leaves a bearish FVG, THEN place a [SELL LIMIT] at the FVG proximal edge targeting External SSL 4110.83. |
| 17 | 2026-10-06 16:00 (NY Post-Open) | 4157.05 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price rejects the 4158.17 peak and prints an energetic M5 displacement close below 4154.00 (Bearish MSS), THEN prepare SELL LIMIT at the resulting Bearish FVG proximal edge targeting SSL (4110.83). |
| 18 | 2026-10-06 17:30 (NY Silver Bullet Open) | 4157.43 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an energetic M1/M5 displacement candle closes below 4154.80 confirming a bearish MSS, THEN anchor a SELL LIMIT at the resulting FVG proximal edge targeting SSL at 4110.83 with SL pinned above 4160.84. |
| 19 | 2026-10-06 17:30 (NY Silver Bullet Open) | 60.987 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M1/M5 displacement body closes cleanly below local micro-support (`60.95`), THEN issue a [SELL LIMIT] at the FVG Proximal Edge `61.055`, targeting External SSL `59.671` with SL pinned at `61.155`. |
| 20 | 2026-10-06 18:00 (NY Silver Bullet Mid) | 4168.52 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 displacement body close below the 4160.79 pivot (confirming Bearish MSS), THEN anchor a SELL LIMIT at the newly formed Bearish FVG proximal edge targeting External SSL 4110.83. |
| 21 | 2026-10-06 18:00 (NY Silver Bullet Mid) | 61.440 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an M5 displacement candle prints an energetic body close below 61.140 (Bearish MSS) confirming the 61.469 sweep, THEN anchor a SELL LIMIT at the proximal boundary of the newly formed Bearish FVG with SL pinned >= 0.08 pts above 61.470. |
| 22 | 2026-10-07 10:00 (London Pre-Open) | 4142.86 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price runs the Asian High (4169.80) or OTE Premium (4157.77–4163.15) and prints an energetic M1/M5 bearish MSS displacement close, THEN issue a pending SELL LIMIT at the proximal FVG edge targeting SSL at 4104.38. |
| 23 | 2026-10-07 10:00 (London Pre-Open) | 60.816 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (61.487) or PDH (61.859) during London killzone and forms an M1/M5 bearish displacement MSS below micro-pivots, THEN issue a [SELL LIMIT] at the proximal FVG edge targeting SSL (59.671). |
| 24 | 2026-10-07 10:30 (London Open) | 4142.98 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range High (4169.80) into London session and prints an M1/M5 bearish displacement MSS close, THEN place SELL LIMIT at Bearish POI Proximal Edge targeting 4104.38 SSL. |
| 25 | 2026-10-07 10:30 (London Open) | 60.872 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price rallies into Asian High (61.487) or OTE zone (61.247) and executes a verified liquidity sweep with an M1/M5 bearish displacement MSS close below 61.100, THEN trigger SELL LIMIT at the resulting FVG proximal edge targeting SSL at 59.671. |
| 26 | 2026-10-07 11:00 (London Post-Open) | 4139.47 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price tags 4143.12 before taking out 4138.15, THEN execute Sell Limit into structural drop toward 4104.38. |
| 27 | 2026-10-07 11:00 (London Post-Open) | 60.782 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range Low (60.673) or PDL (60.266) with a verified Bullish SMT divergence against XAUUSD, THEN await M1/M5 displacement MSS to stage a long entry. |
| 28 | 2026-10-08 15:30 (NY Open) | G:4130.62 S:59.034 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 29 | 2026-10-08 18:00 (NY Silver Bullet Mid) | G:4121.77 S:58.764 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*