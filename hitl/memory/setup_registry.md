# 🏛️ TradingGuard Ratified Setup Archetype Registry
**Last Calibration:** `2026-11-04T22:42:14.975658` | **Version:** `1.0.0`

> **Mandatory Firm Governance:** The Operational Trading Council is **strictly prohibited** from placing orders on unratified setups.
> Every candidate archetype must pass forensic risk stress-testing by the Retrospective Review Council before authorization.

---
## 📌 Active Ratified Archetypes

### 🟢 [SETUP-ARCH-001] Judas Swing Liquidity Sweep & Breaker Block Reversal (Liquidity Sweep & Reversal)
- **Description:** Intraday sweep of Asian or London extreme that immediately rejects into an opposite 5M breaker block.
- **Entry Trigger:** `Anchor Limit Order at Breaker Block proximal edge.`
- **Invalidation Anchor:** `Structural extreme of the Judas sweep wick with mandated ATR buffer.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Extreme of Judas Sweep Wick + Max(1.5 * 5M ATR, 2.0 * Median Session Spread), with hard floor at 3.5 pips (FX) / $1.80 (XAUUSD).`
> **Supervisory Audit Verdict:** RATIFIED | *Approved for automated and discretionary deployment across MULTI engine runtime during designated London and NY session killzones. All orders must enforce proximal breaker block limit mitigation with strict OCO execution.*

### 🟢 [SETUP-ARCH-002] Judas Swing & Fair Value Gap Mitigation (Liquidity Sweep & FVG Mitigation)
- **Description:** Session sweep of liquidity followed by immediate mitigation of a newly formed 5M Fair Value Gap.
- **Entry Trigger:** `Limit order at 5M FVG proximal edge.`
- **Invalidation Anchor:** `Distal edge of FVG plus active session ATR buffer.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Distal FVG edge + max(0.5 * 5M ATR, 1.5 * Real-Time Spread)`
> **Supervisory Audit Verdict:** RATIFIED | *Authorized for active execution across MULTI portfolio assets. Execution is strictly conditioned on confirmed HTF liquidity run prior to 5M FVG creation during designated high-volume session windows (London & NY Open). Limit orders must verify spread normalization prior to routing. [AUDIT 2026-11-04]: Decommissioned on Gold (-17.5R). Highly Ratified on GBPUSD (+6.0R, 40.0% WR, PF 2.50) for London Open / Continuation order block retests.*

### 🟢 [SETUP-ARCH-003] Confirmed Market Structure Shift (MSS) Breaker Retest (Structural Shift & Breaker Retest)
- **Description:** Displacement through opposing swing pivot establishing a Breaker Block, followed by a retest.
- **Entry Trigger:** `Limit order at Breaker Block proximal boundary.`
- **Invalidation Anchor:** `Opposing swing extreme or Breaker distal boundary.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Max(2.0 pips + 1.2x Current Spread, 0.25x M15 ATR) beyond the breaker distal boundary or originating swing pivot`
> **Supervisory Audit Verdict:** RATIFIED | *The structural transition of failed order flow into a breaker block demonstrates robust statistical expectancy and distinct institutional footprints under NY liquidity conditions. Deployment authorized strictly with candle-body displacement confirmation and mandated spread-adjusted buffers. [AUDIT 2026-11-04]: Core Tier-1 Flagship on both Gold (+9.0R) and GBPUSD (+15.0R, 31.4% WR, PF 1.60).*

### 🟢 [SETUP-ARCH-004] Institutional Range Expansion / NY Silver Bullet (Trend Continuation / Range Expansion)
- **Description:** High-volume displacement breaking past session range high/low leaving an unbalanced FVG.
- **Entry Trigger:** `Limit order at Expansion FVG proximal edge.`
- **Invalidation Anchor:** `Prior session boundary or FVG distal edge.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `FVG Distal Edge + minimum 3.0 pips (FX) / 2.0 ticks outside displacement pivot`
> **Supervisory Audit Verdict:** RATIFIED | *Authorized strictly for execution within the 10:00 AM - 11:00 AM NY window, conditional on higher-timeframe trend alignment and post-news spread normalization.*

### 🟢 [SETUP-ARCH-005] Precious Metals Intermarket SMT Divergence & Liquidity Sweep Mitigation (Intermarket SMT Divergence & Liquidity Sweep)
- **Description:** Relative structural non-confirmation between Gold (XAUUSD) and Silver (XAGUSD) at key session liquidity boundaries (London / NY Open). When one metal sweeps session extremes (Judas swing) while the other refuses to sweep (holding higher low or lower high), enter on the mitigation of the confirmed 5M FVG or Breaker Block aligned with institutional accumulation/distribution.
- **Entry Trigger:** `Limit order at the proximal edge of the confirmed 5M FVG or Breaker Block on the metal exhibiting clean structural displacement.`
- **Invalidation Anchor:** `Extreme of the Judas sweep wick with mandated volatility and spread buffer.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `XAUUSD: Max($1.50, $0.80 + 1.5x 5M ATR) | XAGUSD: Max($0.06, $0.03 + 1.5x 5M ATR) beyond Judas sweep extreme`
> **Supervisory Audit Verdict:** RATIFIED | *Approved for algorithmic and discretionary execution exclusively within the designated London Open (07:00–09:00 UTC) and NY Open (12:30–14:30 UTC) liquidity windows. Execution is strictly conditioned on confirmed 5M structural displacement and strict enforcement of the spread-expansion cap.*

