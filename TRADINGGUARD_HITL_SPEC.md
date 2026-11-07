# TradingGuard HITL: Human-In-The-Loop Semi-Automated Trading System
## System Architecture & Technical Specification

---

## 1. Executive Summary & Philosophy

The **TradingGuard HITL (Human-In-The-Loop)** system is a disciplined, remote trading assistant designed to bridge the gap between human market insight and machine execution reliability. 

### Core Problems Addressed:
1. **Psychological Pitfalls**: Eliminates execution hesitation, fear of pulling the trigger, greed, and revenge trading by delegating cold execution and hard-coded risk math to a computer.
2. **Physical Constraints**: Accommodates traders with full-time jobs or obligations away from the workstation by providing a responsive remote bridge (Telegram) and automated monitoring.
3. **Execution Latency Elimination**: Uses **Limit Orders** exclusively, rendering network lag and communication delays completely harmless to entry pricing.

---

## 2. High-Level Architecture Diagram

```
+---------------------------------------------------------------------------------+
|                                 HOME WORKSTATION                                |
|                                                                                 |
|  +---------------------------+             +---------------------------------+  |
|  | Google Chrome             |             | MetaTrader 5 Terminal           |  |
|  | (TradingView Web App)     |             | (LiteFinance - Demo/Live)       |  |
|  +-------------+-------------+             +----------------+----------------+  |
|                | (Win32 GDI/PrintWindow)                    | (Native Python API|
|                v                                            v  MetaTrader5)     |
|  +---------------------------------------------------------------------------+  |
|  |                          TRADINGGUARD CORE ENGINE                         |  |
|  |                                                                           |  |
|  |  [ Chart Capture Service ]        [ Momentum / ATR Watchdog ]             |  |
|  |  Captures background 1080p         Samples ticks/M1 candles;              |  |
|  |  TradingView chart canvas.         Auto-cancels orders on sharp moves.    |  |
|  |                                                                           |  |
|  |  [ MT5 Execution Engine ]         [ Discipline & Risk Guard ]             |  |
|  |  Places/Cancels Limit Orders.      Validates $12 max risk ceiling.        |  |
|  |  Submits broker-side SL/TP.        Enforces daily loss & trade limits.    |  |
|  +-------------------------------------+-------------------------------------+  |
|                                        ^                                        |
|                                        | (Encrypted TLS / Bot API)              |
+----------------------------------------|----------------------------------------+
                                         v
+---------------------------------------------------------------------------------+
|                                 MOBILE TELEGRAM                                 |
|                                                                                 |
|  1. Periodic / On-Demand Chart Snapshots delivered to your smartphone.          |
|  2. User reviews chart and issues Limit Command (e.g. `/buy_limit ...`).        |
|  3. Automated Notification if Limit Order is cancelled due to sharp momentum.   |
|  4. Expiry / Inactivity Reminder after configured timeout: [Keep] / [Cancel].   |
|  5. Trade outcome updates (Set & Forget).                                       |
+---------------------------------------------------------------------------------+
```

---

## 3. Detailed Component Specifications

### 3.1. Remote Interface & Communication (Telegram Bridge)
* **Authentication & Whitelist**: Strictly restricted to a single authenticated Telegram `chat_id`. Any unauthorized request is dropped and logged.
* **On-Demand Snapshots**: User can query `/chart [symbol]` anytime; system captures the current TradingView chart in the background and delivers an uncompressed photo within 3–5 seconds.
* **Scheduled Snapshots**: Automatically delivers chart updates at predetermined candle closes (e.g., M15/H1 close) during user-specified active hours.

### 3.2. Order Protocol & Risk Architecture
* **Order Type**: Exclusively **Limit Orders** (`BUY_LIMIT`, `SELL_LIMIT`).
  * *Rationale*: Market orders suffer from price drift and slippage over mobile-to-PC latency. Limit orders guarantee exact or better execution price regardless of communication delay.
* **Lot Sizing & Risk Ceiling**:
  * Base Lot Size: Minimum broker lot (`0.01`).
  * Risk Ceiling per Trade: Fixed dollar maximum (e.g., **$12.00**).
  * **Pre-Execution Invalidation Check**:
    $$\text{Expected Loss} = \text{Stop Distance} \times \text{Tick Value} \times \text{Lot Size}$$
    If $\text{Expected Loss} > \$12.00$ at minimum lot (`0.01`), the order is **REJECTED** immediately. The user must refine the setup with a tighter stop loss before re-submitting.
* **Trade Management Policy**: **Strictly Set & Forget**.
  * Both Stop Loss (SL) and Take Profit (TP) are submitted as hard broker-side parameters simultaneously with the limit order.
  * No partial closes (irrelevant at minimum lot size).
  * No discretionary mid-trade interference. The position resolves cleanly at either SL or TP.

