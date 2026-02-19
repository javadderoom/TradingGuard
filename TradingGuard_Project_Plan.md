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

[ Windows App (Python) ]  JSON Bridge [ session.json ]  [ MT5
Expert Advisor ]

Windows App = Behavioral Gatekeeper
Expert Advisor = Execution & Risk Enforcer
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
    -   High-impact USD news
    -   Outside trading hours (11:00-21:00 Tehran)
    -   Daily break (16:20 Tehran)
9.  Read permissions from session.json
10. Write trade results back to session.json
11. Display on-chart status panel

------------------------------------------------------------------------

## Dollar-Based Risk Logic

### Per Trade

-   Maximum loss per trade: $12
-   If floating loss  -12  force close trade
-   EA calculates lot internally
-   Manual lot size input is ignored

### Daily Limits

-   Maximum daily loss: $24
-   Maximum daily profit: $35
-   Maximum trades per day: 3
-   Stop immediately after 2 consecutive losses

### Daily Shutdown Conditions

If any condition is met:

-   Daily loss  -24
-   Daily profit  35
-   2 consecutive losses
-   3 trades reached

Then:

-   Close all open trades
-   Disable trading
-   Signal Windows app to force close MT5

------------------------------------------------------------------------

## Cooldown System

After any trade opens:

-   15-minute lock starts
-   +10 extra minutes if trade closes at a loss
-   Current trade is NOT closed (only prevents new trades)
-   Cooldown persists across EA restarts (via session.json)
-   Display countdown timer on chart

During cooldown:

-   Block new entries
-   Close positions opened BEFORE cooldown started
-   Keep current trade open

------------------------------------------------------------------------

## Bias System

Read from session.json:

-   bias: bullish / bearish / neutral
-   invalidation: price level
-   strict_mode: on/off

Rules:

-   Strict mode blocks opposite direction trades
-   Bias expires after 2 hours OR 3 losses
-   After expiry  disable trading until re-analysis

------------------------------------------------------------------------

## Trading Hours

-   Trading allowed: 11:00 - 21:00 Tehran time (UTC+3:30)
-   Outside these hours: all positions closed, no new trades
-   Display Tehran time on chart panel

## Daily Break

-   Daily break: 16:20 Tehran time (UTC+3:30)
-   Duration: 12 minutes
-   During break: MT5 is killed by Python app
-   Positions NOT closed by EA (app handles MT5 closure)

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
7.  Manage news lock (manual + auto from API)
8.  Maintain session.json
9.  Prevent MT5 reopening after daily shutdown
10. Enforce trading hours (11:00-21:00 Tehran)
11. Enforce daily break (16:20 Tehran)

------------------------------------------------------------------------

## News API Integration

-   Uses JBlanked free API (1 request/day)
-   Fetches high-impact USD news events
-   Auto-locks trading 30 minutes before/after news
-   Caches results to avoid repeated API calls
-   Shows upcoming news in UI

------------------------------------------------------------------------

# 5. Technology Stack

-   Python 3.11+
-   PyQt6 (UI framework)
-   SQLite (daily tracking)
-   JSON file bridge
-   JBlanked News API (free)
-   PyInstaller (compile to .exe)

------------------------------------------------------------------------

# 6. Development Roadmap

## Phase 1 -- MVP (COMPLETED)

-   JSON bridge
-   EA dollar-based enforcement
-   Daily limits
-   20-minute timer
-   Bias input
-   Manual news lock

## Phase 2 -- Behavior Hardening (COMPLETED)

-   Cooldown synchronization
-   Consecutive loss tracking
-   Two red days logic
-   Auto MT5 shutdown
-   Trading hours (11:00-21:00 Tehran)
-   Daily break (16:20 Tehran, 12 min)
-   News API integration

## Phase 3 -- Full Automation (COMPLETED)

-   News API integration
-   Bias expiry automation
-   Strict mode enforcement
-   Session.json state reset fixes

------------------------------------------------------------------------

# 7. Implemented Features

## Risk Management

-   $12 max loss per trade
-   $24 max daily loss
-   $35 max daily profit
-   3 trades max per day
-   2 consecutive losses = shutdown

## Cooldown

-   15 min after trade opens
-   +10 min if trade closes at loss
-   Persists across EA restarts
-   Only closes OLD positions (not current trade)

## Bias & Strict Mode

-   Bullish/Bearish/Neutral selection
-   Strict mode blocks opposite trades
-   Bias expires after 2 hours or 3 losses

## Time Controls

-   Trading hours: 11:00-21:00 Tehran
-   Daily break: 16:20-16:32 Tehran (12 min)
-   20-min pre-session analysis timer

## News Protection

-   Manual news lock toggle
-   Auto lock during high-impact USD news (via API)
-   API key required (free at jblanked.com)

## Session Management

-   Reset button clears daily lock
-   Recovery day after 2 red days
-   MT5 auto-launch and kill
-   Session persists in JSON

------------------------------------------------------------------------

# 8. Non-Negotiable Rules

-   No manual lot control
-   No risk escalation after loss
-   No "just one more trade"
-   No reopening after daily shutdown
-   No bypassing cooldown
-   No override buttons
-   No trading outside hours
-   No trading during daily break

System removes emotional decision power.

------------------------------------------------------------------------

# 9. Final Goal

Create a trading environment where:

-   Impulse is slowed
-   Risk is capped
-   Daily exposure is controlled
-   Emotional escalation is impossible
-   Discipline is automated

This system converts trading from emotional reaction into rule-based
execution.
