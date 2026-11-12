# TradingGuard Visual Co-Backtester & Agentify Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a continuous multi-asset, multi-timeframe (`1M/5M/15M/1H/4H/1D`) interactive visual co-backtester combining Tornado Python backend forensics (`screen_ict_session` + `evaluate_council_decision`) with a React + TradingView `lightweight-charts` UI where Human and Bot trade side-by-side and export Agentify alignment bundles to Antigravity.

**Architecture:** A local Tornado HTTP server (`hitl/replay_server.py`) manages lazy-cached Parquet `M1` histories (`hitl/replay_data.py`), computes zero-lookahead resampled candles, executes causal SMC screener scans under `$2,000 / $20` system risk limits (`hitl/replay_forensics.py`), and persists shared marked co-trades and Agentify forensic cases (`hitl/replay_ledger.py`). The isolated Vite + React + TypeScript frontend (`web_replayer/`) renders TradingView `lightweight-charts` with independent time/price axis scaling, toggleable ICT box/line primitives, draggable Long/Short position tools, and synchronized Bot Brain / Scorecard / Agentify panels.

**Tech Stack:** Python 3.14 (`tornado 6.5.4`, `pandas`, `pyarrow`, `MetaTrader5`, `zoneinfo`, `pytest`), Node `v22.23.4` / `npm 11.7.0`, React 18+, TypeScript, Vite, TradingView `lightweight-charts`, `vitest`.

