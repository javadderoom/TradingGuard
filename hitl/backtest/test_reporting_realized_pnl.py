"""Pack 6 verification — synthetic records only, no MT5, no live runs.

Run from the repo root:  python3 hitl/backtest/test_reporting_realized_pnl.py
Covers:
  * summarize_pnl() splits realised vs OPEN_AT_END floating PnL
    (pooled +$38.83 closed vs +$127.48 reported; worst file closed
    -$37.60 reported as +$8.05),
  * BacktestLogger derives the executive-report header from the session
    dataset (not the caller scorecard) and flags mismatches, and shows
    unrealised PnL separately,
  * annual summary builders label breakdown populations (calibrated
    fills only vs all fills),
  * the counterfactual auditor's actual net excludes OPEN_AT_END.
"""
import sys, json, types, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

# --- Stub MetaTrader5 + MT5 engine so hitl modules import on Linux ---
mt5_stub = types.ModuleType('MetaTrader5')
sys.modules['MetaTrader5'] = mt5_stub
mt5eng_stub = types.ModuleType('hitl.mt5_engine')
class _FakeEngine:
    pass
mt5eng_stub.MT5Engine = _FakeEngine
sys.modules['hitl.mt5_engine'] = mt5eng_stub

from hitl.backtest.evaluator import summarize_pnl, is_trade_realized
from hitl.backtest.logger import BacktestLogger
from hitl.counterfactual_auditor import CounterfactualOpportunityAuditor
from hitl.backtest.gold_annual_4season_master_synthesis import build_annual_summary as build_gold_summary
from hitl.backtest.gbpusd_annual_4season_master_synthesis import build_annual_summary as build_gbp_summary

PASS = FAIL = 0
def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}  {detail}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")

def rec(status, pnl, realized=None):
    r = {"status": status, "realized_pnl_usd": pnl}
    if realized is not None:
        r["is_realized"] = realized
    return r

# --- 1. summarize_pnl: worst single file (metals 20261101_075029) ---
# Closed trades net -$37.60; one OPEN XAG trade floating +$45.65.
worst = [rec("LOSS", -40.00), rec("WIN", 2.40), rec("OPEN_AT_END", 45.65)]
s = summarize_pnl(worst)
check("worst file: realised net is -$37.60, not +$8.05",
      s["realized_net_usd"] == -37.60, f"got {s['realized_net_usd']}")
check("worst file: unrealised +$45.65 reported separately",
      s["unrealized_net_usd"] == 45.65 and s["open_trades"] == 1,
      f"got {s['unrealized_net_usd']} / {s['open_trades']} open")
check("worst file: realised gross profit/loss exclude the open trade",
      s["realized_gross_profit_usd"] == 2.40 and s["realized_gross_loss_usd"] == 40.00,
      f"got +{s['realized_gross_profit_usd']} / -{s['realized_gross_loss_usd']}")

# --- 2. summarize_pnl: pooled council ledgers (+$38.83 vs +$127.48) ---
pooled = [rec("WIN", 10.88)] * 35 + [rec("LOSS", -5.43)] * 63
# 35 x 10.88 - 63 x 5.43 = 380.80 - 342.09 = +38.71; top up to the
# exact pooled closed net with one more realised win.
pooled.append(rec("WIN", 0.12))
open_trades = [rec("OPEN_AT_END", 88.65 / 12.0)] * 12  # +$88.65 floating
s2 = summarize_pnl(pooled + open_trades)
check("pooled: realised net is +$38.83 (closed only)",
      s2["realized_net_usd"] == 38.83, f"got {s2['realized_net_usd']}")
check("pooled: unrealised +$88.65 kept out of the realised total",
      s2["unrealized_net_usd"] == 88.65 and s2["open_trades"] == 12,
      f"got {s2['unrealized_net_usd']} / {s2['open_trades']} open")
check("pooled: realised + unrealised still reconciles to +$127.48",
      round(s2["realized_net_usd"] + s2["unrealized_net_usd"], 2) == 127.48)

# --- 3. is_realized flag wins over status; legacy dicts fall back ---
check("is_realized=True honoured even with OPEN_AT_END status",
      is_trade_realized(rec("OPEN_AT_END", 5.0, realized=True)) is True)
check("is_realized=False honoured even with WIN status",
      is_trade_realized(rec("WIN", 5.0, realized=False)) is False)
check("legacy dict without flag falls back to status",
      is_trade_realized(rec("OPEN_AT_END", 5.0)) is False
      and is_trade_realized(rec("WIN", 5.0)) is True)
