# TradingGuard Quantitative Alpha Research - New Model Specifications (2026)
**Author:** Senior Quantitative Alpha & Pattern Discovery Researcher (`@miner`)  
**Audience:** Institutional Quantitative Backtest Auditor (`@auditor`), Senior Microstructure Optimizer (`@optimizer`)  
**Status:** Strategy Specification Ready for Zero-Lookahead Audit  
**Date:** November 14, 2026  

---

## Executive Summary & Vulnerability Analysis
Recent live execution and replay audits highlighted a critical systemic vulnerability: **counter-trend entries during high-volume liquidation expansion runs** (e.g., naive swing low sweep fades getting run over on -3.0 sigma trend days).

To solve this, three orthogonal, mathematically precise quantitative models are formulated:
1. **Model 1 (`MODEL-ISB-PC-01`)**: Institutional Session Breakout & Pullback Continuation (filters with ADR and H1/H4 EMA trend alignment to capture high-volume trend expansion).
2. **Model 2 (`MODEL-SE-JSR-02`)**: Statistical Extreme Judas Swing Reversal (eliminates premature knife-catching by enforcing Z-score / ATR band exhaustion, bounded penetration, rejection candle footprints, and Bar T+1 MSS confirmation).
3. **Model 3 (`MODEL-SMT-CD-03`)**: Intermarket SMT Correlation Divergence (exploits institutional non-confirmation across correlated asset pairs: XAUUSD vs XAGUSD, NQ vs SPX/YM, GBPUSD vs EURUSD to mathematically distinguish absorption sweeps from synchronized liquidation runs).

---

## Model 1: Institutional Session Breakout & Pullback Continuation (`MODEL-ISB-PC-01`)

### 1. Target Instruments & Asset Physics
- **Instruments**: `XAUUSD_o`, `GBPUSD_o`, `NQ`
- **Spread Assumptions**: Gold: `$0.22` ($22 pts) | GBPUSD: `0.6 pips` ($0.00006) | NQ: `1.0 pt`
- **Commission**: `$0.10` per 0.01 lot ($10.00 / standard lot)
- **Slippage**: `$0.05` on Gold, `0.1 pip` on GBPUSD, `0.25 pt` on NQ

### 2. Macro Structural Gates (Zero-Lookahead Causal Filters)
1. **H1 EMA50 Trend Alignment**:
   - Evaluated strictly on the latest closed H1 bar prior to signal time:
     - **Bullish Gate**: $Close_{H1} > EMA50_{H1}$ AND $EMA50_{H1, closed} > EMA50_{H1, closed-5}$ (positive slope).
     - **Bearish Gate**: $Close_{H1} < EMA50_{H1}$ AND $EMA50_{H1, closed} < EMA50_{H1, closed-5}$ (negative slope).
2. **ADR Headroom Constraint**:
   - $ADR_{14} = \frac{1}{14}\sum_{k=1}^{14} TrueRange_{D1, -k}$
   - Real-time consumed range at signal bar $T$: $Range_{consumed}(T) = \max_{t \le T}(High_t) - \min_{t \le T}(Low_t)$
   - **Exhaustion Gate**: $\frac{Range_{consumed}(T)}{ADR_{14}} \le 0.70$ (Max 70% ADR consumed). Breakouts triggered after $\ge 70\%$ ADR consumption are strictly suppressed.

### 3. Session Windows (Dynamic Seasonal Clock via `session_clock.py`)
- **London Breakout Window** (Breaks Asian Range: 00:00 UTC to London Open):
  - Summer (BST / EDT): `07:00 UTC - 09:30 UTC` (`10:30 - 13:00 Tehran`)
  - Winter (GMT / EST): `08:00 UTC - 10:30 UTC` (`11:30 - 14:00 Tehran`)
- **NY Breakout Window** (Breaks London Range):
  - Gold & GBPUSD:
    - Summer: `12:00 UTC - 14:30 UTC` (`15:30 - 18:00 Tehran`)
    - Winter: `13:00 UTC - 15:30 UTC` (`16:30 - 19:00 Tehran`)
  - NQ (NYSE Cash Open Opening Range Breakout):
    - Summer: `13:45 UTC - 16:00 UTC` (`17:15 - 19:30 Tehran`)
    - Winter: `14:45 UTC - 17:00 UTC` (`18:15 - 20:30 Tehran`)

