# TradingGuard HITL & Trading Bot Audit (2026-11-18)

A technical audit of the `hitl/` trading bot pipeline—covering order execution, risk math, watchdog management, SMC/Quant signal generation, and timezone/DST handling—based on direct inspection of the codebase.

---

## How the Bot Currently Trades (3 Paths)

1. **Autonomous SMC Pipeline (`hitl/watchdog.py` → `hitl/live_radar.py` → `hitl/screener_gate.py` / `hitl/backtest/fast_screener.py` → `hitl/council.py` → `hitl/tools/smc_tools.py` → `hitl/mt5_engine.py`)**
   - `MarketWatchdog.poll()` runs every 3s and invokes `LiveMarketRadar.poll()` every 15s.
   - During active killzones (`hitl/backtest/session_clock.py`), `LiveMarketRadar.scan_symbol()` scans `GBPUSD`, `XAUUSD`, and `NQ`.
   - When triggered, a background thread renders 4-TF charts, gates through `screen_ict_session(..., closed_bars_only=True)`, convenes the 3-round AI Council (`agy.exe`), constructs a limit order via `build_validated_order_plan()`, and either **auto-places on Demo** (`is_autonomous=True`) or sends a Telegram approval card (`PENDING_EXECUTION_PLANS`) on **Live Real**.
2. **Autonomous Quant Pipeline (`hitl/quant_engine/live_quant_bridge.py`)**
   - Runs at the top of `LiveMarketRadar.poll()` (every 15s) on `XAUUSD` and `NQ` using ratified statistical rules from `backtest_results/quant_discovery/annual_1year/`.
   - Evaluates closed bar `iloc[-2]` on 5M bars, gates via `AccountRiskManager` (`risk_governor`), and auto-places on Demo or sends an approval card on Live Real.
3. **Manual / On-Demand Telegram Commands (`hitl/bot.py`)**
   - Direct `/buylimit` / `/selllimit`, plus `/chart` (`_chart_worker`) and `/council` (`_council_worker`).
   - `MarketWatchdog` manages all pending orders (momentum/spread cancellation, 75m stale reminder) and open positions (breakeven ratchet, closure detection, cooldowns, daily circuit breaker).

---

## 1. Critical Execution & Risk Calculation Bugs

### A. `LiveMarketRadar` & `bot.py` Discard the Screener’s Entry, SL, Archetype, and Target R:R
- **Where:** `hitl/live_radar.py:358-369`, `hitl/bot.py:250-256`, `hitl/bot.py:390-399`, `hitl/tools/smc_tools.py:313-450`
- **Bug:** `screen_ict_session()` detects a specific ratified archetype (`SETUP-ARCH-001`, `013`, `015`, `017`, `019`, etc.) and returns its exact `entry_ref`, `sl_ref`, `archetype_id`, `recommended_target_rr`, and `recommended_be_rr`.
- Right after the Council finishes, `live_radar.py` and `bot.py` **throw those away** and call `build_validated_order_plan(..., poi_selection="PROXIMAL_EDGE", landmarks=landmarks)`.
- `build_validated_order_plan()` always anchors the entry at the newest 5M FVG (even for Breaker Block, ORB Breakout, Double Sweep, or NY Trend Continuation setups), sets SL to the 15-bar extreme ± `1 pip` (`$0.01` on Gold—smaller than the `$0.22` spread), and forces `min_rr=3.0` via `validate_order_ticket()`.
- `live_radar.py:382` then calls `get_optimal_trade_management(sym, sess_key)` **without `setup_arch_id`**, overwriting archetype-specific R:R/BE rules. `_chart_worker` and `_council_worker` in `bot.py` don't apply `target_rr_cap` or `macro_filter` at all.

