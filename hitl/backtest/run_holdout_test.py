"""
TradingGuard HITL — True Holdout Test Runner (Pack 7).

Runs the FROZEN rule set (hitl/backtest/holdout_frozen_rules_2026-11-07.json)
over a genuinely held-out period and writes a trade-level ledger plus a
summary. It exists because the reported +17.0R was post-hoc: the bans
(ARCH-002, ARCH-009, Silver Bullet) were picked after seeing Jan–Nov 2026,
so that year is the TUNING period and can never be a holdout again.

Anti-tamper guarantees (the whole point of this file):
  * The runner loads the FROZEN rule file, never the live playbook, so a
    rule change made after freezing cannot leak into the holdout.
  * At startup it re-hashes the source files the rules live in
    (fast_screener.py, evaluator.py, data_feed.py, council_playbook.json,
    setup_registry.json, setup_registry.py) and REFUSES to run if any hash
    differs from the frozen record. To change a rule you must re-freeze
    (``--freeze``), which stamps a new date/hash — the tampering is then
    visible in the output instead of silent.
  * Any period overlapping the tuning year (2026-01-01..2026-11-06) is
    REFUSED unless ``--allow-tuning-period`` is passed, and then the output
    is labelled TUNING-PERIOD, never HOLDOUT.
  * Missing data FAILS LOUDLY (exit 3) instead of silently running on a
    partial sample: no data source at all, or >10% of checkpoints without
    bars, aborts the run.

What is actually tested (screener mode, the default):
  screen_ict_session(closed_bars_only=True) -> mechanical decision from the
  screener's own refs (entry_ref / sl_ref / recommended_target_rr) ->
  evaluate_council_decision() (canonical simulator, Pack 4: SL-first,
  symmetric spread, $0.10 commission / 0.01 lot, 75-min TTL) ->
  summarize_pnl() (Pack 6: realised vs unrealised split).
  This is deterministic and reproducible. The LLM council is NOT in this
  loop: one agy.exe call per setup is slow, non-deterministic (no
  temperature/seed flag exists), and would make the holdout unreproducible.
  A council holdout needs a separate protocol (fixed model + logged raw
  outputs); it is not claimed here.

Windows (MT5) usage — the run itself needs MT5, it cannot run on Linux:
  cd G:\\Code\\TradingGuard
  python -m hitl.backtest.run_holdout_test
  python -m hitl.backtest.run_holdout_test --start 2026-11-07 --end 2026-12-31 --symbols XAUUSD,GBPUSD
  python -m hitl.backtest.run_holdout_test --start 2025-01-06 --end 2025-03-31 --data-dir backtest_results\\cache

Data sources (in order):
  1. Live MT5 (default): bars are fetched with mt5.copy_rates_from, the
     same call the 60/90-day runners use. MT5 must be running and logged in.
  2. --data-dir: a directory of M1 cache files, M1_<SYMBOL>_<YEAR>.parquet
     (same layout as backtest_results/cache, written by
     htf_macro_runner_backtest.py) or M1_<SYMBOL>_<YEAR>.csv with columns
     time,open,high,low,close,tick_volume (time = unix epoch seconds).
     5M/1H bars are resampled from M1, which is equivalent for closed bars.

Checkpoints use the same milestone clock as the 60/90-day runners
(10:00/10:30/11:00 London, 15:00/15:30/16:00 NY, 17:30/18:00 Silver Bullet,
MT5 terminal time). One trade max per (symbol, day, window); live daily
discipline is enforced per symbol per day: max 3 trades, stop at -$34
realised daily loss, stop at +$35 realised daily profit (frozen caps).

Exit codes: 0 = holdout completed; 2 = config / tuning-guard / frozen-code
mismatch; 3 = data failure (missing source or >10% checkpoints without bars).
"""

import argparse
import csv
import datetime
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from hitl.backtest.evaluator import (
    CANONICAL_TTL_MINUTES,
    DEFAULT_COMMISSION_USD_PER_001_LOT,
    evaluate_council_decision,
    summarize_pnl,
)
from hitl.backtest.fast_screener import screen_ict_session

FROZEN_PATH = Path(__file__).resolve().parent / "holdout_frozen_rules_2026-11-07.json"

# Jan–Nov 2026 is the tuning year (the +17.0R bans were picked from it).
TUNING_START = datetime.date(2026, 1, 1)
TUNING_END = datetime.date(2026, 11, 6)
DEFAULT_START = datetime.date(2026, 11, 7)
DEFAULT_END = datetime.date(2026, 12, 31)

DEFAULT_SYMBOLS = ["XAUUSD", "XAGUSD", "EURUSD", "GBPUSD"]

# Same milestone clock as the 60/90-day runners (MT5 terminal time).
CHECKPOINTS: List[Tuple[int, int, str, str]] = [
    (10, 0, "London Pre-Open", "London"),
    (10, 30, "London Open", "London"),
    (11, 0, "London Post-Open", "London"),
    (15, 0, "NY Pre-Open", "NY"),
    (15, 30, "NY Open", "NY"),
    (16, 0, "NY Post-Open", "NY"),
    (17, 30, "NY Silver Bullet Open", "Silver Bullet"),
    (18, 0, "NY Silver Bullet Mid", "Silver Bullet"),
]