### 🟢 [SETUP-ARCH-006] Forex Intermarket SMT Divergence & Symbiotic Cross-Pair Mitigation (Forex Intermarket SMT & Cross-Pair Confluence)
- **Description:** Relative structural non-confirmation between EURUSD and GBPUSD at key session extremes (London/NY Open). When one currency sweeps session liquidity (Judas purge) while the other holds structural divergence (Higher Low / Lower High), or when a leading pair prints a market structure shift that forecasts the lagging pair expansion, enter on the proximal mitigation of the confirmed 5M FVG or Breaker Block.
- **Entry Trigger:** `Limit order at proximal edge of the confirmed 5M FVG or Breaker Block on the currency pair offering the highest risk-reward asymmetry.`
- **Invalidation Anchor:** `Extreme of the Judas sweep wick with mandated volatility and spread buffer (min 8.0-12.0 pips on EURUSD, 9.0-14.0 pips on GBPUSD).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Base Judas sweep extreme + 10.0 pips (EURUSD) / + 13.0 pips (GBPUSD), or 1.2x/1.5x 5M ATR minimum`
> **Supervisory Audit Verdict:** RATIFIED | *Approved for live deployment across EURUSD and GBPUSD during London Open (07:00-09:30 UTC) and NY Open (12:30-15:00 UTC) session windows. Execution requires documented 5M structural shift confirmation prior to limit entry on proximal FVG/Breaker boundaries.*

