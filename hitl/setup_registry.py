"""
TradingGuard HITL - Modular Setup Archetype Registry & Governance Engine
Enforces the mandatory institutional rule:
"Every new setup must first be vetted and ratified by the Review Council before operational deployment."

Lifecycle States:
- PROPOSED: Candidate pattern discovered/mined from historical data.
- UNDER_REVIEW: Submitted to the Supervisory Review Council for stress-testing.
- RATIFIED: Formally approved with strict entry anchors, invalidation levels, and minimum R:R.
- REJECTED: Failed risk audit or edge stability check.
- DEPRECATED: Retired due to edge decay.
"""

import json
import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

MEMORY_DIR = Path(__file__).resolve().parent / "memory"
MEMORY_DIR.mkdir(parents=True, exist_ok=True)

REGISTRY_JSON = MEMORY_DIR / "setup_registry.json"
REGISTRY_MD = MEMORY_DIR / "setup_registry.md"


class SetupRegistry:
    def __init__(self):
        self.json_file = REGISTRY_JSON
        self.md_file = REGISTRY_MD
        self.data = self._load()

    def _load(self) -> Dict[str, Any]:
        if not self.json_file.exists():
            default_data = {
                "version": "1.0.0",
                "last_updated": datetime.datetime.now().isoformat(),
                "archetypes": []
            }
            self._save_raw(default_data)
            return default_data
        try:
            with open(self.json_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[SetupRegistry] Error loading registry: {e}. Reverting to defaults.")
            return {"version": "1.0.0", "archetypes": []}

    def _save_raw(self, data: Dict[str, Any]):
        data["last_updated"] = datetime.datetime.now().isoformat()
        with open(self.json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        self._export_markdown(data)

    def save(self):
        self._save_raw(self.data)

    def propose_candidate(
        self,
        archetype_id: str,
        name: str,
        category: str,
        description: str,
        entry_trigger: str,
        invalidation_anchor: str,
        proposer: str = "Quantitative Screener / CDO Mining"
    ) -> Dict[str, Any]:
        """Proposes a candidate setup archetype. Status is set to PROPOSED (Blocked from live execution)."""
        archetypes = self.data.setdefault("archetypes", [])
        for a in archetypes:
            if a["id"] == archetype_id:
                return a  # Already exists

        candidate = {
            "id": archetype_id,
            "name": name,
            "category": category,
            "description": description,
            "entry_trigger": entry_trigger,
            "invalidation_anchor": invalidation_anchor,
            "proposer": proposer,
            "status": "PROPOSED",
            "proposed_at": datetime.datetime.now().isoformat(),
            "ratified_at": None,
            "vetting_verdict": None,
            "ratified_criteria": {}
        }
        archetypes.append(candidate)
        self.save()
        return candidate

    def ratify_archetype(
        self,
        archetype_id: str,
        vetting_verdict: str,
        ratified_criteria: Dict[str, Any],
        auditor_notes: str
    ):
        """Ratifies a setup archetype following Review Council approval."""
        archetypes = self.data.setdefault("archetypes", [])
        for a in archetypes:
            if a["id"] == archetype_id:
                a["status"] = "RATIFIED"
                a["vetting_verdict"] = vetting_verdict
                a["ratified_criteria"] = ratified_criteria
                a["auditor_notes"] = auditor_notes
                a["ratified_at"] = datetime.datetime.now().isoformat()
                self.save()
                return
        # If not found, add directly as ratified
        archetypes.append({
            "id": archetype_id,
            "name": ratified_criteria.get("name", archetype_id),
            "category": ratified_criteria.get("category", "SMC Setup"),
            "description": ratified_criteria.get("description", ""),
            "entry_trigger": ratified_criteria.get("entry_trigger", ""),
            "invalidation_anchor": ratified_criteria.get("invalidation_anchor", ""),
            "status": "RATIFIED",
            "vetting_verdict": vetting_verdict,
            "ratified_criteria": ratified_criteria,
            "auditor_notes": auditor_notes,
            "ratified_at": datetime.datetime.now().isoformat()
        })
        self.save()

    def is_archetype_ratified(self, archetype_id: str) -> bool:
        """Checks if a setup archetype is formally ratified and authorized for execution."""
        for a in self.data.get("archetypes", []):
            if a.get("id") == archetype_id and a.get("status") == "RATIFIED":
                return True
        return False

    def get_ratified_archetypes(self) -> List[Dict[str, Any]]:
        """Returns all ratified and active setup archetypes."""
        return [a for a in self.data.get("archetypes", []) if a.get("status") == "RATIFIED"]

    def _export_markdown(self, data: Dict[str, Any]):
        """Generates a human-readable setup governance ledger in markdown."""
        md = [
            "# 🏛️ TradingGuard Ratified Setup Archetype Registry",
            f"**Last Calibration:** `{data.get('last_updated', 'N/A')}` | **Version:** `{data.get('version', '1.0.0')}`\n",
            "> **Mandatory Firm Governance:** The Operational Trading Council is **strictly prohibited** from placing orders on unratified setups.",
            "> Every candidate archetype must pass forensic risk stress-testing by the Retrospective Review Council before authorization.\n",
            "---",
            "## 📌 Active Ratified Archetypes\n"
        ]

        archetypes = data.get("archetypes", [])
        ratified = [a for a in archetypes if a.get("status") == "RATIFIED"]
        proposed = [a for a in archetypes if a.get("status") != "RATIFIED"]

        if not ratified:
            md.append("*No ratified archetypes registered yet.*\n")
        else:
            for r in ratified:
                crit = r.get("ratified_criteria", {})
                md.append(f"### 🟢 [{r['id']}] {r['name']} ({r.get('category', 'SMC')})")
                md.append(f"- **Description:** {r.get('description')}")
                md.append(f"- **Entry Trigger:** `{r.get('entry_trigger')}`")
                md.append(f"- **Invalidation Anchor:** `{r.get('invalidation_anchor')}`")
                md.append(f"- **Mandated Minimum R:R:** `{crit.get('min_rr', '1:2.0')}`")
                md.append(f"- **Stop Buffer Requirement:** `{crit.get('stop_buffer_rule', 'Per Active Playbook')}`")
                md.append(f"> **Supervisory Audit Verdict:** {r.get('vetting_verdict', 'Approved')} | *{r.get('auditor_notes', '')}*\n")

        if proposed:
            md.append("---\n## ⏳ Candidate Archetypes Under Review / Proposed\n")
            md.append("| ID | Name | Category | Status | Proposed Trigger |")
            md.append("| :--- | :--- | :--- | :---: | :--- |")
            for p in proposed:
                md.append(f"| `{p['id']}` | {p['name']} | {p['category']} | **{p['status']}** | {p['entry_trigger']} |")

        with open(self.md_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md))


# Global Singleton Instance
setup_registry = SetupRegistry()
