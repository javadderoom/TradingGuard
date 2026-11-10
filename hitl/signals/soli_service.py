"""
TradingGuard HITL - Soli-Trader Signal Ingestion & Dispatch Engine
Fetches, decodes, and standardizes weekly key levels and institutional signals from Soli-Trader.
Provides structured level validation, MT5 symbol translation, and Telegram alert formatting.
"""

import os
import sys
import json
import time
import logging
import urllib.request
import ssl
from pathlib import Path
from typing import Dict, List, Optional, Any

# Ensure workspace root is in sys.path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logger = logging.getLogger("SoliService")
if not logger.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] [SoliService] %(message)s"
    )

SIGNALS_DIR = BASE_DIR / "hitl" / "signals"
COOKIES_FILE = SIGNALS_DIR / "soli_cookies.json"
ACTIVE_SIGNALS_FILE = SIGNALS_DIR / "active_signals.json"

BASE_URL = "https://soli-trader.com"

# Broker MT5 symbol mapping
SYMBOL_MAP = {
    "XAUUSD": "XAUUSD_o",
    "XAGUSD": "XAGUSD_o",
    "EURUSD": "EURUSD_o",
    "USDCAD": "USDCAD_o",
    "AUDJPY": "AUDJPY_o",
    "GBPUSD": "GBPUSD_o",
    "USDJPY": "USDJPY_o",
    "BTCUSDT": "BTCUSD",
    "ETHUSDT": "ETHUSD",
    "DXY": "USDX",
}


def _unpack_sveltekit_node(data_array: List[Any]) -> Any:
    """Unpacks SvelteKit devalue serialized JSON node references."""
    if not isinstance(data_array, list) or not data_array:
        return data_array

    root = data_array[0]

    def _resolve(idx):
        if idx is None or not isinstance(idx, (int, float)):
            return idx
        if 0 <= idx < len(data_array):
            v = data_array[idx]
            if isinstance(v, dict):
                return {k: _resolve(val_idx) for k, val_idx in v.items()}
            elif isinstance(v, list):
                return [_resolve(item) for item in v]
            return v
        return idx

    if isinstance(root, dict):
        return {k: _resolve(v) for k, v in root.items()}
    elif isinstance(root, list):
        return [_resolve(v) for v in root]
    return root


