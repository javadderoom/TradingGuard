# TradingGuard Backtesting Integrity & Cryptographic Governance Rules

> **Status**: ACTIVE & BINDING SYSTEM LAW  
> **Effective Date**: 2026-11-19  
> **Enforcement**: Automated via `app/tests/test_backtest_integrity.py` and Pre-Commit CI.

---

## 1. Core Binding Governance Mandates

### 1.1 Single Simulator Mandate
- **Rule**: Custom trade-simulation loops inside individual research scripts, seasonal notebooks, or portfolio auditors are strictly forbidden.
- **Implementation**: Every backtest, benchmark, and holdout evaluation MUST route order execution through the canonical, audited simulator: `hitl/backtest/evaluator.py::evaluate_council_decision`.
- **AST Linter**: Any script in `hitl/backtest/` containing an ad-hoc loop inspecting `hit_sl` or `hit_tp` outside `evaluator.py` without an explicit `# STATUS: DEPRECATED_UNVERIFIABLE` header will trigger an immediate build/test failure.

### 1.2 No Artifact, No Claim Mandate
- **Rule**: Reporting any Net R, Win Rate, Profit Factor, Sharpe Ratio, or Expectancy in git commit messages, documentation, or chat responses without a saved, reproducible `trade_ledger.csv` and `run_manifest.json` on disk is strictly forbidden.
- **Proof Requirement**: If an execution cannot be reproduced byte-for-byte from raw data to CSV output, the claim is treated as unverified and mathematically invalid.

### 1.3 Mandatory Unfiltered Baseline Mandate
- **Rule**: Whenever any strategy report applies session filters, archetype pruning, volatility bans, or trend-regime gates, the **unfiltered baseline** over the exact same symbol and date universe MUST be presented alongside the filtered result.
- **In-Sample Tuning Taint**: Any filter or rule modification chosen after inspecting performance across a specific date range permanently classifies that date range as `IN_SAMPLE_TUNED`.

### 1.4 Strict Realized vs. Unrealized Split
- **Rule**: Floating positions active at the end of a backtest window (`status == "OPEN_AT_END"`) MUST NEVER be summed into realized Net R, Win Rate, or Profit Factor.
- **Reporting**: Realized metrics must only reflect completed, closed trades with verified exit timestamps. Floating metrics must be segregated under an explicit `Unrealized Floating Equity` section.

---

## 2. Execution & Microstructure Integrity Standards

### 2.1 Symmetric Risk & Live Parity
- **No Asymmetric Clamping**: Evaluators must never clamp losses to `$12.00` while allowing wins to pay their full unconstrained distance.
- **Live MT5 Parity**: If a proposed trade's total structural stop-loss risk (`price_risk_usd + spread_cost + commission`) exceeds `max_risk_usd` ($12.00 at 0.01 lot), the order is immediately rejected:
  ```python
  status = "REJECTED_RISK_CAP"
  realized_pnl_usd = 0.0
  ```
- **Dynamic Lot Scaling**: When variable sizing is used, lot size scales dynamically:
  $$\text{Lot} = \max\left(0.01, \text{round}\left(\frac{\text{Risk}_{\text{USD}}}{\text{Risk}_{\text{Points}} \times \text{PointVal}_{0.01}} \times 0.01, 2\right)\right)$$
  The resulting lot is applied symmetrically to **both** wins, losses, and commissions.

### 2.2 Intrabar Conflict & Same-Bar Fill Blow-Through
- **Pessimistic Mandate**: If an order fills on M1 bar `idx` and the same bar touches Stop Loss, the trade is resolved as `LOSS` on bar `idx`.
- **Zero SL Immunity**: Limit orders are never granted 1-minute immunity on the fill bar.
- **Ratchet Precedence**: Breakeven ratchets arm strictly at the **end** of a bar for subsequent bars (`idx + 1`), preventing same-bar lookahead.

### 2.3 Broker Spread & Commission Realism
- **Spread Model**: Backtests must use authentic broker spreads matching live raw ECN accounts:
  - Gold (`XAUUSD_o`): 22 pts ($0.22)
  - Silver (`XAGUSD_o`): 2.7 cents ($0.027)
  - British Pound (`GBPUSD_o`): 0.6 pips ($0.00006)
  - Euro (`EURUSD_o`): 0.5 pips ($0.00005)
  - Nasdaq 100 (`NQ`): 1.0 point
  - Bitcoin (`BTCUSD`): $0.20
- **Overnight Rollover Widening**: Between `23:45` and `01:05` broker server time (EET/EEST), spreads are multiplied by $5.0\times$ to model real institutional bank liquidity blackouts, and limit order placement is frozen.
- **Lot-Scaled Commission**: Commission scales linearly with volume:
  $$\text{Commission}_{\text{Total}} = \text{Commission}_{0.01} \times \left(\frac{\text{Lot}}{0.01}\right)$$

### 2.4 MT5 Strategy Tester Parity
- **Limit-Only Enforcement**: In `mql5/TradingGuard_Executor.mq5`, if market price has reached or crossed limit entry at `trigger_time`, the order is marked `EXPIRED` and skipped.
- **Zero Market Fallback**: Limit orders must never be converted to Market Orders, ensuring Strategy Tester ("Every tick based on real ticks") mirrors backtest fills identically.

---

## 3. Causal Data Architecture & Three-Vault Partition

### 3.1 Strict Bar-Close Visibility
- A candle `[open_ts, open_ts + tf_seconds)` is visible to screener algorithms if and only if:
  $$\text{decision\_ts} \ge \text{open\_ts} + \text{tf\_seconds}$$
- Forming candles are strictly excluded from closed-bar detectors.
- Daily bars are filtered by `open_ts + 86400 <= decision_ts`, guaranteeing `closed_1d[-1]` is unambiguously **Prior Day (`T-1`)**.

### 3.2 Three-Vault Chronological Data Split

```
+-------------------------------------------------------------------------+
| VAULT 1: DISCOVERY / TRAINING (2025 H1 - 2026 Q1)                       |
| Archetype mining, genetic rule evolution, indicator space exploration. |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| VAULT 2: VALIDATION / CALIBRATION (2026 Q2 - Nov 6, 2026)               |
| Parameter calibration, portfolio orthogonalization, Deflated Sharpe.    |
| All tested rules (N) logged for multiple-testing penalty.               |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| VAULT 3: LOCKED HOLDOUT (2025 H2 OOS & Post-Nov 7, 2026 Forward)        |
| Cryptographically frozen dataset. Zero parameter re-tuning allowed.     |
| Audited strictly via holdout_audit_log.jsonl.                           |
+-------------------------------------------------------------------------+
```

### 3.3 Cryptographic Run Manifest (`run_manifest.json`)
Every formal backtest and benchmark output directory must generate a `run_manifest.json` containing:
1. `git_commit`: Current git `HEAD` SHA.
2. `git_dirty`: Boolean flag indicating uncommitted workspace edits.
3. `code_hashes`: SHA-256 hashes of `evaluator.py`, `fast_screener.py`, `causal_feed.py`, and runner script.
4. `input_hashes`: SHA-256 hashes of all input parquet / data files.
5. `output_hash`: SHA-256 hash of output `trade_ledger.csv`.
6. `parameters`: Dictionary of spread, slippage, commission, max risk, and TTL settings.
7. `candidates_tested_n`: Total number of rules or parameter combinations searched (for Deflated Sharpe evaluation).
