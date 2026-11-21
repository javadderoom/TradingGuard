"""
TradingGuard HITL - Evidence-Grounded Causal Fundamental Intelligence Package
"""

from hitl.fundamental.causal_engine import CORE_ASSETS, FundamentalCausalEngine, fundamental_engine
from hitl.fundamental.formatter import (
    format_asset_macro_card,
    format_council_macro_block,
    format_global_macro_card,
)
from hitl.fundamental.governor import (
    evaluate_fundamental_gate,
    get_enforcement_mode,
    get_governor_info,
    normalize_fundamental_symbol,
    set_enforcement_mode,
    toggle_enforcement_mode,
)

__all__ = [
    "CORE_ASSETS",
    "FundamentalCausalEngine",
    "fundamental_engine",
    "get_enforcement_mode",
    "set_enforcement_mode",
    "toggle_enforcement_mode",
    "get_governor_info",
    "evaluate_fundamental_gate",
    "normalize_fundamental_symbol",
    "format_global_macro_card",
    "format_asset_macro_card",
    "format_council_macro_block",
]
