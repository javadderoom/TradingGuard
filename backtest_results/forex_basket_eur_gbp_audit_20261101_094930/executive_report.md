# 🏆 Executive Backtest Audit Report: FOREX_BASKET_EUR_GBP_AUDIT
> **Run ID**: `forex_basket_eur_gbp_audit_20261101_094930` | **Generated**: 2026-11-01 09:55:51 Tehran Time

## 📊 Portfolio Summary Scorecard
| Metric | Result | Benchmark Significance |
| :--- | :---: | :--- |
| **Total Calendar Sessions** | **24** | All market open milestones evaluated |
| **Stand-Aside Directives** | **16 (66.7%)** | Capital preserved in non-trending drift |
| **Approved Limit Orders** | **8** | Strict SMC confluences satisfied |
| **Unfilled Orders (75m TTL)** | **1** | Safely cancelled after 75 minutes |
| **Watchdog Radar Interceptions** | **0** | Adverse spikes killed before execution |
| **Filled Institutional Trades** | **5** | Executed with strict hard stop-losses |
| **Win Rate on Fills** | **60.0%** | Won / Total Filled |
| **Gross Profit** | **+$9.13** | Cumulative winning trades |
| **Gross Loss** | **-$2.10** | Strictly contained under $17 cap |
| **Net Realized PnL** | **$+7.03** | **Bottom-line cash flow on 0.01 base lots** |
| **Profit Factor** | **4.35** | Gross Profit / Gross Loss |

## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)
> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?

| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |
| :--- | :---: | :---: | :--- |
| **Total Setups Screened** | **24** | **24** | 100% of candidate opportunities |
| **Filled Trades** | **5** | **12** | Filtered 16 questionable sessions |
| **Win / Loss Record** | **3 W / 2 L** | **4 W / 8 L** | Prevented 6 direct stop-outs |
| **Win Rate on Fills** | **60.0%** | **33.3%** | Council delta: +26.7% |
| **Gross Losses Incurred** | **-$37.97** | **-$8.10** | **Saved +$6.00 from bad entries** |
| **Gross Profits Captured** | **+$27.03** | **+$10.83** | Missed -$2.50 in passed winners |
| **Net Realized PnL** | **$+7.03** | **$+2.73** | **Net Council Value: +$3.50** |
| **Profit Factor** | **3.97** | **1.34** | Risk-adjusted quality improvement |

