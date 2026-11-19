# HITL Bot Pipeline Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remediate all critical execution bugs, risk calculation errors, watchdog auto-cancellations, scanner blind spots, and timezone/DST inconsistencies identified in `docs/HITL_BOT_AUDIT_2026-11-18.md`.

**Architecture:** 
1. Unify execution geometry between `fast_screener.py` and `live_radar.py`/`bot.py`/`smc_tools.py` so screener coordinates, ratified archetype IDs, target R:R, and BE rules are preserved without generic overwrites.
2. Fix asset microstructure (NQ point values, broker spreads, MT5 filling modes, and broker-midnight daily PnL sync).
3. Align `MarketWatchdog` with `evaluator.py` physics (asset-scaled spreads, 3.5x/2.0x ATR momentum cancellations within 3.0x ATR, and ticket-level archetype metadata tracking).
4. Harmonize `LiveQuantBridge` with `VectorizedBacktester` (market/tight-limit entries, duplicate exposure veto, active killzone gating, and $12 risk position sizing).
5. Unify scanner architecture in `LiveMarketRadar` on closed bars (≥200 bars lookback, passing `smt_info` and `bars_1m`, removing the divergent sweep-only pre-filter, and fixing inverted breaker pivots / unmitigated FVG checks).
6. Maintain 100% synchronization with `docs/SYSTEM_EXECUTION_MIRROR.md`.

**Tech Stack:** Python 3.14, MetaTrader 5 API (`MetaTrader5`), pandas, numpy, ZoneInfo / `session_clock.py`.

**Spec:** `docs/HITL_BOT_AUDIT_2026-11-18.md` and `docs/SYSTEM_EXECUTION_MIRROR.md`.

## Global Constraints
- Strictly adhere to `g:\Code\TradingGuard\GEMINI.md`: 100% English communication, zero hallucination/distortion, zero manual injection, and dynamic DST session clock handling (Tehran UTC+3:30 vs London/NY DST).
- `docs/SYSTEM_EXECUTION_MIRROR.md` must be updated in the exact same turn as code modifications.
- All limit orders must obey the firm $12.00 dollar risk cap (`MAX_RISK_USD`).
- Closed bars only for signal generation (`closed_bars_only=True`).

## Review Focus
1. `NQ` orders must correctly calculate risk via broker tick value and never trigger false $12 risk cap rejections.
2. `MarketWatchdog` must not cancel orders on normal NQ (1.0 pt) or Gold ($0.50) spreads.
3. Ratified archetypes (`SETUP-ARCH-015`, `017`, `019`) must pass their exact entry/SL/TP coordinates to MT5 without being overwritten by generic 5M FVG + 15-bar SL.
4. `LiveMarketRadar` must not burn 30-minute cooldowns on unclosed bars or block continuation/breakout setups.
5. Inverted breaker/MSS pivot ordering must be corrected so high-sweep reversals fire on genuine sweeps.

---

### Task 1: Unify Screener Setup Geometry & Multi-Asset Risk Math

**Files:**
- Modify: `hitl/tools/smc_tools.py`
- Modify: `hitl/live_radar.py`
- Modify: `hitl/bot.py`
- Modify: `hitl/mt5_engine.py`
- Test: `app/tests/test_task1_geometry_and_risk.py`

- [x] **Step 1: Write verification test for multi-asset point size, risk math, and geometry preservation**
  Create `app/tests/test_task1_geometry_and_risk.py` verifying:
  - `smc_tools.py` point value on NQ is not treated as $0.01 Gold pip.
  - `build_validated_order_plan()` accepts explicit `entry_ref`, `sl_ref`, `target_rr`, `archetype_id` and does not overwrite them with generic 5M FVG / 15-bar SL.
  - `bot.py` order plan dict format contains flat keys `entry`, `sl`, `tp`, `lot`, `symbol`, `direction`, `archetype_id`.

- [x] **Step 2: Fix `pip_size` and risk calculation in `hitl/tools/smc_tools.py`**
  - In `get_smc_landmarks()`, dynamically determine point size:
    - FX: `0.0001` (or `0.01` for JPY)
    - XAUUSD: `0.01` ($1.00 per point / 100 oz contract)
    - XAGUSD: `0.001`
    - Indices (`NQ`, `SPX`, `YM`): Use index point size (e.g. `0.25` or `1.0` depending on broker `symbol_info.point`).
  - In `validate_order_ticket()`, calculate dollar risk using broker contract specifications (`trade_tick_value / trade_tick_size * price_dist * lot` or `MT5Engine.calculate_risk_usd`). For NQ, a 30 pt stop on 0.01 lot is $6.00 (not $30.00), fitting safely inside the $12.00 cap.

