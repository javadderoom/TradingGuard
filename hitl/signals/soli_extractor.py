"""
TradingGuard HITL - Soli-Trader Automated Signal Extractor
Uses native Google Chrome with a persistent user data profile and Chrome DevTools Protocol (CDP).
Eliminates brittle web scraping by executing directly within the authentic browser session.
"""

import os
import sys
import json
import time
import asyncio
import logging
import urllib.request
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

import websockets

# Setup root path
BASE_DIR = Path(__file__).resolve().parent.parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SoliExtractor] %(message)s"
)
logger = logging.getLogger("SoliExtractor")

SIGNALS_DIR = BASE_DIR / "hitl" / "signals"
PROFILE_DIR = SIGNALS_DIR / "soli_chrome_profile"
COOKIES_FILE = SIGNALS_DIR / "soli_cookies.json"
SIGNALS_FILE = SIGNALS_DIR / "extracted_signals.json"

CDP_PORT = 9222
CDP_BASE_URL = f"http://127.0.0.1:{CDP_PORT}"
TARGET_URL = "https://soli-trader.com/signals"

CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
]


def find_browser_executable() -> str:
    """Finds installed Chrome or Edge executable."""
    for p in CHROME_PATHS:
        if os.path.exists(p):
            return p
    raise FileNotFoundError("Neither Google Chrome nor Microsoft Edge could be found on standard paths.")


