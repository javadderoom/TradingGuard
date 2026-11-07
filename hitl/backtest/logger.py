"""
TradingGuard HITL - Backtest Persistence & Audit Logger
Saves complete backtest runs into structured files in `backtest_results/`:
1. `run_<timestamp>_ledger.csv`: Complete tabular ledger of every session.
2. `run_<timestamp>_full.json`: Exhaustive JSON with exact telemetry, 6-seat deliberations, and tick replay data.
3. `run_<timestamp>_scorecard.md`: Human-readable executive markdown scorecard.
"""

import csv
import json
import datetime
from pathlib import Path
from typing import List, Dict, Any

from hitl.backtest.evaluator import summarize_pnl

RESULTS_DIR = Path(__file__).resolve().parent.parent.parent / "backtest_results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class BacktestLogger:
    def __init__(self, run_name: str = "30day_gold_comparison"):
        self.run_name = run_name
        self.timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.run_id = f"{run_name}_{self.timestamp_str}"
        self.run_dir = RESULTS_DIR / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=True)

    def log_run(
        self,
        metadata: Dict[str, Any],
        sessions: List[Dict[str, Any]],
        scorecard: Dict[str, Any]
    ) -> Dict[str, Path]:
        """
        Persists the entire backtest dataset into CSV, JSON, and Markdown.
        """
        csv_path = self.run_dir / "trade_ledger.csv"
        json_path = self.run_dir / "full_dataset.json"
        md_path = self.run_dir / "executive_report.md"

        # 1. Export CSV Ledger
        fieldnames = [
            "session_id", "symbol", "timestamp", "session", "decision",
            "entry", "sl", "tp", "rr", "status", "realized_pnl_usd",
            "is_realized",
            "fill_minute", "exit_minute", "mfe_price", "max_rr_potential",
            "extension_beyond_tp", "capture_efficiency_pct", "notes", "cdo_watchlist_trigger"
        ]
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for idx, s in enumerate(sessions, 1):
                t_opt = s.get("target_optimization", {}) or {}
                writer.writerow({
                    "session_id": idx,
                    "symbol": s.get("symbol", "XAUUSD"),
                    "timestamp": s.get("timestamp"),
                    "session": s.get("session"),
                    "decision": s.get("decision"),
                    "entry": s.get("entry"),
                    "sl": s.get("sl"),
                    "tp": s.get("tp"),
                    "rr": s.get("rr"),
                    "status": s.get("status"),
                    "realized_pnl_usd": s.get("realized_pnl_usd", 0.0),
                    # Pack 6: True for closed trades, False for
                    # OPEN_AT_END floating PnL (see evaluator).
                    "is_realized": s.get("is_realized", s.get("status") != "OPEN_AT_END"),
                    "fill_minute": s.get("fill_minute"),
                    "exit_minute": s.get("exit_minute"),
                    "mfe_price": t_opt.get("mfe_price", ""),
                    "max_rr_potential": t_opt.get("max_rr_potential", ""),
                    "extension_beyond_tp": t_opt.get("extension_beyond_tp", ""),
                    "capture_efficiency_pct": t_opt.get("capture_efficiency_pct", ""),
                    "notes": s.get("notes", ""),
                    "cdo_watchlist_trigger": s.get("cdo_trigger", "")
                })

        # 2. Export Full JSON Dataset
        full_payload = {
            "run_id": self.run_id,
            "created_at": datetime.datetime.now().isoformat(),
            "metadata": metadata,
            "scorecard": scorecard,
            "sessions": sessions
        }
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(full_payload, f, indent=2, ensure_ascii=False)

        # 3. Export Executive Markdown Report
        md_content = self._generate_markdown_report(metadata, scorecard, sessions)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

        print(f"\n💾 Backtest Results Successfully Persisted to: {self.run_dir.as_posix()}")
        print(f"   • CSV Ledger: {csv_path.name}")
        print(f"   • Full JSON Dataset: {json_path.name}")
        print(f"   • Executive Report: {md_path.name}")

        return {
            "dir": self.run_dir,
            "csv": csv_path,
            "json": json_path,
            "md": md_path
        }

    def _generate_markdown_report(
        self,
        meta: Dict[str, Any],
        scorecard: Dict[str, Any],
        sessions: List[Dict[str, Any]]
    ) -> str:
        # Pack 6: the headline numbers are DERIVED from `sessions` — the
        # same records written to full_dataset.json — instead of trusting
        # the caller-supplied scorecard. Three historical reports shipped
        # with zeroed headers (0 orders / $0 net / 0.0% win rate) while
        # their own datasets showed real trades, because the scorecard
        # keys the generator read did not match what the runner passed.
        # Deriving here makes the report and its dataset agree by
        # construction. The caller scorecard is still cross-checked and
        # any disagreement is flagged loudly in the report itself.
        # Filled = WIN + LOSS + BREAKEVEN (a fill is a fill; the old
        # single-asset runners excluded BREAKEVEN from `filled`).
        pnl = summarize_pnl(sessions)
        tot_sess = len(sessions)
        tot_sa = sum(1 for s in sessions if s.get("decision") == "STAND_ASIDE")
        sa_pct = (tot_sa / tot_sess * 100) if tot_sess > 0 else 0.0
        tot_orders = tot_sess - tot_sa
        tot_exp = sum(1 for s in sessions if s.get("status") == "EXPIRED")
        tot_canc = sum(1 for s in sessions if s.get("status") == "CANCELLED_WATCHDOG")
        wins = sum(1 for s in sessions if s.get("status") == "WIN")
        losses = sum(1 for s in sessions if s.get("status") == "LOSS")
        bes = sum(1 for s in sessions if s.get("status") == "BREAKEVEN")
        tot_filled = wins + losses + bes
        wr = (wins / tot_filled * 100) if tot_filled > 0 else 0.0
        gp = pnl["realized_gross_profit_usd"]
        gl = pnl["realized_gross_loss_usd"]
        net_pnl = pnl["realized_net_usd"]
        pf = pnl["realized_profit_factor"]
        unreal_pnl = pnl["unrealized_net_usd"]
        n_open = pnl["open_trades"]

        # Cross-check against the caller-supplied scorecard (flat keys
        # or the consolidated_basket nest). A mismatch means the runner
        # and the dataset disagree — report it, do not silently pick one.
        target_sc = scorecard.get('consolidated_basket', scorecard)
        reported = {
            "orders": target_sc.get('orders_approved', scorecard.get('orders')),
            "filled": target_sc.get('filled_trades', scorecard.get('filled')),
            "wins": target_sc.get('wins', scorecard.get('wins')),
            "losses": target_sc.get('losses', scorecard.get('losses')),
            "net_pnl_usd": target_sc.get('net_pnl_usd', scorecard.get('net_pnl')),
        }
        derived = {
            "orders": tot_orders,
            "filled": tot_filled,
            "wins": wins,
            "losses": losses,
            "net_pnl_usd": net_pnl,
        }
        mismatches = []
        for key, rep in reported.items():
            if rep is None:
                continue
            try:
                if round(float(rep), 2) != round(float(derived[key]), 2):
                    mismatches.append(
                        f"{key}: scorecard {rep} vs dataset {derived[key]}"
                    )
            except (TypeError, ValueError):
                continue
        if mismatches:
            print("⚠️ [BacktestLogger] SCORECARD MISMATCH — report header "
                  "is derived from the session dataset; the caller "
                  f"scorecard disagrees: {'; '.join(mismatches)}")

        lines = [
            f"# 🏆 Executive Backtest Audit Report: {self.run_name.upper()}",
            f"> **Run ID**: `{self.run_id}` | **Generated**: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S Tehran Time')}",
            "",
        ]
        if mismatches:
            lines.extend([
                "> ⚠️ **SCORECARD MISMATCH (Pack 6):** the runner-supplied scorecard disagrees with "
                "the session dataset in this same run. The numbers below are derived from the "
                "dataset (`full_dataset.json`); the scorecard values were: "
                + "; ".join(mismatches) + ".",
                "",
            ])
        lines.extend([
            "## 📊 Portfolio Summary Scorecard",
            "| Metric | Result | Benchmark Significance |",
            "| :--- | :---: | :--- |",
            f"| **Total Calendar Sessions** | **{tot_sess}** | All market open milestones evaluated |",
            f"| **Stand-Aside Directives** | **{tot_sa} ({sa_pct:.1f}%)** | Capital preserved in non-trending drift |",
            f"| **Approved Limit Orders** | **{tot_orders}** | Strict SMC confluences satisfied |",
            f"| **Unfilled Orders (75m TTL)** | **{tot_exp}** | Safely cancelled after 75 minutes |",
            f"| **Watchdog Radar Interceptions** | **{tot_canc}** | Adverse spikes killed before execution |",
            f"| **Filled Institutional Trades** | **{tot_filled} ({wins}W / {losses}L / {bes}BE)** | Executed with dynamic BE & target cap |",
            f"| **Win Rate on Fills** | **{wr:.1f}%** | Won / Total Filled |",
            f"| **Gross Profit (realised)** | **+${gp:.2f}** | Cumulative winning trades |",
            f"| **Gross Loss (realised)** | **-${gl:.2f}** | Strictly contained under $12 cap |",
            f"| **Net Realized PnL** | **${net_pnl:+.2f}** | **Bottom-line cash flow on 0.01 base lots** |",
            f"| **Unrealised PnL — open at end ({n_open} trade(s), NOT counted above)** | **${unreal_pnl:+.2f}** | Floating mark-to-market on still-open trades; excluded from realised totals |",
            f"| **Profit Factor (realised)** | **{pf:.2f}** | Gross Profit / Gross Loss |",
            ""
        ])

        if "gold_performance" in scorecard and "silver_performance" in scorecard:
            g = scorecard["gold_performance"]
            s = scorecard["silver_performance"]
            smt = scorecard.get("smt_trades_performance", {})
            lines.extend([
                "## 🥇 Dual-Asset Segmented Breakdown (Gold vs Silver vs SMT)",
                "| Asset Segment | Approved Orders | Filled | Wins | Losses | Breakeven | Win Rate | Net PnL (0.01 lot) | Profit Factor |",
                "| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |",
                f"| **Gold (XAUUSD)** | {g.get('orders_approved', 0)} | {g.get('filled_trades', 0)} | {g.get('wins', 0)} | {g.get('losses', 0)} | {g.get('breakevens', 0)} | {g.get('win_rate_pct', 0.0):.1f}% | ${g.get('net_pnl_usd', 0.0):+.2f} | {g.get('profit_factor', 0.0):.2f} |",
                f"| **Silver (XAGUSD)** | {s.get('orders_approved', 0)} | {s.get('filled_trades', 0)} | {s.get('wins', 0)} | {s.get('losses', 0)} | {s.get('breakevens', 0)} | {s.get('win_rate_pct', 0.0):.1f}% | ${s.get('net_pnl_usd', 0.0):+.2f} | {s.get('profit_factor', 0.0):.2f} |",
                f"| **Intermarket SMT Setups** | {smt.get('orders_approved', 0)} | {smt.get('filled_trades', 0)} | {smt.get('wins', 0)} | {smt.get('losses', 0)} | {smt.get('breakevens', 0)} | {smt.get('win_rate_pct', 0.0):.1f}% | ${smt.get('net_pnl_usd', 0.0):+.2f} | {smt.get('profit_factor', 0.0):.2f} |",
                ""
            ])

        if "shadow_portfolio" in scorecard:
            sh = scorecard["shadow_portfolio"]
            act = sh.get("actual_council_portfolio", {})
            bld = sh.get("blind_execution_shadow_portfolio", {})
            cfa = sh.get("counterfactual_stand_aside_breakdown", {})
            val = sh.get("net_council_filtering_value_usd", 0.0)
            val_sign = "+" if val >= 0 else "-"
            lines.extend([
                "## 🕵️ Missed Opportunities & Shadow Portfolio Audit (Blind Execution vs Council)",
                "> **The Counterfactual Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?",
                "",
                "| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |",
                "| :--- | :---: | :---: | :--- |",
                f"| **Total Setups Screened** | **{sh.get('total_opportunities_screened', 0)}** | **{sh.get('total_opportunities_screened', 0)}** | 100% of candidate opportunities |",
                f"| **Filled Trades** | **{act.get('filled_trades', 0)}** | **{bld.get('total_filled_if_traded_all', 0)}** | Filtered {cfa.get('total_stand_asides', 0)} questionable sessions |",
                f"| **Win / Loss Record** | **{act.get('wins', 0)} W / {act.get('losses', 0)} L** | **{bld.get('wins', 0)} W / {bld.get('losses', 0)} L** | Prevented {cfa.get('protective_vetoes_losses_prevented', 0)} direct stop-outs |",
                f"| **Win Rate on Fills** | **{act.get('win_rate_pct', 0.0):.1f}%** | **{bld.get('win_rate_pct', 0.0):.1f}%** | Council delta: {act.get('win_rate_pct', 0.0) - bld.get('win_rate_pct', 0.0):+.1f}% |",
                f"| **Gross Losses Incurred** | **-${act.get('gross_loss_usd', 0.0):.2f}** | **-${bld.get('gross_loss_usd', 0.0):.2f}** | **Saved +${cfa.get('capital_saved_usd', 0.0):.2f} from bad entries** |",
                f"| **Gross Profits Captured** | **+${act.get('gross_profit_usd', 0.0):.2f}** | **+${bld.get('gross_profit_usd', 0.0):.2f}** | Missed -${cfa.get('missed_alpha_usd', 0.0):.2f} in passed winners |",
                f"| **Net Realized PnL** | **${act.get('net_pnl_usd', 0.0):+.2f}** | **${bld.get('net_pnl_usd', 0.0):+.2f}** | **Net Council Value: {val_sign}${abs(val):.2f}** |",
                f"| **Profit Factor** | **{act.get('profit_factor', 0.0):.2f}** | **{bld.get('profit_factor', 0.0):.2f}** | Risk-adjusted quality improvement |",
                ""
            ])

        lines.extend([
            "## 📋 Session-by-Session Trade & Watchlist Ledger",
            "| # | Date & Session | Quote at T | Council Directive | Status | Realized PnL | CDO Tactical Watchlist Memo |",
            "| :-: | :--- | :---: | :---: | :---: | :---: | :--- |"
        ])

        for idx, s in enumerate(sessions, 1):
            # Pack 6: WIN/LOSS/BREAKEVEN show their (realised) PnL — the
            # old code printed $0.00 for BREAKEVEN even when it banked
            # spread-minus-commission. OPEN_AT_END shows $0.00 realised
            # and its floating PnL separately, never as realised profit.
            if s.get('status') == 'OPEN_AT_END':
                pnl_str = f"$0.00 realised (unrealised ${s.get('realized_pnl_usd', 0.0):+.2f})"
            elif s.get('status') in ('WIN', 'LOSS', 'BREAKEVEN'):
                pnl_str = f"${s.get('realized_pnl_usd', 0.0):+.2f}"
            else:
                pnl_str = "$0.00"
            cdo_note = s.get("cdo_trigger", "N/A")
            lines.append(
                f"| {idx} | {s.get('timestamp')} ({s.get('session')}) | {s.get('price_at_t', 'N/A')} | "
                f"`{s.get('decision')}` | **{s.get('status')}** | {pnl_str} | {cdo_note} |"
            )

        lines.extend([
            "",
            "---",
            "*TradingGuard Institutional HITL Engine — Prop Firm Capital Defense & Cash Flow Architecture*"
        ])
        return "\n".join(lines)