### B. `NQ` (Nasdaq 100) Dollar Risk & Point-Size Miscalculation Blocks Every SMC Order and Breaks Watchdog
- **Where:** `hitl/tools/smc_tools.py:42, 255-282`, `hitl/live_radar.py:396`, `hitl/watchdog.py:125, 245`
- **Bugs:**
  1. `get_smc_landmarks()` sets `pip_size = 0.01` for anything that isn't FX or Crypto—treating **`NQ` as Gold**. `validate_order_ticket()` then computes `risk_usd = price_dist * 1.0` (`$1.00/pt`), so a normal 20–40 pt NQ stop calculates as `$20–$40` risk and gets **100% rejected** by the `$12.00` cap (`smc_tools.py:275`).
  2. `MarketWatchdog.check_momentum_and_spread()` (`watchdog.py:125`) cancels any pending order if `sym_info.spread > 50`. On 2-digit brokers (`point = 0.01`), a normal `1.0 pt` NQ spread is `100` points (`> 50`), and `$0.51` Gold spread is `51` points (`> 50`)—causing **immediate auto-cancellation** of valid NQ (and occasionally Gold/BTC) limit orders within 3 seconds of placement.
  3. `MarketWatchdog` BE ratchet (`watchdog.py:245`) hardcodes `digits = 5 if ("EUR" in p.symbol or "GBP" in p.symbol) else 2`, breaking 3-digit instruments (`XAGUSD`, JPY pairs) and 1-digit index feeds.

### C. `MarketWatchdog` Breakeven Ratchet Uses Wrong Policy & Ignores Archetypes/Quant Rules
- **Where:** `hitl/watchdog.py:235-278`, `hitl/backtest/evaluator.py:51-79`
- **Bugs:**
  1. `get_optimal_trade_management(p.symbol, sess_key)` (`evaluator.py:53`) maps any symbol other than `EUR`/`GBP` to **`XAUUSD`**, so `NQ` and `BTCUSD` positions are managed using Gold’s BE policy.
  2. `watchdog.py:240` does not pass `setup_arch_id`, so `SETUP-ARCH-013` (`be_rr=3.0`), `SETUP-ARCH-015` (`be_rr=1.5`), and `SETUP-ARCH-001` (`be_rr=1.2`) never get their calibrated BE ratchet.
  3. Quant positions placed by `LiveQuantBridge` have their own `rule.be_ratchet_r` (e.g., `2.0R`) and `rule.ttl_bars` (`24` bars = 120m), which are never stored or enforced; `Watchdog` overrides them with SMC's session BE policy and 75m TTL reminder.
  4. If a session rolls into `NY_Silver_Bullet` (`breakeven_rr: null` in `hitl/memory/optimal_trade_management_policy.json`) or `Outside_Killzones` (falls back to `London_Open` in `evaluator.py:72`), the BE rule changes mid-trade.

### D. `MT5Engine.get_daily_performance()` Timezone & Net-Loss Bugs
- **Where:** `hitl/mt5_engine.py:166-191`
- **Bugs:**
  1. `mt5.history_deals_get(midnight, ...)` passes naive local Windows/Tehran midnight (`datetime.datetime.now()`). MT5 expects broker server time (EET/EEST), so Tehran `00:00` (`20:30` server time in winter) pulls **previous day's NY deals** into today's `daily_loss` and `consecutive_losses`.
  2. `AccountRiskManager.sync_state()` (`hitl/account_risk_manager.py:212-215`) relies on `get_daily_performance()["realized_pnl"]` to anchor `daily_reference_equity`, propagating that skew.
  3. `mt5_engine.py:188` checks `if ct.profit < 0:` without including `commission`, `swap`, and `fee`—so a breakeven trade that is net negative after commission isn't counted as a loss, while a `-0.01` raw profit trade is.