class SoliTraderService:
    """Service for fetching, decoding, and managing Soli-Trader signals."""

    def __init__(self):
        self.ssl_ctx = ssl._create_unverified_context()

    def _get_cookie_header(self) -> Optional[str]:
        """Loads and formats the session cookie header."""
        if not COOKIES_FILE.exists():
            return None
        try:
            cookies = json.loads(COOKIES_FILE.read_text(encoding="utf-8"))
            return "; ".join([f"{c['name']}={c['value']}" for c in cookies if "name" in c and "value" in c])
        except Exception as e:
            logger.error(f"Error reading cookies file: {e}")
            return None

    def _fetch_url(self, url: str) -> Optional[str]:
        """Fetches URL using saved session cookies."""
        cookie_hdr = self._get_cookie_header()
        if not cookie_hdr:
            logger.warning("No session cookies available.")
            return None

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Cookie": cookie_hdr
        }

        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=12) as resp:
                if resp.status == 200:
                    return resp.read().decode("utf-8", errors="ignore")
        except Exception as e:
            logger.error(f"HTTP request failed for {url}: {e}")
            return None

    def download_chart_image(self, image_id: Any) -> Optional[bytes]:
        """Downloads official chart image bytes directly for Telegram dispatch."""
        if not image_id:
            return None
        cookie_hdr = self._get_cookie_header()
        url = f"{BASE_URL}/signals/img/{image_id}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Cookie": cookie_hdr or ""
        }
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, context=self.ssl_ctx, timeout=12) as resp:
                if resp.status == 200:
                    return resp.read()
        except Exception as e:
            logger.error(f"Failed to download image {image_id}: {e}")
            return None

    def get_chart_image_path(self, image_id: Any) -> Optional[str]:
        """Downloads and caches the official chart image to disk, returning its absolute path."""
        if not image_id:
            return None
        charts_dir = SIGNALS_DIR / "charts"
        charts_dir.mkdir(parents=True, exist_ok=True)
        img_path = charts_dir / f"soli_chart_{image_id}.png"
        if img_path.exists() and img_path.stat().st_size > 1000:
            return str(img_path)

        data = self.download_chart_image(image_id)
        if data:
            img_path.write_bytes(data)
            return str(img_path)
        return None

    def fetch_hub_data(self) -> Optional[Dict[str, Any]]:
        """Fetches the weekly signals hub data."""
        raw = self._fetch_url(f"{BASE_URL}/signals/__data.json")
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Failed to parse hub JSON: {e}")
            return None

    def fetch_entry_detail(self, entry_id: str) -> Optional[Dict[str, Any]]:
        """Fetches detailed levels and analysis for a specific signal entry."""
        raw = self._fetch_url(f"{BASE_URL}/signals/{entry_id}/__data.json")
        if not raw:
            return None
        try:
            payload = json.loads(raw)
            nodes = payload.get("nodes", [])
            if len(nodes) >= 3:
                data_list = nodes[2].get("data", [])
                unpacked = _unpack_sveltekit_node(data_list)
                return unpacked.get("entry")
            return None
        except Exception as e:
            logger.error(f"Failed to decode entry {entry_id}: {e}")
            return None

    def sync_all_signals(self) -> List[Dict[str, Any]]:
        """
        Synchronizes all active signals from Soli-Trader.
        Returns a list of standardized signal dictionaries.
        """
        hub_data = self.fetch_hub_data()
        if not hub_data:
            logger.warning("Could not fetch hub data. Cookie may be expired or network unreachable.")
            return []

        # Check authentication in hub response
        nodes = hub_data.get("nodes", [])
        if not nodes:
            return []

        # Find entries from nodes
        entries_list = []
        for n in nodes:
            if isinstance(n, dict) and "data" in n:
                data_list = n.get("data", [])
                unpacked = _unpack_sveltekit_node(data_list)
                if isinstance(unpacked, dict):
                    if "entries" in unpacked:
                        entries_list = unpacked.get("entries", [])
                        break
                    elif "set" in unpacked and isinstance(unpacked["set"], dict):
                        entries_list = unpacked["set"].get("entries", [])
                        break

        logger.info(f"Hub returned {len(entries_list)} active signal entries.")

        standardized_signals = []
        for summary in entries_list:
            entry_id = str(summary.get("entryId"))
            symbol = summary.get("symbol", "").upper()
            
            logger.info(f"Decoding details for {symbol} (Entry ID: {entry_id})...")
            detail = self.fetch_entry_detail(entry_id)
            if not detail:
                detail = summary

            raw_levels = detail.get("levels", [])
            clean_levels = []
            for lvl in raw_levels:
                if isinstance(lvl, dict):
                    clean_levels.append({
                        "kind": lvl.get("kind"),
                        "price": float(lvl.get("price", 0.0)),
                        "role": lvl.get("role"),               # support, resistance
                        "expectation": lvl.get("expectation"), # react, break
                        "timeframe": lvl.get("timeframe"),
                        "isNew": lvl.get("isNew", False)
                    })

            image_id = detail.get("imageId")
            image_url = f"{BASE_URL}/signals/img/{image_id}" if image_id else None

            broker_symbol = SYMBOL_MAP.get(symbol, symbol)

            sig = {
                "entryId": entry_id,
                "symbol": symbol,
                "brokerSymbol": broker_symbol,
                "category": detail.get("category"),
                "timeframe": detail.get("timeframe"),
                "caption": detail.get("caption"),
                "levels": clean_levels,
                "supports": [lvl["price"] for lvl in clean_levels if lvl.get("role") == "support"],
                "resistances": [lvl["price"] for lvl in clean_levels if lvl.get("role") == "resistance"],
                "imageId": image_id,
                "imageUrl": image_url,
                "detailUrl": f"{BASE_URL}/signals/{entry_id}",
                "version": detail.get("version", 1),
                "updatedAt": detail.get("updatedAt"),
                "extractedAt": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
            }
            standardized_signals.append(sig)

        # Save to active signals file
        ACTIVE_SIGNALS_FILE.write_text(
            json.dumps(standardized_signals, indent=2, ensure_ascii=False),
            encoding="utf-8"
        )
        logger.info(f"Successfully saved {len(standardized_signals)} structured signals to {ACTIVE_SIGNALS_FILE.name}")
        return standardized_signals

    def format_telegram_card(self, signal: Dict[str, Any]) -> str:
        """Formats an institutional telegram alert card for the signal."""
        sym = signal.get("symbol")
        broker_sym = signal.get("brokerSymbol")
        tf = signal.get("timeframe", "H4")
        category = signal.get("category", "").upper()
        caption = signal.get("caption", "").strip()
        
        supports = signal.get("supports", [])
        resistances = signal.get("resistances", [])

        lines = [
            f"📡 <b>SOLI-TRADER KEY LEVELS & SIGNAL</b>",
            f"━━━━━━━━━━━━━━━━━━━",
            f"<b>Asset:</b> <code>{sym}</code> ({category}) ➔ <i>{broker_sym}</i>",
            f"<b>Timeframe:</b> <code>{tf}</code> | <b>Version:</b> <code>v{signal.get('version', 1)}</code>",
            f"",
            f"🎯 <b>KEY INSTITUTIONAL LEVELS:</b>"
        ]

        if supports:
            supp_str = " | ".join([f"<code>{p}</code>" for p in sorted(supports)])
            lines.append(f"🟢 <b>Support / Demand:</b> {supp_str}")
        if resistances:
            res_str = " | ".join([f"<code>{p}</code>" for p in sorted(resistances)])
            lines.append(f"🔴 <b>Resistance / Supply:</b> {res_str}")

        if caption:
            # Shorten caption if very long
            lines.append(f"")
            lines.append(f"📝 <b>Analyst Thesis:</b>")
            lines.append(f"<i>{caption}</i>")

        lines.append(f"")
        lines.append(f"🔗 <a href='{signal.get('detailUrl')}'>View on Soli-Trader</a>")
        if signal.get("imageUrl"):
            lines.append(f"🖼️ <a href='{signal.get('imageUrl')}'>View Official Chart</a>")

        return "\n".join(lines)


if __name__ == "__main__":
    service = SoliTraderService()
    signals = service.sync_all_signals()
    print(f"\nSynced {len(signals)} signals cleanly:")
    for s in signals:
        print(f"\n--- {s['symbol']} ({s['category']}) ---")
        print(f"Supports: {s['supports']}")
        print(f"Resistances: {s['resistances']}")
        print(f"Levels count: {len(s['levels'])}")
        print(f"Chart: {s['imageUrl']}")
