# TradingGuard Backtesting Audit & Integrity Plan (2026-11-19)

A forensic audit of why existing backtest results in `TradingGuard` cannot be trusted at face value, followed by the engineering and governance rules required to make all future backtests verifiable, causal, and tamper-proof.

---

## Part 1: Why Current Backtests Cannot Be Trusted (Verified in Code)

Beyond the issues already recorded in `docs/MIRROR_RECONCILIATION_2026-11-07.md` (multiple incompatible simulators, post-hoc bans selected after seeing full-year 2026 data, and `OPEN_AT_END` floating PnL summed as realized profit) and `docs/NOV05_NOV06_VISION_CLAIM_WITHDRAWAL.md` (a `+2.50R` commit message with zero trade artifacts), the following bugs remain active in the backtesting codebase:

### 1.1 100% Phantom Instant Fills, Lookahead & TP-First Bias (`hitl/backtest/master_production_portfolio_audit.py`)
This script produced the `+116.5R, PF 2.97` headline figure:
- **Zero Fill Verification (`lines 166–245`)**: `simulate_production_execution()` never checks whether forward M1 bars actually touched `entry`. Every limit-order setup (`entry_ref` at an FVG or Breaker away from market price) is assumed 100% filled on minute 0—even when price ran away without retracing.
- **4-Minute Intrabar Lookahead (`lines 349–352`)**: `t_entry = bars_m5[m5_idx]['time']` is the **open** timestamp of the 5M signal bar (e.g., `10:00:00`), and `forward_window = bars_m1[m1_idx + 1 : m1_idx + 480]` begins at `10:01:00`—simulating trades *inside* the forming 5M signal bar 4 minutes before it closes at `10:05:00`.
- **15M Future-Bar Lookahead (`lines 182–190`)**: At minute 1 of a 15-minute slot, `bars_m15_map[bar_m15_slot]` loads the completed 15M bar's high and low from 14 minutes in the future.
- **Same-Bar Ratchet & TP-First Precedence (`lines 195–244`)**: Updates `max_mfe_r` and arms Breakeven / 15M trailing *before* checking `hit_sl` on the same M1 bar, checks `if hit_tp:` *before* `elif hit_sl:`, omits spread on `hit_sl`/`hit_tp`, ignores the `$12` risk cap, and deducts zero commission.

### 1.2 Optimism Bugs in the "Canonical" Simulator (`hitl/backtest/evaluator.py`)
- **Asymmetric Loss Clamping vs. Uncapped Wins (`lines 344–360, 456, 485`)**:
  - When `abs(effective_entry - sl) * pip_val` exceeds `max_risk_usd` (`$12.00` at `0.01` lot), `evaluator.py` clamps `price_risk_usd = 12.0` on losses **without rejecting the trade or scaling down lot size / `pip_val` on wins**.
  - Example: A 20-pt Gold stop (`$20` risk on `0.01` lot—rejected in live `MT5Engine`) loses only `-$12.10` when stopped out, but still uses `risk_pts = 20` to set `max_tp = entry + 70` and pays `+$69.90` on a win, recording `+5.82R` (`69.90 / 12.00`).
- **Fill-Bar Stop-Loss Immunity (`lines 414–423`)**:
  - Because `evaluate_council_decision()` uses `if not is_filled: ... else: ...`, when a limit order fills on M1 bar `idx`, `hit_sl` is **not checked until `idx + 1`**. Violent news/sweep candles that fill a limit order and blow through SL within the same minute are granted 1 minute of SL immunity.

### 1.3 Off-by-One Prior-Day (`PDH`/`PDL`) Shift (`hitl/backtest/fast_screener.py:1485`, `hitl/backtest/mtf_structure.py:46`)
- `screen_ict_session(closed_bars_only=True)` slices `bars_1d = bars_1d[:-1]`.
- When `bars_1d[-1]` is today's forming D1 bar, `bars_1d[:-1]` makes `bars_1d[-1]` *yesterday*. Downstream code in `mtf_structure.py:46` and `fast_screener.py:608, 1209` then reads `bars_1d[-2]`, which is **two trading days ago (`T-2`)** rather than Prior Day (`T-1`), corrupting `PDH`, `PDL`, and `is_inside_day`.

