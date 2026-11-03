"""
TradingGuard HITL - Counterfactual Opportunity Journaling & Replay Agent
Specifically addresses:
"If 12 opportunities were selected in total, what outcome would have occurred if we had entered those positions?"

When the Council decides STAND_ASIDE on an identified setup:
1. Reconstructs the exact theoretical SMC limit order (Entry, SL, TP, R:R).
2. Simulates full M1 forward replay with realistic broker Bid/Ask spreads and 75m TTL.
3. Classifies the outcome:
   - PROTECTIVE_VETO: Setup would have hit SL. Council's stand-aside SAVED capital!
   - DAMAGING_STAND_ASIDE: Setup would have hit TP. Council missed valid alpha!
   - BENIGN_UNFILLED: Setup expired after 75m with zero fill ($0.00 PnL).
4. Maintains the Shadow Portfolio Ledger comparing Council Filtering vs. Blind Execution.
"""

from typing import Dict, Any, List, Optional
from hitl.backtest.evaluator import evaluate_council_decision, get_default_broker_spread
from hitl.council_memory import memory_engine


class CounterfactualOpportunityAuditor:
    """
    Dedicated agent seat evaluating missed opportunities and shadow portfolio performance.
    """

    def build_theoretical_order(
        self,
        screener_result: Dict[str, Any],
        dossier: Dict[str, Any],
        symbol: str
    ) -> Dict[str, Any]:
        """
        Reconstructs the precise mathematical trade plan that would have been placed
        for an opportunity that the Council decided to pass over.
        """
        setup_type = screener_result.get("setup_type", "NONE").upper()
        arch_id = screener_result.get("archetype_id", "SETUP-ARCH-001")
        entry_ref = screener_result.get("entry_ref", dossier.get("price_at_t", 0.0))

        is_buy = "BULLISH" in setup_type
        telemetry = dossier.get("telemetry", {})
        atr_5m = telemetry.get("atr_5m", 1.0)
        bench_high = telemetry.get("bench_high", entry_ref)
        bench_low = telemetry.get("bench_low", entry_ref)

        # Extract candidate structural liquidity levels from dossier if present
        bench_high = dossier.get("bench_high")
        bench_low = dossier.get("bench_low")
        pdh = dossier.get("pdh")
        pdl = dossier.get("pdl")

        target_rr = screener_result.get("recommended_target_rr", 3.0)

        sym = symbol.upper()
        if "XAU" in sym:
            # Gold: $1.00 per point on 0.01 lot. Mandate min 5.5 to 7.0 pt buffer
            sl_dist = min(17.0, max(5.5, 1.5 * atr_5m))
            entry = round(entry_ref, 2)
            min_target_dist = target_rr * sl_dist
            if is_buy:
                sl = round(entry - sl_dist, 2)
                cand_tp = bench_high if (bench_high and (bench_high - entry) >= min_target_dist) else None
                if not cand_tp:
                    cand_tp = pdh if (pdh and (pdh - entry) >= min_target_dist) else (entry + min_target_dist)
                tp = round(cand_tp, 2)
            else:
                sl = round(entry + sl_dist, 2)
                cand_tp = bench_low if (bench_low and (entry - bench_low) >= min_target_dist) else None
                if not cand_tp:
                    cand_tp = pdl if (pdl and (entry - pdl) >= min_target_dist) else (entry - min_target_dist)
                tp = round(cand_tp, 2)
        elif "XAG" in sym:
            # Silver: $50.00 per point on 0.01 lot ($0.50/cent). Max stop ceiling 0.34 pts ($17)
            sl_dist = min(0.34, max(0.20, 1.5 * atr_5m))
            entry = round(entry_ref, 3)
            min_target_dist = target_rr * sl_dist
            if is_buy:
                sl = round(entry - sl_dist, 3)
                cand_tp = bench_high if (bench_high and (bench_high - entry) >= min_target_dist) else None
                if not cand_tp:
                    cand_tp = pdh if (pdh and (pdh - entry) >= min_target_dist) else (entry + min_target_dist)
                tp = round(cand_tp, 3)
            else:
                sl = round(entry + sl_dist, 3)
                cand_tp = bench_low if (bench_low and (entry - bench_low) >= min_target_dist) else None
                if not cand_tp:
                    cand_tp = pdl if (pdl and (entry - pdl) >= min_target_dist) else (entry - min_target_dist)
                tp = round(cand_tp, 3)
        else:
            # FX (EURUSD, GBPUSD): $0.10 per pip on 0.01 lot
            sl_dist = max(0.0010, 1.5 * atr_5m)
            entry = round(entry_ref, 5)
            min_target_dist = target_rr * sl_dist
            if is_buy:
                sl = round(entry - sl_dist, 5)
                cand_tp = bench_high if (bench_high and (bench_high - entry) >= min_target_dist) else None
                if not cand_tp:
                    cand_tp = pdh if (pdh and (pdh - entry) >= min_target_dist) else (entry + min_target_dist)
                tp = round(cand_tp, 5)
            else:
                sl = round(entry + sl_dist, 5)
                cand_tp = bench_low if (bench_low and (entry - bench_low) >= min_target_dist) else None
                if not cand_tp:
                    cand_tp = pdl if (pdl and (entry - pdl) >= min_target_dist) else (entry - min_target_dist)
                tp = round(cand_tp, 5)

        rr = round(abs(tp - entry) / max(0.0001, abs(entry - sl)), 2)

        return {
            "decision": "BUY_LIMIT" if is_buy else "SELL_LIMIT",
            "entry": entry,
            "sl": sl,
            "tp": tp,
            "lot": 0.01,
            "rr": rr,
            "archetype_id": arch_id,
            "setup_type": setup_type,
            "reason": screener_result.get("reason", "Missed opportunity")
        }

    def replay_missed_opportunity(
        self,
        screener_result: Dict[str, Any],
        dossier: Dict[str, Any],
        forward_m1_bars: List[Dict[str, Any]],
        symbol: str
    ) -> Dict[str, Any]:
        """
        Performs full forward M1 execution replay on a passed setup, accounting for:
        - Exact limit entry fill at Bid/Ask with broker spread penalty
        - 75-minute TTL order cancellation
        - Watchdog 2xATR adverse momentum spike cancellations
        - Hard Stop Loss and Take Profit resolutions
        """
        hypo_order = self.build_theoretical_order(screener_result, dossier, symbol)
        tgt_cap = screener_result.get("recommended_target_rr", 3.0)
        be_cap = screener_result.get("recommended_be_rr")
        if be_cap is None:
            be_cap = 999.0
        eval_res = evaluate_council_decision(hypo_order, forward_m1_bars, symbol, breakeven_rr=be_cap, target_rr_cap=tgt_cap)

        status = eval_res.get("status", "EXPIRED")
        pnl = eval_res.get("realized_pnl_usd", 0.0)
        fill_min = eval_res.get("fill_minute")
        exit_min = eval_res.get("exit_minute")

        # Classify the counterfactual impact of the Council's Stand-Aside decision
        if status == "WIN":
            verdict = "DAMAGING_STAND_ASIDE"
            effect = "MISSED_ALPHA"
            missed_alpha = pnl
            capital_saved = 0.0
            t_opt = eval_res.get("target_optimization", {})
            opt_str = ""
            if t_opt:
                opt_str = f" [Peak Excursion: {t_opt.get('mfe_price')} (Max R:R 1:{t_opt.get('max_rr_potential')}, +{t_opt.get('extension_beyond_tp')} units beyond TP, Efficiency: {t_opt.get('capture_efficiency_pct')}%)]."
            summary = (
                f"MISSED WINNER: If entered at {hypo_order['entry']}, trade would have filled "
                f"at min {fill_min} and hit TP at min {exit_min} for +${missed_alpha:.2f} profit. "
                f"Council veto caused alpha leakage.{opt_str}"
            )
        elif status == "LOSS":
            verdict = "PROTECTIVE_VETO"
            effect = "SAVED_CAPITAL"
            missed_alpha = 0.0
            capital_saved = abs(pnl)
            summary = (
                f"PROTECTIVE VETO: If entered at {hypo_order['entry']}, trade would have filled "
                f"at min {fill_min} and hit SL at min {exit_min} for -${capital_saved:.2f} loss. "
                f"Council stand-aside successfully defended capital!"
            )
        elif status == "CANCELLED_WATCHDOG":
            verdict = "WATCHDOG_INTERCEPTED"
            effect = "NEUTRAL"
            missed_alpha = 0.0
            capital_saved = 0.0
            summary = "Order would have been cancelled by Watchdog ATR momentum radar prior to fill ($0.00 PnL)."
        else:
            verdict = "BENIGN_UNFILLED"
            effect = "NEUTRAL"
            missed_alpha = 0.0
            capital_saved = 0.0
            summary = "75m TTL would have expired without order fill ($0.00 PnL). Zero harm."

        audit_record = {
            "timestamp": dossier.get("target_time").strftime("%Y-%m-%d %H:%M") if hasattr(dossier.get("target_time"), "strftime") else str(dossier.get("target_time")),
            "symbol": symbol,
            "discussed_setup": screener_result.get("reason", "N/A"),
            "cio_decision": "STAND_ASIDE",
            "hypothetical_order": hypo_order,
            "counterfactual_status": status,
            "counterfactual_pnl_usd": pnl,
            "verdict": verdict,
            "effect": effect,
            "missed_alpha_usd": missed_alpha,
            "capital_saved_usd": capital_saved,
            "fill_minute": fill_min,
            "exit_minute": exit_min,
            "target_optimization": eval_res.get("target_optimization", {}),
            "notes": eval_res.get("notes", ""),
            "summary": summary
        }

        # Persist into memory engine
        open_p = forward_m1_bars[0]['open'] if forward_m1_bars else 0.0
        max_h = max(b['high'] for b in forward_m1_bars[:240]) if forward_m1_bars else open_p
        min_l = min(b['low'] for b in forward_m1_bars[:240]) if forward_m1_bars else open_p
        close_p = forward_m1_bars[239]['close'] if len(forward_m1_bars) >= 240 else open_p

        memory_engine.record_counterfactual_audit(
            symbol=symbol,
            session_time=audit_record["timestamp"],
            discussed_setup=audit_record["discussed_setup"],
            cio_decision="STAND_ASIDE",
            forward_4h_max_gain=round(max_h - open_p, 2),
            forward_4h_max_dd=round(open_p - min_l, 2),
            forward_4h_close_change=round(close_p - open_p, 2),
            verdict=verdict,
            lesson=summary
        )

        return audit_record

    def generate_shadow_portfolio_scorecard(
        self,
        executed_trades: List[Dict[str, Any]],
        stand_aside_audits: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compiles the comprehensive Shadow Portfolio comparison:
        Answers: If all selected setups had been traded blindly vs Council filtering.
        """
        total_opportunities = len(executed_trades) + len(stand_aside_audits)

        # 1. Actual Council Performance
        actual_fills = [t for t in executed_trades if t.get("status") in ("WIN", "LOSS")]
        actual_wins = [t for t in actual_fills if t.get("status") == "WIN"]
        actual_losses = [t for t in actual_fills if t.get("status") == "LOSS"]
        actual_net_pnl = sum(t.get("realized_pnl", 0.0) for t in executed_trades)
        actual_gross_profit = sum(t.get("realized_pnl", 0.0) for t in actual_wins)
        actual_gross_loss = abs(sum(t.get("realized_pnl", 0.0) for t in actual_losses))
        actual_pf = (actual_gross_profit / actual_gross_loss) if actual_gross_loss > 0 else (99.0 if actual_gross_profit > 0 else 0.0)
        actual_wr = (len(actual_wins) / len(actual_fills) * 100) if actual_fills else 0.0

        # 2. Missed Opportunities Performance (Counterfactual Replay)
        vetoed_losses = [a for a in stand_aside_audits if a.get("verdict") == "PROTECTIVE_VETO"]
        missed_winners = [a for a in stand_aside_audits if a.get("verdict") == "DAMAGING_STAND_ASIDE"]
        unfilled_setups = [a for a in stand_aside_audits if a.get("verdict") in ("BENIGN_UNFILLED", "WATCHDOG_INTERCEPTED")]

        total_capital_saved = sum(a.get("capital_saved_usd", 0.0) for a in vetoed_losses)
        total_missed_alpha = sum(a.get("missed_alpha_usd", 0.0) for a in missed_winners)

        # 3. Blind Execution Shadow Portfolio (If all setups had been executed blindly)
        blind_filled = len(actual_fills) + len(vetoed_losses) + len(missed_winners)
        blind_wins = len(actual_wins) + len(missed_winners)
        blind_losses = len(actual_losses) + len(vetoed_losses)
        blind_wr = (blind_wins / blind_filled * 100) if blind_filled else 0.0

        blind_gross_profit = actual_gross_profit + total_missed_alpha
        blind_gross_loss = actual_gross_loss + total_capital_saved
        blind_net_pnl = blind_gross_profit - blind_gross_loss
        blind_pf = (blind_gross_profit / blind_gross_loss) if blind_gross_loss > 0 else 0.0

        # 4. Council Filtering Value-Add
        net_council_value_add = total_capital_saved - total_missed_alpha

        scorecard = {
            "total_opportunities_screened": total_opportunities,
            "actual_council_portfolio": {
                "trades_approved": len(executed_trades),
                "filled_trades": len(actual_fills),
                "wins": len(actual_wins),
                "losses": len(actual_losses),
                "win_rate_pct": round(actual_wr, 1),
                "gross_profit_usd": round(actual_gross_profit, 2),
                "gross_loss_usd": round(actual_gross_loss, 2),
                "net_pnl_usd": round(actual_net_pnl, 2),
                "profit_factor": round(actual_pf, 2)
            },
            "counterfactual_stand_aside_breakdown": {
                "total_stand_asides": len(stand_aside_audits),
                "protective_vetoes_losses_prevented": len(vetoed_losses),
                "capital_saved_usd": round(total_capital_saved, 2),
                "damaging_stand_asides_missed_winners": len(missed_winners),
                "missed_alpha_usd": round(total_missed_alpha, 2),
                "unfilled_or_expired": len(unfilled_setups)
            },
            "blind_execution_shadow_portfolio": {
                "total_filled_if_traded_all": blind_filled,
                "wins": blind_wins,
                "losses": blind_losses,
                "win_rate_pct": round(blind_wr, 1),
                "gross_profit_usd": round(blind_gross_profit, 2),
                "gross_loss_usd": round(blind_gross_loss, 2),
                "net_pnl_usd": round(blind_net_pnl, 2),
                "profit_factor": round(blind_pf, 2)
            },
            "net_council_filtering_value_usd": round(net_council_value_add, 2)
        }

        return scorecard

    def format_shadow_portfolio_markdown(self, scorecard: Dict[str, Any]) -> str:
        """Renders an executive markdown audit table comparing Council vs Blind execution."""
        act = scorecard["actual_council_portfolio"]
        bld = scorecard["blind_execution_shadow_portfolio"]
        cfa = scorecard["counterfactual_stand_aside_breakdown"]
        val = scorecard["net_council_filtering_value_usd"]

        val_sign = "+" if val >= 0 else "-"
        val_status = "POSITIVE VALUE ADD (Council filtering saved net capital)" if val >= 0 else "NEGATIVE DRAG (Council over-filtered winners)"

        lines = [
            "## 🕵️ Missed Opportunities & Shadow Portfolio Audit",
            "> **The Blind Execution Benchmark**: What outcome would have occurred if EVERY screened setup had been entered?",
            "",
            "| Performance Metric | AI Council Actual (Filtered) | Shadow Portfolio (Blind Execution) | Council Filtering Impact |",
            "| :--- | :---: | :---: | :--- |",
            f"| **Total Setups Available** | **{scorecard['total_opportunities_screened']}** | **{scorecard['total_opportunities_screened']}** | 100% of candidate opportunities |",
            f"| **Filled Trades** | **{act['filled_trades']}** | **{bld['total_filled_if_traded_all']}** | Filtered {cfa['total_stand_asides']} questionable sessions |",
            f"| **Win / Loss Record** | **{act['wins']} W / {act['losses']} L** | **{bld['wins']} W / {bld['losses']} L** | Prevented {cfa['protective_vetoes_losses_prevented']} direct stop-outs |",
            f"| **Win Rate** | **{act['win_rate_pct']:.1f}%** | **{bld['win_rate_pct']:.1f}%** | Council delta: {act['win_rate_pct'] - bld['win_rate_pct']:+.1f}% |",
            f"| **Gross Losses Incurred** | **-${act['gross_loss_usd']:.2f}** | **-${bld['gross_loss_usd']:.2f}** | **Saved +${cfa['capital_saved_usd']:.2f} from bad entries** |",
            f"| **Gross Profits Captured** | **+${act['gross_profit_usd']:.2f}** | **+${bld['gross_profit_usd']:.2f}** | Missed -${cfa['missed_alpha_usd']:.2f} in passed winners |",
            f"| **Net Realized PnL** | **${act['net_pnl_usd']:+.2f}** | **${bld['net_pnl_usd']:+.2f}** | **Net Council Value: {val_sign}${abs(val):.2f}** |",
            f"| **Profit Factor** | **{act['profit_factor']:.2f}** | **{bld['profit_factor']:.2f}** | Risk-adjusted quality improvement |",
            "",
            f"> **Executive Takeaway**: `{val_status}`. "
            f"The Council defended **${cfa['capital_saved_usd']:.2f}** across {cfa['protective_vetoes_losses_prevented']} losing setups while missing **${cfa['missed_alpha_usd']:.2f}** in alpha."
        ]
        return "\n".join(lines)


# Singleton instance
counterfactual_auditor = CounterfactualOpportunityAuditor()
