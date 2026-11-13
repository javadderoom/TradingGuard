# TradingGuard — How to Run Scripts

## Prerequisites

| Requirement | Details |
| :--- | :--- |
| **Python** | 3.11+ (Windows, 64-bit) |
| **MetaTrader 5** | Installed and logged in to your broker account. Must be running before any MT5-dependent script. |
| **Proxy (v2rayN)** | Running on `127.0.0.1:10808` for Telegram bot connectivity |
| **Working Directory** | Always `g:\Code\TradingGuard` |

### Install Dependencies

```bash
pip install -r requirements.txt
```

Core packages: `PyQt6`, `pytest`, `requests`, `beautifulsoup4`.

Additional packages used across the codebase (install as needed):

```bash
pip install MetaTrader5 pandas numpy tornado Pillow
```

### Environment Variables

The system reads a `.env` file from the project root. Required keys:

| Variable | Purpose | Example |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | Telegram bot API token | `123456:ABC-DEF...` |
| `TELEGRAM_CHAT_ID` | Your Telegram chat ID | `123456789` |
| `TELEGRAM_PROXY` | HTTP proxy for Telegram | `http://127.0.0.1:10808` |
| `DEFAULT_SYMBOL` | Default trading instrument | `XAUUSD_o` |
| `MAX_RISK_USD` | Max risk per trade (USD) | `12.0` |
| `MAX_DAILY_LOSS_USD` | Daily loss circuit breaker | `34.0` |
| `SNAP_API_KEY` | SubQ Snap Decision Engine key | *(optional)* |

---

## 1. Telegram Trade Bot (Primary Live System)

The main entry point for the live trading system. Runs as a long-lived daemon.

```bash
python hitl/bot.py
```

**What it does:**
- Connects to Telegram as `@TradingGuard2Bot`
- Provides interactive commands: `/chart`, `/buylimit`, `/selllimit`, `/orders`, `/positions`, `/status`, `/cancel`
- Runs background watchdog for momentum cancellation and stale order reminders
- Enforces the \$12 risk cap and daily loss limits

**Requires:** MetaTrader 5 running, Telegram proxy active, `.env` configured.

---

## 2. Live Market Radar (Autonomous Scanner)

The radar is integrated into the bot and starts automatically. It can also be invoked programmatically:

```python
from hitl.live_radar import LiveMarketRadar
radar = LiveMarketRadar(mt5_engine, telegram_client, council_fn)
radar.start()
```

**What it does:**
- Monitors live MT5 feeds during London and NY killzones
- Detects liquidity sweeps and Market Structure Shifts (MSS)
- Autonomously captures MTF charts, convenes the AI Council, and dispatches trade cards to Telegram

**Requires:** MetaTrader 5 running, bot active.

---

## 3. Desktop GUI Application

```bash
python app/main.py
```

**What it does:**
- Launches the PyQt6 dark-themed desktop dashboard
- Provides session widgets, bias panels, trade checklists, news lock, and analysis views

**Requires:** `PyQt6` installed.

---

## 4. Web Replay Server (Agentify Chart UI)

```bash
python hitl/replay_server.py --port 8765
```

Or to suppress auto-opening the browser:

```bash
python hitl/replay_server.py --port 8765 --no-browser
```

**What it does:**
- Tornado HTTP server serving the Agentify web replayer at `http://127.0.0.1:8765`
- REST API endpoints: `/api/catalog`, `/api/candles`, `/api/bot-scan`, `/api/simulate-trade`, `/api/co-trades`, `/api/feedback`, `/api/sync-mt5`
- Serves the built Vue.js SPA from `web_replayer/dist/`

**Requires:** Cached parquet data in `backtest_results/cache/`. MetaTrader 5 for live sync.

### Building the Web Frontend (if needed)

```bash
cd web_replayer
npm install
npm run build
```

---

## 5. Data Caching Scripts

These scripts download historical data from MT5 and store it as Parquet files in `backtest_results/cache/`. **Run these first before any backtest.**