check("BREAKEVEN with +$0.05 counts as realised gross profit",
      summarize_pnl([rec("BREAKEVEN", 0.05)])["realized_gross_profit_usd"] == 0.05)
check("empty record list sums to zero",
      summarize_pnl([])["realized_net_usd"] == 0.0
      and summarize_pnl([])["realized_profit_factor"] == 0.0)

# --- 4. Logger: header derived from the dataset, not the scorecard ---
DATA = pathlib.Path(__file__).resolve().parents[2] / "backtest_results" / \
    "90day_eurusd_6seat_audit_20261031_233557" / "full_dataset.json"
if DATA.exists():
    d = json.loads(DATA.read_text())
    sessions = d["sessions"]
    lg = BacktestLogger(run_name="probe_pack6")
    zeroed = {"total_sessions": 0, "stand_asides": 0, "orders_approved": 0,
              "filled_trades": 0, "wins": 0, "losses": 0, "win_rate_pct": 0.0,
              "gross_profit_usd": 0.0, "gross_loss_usd": 0.0,
              "net_pnl_usd": 0.0, "profit_factor": 0.0}
    md = lg._generate_markdown_report({}, zeroed, sessions)
    check("logger: zeroed scorecard cannot zero the header (4 orders)",
          "| **Approved Limit Orders** | **4** |" in md)
    check("logger: header shows 2 filled, 1W/1L from the dataset",
          "| **Filled Institutional Trades** | **2 (1W / 1L / 0BE)** |" in md)
    check("logger: header net is realised +$1.33, not scorecard +$2.26",
          "| **Net Realized PnL** | **$+1.33** |" in md)
    check("logger: unrealised +$0.93 shown separately, not in the net",
          "Unrealised PnL" in md and "$+0.93" in md)
    check("logger: scorecard mismatch is flagged in the report",
          "SCORECARD MISMATCH" in md)
    check("logger: stand-aside rate recomputed (96.9%), not 0.0%",
          "126 (96.9%)" in md)
    check("logger: OPEN_AT_END ledger row shows floating PnL as unrealised",
          "unrealised $" in md)
    # Correct scorecard -> no mismatch note, same realised header.
    # Note: the HISTORICAL scorecard in this file still disagrees on
    # purpose — its net (+$2.26) includes the unrealised +$0.93, so
    # the flag correctly fires for it. A realised-only scorecard must
    # not flag.
    md2 = lg._generate_markdown_report({}, d["scorecard"], sessions)
    check("logger: historical scorecard (net incl. unrealised) is flagged",
          "SCORECARD MISMATCH" in md2
          and "net_pnl_usd: scorecard 2.26 vs dataset 1.33" in md2)
    realised_sc = dict(d["scorecard"], net_pnl_usd=1.33,
                       gross_profit_usd=1.93, gross_loss_usd=0.60)
    md2b = lg._generate_markdown_report({}, realised_sc, sessions)
    check("logger: realised-only scorecard produces no mismatch flag",
          "SCORECARD MISMATCH" not in md2b)
    check("logger: header still realised +$1.33 with the true scorecard",
          "| **Net Realized PnL** | **$+1.33** |" in md2)
    # Shadow section: real gross figures, not the wins*15 fabrication.
    shadow_sc = {
        "total_opportunities_screened": 10,
        "actual_council_portfolio": {
            "filled_trades": 2, "wins": 1, "losses": 1, "win_rate_pct": 50.0,
            "gross_profit_usd": 3.46, "gross_loss_usd": 1.20,
            "net_pnl_usd": 2.26, "profit_factor": 2.88,
        },
        "blind_execution_shadow_portfolio": {
            "total_filled_if_traded_all": 5, "wins": 2, "losses": 3,
            "win_rate_pct": 40.0, "gross_profit_usd": 6.00,
            "gross_loss_usd": 4.00, "net_pnl_usd": 2.00, "profit_factor": 1.50,
        },
        "counterfactual_stand_aside_breakdown": {
            "total_stand_asides": 8, "protective_vetoes_losses_prevented": 1,
            "capital_saved_usd": 1.00, "damaging_stand_asides_missed_winners": 0,
            "missed_alpha_usd": 0.00, "unfilled_or_expired": 7,
        },
        "net_council_filtering_value_usd": 1.00,
    }
    md3 = lg._generate_markdown_report({}, {"shadow_portfolio": shadow_sc}, sessions)
    check("logger: shadow gross loss uses real $1.20, not net-wins*15",
          "-$1.20" in md3 and "-$12.74" not in md3)
    check("logger: shadow gross profit uses real $3.46, not net+losses*10",
          "+$3.46" in md3 and "+$12.26" not in md3)
    # BacktestLogger.__init__ created an empty probe run dir; remove it.
    import shutil
    shutil.rmtree(lg.run_dir, ignore_errors=True)