- [x] **Step 3: Update `build_validated_order_plan()` to preserve screener coordinates**
  - Add optional parameters `entry_ref: Optional[float] = None`, `sl_ref: Optional[float] = None`, `recommended_target_rr: Optional[float] = None`, `archetype_id: Optional[str] = None`.
  - When `entry_ref` and `sl_ref` are provided, use them directly, format SL with asset buffer, and compute TP using `recommended_target_rr` instead of falling back to generic 15-bar high/low $\pm 1$ pip and forcing 3.0 R:R.

- [x] **Step 4: Update `hitl/live_radar.py` and `hitl/bot.py` call sites**
  - In `live_radar.py:358-385`, pass `setup["entry_ref"]`, `setup["sl_ref"]`, `setup["recommended_target_rr"]`, and `setup["archetype_id"]` to `build_validated_order_plan()`.
  - In `bot.py:250-285` (`_chart_worker`) and `bot.py:420-435` (`_council_worker`), ensure `landmarks` is always computed (even when TradingView capture succeeds), pass screener coordinates, and flatten `PENDING_EXECUTION_PLANS[plan_id]` keys so inline approval buttons execute cleanly.

- [x] **Step 5: Run tests and verify**
  Run `python app/tests/test_task1_geometry_and_risk.py` and ensure all tests pass.

---

### Task 2: Calibrate MarketWatchdog & Daily Performance Accounting

**Files:**
- Modify: `hitl/watchdog.py`
- Modify: `hitl/mt5_engine.py`
- Modify: `hitl/backtest/evaluator.py`
- Test: `app/tests/test_task2_watchdog_and_performance.py`

- [x] **Step 1: Write test for Watchdog spread thresholds, momentum calibration, and daily performance**
  Create `app/tests/test_task2_watchdog_and_performance.py` verifying:
  - Watchdog does not cancel NQ on 100-point (1.0 pt) spread.
  - Momentum check uses 3.5x ATR for metals / 2.0x for FX and requires price to be within 3.0x ATR of entry.
  - `MT5Engine.get_daily_performance()` uses broker server midnight and includes commission/swap in consecutive loss counting.

- [x] **Step 2: Fix asset-scaled spread threshold in `hitl/watchdog.py`**
  - Replace `if sym_info.spread > 50:` with an asset-calibrated check:
    - Query `get_default_broker_spread(p.symbol)` or broker normal spread.
    - Set threshold to $\max(3.0 \times \text{normal\_spread\_points}, 50 \times \text{point\_multiplier})$.
    - For NQ (where normal spread is 100–150 points = 1.0–1.5 pts), allow up to 400 points before triggering spread protection.

- [x] **Step 3: Align momentum cancellation in `hitl/watchdog.py` with `evaluator.py`**
  - Exclude forming bar from ATR baseline (`bars_1m[-15:-1]`).
  - Use $3.5\times$ ATR for Gold/Metals and $2.0\times$ ATR for FX/Indices.
  - Only cancel if current price is within $3.0\times$ ATR of the limit entry (matching `evaluator.py:390-410`).

- [x] **Step 4: Track archetype metadata and dynamic BE ratchets**
  - Create or update ticket metadata store (`hitl/memory/active_order_meta.json`) mapping MT5 order ticket to `{archetype_id, be_ratchet_r, target_rr, ttl_minutes, created_at}`.
  - In `MarketWatchdog.check_breakeven_ratchet()`, look up the ticket's ratified `be_ratchet_r` (e.g., 1.2R for ARCH-001, 1.5R for ARCH-015/ARCH-019, 3.0R for ARCH-013, 2.0R for Quant) instead of overwriting with generic session policy.
  - Fix `get_optimal_trade_management()` fallback for `NQ` and `BTCUSD` in `evaluator.py`.

- [x] **Step 5: Fix broker server midnight & net loss calculation in `hitl/mt5_engine.py`**
  - In `get_daily_performance()`, calculate `midnight` in broker server time (EET/EEST) rather than naive local Windows/Tehran time.
  - Calculate net deal PnL as `deal.profit + deal.commission + deal.swap + deal.fee` to ensure commission-drag breakevens are correctly registered as net losses.

- [x] **Step 6: Run tests and verify**
  Run `python app/tests/test_task2_watchdog_and_performance.py` and ensure all tests pass.

---

### Task 3: Align LiveQuantBridge with VectorizedBacktester

**Files:**
- Modify: `hitl/quant_engine/live_quant_bridge.py`
- Test: `app/tests/test_task3_quant_bridge_alignment.py`