# Source files whose hashes are frozen. Any change -> runner refuses to run.
SOURCE_FILES = [
    "hitl/backtest/fast_screener.py",
    "hitl/backtest/evaluator.py",
    "hitl/backtest/data_feed.py",
    "hitl/memory/council_playbook.json",
    "hitl/memory/setup_registry.json",
    "hitl/setup_registry.py",
]

MAX_MISSING_FRACTION = 0.10
FORWARD_WINDOW_HOURS = 12

LEDGER_FIELDS = [
    "date", "session", "checkpoint", "symbol", "archetype_id", "setup_type",
    "decision", "entry", "sl", "tp", "target_rr", "risk_usd", "status",
    "fill_minute", "exit_minute", "rr_realized", "pnl_usd", "is_realized",
    "realized_pnl_usd", "realized_R", "floating_pnl_usd", "floating_R",
    "notes",
]


def pip_value_per_001_lot(symbol: str) -> float:
    """$ per price point at 0.01 lot. Mirrors evaluator.evaluate_council_decision."""
    sym = symbol.upper()
    if "XAU" in sym:
        return 1.0
    if "XAG" in sym:
        return 50.0
    if "EUR" in sym or "GBP" in sym:
        return 1000.0
    return 1.0


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(args: List[str]) -> Optional[str]:
    try:
        out = subprocess.run(
            ["git"] + args, cwd=str(BASE_DIR), capture_output=True,
            text=True, timeout=30,
        )
        return out.stdout.strip() if out.returncode == 0 else None
    except Exception:
        return None


# --------------------------------------------------------------------------
# Frozen rule set
# --------------------------------------------------------------------------

def build_frozen_rules() -> Dict[str, Any]:
    """Snapshot the rule set exactly as it stands in this working tree."""
    playbook = json.loads(
        (BASE_DIR / "hitl/memory/council_playbook.json").read_text(encoding="utf-8")
    )
    registry = json.loads(
        (BASE_DIR / "hitl/memory/setup_registry.json").read_text(encoding="utf-8")
    )
    head = _git(["rev-parse", "HEAD"])
    dirty = _git(["status", "--porcelain", "--"] + SOURCE_FILES)
    hashes = {}
    for rel in SOURCE_FILES:
        p = BASE_DIR / rel
        hashes[rel] = sha256_file(p) if p.exists() else "MISSING"

    active = [r for r in playbook.get("active_rules", []) if r.get("status") == "ACTIVE"]
    superseded = [r for r in playbook.get("active_rules", []) if r.get("status") != "ACTIVE"]
    ratified = [a["id"] for a in registry.get("archetypes", []) if a.get("status") == "RATIFIED"]

    return {
        "frozen_rule_set": "TradingGuard holdout — frozen 2026-11-07 (Pack 7)",
        "frozen_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "base_commit": head,
        "working_tree_dirty_at_freeze": bool(dirty),
        "dirty_files_at_freeze": dirty.splitlines() if dirty else [],
        "source_file_sha256": hashes,
        "tuning_period": {"start": str(TUNING_START), "end": str(TUNING_END)},
        "default_holdout_period": {"start": str(DEFAULT_START), "end": str(DEFAULT_END)},
        "risk_caps": {
            "max_risk_usd_per_trade": 12.0,
            "max_daily_loss_usd": 34.0,
            "max_daily_profit_usd": 35.0,
            "max_trades_per_day_per_symbol": 3,
            "lot": 0.01,
            "note": "RULE-CORE-001 ($12) + live daily limits. $34 daily loss set 2026-11-07.",
        },
        "simulator": {
            "closed_bars_only": True,
            "sl_first": True,
            "commission_usd_per_001_lot": DEFAULT_COMMISSION_USD_PER_001_LOT,
            "slippage_pts": 0.0,
            "ttl_minutes": CANONICAL_TTL_MINUTES,
            "forward_window_hours": FORWARD_WINDOW_HOURS,
            "breakeven_rr": 2.0,
            "target_rr_cap": 3.5,
            "spreads_pts": {"XAUUSD": 0.15, "XAGUSD": 0.030, "EURUSD": 0.00018, "GBPUSD": 0.00025},
        },
        "screener": {
            "checkpoints": [
                {"hour": h, "minute": m, "label": label, "window": window}
                for h, m, label, window in CHECKPOINTS
            ],
            "one_trade_per_symbol_day_window": True,
            "bans_coded_in_screener": {
                "silver_bullet_banned_symbols": ["XAUUSD", "GBPUSD"],
                "gbp_ny_open_bypass": True,
                "note": "Bans are hard-coded in fast_screener.py and therefore covered "
                        "by its frozen hash. No additional bans are applied by this runner.",
            },
            "ratified_archetypes_at_freeze": ratified,
        },
        "symbols": DEFAULT_SYMBOLS,
        "playbook": {
            "version": playbook.get("version"),
            "last_updated": playbook.get("last_updated"),
            "active_rules": active,
            "superseded_rules_preserved_for_history": superseded,
            "note": "ACTIVE rules are the frozen set. SUPERSEDED rules (the old $2 caps) "
                    "are preserved verbatim for history and are NOT part of the frozen set.",
        },
        "honesty_notes": [
            "The 2026-11-06 analysis showed the +17.0R calibrated result was post-hoc: "
            "its bans were picked after seeing Jan–Nov 2026. This holdout therefore tests "
            "the rules AS THEY STAND at freeze time, including ARCH-002 and ARCH-009, which "
            "are RATIFIED in the registry at freeze time — no re-tuned subset is applied.",
            "The LLM council is NOT in this loop (non-deterministic, no temperature/seed "
            "flag). This holdout measures the rule-based screener + canonical simulator only.",
            "If any source file hash differs from this record at run time, the runner "
            "refuses to run. Re-freeze with --freeze to bless a new rule set, and record "
            "why in the commit message — a re-freeze after seeing holdout results is "
            "itself tuning on the holdout and must be disclosed as such.",
        ],
    }