### 4. Mathematical Trigger & Acceptance (M5 Bar T)
- **Benchmark Level**: $Benchmark_{High} = \max_{t \in SessionPrior}(High_t)$, $Benchmark_{Low} = \min_{t \in SessionPrior}(Low_t)$
- **Decisive Acceptance Threshold**:
  - Gold (`XAUUSD_o`): $Close_T \ge Benchmark_{High} + \$0.50$ (Long) OR $Close_T \le Benchmark_{Low} - \$0.50$ (Short).
  - GBPUSD (`GBPUSD_o`): $Close_T \ge Benchmark_{High} + 0.0003$ (Long) OR $Close_T \le Benchmark_{Low} - 0.0003$ (Short).
  - NQ: $Close_T \ge Benchmark_{High} + 5.0\text{ pts}$ (Long) OR $Close_T \le Benchmark_{Low} - 5.0\text{ pts}$ (Short).
- **Candle Footprint Quality**:
  - Body Ratio: $\frac{|Close_T - Open_T|}{High_T - Low_T} \ge 0.55$ (Institutional expansion body).
  - Breakout Wick Ratio: $\le 0.25$ (Upper wick $\le 0.25 \times Range$ for Longs; Lower wick $\le 0.25 \times Range$ for Shorts).
- **Displacement Magnitude**:
  - $Range_T = High_T - Low_T \ge 1.2 \times ATR_{14, M5}$ (or $\ge \$2.00$ on Gold, $\ge 12\text{ pips}$ on Cable, $\ge 25\text{ pts}$ on NQ).

### 5. Execution & Retest Mechanics (Bar T+1)
- **Extension Confirmation**: Bar T+1 must pierce Bar T extreme ($High_{T+1} > High_T$ for Longs; $Low_{T+1} < Low_T$ for Shorts).
- **Limit Order Entry**:
  - Long: $BuyLimit = \max(Benchmark_{High}, Open_T)$ (retest of broken level or Bar T open).
  - Short: $SellLimit = \min(Benchmark_{Low}, Open_T)$.
- **Stop Loss**:
  - Long: $SL = Low_T - Buffer$ (Gold: $-\$1.00$, Cable: $-5\text{ pips}$, NQ: $-8.0\text{ pts}$).
  - Short: $SL = High_T + Buffer$ (Gold: $+\$1.00$, Cable: $+5\text{ pips}$, NQ: $+8.0\text{ pts}$).
  - Risk Caps: Gold: $\$3.00 \le SL_{dist} \le \$9.00$ | Cable: $10\text{ pips} \le SL_{dist} \le 22\text{ pips}$ | NQ: $15.0\text{ pts} \le SL_{dist} \le 40.0\text{ pts}$.
- **Target & Trade Management**:
  - Take Profit: **3.0R** (Auditor to test grid: `[2.0R, 2.5R, 3.0R, 3.5R]`).
  - Breakeven Ratchet: Dynamic ratchet at **+1.8R** peak excursion (move SL to $Entry + Spread$).
  - Order Inactivity TTL: 60 minutes.

---

## Model 2: Statistical Extreme Judas Swing Reversal (`MODEL-SE-JSR-02`)

### 1. Target Instruments & Asymmetric Bias
- **Instruments**:
  - `XAUUSD_o`: Bearish Judas Breaker priority (SHORT after Asian/London High sweep).
  - `GBPUSD_o`: London Open Judas Swing (Both directions).
  - `NQ`: London Open & NYSE Cash Open Judas Reversal.