### E. `bot.py` Chart/Council Workers Have Broken Order-Plan Schema & Undefined `landmarks`
- **Where:** `hitl/bot.py:250, 277-285, 420-428, 1079-1086`
- **Bugs:**
  1. In `_chart_worker` (`bot.py:250`), `landmarks` is only assigned inside `if not media_items:` (MT5 fallback). Whenever TradingView Chrome capture succeeds, `landmarks` is undefined, so **no order plan is ever built**.
  2. In both `_chart_worker` (`bot.py:277`) and `_council_worker` (`bot.py:420`), `PENDING_EXECUTION_PLANS[plan_id]` stores a nested `"plan": plan` dict instead of flat `"entry"`, `"sl"`, `"tp"`, `"lot"` keys, and omits the `"Approve & Place"` button on Live Real accounts. Triggering `exec_plan_` on those plans would raise `KeyError: 'entry'`.

### F. `MT5Engine.place_limit_order()` & `AccountRiskManager` Edge Cases
- **Where:** `hitl/mt5_engine.py:360-371`, `hitl/account_risk_manager.py:356`
- **Issues:**
  - Hardcodes `"type_filling": mt5.ORDER_FILLING_RETURN` instead of inspecting `symbol_info.filling_mode`, and doesn't snap `price`/`sl`/`tp` to `symbol_info.trade_tick_size` / `digits`.
  - `AccountRiskManager.evaluate_order_feasibility()` (`line 356`) computes `projected_daily_dd_pct` from `daily_loss_usd + risk_usd`, ignoring remaining SL distance on already-open positions that haven't hit SL yet.
  - Multiple modules (`live_radar.py`, `bot.py`, `screener_gate.py`, `council.py`) instantiate fresh `MT5Engine()` objects across background threads calling `mt5.initialize()` concurrently on a global C-extension state.

---

## 2. Wrong / Mismatched Implementations of Trading Concepts

