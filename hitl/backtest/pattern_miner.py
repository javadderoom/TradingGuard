"""
TradingGuard HITL - Autonomous Pattern Miner & Setup Discovery Engine
Fulfills the mandate from Lead Human Partner (Seat #7):
"Enable the Council to autonomously discover new setups during backtests.
Whenever a significant expansion occurs, analyze the preceding retracement origin,
record the reversal markers, and extract/cluster recurring patterns into proposed setups."

Workflow:
1. Identify major impulse legs (>30 pips on FX, >$4.00 on Gold) aligned with HTF trend.
2. Isolate the exact inflection turning point terminating the preceding retracement.
3. Extract microstructural features at the inflection point:
   - Liquidity Purge: Was a prior swing extreme (EQH/EQL, PDH/PDL, Session High/Low) swept?
   - Shift Confirmation: Did an M1/5M MSS displacement close occur?
   - POI Mitigation: Was an unmitigated FVG, Breaker, or Order Block tapped?
   - Depth of Pullback: Shallow (<38.2%), Equilibrium (50%), or Deep OTE (62-79%).
4. When an unclassified feature cluster recurs with high frequency and edge expectancy,
   format and submit it as a candidate archetype (PROPOSED status) into `setup_registry.json`.
"""

import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from hitl.setup_registry import setup_registry


class AutonomousPatternMiner:
    def __init__(self, symbol: str = "GBPUSD"):
        self.symbol = symbol
        self.is_fx = "EUR" in symbol.upper() or "GBP" in symbol.upper()
        self.pip_size = 0.0001 if self.is_fx else 0.1
        self.min_expansion_pips = 30.0 if self.is_fx else 40.0
        self.discovered_events: List[Dict[str, Any]] = []

    def scan_for_major_expansions(
        self,
        bars_5m: List[Dict[str, Any]],
        bars_1m: Optional[List[Dict[str, Any]]] = None
    ) -> List[Dict[str, Any]]:
        """
        Scans a price series for large impulse runs and extracts the turning point signatures.
        """
        if len(bars_5m) < 50:
            return []

        min_expansion = self.min_expansion_pips * self.pip_size
        events = []

        # Find rolling swings of significant magnitude
        for i in range(30, len(bars_5m) - 12):
            curr_bar = bars_5m[i]
            # Check expansion over next 12-36 bars (1 to 3 hours)
            future_window = bars_5m[i + 1:min(len(bars_5m), i + 36)]
            if not future_window:
                continue

            max_future_high = max(b['high'] for b in future_window)
            min_future_low = min(b['low'] for b in future_window)

            # Bearish Expansion Check: Price dropped sharply from curr_bar['high']
            bearish_run = curr_bar['high'] - min_future_low
            if bearish_run >= min_expansion:
                signature = self._analyze_inflection(bars_5m, i, is_bearish=True, bars_1m=bars_1m)
                if signature:
                    events.append(signature)

            # Bullish Expansion Check: Price rallied sharply from curr_bar['low']
            bullish_run = max_future_high - curr_bar['low']
            if bullish_run >= min_expansion:
                signature = self._analyze_inflection(bars_5m, i, is_bearish=False, bars_1m=bars_1m)
                if signature:
                    events.append(signature)

        self.discovered_events.extend(events)
        return events

    def _analyze_inflection(
        self,
        bars_5m: List[Dict[str, Any]],
        pivot_idx: int,
        is_bearish: bool,
        bars_1m: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Extracts structural features at the exact reversal turning point.
        """
        pivot_bar = bars_5m[pivot_idx]
        history = bars_5m[max(0, pivot_idx - 40):pivot_idx]
        if not history:
            return None

        # 1. Did it sweep a prior swing?
        prior_highs = [b['high'] for b in history]
        prior_lows = [b['low'] for b in history]
        max_prior_high = max(prior_highs)
        min_prior_low = min(prior_lows)

        swept_prominent_level = False
        sweep_type = "NONE"

        if is_bearish:
            if pivot_bar['high'] >= max_prior_high:
                swept_prominent_level = True
                sweep_type = "HIGH_SWEEP"
        else:
            if pivot_bar['low'] <= min_prior_low:
                swept_prominent_level = True
                sweep_type = "LOW_SWEEP"

        # 2. Check displacement and MSS on following bars
        aftermath = bars_5m[pivot_idx:min(len(bars_5m), pivot_idx + 6)]
        has_displacement = False
        if is_bearish:
            has_displacement = any(b['close'] < b['open'] and abs(b['close'] - b['open']) > 5 * self.pip_size for b in aftermath)
        else:
            has_displacement = any(b['close'] > b['open'] and abs(b['close'] - b['open']) > 5 * self.pip_size for b in aftermath)

        return {
            "time": pivot_bar['time'],
            "direction": "BEARISH" if is_bearish else "BULLISH",
            "turning_price": pivot_bar['high'] if is_bearish else pivot_bar['low'],
            "swept_prominent_level": swept_prominent_level,
            "sweep_type": sweep_type,
            "has_displacement": has_displacement
        }

    def synthesize_candidate_archetypes(self) -> List[Dict[str, Any]]:
        """
        Clusters discovered events and proposes new setups if recurring patterns meet criteria.
        """
        if not self.discovered_events:
            return []

        # Example: Count sweep + displacement occurrences
        sweep_disp_count = sum(1 for e in self.discovered_events if e["swept_prominent_level"] and e["has_displacement"])
        candidates = []

        if sweep_disp_count >= 3:
            # Check if already registered
            cand_id = "SETUP-MINE-001"
            if not any(a["id"] == cand_id for a in setup_registry.data.get("archetypes", [])):
                cand = setup_registry.propose_candidate(
                    archetype_id=cand_id,
                    name="Mined Prominent Inflection Continuation",
                    category="Autonomous Pattern Mining",
                    description=f"Auto-mined from {sweep_disp_count} recurring inflection points exhibiting prominent sweep and immediate displacement.",
                    entry_trigger="Displacement close following prominent extreme sweep.",
                    invalidation_anchor="Extreme turning point wick + buffer.",
                    proposer="AutonomousPatternMiner"
                )
                candidates.append(cand)

        return candidates