### 2. Statistical Stretch & Exhaustion Filter (Zero Naive Fading)
1. **Session Anchored VWAP & Z-Score**:
   - $VWAP(t) = \frac{\sum_{i=1}^t TypicalPrice_i \times Volume_i}{\sum_{i=1}^t Volume_i}$
   - Rolling Standard Deviation: $\sigma(t) = \sqrt{\frac{\sum_{i=1}^t Volume_i \times (TypicalPrice_i - VWAP(t))^2}{\sum_{i=1}^t Volume_i}}$
   - Z-Score: $Z(t) = \frac{Close_t - VWAP(t)}{\sigma(t)}$
   - **Exhaustion Gate**:
     - Short Setup: $Z(t) \ge +2.00$ (Overbought statistical stretch).
     - Long Setup: $Z(t) \le -2.00$ (Oversold statistical stretch).
2. **Alternative Dynamic ATR Stretch**:
   - Distance from M5 20 EMA $\ge 2.2 \times ATR_{14, M5}$.
3. **Daily ADR Exhaustion Context**:
   - $Range_{consumed} \ge 0.75 \times ADR_{14}$ confirms climactic sweep regime.

### 3. Liquidity Sweep Benchmark & Penetration Physics
- **Swept Levels**: Prior Day High/Low (PDH/PDL) or Prior Session High/Low (Asian High/Low during London, London High/Low during NY).
- **Penetration Depth Boundaries**:
  - Gold: $\$0.30 \le Penetration \le 0.80 \times ATR_{14, M5}$ (typically $\$0.30 \le Depth \le \$2.50$).
  - Cable: $3\text{ pips} \le Penetration \le 15\text{ pips}$.
  - NQ: $5.0\text{ pts} \le Penetration \le 25.0\text{ pts}$.
  - **Runaway Blowout Veto**: If penetration $> 1.0 \times ATR_{14, M5}$, cancel setup immediately (orderflow runaway, do NOT fade).

### 4. Candle Footprint & Reversal MSS Trigger
- **Absorption Footprint (Bar T)**:
  - Rejection Wick Ratio: $\frac{UpperWick_T}{Range_T} \ge 0.40$ (for High sweep) or $\frac{LowerWick_T}{Range_T} \ge 0.40$ (for Low sweep).
  - Body Ratio: $\le 0.35$.
  - Close Location: $Close_T \le Benchmark_{High} + \$0.40$ (Gold) / $+2\text{ pips}$ (Cable) / $+3.0\text{ pts}$ (NQ).
- **Mandatory Bar T+1 Follow-Through (Micro MSS)**:
  - Short Setup: Bar T+1 must close strictly BELOW Bar T low ($Close_{T+1} < Low_T$).
  - Long Setup: Bar T+1 must close strictly ABOVE Bar T high ($Close_{T+1} > High_T$).

### 5. Execution & Target Geometry
- **Entry**: Limit order at Bar T+1 Close, or limit at Bar T Midpoint ($Entry = \frac{High_T + Low_T}{2}$).
- **Stop Loss**:
  - Short: $SL = High_T + Buffer$ (Gold: $+\$1.20$, Cable: $+4\text{ pips}$, NQ: $+6.0\text{ pts}$).
  - Long: $SL = Low_T - Buffer$ (Gold: $-\$1.20$, Cable: $-4\text{ pips}$, NQ: $-6.0\text{ pts}$).
- **Take Profit**: **2.0R** (Mean-reversion back to Session VWAP / Equilibrium; test grid `[1.5R, 2.0R, 2.5R]`).
- **Breakeven Ratchet**: $+1.2R$ peak excursion moves SL to $Entry + Spread$.
- **Order Inactivity TTL**: 45 minutes.

---

## Model 3: Intermarket SMT Correlation Divergence (`MODEL-SMT-CD-03`)

### 1. Target Instruments & Correlation Triads
- **Pair A (Precious Metals)**: `XAUUSD_o` (Gold, Executing) vs `XAGUSD_o` (Silver, Radar).
- **Pair B (US Equities)**: `NQ` (Nasdaq 100, Executing) vs `SPX` / `YM` (S&P 500 / Dow Jones, Radar).
- **Pair C (Forex)**: `GBPUSD_o` (Cable, Executing) vs `EURUSD_o` (Euro, Radar).

