"""
TradingGuard HITL - Quantitative Subagent Suite Architecture Tests
Verifies that all specialized subagents (QuantBacktestAuditor, StrategyOptimizer, PatternMiner)
are properly configured with YAML frontmatter, valid tools, and institutional mandates.
"""

import os
from pathlib import Path
import pytest

AGENTS_DIR = Path(__file__).resolve().parent.parent.parent / ".agents" / "agents"

REQUIRED_AGENTS = [
    "QuantBacktestAuditor",
    "StrategyOptimizer",
    "PatternMiner",
]

REQUIRED_MANDATES = {
    "QuantBacktestAuditor": [
        "Zero Developer Shortcuts",
        "Authentic Broker Realism",
        "Unvarnished Reporting",
        "Pure English Output",
    ],
    "StrategyOptimizer": [
        "Solve the Realized R:R Paradox",
        "Root-Engine Calibration",
        "Anti-Overfitting Rigor",
        "Seasonal Clock Alignment",
        "Pure English Output",
    ],
    "PatternMiner": [
        "Dual-Pillar Discovery",
        "Statistical Edge Validation",
        "Formal Setup Specification",
        "Pure English Output",
    ],
}

REQUIRED_TOOLS = [
    "run_command",
    "edit_file",
    "write_file",
    "view_file",
]


def test_agent_directories_and_files_exist():
    assert AGENTS_DIR.exists(), f"Directory not found: {AGENTS_DIR}"
    for agent_name in REQUIRED_AGENTS:
        agent_file = AGENTS_DIR / agent_name / "agent.md"
        assert agent_file.exists(), f"Agent file missing: {agent_file}"
        assert agent_file.stat().st_size > 0, f"Agent file is empty: {agent_file}"


def test_agent_frontmatter_and_tools():
    for agent_name in REQUIRED_AGENTS:
        agent_file = AGENTS_DIR / agent_name / "agent.md"
        content = agent_file.read_text(encoding="utf-8")
        
        # Verify YAML frontmatter markers
        assert content.startswith("---"), f"Missing frontmatter start in {agent_name}"
        second_dash = content.find("---", 3)
        assert second_dash != -1, f"Missing frontmatter end in {agent_name}"
        
        frontmatter = content[3:second_dash]
        assert f"name: {agent_name}" in frontmatter, f"Name mismatch in {agent_name}"
        assert "description:" in frontmatter, f"Description missing in {agent_name}"
        assert "tools:" in frontmatter, f"Tools missing in {agent_name}"
        
        # Verify required developer tools
        for tool in REQUIRED_TOOLS:
            assert f"- {tool}" in frontmatter, f"Tool {tool} missing in {agent_name}"


def test_agent_system_prompts_and_mandates():
    for agent_name, mandates in REQUIRED_MANDATES.items():
        agent_file = AGENTS_DIR / agent_name / "agent.md"
        content = agent_file.read_text(encoding="utf-8")
        
        for mandate in mandates:
            assert mandate in content, f"Mandate '{mandate}' missing from {agent_name} instructions"