def is_cdp_available() -> bool:
    """Checks if Chrome CDP endpoint is already responding."""
    try:
        req = urllib.request.Request(f"{CDP_BASE_URL}/json/version", headers={"User-Agent": "TradingGuard"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def launch_chrome(headless: bool = False) -> subprocess.Popen:
    """Launches Chrome with remote debugging port and persistent profile."""
    if is_cdp_available():
        logger.info(f"CDP is already active on port {CDP_PORT}.")
        return None

    exe = find_browser_executable()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    args = [
        exe,
        f"--remote-debugging-port={CDP_PORT}",
        f"--user-data-dir={PROFILE_DIR}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
        TARGET_URL
    ]
    if headless:
        args.append("--headless=new")

    logger.info(f"Launching browser: {exe}")
    logger.info(f"Profile directory: {PROFILE_DIR}")
    proc = subprocess.Popen(args)
    
    # Wait for CDP to become ready
    for _ in range(15):
        time.sleep(1)
        if is_cdp_available():
            logger.info("Browser CDP endpoint connected successfully.")
            return proc

    raise TimeoutError("Browser launched but CDP port 9222 failed to respond within 15 seconds.")


def get_tabs() -> List[Dict[str, Any]]:
    """Gets list of active browser tabs from CDP."""
    req = urllib.request.Request(f"{CDP_BASE_URL}/json", headers={"User-Agent": "TradingGuard"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


def get_or_create_signals_tab() -> Dict[str, Any]:
    """Finds existing soli-trader tab or opens a new one."""
    tabs = get_tabs()
    for tab in tabs:
        if tab.get("type") == "page" and "soli-trader.com" in tab.get("url", ""):
            return tab
    
    # Open new tab
    encoded_url = urllib.parse.quote(TARGET_URL, safe="")
    req = urllib.request.Request(f"{CDP_BASE_URL}/json/new?{encoded_url}", method="PUT")
    with urllib.request.urlopen(req, timeout=5) as resp:
        return json.loads(resp.read().decode("utf-8"))


class SoliTraderExtractor:
    """Automated signal extraction client via native Chrome DevTools Protocol."""

    def __init__(self, cdp_port: int = CDP_PORT):
        self.cdp_port = cdp_port
        self.msg_id = 0

    async def _send_cdp(self, ws, method: str, params: Optional[Dict] = None) -> Any:
        """Sends a JSON-RPC message over CDP WebSocket and waits for the matching reply."""
        self.msg_id += 1
        call_id = self.msg_id
        payload = {"id": call_id, "method": method, "params": params or {}}
        await ws.send(json.dumps(payload))
        
        while True:
            raw = await ws.recv()
            data = json.loads(raw)
            if data.get("id") == call_id:
                if "error" in data:
                    raise RuntimeError(f"CDP Error in {method}: {data['error']}")
                return data.get("result", {})

    async def evaluate_js(self, ws, expression: str) -> Any:
        """Evaluates an asynchronous JavaScript expression in the tab."""
        res = await self._send_cdp(ws, "Runtime.evaluate", {
            "expression": expression,
            "awaitPromise": True,
            "returnByValue": True
        })
        val = res.get("result", {}).get("value")
        return val

    async def get_session_cookies(self, ws) -> List[Dict[str, Any]]:
        """Extracts cookies for soli-trader.com from browser session."""
        res = await self._send_cdp(ws, "Network.getCookies", {
            "urls": ["https://soli-trader.com"]
        })
        cookies = res.get("cookies", [])
        COOKIES_FILE.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
        logger.info(f"Extracted {len(cookies)} session cookies to {COOKIES_FILE.name}")
        return cookies

    async def check_auth_status(self, ws) -> Dict[str, Any]:
        """Checks whether the browser session is authenticated on Soli-Trader."""
        js_code = """
        (async () => {
            try {
                const res = await fetch('/signals/__data.json');
                if (!res.ok) return { ok: false, status: res.status };
                const text = await res.text();
                const isTeaser = text.includes('"teaser"') && text.includes('"loginHref"');
                const hasEntries = text.includes('"entries"') || text.includes('"assets"');
                return {
                    ok: true,
                    status: res.status,
                    isLoggedIn: !isTeaser && hasEntries,
                    rawPreview: text.slice(0, 500)
                };
            } catch (err) {
                return { ok: false, error: err.toString() };
            }
        })()
        """
        return await self.evaluate_js(ws, js_code)

    async def extract_signals_data(self, ws) -> Dict[str, Any]:
        """
        Extracts structured signals from the authenticated page.
        Combines SvelteKit __data.json with DOM elements for 100% fidelity.
        """
        js_code = """
        (async () => {
            try {
                // 1. Fetch main signals JSON
                const res = await fetch('/signals/__data.json');
                const rawJsonText = await res.text();
                
                // 2. Extract DOM cards for visual metadata
                const cards = Array.from(document.querySelectorAll('a[href^="/signals/"]')).map(a => {
                    const href = a.getAttribute('href');
                    const text = a.innerText.trim();
                    const img = a.querySelector('img');
                    const imgSrc = img ? img.getAttribute('src') : null;
                    return { href, text, imgSrc };
                });
                
                // 3. Return combined payload
                return {
                    ok: true,
                    url: window.location.href,
                    cards: cards,
                    rawJson: rawJsonText
                };
            } catch (e) {
                return { ok: false, error: e.toString() };
            }
        })()
        """
        return await self.evaluate_js(ws, js_code)

    async def extract_signal_detail(self, ws, entry_href: str) -> Dict[str, Any]:
        """Fetches full breakdown for a specific signal entry."""
        target_path = entry_href if entry_href.endswith("/__data.json") else f"{entry_href}/__data.json"
        js_code = f"""
        (async () => {{
            try {{
                const res = await fetch('{target_path}');
                if (!res.ok) return {{ ok: false, status: res.status }};
                const text = await res.text();
                return {{ ok: true, data: text }};
            }} catch (e) {{
                return {{ ok: false, error: e.toString() }};
            }}
        }})()
        """
        return await self.evaluate_js(ws, js_code)


def devalue_parse(raw_text: str) -> Any:
    """
    Parses SvelteKit devalue serialized JSON format.
    SvelteKit formats data as {"type": "data", "nodes": [{"type": "data", "data": [...]}]}
    """
    try:
        data = json.loads(raw_text)
        return data
    except Exception as e:
        return {"error": str(e), "raw": raw_text}


async def run_extraction_flow(interactive: bool = True):
    """Orchestrates launch, login detection, signal extraction, and disk persistence."""
    logger.info("Initializing Soli-Trader extraction workflow...")
    
    # 1. Ensure browser is open
    launch_chrome(headless=False if interactive else True)
    
    # 2. Connect to tab
    tab = get_or_create_signals_tab()
    ws_url = tab.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError("No WebSocket debugger URL found for tab.")

    extractor = SoliTraderExtractor()

    async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
        logger.info("Connected to browser tab WebSocket.")
        
        # 3. Check authentication status
        auth = await extractor.check_auth_status(ws)
        logger.info(f"Auth check result: {auth}")

        if not auth.get("isLoggedIn"):
            logger.warning("=" * 60)
            logger.warning("ACTION REQUIRED: USER AUTHENTICATION NEEDED")
            logger.warning("Please switch to the opened Chrome window and log in to Soli-Trader")
            logger.warning("(Enter your mobile number and the SMS OTP).")
            logger.warning("The script is waiting and will automatically proceed upon login...")
            logger.warning("=" * 60)

            # Wait loop for login
            while True:
                await asyncio.sleep(3)
                auth = await extractor.check_auth_status(ws)
                if auth.get("isLoggedIn"):
                    logger.info("AUTHENTICATION CONFIRMED! Proceeding to extract signals...")
                    break
        else:
            logger.info("Authenticated session active. Proceeding with extraction.")

        # 4. Save session cookies
        await extractor.get_session_cookies(ws)

        # 5. Extract main signals payload
        logger.info("Extracting weekly signals data...")
        raw_result = await extractor.extract_signals_data(ws)
        
        parsed_payload = {
            "extracted_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
            "url": raw_result.get("url"),
            "cards": raw_result.get("cards", []),
            "raw_data": devalue_parse(raw_result.get("rawJson", "{}"))
        }

        # 6. For each unique card link, fetch individual detailed levels
        detailed_signals = []
        for card in raw_result.get("cards", []):
            href = card.get("href")
            if href and href.startswith("/signals/"):
                logger.info(f"Fetching level details for: {href}")
                detail = await extractor.extract_signal_detail(ws, href)
                detailed_signals.append({
                    "card": card,
                    "detail_raw": devalue_parse(detail.get("data", "{}")) if detail.get("ok") else None
                })
        
        parsed_payload["detailed_signals"] = detailed_signals

        # Save to disk
        SIGNALS_FILE.write_text(json.dumps(parsed_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        logger.info(f"Successfully saved signals to {SIGNALS_FILE}")
        logger.info(f"Total cards captured: {len(raw_result.get('cards', []))}")
        
        return parsed_payload


if __name__ == "__main__":
    import urllib.parse
    asyncio.run(run_extraction_flow(interactive=True))
