# 🏛️ TradingGuard Ratified Setup Archetype Registry
**Last Calibration:** `2026-11-16T18:15:29.727129` | **Version:** `1.0.0`

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
> **Supervisory Audit Verdict:** RATIFIED | *Approved for automated and discretionary deployment across MULTI engine runtime during designated London and NY session killzones. All orders must enforce proximal breaker block limit mitigation with strict OCO execution. NOTE: DECOMMISSIONED on GBPUSD due to -9.50R empirical drag (PF 0.44). On NQ, strictly restricted to London Open Bearish Judas Breakers (SHORT only, fading session highs, +5.36R, PF 1.60); Bullish Breaker decommissioned (-6.02R drag, 10% WR). Active on XAUUSD (+2.50R) and NQ London Open SHORT.*

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
> **Supervisory Audit Verdict:** RATIFIED | *Authorized strictly for execution within the 10:00 AM - 11:00 AM NY window, conditional on higher-timeframe trend alignment and post-news spread normalization. NOTE: DECOMMISSIONED on GBPUSD due to -8.50R empirical drag (PF 0.83). Active on XAUUSD (PRO_EXPANSION only).*

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

### 🟢 [SETUP-ARCH-010] Prominent Liquidity Sweep with Pro-Trend M1 MSS Displacement (Pro-Trend Prominent Sweep & LTF Execution)
- **Description:** High-conviction trend continuation archetype executing exclusively in the direction of the confirmed HTF trend (Daily/4H). When price sweeps a visually prominent horizontal liquidity ceiling or floor (Equal Highs/Lows [EQH/EQL], Previous Day High/Low [PDH/PDL], or Prior Session Extreme), it bypasses deep HTF retracement requirements. Execution is triggered when price prints an immediate 1-Minute (M1) Market Structure Shift (MSS) with an energetic displacement candle body closing past the micro-swing pivot in the pre-determined trend direction. Entry is placed on the M1 FVG / Breaker retest or immediate execution upon M1 MSS close, with Stop Loss strictly anchored 1.0 pip beyond the sweep wick extreme.
- **Entry Trigger:** `M1 MSS displacement body close in pre-determined trend direction, followed by retest of M1 FVG / Breaker origin.`
- **Invalidation Anchor:** `Extreme of the prominent sweep wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Sweep Wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified collaboratively with Lead Human Partner (Seat #7). Designed specifically to capture runaway trend expansions (such as September 11 Equal Highs sweep and September 16 PDH sweep) without demanding deep 50% HTF retracements. By locking invalidation to the M1 sweep wick, dollar risk remains strictly within the  cap while providing 1:3R to 1:6R+ asymmetry. [AUDIT 2026-11-04]: Flagship on Gold (+14.0R, PF 1.67) and 100% WR on Cable (+5.0R, 2/2 wins).*

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

### 🟢 [SETUP-QUANT-BTCUSD-R3_007] Autonomous Machine Quant Rule (BTCUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (price_zscore_100 <= -1.1366) AND (parkinson_vol >= 0.0007) AND (-0.0008 <= velocity_55 <= 0.0004) | TP: 1.8xATR, SL: 2.0xATR, BE: 1.2R, TTL: 36b
- **Entry Trigger:** `[SELL] (price_zscore_100 <= -1.1366) AND (parkinson_vol >= 0.0007) AND (-0.0008 <= velocity_55 <= 0.0004) | TP: 1.8xATR, SL: 2.0xATR, BE: 1.2R, TTL: 36b`
- **Invalidation Anchor:** `2.0x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:0.9`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7882 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-BTCUSD-R5_014] Autonomous Machine Quant Rule (BTCUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (-0.0008 <= velocity_55 <= 0.0004) AND (parkinson_vol >= 0.0007) AND (price_zscore_100 <= -1.1366) | TP: 3.0xATR, SL: 2.0xATR, BE: 1.2R, TTL: 36b
- **Entry Trigger:** `[SELL] (-0.0008 <= velocity_55 <= 0.0004) AND (parkinson_vol >= 0.0007) AND (price_zscore_100 <= -1.1366) | TP: 3.0xATR, SL: 2.0xATR, BE: 1.2R, TTL: 36b`
- **Invalidation Anchor:** `2.0x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:2.8`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7882 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-BTCUSD-R2_029] Autonomous Machine Quant Rule (BTCUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (price_zscore_100 <= -1.1366) AND (parkinson_vol >= 0.0007) AND (-0.0008 <= velocity_55 <= 0.0107) | TP: 2.2xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b
- **Entry Trigger:** `[SELL] (price_zscore_100 <= -1.1366) AND (parkinson_vol >= 0.0007) AND (-0.0008 <= velocity_55 <= 0.0107) | TP: 2.2xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b`
- **Invalidation Anchor:** `0.8x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:2.8`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7882 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-BTCUSD-R5_029] Autonomous Machine Quant Rule (BTCUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (price_zscore_100 <= -1.1366) AND (parkinson_vol >= 0.0007) AND (-0.0008 <= velocity_55 <= 0.0004) | TP: 2.2xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b
- **Entry Trigger:** `[SELL] (price_zscore_100 <= -1.1366) AND (parkinson_vol >= 0.0007) AND (-0.0008 <= velocity_55 <= 0.0004) | TP: 2.2xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b`
- **Invalidation Anchor:** `0.8x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:2.8`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7882 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-XAUUSD-R3_013] Autonomous Machine Quant Rule (XAUUSD BUY) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [BUY] (0.0008 <= norm_atr <= 0.0012) AND (volume_ratio >= 1.6177) AND (accel_3 > 0.0018) | TP: 3.0xATR, SL: 1.5xATR, TTL: 72b
- **Entry Trigger:** `[BUY] (0.0008 <= norm_atr <= 0.0012) AND (volume_ratio >= 1.6177) AND (accel_3 > 0.0018) | TP: 3.0xATR, SL: 1.5xATR, TTL: 72b`
- **Invalidation Anchor:** `1.5x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:2.0`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7656 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-GBPUSD-R4_029] Autonomous Machine Quant Rule (GBPUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (autocorr_lag3 <= -0.3221) AND (velocity_21 >= -0.0001) AND (-2.9992 <= kurtosis_30 <= -2.9837) | TP: 2.2xATR, SL: 2.0xATR, TTL: 48b
- **Entry Trigger:** `[SELL] (autocorr_lag3 <= -0.3221) AND (velocity_21 >= -0.0001) AND (-2.9992 <= kurtosis_30 <= -2.9837) | TP: 2.2xATR, SL: 2.0xATR, TTL: 48b`
- **Invalidation Anchor:** `2.0x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:1.1`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 8004 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-BTCUSD-R2_006] Autonomous Machine Quant Rule (BTCUSD BUY) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [BUY] (0.0008 <= norm_atr <= 0.0014) AND (accel_3 > 0.0023) AND (velocity_8 <= 0.0000) | TP: 2.2xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b
- **Entry Trigger:** `[BUY] (0.0008 <= norm_atr <= 0.0014) AND (accel_3 > 0.0023) AND (velocity_8 <= 0.0000) | TP: 2.2xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b`
- **Invalidation Anchor:** `0.8x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:2.8`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7882 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-BTCUSD-R5_005] Autonomous Machine Quant Rule (BTCUSD BUY) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [BUY] (velocity_8 <= 0.0000) AND (0.1337 <= autocorr_lag5 <= 0.2202) AND (0.0008 <= norm_atr <= 0.0014) | TP: 1.8xATR, SL: 1.5xATR, BE: 2.0R, TTL: 24b
- **Entry Trigger:** `[BUY] (velocity_8 <= 0.0000) AND (0.1337 <= autocorr_lag5 <= 0.2202) AND (0.0008 <= norm_atr <= 0.0014) | TP: 1.8xATR, SL: 1.5xATR, BE: 2.0R, TTL: 24b`
- **Invalidation Anchor:** `1.5x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:1.2`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7882 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-XAUUSD-R2_020] Autonomous Machine Quant Rule (XAUUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (accel_3 > 0.0018) AND (-1.3137 <= vol_regime_z <= 0.0245) AND (velocity_8 <= 0.0005) | TP: 1.8xATR, SL: 1.8xATR, BE: 1.2R, TTL: 48b
- **Entry Trigger:** `[SELL] (accel_3 > 0.0018) AND (-1.3137 <= vol_regime_z <= 0.0245) AND (velocity_8 <= 0.0005) | TP: 1.8xATR, SL: 1.8xATR, BE: 1.2R, TTL: 48b`
- **Invalidation Anchor:** `1.8x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:1.0`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7656 OOS bars with zero narrative bias.*

### 🟢 [SETUP-QUANT-XAUUSD-R5_006] Autonomous Machine Quant Rule (XAUUSD SELL) (Machine-Discovered Quant)
- **Description:** Autonomous pure mathematical state-space model: [SELL] (vwap_deviation_z > 0.4269) AND (0.0009 <= norm_atr <= 0.0014) AND (skewness_30 > -1.2330) | TP: 4.5xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b
- **Entry Trigger:** `[SELL] (vwap_deviation_z > 0.4269) AND (0.0009 <= norm_atr <= 0.0014) AND (skewness_30 > -1.2330) | TP: 4.5xATR, SL: 0.8xATR, BE: 1.2R, TTL: 48b`
- **Invalidation Anchor:** `0.8x ATR dynamic trailing/stop`
- **Mandated Minimum R:R:** `1:5.6`
- **Stop Buffer Requirement:** `Per Active Playbook`
> **Supervisory Audit Verdict:** PASSED_WALK_FORWARD_CROSS_VALIDATION | *Walk-forward verified on 7656 OOS bars with zero narrative bias.*

### 🟢 [SETUP-ARCH-015] NY Open One-Sided Trend Continuation Sweep (Gold) (NY Session Trend Continuation)
- **Description:** Following a clean one-sided London expansion beyond Asian Range (without dual-sweep of the opposite Asian boundary) and H1 close aligned with H1 EMA(50), a counter-trend pullback >=45% of the London leg sets up a dynamic DST NY Open (08:00 NY to NYSE +1h) 5M stop-hunt rejection bar (>=25% wick, closing aggressively in trend direction).
- **Entry Trigger:** `Close of confirmed 5M NY stop-hunt continuation bar aligned with H1 EMA(50) and one-sided London trend.`
- **Invalidation Anchor:** `Sweep wick extreme of the 5M NY continuation bar plus $1.50 structural buffer ($1.80-$20.00 risk bounds).`
- **Mandated Minimum R:R:** `1:2.5`
- **Stop Buffer Requirement:** `5M NY continuation sweep extreme +/- $1.50 (clamped within $1.80-$20.00 risk at 0.01 lot).`
> **Supervisory Audit Verdict:** RATIFIED | *Zero-lookahead 17-month validation on Gold (XAUUSD_o): 89 trades across 2026 M1 (57tr, +16.85R, PF 1.56) and 2025 H2 OOS (32tr, +8.60R, PF 1.54); combined +25.45R, 32.6% WR, PF 1.55, MaxDD 5.00R at 2.5R target / 1.5R BE. Remains profitable under $0.25 extra slippage (+24.71R, PF 1.54) and 30m limit order (+21.32R, PF 1.46). NOTE: Gated to Long-Only during Macro Bullish regimes; Short continuations suppressed to prevent counter-trend friction.*

### 🟢 [SETUP-ARCH-016] Intermarket SMT Correlation Divergence (NQ vs SPX/YM) (Intermarket Correlation Divergence)
- **Description:** High-conviction non-confirmation divergence where NQ sweeps Asian or London extremes while SPX or YM holds a structural swing pivot (higher low / lower high), confirmed by M5 FVG displacement >= 20.0 pts back inside the reference range. Synchronized Liquidation Veto suppresses signals if all 3 benchmarks sweep simultaneously.
- **Entry Trigger:** `Limit order at M5 FVG proximal boundary following non-confirmation divergence.`
- **Invalidation Anchor:** `NQ sweep extreme wick +/- 8.0 pts buffer.`
- **Mandated Minimum R:R:** `1:2.5`
- **Stop Buffer Requirement:** `Sweep extreme +/- 8.0 points on NQ (Max risk 60.0 pts).`
> **Supervisory Audit Verdict:** RATIFIED | *Verified in MetaTrader 5 (LiteFinance) and 2026 M1 tick data: 15 orders, 11 fills, 5W-3L-3BE (62.5% decisive WR), +9.17R Net Alpha, PF 4.06, Max DD 2.00R. Synchronized Liquidation Veto successfully prevented 100% of counter-trend trap entries during aggressive macro selloffs.*

### 🟢 [SETUP-ARCH-017] Multi-Asset Institutional 15m Opening Range Breakout Continuation (ORB) (Opening Range Breakout & Momentum Expansion)
- **Description:** High-momentum breakout of the 15-minute Opening Range established during the London Cash Open or NYSE Cash Open across NQ, XAUUSD, GBPUSD, SPX, YM. Requires M5 body displacement, volume expansion >= 1.15x 20-bar moving average, and remaining ADR headroom <= 75%. Direction is governed symmetrically by the prior H1/D1 Macro Regime: Bullish Trend -> LONG ONLY; Bearish Trend -> SHORT ONLY; Range-Bound / Chop -> VETOED. Enforces Prop Firm Dynamic Limit Entry Retracement.
- **Entry Trigger:** `Limit order at the retest of the broken 15m Opening Range boundary (dynamically adjusted if risk exceeds $10.00).`
- **Invalidation Anchor:** `Opposite extreme of the breakout displacement bar or IB midpoint (risk clamped to account budget).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Displacement bar extreme +/- buffer (Gold $1.20, Forex 4 pips, NQ 6.0 pts).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified multi-asset across 1-Year (2025-2026) backtest: 556 trades, 34.2% WR, +345.50R Net Alpha, PF 3.17. Gold: +171.30R (PF 4.26). NQ: +95.00R (PF 1.73). GBPUSD: +79.20R (PF 1.48). Directionally symmetric: Longs +182.20R, Shorts +163.30R. Combined with dynamic limit retracement for prop firm compliance.*