### 3.3. Automated Momentum Guard (Sharp Move Veto)
* **Objective**: Protect pending limit orders from adverse price momentum (e.g., high-velocity sell-offs or buy-surges driven by unexpected news or liquidity runs).
* **Detection Mechanism**:
  * An automated background loop inspects active pending limit orders every 2 to 5 seconds.
  * Evaluates incoming price velocity relative to recent baseline volatility (Average True Range - ATR).
  * **Trigger Conditions**:
    1. **Candlestick Size Explosion**: Recent candle(s) moving directly toward the limit order exceed **$2.0 \times \text{ATR}$**.
    2. **Spread Expansion**: Broker spread widens beyond $3\times$ normal baseline (indicating news release or liquidity void).
* **Execution**:
  * **100% Fully Automated**: The system cancels the pending limit order directly on MT5 in milliseconds via `TRADE_ACTION_REMOVE`.
  * **Alert Notification**: Sends an immediate alert to Telegram:
    > ⚠️ **Limit Order Automatically Cancelled**  
    > **Symbol**: `XAUUSD_o` | **Type**: `BUY LIMIT` @ `3870.00`  
    > **Reason**: Sharp directional momentum detected ($>2\times$ ATR expansion towards entry).

### 3.4. Time-Based Inactivity Reminder (TTL Notification)
* **Objective**: Prevent "stale" limit orders from remaining active indefinitely after the market context or session narrative has shifted.
* **Mechanism**:
  * If a pending limit order has not been filled after a preconfigured time window (e.g., 60 minutes or at session close):
  * The system does **NOT** cancel silently. Instead, it sends an interactive Telegram prompt:
    > ⏳ **Pending Order Review Reminder**  
    > **Symbol**: `XAUUSD_o` | **Limit**: `3870.00`  
    > **Age**: 60 minutes active without fill.  
    > `[ ❌ Cancel Order ]`   `[ 👁 Keep Active ]`
  * Tapping `[ Cancel Order ]` drops the order from MT5 instantly.

---

## 4. Failsafe & Operational Guardrails

| Risk Vector | Potential Consequence | Engineering Mitigation |
| :--- | :--- | :--- |
| **Power or ISP Outage** | Home PC loses connection while in an open trade. | **Broker-side SL/TP**: Hard SL and TP exist directly on LiteFinance servers; position is protected regardless of PC status. |
| **VPN / Proxy Drop** | Telegram messages fail to deliver. | **Heartbeat Watchdog**: Periodic pulse notification. If no heartbeat within 15 min, user knows local connection requires attention. |
| **Daily Loss Limit Hit** | Risk of revenge trading via mobile. | **Hard Daily Lock**: TradingGuard blocks any new limit orders once cumulative daily loss hits the daily threshold (e.g., $34.00). |
| **Syntax / Typing Error** | Accidental invalid price or misplaced SL. | **Strict Regex & Semantic Validator**: Ensures price, SL, and TP logic align (e.g., Buy Limit must have entry < market, SL < entry, TP > entry). Rejects anomalies instantly. |

---

## 5. Technical Stack

* **Platform / OS**: Windows 11 (Desktop Console Session).
* **Language / Runtime**: Python 3.14.x.
* **Broker Interface**: Native `MetaTrader5` Python API (connected to LiteFinance Terminal, Account `91235314`).
* **Chart Capture Engine**: Custom Win32 GDI / `PrintWindow` background renderer for Google Chrome / TradingView.
* **Remote Gateway**: `python-telegram-bot` (Asyncio polling / Long-polling with local proxy/VPN support).
* **Local Data & Audit**: SQLite (`tradingguard.db`) for logging all snapshots, orders, cancellations, and outcomes.

---

## 6. Phased Implementation Roadmap

1. **Phase 1: Telegram Bot & Background Capture Service**
   * Deploy dedicated Telegram bot with whitelist security.
   * Wire the Win32 TradingView Chrome background snapshot engine to `/chart` command.
2. **Phase 2: MT5 Execution Engine & Math Validator**
   * Implement Limit Order placement with hard SL/TP via `MetaTrader5` API.
   * Implement mathematical $12 risk cap enforcement and rejection logic.
3. **Phase 3: Watchdog Services**
   * Build the **Automated Momentum Guard** (ATR + Spread monitor with auto-cancellation).
   * Build the **Time-Based Inactivity Reminder** (TTL interactive button).
4. **Phase 4: Dry-Run & Paper Validation**
   * Live testing on LiteFinance Demo account across multiple market sessions.