def freeze_rules() -> Tuple[Path, str]:
    frozen = build_frozen_rules()
    FROZEN_PATH.write_text(json.dumps(frozen, indent=2, ensure_ascii=False), encoding="utf-8")
    return FROZEN_PATH, sha256_file(FROZEN_PATH)


def load_frozen_rules() -> Dict[str, Any]:
    if not FROZEN_PATH.exists():
        raise FileNotFoundError(
            f"Frozen rule file not found: {FROZEN_PATH}\n"
            "Generate it with: python -m hitl.backtest.run_holdout_test --freeze"
        )
    return json.loads(FROZEN_PATH.read_text(encoding="utf-8"))


def verify_source_hashes(frozen: Dict[str, Any]) -> List[str]:
    """Return a list of mismatch descriptions (empty = all hashes match)."""
    mismatches = []
    recorded = frozen.get("source_file_sha256", {})
    for rel, expected in recorded.items():
        p = BASE_DIR / rel
        if not p.exists():
            mismatches.append(f"{rel}: file missing (was {expected[:12]}...)")
            continue
        actual = sha256_file(p)
        if actual != expected:
            mismatches.append(
                f"{rel}: changed since freeze (frozen {expected[:12]}..., now {actual[:12]}...)"
            )
    return mismatches


# --------------------------------------------------------------------------
# Bar sources
# --------------------------------------------------------------------------

def _ceil_to_5m_boundary(dt: datetime.datetime) -> datetime.datetime:
    """Rounds a timestamp up to the next 5-minute bar boundary (unchanged if already on one)."""
    if dt.second == 0 and dt.microsecond == 0 and dt.minute % 5 == 0:
        return dt
    base = dt.replace(second=0, microsecond=0)
    return base + datetime.timedelta(minutes=5 - (dt.minute % 5))


def _convert_records(bars) -> List[Dict[str, Any]]:
    """Same bar dict shape as hitl.backtest.data_feed._convert_records."""
    if bars is None or len(bars) == 0:
        return []
    return [
        {
            "time": int(b[0]),
            "dt": datetime.datetime.fromtimestamp(int(b[0]), tz=datetime.timezone.utc),
            "open": float(b[1]),
            "high": float(b[2]),
            "low": float(b[3]),
            "close": float(b[4]),
            "tick_volume": int(b[5]),
        }
        for b in bars
    ]


