"""
TradingGuard HITL - Retrospective Review Council (Supervisory Post-Mortem Desk)
Decoupled supervisory engine that runs off-hours or after backtests to:
1. Ingest raw execution data and counterfactual stand-aside logs.
2. Convene a 3-member Supervisory Review Committee (Auditor, Alpha Scout, Chief Arbiter).
3. Extract, refine, and ratify institutional rules into `hitl/memory/council_playbook.json`.
"""

import sys
import json
import re
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.council import find_agy_binary
from hitl.council_memory import memory_engine


def convene_review_council(
    executed_trades: List[Dict[str, Any]],
    stand_aside_audits: List[Dict[str, Any]],
    symbol: str = "XAUUSD"
) -> Optional[Dict[str, Any]]:
    """
    Feeds historical post-mortems and counterfactual logs to the Supervisory Review Council.
    The committee analyzes failures and missed alpha, extracting formal operational rules.
    """
    agy_bin = find_agy_binary()

    # Format historical evidence payload for the review council
    trades_summary = []
    for t in executed_trades:
        trades_summary.append(
            f"- Trade [{t.get('timestamp')}]: {t.get('decision')} | Entry: {t.get('entry')} | SL: {t.get('sl')} | TP: {t.get('tp')} | "
            f"Result: {t.get('status')} (${t.get('realized_pnl', 0.0):+.2f}) | Notes: {t.get('notes', 'N/A')}"
        )
    trades_block = "\n".join(trades_summary) if trades_summary else "No executed trades in this evaluation cycle."

    audits_summary = []
    # Prioritize audits: Damaging stand-asides (missed alpha) first, then protective vetoes
    prioritized_audits = sorted(
        stand_aside_audits,
        key=lambda x: (x.get('missed_alpha_usd', 0.0) > 0, x.get('capital_saved_usd', 0.0) > 0),
        reverse=True
    )[:8]

    for a in prioritized_audits:
        hypo = a.get("hypothetical_order")
        if hypo:
            order_str = f"Theoretical Order: {hypo.get('decision')} @ {hypo.get('entry')} (SL: {hypo.get('sl')}, TP: {hypo.get('tp')})"
            res_str = f"M1 Spread Replay: {a.get('counterfactual_status')} (${a.get('counterfactual_pnl_usd', 0.0):+.2f})"
            if a.get('capital_saved_usd', 0.0) > 0:
                effect_str = f"Council Effect: SAVED +${a.get('capital_saved_usd'):.2f} CAPITAL (Protective Veto)"
            elif a.get('missed_alpha_usd', 0.0) > 0:
                effect_str = f"Council Effect: MISSED -${a.get('missed_alpha_usd'):.2f} ALPHA (Over-Conservative)"
            else:
                effect_str = "Council Effect: NEUTRAL (Order would have expired unfilled)"
            audits_summary.append(
                f"- Stand-Aside [{a.get('timestamp')}]: {a.get('symbol')} | Setup: '{a.get('discussed_setup')}'\n"
                f"  • {order_str} | {res_str}\n"
                f"  • {effect_str} | Verdict: {a.get('verdict')}\n"
                f"  • Diagnosis: {a.get('summary', a.get('lesson', 'N/A'))}"
            )
        else:
            audits_summary.append(
                f"- Stand-Aside [{a.get('timestamp')}]: Discussed: '{a.get('discussed_setup')}' | "
                f"Forward 4H Excursion: Max High +{a.get('forward_4h_mfe', 0.0):.2f} pts / Min Low -{a.get('forward_4h_mae', 0.0):.2f} pts | "
                f"Verdict: {a.get('verdict')} | Initial Note: {a.get('lesson', 'N/A')}"
            )
    audits_block = "\n".join(audits_summary) if audits_summary else "No debated stand-asides in this cycle."

    # Current active rules: full text of the latest 10 (Windows CLI prompt
    # size), plus the IDs of ALL active rules so the committee knows the
    # full playbook it is calibrating against — previously it saw only the
    # last 10 while the live council gets all 52.
    all_rules = memory_engine.data.get("active_rules", [])
    current_rules = all_rules[-10:]
    rules_summary = [f"- [{r.get('id')}]: {r.get('rule')}" for r in current_rules]
    all_ids = ", ".join(r.get("id", "?") for r in all_rules)
    current_rules_block = "\n".join(rules_summary) if rules_summary else "None"
    current_rules_block += f"\n\nAll active rule IDs ({len(all_rules)}): {all_ids}"

    prompt = (
        f"You are the Antigravity Supervisory Review Council, an elite proprietary post-mortem committee.\n"
        f"Your mission is to conduct a forensic performance review for {symbol} and calibrate the operational playbook.\n\n"
        f"=== CURRENT ACTIVE PLAYBOOK RULES ===\n"
        f"{current_rules_block}\n\n"
        f"=== EXECUTED TRADES AUDIT LOGS ===\n"
        f"{trades_block}\n\n"
        f"=== COUNTERFACTUAL STAND-ASIDE LOGS (MISSED SETUPS & VETOES) ===\n"
        f"{audits_block}\n\n"
        f"=== COMMITTEE MANDATE ===\n"
        f"Deliberate through the following 3 specialized review seats:\n\n"
        f"🔍 **1. Forensic Risk & Execution Auditor**\n"
        f"• Evaluate all losing trades: Identify whether losses were caused by structural thesis failures or micro-stop choking / execution friction.\n"
        f"• Evaluate stop buffer sizing against prevailing volatility.\n\n"
        f"🎯 **2. Alpha Scout & Opportunity Arbiter**\n"
        f"• Evaluate all debated Stand-Asides: Did the Operational Council leave substantial alpha on the table (+20 to +35 pts) due to over-filtering or excessive conservatism?\n"
        f"• Validate whether capital preservation vetoes correctly avoided falling knives.\n\n"
        f"⚖️ **3. Chief Governance Arbiter (Rule Synthesis & Ratification)**\n"
        f"• Formulate 1 to 3 explicit, mathematically rigorous operational rules to add or update in the Playbook.\n"
        f"• These are PROPOSALS only — a proposed rule does NOT become an active "
        f"playbook rule until a human approves it. Never claim a rule is ratified "
        f"or already in force.\n"
        f"• Format each proposed rule EXACTLY as follows:\n"
        f"  [PROPOSED RULE]\n"
        f"  ID: RULE-XXX-00X\n"
        f"  Category: [Risk Calibration | Setup Selection | Capital Preservation | Macro Alignment]\n"
        f"  Rule: <Clear, actionable operational directive>\n"
        f"  Rationale: <Specific empirical evidence from the logs justifying this rule>\n\n"
        f"Keep the review objective, strictly empirical, and concise."
    )

    cmd = [
        agy_bin,
        "--dangerously-skip-permissions",
        "--model", "gemini-3.8-flash-low",
        "-p", prompt
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60
        )
        if proc.returncode != 0:
            print(f"[ReviewCouncil] agy error: {proc.stderr}")
            return None

        report = proc.stdout.strip()

        # Parse proposed rules. Both [PROPOSED RULE] (current prompt) and
        # the legacy [RATIFIED RULE] header are accepted, so older LLM
        # outputs still parse — but either way the rule is stored as a
        # PENDING proposal, never as an active rule (Pack 5 governance:
        # the review council may propose, only a human may ratify).
        ratified_rules = []
        rule_blocks = re.findall(
            r'\[(?:PROPOSED|RATIFIED) RULE\]\s*\nID:\s*([^\n]+)\s*\nCategory:\s*([^\n]+)\s*\nRule:\s*([^\n]+)\s*\nRationale:\s*([^\n]+)',
            report,
            re.MULTILINE
        )

        for rid, cat, rtext, rat in rule_blocks:
            rule_entry = {
                "id": rid.strip(),
                "category": cat.strip(),
                "symbol": symbol,
                "rule": rtext.strip(),
                "rationale": rat.strip()
            }
            ratified_rules.append(rule_entry)
            # PENDING proposal only — see CouncilMemory.add_pending_rule().
            memory_engine.add_pending_rule(
                rule_id=rule_entry["id"],
                category=rule_entry["category"],
                symbol=symbol,
                rule=rule_entry["rule"],
                rationale=rule_entry["rationale"],
                source="review_council:convene_review_council",
            )

        return {
            "full_report": report,
            # "proposed_rules" is the honest name; "ratified_rules" is kept
            # only so the backtest runners' len(rev_res['ratified_rules'])
            # print still works — these rules are NOT ratified.
            "proposed_rules": ratified_rules,
            "ratified_rules": ratified_rules,
        }

    except Exception as e:
        print(f"[ReviewCouncil] Execution exception: {e}")
        return None


