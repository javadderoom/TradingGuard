"""
TradingGuard Fundamental Engine - Layer 1 Quantitative Macro Tape
Pulls live sovereign nominal & TIPS real yield curves (US Treasury official CSVs),
intraday bond/credit/Asia/commodity stress tickers (Yahoo Finance), and live MT5
cross-asset telemetry, then computes universal cross-asset regime diagnostics.
"""

import concurrent.futures
import csv
import datetime
import io
import logging
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

from hitl.config import ASSETS_DIR
from hitl.fundamental.http_utils import fetch_json, fetch_text, read_json_cache, write_json_atomic

logger = logging.getLogger(__name__)

TREASURY_CACHE_FILE = ASSETS_DIR / "treasury_curves_cache.json"
TREASURY_TTL_SEC = 4 * 3600  # 4 hours

YAHOO_CACHE_FILE = ASSETS_DIR / "yahoo_macro_cache.json"
YAHOO_TTL_SEC = 15 * 60  # 15 minutes

# Yahoo Finance macro & cross-asset universe
YAHOO_TICKERS: Dict[str, str] = {
    "US10Y_YF": "^TNX",
    "US30Y_YF": "^TYX",
    "US05Y_YF": "^FVX",
    "US03M_YF": "^IRX",
    "TLT": "TLT",          # 20+ Year US Treasury ETF
    "SHY": "SHY",          # 1-3 Year US Treasury ETF
    "TIP": "TIP",          # TIPS Bond ETF
    "HYG": "HYG",          # High Yield Corporate Bond ETF (credit stress)
    "CSI300": "000300.SS", # Mainland China Equities
    "HSI_YF": "^HSI",      # Hang Seng Index
    "USDCNH": "CNH=X",     # Offshore Chinese Yuan per USD (higher = CNH depreciation)
    "COPPER": "HG=F",      # COMEX Copper Futures (global growth barometer)
    "VIX_YF": "^VIX",      # Equity Volatility Index
    "DXY_YF": "DX-Y.NYB",  # ICE US Dollar Index
    "WTI_YF": "CL=F",      # WTI Crude Oil
    "GOLD_YF": "GC=F",     # COMEX Gold
    "BTC_YF": "BTC-USD",   # Bitcoin Spot
}

# Tickers representing yield levels rather than prices
YIELD_INDICES = {"US10Y_YF", "US30Y_YF", "US05Y_YF", "US03M_YF"}

MT5_CROSS_ASSETS: Dict[str, List[str]] = {
    "USDX": ["USDX"],
    "EURLFX": ["EURLFX"],
    "GBPLFX": ["GBPLFX"],
    "LFXJPY": ["LFXJPY"],
    "CHFLFX": ["CHFLFX"],
    "AUDLFX": ["AUDLFX"],
    "CADLFX": ["CADLFX"],
    "VIX": ["VIX"],
    "SPX": ["SPX", "US500", "SP500"],
    "NQ": ["NQ_o", "NQ", "USTEC", "US100"],
    "FDAX": ["FDAX", "DE40", "DAX"],
    "HK50": ["HK50", "HSI"],
    "NI225": ["NI225", "JP225"],
    "UKBRENT": ["UKBRENT", "BRENT"],
    "USCRUDE": ["USCRUDE", "WTI", "USOIL"],
    "XAUUSD": ["XAUUSD_o", "XAUUSD", "GOLD"],
    "XAGUSD": ["XAGUSD_o", "XAGUSD", "SILVER"],
    "BTCUSD": ["BTCUSD", "BTCUSD_o"],
    "ETHUSD": ["ETHUSD", "ETHUSD_o"],
    "USDJPY": ["USDJPY_o", "USDJPY"],
    "USDCHF": ["USDCHF_o", "USDCHF"],
    "EURUSD": ["EURUSD_o", "EURUSD"],
    "GBPUSD": ["GBPUSD_o", "GBPUSD"],
}


