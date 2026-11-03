# 🏛️ TradingGuard Ratified Setup Archetype Registry
**Last Calibration:** `2026-11-01T14:25:53.182299` | **Version:** `1.0.0`

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
> **Supervisory Audit Verdict:** RATIFIED | *Authorized for active execution across MULTI portfolio assets. Execution is strictly conditioned on confirmed HTF liquidity run prior to 5M FVG creation during designated high-volume session windows (London & NY Open). Limit orders must verify spread normalization prior to routing.*

### 🟢 [SETUP-ARCH-003] Confirmed Market Structure Shift (MSS) Breaker Retest (Structural Shift & Breaker Retest)
- **Description:** Displacement through opposing swing pivot establishing a Breaker Block, followed by a retest.
- **Entry Trigger:** `Limit order at Breaker Block proximal boundary.`
- **Invalidation Anchor:** `Opposing swing extreme or Breaker distal boundary.`
- **Mandated Minimum R:R:** `1:3.0`
- **Stop Buffer Requirement:** `Max(2.0 pips + 1.2x Current Spread, 0.25x M15 ATR) beyond the breaker distal boundary or originating swing pivot`
> **Supervisory Audit Verdict:** RATIFIED | *The structural transition of failed order flow into a breaker block demonstrates robust statistical expectancy and distinct institutional footprints under NY liquidity conditions. Deployment authorized strictly with candle-body displacement confirmation and mandated spread-adjusted buffers.*

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

---

### [SETUP-ARCH-008] HTF Liquidity Sweep with LTF (M1) Market Structure Shift & Displacement Retest
* **Category:** HTF Liquidity Purge & LTF Execution Confirmation
* **Context:** Active Killzone windows (London Open, NY Open). Price purges a critical Higher-Timeframe liquidity boundary (Previous Day High/Low [PDH/PDL], Previous Week High/Low [PWH/PWL], or Asian Extremes).
* **Execution Trigger:** Transition from HTF to 1-Minute (M1) timeframe upon sweep. Require an M1 Market Structure Shift (MSS) featuring an energetic displacement body close breaking the preceding micro-swing pivot. Enter upon 50%-62% FVG / mitigation retest (Mean Threshold or OTE).
* **Invalidation Anchor:** Pinned strictly beyond the HTF sweep peak wick + asset-specific spread buffer (1.0 pip for GBPUSD; 1.5–2.5 pips for EURUSD).
* **Target Anchor:** Anchored to opposing major HTF liquidity pool (e.g. Session Lows, PDL, or opposing 15M/1H FVG) per `RULE-TARGET-037`.
* **Minimum R:R:** Mandatory >= 1:3.0.
* **Status:** **RATIFIED**
> **Supervisory Audit Verdict:** RATIFIED | *Initiated and proven by Lead Human Partner (Seat #7) on Monday, September 21, 2026 Cable NY Open sweep (PDH 1.33982 swept to 1.34003; M1 MSS at 1.33925; entry at 1.33933 with 7.8 pip stop at 1.34011; TP hit at 1.33686 for +24.7 pips / 3.17R). Eliminates premature blind sweep fills and delivers pristine R:R asymmetry.*

---

### [SETUP-ARCH-009] Pro-Trend Session Breakdown Origin Retest (NY AM Trend Continuation)
* **Category:** Pro-Trend POI Mitigation & Trend Continuation
* **Context:** Active New York session (15:30–17:30 Tehran / 08:00–10:00 NY). Prior session (London) generated a strong impulse expansion (>30 pips). Macro Directional Filter is strictly aligned (SELL_ONLY or BUY_ONLY).
* **Execution Trigger:** Bypasses external sweep requirements; detects internal retracement into the unmitigated origin of the prior session breakdown/breakout (Breaker Block, 15M/1H FVG, or 50% Mean Threshold). Drops to 1-Minute (M1) chart to confirm an energetic Market Structure Shift (MSS) displacement body close breaking counter-trend micro-pivot. Enters on the 50%-62% M1 FVG retest.
* **Invalidation Anchor:** Retracement swing peak wick + asset spread buffer (1.0 pip for GBPUSD; 1.5–2.5 pips for EURUSD).
* **Target Anchor:** Daily Session Extremes (e.g. London Low 1.3326) and opposing HTF expansion targets per RULE-TARGET-037. Minimum R:R >= 1:3.0.
* **Status:** **RATIFIED**
> **Supervisory Audit Verdict:** RATIFIED | *Initiated and proven collaboratively on Tuesday, September 22, 2026 Cable NY retracement (London dump from 1.3387 to 1.3326; NY retracement into London breakdown origin at 1.3368–1.3373; M1 MSS trigger at 1.33685 with 6.1 pip stop; dump to 1.33215 yielding +45 pips / 6.9R). Eliminates the mid-range chop blind spot on trend continuation days.*

### 10. Prominent Liquidity Sweep with Pro-Trend M1 MSS Displacement (SETUP-ARCH-010)
* **Category**: Pro-Trend Prominent Sweep & LTF Execution
* **Status**: **RATIFIED**
* **Proposer**: Lead Discretionary Trader & Human Partner (Seat #7)
* **Description**: High-conviction trend continuation archetype executing exclusively in the direction of the confirmed HTF trend (Daily/4H). When price sweeps a visually prominent horizontal liquidity ceiling or floor (Equal Highs/Lows [EQH/EQL], Previous Day High/Low [PDH/PDL], or Prior Session Extreme), it bypasses deep HTF retracement requirements. Execution is triggered when price prints an immediate 1-Minute (M1) Market Structure Shift (MSS) with an energetic displacement candle body closing past the micro-swing pivot in the pre-determined trend direction. Entry is placed on the M1 FVG / Breaker retest or immediate execution upon M1 MSS close.
* **Entry Trigger**: M1 MSS displacement candle body close in pre-determined trend direction, followed by retest of M1 FVG / Breaker origin.
* **Invalidation Anchor**: Extreme of the prominent sweep wick + 1.0 pip spread buffer (GBPUSD) / 1.5-2.5 pips (EURUSD).
* **Mandatory Minimum R:R**: 1:3.0 targeting the next major HTF liquidity pool or session extreme.
* **Auditor Notes**: Ratified collaboratively with Lead Human Partner (Seat #7). Designed specifically to capture runaway trend expansions (such as September 11 Equal Highs sweep and September 16 PDH sweep) without demanding deep 50% HTF retracements. By locking invalidation to the M1 sweep wick, dollar risk remains strictly within the  cap while providing 1:3R to 1:6R+ asymmetry.
