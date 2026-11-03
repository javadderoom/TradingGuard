# 🏆 Executive Backtest Audit Report: METALS_BASKET_XAU_XAG_AUDIT
> **Run ID**: `metals_basket_xau_xag_audit_20261102_201700` | **Generated**: 2026-11-02 20:23:28 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **24** | All market open milestones evaluated |
| **Stand-Aside Directives** | **16 (66.7%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **8** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **3** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **5** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **20.0%** | Won / Total Filled |
| **Gross Profit** | **+$21.40** | Cumulative winning trades |
| **Gross Loss** | **-$21.45** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$-0.05** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **1.00** | Gross Profit / Gross Loss |

## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)
| Asset Segment | Approved Orders | Filled | Wins | Losses | Win Rate | Net PnL (0.01 lot) | Profit Factor |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Gold (XAUUSD)** | 5 | 3 | 1 | 2 | 33.3% | $+11.45 | 2.15 |
| **Silver (XAGUSD)** | 3 | 2 | 0 | 2 | 0.0% | $-11.50 | 0.00 |
| **Intermarket SMT Setups** | 1 | 0 | 0 | 0 | 0.0% | $+0.00 | 0.00 |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **24** | **24** | 100% of candidate opportunities |
| **Filled Trades** | **5** | **15** | Filtered 16 questionable sessions |
| **Win / Loss Record** | **1 W / 4 L** | **8 W / 7 L** | Prevented 3 direct stop-outs |
| **Win Rate on Fills** | **20.0%** | **53.3%** | Council delta: -33.3% |
| **Gross Losses Incurred** | **-$15.05** | **-$43.80** | **Saved +$22.35 from bad entries** |
| **Gross Profits Captured** | **+$39.95** | **+$131.50** | Missed -$110.10 in passed winners |
| **Net Realized PnL** | **$-0.05** | **$+87.70** | **Net Council Value: -$87.75** |
| **Profit Factor** | **1.00** | **3.00** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-10-12 10:00 (London Pre-Open) | G:4204.56 S:61.030 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 2 | 2026-10-12 10:30 (London Open) | 4200.46 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price pulls back to 4204.84 prior to breaking 4185.57, THEN fill pending SELL LIMIT. |
| 3 | 2026-10-12 11:00 (London Post-Open) | 61.026 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (61.441) or PDH (61.175) followed by an M1/M5 bearish displacement MSS closing below 61.02, THEN issue a [SELL LIMIT] at the proximal edge of the resulting displacement FVG. |
| 4 | 2026-10-12 15:00 (NY Pre-Open) | 4176.50 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price retraces into the Bearish FVG (`4178.30`) and prints an M1/M5 bearish displacement MSS close below `4174.80`, THEN execute pending SELL LIMIT targeting External Swing Low `4078.16`. |
| 5 | 2026-10-12 15:30 (NY Open) | 4176.34 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back into the 4184.00–4192.00 premium zone and prints an M1/M5 displacement MSS downward, THEN execute SELL LIMIT targeting PDL (4130.84) and External SSL (4078.00). |
| 6 | 2026-10-12 15:30 (NY Open) | 60.573 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back to test the Bearish Breaker / OTE zone at 60.95–61.02 during NY session open, THEN stage a SELL LIMIT targeting External SSL at 58.492. |
| 7 | 2026-10-12 16:00 (NY Post-Open) | 4174.08 | `SELL_LIMIT` | **LOSS** | $-4.28 | IF price pulls back to tap 4174.94 before 17:15 UTC, THEN order fills automatically; trail stop per [RULE-RISK-014] at 1:2.0R excursion. |
| 8 | 2026-10-12 16:00 (NY Post-Open) | 60.631 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back into OTE Premium (60.910–60.983) and prints an energetic M1/M5 Bearish MSS with displacement, THEN issue SELL LIMIT at the resulting Bearish FVG proximal edge targeting 58.492 SSL (R:R > 1:4.0). |
| 9 | 2026-10-12 17:30 (NY Silver Bullet Open) | 60.594 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price rallies into 60.678–60.680 before breaking the London Low (60.462), THEN limit order fills for expansion into 58.492. |
| 10 | 2026-10-13 10:00 (London Pre-Open) | 4179.43 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an energetic M1/M5 displacement candle body close below `4170.80` with a fresh bearish FVG during London killzone, THEN deploy a SELL LIMIT at the proximal FVG edge targeting `4084.74` (SL pinned at `4183.73`). |
| 11 | 2026-10-13 10:30 (London Open) | 4188.73 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian Range Low / PDL (4150.65–4154.60) and prints an energetic M1/M5 bullish displacement MSS breaking prior swing highs, THEN queue BUY LIMIT at the displacement FVG proximal edge. |
| 12 | 2026-10-13 10:30 (London Open) | 60.494 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (60.510) and PDH (61.441) followed by an M1/M5 bearish displacement MSS, THEN evaluate counter-trend SELL LIMIT; IF price sweeps Asian Low (59.561) and prints an energetic bullish MSS, THEN anchor BUY LIMIT at newly formed FVG. |
| 13 | 2026-10-13 11:00 (London Post-Open) | 4191.76 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF an energetic M5 displacement candle closes below 4187.00 confirming a bearish MSS, THEN evaluate a SELL LIMIT at 4189.41 targeting 4150.65 with SL at 4194.21. |
| 14 | 2026-10-13 11:00 (London Post-Open) | 60.518 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back to retest the 60.149–60.230 OTE discount with an M1 bullish MSS and SL distance <= 0.34 pts ($17 cap), THEN deploy BUY LIMIT. |
| 15 | 2026-10-13 15:00 (NY Pre-Open) | 4192.24 | `BUY_LIMIT` | **LOSS** | $-5.67 | IF price retraces to fill `4189.18` without breaking `4183.51`, THEN maintain buy limit for expansion into `4217.15`. |
| 16 | 2026-10-13 17:30 (NY Silver Bullet Open) | 60.257 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an M5 energetic displacement candle closing above 60.380, THEN anchor a BUY LIMIT at the FVG proximal edge (60.340) targeting 62.029 (BSL). |
| 17 | 2026-10-13 18:00 (NY Silver Bullet Mid) | 60.389 | `BUY_LIMIT` | **LOSS** | $-6.50 | IF price pulls back to retest the 60.350 breaker boundary before breaking 60.680, THEN order fills and automatically tracks to 61.440 with breakeven step at 1:2.0R (60.670). |
| 18 | 2026-10-14 10:00 (London Pre-Open) | 4163.79 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF London Open sweeps Asian High (4170.36) or PDH (4200.47) and prints an M1/M5 bearish displacement MSS close, THEN place SELL LIMIT at the proximal FVG edge targeting SSL at 4066.40. |
| 19 | 2026-10-14 10:00 (London Pre-Open) | 59.191 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price sweeps Asian High (59.340) and produces an energetic M1/M5 displacement body close back below 59.220 with Bearish Metals SMT, THEN place a pending SELL LIMIT at 59.221 targeting 58.492. |
| 20 | 2026-10-14 10:30 (London Open) | 4161.30 | `SELL_LIMIT` | **WIN** | $+21.40 | IF price pulls back to retest Bearish FVG at `4162.86` during London killzone, THEN execute the short order targeting `4066.40`. |
| 21 | 2026-10-14 10:30 (London Open) | 59.167 | `SELL_LIMIT` | **LOSS** | $-5.00 | IF market prints an M1 pull-back touching `59.221`, THEN fill SELL LIMIT order targeting external liquidity at `58.492`. |
| 22 | 2026-10-14 15:00 (NY Pre-Open) | 4148.67 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price retraces to fill the Bearish FVG at `4151.88`, THEN activate short execution targeting external structural swing low at `4050.62`. |
| 23 | 2026-10-14 15:00 (NY Pre-Open) | 58.720 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price pulls back and prints a 5M Bearish FVG near 58.850–58.890 followed by an M1/M5 bearish displacement MSS, THEN issue a [SELL LIMIT] at the FVG proximal edge targeting External SSL at 56.111. |
| 24 | 2026-10-14 15:30 (NY Open) | 58.522 | `SELL_LIMIT` | **EXPIRED** | $0.00 | IF price displaces with an energetic M5 body close above `58.890`, THEN cancel sell limit and evaluate counter-trend mean reversion. |
| 25 | 2026-10-15 10:00 (London Pre-Open) | 4150.60 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | IF price prints an M1/M5 displacement candle body closing below the micro-swing low with a valid Bearish FVG, THEN place **SELL LIMIT** at `4151.62`, SL `4161.72`, targeting SSL `4066.40` (R:R > 1:8.0). |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*