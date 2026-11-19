"""
Unit Tests for Review Council Governor (hitl/council_governor.py)
"""

import json
from pathlib import Path
import pytest

from hitl.council_governor import (
    STATE_FILE,
    get_council_state_info,
    is_council_enabled,
    set_council_enabled,
    toggle_council,
    format_council_status_card,
)


@pytest.fixture(autouse=True)
def clean_council_state():
    """Ensure clean state file before and after each test."""
    backup = None
    if STATE_FILE.exists():
        backup = STATE_FILE.read_text(encoding="utf-8")
        STATE_FILE.unlink(missing_ok=True)
    yield
    if backup is not None:
        STATE_FILE.write_text(backup, encoding="utf-8")
    else:
        STATE_FILE.unlink(missing_ok=True)


def test_council_default_state():
    """Verify default council state when no persistent file exists."""
    assert is_council_enabled() in (True, False)
    info = get_council_state_info()
    assert info["source"] == "config_default"


def test_set_and_get_council_state():
    """Verify setting council state persists to file and is retrievable."""
    # Explicitly disable
    res = set_council_enabled(False, toggled_by="test_suite")
    assert res is False
    assert is_council_enabled() is False

    info = get_council_state_info()
    assert info["council_enabled"] is False
    assert info["source"] == "runtime_state"
    assert info["toggled_by"] == "test_suite"
    assert info["last_toggled"] is not None

    # Verify on-disk file
    assert STATE_FILE.exists()
    disk_data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    assert disk_data["council_enabled"] is False

    # Explicitly enable
    res = set_council_enabled(True, toggled_by="admin")
    assert res is True
    assert is_council_enabled() is True
    info = get_council_state_info()
    assert info["council_enabled"] is True
    assert info["toggled_by"] == "admin"


def test_toggle_council():
    """Verify toggling inverts the state properly."""
    set_council_enabled(True, toggled_by="setup")
    assert is_council_enabled() is True

    new_st = toggle_council(toggled_by="toggle_test_1")
    assert new_st is False
    assert is_council_enabled() is False

    new_st_2 = toggle_council(toggled_by="toggle_test_2")
    assert new_st_2 is True
    assert is_council_enabled() is True


def test_format_council_status_card():
    """Verify format_council_status_card outputs correct Telegram cards and keyboards."""
    # Enabled state
    set_council_enabled(True, toggled_by="tester")
    card_en, kb_en = format_council_status_card()
    assert "🟢 *ENABLED*" in card_en
    assert "🔴 Disable Review Council" in kb_en["inline_keyboard"][0][0]["text"]
    assert kb_en["inline_keyboard"][0][0]["callback_data"] == "council_disable"

    # Disabled state
    set_council_enabled(False, toggled_by="tester")
    card_dis, kb_dis = format_council_status_card()
    assert "🔴 *DISABLED / BYPASSED*" in card_dis
    assert "🟢 Enable Review Council" in kb_dis["inline_keyboard"][0][0]["text"]
    assert kb_dis["inline_keyboard"][0][0]["callback_data"] == "council_enable"


def test_corrupt_state_file_resilience():
    """Verify that corrupt JSON in state file does not raise an unhandled exception."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text("{invalid json corrupt content...", encoding="utf-8")

    # Should safely catch exception and fall back to config default without crash
    enabled = is_council_enabled()
    assert isinstance(enabled, bool)
    info = get_council_state_info()
    assert isinstance(info, dict)