def _safe_float(val: Any) -> Optional[float]:
    if val is None:
        return None
    try:
        s = str(val).strip()
        if not s or s.upper() in ("N/A", "NAN", "NONE", "-"):
            return None
        return float(s)
    except Exception:
        return None


def _parse_treasury_csv(csv_text: str) -> List[Dict[str, Any]]:
    """
    Parses US Treasury CSV (which arrives newest-first) and returns rows sorted ASCENDING by Date.
    """
    if not csv_text or "Date" not in csv_text:
        return []
    rows = []
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    for row in reader:
        date_str = (row.get("Date") or "").strip()
        if not date_str:
            continue
        try:
            dt = datetime.datetime.strptime(date_str, "%m/%d/%Y").date()
        except ValueError:
            try:
                dt = datetime.date.fromisoformat(date_str[:10])
            except ValueError:
                continue
        cleaned = {"_date": dt.isoformat()}
        for k, v in row.items():
            if k and k != "Date":
                fv = _safe_float(v)
                if fv is not None:
                    cleaned[k.strip()] = fv
        rows.append(cleaned)
    rows.sort(key=lambda r: r["_date"])
    return rows


def _extract_curve_metric(rows: List[Dict[str, Any]], col: str) -> Dict[str, Any]:
    """Computes latest yield level + 1D/5D/20D deltas in basis points from ascending rows."""
    series = [(r["_date"], r[col]) for r in rows if col in r]
    if not series:
        return {}
    latest_dt, latest = series[-1]
    d1 = series[-2][1] if len(series) >= 2 else latest
    d5 = series[-6][1] if len(series) >= 6 else series[0][1]
    d20 = series[-21][1] if len(series) >= 21 else series[0][1]
    return {
        "date": latest_dt,
        "latest": round(latest, 2),
        "chg_1d_bps": round((latest - d1) * 100.0, 1),
        "chg_5d_bps": round((latest - d5) * 100.0, 1),
        "chg_20d_bps": round((latest - d20) * 100.0, 1),
    }