### 🟢 [SETUP-ARCH-007] Unmitigated ChoCh Origin & SMT Liquidity Sweep Mitigation (Counter-Trend POI Mitigation & SMT Sweep)
- **Description:** Selective counter-trend reaction setup targeting internal mean-reversion liquidity (Midnight Open, Session Open, or Opposing Session FVG) when price mitigates the unmitigated origin of a prior major ChoCh displacement leg, confirmed by intermarket SMT divergence.
- **Entry Trigger:** `Limit order anchored at the 50% Mean Threshold (MT) or 75% Deep Discount (OTE) of the unmitigated POI origin (RULE-EXEC-036). Proximal edge entry is prohibited.`
- **Invalidation Anchor:** `Distal boundary of originating sweep low/high + 2.0 pip spread buffer (Forex) / .50 (Gold).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Distal Edge + 2.0 pips spread buffer (Forex) / .50 (Gold).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified collaboratively by Review Council and Lead Human Partner (Seat #7). Allows selective counter-trend execution exclusively when mitigating an unmitigated ChoCh origin with confirmed SMT divergence. Mandatory deep limit entry (50%-75% depth) guarantees R:R >= 1:3.0 to internal liquidity pools.*

### 🟢 [SETUP-ARCH-008] HTF Liquidity Sweep with LTF (M1) Market Structure Shift & Displacement Retest (HTF Liquidity Purge & LTF Execution Confirmation)
- **Description:** High-probability reversal archetype triggered when price purges a critical Higher-Timeframe liquidity extreme (Previous Day High/Low [PDH/PDL], Previous Week High/Low [PWH/PWL], or Session High/Low) during key Killzone windows (London/NY Open). Instead of taking blind limit orders on 5M/15M, execution requires dropping to the 1-Minute (M1) timeframe to confirm an energetic Market Structure Shift (MSS) displacement body close breaking the preceding micro-swing pivot, followed by entry on the 50%-62% FVG / mitigation retest.
- **Entry Trigger:** `Limit or market execution upon M1 retest of the Fair Value Gap (FVG) or Breaker/Order Block created by the M1 MSS displacement candle (50% Mean Threshold or OTE zone).`
- **Invalidation Anchor:** `Pinned strictly beyond the extreme wick of the HTF sweep peak + spread buffer (1.0 pip for GBPUSD per amended RULE-RISK-011; 1.5-2.5 pips for EURUSD per amended RULE-RISK-007).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Sweep Wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified collaboratively with Lead Human Partner (Seat #7). Proven on Monday, September 21, 2026 Cable NY Open sweep (PDH 1.33982 swept to 1.34003 peak; M1 MSS at 1.33925; entry at 1.33933 with 7.8 pip stop at 1.34011; TP hit at 1.33686 for +24.7 pips / 3.17R). Eliminates blind sweep stop-outs.*

### 🟢 [SETUP-ARCH-009] Pro-Trend Session Breakdown Origin Retest (NY AM Trend Continuation) (Pro-Trend POI Mitigation & Trend Continuation)
- **Description:** High-probability trend continuation archetype executing during the New York session (15:30-17:30 Tehran / 08:00-10:00 NY) when price is aligned with the Macro Directional Filter (SELL_ONLY or BUY_ONLY). Bypasses mid-range chop filters by recognizing internal retracement into the unmitigated origin of the prior session's impulse leg (London Breaker Block, 15M/1H FVG, or 50% Mean Threshold). Requires M1 Market Structure Shift (MSS) displacement confirmation before entry.
- **Entry Trigger:** `M1 retracement into the displacement FVG / Breaker following confirmed M1 MSS at the London breakdown/breakout origin zone.`
- **Invalidation Anchor:** `Retracement swing peak + spread buffer (1.0 pip for GBPUSD; 1.5-2.5 pips for EURUSD).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Retracement Peak Wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified collaboratively with Lead Human Partner (Seat #7). Proven on Tuesday, September 22, 2026 Cable NY retracement (London dump from 1.3387 to 1.3326; NY retracement into London breakdown origin at 1.3368-1.3373; M1 MSS trigger at 1.33685 with 6.1 pip stop; dump to 1.33215 yielding +45 pips / 6.9R). Eliminates the mid-range chop blind spot on trend continuation days. [AUDIT 2026-11-04]: Permanently Decommissioned on Gold (-46.5R) and GBPUSD (-20.5R, 13.2% WR, PF 0.46) due to deep retracement failure in trending markets.*

### 🟢 [SETUP-ARCH-010] Prominent Liquidity Sweep with Pro-Trend M1 MSS Displacement (Pro-Trend Prominent Sweep & LTF Execution)
- **Description:** High-conviction trend continuation archetype executing exclusively in the direction of the confirmed HTF trend (Daily/4H). When price sweeps a visually prominent horizontal liquidity ceiling or floor (Equal Highs/Lows [EQH/EQL], Previous Day High/Low [PDH/PDL], or Prior Session Extreme), it bypasses deep HTF retracement requirements. Execution is triggered when price prints an immediate 1-Minute (M1) Market Structure Shift (MSS) with an energetic displacement candle body closing past the micro-swing pivot in the pre-determined trend direction. Entry is placed on the M1 FVG / Breaker retest or immediate execution upon M1 MSS close, with Stop Loss strictly anchored 1.0 pip beyond the sweep wick extreme.
- **Entry Trigger:** `M1 MSS displacement body close in pre-determined trend direction, followed by retest of M1 FVG / Breaker origin.`
- **Invalidation Anchor:** `Extreme of the prominent sweep wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Sweep Wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified collaboratively with Lead Human Partner (Seat #7). Designed specifically to capture runaway trend expansions (such as September 11 Equal Highs sweep and September 16 PDH sweep) without demanding deep 50% HTF retracements. By locking invalidation to the M1 sweep wick, dollar risk remains strictly within the  cap while providing 1:3R to 1:6R+ asymmetry. [AUDIT 2026-11-04]: Flagship on Gold (+14.0R, PF 1.67) and 100% WR on Cable (+5.0R, 2/2 wins).*

### 🟢 [SETUP-ARCH-011] Nested Double MSS (Macro Shift + Pullback Exhaustion Shift) (Structural Shift & Complex Pullback Exhaustion)
- **Description:** Multi-wave nested reversal formation. Price sweeps macro liquidity (L1->L2), displaces above H1 (1st MSS to H2), forms an internal pullback (H2->L3->H3->L4), and prints a 2nd MSS displacement breaking H3 to H4. Entry is placed on the retest of H3 / FVG at L5 with Stop Loss anchored below L4.
- **Entry Trigger:** `Limit order at H3 breaker retest or newly formed displacement FVG at L5.`
- **Invalidation Anchor:** `Structural extreme of the internal low L4 + $1.50 spread buffer.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `L4 swing extreme + $1.50 spread buffer (Gold), bounded between $3.50 min and $8.00 max.`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified following comprehensive 2-month empirical audit on Gold (Sep 1 - Nov 4, 2026). Achieved 30.0% Win Rate, +8.0R Net Profit, and 1.62 Profit Factor with sweep confirmation. Unanchored execution without sweep is strictly banned due to 10% win rate collapse.*

### 🟢 [SETUP-ARCH-012] Macro ADR Exhaustion Mean-Reversion Snapback (Quantitative Statistical Arbitrage & Mean-Reversion)
- **Description:** Statistical exhaustion pattern triggering when an asset expands >= 85% of its 20-day Average Daily Range (ADR) during institutional session hours before 16:00 UTC, followed by an M5 rejection bar at the intraday extreme. Exploits low probability of unilateral trend continuation past ADR without mean-reverting towards session equilibrium.
- **Entry Trigger:** `Market order on M5 rejection candle close at intraday extreme (Bearish close at Day High for Short; Bullish close at Day Low for Long).`
- **Invalidation Anchor:** `Structural extreme of the day + .50 buffer (Gold). Risk strictly bounded within [.50, .00] pts.`
- **Mandated Minimum R:R:** `1:2.5`
- **Stop Buffer Requirement:** `Extreme of the day + .50 spread buffer (Gold), bounded between .50 min and .00 max.`
> **Supervisory Audit Verdict:** RATIFIED | *Formally ratified following multi-seasonal raw broker tick mining across all 4 calendar seasons of 2026 (67.48M ticks on XAUUSD_o). Demonstrated positive expectancy across every single season: Winter +1.5R, Spring +1.0R, Summer +5.5R, Autumn +1.0R (Total: 34 Fills, 10W-16L-8BE, +9.0R Net, Profit Factor 1.56). Strictly specialized for Gold (XAUUSD); prohibited on GBPUSD (-10.0R failure due to non-mean-reverting intraday trends). Target strictly capped at 2.5R (empirical ceiling for mean-reversion counter-trend trades; 0 wins at >=3.5R).*

### 🟢 [SETUP-ARCH-013] HTF Draw on Liquidity (DOL) Sweep & 15M Structural Trailing Runner (Macro Trend Expansion & Structural Trailing)
- **Description:** Captures multi-hour higher timeframe expansion legs on Cable (GBPUSD) by identifying liquidity sweeps of Prior Day High/Low (PDH/PDL) or Asian Session extremes, triggering on 1-minute Market Structure Shift displacement, and holding across multi-hour expansions by trailing invalidation behind 15-minute swing pivots.
- **Entry Trigger:** `1-Minute MSS displacement body close breaking counter-trend micro-pivot following sweep of PDH/PDL or Asian extreme.`
- **Invalidation Anchor:** `Extreme of 1-minute sweep wick + 0.6 pip spread buffer. Bounded between 5.0 and 12.0 pips.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `M1 sweep wick extreme + 0.6 pips (0.00006), clamped to [5.0, 12.0] pips.`
> **Supervisory Audit Verdict:** RATIFIED | *Formally ratified following full-year 2026 multi-seasonal audit on GBPUSD across 22.74M ticks (126 setups). Delivered +47.1R Net Realized Profit (PF 1.53, 24.6% WR) by trailing 15-minute swing structure to capture multi-hour expansions, compared to only +7.0R under static 2.5R target. Produced multiple massive winners: +9.08R (Jun 5), +8.33R (Jul 20), +8.09R (Jun 1), +8.03R (Jun 22), and +7.46R (Oct 6). Positive in 3 of 4 seasons: Summer +37.1R, Winter +8.1R, Autumn +6.0R.*

### 🟢 [SETUP-ARCH-014] Macro H1 Reversal Origin Retest (MSS Ignition Base) (Multi-Day Structural Retest & Institutional Base Mitigation)
- **Description:** Identifies the exact multi-day H1 consolidation base that launched a major Market Structure Shift (MSS) reversal (> .00 displacement). When price retraces back into the unmitigated origin base 1 to 7 days later during institutional London/NY hours, enters with Stop Loss strictly anchored beyond the origin base wick.
- **Entry Trigger:** `Market entry upon M5 confirmation inside the unmitigated H1 MSS origin zone.`
- **Invalidation Anchor:** `Extreme wick of the origin base + .00 spread buffer. Risk bounded within [.00, .00].`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Origin base extreme wick + .00 spread buffer (Gold), bounded to [.00, .00].`
> **Supervisory Audit Verdict:** RATIFIED | *Formally ratified following full-year 2026 empirical audit across 298,638 M1 bars and 67.5M ticks on Gold (XAUUSD_o). Achieved +14.0R Net Realized Profit (PF 1.40, 23.3% WR) across 60 completed fills on retests of 2 to 7 day-old H1 MSS origins. MFE analysis confirms multiple deep expansions: +10.30R (Mar 3), +8.25R (Nov 3), +6.81R (Oct 27), and +6.37R (Jan 27). Strictly restricted to Reversal Origins (MSS); Continuation Origins (BOS) failed (-16.5R) due to deep pullback invalidations. Banned on GBPUSD (-26.5R) where Cable trends in open air without respecting multi-day H1 bases.*