else:
    print("  SKIP  logger dataset checks (full_dataset.json not present)")

# --- 5. Annual summary builders label the populations ---
gold = build_gold_summary(
    symbol='XAUUSD_o',
    baseline_annual={'fills': 414, 'wins': 66, 'losses': 285, 'be': 63,
                     'wr': 15.9, 'net_r': -54.0, 'pf': 0.81, 'ev': -0.13},
    calibrated_annual={'fills': 137, 'wins': 30, 'losses': 88, 'be': 19,
                       'wr': 21.9, 'net_r': 17.0, 'pf': 1.19, 'ev': 0.124},
    seasonal_breakdown={'Winter': {'fills': 29, 'net_r': -6.0}},
    archetype_breakdown={'SETUP-ARCH-010': {'fills': 36, 'net_r': 14.0}},
    session_breakdown={'London_Open': {'fills': 40, 'net_r': 5.0}},
    seasonal_breakdown_all_fills={'Winter': {'fills': 102, 'net_r': -33.5}},
    archetype_breakdown_all_fills={'SETUP-ARCH-010': {'fills': 50, 'net_r': 2.0}},
    session_breakdown_all_fills={'London_Open': {'fills': 120, 'net_r': -10.0}},
    nested_double_mss_annual={'fills': 128, 'net_r': 13.0},
    decommissioned_drag={},
)
check("gold summary: breakdown_population labels calibrated as 137 fills",
      "137 fills" in gold['breakdown_population']['seasonal_breakdown']
      and "CALIBRATED fills only" in gold['breakdown_population']['seasonal_breakdown'])
check("gold summary: all-fills Winter is 102, not the calibrated 29",
      gold['seasonal_breakdown_all_fills']['Winter']['fills'] == 102
      and gold['seasonal_breakdown']['Winter']['fills'] == 29)
check("gold summary: old keys kept for back-compat",
      gold['seasonal_breakdown']['Winter']['fills'] == 29
      and gold['calibrated_annual']['net_r'] == 17.0)

gbp = build_gbp_summary(
    symbol='GBPUSD_o',
    baseline_annual={'fills': 255, 'net_r': -7.0, 'pf': 0.95},
    calibrated_annual={'fills': 123, 'net_r': 17.0, 'pf': 1.25},
    seasonal_breakdown={'Winter': {'fills': 38, 'net_r': 5.5}},
    archetype_breakdown={},
    session_breakdown={},
    seasonal_breakdown_all_fills={'Winter': {'fills': 73, 'net_r': 6.0}},
    archetype_breakdown_all_fills={},
    session_breakdown_all_fills={},
    decommissioned_drag={},
)
check("gbp summary: breakdown_population labels calibrated as 123 fills",
      "123 fills" in gbp['breakdown_population']['seasonal_breakdown']
      and "CALIBRATED fills only" in gbp['breakdown_population']['seasonal_breakdown'])
check("gbp summary: all-fills Winter is 73, not the calibrated 38",
      gbp['seasonal_breakdown_all_fills']['Winter']['fills'] == 73)

# --- 6. Counterfactual auditor: actual net excludes OPEN_AT_END ---
aud = CounterfactualOpportunityAuditor()
trades = [
    {"status": "WIN", "realized_pnl": 3.46},
    {"status": "LOSS", "realized_pnl": -1.20},
    {"status": "OPEN_AT_END", "realized_pnl": 45.65},
]
sc = aud.generate_shadow_portfolio_scorecard(
    executed_trades=trades, stand_aside_audits=[])
act = sc["actual_council_portfolio"]
check("auditor: actual net is +$2.26 realised, open +$45.65 excluded",
      act["net_pnl_usd"] == 2.26, f"got {act['net_pnl_usd']}")
check("auditor: unrealised +$45.65 reported separately with 1 open trade",
      act["unrealized_pnl_usd"] == 45.65 and act["open_at_end_trades"] == 1,
      f"got {act['unrealized_pnl_usd']} / {act['open_at_end_trades']}")

print(f"\n{PASS} passed, {FAIL} failed")
sys.exit(1 if FAIL else 0)