def fetch_treasury_curves(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Fetches official US Treasury nominal & TIPS real yield curves (4h cached).
    Returns levels, bps changes, 2s10s/3m10s slopes, and 10Y breakeven inflation.
    """
    if not force_refresh:
        cached, fresh = read_json_cache(TREASURY_CACHE_FILE, TREASURY_TTL_SEC)
        if cached and fresh:
            return cached

    year = datetime.date.today().year
    years_to_try = [year, year - 1]
    nom_rows: List[Dict[str, Any]] = []
    real_rows: List[Dict[str, Any]] = []

    for y in years_to_try:
        if len(nom_rows) < 25:
            nom_url = (
                f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv"
            )
            txt = fetch_text(nom_url, timeout=10)
            parsed = _parse_treasury_csv(txt or "")
            if parsed:
                # Merge without duplicates so early-January rolls preserve 20D lookback
                existing = {r["_date"]: r for r in parsed}
                for r in nom_rows:
                    existing[r["_date"]] = r
                nom_rows = sorted(existing.values(), key=lambda x: x["_date"])

        if len(real_rows) < 25:
            real_url = (
                f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/"
                f"daily-treasury-rates.csv/{y}/all?type=daily_treasury_real_yield_curve&field_tdr_date_value={y}&page&_format=csv"
            )
            txt_r = fetch_text(real_url, timeout=10)
            parsed_r = _parse_treasury_csv(txt_r or "")
            if parsed_r:
                existing_r = {r["_date"]: r for r in parsed_r}
                for r in real_rows:
                    existing_r[r["_date"]] = r
                real_rows = sorted(existing_r.values(), key=lambda x: x["_date"])

    if not nom_rows and not real_rows:
        stale, _ = read_json_cache(TREASURY_CACHE_FILE, TREASURY_TTL_SEC)
        return stale or {"status": "UNAVAILABLE"}

    nom_3m = _extract_curve_metric(nom_rows, "3 Mo")
    nom_2y = _extract_curve_metric(nom_rows, "2 Yr")
    nom_5y = _extract_curve_metric(nom_rows, "5 Yr")
    nom_10y = _extract_curve_metric(nom_rows, "10 Yr")
    nom_30y = _extract_curve_metric(nom_rows, "30 Yr")

    real_5y = _extract_curve_metric(real_rows, "5 YR")
    real_10y = _extract_curve_metric(real_rows, "10 YR")
    real_30y = _extract_curve_metric(real_rows, "30 YR")

    # Compute 10Y Breakeven Inflation = Nominal 10Y - Real 10Y aligned by date
    real_by_dt = {r["_date"]: r for r in real_rows}
    breakeven_rows = []
    for nr in nom_rows:
        dt = nr["_date"]
        rr = real_by_dt.get(dt)
        if rr and "10 Yr" in nr and "10 YR" in rr:
            breakeven_rows.append({"_date": dt, "BE10": nr["10 Yr"] - rr["10 YR"]})
    breakeven_10y = _extract_curve_metric(breakeven_rows, "BE10")

    # Compute slopes
    slope_2s10s_rows = [
        {"_date": r["_date"], "S2S10": r["10 Yr"] - r["2 Yr"]}
        for r in nom_rows if "10 Yr" in r and "2 Yr" in r
    ]
    slope_3m10s_rows = [
        {"_date": r["_date"], "S3M10": r["10 Yr"] - r["3 Mo"]}
        for r in nom_rows if "10 Yr" in r and "3 Mo" in r
    ]

    result = {
        "status": "OK",
        "as_of_date": nom_rows[-1]["_date"] if nom_rows else (real_rows[-1]["_date"] if real_rows else None),
        "nom_3m": nom_3m,
        "nom_2y": nom_2y,
        "nom_5y": nom_5y,
        "nom_10y": nom_10y,
        "nom_30y": nom_30y,
        "real_5y": real_5y,
        "real_10y": real_10y,
        "real_30y": real_30y,
        "breakeven_10y": breakeven_10y,
        "slope_2s10s": _extract_curve_metric(slope_2s10s_rows, "S2S10"),
        "slope_3m10s": _extract_curve_metric(slope_3m10s_rows, "S3M10"),
    }
    write_json_atomic(TREASURY_CACHE_FILE, result)
    return result


def _fetch_single_yahoo_ticker(item: Tuple[str, str]) -> Tuple[str, Optional[Dict[str, Any]]]:
    key, ticker = item
    encoded = urllib.parse.quote(ticker, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=2mo&interval=1d"
    payload = fetch_json(url, timeout=8)
    try:
        res_list = (payload or {}).get("chart", {}).get("result") or []
        if not res_list:
            return key, None
        res = res_list[0]
        meta = res.get("meta", {})
        closes_raw = (res.get("indicators", {}).get("quote") or [{}])[0].get("close") or []
        closes = [float(c) for c in closes_raw if c is not None]
        if len(closes) < 2:
            return key, None

        reg_price = _safe_float(meta.get("regularMarketPrice"))
        latest = reg_price if reg_price is not None else closes[-1]
        d1 = closes[-2]
        d5 = closes[-6] if len(closes) >= 6 else closes[0]
        d20 = closes[-21] if len(closes) >= 21 else closes[0]

        entry: Dict[str, Any] = {
            "ticker": ticker,
            "latest": round(latest, 4),
            "chg_1d_pct": round(((latest - d1) / d1) * 100.0, 2) if d1 else 0.0,
            "chg_5d_pct": round(((latest - d5) / d5) * 100.0, 2) if d5 else 0.0,
            "chg_20d_pct": round(((latest - d20) / d20) * 100.0, 2) if d20 else 0.0,
        }
        if key in YIELD_INDICES:
            # Yahoo ^TNX/^TYX/^FVX/^IRX are quoted in percentage points (e.g. 4.92 = 4.92%)
            entry["chg_1d_bps"] = round((latest - d1) * 100.0, 1)
            entry["chg_5d_bps"] = round((latest - d5) * 100.0, 1)
            entry["chg_20d_bps"] = round((latest - d20) * 100.0, 1)
        return key, entry
    except Exception as e:
        logger.debug(f"[MarketTape] Yahoo parse error for {key} ({ticker}): {e}")
        return key, None


def fetch_yahoo_macro_tape(force_refresh: bool = False) -> Dict[str, Any]:
    """Fetches intraday yields, credit, China/Asia, Copper, VIX, and Dollar via Yahoo Finance."""
    if not force_refresh:
        cached, fresh = read_json_cache(YAHOO_CACHE_FILE, YAHOO_TTL_SEC)
        if cached and fresh:
            return cached

    tickers_out: Dict[str, Any] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        for k, val in ex.map(_fetch_single_yahoo_ticker, YAHOO_TICKERS.items()):
            if val:
                tickers_out[k] = val

    if not tickers_out:
        stale, _ = read_json_cache(YAHOO_CACHE_FILE, YAHOO_TTL_SEC)
        return stale or {}

    result = {
        "fetched_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "tickers": tickers_out,
    }
    write_json_atomic(YAHOO_CACHE_FILE, result)
    return result


def fetch_mt5_cross_asset_tape() -> Dict[str, Any]:
    """Pulls live D1 % changes directly from the connected MT5 broker terminal."""
    try:
        import MetaTrader5 as mt5
        from hitl.mt5_engine import MT5Engine

        engine = MT5Engine()
        if not engine.ensure_connected():
            return {}

        out: Dict[str, Any] = {}
        for canon, candidates in MT5_CROSS_ASSETS.items():
            resolved = None
            for cand in candidates:
                r = engine.resolve_symbol(cand)
                if r:
                    resolved = r
                    break
            if not resolved:
                continue

            rates = mt5.copy_rates_from_pos(resolved, mt5.TIMEFRAME_D1, 0, 25)
            if rates is None or len(rates) < 2:
                continue
            closes = [float(x["close"]) for x in rates]
            latest = closes[-1]
            tk = mt5.symbol_info_tick(resolved)
            if tk and tk.bid > 0:
                latest = float(tk.bid)

            d1 = closes[-2]
            d5 = closes[-6] if len(closes) >= 6 else closes[0]
            d20 = closes[-21] if len(closes) >= 21 else closes[0]

            out[canon] = {
                "broker_symbol": resolved,
                "latest": round(latest, 5 if ("EUR" in canon or "GBP" in canon or "LFX" in canon) else 2),
                "chg_1d_pct": round(((latest - d1) / d1) * 100.0, 2) if d1 else 0.0,
                "chg_5d_pct": round(((latest - d5) / d5) * 100.0, 2) if d5 else 0.0,
                "chg_20d_pct": round(((latest - d20) / d20) * 100.0, 2) if d20 else 0.0,
            }
        return out
    except Exception as e:
        logger.debug(f"[MarketTape] MT5 cross-asset tape skipped: {e}")
        return {}


def compute_cross_asset_diagnostics(
    treasury: Dict[str, Any],
    yahoo: Dict[str, Any],
    mt5_tape: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Computes universal, non-hardcoded cross-asset regime indicators from live numbers.
    Captures real-yield vs inflation decomposition, simultaneous bond-equity liquidation,
    credit stress, Asia/China currency-equity stress, energy shocks, and FX dispersion.
    """
    yf = yahoo.get("tickers", {}) if isinstance(yahoo, dict) else {}

    def _chg5(mt5_key: Optional[str], yf_key: Optional[str]) -> Optional[float]:
        if mt5_key and mt5_key in mt5_tape:
            return mt5_tape[mt5_key]["chg_5d_pct"]
        if yf_key and yf_key in yf:
            return yf[yf_key]["chg_5d_pct"]
        return None

    def _latest(mt5_key: Optional[str], yf_key: Optional[str]) -> Optional[float]:
        if mt5_key and mt5_key in mt5_tape:
            return mt5_tape[mt5_key]["latest"]
        if yf_key and yf_key in yf:
            return yf[yf_key]["latest"]
        return None

    # 1. Sovereign Yields & Real Rates (official Treasury combined with intraday Yahoo 10Y)
    nom_10y_level = treasury.get("nom_10y", {}).get("latest")
    nom_10y_5d_bps = treasury.get("nom_10y", {}).get("chg_5d_bps")
    intraday_10y = yf.get("US10Y_YF", {})
    if intraday_10y:
        nom_10y_level = intraday_10y.get("latest", nom_10y_level)
        if nom_10y_5d_bps is None:
            nom_10y_5d_bps = intraday_10y.get("chg_5d_bps")

    real_10y_level = treasury.get("real_10y", {}).get("latest")
    real_10y_5d_bps = treasury.get("real_10y", {}).get("chg_5d_bps")
    breakeven_10y_level = treasury.get("breakeven_10y", {}).get("latest")
    breakeven_5d_bps = treasury.get("breakeven_10y", {}).get("chg_5d_bps")
    slope_2s10s = treasury.get("slope_2s10s", {}).get("latest")

    # Classify rate impulse driver (Real Rate Tightening vs Inflation Repricing vs Flight to Safety)
    rate_driver = "BALANCED"
    if real_10y_5d_bps is not None:
        be_move = breakeven_5d_bps or 0.0
        if real_10y_5d_bps >= 8.0 and real_10y_5d_bps > be_move:
            rate_driver = "REAL_YIELD_TIGHTENING"
        elif real_10y_5d_bps <= -8.0 and (nom_10y_5d_bps or 0.0) <= -5.0:
            rate_driver = "REAL_YIELD_EASING"
        elif be_move >= 8.0:
            rate_driver = "INFLATION_BREAKEVEN_SURGE"

    # 2. Equities vs Bonds -> Bond-Equity Co-Selloff (Liquidity / Reserve Selling Signature)
    spx_5d = _chg5("SPX", None)
    nq_5d = _chg5("NQ", None)
    tlt_5d = yf.get("TLT", {}).get("chg_5d_pct")
    eq_5d = spx_5d if spx_5d is not None else nq_5d

    bond_equity_co_selloff = False
    if eq_5d is not None and eq_5d <= -1.0:
        if (tlt_5d is not None and tlt_5d <= -0.8) or (nom_10y_5d_bps is not None and nom_10y_5d_bps >= 8.0):
            bond_equity_co_selloff = True

    # 3. Credit Stress (HYG vs SHY 5D spread)
    hyg_5d = yf.get("HYG", {}).get("chg_5d_pct")
    shy_5d = yf.get("SHY", {}).get("chg_5d_pct")
    credit_stress_5d = round(hyg_5d - (shy_5d or 0.0), 2) if hyg_5d is not None else None

    # 4. Asia / China Liquidity & CNH Stress
    csi_5d = yf.get("CSI300", {}).get("chg_5d_pct")
    hk50_5d = _chg5("HK50", "HSI_YF")
    cnh_5d = yf.get("USDCNH", {}).get("chg_5d_pct")  # >0 = USD strengthens / CNH weakens
    china_eq = csi_5d if csi_5d is not None else hk50_5d
    asia_china_stress = False
    if (china_eq is not None and china_eq <= -2.0) or (
        china_eq is not None and china_eq <= -1.0 and cnh_5d is not None and cnh_5d >= 0.35
    ):
        asia_china_stress = True

    # 5. Energy & Industrial Metals
    oil_5d = _chg5("USCRUDE", "WTI_YF") or _chg5("UKBRENT", None)
    oil_20d = (
        mt5_tape.get("USCRUDE", {}).get("chg_20d_pct")
        or yf.get("WTI_YF", {}).get("chg_20d_pct")
        or mt5_tape.get("UKBRENT", {}).get("chg_20d_pct")
    )
    copper_5d = yf.get("COPPER", {}).get("chg_5d_pct")
    gold_5d = _chg5("XAUUSD", "GOLD_YF")
    copper_gold_5d_diff = (
        round(copper_5d - gold_5d, 2) if (copper_5d is not None and gold_5d is not None) else None
    )

    # 6. Dollar & Volatility
    dxy_level = _latest("USDX", "DXY_YF")
    dxy_1d = mt5_tape.get("USDX", {}).get("chg_1d_pct") or yf.get("DXY_YF", {}).get("chg_1d_pct")
    dxy_5d = _chg5("USDX", "DXY_YF")
    dxy_20d = mt5_tape.get("USDX", {}).get("chg_20d_pct") or yf.get("DXY_YF", {}).get("chg_20d_pct")
    vix_level = _latest("VIX", "VIX_YF")
    vix_5d = _chg5("VIX", "VIX_YF")

    # 7. G7 Sovereign Currency Strength Ranking (5D% via LFX indexes)
    fx_map = {
        "USD": _chg5("USDX", "DXY_YF"),
        "EUR": _chg5("EURLFX", None),
        "GBP": _chg5("GBPLFX", None),
        "JPY": _chg5("LFXJPY", None),
        "CHF": _chg5("CHFLFX", None),
        "AUD": _chg5("AUDLFX", None),
        "CAD": _chg5("CADLFX", None),
    }
    fx_ranked = sorted(
        [(ccy, round(val, 2)) for ccy, val in fx_map.items() if val is not None],
        key=lambda x: x[1],
        reverse=True,
    )

    return {
        "nom_10y_level": nom_10y_level,
        "nom_10y_5d_bps": nom_10y_5d_bps,
        "real_10y_level": real_10y_level,
        "real_10y_5d_bps": real_10y_5d_bps,
        "breakeven_10y_level": breakeven_10y_level,
        "breakeven_5d_bps": breakeven_5d_bps,
        "slope_2s10s": slope_2s10s,
        "rate_impulse_driver": rate_driver,
        "bond_equity_co_selloff": bond_equity_co_selloff,
        "tlt_5d_pct": tlt_5d,
        "spx_5d_pct": spx_5d,
        "nq_5d_pct": nq_5d,
        "credit_stress_5d_pct": credit_stress_5d,
        "asia_china_stress": asia_china_stress,
        "csi300_5d_pct": csi_5d,
        "hk50_5d_pct": hk50_5d,
        "usdcnh_5d_pct": cnh_5d,
        "oil_5d_pct": oil_5d,
        "oil_20d_pct": oil_20d,
        "copper_5d_pct": copper_5d,
        "gold_5d_pct": gold_5d,
        "copper_gold_5d_diff": copper_gold_5d_diff,
        "dxy_level": dxy_level,
        "dxy_1d_pct": dxy_1d,
        "dxy_5d_pct": dxy_5d,
        "dxy_20d_pct": dxy_20d,
        "vix_level": vix_level,
        "vix_5d_pct": vix_5d,
        "fx_strength_ranking_5d": fx_ranked,
    }


def collect_full_market_tape(force_refresh: bool = False) -> Dict[str, Any]:
    """Orchestrates parallel collection of Treasury curves, Yahoo tape, and MT5 cross-assets."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        f_ust = ex.submit(fetch_treasury_curves, force_refresh)
        f_yf = ex.submit(fetch_yahoo_macro_tape, force_refresh)
        f_mt5 = ex.submit(fetch_mt5_cross_asset_tape)
        treasury = f_ust.result()
        yahoo = f_yf.result()
        mt5_tape = f_mt5.result()

    diagnostics = compute_cross_asset_diagnostics(treasury, yahoo, mt5_tape)
    return {
        "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "treasury_curves": treasury,
        "yahoo_tape": yahoo.get("tickers", {}) if isinstance(yahoo, dict) else {},
        "mt5_tape": mt5_tape,
        "diagnostics": diagnostics,
    }
