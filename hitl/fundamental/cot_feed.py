"""
TradingGuard Fundamental Engine - Official CFTC Commitment of Traders (COT) Feed
Fetches weekly institutional positioning via CFTC Socrata APIs:
  - Traders in Financial Futures (TFF: gpe5-46if) -> Leveraged Funds (FX, Indices, BTC, UST10Y)
  - Disaggregated Futures (72hh-3qpy)             -> Managed Money (Gold, Silver, Copper, WTI)
24-hour disk cache with clean normalization to asset direction.
"""

import datetime
import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from hitl.config import ASSETS_DIR
from hitl.fundamental.http_utils import fetch_json, read_json_cache, write_json_atomic

logger = logging.getLogger(__name__)

COT_CACHE_FILE = ASSETS_DIR / "cot_cache.json"
COT_TTL_SEC = 24 * 3600

# Contract mapping: exact CFTC market_and_exchange_names -> (canonical_asset, invert_for_pair, note)
TFF_CONTRACTS: Dict[str, Tuple[str, bool, str]] = {
    "UST 10Y NOTE - CHICAGO BOARD OF TRADE": ("UST10Y", False, "10Y Treasury Note price futures (short=bearish bonds / higher yields)"),
    "EURO FX - CHICAGO MERCANTILE EXCHANGE": ("EURUSD", False, "CME Euro FX futures (Leveraged Funds)"),
    "BRITISH POUND - CHICAGO MERCANTILE EXCHANGE": ("GBPUSD", False, "CME British Pound futures (Leveraged Funds)"),
    "JAPANESE YEN - CHICAGO MERCANTILE EXCHANGE": ("USDJPY", True, "Inverted from CME Japanese Yen futures so positive=long USDJPY"),
    "NASDAQ-100 Consolidated - CHICAGO MERCANTILE EXCHANGE": ("NQ", False, "CME Nasdaq-100 Consolidated (Leveraged Funds)"),
    "E-MINI S&P 500 - CHICAGO MERCANTILE EXCHANGE": ("SPX", False, "CME E-Mini S&P 500 (Leveraged Funds)"),
    "BITCOIN - CHICAGO MERCANTILE EXCHANGE": ("BTCUSD", False, "CME Bitcoin futures (Leveraged Funds)"),
}

DISAGG_CONTRACTS: Dict[str, Tuple[str, bool, str]] = {
    "GOLD - COMMODITY EXCHANGE INC.": ("XAUUSD", False, "COMEX Gold futures (Managed Money)"),
    "SILVER - COMMODITY EXCHANGE INC.": ("XAGUSD", False, "COMEX Silver futures (Managed Money)"),
    "COPPER- #1 - COMMODITY EXCHANGE INC.": ("COPPER", False, "COMEX Copper #1 futures (Managed Money)"),
    "WTI-PHYSICAL - NEW YORK MERCANTILE EXCHANGE": ("USCRUDE", False, "NYMEX WTI Physical Crude (Managed Money)"),
}


def _to_int(val: Any) -> int:
    try:
        return int(float(val))
    except Exception:
        return 0