def resample_bars(m1_bars: List[Dict[str, Any]], minutes: int) -> List[Dict[str, Any]]:
    """Resample M1 bars to N-minute bars. Equivalent to MT5's own TF bars for closed bars."""
    if not m1_bars:
        return []
    out: List[Dict[str, Any]] = []
    cur_key = None
    cur = None
    for b in sorted(m1_bars, key=lambda x: x["time"]):
        key = (b["time"] // (minutes * 60)) * (minutes * 60)
        if key != cur_key:
            if cur is not None:
                out.append(cur)
            cur_key = key
            cur = {
                "time": key,
                "dt": datetime.datetime.fromtimestamp(key, tz=datetime.timezone.utc),
                "open": b["open"], "high": b["high"], "low": b["low"],
                "close": b["close"], "tick_volume": b["tick_volume"],
            }
        else:
            cur["high"] = max(cur["high"], b["high"])
            cur["low"] = min(cur["low"], b["low"])
            cur["close"] = b["close"]
            cur["tick_volume"] += b["tick_volume"]
    if cur is not None:
        out.append(cur)
    return out


class DataUnavailable(RuntimeError):
    """Raised when no usable data source exists for a symbol/period."""


class MT5BarSource:
    """Bars straight from a running MT5 terminal (same calls as the 60/90-day runners)."""

    def __init__(self):
        try:
            import MetaTrader5 as mt5
        except ImportError as exc:
            raise DataUnavailable(
                "MetaTrader5 package is not installed / MT5 is not available. "
                "Run this on the Windows machine with MT5 running, or pass --data-dir "
                "with M1 cache files."
            ) from exc
        self.mt5 = mt5
        if not mt5.initialize():
            raise DataUnavailable(
                "MT5 initialize() failed — is the terminal running and logged in? "
                "Alternatively pass --data-dir with M1 cache files."
            )

    def _resolve(self, symbol: str) -> str:
        from hitl.mt5_engine import MT5Engine  # lazy: imports MetaTrader5
        resolved = MT5Engine().resolve_symbol(symbol)
        if not resolved:
            raise DataUnavailable(f"MT5 could not resolve symbol {symbol}.")
        return resolved

    def _bars(self, symbol: str, end_dt: datetime.datetime, timeframe, count: int):
        resolved = self._resolve(symbol)
        return _convert_records(
            self.mt5.copy_rates_from(resolved, timeframe, end_dt, count)
        )

    def bars_5m(self, symbol: str, end_dt: datetime.datetime, count: int = 120):
        return self._bars(symbol, end_dt, self.mt5.TIMEFRAME_M5, count)

    def bars_1h(self, symbol: str, end_dt: datetime.datetime, count: int = 80):
        return self._bars(symbol, end_dt, self.mt5.TIMEFRAME_H1, count)

    def forward_m1(self, symbol: str, start_dt: datetime.datetime, hours: int = FORWARD_WINDOW_HOURS):
        resolved = self._resolve(symbol)
        start = _ceil_to_5m_boundary(start_dt)
        end = start + datetime.timedelta(hours=hours)
        return _convert_records(
            self.mt5.copy_rates_range(resolved, self.mt5.TIMEFRAME_M1, start, end)
        )


class FileBarSource:
    """Bars from M1 cache files: M1_<SYMBOL>_<YEAR>.parquet or .csv in --data-dir."""

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        if not self.data_dir.is_dir():
            raise DataUnavailable(f"--data-dir is not a directory: {data_dir}")
        self._m1: Dict[str, List[Dict[str, Any]]] = {}

    def _load_m1(self, symbol: str, year: int) -> List[Dict[str, Any]]:
        key = f"{symbol}_{year}"
        if key in self._m1:
            return self._m1[key]
        bars: List[Dict[str, Any]] = []
        pq = self.data_dir / f"M1_{symbol}_{year}.parquet"
        csv_path = self.data_dir / f"M1_{symbol}_{year}.csv"
        if pq.exists():
            try:
                import pandas as pd
            except ImportError as exc:
                raise DataUnavailable(
                    "pandas is required to read parquet cache files."
                ) from exc
            df = pd.read_parquet(pq)
            for row in df.itertuples():
                bars.append({
                    "time": int(row.time),
                    "dt": datetime.datetime.fromtimestamp(int(row.time), tz=datetime.timezone.utc),
                    "open": float(row.open), "high": float(row.high),
                    "low": float(row.low), "close": float(row.close),
                    "tick_volume": int(row.tick_volume),
                })
        elif csv_path.exists():
            with open(csv_path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    bars.append({
                        "time": int(float(row["time"])),
                        "dt": datetime.datetime.fromtimestamp(int(float(row["time"])), tz=datetime.timezone.utc),
                        "open": float(row["open"]), "high": float(row["high"]),
                        "low": float(row["low"]), "close": float(row["close"]),
                        "tick_volume": int(float(row.get("tick_volume", 0) or 0)),
                    })
        else:
            raise DataUnavailable(
                f"No M1 cache file for {symbol} {year} in {self.data_dir} "
                f"(looked for M1_{symbol}_{year}.parquet / .csv). "
                "Fetch it from MT5 first (see docs/HOLDOUT_TEST.md) or run without "
                "--data-dir on a machine with MT5 running."
            )
        bars.sort(key=lambda b: b["time"])
        self._m1[key] = bars
        return bars

    def _slice(self, symbol: str, end_dt: datetime.datetime, minutes: int, count: int):
        end_ts = int(end_dt.replace(tzinfo=datetime.timezone.utc).timestamp())
        m1 = self._load_m1(symbol, end_dt.year)
        # Bars starting at/before end_dt; the screener drops the forming bar itself.
        upto = [b for b in m1 if b["time"] <= end_ts]
        if not upto:
            return []
        resampled = resample_bars(upto, minutes)
        return resampled[-count:]

    def bars_5m(self, symbol: str, end_dt: datetime.datetime, count: int = 120):
        return self._slice(symbol, end_dt, 5, count)

    def bars_1h(self, symbol: str, end_dt: datetime.datetime, count: int = 80):
        return self._slice(symbol, end_dt, 60, count)

    def forward_m1(self, symbol: str, start_dt: datetime.datetime, hours: int = FORWARD_WINDOW_HOURS):
        start = _ceil_to_5m_boundary(start_dt)
        start_ts = int(start.replace(tzinfo=datetime.timezone.utc).timestamp())
        end_ts = start_ts + hours * 3600
        m1 = self._load_m1(symbol, start_dt.year)
        return [b for b in m1 if start_ts <= b["time"] < end_ts]

# --------------------------------------------------------------------------
# Holdout loop
# --------------------------------------------------------------------------

def trading_days(start: datetime.date, end: datetime.date) -> List[datetime.date]:
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5:  # Mon–Fri
            days.append(d)
        d += datetime.timedelta(days=1)
    return days


def overlaps_tuning(start: datetime.date, end: datetime.date) -> bool:
    return start <= TUNING_END and end >= TUNING_START


def build_mechanical_decision(
    screener: Dict[str, Any], frozen: Dict[str, Any]
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """Turn a passing screener setup into the simulator's decision dict.

    Direction comes from the setup_type prefix (BULLISH_* -> BUY_LIMIT,
    BEARISH_* -> SELL_LIMIT). Entry/SL are the screener's own refs; TP is
    entry +/- target_rr x risk, capped at the frozen target_rr_cap.
    Returns (decision_dict, skip_reason). skip_reason is set when the
    setup must not be traded (e.g. its risk exceeds the frozen $12 cap).
    """
    setup_type = screener.get("setup_type", "")
    if setup_type.startswith("BULLISH"):
        direction, is_buy = "BUY_LIMIT", True
    elif setup_type.startswith("BEARISH"):
        direction, is_buy = "SELL_LIMIT", False
    else:
        return None, f"NO_DIRECTION:{setup_type}"

    entry = screener.get("entry_ref")
    sl = screener.get("sl_ref")
    if entry is None or sl is None:
        return None, "NO_ENTRY_SL_REFS"
    risk_pts = abs(float(entry) - float(sl))
    if risk_pts <= 0:
        return None, "ZERO_RISK_DISTANCE"

    symbol = screener.get("_symbol", "")
    risk_usd = risk_pts * pip_value_per_001_lot(symbol) * (frozen["risk_caps"]["lot"] / 0.01)
    if risk_usd > frozen["risk_caps"]["max_risk_usd_per_trade"]:
        return None, f"RISK_CAP_SKIP:risk ${risk_usd:.2f} > ${frozen['risk_caps']['max_risk_usd_per_trade']:.2f}"

    target_rr = min(
        float(screener.get("recommended_target_rr") or 2.0),
        float(frozen["simulator"]["target_rr_cap"]),
    )
    sign = 1 if is_buy else -1
    tp = float(entry) + sign * target_rr * risk_pts
    return {
        "decision": direction,
        "entry": float(entry),
        "sl": float(sl),
        "tp": tp,
        "lot": frozen["risk_caps"]["lot"],
        "rr": target_rr,
    }, None


def run_holdout(
    start: datetime.date,
    end: datetime.date,
    symbols: List[str],
    source,
    frozen: Dict[str, Any],
    out_dir: Path,
    allow_tuning_period: bool = False,
) -> Dict[str, Any]:
    """Execute the holdout loop. Returns the summary dict. Raises SystemExit-style
    RuntimeError with a clear message on data failure (caller maps to exit 3)."""
    caps = frozen["risk_caps"]
    sim = frozen["simulator"]
    is_tuning_label = overlaps_tuning(start, end)
    period_label = "TUNING-PERIOD" if is_tuning_label else "HOLDOUT"

    ledger: List[Dict[str, Any]] = []
    missing = 0
    total_checkpoints = 0
    # Per (symbol, date): realised day PnL, trades filled, windows used.
    day_state: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for day in trading_days(start, end):
        date_str = day.isoformat()
        for hour, minute, label, window in CHECKPOINTS:
            milestone = datetime.datetime(day.year, day.month, day.day, hour, minute)
            for symbol in symbols:
                total_checkpoints += 1
                state = day_state.setdefault(
                    (symbol, date_str),
                    {"realized_pnl": 0.0, "trades": 0, "windows": set()},
                )
                try:
                    bars_5m = source.bars_5m(symbol, milestone, count=120)
                    bars_1h = source.bars_1h(symbol, milestone, count=80)
                except DataUnavailable as exc:
                    raise RuntimeError(str(exc)) from exc
                if not bars_5m or not bars_1h:
                    missing += 1
                    ledger.append(_ledger_row(
                        date_str, label, milestone, symbol, None, "NONE",
                        "STAND_ASIDE", None, None, None, None, None,
                        "NO_DATA", None, None, None, 0.0, True, 0.0, None, 0.0, None,
                        "Missing bars for this checkpoint",
                    ))
                    continue

                screener = screen_ict_session(
                    list(bars_5m), list(bars_1h), symbol, milestone.hour,
                    closed_bars_only=True,
                )
                if not screener.get("has_setup"):
                    ledger.append(_ledger_row(
                        date_str, label, milestone, symbol, None,
                        screener.get("setup_type", "NONE"),
                        "STAND_ASIDE", None, None, None, None, None,
                        "STAND_ASIDE", None, None, None, 0.0, True, 0.0, None, 0.0, None,
                        str(screener.get("reason", ""))[:200],
                    ))
                    continue

                # One trade per (symbol, day, window); live daily discipline.
                skip = None
                if window in state["windows"]:
                    skip = "WINDOW_ORDER_ACTIVE"
                elif state["trades"] >= caps["max_trades_per_day_per_symbol"]:
                    skip = "DAILY_TRADE_CAP"
                elif state["realized_pnl"] <= -caps["max_daily_loss_usd"]:
                    skip = "DAILY_LOSS_CAP"
                elif state["realized_pnl"] >= caps["max_daily_profit_usd"]:
                    skip = "DAILY_PROFIT_CAP"
                if skip:
                    ledger.append(_ledger_row(
                        date_str, label, milestone, symbol,
                        screener.get("archetype_id"), screener.get("setup_type"),
                        "SKIPPED", screener.get("entry_ref"), screener.get("sl_ref"),
                        None, screener.get("recommended_target_rr"), None,
                        skip, None, None, None, 0.0, True, 0.0, None, 0.0, None,
                        f"Setup found but skipped: {skip}",
                    ))
                    continue

                screener["_symbol"] = symbol
                decision, skip_reason = build_mechanical_decision(screener, frozen)
                if decision is None:
                    ledger.append(_ledger_row(
                        date_str, label, milestone, symbol,
                        screener.get("archetype_id"), screener.get("setup_type"),
                        "SKIPPED", screener.get("entry_ref"), screener.get("sl_ref"),
                        None, screener.get("recommended_target_rr"), None,
                        skip_reason or "SKIP", None, None, None,
                        0.0, True, 0.0, None, 0.0, None,
                        f"Setup found but not traded: {skip_reason}",
                    ))
                    continue

                try:
                    forward_m1 = source.forward_m1(
                        symbol, milestone, hours=sim["forward_window_hours"]
                    )
                except DataUnavailable as exc:
                    raise RuntimeError(str(exc)) from exc
                eval_res = evaluate_council_decision(
                    decision, forward_m1, symbol,
                    breakeven_rr=float(sim["breakeven_rr"]),
                    target_rr_cap=float(sim["target_rr_cap"]),
                    commission_usd=float(sim["commission_usd_per_001_lot"]),
                    slippage_pts=float(sim["slippage_pts"]),
                    ttl_minutes=int(sim["ttl_minutes"]),
                )
                risk_usd = abs(decision["entry"] - decision["sl"]) * pip_value_per_001_lot(symbol)
                pnl = float(eval_res["realized_pnl_usd"])
                is_realized = bool(eval_res["is_realized"])
                realized_pnl = pnl if is_realized else 0.0
                floating_pnl = pnl if not is_realized else 0.0
                realized_r = (realized_pnl / risk_usd) if (is_realized and risk_usd > 0) else None
                floating_r = (floating_pnl / risk_usd) if (not is_realized and risk_usd > 0) else None

                state["trades"] += 1
                state["windows"].add(window)
                state["realized_pnl"] += realized_pnl

                ledger.append(_ledger_row(
                    date_str, label, milestone, symbol,
                    screener.get("archetype_id"), screener.get("setup_type"),
                    decision["decision"], decision["entry"], decision["sl"],
                    decision["tp"], decision["rr"], round(risk_usd, 2),
                    eval_res["status"], eval_res.get("fill_minute"),
                    eval_res.get("exit_minute"), eval_res.get("rr_realized"),
                    pnl, is_realized, round(realized_pnl, 2),
                    (round(realized_r, 2) if realized_r is not None else None),
                    round(floating_pnl, 2),
                    (round(floating_r, 2) if floating_r is not None else None),
                    str(eval_res.get("notes", ""))[:200],
                ))

    if total_checkpoints and missing / total_checkpoints > MAX_MISSING_FRACTION:
        raise RuntimeError(
            f"DATA FAILURE: {missing}/{total_checkpoints} checkpoints "
            f"({missing / total_checkpoints:.1%}) had no bars — above the "
            f"{MAX_MISSING_FRACTION:.0%} limit. The sample would be unreliable, "
            "so no holdout result is reported. Check MT5 data / --data-dir."
        )

    summary = build_summary(
        ledger, start, end, symbols, frozen, period_label, missing, total_checkpoints
    )
    write_outputs(ledger, summary, frozen, out_dir)
    return summary


def _ledger_row(date_str, label, milestone, symbol, archetype_id, setup_type,
                decision, entry, sl, tp, target_rr, risk_usd, status,
                fill_minute, exit_minute, rr_realized, pnl, is_realized,
                realized_pnl, realized_r, floating_pnl, floating_r, notes):
    return {
        "date": date_str,
        "session": label,
        "checkpoint": milestone.strftime("%Y-%m-%d %H:%M"),
        "symbol": symbol,
        "archetype_id": archetype_id,
        "setup_type": setup_type,
        "decision": decision,
        "entry": entry,
        "sl": sl,
        "tp": tp,
        "target_rr": target_rr,
        "risk_usd": risk_usd,
        "status": status,
        "fill_minute": fill_minute,
        "exit_minute": exit_minute,
        "rr_realized": rr_realized,
        "pnl_usd": pnl,
        "is_realized": is_realized,
        "realized_pnl_usd": realized_pnl,
        "realized_R": realized_r,
        "floating_pnl_usd": floating_pnl,
        "floating_R": floating_r,
        "notes": notes,
    }


def build_summary(ledger, start, end, symbols, frozen, period_label, missing, total_checkpoints):
    trades = [r for r in ledger if r["decision"] in ("BUY_LIMIT", "SELL_LIMIT")]
    realized_trades = [r for r in trades if r["is_realized"]]
    # NOTE: the ledger splits the evaluator's PnL into realized_pnl_usd /
    # floating_pnl_usd, but summarize_pnl() follows the evaluator's own
    # convention — the raw PnL lives in one key and is_realized decides
    # which side of the split it belongs to. Sum the RAW column ("pnl_usd"),
    # not the already-split realised column, or OPEN_AT_END floating PnL
    # would vanish from the unrealised total (Pack 7 test caught this:
    # unrealised showed $0.00 while the open trade floated +$6.93).
    pnl_split = summarize_pnl(trades, pnl_key="pnl_usd")
    wins = sum(1 for r in trades if r["status"] == "WIN")
    losses = sum(1 for r in trades if r["status"] == "LOSS")
    bes = sum(1 for r in trades if r["status"] == "BREAKEVEN")
    opens = sum(1 for r in trades if r["status"] == "OPEN_AT_END")
    net_r = round(sum(r["realized_R"] for r in realized_trades if r["realized_R"] is not None), 2)
    n_realized = len([r for r in realized_trades if r["realized_pnl_usd"] != 0.0])
    expectancy = round(pnl_split["realized_net_usd"] / n_realized, 2) if n_realized else 0.0
    # Max drawdown on the realised equity curve, in ledger (chronological) order.
    equity, peak, max_dd = 0.0, 0.0, 0.0
    for r in trades:
        equity += r["realized_pnl_usd"]
        peak = max(peak, equity)
        max_dd = max(max_dd, peak - equity)
    return {
        "period_label": period_label,
        "period": {"start": str(start), "end": str(end)},
        "symbols": symbols,
        "frozen_rules_file": FROZEN_PATH.name,
        "frozen_rules_sha256": sha256_file(FROZEN_PATH),
        "frozen_at": frozen.get("frozen_at"),
        "base_commit": frozen.get("base_commit"),
        "checkpoints_evaluated": total_checkpoints,
        "checkpoints_missing_data": missing,
        "sessions_evaluated": len(ledger),
        "setups_found": sum(1 for r in ledger if r["decision"] in ("BUY_LIMIT", "SELL_LIMIT", "SKIPPED")),
        "trades_filled": len(trades),
        "wins": wins,
        "losses": losses,
        "breakevens": bes,
        "open_at_end": opens,
        "win_rate": round(wins / (wins + losses), 4) if (wins + losses) else None,
        "realized_net_usd": pnl_split["realized_net_usd"],
        "realized_gross_profit_usd": pnl_split["realized_gross_profit_usd"],
        "realized_gross_loss_usd": pnl_split["realized_gross_loss_usd"],
        "realized_profit_factor": pnl_split["realized_profit_factor"],
        "unrealized_net_usd": pnl_split["unrealized_net_usd"],
        "realized_net_R": net_r,
        "expectancy_usd_per_realized_trade": expectancy,
        "max_drawdown_usd": round(max_dd, 2),
        "note": "Realised figures exclude OPEN_AT_END floating PnL (shown separately as "
                "unrealized_net_usd). Win rate is wins / (wins + losses); breakevens and "
                "open trades are excluded from it.",
    }


def write_outputs(ledger, summary, frozen, out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "trade_ledger.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LEDGER_FIELDS)
        w.writeheader()
        for row in ledger:
            w.writerow({k: row.get(k) for k in LEDGER_FIELDS})
    (out_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (out_dir / "frozen_rules_used.json").write_text(
        json.dumps(frozen, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    lines = [
        f"# TradingGuard {summary['period_label']} — {summary['period']['start']} to {summary['period']['end']}",
        "",
        f"Symbols: {', '.join(summary['symbols'])}",
        f"Frozen rules: {summary['frozen_rules_file']} (sha256 {summary['frozen_rules_sha256'][:16]}…, frozen {summary['frozen_at']})",
        f"Checkpoints evaluated: {summary['checkpoints_evaluated']} ({summary['checkpoints_missing_data']} missing data)",
        "",
        "## Headline (realised only — OPEN_AT_END floating PnL excluded)",
        "",
        f"- Trades filled: {summary['trades_filled']} ({summary['wins']}W / {summary['losses']}L / "
        f"{summary['breakevens']} BE / {summary['open_at_end']} open at end)",
        f"- Win rate: {summary['win_rate'] if summary['win_rate'] is not None else 'n/a'}",
        f"- Realised net: ${summary['realized_net_usd']:+.2f} ({summary['realized_net_R']:+.2f}R)",
        f"- Realised profit factor: {summary['realized_profit_factor']}",
        f"- Expectancy: ${summary['expectancy_usd_per_realized_trade']:+.2f} / realised trade",
        f"- Max drawdown: ${summary['max_drawdown_usd']:.2f}",
        f"- Unrealised (open trades, NOT in the net above): ${summary['unrealized_net_usd']:+.2f}",
        "",
        "Full trade-level ledger: trade_ledger.csv. Frozen rules actually used: frozen_rules_used.json.",
    ]
    (out_dir / "summary.md").write_text("\n".join(lines), encoding="utf-8")


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="TradingGuard true holdout test — frozen rules, trade-level ledger."
    )
    p.add_argument("--start", type=datetime.date.fromisoformat, default=DEFAULT_START,
                   help="Holdout start (default 2026-11-07).")
    p.add_argument("--end", type=datetime.date.fromisoformat, default=DEFAULT_END,
                   help="Holdout end (default 2026-12-31).")
    p.add_argument("--symbols", default=",".join(DEFAULT_SYMBOLS),
                   help="Comma-separated symbols (default XAUUSD,XAGUSD,EURUSD,GBPUSD).")
    p.add_argument("--data-dir", default=None,
                   help="Directory of M1 cache files (M1_<SYMBOL>_<YEAR>.parquet/.csv). "
                        "Default: live MT5.")
    p.add_argument("--out-dir", default=None,
                   help="Output directory (default backtest_results/holdout_<start>_<end>/).")
    p.add_argument("--allow-tuning-period", action="store_true",
                   help="Allow a period overlapping Jan–Nov 2026. Output is labelled "
                        "TUNING-PERIOD, never HOLDOUT.")
    p.add_argument("--freeze", action="store_true",
                   help="Regenerate the frozen rule file from the current tree and exit.")
    p.add_argument("--dry-run", action="store_true",
                   help="Validate config, frozen hashes and data source, then exit "
                        "without running the loop.")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)

    if args.freeze:
        path, digest = freeze_rules()
        print(f"FROZEN: {path}")
        print(f"sha256: {digest}")
        print("Commit this file with a note saying what changed and why. "
              "Re-freezing after seeing holdout results is tuning on the holdout.")
        return 0

    if args.start > args.end:
        print(f"ERROR: --start {args.start} is after --end {args.end}.", file=sys.stderr)
        return 2
    if overlaps_tuning(args.start, args.end) and not args.allow_tuning_period:
        print(
            f"ERROR: {args.start}..{args.end} overlaps the tuning period "
            f"{TUNING_START}..{TUNING_END} (the +17.0R bans were picked from that year).\n"
            "A holdout must be genuinely out-of-sample. If you really mean to re-run "
            "the tuning year, pass --allow-tuning-period — the output will be labelled "
            "TUNING-PERIOD, not HOLDOUT.",
            file=sys.stderr,
        )
        return 2

    try:
        frozen = load_frozen_rules()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    mismatches = verify_source_hashes(frozen)
    if mismatches:
        print("ERROR: rule-source files changed since the freeze — refusing to run:", file=sys.stderr)
        for m in mismatches:
            print(f"  - {m}", file=sys.stderr)
        print("Restore the frozen files, or re-freeze with --freeze (and record why).",
              file=sys.stderr)
        return 2

    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    if not symbols:
        print("ERROR: no symbols given.", file=sys.stderr)
        return 2

    try:
        source = FileBarSource(args.data_dir) if args.data_dir else MT5BarSource()
    except DataUnavailable as exc:
        print(f"ERROR: data source unavailable: {exc}", file=sys.stderr)
        return 3

    label = "tuning-period" if overlaps_tuning(args.start, args.end) else "holdout"
    out_dir = Path(args.out_dir) if args.out_dir else (
        BASE_DIR / "backtest_results" / f"{label}_{args.start}_{args.end}"
    )

    if args.dry_run:
        # Probe the data source for the first trading day; do not run the loop.
        days = trading_days(args.start, args.end)
        if not days:
            print(f"ERROR: no trading days in {args.start}..{args.end}.", file=sys.stderr)
            return 2
        probe_day = days[0]
        probe_dt = datetime.datetime(probe_day.year, probe_day.month, probe_day.day, 10, 0)
        try:
            bars = source.bars_5m(symbols[0], probe_dt, count=120)
        except DataUnavailable as exc:
            print(f"ERROR: data probe failed: {exc}", file=sys.stderr)
            return 3
        print(f"DRY RUN OK: {label} {args.start}..{args.end}, {len(days)} trading days, "
              f"{len(symbols)} symbols ({', '.join(symbols)}), "
              f"{len(CHECKPOINTS)} checkpoints/day.")
        print(f"Frozen rules: {FROZEN_PATH.name} (sha256 {sha256_file(FROZEN_PATH)[:16]}…), "
              "source hashes match.")
        print(f"Data probe: {len(bars)} 5M bars for {symbols[0]} at {probe_dt} "
              f"({'OK' if bars else 'EMPTY — the run would fail loudly on missing data'}).")
        print(f"Output would go to: {out_dir}")
        return 0

    print(f"Running {label} {args.start}..{args.end} on {', '.join(symbols)} "
          f"with frozen rules {FROZEN_PATH.name} …")
    try:
        summary = run_holdout(args.start, args.end, symbols, source, frozen, out_dir,
                              allow_tuning_period=args.allow_tuning_period)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 3

    print(f"Done. Output: {out_dir}")
    print(f"  {summary['period_label']}: {summary['trades_filled']} trades, "
          f"{summary['wins']}W/{summary['losses']}L/{summary['breakevens']}BE, "
          f"win rate {summary['win_rate']}, "
          f"realised ${summary['realized_net_usd']:+.2f} ({summary['realized_net_R']:+.2f}R), "
          f"PF {summary['realized_profit_factor']}, "
          f"unrealised ${summary['unrealized_net_usd']:+.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