- [x] **Step 1: Write test for Quant Bridge entry execution and safeguards**
  Create `app/tests/test_task3_quant_bridge_alignment.py` verifying:
  - Quant bridge enters next-bar open market order or tight limit with validated fill logic.
  - Duplicate orders on the same symbol are blocked.
  - Signals outside active killzones/quant hours are suppressed.
  - Lot size scales to risk exactly $12.00 based on stop loss distance.

- [x] **Step 2: Update entry execution & duplicate-exposure gating**
  - In `LiveQuantBridge.evaluate_and_execute()`, check `engine.get_open_positions(symbol)` and `engine.get_pending_orders(symbol)`. If an active position/order already exists, stand aside (matching `VectorizedBacktester` `if idx <= current_active_exit: continue`).
  - Restrict execution to active trading windows.
  - Reconcile entry type: execute market order at next bar open or validated limit without negative-selection offsets.

- [x] **Step 3: Implement dynamic lot sizing for $12 risk**
  - Calculate `lot = max(0.01, round(MAX_RISK_USD / (stop_distance * point_value), 2))` clamped to broker min/max lot and step, ensuring constant dollar risk matching the backtest.

- [x] **Step 4: Run tests and verify**
  Run `python app/tests/test_task3_quant_bridge_alignment.py` and ensure all tests pass.

---

### Task 4: Fix Screener Core, Live Radar Pre-Filter & Dynamic Session Clock

**Files:**
- Modify: `hitl/live_radar.py`
- Modify: `hitl/backtest/fast_screener.py`
- Modify: `hitl/backtest/metals_smt.py`
- Modify: `hitl/screener_gate.py`
- Modify: `hitl/council.py`
- Modify: `hitl/macro_bias.py`
- Modify: `docs/SYSTEM_EXECUTION_MIRROR.md`
- Test: `app/tests/test_task4_screener_and_radar.py`

- [x] **Step 1: Write test for screener pivot ordering, FVG mitigation, and live radar lookback**
  Create `app/tests/test_task4_screener_and_radar.py` verifying:
  - `detect_breaker_and_mss()` correctly requires swing low before sweep high for Bearish MSS (and vice versa for Bullish).
  - `detect_fvg_5m()` rejects FVGs that have been filled/mitigated by subsequent candles.
  - `LiveMarketRadar` feeds ≥200 M5 bars on closed candles (`closed_bars_only=True`), passes `smt_info` and `bars_1m`, and allows continuation/breakout setups to trigger.

- [x] **Step 2: Fix inverted breaker/MSS pivot ordering in `hitl/backtest/fast_screener.py`**
  - In `detect_breaker_and_mss()` (lines 117-138):
    - For Bearish MSS: A true high sweep reversal requires the prior swing low to occur before the sweep high (`last_low_idx < last_high_idx`), followed by a displacement break below that swing low.
    - For Bullish MSS: A true low sweep reversal requires the prior swing high to occur before the sweep low (`last_high_idx < last_low_idx`), followed by a displacement break above that swing high.

- [x] **Step 3: Add FVG mitigation and invalidation check**
  - In `detect_fvg_5m()` and `get_smc_landmarks()`:
    - Verify that no subsequent candle between the FVG and the current bar closed through or fully filled the gap before treating it as an active POI.

- [x] **Step 4: Unify `LiveMarketRadar` scanner and eliminate redundant pre-filter**
  - In `live_radar.py`:
    - Increase M5 fetch from 60 bars to 240 bars (20 hours) so Asian and London ranges are preserved.
    - Evaluate on closed bars (`closed_bars_only=True`).
    - Remove the restrictive `scan_symbol()` sweep-only pre-filter; pass closed bars directly to `screen_ict_session()` so continuation setups (`004`, `015`, `017`, `019`) are evaluated.
    - Fetch and pass `smt_info` (via `detect_metals_smt_divergence` / NQ SMT) and `bars_1m` into `screen_ict_session()`.

- [x] **Step 5: Fix DST session clock in `fast_screener.py` & `metals_smt.py`**
  - Replace static Tehran hour checks with dynamic `session_clock.get_active_session_status(sig_dt)`.
  - Fix `council.py:204` to force chart regeneration when `/council` is called, ensuring fresh charts are analyzed.
  - Remove forced `BUY_ONLY` bias in `macro_bias.py:198` during USD consolidation.

- [x] **Step 6: Synchronize `docs/SYSTEM_EXECUTION_MIRROR.md`**
  - Update `docs/SYSTEM_EXECUTION_MIRROR.md` in the exact same turn per the System-Document Synchronization Mandate, reflecting all unified execution geometry, risk math, watchdog thresholds, and scanner updates.

- [x] **Step 7: Run full integration tests**
  Run `python -m unittest discover -s app/tests -p "test_*.py"`, `npm --prefix web_replayer test`, and verify the entire bot pipeline runs cleanly without errors.