def vet_and_ratify_candidate_setup(
    candidate: Dict[str, Any],
    historical_evidence: List[Dict[str, Any]],
    symbol: str = "XAUUSD"
) -> Optional[Dict[str, Any]]:
    """
    Submits a candidate setup archetype to the Review Council for formal vetting.
    Only when the Review Council formally issues [VETTING VERDICT: RATIFIED]
    is the setup registered into the SetupRegistry and authorized for operational trading.
    """
    from hitl.setup_registry import setup_registry

    agy_bin = find_agy_binary()

    evidence_lines = []
    for ev in historical_evidence:
        evidence_lines.append(
            f"- Milestone [{ev.get('timestamp')}]: {ev.get('session')} | Result: {ev.get('result', 'N/A')} | "
            f"Excursion/PnL: {ev.get('pnl', 'N/A')} | Details: {ev.get('details', 'N/A')}"
        )
    evidence_block = "\n".join(evidence_lines) if evidence_lines else "General backtest empirical evidence provided."

    prompt = (
        f"You are the Antigravity Supervisory Review Council, convening for a formal Strategy Vetting Hearing.\n"
        f"A candidate setup archetype has been proposed for {symbol} and requires formal authorization before live execution.\n\n"
        f"=== CANDIDATE SETUP PROPOSAL ===\n"
        f"• Candidate ID: {candidate.get('id')}\n"
        f"• Name: {candidate.get('name')}\n"
        f"• Category: {candidate.get('category')}\n"
        f"• Structural Concept: {candidate.get('description')}\n"
        f"• Entry Anchor: {candidate.get('entry_trigger')}\n"
        f"• Invalidation Anchor: {candidate.get('invalidation_anchor')}\n\n"
        f"=== HISTORICAL EMPIRICAL EVIDENCE ===\n"
        f"{evidence_block}\n\n"
        f"=== VETTING COMMITTEE MANDATE ===\n"
        f"Deliver your findings strictly through the 3 specialized supervisory seats:\n\n"
        f"🔍 **1. Forensic Risk Auditor**\n"
        f"• Evaluate structural failure modes and vulnerability to broker spread expansion during liquidity windows.\n"
        f"• Mandate the minimum stop-loss buffer required to trade this pattern safely.\n\n"
        f"🎯 **2. Alpha Scout & Edge Validator**\n"
        f"• Validate whether this pattern captures true institutional order flow or is vulnerable to retail bait.\n"
        f"• Prescribe the mandatory minimum Risk-to-Reward (R:R) ratio.\n\n"
        f"⚖️ **3. Chief Governance Arbiter**\n"
        f"• Issue the binding verdict: [VETTING VERDICT: RATIFIED] or [VETTING VERDICT: REJECTED].\n"
        f"• If RATIFIED, provide the exact operational authorization block formatted as:\n"
        f"  [RATIFICATION CERTIFICATE]\n"
        f"  Archetype ID: {candidate.get('id')}\n"
        f"  Status: RATIFIED\n"
        f"  Min R:R: 1:X.X\n"
        f"  Stop Buffer Rule: <Exact required buffer>\n"
        f"  Authorization Note: <Formal supervisory justification>\n\n"
        f"Maintain institutional rigor. Reject any setup that lacks clear structural invalidation or positive expectancy."
    )

    cmd = [
        agy_bin,
        "--dangerously-skip-permissions",
        "--model", "gemini-3.8-flash-low",
        "-p", prompt
    ]

    try:
        proc = subprocess.run(
            cmd,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=60
        )
        if proc.returncode != 0:
            print(f"[ReviewCouncil] Vetting error: {proc.stderr}")
            return None

        report = proc.stdout.strip()
        is_ratified = "[VETTING VERDICT: RATIFIED]" in report or "Status: RATIFIED" in report

        if is_ratified:
            # Extract criteria
            min_rr = "1:2.0"
            rr_match = re.search(r'Min R:R:\s*([^\n]+)', report)
            if rr_match:
                min_rr = rr_match.group(1).strip()

            stop_buf = "Per Active Playbook"
            sb_match = re.search(r'Stop Buffer Rule:\s*([^\n]+)', report)
            if sb_match:
                stop_buf = sb_match.group(1).strip()

            auth_note = "Ratified by Supervisory Review Council"
            an_match = re.search(r'Authorization Note:\s*([^\n]+)', report)
            if an_match:
                auth_note = an_match.group(1).strip()

            ratified_criteria = {
                "name": candidate.get("name"),
                "category": candidate.get("category"),
                "description": candidate.get("description"),
                "entry_trigger": candidate.get("entry_trigger"),
                "invalidation_anchor": candidate.get("invalidation_anchor"),
                "min_rr": min_rr,
                "stop_buffer_rule": stop_buf
            }

            setup_registry.ratify_archetype(
                archetype_id=candidate.get("id"),
                vetting_verdict="RATIFIED",
                ratified_criteria=ratified_criteria,
                auditor_notes=auth_note
            )

            print(f"[ReviewCouncil] Setup Archetype {candidate.get('id')} SUCCESSFULLY RATIFIED!")
            print(f"   Min R:R: {min_rr} | Stop Buffer: {stop_buf}")

            return {
                "verdict": "RATIFIED",
                "full_report": report,
                "ratified_criteria": ratified_criteria
            }
        else:
            print(f"❌ [ReviewCouncil] Setup Archetype {candidate.get('id')} REJECTED by Supervisory Council.")
            return {
                "verdict": "REJECTED",
                "full_report": report
            }

    except Exception as e:
        print(f"[ReviewCouncil] Vetting execution exception: {e}")
        return None