### 2. SMT Divergence Mathematical Specification
- Let $A$ be the Executing Asset and $B$ be the Correlated Radar Asset.
- **Bullish SMT Divergence (Institutional Accumulation)**:
  - Condition: $Low_A(t) < BenchmarkLow_A - \delta_A$ (Asset A sweeps session low).
  - AND: $Low_B(t) \ge BenchmarkLow_B + \delta_B$ (Asset B fails to break low, holding a Higher Low).
  - **Synchronized Liquidation Veto**: If BOTH $A$ and $B$ break below benchmark lows simultaneously, SMT is **FALSE**. The trade is strictly suppressed (confirms market-wide liquidation run).
- **Bearish SMT Divergence (Institutional Distribution)**:
  - Condition: $High_A(t) > BenchmarkHigh_A + \delta_A$ (Asset A sweeps session high).
  - AND: $High_B(t) \le BenchmarkHigh_B - \delta_B$ (Asset B fails to break high, holding a Lower High).
  - **Synchronized Breakout Veto**: If BOTH $A$ and $B$ break above benchmark highs simultaneously, trade is strictly suppressed.

### 3. Displacement & FVG Trigger
- Within 15 minutes (3 M5 bars) following SMT detection, Executing Asset $A$ must print a directional displacement candle forming a valid M5 Fair Value Gap (FVG):
  - Bullish FVG: $Low_{bar} > High_{bar-2}$.
  - Bearish FVG: $High_{bar} < Low_{bar-2}$.
  - Minimum Displacement: Gold $\ge \$1.50$ | Cable $\ge 10\text{ pips}$ | NQ $\ge 20.0\text{ pts}$.

### 4. Execution & Geometry
- **Entry**: Limit order placed at the proximal edge of the confirmed M5 FVG ($BuyLimit = High_{bar-2}$; $SellLimit = Low_{bar-2}$).
- **Stop Loss**: Placed strictly behind the swept swing extreme of Asset A:
  - Long: $SL = Low_{A, sweep} - Buffer$ (Gold: $-\$1.50$, Cable: $-5\text{ pips}$, NQ: $-8.0\text{ pts}$).
  - Short: $SL = High_{A, sweep} + Buffer$ (Gold: $+\$1.50$, Cable: $+5\text{ pips}$, NQ: $+8.0\text{ pts}$).
- **Take Profit**: **3.0R to 3.5R** (Targeting opposing liquidity pool; test grid `[2.5R, 3.0R, 3.5R]`).
- **Breakeven Ratchet**: $+1.8R$ peak excursion moves SL to $Entry + Spread$.
- **Order TTL**: 60 minutes.

---

## Instructions for Institutional Backtest Auditor (`@auditor`)
1. **Data Files to Use**:
   - Gold: `backtest_results/cache/M1_XAUUSD_o_2026.parquet`
   - Cable: `backtest_results/cache/M1_GBPUSD_o_2026.parquet`
   - NQ: `backtest_results/cache/NQ_M1_EXTENDED_2026.parquet` (and `NQ_M1_SUMMER_2026.parquet`)
   - SPX/YM: `backtest_results/cache/SPX_M1_2026.parquet`, `backtest_results/cache/YM_M1_2026.parquet`
2. **Broker Trading Mechanics**:
   - Spread: `$0.22` Gold, `0.6 pip` GBPUSD, `1.0 pt` NQ.
   - Commission: `$0.10` / 0.01 lot.
   - Slippage: `$0.05` Gold, `0.1 pip` GBPUSD, `0.25 pt` NQ.
   - Bar-by-bar M1 collision resolution with strict SL-first rule if both SL and TP are hit on the same closed bar.
3. **Audit Metrics Required**:
   - Total Trades ($N$), Wins ($W$), Losses ($L$), Breakeven ($BE$), Expired ($Exp$).
   - Win Rate %, Net Realized PnL ($USD$), Net Realized $R$, Profit Factor ($PF$), Expected Value $E[R]$.
   - Max Drawdown ($R$ and $USD$), Statistical $t$-statistic.
   - Session breakdown (London Open vs NY Open).
4. **Post Findings**: Post unvarnished results to the board addressed to `@optimizer`.