### A. `LiveQuantBridge` Trades Limit Orders Instead of the Backtested Market Entries
- **Where:** `hitl/quant_engine/live_quant_bridge.py:158-172` vs `hitl/quant_engine/vectorized_backtester.py:173-185`
- **Concept / Implementation Mismatch:**
  - `VectorizedBacktester` backtested and ratified all quant rules as **Market entries on the next bar's open** (`raw_open + spread` for BUY, `raw_open` for SELL).
  - `LiveQuantBridge` places **Limit orders** at `tick.bid - min_offset` (`BUY_LIMIT`) and `tick.ask + min_offset` (`SELL_LIMIT`). Momentum/breakout quant rules will miss fills when price runs away, while adverse reversals fill—creating negative-selection bias vs the backtest.
  - `LiveQuantBridge` also runs in `LiveMarketRadar.poll()` **before** `is_killzone_active()` (`live_radar.py:628-638`), has **no duplicate-exposure check** (unlike the backtester's `if idx <= current_active_exit: continue`), hardcodes `lot=0.01` without pre-checking `$12` risk before sending live cards, and fails `place_limit_order()` outside session hours (spamming failure alerts on Demo).

### B. `detect_breaker_and_mss()` Has Inverted ICT Breaker / MSS Pivot Ordering
- **Where:** `hitl/backtest/fast_screener.py:117-138`
- **Concept Bug:**
  - For a **Bearish Sweep + MSS Reversal** (low → higher high sweeping liquidity → break below prior low), the swing low happens **before** the sweep high (`last_low_idx < last_high_idx`).
  - Requiring `last_high_idx < last_low_idx` does the opposite: it **rejects** true high-sweep reversals and instead fires on `High -> Low -> Lower Low` (chasing a continuation breakdown) using the swing-low candle's high as a "breaker." Same inversion on the Bullish side (`last_low_idx < last_high_idx`).
  - `highs` / `lows` only check 1 neighbor (`idx-1`, `idx+1`), creating noisy micro-pivots.

### C. `detect_fvg_5m()` and `get_smc_landmarks()` Don't Check FVG Mitigation / Invalidation
- **Where:** `hitl/backtest/fast_screener.py:57-76`, `hitl/tools/smc_tools.py:84-103`
- **Concept Bug:** Both scan backwards for the newest 3-candle FVG, but **never check whether subsequent bars already filled or closed through the FVG**. Entering a limit order at an already-mitigated or invalidated FVG is stale. (`range(len(recent) - 1, 2, -1)` in `fast_screener.py:58` also skips `i=2`).

### D. `LiveMarketRadar.scan_symbol()` Pre-Filter Blocks Continuation Setups & Burns Cooldown on Forming Bars
- **Where:** `hitl/live_radar.py:171-206, 265, 287, 644`
- **Concept / Pipeline Mismatch:**
  1. `scan_symbol()` only triggers when price sweeps a session benchmark **and** closes back inside it (`is_bearish_mss` / `is_bullish_mss`). Continuation and breakout setups (`SETUP-ARCH-004`, `015` NY Trend Continuation, `017` ORB Breakout, `003` Breaker Retest) are structurally prevented from ever reaching `screen_ict_session()` in live radar.
  2. `scan_symbol()` evaluates the **forming** bar (`list_5m[-1]`, `list_1m[-1]`) and immediately locks `(sym, side)` on a **30-minute cooldown** (`line 265`). Then `trigger_autonomous_pipeline` calls `screen_ict_session(..., closed_bars_only=True)`, which drops the forming bar (`r5m[:-1]`). If the setup just formed on the live bar, the screener vetoes it—and the 30-minute cooldown prevents re-evaluating it once the bar closes 1–4 minutes later.
  3. `live_radar.py:287` fetches only **60 M5 bars (5 hours)** for `r5m` and passes it to `screen_ict_session()`, truncating Asian and early London ranges needed by `detect_ny_trend_continuation` and `detect_opening_range_breakout` during NY session.

### E. `Watchdog` Momentum Guard Doesn't Match `evaluator.py` Calibration
- **Where:** `hitl/watchdog.py:103-137` vs `hitl/backtest/evaluator.py:390-410`
- **Mismatch:**
  - `evaluator.py` uses `3.5x ATR` for Metals (`XAU`/`XAG`), `2.0x ATR` for FX, and **only cancels if price is within `3.0 * ATR` of entry**.
  - `watchdog.py` uses `2.0x ATR` for all assets (far too sensitive for Gold), includes the forming spike bar inside the 14-period ATR average, and cancels regardless of distance to entry.

### F. `Council` Stale Charts & `macro_bias.py` Forced Directional Bias
- **Where:** `hitl/council.py:204, 339, 346`, `hitl/macro_bias.py:198`
- **Bugs:**
  - `assemble_council_intelligence()` only renders charts if `not all(p.exists())` (`council.py:204`). Running `/council` ("Council Only") sends **old chart images** left on disk from prior sessions.
  - `council.py:339, 346` passes naive Windows local `datetime.datetime.now()` as `broker_time` and `session_hour`.
  - `macro_bias.py:198` sets `execution_filter = "BUY_ONLY"` for Gold whenever `usd_trend == "CONSOLIDATION_RANGE"`, hard-blocking Gold shorts during flat Dollar ranges.

---

## 3. Timezone / DST & Session Window Bugs

1. **`LiveMarketRadar.scan_symbol()` (`hitl/live_radar.py:110-120`)** hardcodes Summer UTC hours (`07:00` London / `12:00` NY). In Winter (Nov–Mar), NY Open is `13:00 UTC` (`16:30 Tehran`), so from `12:00–13:00 UTC` (`15:30–16:30 Tehran`) the radar prematurely switches to NY mode and misclassifies London post-open candles as NY sweeps.
2. **`fast_screener.py` (`lines 1601-1715`)** gates `screen_ict_session()` on hardcoded Tehran integer hours (`9..13`, `14..16`, `17..19`) that **contradict DST** and break ratified detectors:
   - In Winter, `14:00–15:59 Tehran` (`10:30–12:29 UTC`) is **London Killzone**, yet `elif session_hour in (14, 15, 16):` treats it as NY Open and **bans `GBPUSD` and `NQ`**.
   - In Summer, NY Open is `15:30 Tehran` (`hour 15`), yet `detect_ny_trend_continuation` (`SETUP-ARCH-015`) and `detect_opening_range_breakout` (`SETUP-ARCH-017`) are gated inside `elif session_hour in (17, 18, 19):` (`lines 1654-1676`), missing the first 1.5 hours of NY Open in Summer (and London ORB on Gold is killed by `is_lon_continuation` at `line 1623`).
3. **`fast_screener.py:779, 970, 1179, 1318, 1610`** calls `get_broker_utc_offset_seconds()` (which queries live MT5 current tick offset) to convert historical bar timestamps, shifting Summer backtest bars by 1 hour when run during Winter (and vice versa), instead of using `server_epoch_to_zones()` / `Europe/Athens` per bar.
4. **`detect_adr_exhaustion_snapback()` (`fast_screener.py:546`)** checks `curr_dt.hour >= 16` on `_convert_records()` timestamps, which are raw broker server time (EET/EEST), not UTC.

---

## Recommended Fix Plan

1. **Unify Execution Geometry (`live_radar.py`, `bot.py`, `smc_tools.py`)**
   - When `screen_ict_session()` returns a setup (`entry_ref`, `sl_ref`, `archetype_id`, `recommended_target_rr`, `recommended_be_rr`), use those coordinates directly (with broker/tick-size normalization and asset-accurate risk math) instead of overwriting them with `build_validated_order_plan()`’s generic 5M FVG + 15-bar SL.
   - Fix `pip_size` / dollar-per-point calculation in `smc_tools.py` and `live_radar.py` for indices (`NQ`, `SPX`, `YM`) and metals (`XAG`) so `MT5Engine.calculate_risk_usd()` is the single source of truth.
   - Fix `bot.py` `_chart_worker` / `_council_worker` plan schema and always generate fresh `landmarks`.
2. **Fix Watchdog & Daily Performance (`watchdog.py`, `mt5_engine.py`, `evaluator.py`)**
   - Replace `sym_info.spread > 50` with an asset-scaled spread threshold (e.g., `> 3x` `get_default_broker_spread(symbol)`).
   - Align `watchdog.py` momentum ATR check with `evaluator.py` (exclude forming bar from ATR baseline, use `3.5x` for metals / `2.0x` for FX, require `dist_to_entry <= 3.0 * ATR`).
   - Persist `archetype_id` / `be_ratchet_r` / `ttl_minutes` per ticket (e.g., JSON map keyed by MT5 ticket) so `Watchdog` applies the exact BE and TTL for both SMC archetypes and Quant rules—and fix `get_optimal_trade_management()` fallback for `NQ`/`BTCUSD`.
   - Convert `midnight` in `MT5Engine.get_daily_performance()` to broker server time and include `commission + swap + fee` in `consecutive_losses`.
3. **Align `LiveQuantBridge` with `VectorizedBacktester` (`live_quant_bridge.py`)**
   - Either execute next-bar market orders (matching the backtest) or validate/backtest limit-offset execution; add duplicate-exposure gating, killzone/session gating before alerting, and `$12` risk validation.
4. **Fix Screener & DST Session Logic (`fast_screener.py`, `live_radar.py`)**
   - Replace hardcoded UTC/Tehran hours in `live_radar.py` and `fast_screener.py` with `session_clock.get_active_session_status()` / `server_epoch_to_zones()` per bar.
   - Fix `detect_breaker_and_mss()` pivot ordering and `detect_fvg_5m()` / `get_smc_landmarks()` mitigation checks.
   - Evaluate `LiveMarketRadar.scan_symbol()` on closed bars (or remove it as a divergent pre-filter and let `screen_ict_session` be the unified scanner with ≥200 M5 bars), so continuation/ORB setups aren't silently dropped and cooldowns aren't burned on forming bars.
   - Keep `docs/SYSTEM_EXECUTION_MIRROR.md` updated in the same turn when any code changes are made (per `GEMINI.md`).

---

## 4. Setup Detection Bugs & Blind Spots (SMC & Quant Scanners)

Even before an order reaches risk checks or MT5, several ratified strategies are either inverted, silently unreachable in live trading, or mismatched against their backtests.

### 4.1 SMC Bot Setup Detection (`live_radar.py`, `fast_screener.py`, `screener_gate.py`, `metals_smt.py`)

1. **Two-Stage Live Filter Blocks Most Ratified Setups (`hitl/live_radar.py:59-243`)**:
   - `LiveMarketRadar.poll()` only invokes `screen_ict_session()` if `LiveMarketRadar.scan_symbol()` fires first.
   - `scan_symbol()` only triggers on "sweep session extreme + close back inside," so continuation, breakout, and internal-structure setups (`SETUP-ARCH-003`, `004`, `012`, `014`, `015`, `017`, `019`) **cannot trigger** unless price coincidentally pierces the session high/low and closes back inside on that exact candle.
   - `session_high`/`session_low` is computed over the entire session since open (`07:00` or `12:00` UTC), allowing stale sweeps from hours earlier to fire on any later red/green candle.
   - `scan_symbol()` inspects the **forming** bar (`list_5m[-1]`) and immediately locks `(symbol, side)` for **30 minutes** (`line 265`), while `trigger_autonomous_pipeline()` runs `screen_ict_session(..., closed_bars_only=True)` (`line 315`), dropping the forming bar. The screener vetoes the unclosed setup, and the 30-minute cooldown prevents re-checking once the bar closes.
   - `trigger_autonomous_pipeline()` (`line 287`) fetches only **60 M5 bars (5 hours)** for `r5m` and passes that to `screen_ict_session()`, cutting off Asian Range and early London Range during NY session.

2. **SMT & M1 Setups Are 100% Dead in Live Trading (`live_radar.py:309`, `screener_gate.py:95`)**:
   - Neither `LiveMarketRadar.trigger_autonomous_pipeline()` nor `screener_gate.run_screener_gate()` passes `smt_info` or `bars_1m` to `screen_ict_session()`.
   - **`SETUP-ARCH-005`**, **`006`**, **`007`** (Metals/FX SMT) and **`SETUP-ARCH-016`** (NQ Intermarket SMT) can **never fire in live trading**, and `SETUP-ARCH-010`/`013` never get M1 confirmation.
   - Inside `scan_symbol()` (`live_radar.py:218`), `detect_metals_smt_divergence()` is passed **`cur_dt.hour` (UTC hour)** while `metals_smt.py:32-43` checks for **Tehran hours (`9, 10, 11` / `14, 15, 16`)**, causing London Open (`07–08 UTC`) and NY Open (`12–13 UTC`) to fall into the `else` branch (`NY AM Range`).

3. **Core ICT Detector Bugs Inside `fast_screener.py`**:
   - **Inverted Breaker/MSS Pivot Order (`detect_breaker_and_mss`, `lines 117-138`)**: Requires `last_high_idx < last_low_idx` for Bearish MSS (and `last_low_idx < last_high_idx` for Bullish MSS), which **rejects** true sweep reversals and instead fires on continuation breakdowns/breakouts. Swings also only check 1 neighbor bar (`idx-1`, `idx+1`).
   - **Mitigated / Invalidated FVGs Still Used (`detect_fvg_5m` `lines 57-76`, `smc_tools.py:84-103`)**: Never checks whether subsequent bars already filled or closed through the FVG (and `range(len(recent) - 1, 2, -1)` skips `i=2`).
   - **H1 Slope & Cross-Timeframe Bugs (`ARCH-017` `line 1025`, `ARCH-018` `lines 1231, 1245`)**: `ARCH-017` computes `h1_slope = ema50 - float(bars_1h[-6]['close'])` (comparing H1 EMA50 to raw close 6 bars ago instead of EMA50 6 bars ago). `ARCH-018` compares distance from H1 EMA20 against `1.2 * atr_m5` (5M ATR).
   - **Broken Timestamp Offsets (`ARCH-012` `line 546`, `ARCH-013` `line 618`)**: Both inspect `b['dt'].hour` from `_convert_records()`, which is **raw MT5 broker server time (EET/EEST)**, not UTC.
   - **Stale / Already-Mitigated H1 Origin (`ARCH-014`, `lines 717-745`)**: Checks `sb['close'] < inval_sl` (ignoring wicks) and never checks whether the H1 origin zone was already retested earlier.
   - **Stale Sweeps (`line 1739-1755`, `ARCH-010` `line 218`)**: `pierced_high`/`pierced_low` can be up to 9 bars old; `ARCH-010` checks `highs[-3:]` without verifying the sweep/MSS is current.
   - **AI Council Gets Stale Charts (`council.py:204`)**: `assemble_council_intelligence()` only regenerates charts if the PNG files don't exist on disk, so `/council` re-uses old PNGs.

### 4.2 Quant Bot Setup Detection (`live_quant_bridge.py`, `annual_ratified_strategies.json`)

1. **Duplicate / Clone Rules Loaded (`live_quant_bridge.py:56-68`)**: On `NQ`, `R14_011` and `R14_009` share the exact same `price_zscore_50` / `price_zscore_100` thresholds. On `XAUUSD`, `R15_048` and `R11_022` share the same `kurtosis_30 > 1.1932` condition.
2. **Backtest vs Live Entry & Overlap Mismatch (`live_quant_bridge.py:158-172` vs `vectorized_backtester.py:157, 173`)**: Backtest enters **Market at next bar open** and blocks overlapping trades (`if idx <= current_active_exit: continue`). Live bot places **Limit orders** (`tick.bid - min_offset` / `tick.ask + min_offset`) and **never checks if a position/order is already open** on that symbol.
3. **Runs Outside Session Hours (`live_radar.py:628-638`)**: `quant_bridge.scan_all()` runs before `is_killzone_active()`, generates signals off-hours, and gets rejected by `MT5Engine.validate_limit_order()`.
4. **Fixed `0.01` Lot vs Backtest's Constant `$12` Risk (`live_quant_bridge.py:175` vs `vectorized_backtester.py:260`)**: Backtest sizes every trade to risk `$12.00`. Live bot hardcodes `0.01` lot.

---

## 5. System Improvement Proposals

### 5.1 Unify Live Execution with Backtested Edge (1:1 Parity)
1. **Use Screener Coordinates Directly (`live_radar.py`, `bot.py`, `smc_tools.py`)**: Emit a canonical `OrderPlan` directly from `screen_ict_session()` (`entry_ref`, `sl_ref`, `archetype_id`, `recommended_target_rr`, `recommended_be_rr`, `ttl_minutes`) instead of discarding them and overwriting with `build_validated_order_plan()`’s generic 5M FVG + 15-bar SL.
2. **Make `LiveMarketRadar` Run `screen_ict_session()` Directly (`live_radar.py`)**: Trigger once per newly closed M5 candle (`bar[-2]["time"]` advancement), fetch `>= 200` M5 bars + `M1` bars + `XAGUSD`/`SPX`/`YM` bars for SMT, and remove the divergent `scan_symbol()` pre-filter.
3. **Align `LiveQuantBridge` with `VectorizedBacktester` (`live_quant_bridge.py`)**: Either execute Quant rules as next-bar market orders (matching the backtest) or backtest limit-offset fills first; enforce 1 active trade/order per symbol, gate by session/killzone before sending cards, and deduplicate overlapping rules (`R14_011` vs `R14_009` on `NQ`; `R15_048` vs `R11_022` on `XAUUSD`).

### 5.2 Dynamic Position Sizing & Per-Ticket Trade Management
1. **Risk-Normalized Lot Sizing**: Compute lot size dynamically from `MT5Engine.calculate_risk_usd()` (`floor_to_step(target_risk_usd / (risk_per_0.01_lot + friction)) * 0.01`), clamped to broker `[volume_min, volume_max]` and `MAX_RISK_USD` / `AccountRiskManager`.
2. **Persist Per-Ticket Metadata for `MarketWatchdog` (`watchdog.py`)**: Save `ticket -> {archetype_id, rule_id, be_ratchet_r, ttl_minutes, trail_mode, placed_at}` on order placement so `Watchdog` enforces:
   - Exact BE ratchet per archetype/rule (`1.2R` for `ARCH-001`, `1.5R` for `ARCH-015`, `2.0R` for Quant, `3.0R` for `ARCH-013`).
   - `SETUP-ARCH-013` 15M structural trailing once MFE reaches `>= 4.0R`.
   - Automatic TTL cancellation (`75m` for SMC, `ttl_bars * 5m` for Quant) instead of only sending reminders.

### 5.3 Activate Existing Regime & Signal Intelligence
1. **Wire `TrendOracle` Into Execution Sizing & Targets (`trend_oracle.py`)**: Modulate `target_rr`, `be_ratchet_r`, and risk (`1.0R` aligned, `0.5R` counter-trend scalp with tighter TP/BE) instead of only printing a Telegram badge.
2. **Fix `macro_bias.py` (`line 198`)**: Reserve `BUY_ONLY` / `SELL_ONLY` for strong directional USDX trends (`BULLISH_EXPANSION` / `BEARISH_EXPANSION`) and keep `CONSOLIDATION_RANGE` as `SELECTIVE_BI_DIRECTIONAL`.
3. **Fix Core SMC Structural Primitives (`fast_screener.py`, `smc_tools.py`)**: Fix `detect_breaker_and_mss()` pivot ordering, add unmitigated/unviolated validation to `detect_fvg_5m()`, `get_smc_landmarks()`, and `detect_reversal_origin_retest()`, and replace all hardcoded UTC/Tehran hours with `session_clock.py` + `server_epoch_to_zones()`.

### 5.4 Cut Latency & Stale-Data Risk in the AI Decision Layer
1. **Use `SnapDecisionEngine` for Fast Setups (`snap_decision_engine.py` vs `council.py`)**: Route time-sensitive `M1`/`M5` breakout/continuation setups (`ARCH-010`, `013`, `015`, `017`) through `SnapDecisionEngine` (~1–2s) instead of 4 sequential `agy.exe` CLI calls.
2. **Force Fresh Chart Generation (`council.py:204`)**: Always regenerate MTF PNGs (or check file age `< 60s`) so `/council` never evaluates stale charts.

### 5.5 Portfolio Risk, Broker Hardening & Testing
1. **Correlated Exposure Guard (`account_risk_manager.py`)**: Cap combined risk in the same USD direction (e.g., max `1.5%` across correlated `XAUUSD`, `GBPUSD`, `NQ` trades).
2. **Broker-Safe Order Submission & Spread Normalization (`mt5_engine.py`, `watchdog.py`)**:
   - Replace `sym_info.spread > 50` with an asset-scaled spread limit (`> 3.0 * get_default_broker_spread(symbol)`), align momentum ATR thresholds with `evaluator.py`, and add a daily rollover blackout around `23:55–00:15` broker server time.
   - Inspect `symbol_info.filling_mode`, `stops_level`, and `trade_tick_size` in `MT5Engine.place_limit_order()` and `modify_position_sltp()`.
   - Fix `MT5Engine.get_daily_performance()` to query from broker server midnight and include `commission + swap + fee` in `consecutive_losses`.
3. **Single Thread-Safe `MT5Engine` & Live-Bot Unit Tests**: Share one thread-locked `MT5Engine` instance and add mocked-MT5 unit tests in `app/tests/` for `live_radar.py`, `live_quant_bridge.py`, `watchdog.py`, `mt5_engine.py`, `smc_tools.py`, and `bot.py`.
