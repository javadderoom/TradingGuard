"""
Tests for Soli-Trader Signal Ingestion and Formatting Service.
"""

import pytest
from hitl.signals.soli_service import (
    SoliTraderService,
    SYMBOL_MAP,
    _unpack_sveltekit_node,
    ACTIVE_SIGNALS_FILE
)


def test_symbol_mapping():
    assert SYMBOL_MAP.get("XAUUSD") == "XAUUSD_o"
    assert SYMBOL_MAP.get("EURUSD") == "EURUSD_o"
    assert SYMBOL_MAP.get("BTCUSDT") == "BTCUSD"


def test_sveltekit_node_unpacking():
    # Simulated sveltekit devalue structure
    simulated_data = [
        {"symbol": 1, "levels": 2},
        "XAUUSD",
        [3, 4],
        {"price": 5, "role": 6},
        {"price": 7, "role": 8},
        2680.5,
        "support",
        2720.0,
        "resistance"
    ]
    unpacked = _unpack_sveltekit_node(simulated_data)
    assert isinstance(unpacked, dict)
    assert unpacked.get("symbol") == "XAUUSD"
    levels = unpacked.get("levels", [])
    assert len(levels) == 2
    assert levels[0]["price"] == 2680.5
    assert levels[0]["role"] == "support"
    assert levels[1]["price"] == 2720.0
    assert levels[1]["role"] == "resistance"


def test_active_signals_disk_file_exists():
    assert ACTIVE_SIGNALS_FILE.exists(), "active_signals.json must exist after syncing"


def test_telegram_card_formatting():
    service = SoliTraderService()
    dummy_signal = {
        "entryId": "99",
        "symbol": "XAUUSD",
        "brokerSymbol": "XAUUSD_o",
        "category": "metals",
        "timeframe": "4h",
        "caption": "Strong institutional rejection at daily support.",
        "levels": [
            {"kind": "price", "price": 2680.0, "role": "support"},
            {"kind": "price", "price": 2720.0, "role": "resistance"}
        ],
        "supports": [2680.0],
        "resistances": [2720.0],
        "imageId": "41",
        "imageUrl": "https://soli-trader.com/signals/img/41",
        "detailUrl": "https://soli-trader.com/signals/99",
        "version": 1
    }
    card = service.format_telegram_card(dummy_signal)
    assert "XAUUSD" in card
    assert "XAUUSD_o" in card
    assert "2680.0" in card
    assert "2720.0" in card
    assert "Strong institutional rejection" in card
    assert "https://soli-trader.com/signals/99" in card