## 📋 Session-by-Session Trade & Watchlist Ledger
| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |
| :-: | :--- | :---: | :---: | :---: | :---: | :--- |
| 1 | 2026-09-02 10:00 (London Pre-Open) | EUR:1.15787 GBP:1.35034 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 2 | 2026-09-02 10:30 (London Open) | 1.35007 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Potential Bearish Trend Continuation or Validated Liquidity Reversal pending London Open volume. |
| 3 | 2026-09-02 11:00 (London Post-Open) | 1.15758 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Pro-trend Bearish Continuation. Price is consolidating tight against swept session lows beneath the 1.15760 micro-resistance. |
| 4 | 2026-09-02 11:00 (London Post-Open) | 1.34982 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Incubation of a London Open continuation breakdown or a classic Judas swing reversal back into the Asian range. |
| 5 | 2026-09-02 15:00 (NY Pre-Open) | 1.35090 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** A shallow London High sweep (1.35147) without structural follow-through suggests an impending re-sweep or a true New York Judas swing into London Low (1.34897). |
| 6 | 2026-09-02 15:30 (NY Open) | EUR:1.15757 GBP:1.35038 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 7 | 2026-09-02 16:00 (NY Post-Open) | 1.34957 | `SELL_LIMIT` | **EXPIRED** | $0.00 | • **Developing Setup Context:** London session low at 1.34897 remains exposed; if price sweeps this low without filling the limit order, monitor for potential exhaustion. |
| 8 | 2026-09-02 17:30 (NY Silver Bullet Open) | 1.15725 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Bearish continuation setup incubating on an engineered liquidity run into session premium OTE / PDL retest (`1.15764`–`1.15848`). |
| 9 | 2026-09-02 18:00 (NY Silver Bullet Mid) | 1.15761 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Pending purge of Session Sell-Side Liquidity at `1.15670` into higher-timeframe discount, or a clean London/NY AM High sweep at `1.15822`. |
| 10 | 2026-09-03 10:00 (London Pre-Open) | EUR:1.15962 GBP:1.34941 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 11 | 2026-09-03 10:30 (London Open) | EUR:1.15962 GBP:1.34937 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 12 | 2026-09-03 11:00 (London Post-Open) | EUR:1.15987 GBP:1.34965 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 13 | 2026-09-03 15:00 (NY Pre-Open) | 1.16031 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Pre-NY compression between London Low (1.15935) and London High (1.16147). A liquidity purge into London Low or a pro-trend expansion clearing London High is brewing for the NY open. |
| 14 | 2026-09-03 15:00 (NY Pre-Open) | 1.34983 | `SELL_LIMIT` | **LOSS** | $-1.00 | • **Developing Setup Context:** London session liquidity delivery complete; order incubating ahead of NY Pre-Open retest. |
| 15 | 2026-09-03 15:30 (NY Open) | EUR:1.16089 GBP:1.34990 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 16 | 2026-09-04 10:00 (London Pre-Open) | EUR:1.16269 GBP:1.35305 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 17 | 2026-09-04 10:30 (London Open) | EUR:1.16267 GBP:1.35321 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 18 | 2026-09-04 11:00 (London Post-Open) | EUR:1.16248 GBP:1.35306 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 19 | 2026-09-04 15:00 (NY Pre-Open) | 1.35306 | `SELL_LIMIT` | **WIN** | $+2.89 | • **Developing Setup Context:** A deeper retracement into the OTE 70.5% premium level (1.35426) before NY Open acceleration if the immediate FVG fails to contain price. |
| 20 | 2026-09-04 15:30 (NY Open) | EUR:1.16227 GBP:1.35309 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 21 | 2026-09-04 17:30 (NY Silver Bullet Open) | EUR:1.16218 GBP:1.35336 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 22 | 2026-09-04 18:00 (NY Silver Bullet Mid) | EUR:1.16211 GBP:1.35347 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 23 | 2026-09-07 10:00 (London Pre-Open) | 1.35096 | `BUY_LIMIT` | **WIN** | $+3.00 | • **Developing Setup Context:** Pre-London expansion into Asian Range High (1.35221). |
| 24 | 2026-09-07 10:30 (London Open) | EUR:1.16105 GBP:1.35100 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 25 | 2026-09-07 11:00 (London Post-Open) | EUR:1.16103 GBP:1.35101 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 26 | 2026-09-07 15:00 (NY Pre-Open) | 1.35433 | `BUY_LIMIT` | **OPEN_AT_END** | $0.00 | • **Developing Setup Context:** Should price push directly to PDH `1.35492` without mitigating the 5M FVG, a shallow runner may leave unfilled limit exposure before the New York pre-open. |
| 27 | 2026-09-07 15:30 (NY Open) | 1.16226 | `SELL_LIMIT` | **OPEN_AT_END** | $0.00 | • **Developing Setup Context:** If the 5M Bearish FVG fails to contain price and re-expansion breaches 1.16358, the setup transitions into a pro-trend continuation runner per [RULE-TREND-008] and [RULE-SETUP-010]. |
| 28 | 2026-09-07 16:00 (NY Post-Open) | EUR:1.16259 GBP:1.35418 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 29 | 2026-09-07 17:30 (NY Silver Bullet Open) | EUR:1.16242 GBP:1.35376 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 30 | 2026-09-07 18:00 (NY Silver Bullet Mid) | EUR:1.16229 GBP:1.35348 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 31 | 2026-09-08 10:00 (London Pre-Open) | 1.35368 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Incipient London session manipulation; price is hovering just below Asian Low (1.35348) without energetic rejection. |
| 32 | 2026-09-08 10:30 (London Open) | EUR:1.16247 GBP:1.35377 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 33 | 2026-09-08 11:00 (London Post-Open) | EUR:1.16239 GBP:1.35367 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 34 | 2026-09-08 15:00 (NY Pre-Open) | 1.16149 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Price is consolidating near London Lows ahead of NY Open (15:30–16:00 UTC) with unswept PDL (1.16063) resting just 2.2 pips below the current extreme. |
| 35 | 2026-09-08 15:00 (NY Pre-Open) | 1.35315 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Bullish liquidity purge of London Low completed; awaiting New York Open expansion displacement to confirm structural shift. |
| 36 | 2026-09-08 15:30 (NY Open) | 1.16104 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** London Low sweep (1.16085) is incubating an institutional accumulation schematic near PDL (1.16063). We await a decisive 5M displacement breaking above 1.16130 to confirm a valid shift. |
| 37 | 2026-09-08 15:30 (NY Open) | 1.35268 | `BUY_LIMIT` | **WIN** | $+2.44 | • **Developing Setup Context:** Pro-trend NY Open expansion setup into premium BSL following London discount clearance. |
| 38 | 2026-09-08 16:00 (NY Post-Open) | EUR:1.16118 GBP:1.35261 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 39 | 2026-09-09 10:00 (London Pre-Open) | EUR:1.16301 GBP:1.35457 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 40 | 2026-09-09 10:30 (London Open) | EUR:1.16313 GBP:1.35466 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 41 | 2026-09-09 11:00 (London Post-Open) | EUR:1.16322 GBP:1.35476 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 42 | 2026-09-09 15:00 (NY Pre-Open) | 1.16366 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** A potential Judas Swing distribution top is printing at 1.16494 with SMT divergence, but price is drifting without displacement. |
| 43 | 2026-09-09 15:00 (NY Pre-Open) | 1.35473 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** Awaiting a NY pre-open liquidity purge of the London Low (`1.35445`) or London High (`1.35680`) to trigger institutional order flow expansion. |
| 44 | 2026-09-09 15:30 (NY Open) | 1.35432 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** London Low Judas sweep at 1.35412 incubating a potential reversal, but pending 5M displacement and closure above the active Bearish FVG. |
| 45 | 2026-09-09 16:00 (NY Post-Open) | 1.35431 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** A potential bullish Judas reversal is incubating following the London Low purge, but requires institutional displacement to prove smart-money accumulation over continuation drift. |
| 46 | 2026-09-09 17:30 (NY Silver Bullet Open) | EUR:1.16324 GBP:1.35377 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 47 | 2026-09-09 18:00 (NY Silver Bullet Mid) | 1.35632 | `BUY_LIMIT` | **LOSS** | $-1.10 | • **Developing Setup Context:** A deeper retracement into the London breakout Breaker Block / 62%–79% OTE discount zone (1.35416–1.35447) if the shallow 5M FVG fails to hold. |
| 48 | 2026-09-10 10:00 (London Pre-Open) | EUR:1.16378 GBP:1.35555 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 49 | 2026-09-10 10:30 (London Open) | 1.35555 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | • **Developing Setup Context:** London Open Judas Swing manipulation setup incubating. Both Asian extremes (1.35603 High / 1.35447 Low) remain intact and unswept. |
| 50 | 2026-09-10 11:00 (London Post-Open) | EUR:1.16382 GBP:1.35557 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 51 | 2026-09-10 15:00 (NY Pre-Open) | EUR:1.16385 GBP:1.35496 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 52 | 2026-09-10 15:30 (NY Open) | EUR:1.16376 GBP:1.35540 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 53 | 2026-09-10 16:00 (NY Post-Open) | EUR:1.16349 GBP:1.35473 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 54 | 2026-09-11 15:00 (NY Pre-Open) | EUR:1.16039 GBP:1.35083 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 55 | 2026-09-11 15:30 (NY Open) | EUR:1.15988 GBP:1.35041 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 56 | 2026-09-15 10:00 (London Pre-Open) | EUR:1.15385 GBP:1.34873 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 57 | 2026-09-15 11:00 (London Post-Open) | EUR:1.15367 GBP:1.34846 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 58 | 2026-09-15 15:00 (NY Pre-Open) | EUR:1.15355 GBP:1.34753 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 59 | 2026-09-15 15:30 (NY Open) | EUR:1.15349 GBP:1.34741 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 60 | 2026-09-15 16:00 (NY Post-Open) | EUR:1.15348 GBP:1.34732 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 61 | 2026-09-15 17:30 (NY Silver Bullet Open) | EUR:1.15351 GBP:1.34752 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 62 | 2026-09-15 18:00 (NY Silver Bullet Mid) | EUR:1.15418 GBP:1.34891 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 63 | 2026-09-16 10:00 (London Pre-Open) | EUR:1.15417 GBP:1.34793 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 64 | 2026-09-16 18:00 (NY Silver Bullet Mid) | EUR:1.15393 GBP:1.34632 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 65 | 2026-09-17 10:30 (London Open) | EUR:1.14610 GBP:1.33755 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 66 | 2026-09-17 16:00 (NY Post-Open) | EUR:1.14764 GBP:1.33949 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 67 | 2026-09-18 10:00 (London Pre-Open) | EUR:1.14854 GBP:1.33678 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 68 | 2026-09-18 15:00 (NY Pre-Open) | EUR:1.14811 GBP:1.33688 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 69 | 2026-09-18 15:30 (NY Open) | EUR:1.14836 GBP:1.33709 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 70 | 2026-09-18 16:00 (NY Post-Open) | EUR:1.14838 GBP:1.33668 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 71 | 2026-09-18 17:30 (NY Silver Bullet Open) | EUR:1.14767 GBP:1.33620 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 72 | 2026-09-21 10:00 (London Pre-Open) | EUR:1.14766 GBP:1.33835 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 73 | 2026-09-21 10:30 (London Open) | EUR:1.14748 GBP:1.33818 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 74 | 2026-09-21 11:00 (London Post-Open) | EUR:1.14746 GBP:1.33775 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 75 | 2026-09-21 17:30 (NY Silver Bullet Open) | EUR:1.14812 GBP:1.33828 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 76 | 2026-09-21 18:00 (NY Silver Bullet Mid) | EUR:1.14836 GBP:1.33887 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 77 | 2026-09-22 16:00 (NY Post-Open) | EUR:1.14564 GBP:1.33565 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 78 | 2026-09-22 17:30 (NY Silver Bullet Open) | EUR:1.14658 GBP:1.33628 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 79 | 2026-09-22 18:00 (NY Silver Bullet Mid) | EUR:1.14603 GBP:1.33551 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 80 | 2026-09-23 15:30 (NY Open) | EUR:1.14150 GBP:1.32964 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 81 | 2026-09-24 10:00 (London Pre-Open) | EUR:1.13786 GBP:1.32375 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 82 | 2026-09-24 10:30 (London Open) | EUR:1.13771 GBP:1.32349 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 83 | 2026-09-24 11:00 (London Post-Open) | EUR:1.13809 GBP:1.32400 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 84 | 2026-09-24 18:00 (NY Silver Bullet Mid) | EUR:1.13749 GBP:1.32286 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 85 | 2026-09-25 10:00 (London Pre-Open) | EUR:1.13695 GBP:1.32118 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 86 | 2026-09-25 10:30 (London Open) | EUR:1.13696 GBP:1.32116 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 87 | 2026-09-25 11:00 (London Post-Open) | EUR:1.13701 GBP:1.32127 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 88 | 2026-09-25 17:30 (NY Silver Bullet Open) | EUR:1.14027 GBP:1.32493 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 89 | 2026-09-28 18:00 (NY Silver Bullet Mid) | EUR:1.13757 GBP:1.32667 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 90 | 2026-09-29 10:00 (London Pre-Open) | EUR:1.13643 GBP:1.32445 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 91 | 2026-09-29 10:30 (London Open) | EUR:1.13611 GBP:1.32399 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 92 | 2026-09-29 15:00 (NY Pre-Open) | EUR:1.13441 GBP:1.32342 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 93 | 2026-09-29 15:30 (NY Open) | EUR:1.13477 GBP:1.32344 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 94 | 2026-09-29 18:00 (NY Silver Bullet Mid) | EUR:1.13485 GBP:1.32398 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 95 | 2026-09-30 10:00 (London Pre-Open) | EUR:1.13347 GBP:1.32278 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 96 | 2026-09-30 10:30 (London Open) | EUR:1.13328 GBP:1.32269 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 97 | 2026-09-30 11:00 (London Post-Open) | EUR:1.13308 GBP:1.32239 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 98 | 2026-09-30 15:00 (NY Pre-Open) | EUR:1.13535 GBP:1.32727 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 99 | 2026-09-30 18:00 (NY Silver Bullet Mid) | EUR:1.13558 GBP:1.32893 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 100 | 2026-10-01 11:00 (London Post-Open) | EUR:1.13216 GBP:1.32513 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 101 | 2026-10-01 17:30 (NY Silver Bullet Open) | EUR:1.12942 GBP:1.32272 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 102 | 2026-10-02 15:30 (NY Open) | EUR:1.12470 GBP:1.32023 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 103 | 2026-10-05 10:30 (London Open) | EUR:1.11628 GBP:1.31942 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 104 | 2026-10-05 11:00 (London Post-Open) | EUR:1.11710 GBP:1.31998 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 105 | 2026-10-05 17:30 (NY Silver Bullet Open) | EUR:1.12019 GBP:1.32224 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 106 | 2026-10-06 10:30 (London Open) | EUR:1.12218 GBP:1.32212 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 107 | 2026-10-06 11:00 (London Post-Open) | EUR:1.12211 GBP:1.32172 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 108 | 2026-10-06 18:00 (NY Silver Bullet Mid) | EUR:1.12612 GBP:1.32654 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 109 | 2026-10-07 10:00 (London Pre-Open) | EUR:1.12375 GBP:1.32535 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 110 | 2026-10-08 10:30 (London Open) | EUR:1.12042 GBP:1.32116 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 111 | 2026-10-08 11:00 (London Post-Open) | EUR:1.12033 GBP:1.32086 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 112 | 2026-10-08 15:00 (NY Pre-Open) | EUR:1.11886 GBP:1.31995 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 113 | 2026-10-08 15:30 (NY Open) | EUR:1.11901 GBP:1.31958 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 114 | 2026-10-08 16:00 (NY Post-Open) | EUR:1.11894 GBP:1.31957 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 115 | 2026-10-09 10:00 (London Pre-Open) | EUR:1.12242 GBP:1.32376 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 116 | 2026-10-09 10:30 (London Open) | EUR:1.12271 GBP:1.32408 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 117 | 2026-10-12 10:00 (London Pre-Open) | EUR:1.12100 GBP:1.32455 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 118 | 2026-10-12 10:30 (London Open) | EUR:1.12094 GBP:1.32456 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 119 | 2026-10-12 11:00 (London Post-Open) | EUR:1.12100 GBP:1.32476 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 120 | 2026-10-12 15:00 (NY Pre-Open) | EUR:1.11926 GBP:1.32419 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 121 | 2026-10-13 10:30 (London Open) | EUR:1.11725 GBP:1.32186 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 122 | 2026-10-13 17:30 (NY Silver Bullet Open) | EUR:1.11886 GBP:1.32440 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 123 | 2026-10-13 18:00 (NY Silver Bullet Mid) | EUR:1.11871 GBP:1.32405 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 124 | 2026-10-14 11:00 (London Post-Open) | EUR:1.12090 GBP:1.32727 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 125 | 2026-10-14 15:30 (NY Open) | EUR:1.11946 GBP:1.32620 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 126 | 2026-10-14 18:00 (NY Silver Bullet Mid) | EUR:1.11919 GBP:1.32594 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 127 | 2026-10-15 18:00 (NY Silver Bullet Mid) | EUR:1.12167 GBP:1.32557 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 128 | 2026-10-16 10:00 (London Pre-Open) | EUR:1.12173 GBP:1.32821 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 129 | 2026-10-16 15:00 (NY Pre-Open) | EUR:1.12427 GBP:1.33214 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 130 | 2026-10-19 10:00 (London Pre-Open) | EUR:1.12273 GBP:1.33266 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 131 | 2026-10-19 10:30 (London Open) | EUR:1.12299 GBP:1.33266 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 132 | 2026-10-19 16:00 (NY Post-Open) | EUR:1.12130 GBP:1.33313 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 133 | 2026-10-20 15:00 (NY Pre-Open) | EUR:1.12314 GBP:1.33495 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 134 | 2026-10-20 15:30 (NY Open) | EUR:1.12128 GBP:1.33454 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 135 | 2026-10-20 18:00 (NY Silver Bullet Mid) | EUR:1.12074 GBP:1.33381 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 136 | 2026-10-21 10:00 (London Pre-Open) | EUR:1.12281 GBP:1.33743 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 137 | 2026-10-21 10:30 (London Open) | EUR:1.12279 GBP:1.33753 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 138 | 2026-10-21 11:00 (London Post-Open) | EUR:1.12242 GBP:1.33733 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 139 | 2026-10-21 17:30 (NY Silver Bullet Open) | EUR:1.12287 GBP:1.33903 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 140 | 2026-10-22 11:00 (London Post-Open) | EUR:1.12437 GBP:1.33976 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 141 | 2026-10-22 16:00 (NY Post-Open) | EUR:1.12318 GBP:1.34091 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 142 | 2026-10-23 10:00 (London Pre-Open) | EUR:1.12146 GBP:1.33952 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 143 | 2026-10-23 11:00 (London Post-Open) | EUR:1.12117 GBP:1.33926 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 144 | 2026-10-23 16:00 (NY Post-Open) | EUR:1.11958 GBP:1.33800 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 145 | 2026-10-23 17:30 (NY Silver Bullet Open) | EUR:1.11985 GBP:1.33755 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 146 | 2026-10-23 18:00 (NY Silver Bullet Mid) | EUR:1.11931 GBP:1.33734 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 147 | 2026-10-26 10:00 (London Pre-Open) | EUR:1.12207 GBP:1.33795 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 148 | 2026-10-26 11:00 (London Post-Open) | EUR:1.12196 GBP:1.33755 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 149 | 2026-10-26 16:00 (NY Post-Open) | EUR:1.12030 GBP:1.33486 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 150 | 2026-10-27 10:00 (London Pre-Open) | EUR:1.11712 GBP:1.33413 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 151 | 2026-10-27 10:30 (London Open) | EUR:1.11688 GBP:1.33367 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 152 | 2026-10-28 10:30 (London Open) | EUR:1.11210 GBP:1.32944 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 153 | 2026-10-28 15:00 (NY Pre-Open) | EUR:1.11226 GBP:1.32927 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 154 | 2026-10-28 17:30 (NY Silver Bullet Open) | EUR:1.11333 GBP:1.32909 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 155 | 2026-10-29 10:00 (London Pre-Open) | EUR:1.11455 GBP:1.33210 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 156 | 2026-10-29 10:30 (London Open) | EUR:1.11440 GBP:1.33199 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 157 | 2026-10-29 11:00 (London Post-Open) | EUR:1.11423 GBP:1.33181 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 158 | 2026-10-30 10:00 (London Pre-Open) | EUR:1.11898 GBP:1.33918 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 159 | 2026-10-30 10:30 (London Open) | EUR:1.11860 GBP:1.33860 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |
| 160 | 2026-10-30 17:30 (NY Silver Bullet Open) | EUR:1.11934 GBP:1.34269 | `STAND_ASIDE` | **STAND_ASIDE** | $0.00 | Filtered: No ratified setup |

---
*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*