**Spec:** [`docs/superpowers/specs/2026-11-11-visual-co-backtester-design.md`](file:///g:/Code/TradingGuard/docs/superpowers/specs/2026-11-11-visual-co-backtester-design.md)

## Global Constraints

- **Strictly Local Only**: Bind Tornado HTTP server to `127.0.0.1` (default port `8765`); zero live MT5 order placement or modifications to production `orders_schedule.csv`.
- **Zero Pip Dependencies**: Use installed Python stdlib + `tornado 6.5.4` + `pandas`/`pyarrow`/`MetaTrader5`. Frontend dependencies stay isolated inside `web_replayer/package.json`.
- **System-Wide Governance ($2,000 Account / $20 Risk)**: Enforce `AccountRiskManager` `PROP_FIRM` rules (`max_open_trades = 3`, `max_concurrent_risk_pct = 1.5%` / hard `2.0%`, `max_daily_drawdown_pct = 4.0%`, `max_overall_drawdown_pct = 10.0%`) at `$2,000.00` account size and `$20.00` per-trade risk cap for Bot trades; Human setups evaluate with uncapped R:R (`target_rr_cap=None`, `max_risk_usd=None`) plus a `$20` compliance warning badge.
- **Unmodified Live Screener**: Keep `hitl/backtest/fast_screener.py` unchanged during observation (`closed_bars_only=True` everywhere); pass historical DST offsets and toggleable `clock_mode` (`true_tehran` vs `live_legacy`) from the forensic wrapper.
- **Strict Documentation Sync**: Update `docs/SYSTEM_EXECUTION_MIRROR.md` whenever `hitl/backtest/evaluator.py` or core replay components change.
- **Zero-Lookahead Anti-Spoiler**: At replay cursor `T`, forming HTF bars use only `M1 <= T`, same-day Asian High/Low uses `[open .. min(T, asian_end)]`, and trades mask `exit_time`/`outcome`/`pnl` when `T < exit_time`.

## Review Focus

- **Unfinished HTF Bar Leakage (`replay_data.py`)**: Querying `1H`/`4H`/`1D` at `replay_to = T` mid-bar must synthesize the forming candle strictly from `M1 <= T` and omit closed high/low values from past `T`.
- **Missing Schema Column & Crypto Asset Handling (`replay_data.py` & `replay_forensics.py`)**: `M1_GBPUSD_o_2026.parquet` lacks `real_volume`, and `BTCUSD` hard-vetoes in `screen_ict_session()`; loaders must normalize columns safely and tag `BTCUSD` as `MANUAL_ONLY` without throwing `KeyError` or halting scans.
- **Wide-Stop Human Trade R:R Distortion (`evaluator.py`)**: Passing `max_risk_usd=None` and `target_rr_cap=None` on a `$30` SL / `4.5R` Human setup must return true `LOSS = -$30.00 - comm` and true `WIN = +4.5R`, never silently clamping `price_risk_usd` to `$12.0`.
- **Historical DST Rollover Parity (`replay_data.py` & `replay_forensics.py`)**: Grouping `1D`/`4H` on `Europe/Athens` broker days and computing `true_tehran` offsets across summer/winter DST transitions must apply the date's historical offset rather than today's live MT5 winter offset.
- **Oversized `1M` Range / Empty Weekend Query (`replay_server.py`)**: Requesting `1M` across >10 trading days (`~15,000+` bars cap) or on Sat/Sun must cleanly cap/truncate with explicit `truncated: true` metadata or empty bar array + HTTP 200 rather than hanging or raising 500.

---

### Task 1: Configurable `max_risk_usd` in Canonical Evaluator

**Files:**
- Modify: `hitl/backtest/evaluator.py:191-202,337-340,448,473,548,573`
- Modify: `docs/SYSTEM_EXECUTION_MIRROR.md` (Section 7 / risk note)
- Test: `app/tests/test_evaluator_max_risk.py`

**Interfaces:**
- Consumes: Existing `evaluate_council_decision(...)` in `hitl/backtest/evaluator.py`
- Produces: `evaluate_council_decision(..., max_risk_usd: Optional[float] = 12.0) -> Dict[str, Any]` (default preserves `$12.0` backwards-compatibility; `20.0` enforces `$20` ceiling; `None` disables USD risk clamping for uncapped Human setups).

- [ ] **Step 1: Write failing tests in `app/tests/test_evaluator_max_risk.py`**

```python
from hitl.backtest.evaluator import evaluate_council_decision

def _sample_bars(prices):
    return [{"time": 1700000000 + i * 60, "open": p, "high": p + 0.5, "low": p - 0.5, "close": p} for i, p in enumerate(prices)]

def test_default_max_risk_remains_12():
    bars = [{"time": 60, "open": 4000.0, "high": 4001.0, "low": 3970.0, "close": 3975.0}]
    res = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01}, bars, symbol="XAUUSD_o", spread_pts=0.2, commission_usd=0.0, target_rr_cap=None)
    assert res["status"] == "LOSS"
    assert res["realized_pnl_usd"] == -12.0

def test_20_dollar_risk_cap_and_uncapped_human_rr():
    bars_loss = [{"time": 60, "open": 4000.0, "high": 4001.0, "low": 3965.0, "close": 3968.0}]
    res_20 = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3975.0, "tp": 4050.0, "lot": 0.01}, bars_loss, symbol="XAUUSD_o", spread_pts=0.2, commission_usd=0.0, target_rr_cap=None, max_risk_usd=20.0)
    assert res_20["realized_pnl_usd"] == -20.0

    bars_win = [
        {"time": 60, "open": 4000.0, "high": 4001.0, "low": 3999.0, "close": 4000.0},
        {"time": 120, "open": 4000.0, "high": 4135.0, "low": 3999.0, "close": 4130.0},
    ]
    res_uncapped = evaluate_council_decision({"decision": "BUY_LIMIT", "entry": 4000.0, "sl": 3970.0, "tp": 4135.0, "lot": 0.01}, bars_win, symbol="XAUUSD_o", spread_pts=0.2, commission_usd=0.0, target_rr_cap=None, max_risk_usd=None)
    assert res_uncapped["status"] == "WIN"
    assert res_uncapped["rr_realized"] == 4.5
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest app/tests/test_evaluator_max_risk.py -v`
Expected: FAIL (`TypeError: unexpected keyword argument 'max_risk_usd'`).

- [ ] **Step 3: Update `evaluate_council_decision()` in `hitl/backtest/evaluator.py` & sync `docs/SYSTEM_EXECUTION_MIRROR.md`**

Add `max_risk_usd: Optional[float] = 12.0` to `evaluate_council_decision()`. Replace hardcoded `12.0` clamp at line 338 with `if max_risk_usd is not None and price_risk_usd > max_risk_usd: price_risk_usd = float(max_risk_usd)`. Replace `-min(12.0, price_risk_usd)` at lines 448 and 548 with `-price_risk_usd`, and update the loss note format string at lines 473 and 573 to cite `{max_risk_usd:.2f}` when capped vs `"uncapped"` when `None`. Update Section 7 of `docs/SYSTEM_EXECUTION_MIRROR.md` documenting the configurable `max_risk_usd` parameter (`12.0` legacy default / `20.0` at `$2,000` tier / `None` uncapped research).

- [ ] **Step 4: Run new & existing evaluator tests**

Run: `pytest app/tests/test_evaluator_max_risk.py -v && python hitl/backtest/test_reporting_realized_pnl.py`
Expected: 2 passed + 30 passed, 0 failed.

- [ ] **Step 5: Commit**

```bash
git add hitl/backtest/evaluator.py app/tests/test_evaluator_max_risk.py docs/SYSTEM_EXECUTION_MIRROR.md
git commit -m "feat(evaluator): add configurable max_risk_usd parameter preserving $12 default"
```

---

### Task 2: Multi-Asset Historical Data & Causal MTF Slicer (`hitl/replay_data.py`)

**Files:**
- Create: `hitl/replay_data.py`
- Test: `app/tests/test_replay_data.py`

**Interfaces:**
- Consumes: `backtest_results/cache/*.parquet`, `hitl/mt5_engine.MT5Engine`
- Produces:
  - `SYMBOL_CATALOG`: dict mapping `"XAUUSD_o"`, `"GBPUSD_o"`, `"NQ"`, `"SPX"`, `"YM"`, `"BTCUSD"` -> cache file, `engine_mode` (`"SMC"` vs `"MANUAL_ONLY"`), `uncalibrated` flag, default `spread_pts`.
  - `server_epoch_to_zones(srv_epoch: int) -> Dict[str, Any]` (`srv_str`, `utc_str`, `tehran_str`, `utc_epoch`, `offset_sec`).
  - `class ReplayDataManager`:
    - `get_catalog(self) -> List[Dict[str, Any]]`
    - `load_m1_df(self, symbol: str) -> pd.DataFrame` (LRU cached, normalized columns without requiring `real_volume`)
    - `get_candles(self, symbol: str, tf: str, start_epoch: int, end_epoch: int, replay_to: Optional[int] = None, max_bars: int = 15000) -> Dict[str, Any]` (returns `{"bars": [...], "truncated": bool, "forming_bar": bool}`; builds `1D`/`4H` on `Europe/Athens` broker days, `1M/5M/15M/1H` aligned cleanly, and synthesizes trailing partial candle strictly from `M1 <= replay_to`)
    - `sync_symbol_from_mt5(self, symbol: str, days_back: int = 5) -> Dict[str, Any]`

- [ ] **Step 1: Write failing tests in `app/tests/test_replay_data.py`**

Include explicit tests covering **Review Focus #1, #2, #4, #5**:
- `test_catalog_marks_btcusd_manual_only_and_loads_gbpusd_without_real_volume`: Verifies catalog metadata (`BTCUSD` `engine_mode == "MANUAL_ONLY"`, `GBPUSD_o` loads cleanly despite missing `real_volume`).
- `test_causal_partial_htf_bar_prevents_lookahead`: Queries `tf="1H"` on `2026-11-11` up to `10:15` server epoch (`replay_to`); verifies the `10:00` bar's High/Low/Close reflects ONLY M1 bars `10:00..10:15`, NOT the final `10:00..10:59` high/low/close.
- `test_broker_day_1d_and_dst_summer_offset`: Verifies `1D` bar spans `Europe/Athens` `00:00..23:59` rather than `00:00 UTC`, and July summer timestamp computes `offset_sec == 10800` vs November winter `7200`.
- `test_max_bars_cap_and_weekend_range_safe`: Queries 30 days of `1M` -> returns `truncated=True` and `len(bars) <= 15000`; queries Saturday -> returns `bars=[]` cleanly.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest app/tests/test_replay_data.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'hitl.replay_data'`).

- [ ] **Step 3: Implement `hitl/replay_data.py`**

Load parquet frames into an ordered LRU dict (`MAX_CACHED_ASSETS = 4`), normalize missing `real_volume` to `0`, derive `athens_dt` (`UTC` column parsed via `Europe/Athens` wall-clock rules for broker `1D`/`4H` bucketing), apply `get_candles` slicing with causal forming-bar aggregation when `replay_to` splits an incomplete timeframe bucket, and implement `sync_symbol_from_mt5` fetching recent bars safely into the active dataframe + parquet file.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest app/tests/test_replay_data.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hitl/replay_data.py app/tests/test_replay_data.py
git commit -m "feat(replay): add multi-asset Parquet loader and causal MTF resampler"
```

---

### Task 3: SMC Forensic Scanner & Shared Co-Backtest Ledger (`hitl/replay_forensics.py` & `hitl/replay_ledger.py`)

**Files:**
- Create: `hitl/replay_forensics.py`
- Create: `hitl/replay_ledger.py`
- Test: `app/tests/test_replay_forensics.py`

**Interfaces:**
- Consumes: `ReplayDataManager` (`hitl/replay_data.py`), `screen_ict_session` / `detect_fvg_5m` / `detect_breaker_and_mss` (`hitl/backtest/fast_screener.py`), `analyze_mtf_state` (`hitl/backtest/mtf_structure.py`), `get_session_times_for_date` (`hitl/backtest/session_clock.py`), `evaluate_council_decision` (`hitl/backtest/evaluator.py`), `AccountRiskManager` profile defaults.
- Produces:
  - `run_bot_scan(data_mgr: ReplayDataManager, symbol: str, start_epoch: int, end_epoch: int, clock_mode: str = "true_tehran", account_size_usd: float = 2000.0, max_risk_usd: float = 20.0, horizon: str = "window") -> Dict[str, Any]` -> returns `killzones`, `asian_ranges_by_day` (plus incremental boundary points per M5 bar), `diagnostics` (each M5 bar's Bot Brain state, sub-detector states, `fvg_box`, `breaker_box`, exact veto/reason), `events`, `bot_trades` (all tagged `origin="BOT"`, governed by `$2,000` / `$20` risk + `max_open_trades=3`, `4.0%` daily DD, `10.0%` overall DD, 30m duplicate-wave filter), and `bot_scorecard`.
  - `simulate_custom_trade(data_mgr: ReplayDataManager, symbol: str, direction: str, signal_time: int, entry: float, sl: float, tp: float, be_rr: Optional[float] = None, max_risk_usd: Optional[float] = None, horizon_end: Optional[int] = None, lot: float = 0.01) -> Dict[str, Any]` -> evaluates exact M1 fills/exits via `evaluate_council_decision`, computes uncapped R:R + `$20` risk limit compliance (`exceeds_risk_cap`, `risk_usd_001`).
  - `class CoBacktestLedger` (in `hitl/replay_ledger.py`): Atomic JSON CRUD over `hitl/memory/visual_co_backtest_ledger.json` with methods `list_trades(symbol: Optional[str] = None) -> List[Dict[str, Any]]`, `add_trade(payload: Dict[str, Any]) -> Dict[str, Any]`, `update_trade(trade_id: str, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]`, `delete_trade(trade_id: str) -> bool` (records strictly carry `origin`: `"BOT" | "HUMAN_PROPOSED" | "HUMAN_EDITED_BOT"`, `parent_bot_ref`, `risk_usd_001`, `exceeds_risk_cap`).
  - `class AgentifyFeedbackStore` (in `hitl/replay_ledger.py`): `list_cases() -> List[Dict[str, Any]]`, `add_case(payload: Dict[str, Any]) -> Dict[str, Any]`, `delete_case(case_id: str) -> bool` over `hitl/memory/visual_feedback_cases.json` (generates copy-ready `prompt_markdown` containing exact candle context, user setup vs bot trade, and Python screener diagnostic flags).

- [ ] **Step 1: Write failing tests in `app/tests/test_replay_forensics.py`**

- `test_bot_scan_nov11_gold_finds_arch001_and_live_legacy_reproduces_ny_veto`: Runs `run_bot_scan` on `2026-11-11` (`XAUUSD_o`) verifying `SETUP-ARCH-001` fires at `10:05` server time (`true_tehran`), incremental Asian High (`4065.88`) never leaks prior to `07:00 UTC`, and `clock_mode="live_legacy"` reproduces the `16:40 Tehran` NY PM veto at `15:10` server time.
- `test_system_risk_limits_enforce_20_cap_and_max_open_3`: Verifies simultaneous open bot positions never exceed `3` (`max_open_trades`) or daily drawdown `$80.00` (4% of `$2,000`).
- `test_simulate_human_wide_stop_returns_uncapped_rr_and_compliance_flag`: Tests `$30` stop + `4.5R` TP through `simulate_custom_trade(..., max_risk_usd=None)` -> returns `exceeds_risk_cap=True`, `risk_usd_001=30.0`, true `rr_realized=4.5`.
- `test_shared_ledger_marks_origins_and_agentify_builds_prompt`: Creates `HUMAN_PROPOSED` and `HUMAN_EDITED_BOT` entries in `CoBacktestLedger` (`tmp_path`) + `AgentifyFeedbackStore` case, asserting distinct `origin` badges and non-empty `prompt_markdown` containing screener veto/flags.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest app/tests/test_replay_forensics.py -v`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `hitl/replay_forensics.py` and `hitl/replay_ledger.py`**

In `hitl/replay_forensics.py`: wrap `screen_ict_session()` with a temporary `get_broker_utc_offset_seconds` monkeypatch when in `true_tehran` mode so historical Summer DST days use their exact historical `Europe/Athens` offset without altering `fast_screener.py` on disk; compute incremental running `(asian_high, asian_low)` per M5 bar; extract FVG `[t_start, t_end, proximal, distal]` and Breaker `[t_start, t_end, top, bottom]` coordinates; pass `smt_info=None`; evaluate `ARCH-013` with `dol_target` (`target_rr_cap=7.5` when present); enforce system-wide limits chronologically. In `hitl/replay_ledger.py`: atomic temp-file swap writes matching `AccountRiskManager.save()` pattern.

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest app/tests/test_replay_forensics.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hitl/replay_forensics.py hitl/replay_ledger.py app/tests/test_replay_forensics.py
git commit -m "feat(replay): add SMC forensic scanner, $2000/$20 risk governor, and marked co-trade ledger"
```

---

### Task 4: Tornado HTTP API & Static Server (`hitl/replay_server.py`)

**Files:**
- Create: `hitl/replay_server.py`
- Test: `app/tests/test_replay_server_and_ledger.py`

**Interfaces:**
- Consumes: `ReplayDataManager`, `run_bot_scan`, `simulate_custom_trade`, `CoBacktestLedger`, `AgentifyFeedbackStore`
- Produces: Tornado `Application` (`make_app(data_mgr, ledger, fb_store, static_dir)`) binding `127.0.0.1:8765` with routes:
  - `GET /api/catalog`
  - `GET /api/candles`
  - `GET /api/bot-scan`
  - `POST /api/simulate-trade`
  - `GET /api/co-trades`, `POST /api/co-trades`, `PATCH /api/co-trades/([^/]+)`, `DELETE /api/co-trades/([^/]+)`
  - `GET /api/feedback`, `POST /api/feedback`, `DELETE /api/feedback/([^/]+)`
  - `POST /api/sync-mt5`
  - Catch-all static handler serving `web_replayer/dist/index.html`

- [ ] **Step 1: Write failing async HTTP tests in `app/tests/test_replay_server_and_ledger.py`**

Use `tornado.testing.AsyncHTTPTestCase`:
- `test_catalog_and_candles_endpoints`: Asserts `GET /api/catalog` returns 6 symbols and `GET /api/candles?symbol=XAUUSD_o&tf=15M&start=...&end=...&replay_to=...` returns causal candles.
- `test_bot_scan_and_simulate_and_co_trade_crud`: Calls `GET /api/bot-scan` on `2026-11-11`, posts a `HUMAN_EDITED_BOT` entry to `/api/co-trades`, verifies `GET /api/co-trades` persists `origin="HUMAN_EDITED_BOT"`, deletes it, and checks 200 status codes.
- `test_agentify_feedback_endpoint_persists_case`: Calls `POST /api/feedback` with a missed-setup payload and asserts response returns `case.id` + `prompt_markdown` containing asset, timestamp, and screener state.
- `test_oversized_m1_range_returns_bounded_200`: Queries 30 days of `1M` and weekend date range -> asserts HTTP 200 with `truncated=True` / empty array safely.

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest app/tests/test_replay_server_and_ledger.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'hitl.replay_server'`).

- [ ] **Step 3: Implement `hitl/replay_server.py`**

Run CPU/pandas-heavy calls cleanly without crashing Tornado; add clean JSON error handling (400 on missing params, 404 on unknown trade ID); configure permissive localhost CORS headers (`127.0.0.1` / `localhost`) for Vite dev HMR mode; include `__main__` entrypoint (`--port 8765`, `--no-browser`, `webbrowser.open`).

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest app/tests/test_replay_server_and_ledger.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add hitl/replay_server.py app/tests/test_replay_server_and_ledger.py
git commit -m "feat(replay): add Tornado REST server for multi-asset visual co-backtesting"
```

---

### Task 5: React + Vite + `lightweight-charts` Frontend Scaffold & Core Charting (`web_replayer/`)

**Files:**
- Create: `web_replayer/package.json`
- Create: `web_replayer/tsconfig.json`
- Create: `web_replayer/vite.config.ts`
- Create: `web_replayer/index.html`
- Create: `web_replayer/src/types/replay.ts`
- Create: `web_replayer/src/utils/coTraderLogic.ts`
- Create: `web_replayer/src/api/client.ts`
- Create: `web_replayer/src/chart/primitives.ts`
- Create: `web_replayer/src/components/ReplayChart.tsx`
- Test: `web_replayer/src/__tests__/coTraderLogic.test.ts`

**Interfaces:**
- Consumes: Tornado REST endpoints (`/api/catalog`, `/api/candles`, `/api/bot-scan`)
- Produces: TypeScript types matching backend JSON; `coTraderLogic.ts` helpers (`formatClockTick(srvEpoch, mode)`, `computeTradeRR(entry, sl, tp, dir)`, `checkRiskLimitUSD(symbol, entry, sl, lot, maxRiskUsd)`, `maskBlindReplayTrade(trade, replayTo)`); `ReplayChart` component embedding `lightweight-charts` with independent time/price scaling (`handleScale` + price axis vertical drag), custom `ISeriesPrimitive`s rendering Killzones, incremental Asian bounds, FVG/Breaker rectangles, sweep flags, and draggable Entry/SL/TP Position Box handles (`onDraftTradeChange`).

- [ ] **Step 1: Scaffold Vite + React + TS project & install `lightweight-charts` (+ `vitest` / `lucide-react`)**

Run inside `web_replayer/`:
```bash
npm create vite@latest . -- --template react-ts
npm install lightweight-charts lucide-react
npm install -D vitest
```
Configure `vite.config.ts` proxy `/api -> http://127.0.0.1:8765` for local dev and clean relative base build into `web_replayer/dist/`.

- [ ] **Step 2: Write unit tests for pure chart/co-trade coordinate & R:R helper logic (`web_replayer/src/__tests__/coTraderLogic.test.ts`)**

Test: time-zone clock formatters (`Tehran UTC+3:30`, `UTC`, `MT5 Server`), R:R calculation from Entry/SL/TP (`(tp - entry)/(entry - sl)`), `$20` compliance calculation (`riskPts * pipVal > 20.0`), and blind-replay anti-spoiler filter (hiding `exit_time > replayTo` and truncating Bot scorecard metrics up to `replayTo`).

- [ ] **Step 3: Run tests to verify failure, then implement `types/replay.ts`, `utils/coTraderLogic.ts`, `api/client.ts`, `chart/primitives.ts`, and `ReplayChart.tsx`**

Run: `npx vitest run` -> FAIL before implementation -> implement files -> Run: `npx vitest run` -> PASS.

- [ ] **Step 4: Verify TypeScript compilation & bundle build**

Run: `npm run build` inside `web_replayer/`
Expected: Clean `dist/` bundle with zero TypeScript errors.

- [ ] **Step 5: Commit**

```bash
git add web_replayer/
git commit -m "feat(web_replayer): scaffold React + lightweight-charts interactive chart with TV zoom & primitives"
```

---

### Task 6: Replay Transport, Bot Brain Inspector, Co-Trade Scorecard & Agentify Feedback Bridge (`web_replayer/src/`)

**Files:**
- Create: `web_replayer/src/components/BotBrainPanel.tsx`
- Create: `web_replayer/src/components/ScorecardPanel.tsx`
- Create: `web_replayer/src/components/AgentifyFeedbackPanel.tsx`
- Modify: `web_replayer/src/App.tsx`
- Modify: `web_replayer/src/components/ReplayChart.tsx`
- Modify: `docs/SYSTEM_EXECUTION_MIRROR.md` (Section 34 updated to v2 workbench architecture)
- Test: `app/tests/test_replay_end_to_end.py`

**Interfaces:**
- Consumes: `api/client.ts` (`/api/co-trades`, `/api/simulate-trade`, `/api/feedback`, `/api/sync-mt5`), `ReplayChart.tsx`
- Produces: Complete multi-panel workbench (`App.tsx`) featuring:
  - Asset Switcher (`XAUUSD_o`, `GBPUSD_o`, `NQ`, `SPX`, `YM`, `BTCUSD` + `[Sync MT5]`), Date Range & Jump-to-Date selector, 6 Timeframe switcher (`1M | 5M | 15M | 1H | 4H | 1D`), Clock Toggle (`Tehran | UTC | MT5`), Screener Clock Mode toggle (`true_tehran | live_legacy`), Blind Replay controls (`Select Replay Cutoff`, `Play/Pause`, `-1/+1`, `1x-20x`, Scrubber).
  - Interactive `+ Long Setup` / `+ Short Setup` position drawing + Bot trade `"Clone & Adjust"` action opening editable draggable Entry/SL/TP handles and persisting marked setups (`HUMAN_PROPOSED`, `HUMAN_EDITED_BOT`) into `hitl/memory/visual_co_backtest_ledger.json`.
  - Side-by-side Scorecard filtering cleanly by origin (`BOT`, `HUMAN_PROPOSED`, `HUMAN_EDITED_BOT`) with anti-spoiler truncation when Blind Replay is active.
  - **Agentify Feedback Inspector**: One-click capture at any bar or active trade (`MISSED_SETUP`, `BOT_TRADE_EDIT`, `VETO_DISAGREEMENT`, `NOTE`) writing `hitl/memory/visual_feedback_cases.json` and copying the structured Antigravity handoff prompt straight to clipboard.

- [ ] **Step 1: Implement `BotBrainPanel.tsx`, `ScorecardPanel.tsx`, `AgentifyFeedbackPanel.tsx`, and wire `App.tsx`**

Keep components modular and concise; ensure anti-spoiler mode masks unreached trade exits/outcomes when `blindReplay && replayTo < trade.exit_time`.

- [ ] **Step 2: Build production frontend bundle (`web_replayer/dist/`)**

Run: `npm run build` inside `web_replayer/`
Expected: Clean `dist/index.html` and JS assets generated with zero warnings/errors.

- [ ] **Step 3: Write & run end-to-end integration test (`app/tests/test_replay_end_to_end.py`)**

Test Tornado app serving built `dist/index.html` on `/`, full workflow (`GET /api/catalog` -> `GET /api/candles` on `1M`/`1H` -> `GET /api/bot-scan` -> `POST /api/simulate-trade` -> `POST /api/co-trades` -> `POST /api/feedback`), asserting `hitl/memory/` temp fixtures parse cleanly. Also update Section 34 of `docs/SYSTEM_EXECUTION_MIRROR.md`.

Run: `pytest app/tests/test_evaluator_max_risk.py app/tests/test_replay_data.py app/tests/test_replay_forensics.py app/tests/test_replay_server_and_ledger.py app/tests/test_replay_end_to_end.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Live Server Smoke Check**

Start `python hitl/replay_server.py --no-browser` briefly, verify HTTP 200 on `http://127.0.0.1:8765/` and `http://127.0.0.1:8765/api/catalog`, verify `Nov 10` + `Nov 11` Gold candles + `SETUP-ARCH-001` load cleanly, and stop test server cleanly.

- [ ] **Step 5: Commit**

```bash
git add web_replayer/ hitl/replay_server.py app/tests/test_replay_end_to_end.py docs/SYSTEM_EXECUTION_MIRROR.md
git commit -m "feat(workbench): complete Visual Co-Backtester React UI & Agentify feedback loop"
```
