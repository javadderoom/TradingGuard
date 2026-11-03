# TradingGuard System Rules

## Language Requirement
- **Always respond strictly in English.**
- Do not mix Persian and English in responses, explanations, or analysis summaries.
- Keep all communication clean, professional, and entirely in English.

## Absolute Truthfulness & Zero Reality Distortion Mandate
- **Strictly zero lying, fabrication, or distortion of reality.**
- **Under no circumstances do you have the right to invent data, information, prices, timestamps, or anything whatsoever from yourself.**
- Never invent, assume, or fabricate trade executions, prices, bar timestamps, backtest fills, or PnL outcomes.
- Never state that a trade filled or hit a target unless raw, verified tick/bar data from the broker strictly proves it at the exact wall-clock time.
- If there is a calculation error, timezone confusion, or missing data, state the failure bluntly, transparently, and immediately. Never mask an error with an imaginary winning scenario.
- Any form of reality distortion or hallucinated outcome is completely unacceptable and strictly forbidden.

## Direct Question-Answering Mandate (No Code on Questions)
- **When the user asks a question, answer the question directly in plain text without running or writing code.**
- Do not spawn unnecessary background Python scripts or tool executions when answering questions.
- Address the user's specific inquiry directly, concisely, and transparently based on visible chart facts.

## Authentic Execution Mandate (Real Tests Only, Zero Shortcutting)
- **When the user instructs to test, the test must run strictly and genuinely through the actual automated codebase end-to-end.**
- **Strictly zero manual injection, manual CSV editing, hardcoding of orders, or pretend runs.**
- Every single trade in `orders_schedule.csv` must be the direct, unedited programmatic output of the automated system.
- If the current codebase, screener, or algorithm has a limitation or cannot detect a setup, state the technical limitation bluntly and immediately. Never manually fabricate or insert a trade to simulate success.
- Any attempt to deceive the user or take shortcuts instead of executing the real pipeline is strictly forbidden.

## Dynamic Seasonal Session Clock Mandate (Tehran No-DST vs London/NY DST)
- **Tehran abolished DST permanently (Fixed at UTC+3:30 year-round).**
- **London (UK) and New York (US) change their clocks twice annually for DST.**
- **Winter / Autumn Schedule (Late October / Early November to March):**
  - London Open (08:00 GMT / UTC) = **11:30 Tehran Time** (NOT 10:30).
  - NY Open Forex Killzone (08:00 EST / 13:00 UTC) = **16:30 Tehran Time** (NOT 15:30).
  - NYSE Equities Cash Open (09:30 EST / 14:30 UTC) = **18:00 Tehran Time**.
- **Summer Schedule (Late March to Late October):**
  - London Open (08:00 BST / 07:00 UTC) = **10:30 Tehran Time**.
  - NY Open Forex Killzone (08:00 EDT / 12:00 UTC) = **15:30 Tehran Time**.
  - NYSE Equities Cash Open (09:30 EDT / 13:30 UTC) = **17:00 Tehran Time**.
- **Enforcement**: Never use static hardcoded Tehran hours across different seasons. All session calculations, backtests, and live radar monitors must dynamically resolve via `hitl/backtest/session_clock.py` or standard `ZoneInfo`.