### 🟢 [SETUP-ARCH-018] Multi-Asset Statistical Extreme Judas Swing Reversal (Judas Reversal in Range) (Statistical Mean Reversion & Liquidity Sweep)
- **Description:** Fading liquidity sweeps that penetrate Asian High/Low or Prior Day High/Low during London/NY Judas window with candle rejection (wick >= 35%, body <= 40%) across XAUUSD, GBPUSD, NQ, SPX, YM. Strictly gated to RANGE_BOUND and TRANSITION regimes. Vetoed in heavy runaway trends to prevent counter-trend knife catching. Enforces Prop Firm Dynamic Limit Entry Retracement.
- **Entry Trigger:** `Retest limit order at the swept boundary or market on close of rejection candle (dynamically adjusted if risk exceeds $10.00).`
- **Invalidation Anchor:** `Sweep wick extreme +/- asset buffer ($1.20 Gold, 4 pips FX, 6.0 pts NQ).`
- **Mandated Minimum R:R:** `1:2.5`
- **Stop Buffer Requirement:** `Sweep extreme +/- buffer ($1.20 Gold, 4 pips FX, 6.0 pts NQ).`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified multi-asset across 1-Year (2025-2026) backtest: 844 trades, 30.9% WR, +343.14R Net Alpha, PF 2.11. Gold: +141.09R (PF 2.09). NQ: +152.50R (PF 2.46). GBPUSD: +49.55R (PF 1.20). Directionally symmetric: Longs +177.21R, Shorts +165.93R. Successfully eliminates knife-catching by vetoing all counter-trend fades when H1 ADX >= 22.*