def parse_cftc_rows(
    tff_rows: Optional[List[Dict[str, Any]]],
    disagg_rows: Optional[List[Dict[str, Any]]],
) -> Dict[str, Any]:
    """
    Pure parser transforming raw CFTC TFF & Disaggregated JSON rows into normalized
    per-asset COT positioning records. Sorted newest-first; computes WoW deltas cleanly.
    """
    assets_out: Dict[str, Any] = {}
    latest_report_date = None

    def _process(rows: Optional[List[Dict[str, Any]]], mapping: Dict[str, Tuple[str, bool, str]], long_k: str, short_k: str, chg_l_k: str, chg_s_k: str, participant_label: str):
        nonlocal latest_report_date
        if not rows:
            return
        grouped: Dict[str, List[Dict[str, Any]]] = {}
        for r in rows:
            mname = r.get("market_and_exchange_names", "")
            if mname in mapping:
                grouped.setdefault(mname, []).append(r)

        for mname, items in grouped.items():
            items.sort(key=lambda x: str(x.get("report_date_as_yyyy_mm_dd", "")), reverse=True)
            cur = items[0]
            prev = items[1] if len(items) > 1 else None

            canon, invert, note = mapping[mname]
            raw_long = _to_int(cur.get(long_k))
            raw_short = _to_int(cur.get(short_k))

            # Adjust direction if contract quotes base/quote inversely (e.g. JPY futures vs USDJPY)
            long_pos = raw_short if invert else raw_long
            short_pos = raw_long if invert else raw_short
            net = long_pos - short_pos

            # Compute WoW change: prefer exact previous report date comparison, fallback to CFTC change fields
            if prev is not None:
                p_raw_long = _to_int(prev.get(long_k))
                p_raw_short = _to_int(prev.get(short_k))
                p_net = (p_raw_short - p_raw_long) if invert else (p_raw_long - p_raw_short)
                net_chg = net - p_net
            else:
                chg_l = _to_int(cur.get(chg_l_k))
                chg_s = _to_int(cur.get(chg_s_k))
                net_chg = (chg_s - chg_l) if invert else (chg_l - chg_s)

            gross = long_pos + short_pos
            long_pct = round((long_pos / gross) * 100.0, 1) if gross > 0 else 50.0
            if long_pct >= 75.0:
                crowding = "EXTREME_LONG"
            elif long_pct <= 25.0:
                crowding = "EXTREME_SHORT"
            else:
                crowding = "BALANCED"

            rep_dt = str(cur.get("report_date_as_yyyy_mm_dd", ""))[:10]
            if rep_dt and (latest_report_date is None or rep_dt > latest_report_date):
                latest_report_date = rep_dt

            assets_out[canon] = {
                "symbol": canon,
                "report_date": rep_dt,
                "participant": participant_label,
                "long_contracts": long_pos,
                "short_contracts": short_pos,
                "net_contracts": net,
                "net_change_wow": net_chg,
                "long_pct": long_pct,
                "crowding_flag": crowding,
                "note": note,
            }

    _process(
        tff_rows,
        TFF_CONTRACTS,
        long_k="lev_money_positions_long",
        short_k="lev_money_positions_short",
        chg_l_k="change_in_lev_money_long",
        chg_s_k="change_in_lev_money_short",
        participant_label="Leveraged Funds",
    )
    _process(
        disagg_rows,
        DISAGG_CONTRACTS,
        long_k="m_money_positions_long_all",
        short_k="m_money_positions_short_all",
        chg_l_k="change_in_m_money_long_all",
        chg_s_k="change_in_m_money_short_all",
        participant_label="Managed Money",
    )

    return {
        "status": "OK" if assets_out else "UNAVAILABLE",
        "latest_report_date": latest_report_date,
        "fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "assets": assets_out,
    }


def fetch_cot_positioning(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetches CFTC TFF & Disaggregated positioning (24h disk cache)."""
    if not force_refresh:
        cached, fresh = read_json_cache(COT_CACHE_FILE, COT_TTL_SEC)
        if cached and fresh:
            return cached

    where_tff = "market_and_exchange_names in (" + ",".join(f"'{n}'" for n in TFF_CONTRACTS) + ")"
    url_tff = (
        f"https://publicreporting.cftc.gov/resource/gpe5-46if.json"
        f"?$where={urllib.parse.quote(where_tff)}&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=35"
    )

    where_dis = "market_and_exchange_names in (" + ",".join(f"'{n}'" for n in DISAGG_CONTRACTS) + ")"
    url_dis = (
        f"https://publicreporting.cftc.gov/resource/72hh-3qpy.json"
        f"?$where={urllib.parse.quote(where_dis)}&$order=report_date_as_yyyy_mm_dd%20DESC&$limit=25"
    )

    tff_rows = fetch_json(url_tff, timeout=10, prefer_proxy=True)
    dis_rows = fetch_json(url_dis, timeout=10, prefer_proxy=True)

    if not tff_rows and not dis_rows:
        stale, _ = read_json_cache(COT_CACHE_FILE, COT_TTL_SEC)
        return stale or {"status": "UNAVAILABLE", "latest_report_date": None, "assets": {}}

    parsed = parse_cftc_rows(
        tff_rows if isinstance(tff_rows, list) else [],
        dis_rows if isinstance(dis_rows, list) else [],
    )
    if parsed.get("assets"):
        write_json_atomic(COT_CACHE_FILE, parsed)
    return parsed