### 1.4 Quant Engine Commission Distortion, Rollover Blindness & Selection Bias (`hitl/quant_engine/`)
- **Unscaled Commissions on Scaled Risk (`vectorized_backtester.py:260–266`)**: Scales position size so every trade risks `$12.00` (`usd_per_pt = 12.0 / initial_risk_pts`), **yet always deducts a flat `$0.10` commission** (valid only for `0.01` lot). Tight-stop rules requiring `0.20+` lots to risk `$12.00` actually pay `$2.00+` round-trip commission + spread—explaining why high-turnover strategies looked profitable in Python but lost `-$3,268.75` to commissions in MT5.
- **Overnight Rollover Fills at Daytime Spread (`consolidated_annual_orders_schedule.csv`)**: Executes Gold and NQ trades during `23:45–03:00` server time assuming tight daytime spreads (`0.22` Gold, `1.0` NQ), ignoring 5x–15x rollover spread widening and daily market-close halts.
- **OOS Cherry-Picking & Clone Rules (`annual_discovery_runner.py:103`)**: Evaluates the top 15 evolved rules on the single 40% OOS window and ratifies whichever pass (`PF >= 1.15`), turning OOS into a validation/selection split rather than an unseen holdout, and ratifying near-identical predicate permutations (`R14_030`, `R14_011`, `R14_020`, `R14_048`, `R14_009` on NQ).

### 1.5 Bugs in the Pack 7 Holdout Runner (`hitl/backtest/run_holdout_test.py`)
- Hardcodes Summer Tehran checkpoints (`10:00`, `10:30`, `15:30`, `17:30`) in `CHECKPOINTS` (`lines 96–105`) and treats them as UTC against EET/EEST broker bar timestamps (`lines 445, 558`).
- Calls `screen_ict_session()` without `bars_1d` (`line 580`), includes banned `XAGUSD` in `DEFAULT_SYMBOLS` (`line 93`), uses an optimistic `0.15` Gold spread (`line 209` vs `0.22` live), and credits/debits a trade's future exit PnL to `state["realized_pnl"]` immediately at entry time before subsequent checkpoints occur (`lines 600–602`).

### 1.6 Native MT5 Tester EA Diverges From Limit-Only Rules (`mql5/TradingGuard_Executor.mq5:220–236`)
- When replaying `orders_schedule.csv` in MT5 Strategy Tester, if market price has already crossed `entry` at `trigger_time`, `TradingGuard_Executor.mq5` converts `SELL_LIMIT` / `BUY_LIMIT` into an immediate **Market Order** (`g_trade.Sell` / `g_trade.Buy`), or shifts invalid limit prices to `ask + stops_level`.

---

## Part 2: Architecture & Rules to Guarantee Legitimate Backtests

### 2.1 Binding Backtest Governance Rules (`GEMINI.md` + `docs/BACKTEST_INTEGRITY_RULES.md`)
1. **Single Simulator Mandate**: Custom trade-simulation loops inside individual research, seasonal, or portfolio scripts are strictly forbidden. Every backtest must route through the single audited simulator (`hitl/backtest/evaluator.py` for order-book/SMC plans, or a unified tick/M1 execution core shared by both SMC and Quant).
2. **No Artifact, No Claim**: Reporting any Net R, Win Rate, Profit Factor, or Sharpe Ratio without a saved `trade_ledger.csv` and cryptographic `run_manifest.json` on disk is forbidden.
3. **Mandatory Unfiltered Baseline**: Any report applying session bans, archetype filters, or regime gates must report the unfiltered baseline over the exact same symbol/date universe alongside the filtered result. Any filter chosen after inspecting a date range permanently classifies that date range as `IN_SAMPLE_TUNED`.
4. **Strict Realized vs. Unrealized Split**: `OPEN_AT_END` positions must never be included in realized Net R, Win Rate, or Profit Factor.

### 2.2 Fix & Lock the Canonical Simulator (`hitl/backtest/evaluator.py` & `vectorized_backtester.py`)
1. **Honest Risk Cap & Lot Scaling**:
   - Match live `MT5Engine`: at fixed `0.01` lot, if `price_risk_usd + spread_cost + commission > max_risk_usd`, return `status = "REJECTED_RISK_CAP"` (`0.0` PnL).
   - When dynamic lot sizing is enabled, compute `lot = floor_to_step(max_risk_usd / risk_per_lot, 0.01)` (clamped to `[volume_min, volume_max]`) and apply that exact `lot` to **both** wins, losses, and commissions—never clamping losses while leaving wins uncapped.