| Script | Assets Cached | Command |
| :--- | :--- | :--- |
| `hitl/backtest/cache_fx_metals_2026.py` | Gold & GBPUSD (M1, M5, H1, D1) | `python hitl/backtest/cache_fx_metals_2026.py` |
| `hitl/backtest/cache_nq_data.py` | Nasdaq 100 | `python hitl/backtest/cache_nq_data.py` |
| `hitl/backtest/cache_nq_extended.py` | Nasdaq 100 extended range | `python hitl/backtest/cache_nq_extended.py` |
| `hitl/backtest/cache_nq_summer_2026.py` | Nasdaq 100 summer season | `python hitl/backtest/cache_nq_summer_2026.py` |
| `hitl/backtest/cache_btcusd_data.py` | Bitcoin | `python hitl/backtest/cache_btcusd_data.py` |
| `hitl/backtest/cache_btcusd_summer_data.py` | Bitcoin summer season | `python hitl/backtest/cache_btcusd_summer_data.py` |
| `hitl/backtest/cache_indices_data.py` | SPX, YM indices | `python hitl/backtest/cache_indices_data.py` |

**Requires:** MetaTrader 5 running and logged in.

> [!IMPORTANT]
> Always run the relevant cache script before executing backtests. Scripts read from `backtest_results/cache/` and will fail if the parquet files don't exist.

---

## 6. Backtest Runners

All backtests run from the project root directory. They read cached parquet data (no MT5 connection needed at runtime).

### 6.1 Master Production Portfolio Audit (Full-Year)

```bash
python hitl/backtest/master_production_portfolio_audit.py
```

Simulates all ratified archetypes (ARCH-001 through ARCH-014) across 175+ trading days on Gold & GBPUSD.

### 6.2 Multi-Day Historical Council Backtest

```bash
python hitl/backtest/run_backtest.py
```

Orchestrates end-to-end walk-forward simulations: slices rates at session milestones, renders MTF charts, invokes the AI Council, and simulates M1 execution.

### 6.3 Single-Day Backtest (Today)

```bash
python hitl/backtest/run_today_backtest.py
```

Runs the full pipeline on Gold for a single day. **Requires:** MetaTrader 5 running (reads live M1 data).

### 6.4 Asset-Specific Seasonal Audits

| Script | Description |
| :--- | :--- |
| `hitl/backtest/gold_spring_2month_audit.py` | Gold spring season |
| `hitl/backtest/gold_winter_2month_audit.py` | Gold winter season |
| `hitl/backtest/gold_oos_2month_audit.py` | Gold out-of-sample |
| `hitl/backtest/gbpusd_spring_2month_audit.py` | Cable spring season |
| `hitl/backtest/gbpusd_summer_2month_audit.py` | Cable summer season |
| `hitl/backtest/gbpusd_autumn_2month_audit.py` | Cable autumn season |
| `hitl/backtest/gbpusd_winter_2month_audit.py` | Cable winter season |
| `hitl/backtest/nq_2month_audit.py` | Nasdaq 100 audit |
| `hitl/backtest/nq_summer_2month_audit.py` | Nasdaq 100 summer |
| `hitl/backtest/btcusd_long_term_audit.py` | Bitcoin long-term |
| `hitl/backtest/btcusd_summer_audit.py` | Bitcoin summer |
| `hitl/backtest/spx_3month_audit.py` | S&P 500 audit |
| `hitl/backtest/ym_3month_audit.py` | Dow Jones (YM) audit |

Run any with:

```bash
python hitl/backtest/<script_name>.py
```

### 6.5 Annual 4-Season Master Synthesis

```bash
python hitl/backtest/gold_annual_4season_master_synthesis.py
python hitl/backtest/gbpusd_annual_4season_master_synthesis.py
```

### 6.6 2025 Out-of-Sample Benchmark

```bash
python hitl/backtest/run_2025_oos_production_benchmark.py
```

---

## 7. Quant Engine (Autonomous Rule Discovery)

```bash
python hitl/quant_engine/engine_runner.py
```

**What it does:**
1. Ingests cached market data
2. Constructs a mathematical state space
3. Splits into In-Sample / Out-of-Sample with purged gap
4. Autonomously evolves and discovers quantitative trading rules
5. Walk-Forward cross-validation with overfitting penalties
6. Cross-asset stress testing
7. Registers ratified archetypes and exports audit reports

**Output:** `backtest_results/quant_discovery/`

### Other Quant Engine Scripts

| Script | Purpose |
| :--- | :--- |
| `hitl/quant_engine/annual_backtest_runner.py` | Annual backtest over discovered rules |
| `hitl/quant_engine/annual_discovery_runner.py` | Annual discovery pipeline |
| `hitl/quant_engine/run_consolidated_annual_portfolio.py` | Consolidated portfolio across all assets |

