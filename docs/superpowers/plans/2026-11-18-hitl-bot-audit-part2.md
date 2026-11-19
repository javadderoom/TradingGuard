# HITL Bot Audit Remediation - Part 2 Implementation Plan (Sections 4 & 5)

**Goal:** Implement and verify the advanced detector fixes, SMT wiring, quant rule orthogonalization, watchdog TTL auto-cancellation, rollover blackout, and MT5 execution hardening outlined in Sections 4 & 5 of `docs/HITL_BOT_AUDIT_2026-11-18.md`.

---

### Task 1: Detector Math & Microstructure Fixes in `hitl/backtest/fast_screener.py`
**Files:**
- Modify: `hitl/backtest/fast_screener.py`
- Test: `app/tests/test_fast_screener_microstructure.py`

- [ ] Step 1: Write test for H1 slope, H1 ATR overextension, broker timestamp conversion, H1 origin mitigation, and fresh sweep window.
- [ ] Step 2: Fix `ARCH-017` (line 1025) and `ARCH-018` (line 1238): calculate true EMA50 series history to determine `h1_slope = ema50 - ema50_prev5` instead of subtracting raw candle close 6 bars ago.
- [ ] Step 3: Fix `ARCH-018` (line 1253): calculate H1 ATR (`atr_h1`) and evaluate `stat_overextended = abs(cur['close'] - ema20) >= (1.2 * atr_h1)` instead of 5M ATR.
- [ ] Step 4: Fix `ARCH-012` (line 554) and `ARCH-013` (line 626): convert bar timestamps to true UTC using `server_epoch_to_zones()` or broker offset so Asian range and ADR cutoff hours don't skew.
- [ ] Step 5: Fix `ARCH-014` (lines 726-750): check candle wicks (`low`/`high`) for invalidation, and reject if the H1 origin zone was already retested by prior candles in `subsequent[:-1]`.
- [ ] Step 6: Fix stale sweeps (lines 1747-1762 & `ARCH-010` line 218): require liquidity sweep pierce to be recent (within the last 4 candles).
- [ ] Step 7: Run `python -m unittest app/tests/test_fast_screener_microstructure.py` and verify all tests pass.

---

### Task 2: Live SMT & M1 Wiring in `hitl/screener_gate.py`
**Files:**
- Modify: `hitl/screener_gate.py`
- Test: `app/tests/test_screener_gate_wiring.py`

- [ ] Step 1: Write test verifying `fetch_live_bars()` returns 240 M5 bars and 60 M1 bars, and `run_screener_gate()` passes `smt_info` and `bars_1m` to `screen_ict_session()`.
- [ ] Step 2: Update `fetch_live_bars()` in `screener_gate.py` to copy 240 M5 bars and 60 M1 bars.
- [ ] Step 3: In `run_screener_gate()`, compute `smt_info` for Gold (via Silver M5) and pass `smt_info` and `bars["bars_1m"]` to `screen_ict_session()`.
- [ ] Step 4: Run tests and verify.

---

### Task 3: Quant Rule Orthogonalization in `hitl/quant_engine/live_quant_bridge.py`
**Files:**
- Modify: `hitl/quant_engine/live_quant_bridge.py`
- Test: `app/tests/test_quant_bridge_dedup.py`

- [ ] Step 1: Write test verifying no clone/overlapping rules are loaded for NQ and Gold.
- [ ] Step 2: Update `_load_ratified_rules()` in `live_quant_bridge.py`:
  - NQ: Load orthogonal rules `R14_011` and `R14_025` (removing subset clone `R14_009`).
  - XAUUSD: Load orthogonal rules `R15_048` (velocity), `R14_058` (orderflow volume imbalance), and `R15_023` (autocorrelation momentum) (removing duplicate `R11_022`).
- [ ] Step 3: Run tests and verify.

---

### Task 4: Watchdog TTL Auto-Cancellation & Broker Rollover Blackout (`hitl/watchdog.py`)
**Files:**
- Modify: `hitl/watchdog.py`
- Test: `app/tests/test_watchdog_ttl_and_rollover.py`

- [ ] Step 1: Write test for automatic TTL order cancellation and daily rollover blackout.
- [ ] Step 2: In `MarketWatchdog.poll()`, check order age against `meta.get("ttl_minutes", 75.0)`. If exceeded, cancel order automatically via `engine.cancel_order()` and notify Telegram.
- [ ] Step 3: Add `is_rollover_blackout()` checking broker server time `23:55–00:15` to suppress new actions and prevent false spread cancellations during bank liquidity rollover.
- [ ] Step 4: Run tests and verify.

---

### Task 5: MT5 Engine Hardening & English Localization (`hitl/mt5_engine.py`)
**Files:**
- Modify: `hitl/mt5_engine.py`
- Test: `app/tests/test_mt5_engine_hardening.py`

- [ ] Step 1: Write test verifying dynamic `type_filling` resolution, tick snapping, and thread-safe lock.
- [ ] Step 2: Implement dynamic `type_filling` resolution checking `symbol_info.filling_mode` (FOK, IOC, RETURN).
- [ ] Step 3: Snap limit order `price`, `sl`, and `tp` to `symbol_info.digits` and tick size.
- [ ] Step 4: Replace all Persian strings with professional English in `mt5_engine.py`.
- [ ] Step 5: Add `threading.Lock()` to synchronize MT5 transactional calls across threads.
- [ ] Step 6: Run tests and verify.

---

### Task 6: System Documentation Synchronization (`docs/SYSTEM_EXECUTION_MIRROR.md`)
**Files:**
- Modify: `docs/SYSTEM_EXECUTION_MIRROR.md`

- [ ] Step 1: Update `docs/SYSTEM_EXECUTION_MIRROR.md` in the exact same turn per the System-Document Synchronization Mandate, detailing all refined detector math, live SMT wiring, quant orthogonal rules, watchdog TTL auto-cancel, rollover blackout, and MT5 filling modes.
- [ ] Step 2: Run full integration suite (`python -m unittest discover -s app/tests -p "test_*.py"` and `npm --prefix web_replayer test`).
- [ ] Step 3: Restart background bot with updated code and verify clean operation.