2. **Same-Bar Fill + SL Check (`fill_idx`)**:
   - On the M1 bar where a limit order fills (`fill_idx`), immediately test `hit_sl` on that same bar. Under conservative M1 OHLC assumptions, if both `entry` and `sl` are touched in `fill_idx`, record `LOSS`. Only allow `TP` or `BE` ratchet starting on `fill_idx + 1` (unless verified tick data proves post-fill excursion order).
3. **Lot-Scaled Commissions & Rollover Spread Realism**:
   - Scale commission linearly with lot (`commission_per_001_lot * (lot / 0.01)`).
   - Use actual historical MT5 bar `spread` from the M1 parquet data when present (`max(bar['spread'] * point, default_spread)`), enforce rollover spread widening / trading embargoes during `23:45–01:05` broker server time, and respect daily symbol market-close windows.

### 2.3 Single Causal Data Slicer (`hitl/backtest/causal_feed.py`)
1. **Strict Bar-Close Visibility**: A timeframe bar `[open_ts, open_ts + tf_seconds)` is only visible to detectors when `decision_ts >= open_ts + tf_seconds`. Forming HTF bars (`H1`, `D1`) are never leaked into historical slices, and closed `D1` bars are indexed unambiguously (`closed_1d[-1]` is always Prior Day `T-1`, eliminating the `T-2` `bars_1d[:-1]` bug).
2. **Unified DST & Broker Timezone Conversion**: Convert all MT5 server epochs via `ZoneInfo("Europe/Athens")` → `UTC` → `Asia/Tehran` / `Europe/London` / `America/New_York` (`session_clock.py`). Dynamic session checkpoints replace static `10:30` / `15:30` timestamps.
3. **Chronological Portfolio State**: Maintain an event queue of open orders/positions across symbols so `max_open_trades`, concurrent risk %, cooldowns, and `-$34` daily circuit breakers trigger **only after** a trade's real `exit_timestamp` has passed.

### 2.4 Three-Way Data Partition & Cryptographic Provenance (`run_manifest.json`)
1. **Strict 3-Vault Chronological Split**:
   - **Vault 1 — Discovery / Train** (e.g., 2025 H1 – 2026 Q1): Strategy mining, genetic evolution, threshold design.
   - **Vault 2 — Validation / Calibration** (e.g., 2026 Q2 – Nov 6, 2026): Archetype/session pruning, deduplicating correlated/identical Quant rules, and applying a **Multiple-Testing / Deflated Sharpe** hurdle that logs total `N` rules tested.
   - **Vault 3 — Locked Holdout** (e.g., pre-2025 H1 OOS + post-Nov 7, 2026 forward holdout): Frozen hashes + append-only `holdout_audit_log.jsonl` that records every holdout execution and every `--freeze` event so repeated re-tuning is permanently auditable.
2. **Automatic `run_manifest.json`**: Every backtest output folder writes SHA-256 hashes of input `.parquet` files, `evaluator.py`, `fast_screener.py`, git `HEAD` + `git diff` hash, spread/slippage/commission parameters, candidate count `N`, and output `trade_ledger.csv` SHA-256.

### 2.5 Automated "Anti-Cheat" Pytest Suite (`app/tests/test_backtest_integrity.py`) & MT5 Tick Parity
1. **Future-Scramble Invariance Test (Zero-Lookahead Mathematical Proof)**: At timestamp `T`, run the causal feed + screener; then mutate all M1/M5/H1/D1 bars after `T` (`+1000%` spikes / `-90%` crashes) and assert the signal, `entry`, `sl`, and `tp` at `T` are 100% identical.
2. **Intrabar Conflict & Fill-Bar Blow-Through Tests**: Verify a single M1 bar touching `entry` + `sl` + `tp` always resolves to `LOSS`, never `WIN` or `BREAKEVEN`.
3. **Risk/Reward Symmetry Test**: Verify wide stops (`risk > max_risk_usd` at `0.01` lot) are rejected, never asymmetrically clamped on losses while paying uncapped wins.
4. **AST Custom-Simulator Linter**: Fail `pytest` if any benchmark runner in `hitl/backtest/` computes `WIN`/`LOSS` loops outside the canonical simulator.
5. **MT5 Real-Tick Cross-Validation**: Remove the limit-to-market fallback in `mql5/TradingGuard_Executor.mq5` so MT5 Strategy Tester ("Every tick based on real ticks") executes the exact limit orders from `orders_schedule.csv` and serves as the independent broker-grade ground truth.