### 🟢 [SETUP-ARCH-019] Gold Double Sweep Displacement Reversal (Secondary Stop-Hunt Reversal) (Cascade Liquidity Sweep & Displacement Reversal)
- **Description:** Institutional secondary stop-hunt and trapped breakout reversal strictly on Gold (XAUUSD). Price sweeps a prominent high/low (H0/L0) from a prior leg, pulls back by at least $1.20 forming an intermediate swing level (L_mid/H_mid), pushes again to sweep the new high/low (H2 > H1 or L2 < L1) with a rejection wick >= 25% or close back inside, and immediately prints an opposing 5M Fair Value Gap (FVG) and Market Structure Shift (MSS) through L_mid/H_mid. Active during London Open through NY Open Killzones. Enforces Prop Firm Dynamic Limit Entry Retracement.
- **Entry Trigger:** `Limit order at the 50% equilibrium of the opposing displacement 5M FVG (dynamically adjusted if risk exceeds $10.00).`
- **Invalidation Anchor:** `Secondary sweep extreme (H2/L2) +/- $1.20 Gold spread buffer (risk clamped to $1.50 - $10.00).`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Secondary sweep extreme +/- $1.20 Gold spread buffer.`
> **Supervisory Audit Verdict:** RATIFIED | *Ratified on Gold across 2026 dataset: 235 fills, +41.50R Net Alpha, PF 1.25 to 1.76 (London & NY Killzones). Captures trapped breakout liquidity following false double-top expansions with confirmed MSS through intermediate low/high.*

---
## ⏳ Candidate Archetypes Under Review / Proposed

| ID | Name | Category | Status | Proposed Trigger |
| :--- | :--- | :--- | :---: | :--- |
| `SETUP-ARCH-009` | Pro-Trend Session Breakdown Origin Retest (NY AM Trend Continuation) | Pro-Trend POI Mitigation & Trend Continuation | **DECOMMISSIONED** | M1 retracement into the displacement FVG / Breaker following confirmed M1 MSS at the London breakdown/breakout origin zone. |
| `SETUP-ARCH-011` | Nested Double MSS (Macro Shift + Pullback Exhaustion Shift) | Structural Shift & Complex Pullback Exhaustion | **DECOMMISSIONED** | Limit order at H3 breaker retest or newly formed displacement FVG at L5. |