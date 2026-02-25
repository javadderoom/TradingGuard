# TradingGuard

TradingGuard is a Windows-based trading discipline system made of two parts:

- A Python desktop app (`PyQt6`) that controls session lifecycle and enforces behavioral rules.
- An MT5 Expert Advisor (EA) that enforces real-time execution/risk rules on the chart.

Both sides sync through a shared JSON file (`session.json`) in MT5 Common Files.

## Purpose

This project is designed to reduce discretionary mistakes by automating guardrails:

- Hard per-trade and daily risk limits.
- Session start gating (analysis timer + bias setup).
- Time-based restrictions (trading window + daily break).
- News lock and bias expiry behavior.
- Forced MT5 shutdown when lock conditions are hit.
- Persistent journaling/history for review and accountability.

## Current Rule Set (From Implementation)

- Max loss per trade: `$12`
- Max daily loss: `$24`
- Max daily profit: `$35`
- Max trades per day: `3`
- Consecutive-loss trigger: `2` losses (starts a 1-hour break)
- Base cooldown after entry: `15 min`
- Extra cooldown after losing close: `+10 min`
- Trading hours: `11:00-21:00` Tehran time
- Daily break: `16:20` Tehran time for `12 min`
- Recovery day: blocked after 2 consecutive red days (based on completed daily rows)

Important: `ANALYSIS_TIMER_MINUTES` is currently set to `1` in `app/config.py` for testing. Set it to `20` for live use.

## Architecture

- Python app
  - UI, session orchestration, MT5 process guard, history and analysis journal.
  - Writes/reads `session.json` via file locking.
  - Persists daily/trade/audit data to `SQLite` (`tradingguard.db`).
- MT5 EA
  - Reads JSON state, enforces risk/time/entry constraints on each tick and trade transaction.
  - Writes trade counters and status back to JSON.
- Shared bridge
  - `session.json` in `%APPDATA%\MetaQuotes\Terminal\Common\Files\session.json`

## Repository Layout

```text
app/
  main.py                 # PyQt entry point
  config.py               # Limits, paths, schedule, env config
  bridge.py               # session.json read/write with locking
  database.py             # SQLite schema + data access
  mt5_controller.py       # launch/kill/check MT5 process
  news_service.py         # high-impact USD news fetch + cache
  ui/                     # Main window + tab widgets
  tests/                  # pytest tests for bridge/database

ea/
  TradingGuard.mq5        # EA entry
  features/*.mqh          # bridge sync, risk logic, events, chart UI

analysis_assets/          # Screenshot journal assets
tradingguard.db           # Local SQLite database file
```

## Python App Features

- Tabs in main window:
  - Analysis: pre-session timer + HTF bias setup.
  - Session: live session metrics + news lock controls + end session.
  - History: performance cards, daily rows, trade ledger, rule violations.
  - Trade Analysis: trade-by-trade notes and screenshot journal (MT5 + TradingView timeframes).
- Session polling (`session.json`) every 2 seconds.
- MT5 guard loop every 5 seconds (prevents reopen after shutdown/recovery lock).
- Auto-handling of stale bridge/session carryover data across session days.

## EA Enforcement Highlights

- Monitors open positions and force-closes when needed:
  - Floating loss exceeds per-trade risk.
  - Lot size exceeds max lot.
  - Strict-mode opposite-bias trade detected.
- Blocks/auto-closes entries when:
  - Session disallows trading.
  - News lock is active.
  - Cooldown is active.
  - Checklist is incomplete (EA-side 4-item checklist).
  - Time is outside allowed hours.
- During configured daily break, the Python MT5 guard keeps MT5 closed.
- Tracks trade closes and updates:
  - `daily_loss_usd`, `daily_profit_usd`, `trades_today`, `consecutive_losses`, `losses_since_bias`, `last_trade_*`.

## Configuration

Primary config is in `app/config.py`.

Key values:

- Risk/session constants (`RISK_PER_TRADE_USD`, `MAX_DAILY_LOSS_USD`, etc.).
- Trading window and daily break constants.
- Paths:
  - `SESSION_JSON_PATH`
  - `DB_PATH`
  - `MT5_EXE_PATH`
- News settings:
  - `NEWS_API_KEY` (env var)
  - `NEWS_PROXY_URL` (optional)
  - `NEWS_TIME_OFFSET_MINUTES` (optional correction)

## Setup

1. Install Python dependencies:

```powershell
pip install -r requirements.txt
```

2. Ensure MT5 path is correct in `app/config.py` (`MT5_EXE_PATH`).

3. (Optional) Set news API key:

```powershell
$env:NEWS_API_KEY="your_key_here"
```

4. Install/compile EA:

- Open `ea/TradingGuard.mq5` in MetaEditor.
- Compile and attach to your target chart in MT5.
- Confirm both EA and app point to the same `session.json` in MT5 Common Files.

5. Run the app:

```powershell
python -m app.main
```

## Session Flow

1. Complete pre-session timer.
2. Set bias/invalidation/strict mode.
3. Start session from app (launches MT5).
4. EA enforces rules while app monitors and records.
5. On shutdown conditions, app and EA lock session and close MT5.
6. Review outcomes in History and Trade Analysis tabs.

## Data Model (High Level)

`session.json` includes fields such as:

- State: `session_active`, `trading_allowed`, `shutdown_signal`, `break_active`, `break_until`
- Risk counters: `daily_loss_usd`, `daily_profit_usd`, `trades_today`, `consecutive_losses`
- Bias/news: `bias`, `invalidation_price`, `strict_mode`, `bias_set_at`, `losses_since_bias`, `bias_expired`, `news_lock`
- Trade info: `cooldown_until`, `last_trade_result`, `last_trade_pnl`, `timestamp`

SQLite tables in `tradingguard.db`:

- `daily_results`
- `trade_events`
- `trade_ledger`
- `violation_log`
- `trade_analysis`

## Testing

Run tests:

```powershell
pytest app/tests -q
```

Current automated tests focus on:

- `SessionBridge` read/write/reset behavior.
- `DailyDatabase` CRUD and stats behavior.

## Platform Notes

- This project is Windows-oriented (`msvcrt` locking, `tasklist`/`taskkill`, MT5 path defaults).
- Time logic uses fixed Tehran offset (`UTC+3:30`).
- If you use non-default MT5 install paths, update config accordingly.
