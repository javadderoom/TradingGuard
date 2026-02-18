# TradingGuard System

## MT5 Expert Advisor + Windows Control App

### Full Development Plan

------------------------------------------------------------------------

# 1. Project Objective

Build a behavioral enforcement system that:

-   Prevents overtrading
-   Prevents revenge trading
-   Prevents lot escalation
-   Enforces strict daily profit/loss limits
-   Forces structured pre-session analysis
-   Blocks trading during high-risk volatility moments
-   Prevents reopening MT5 after session termination
-   Enforces recovery day after two consecutive red days

This system is NOT a strategy engine. It is a discipline and risk
enforcement system.

------------------------------------------------------------------------

# 2. System Architecture

\[ Windows App (Python) \] ↓ JSON Bridge \[ session.json \] ↓ \[ MT5
Expert Advisor \]

Windows App = Behavioral Gatekeeper\
Expert Advisor = Execution & Risk Enforcer\
JSON File = Communication Bridge

------------------------------------------------------------------------

# 3. Expert Advisor (MT5) -- Detailed Plan

## Core Responsibilities

The EA must:

1.  Enforce fixed dollar risk per trade
2.  Enforce daily loss limit
3.  Enforce daily profit lock
4.  Enforce cooldown logic
5.  Enforce max trades per day
6.  Enforce stop after 2 consecutive losses
7.  Enforce bias direction rules
8.  Block trading during:
    -   London open 1m candle
    -   New York open 1m candle
    -   High-impact USD news 1m candle
9.  Read permissions from session.json
10. Write trade results back to session.json
11. Display on-chart status panel

------------------------------------------------------------------------

## Dollar-Based Risk Logic

### Per Trade

-   Maximum loss per trade: \$12
-   If floating loss ≤ -12 → force close trade
-   EA calculates lot internally
-   Manual lot size input is ignored

### Daily Limits

-   Maximum daily loss: \$24
-   Maximum daily profit: \$35
-   Maximum trades per day: 3
-   Stop immediately after 2 consecutive losses

### Daily Shutdown Conditions

If any condition is met:

-   Daily loss ≤ -24
-   Daily profit ≥ 35
-   2 consecutive losses
-   3 trades reached

Then:

-   Close all open trades
-   Disable trading
-   Signal Windows app to force close MT5

------------------------------------------------------------------------

## Cooldown System

After any trade closes:

-   15-minute lock
-   +10 extra minutes if trade was a loss

During cooldown:

-   Block new entries
-   Display countdown timer on chart
-   Ignore manual trade attempts

------------------------------------------------------------------------

## Bias System

Read from session.json:

-   bias: bullish / bearish / neutral
-   invalidation: price level

Rules:

-   Optional strict mode to block opposite direction trades
-   Bias expires after 2 hours OR 3 losses
-   After expiry → disable trading until re-analysis

------------------------------------------------------------------------

# 4. Windows App (Python) -- Detailed Plan

## Core Responsibilities

The Windows App must:

1.  Enforce 20-minute pre-session analysis
2.  Require HTF bias input before trading
3.  Control MT5 launch
4.  Force close MT5 when limits hit
5.  Track daily results
6.  Enforce 2 red days recovery rule
7.  Manage news lock
8.  Maintain session.json
9.  Prevent MT5 reopening after daily shutdown

------------------------------------------------------------------------

# 5. Technology Stack

-   Python 3.11+
-   PyQt6 (UI framework)
-   SQLite (daily tracking)
-   JSON file bridge
-   PyInstaller (compile to .exe)

------------------------------------------------------------------------

# 6. Development Roadmap

## Phase 1 -- MVP

-   JSON bridge
-   EA dollar-based enforcement
-   Daily limits
-   20-minute timer
-   Bias input
-   Manual news lock

## Phase 2 -- Behavior Hardening

-   Cooldown synchronization
-   Consecutive loss tracking
-   Two red days logic
-   Auto MT5 shutdown

## Phase 3 -- Full Automation

-   News API integration
-   Bias expiry automation
-   Strict mode enforcement
-   Auto Windows startup

------------------------------------------------------------------------

# 7. Non-Negotiable Rules

-   No manual lot control
-   No risk escalation after loss
-   No "just one more trade"
-   No reopening after daily shutdown
-   No bypassing cooldown
-   No override buttons

System removes emotional decision power.

------------------------------------------------------------------------

# 8. Final Goal

Create a trading environment where:

-   Impulse is slowed
-   Risk is capped
-   Daily exposure is controlled
-   Emotional escalation is impossible
-   Discipline is automated

This system converts trading from emotional reaction into rule-based
execution.