---

## 8. MT5 Strategy Tester Bridge

### Export Orders to MT5

```bash
python hitl/backtest/export_master_orders_schedule.py
```

Exports all production trades into `orders_schedule.csv` for the MT5 Strategy Tester EA.

### Asset-Specific Schedule Exports

```bash
python hitl/backtest/export_gold_quant_schedule.py
python hitl/backtest/export_cable_quant_schedule.py
python hitl/backtest/export_btc_quant_schedule.py
python hitl/backtest/export_nq_schedule.py
```

### Execute in MT5 Native Tester

```bash
python hitl/backtest/run_mt5_native_backtest.py
python hitl/backtest/execute_today_mt5_tester.py
```

**Requires:** MetaTrader 5 running with the TradingGuard EA loaded.

---

## 9. Research & Analysis Scripts

### Structural Analysis

| Script | Purpose |
| :--- | :--- |
| `hitl/backtest/double_mss_quant_audit.py` | Double MSS pattern audit |
| `hitl/backtest/nested_double_mss_audit.py` | Nested Double MSS patterns |
| `hitl/backtest/diagnose_trend_inversions.py` | Trend inversion diagnostics |
| `hitl/backtest/diagnose_london_to_ny_dynamics.py` | London→NY session transition |
| `hitl/backtest/discover_ny_confluence_edge.py` | NY confluence edge research |

### Optimization Scripts

| Script | Purpose |
| :--- | :--- |
| `hitl/backtest/optimize_gold_setup_a.py` | Gold setup parameter optimization |
| `hitl/backtest/optimize_trend_oracle.py` | Trend Oracle model tuning |
| `hitl/backtest/optimize_cable_trend_policy.py` | Cable trend policy calibration |
| `hitl/backtest/optimize_nq_trend_policy.py` | Nasdaq trend policy calibration |
| `hitl/backtest/trade_management_optimizer.py` | Trade management (R:R, BE) optimization |
| `hitl/backtest/optimize_btcusd_portfolio.py` | Bitcoin portfolio optimization |

### Screener Impact Audits

| Script | Purpose |
| :--- | :--- |
| `hitl/backtest/audit_trend_screener_impact.py` | Trend Oracle screener impact |
| `hitl/backtest/audit_gbpusd_screener_impact.py` | Cable screener impact |
| `hitl/backtest/audit_nq_screener_impact.py` | Nasdaq screener impact |

---

## 10. Test Suite

```bash
pytest app/tests/ -v
```

Individual test files:

```bash
pytest app/tests/test_evaluator_max_risk.py -v
pytest app/tests/test_review_engine.py -v
pytest app/tests/test_replay_server_and_ledger.py -v
pytest app/tests/test_quant_engine.py -v
```

---

## 11. Scratch Scripts (Ad-Hoc Research)

Temporary research scripts live in `scratch/`. They are not part of the production pipeline.

```bash
python scratch/mine_sweep_vs_bos_gold.py          # Mine sweep vs BOS events
python scratch/analyze_sweep_vs_bos_stats.py       # Statistical analysis
python scratch/validate_2025_oos_breaches.py       # 2025 OOS validation
python scratch/backtest_sweep_trend_aligned.py     # Pro-trend sweep backtest
python scratch/backtest_bos_continuation.py        # BOS continuation backtest
```

---

## Quick Reference

| Task | Command |
| :--- | :--- |
| **Start live bot** | `python hitl/bot.py` |
| **Start web UI** | `python hitl/replay_server.py` |
| **Start desktop GUI** | `python app/main.py` |
| **Cache Gold/Cable data** | `python hitl/backtest/cache_fx_metals_2026.py` |
| **Full portfolio audit** | `python hitl/backtest/master_production_portfolio_audit.py` |
| **Run quant discovery** | `python hitl/quant_engine/engine_runner.py` |
| **Export MT5 schedule** | `python hitl/backtest/export_master_orders_schedule.py` |
| **Run tests** | `pytest app/tests/ -v` |

> [!TIP]
> All scripts should be run from the project root `g:\Code\TradingGuard`. Most backtest scripts automatically insert the project root into `sys.path`.

> [!WARNING]
> Scripts that depend on live MT5 data (`run_today_backtest.py`, `cache_*.py`, `sync-mt5` API) require MetaTrader 5 to be running and logged in. If MT5 is not initialized, they will exit with an error.
