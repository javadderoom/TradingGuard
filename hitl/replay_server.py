"""
TradingGuard HITL - Tornado HTTP API & Static Replay Server (hitl/replay_server.py)
Provides:
- make_app: Factory creating Tornado Application binding REST API routes and SPA static fallbacks:
  * GET /api/catalog: Unified asset registry, cached bounds, engine mode, and $2,000/$20 system risk limits.
  * GET /api/candles: Causal resampled OHLCV with zero-lookahead partial bar synthesis and bounded limits.
  * GET /api/bot-scan: Full chronological SMC forensic scanner with LRU result caching and Killzones.
  * POST /api/simulate-trade: Canonical M1 order execution simulator with true risk compliance tagging.
  * GET/POST/PATCH/DELETE /api/co-trades: Persistent CRUD over shared CoBacktestLedger.
  * GET/POST/DELETE /api/feedback: Persistent CRUD over AgentifyFeedbackStore with prompt markdown generation.
  * POST /api/sync-mt5: Live broker M1 candle fetcher with automatic bot-scan cache invalidation.
  * Catch-all static handler: Serves web_replayer/dist/ static assets or fallback HTML.
- Permissive localhost/127.0.0.1 CORS support for Vite HMR dev server (http://localhost:5173).
- Non-blocking execution offloading CPU/Parquet tasks via asyncio.to_thread.
- CLI entrypoint binding strictly to 127.0.0.1 (--port 8765, --no-browser, webbrowser.open).
"""

import argparse
import asyncio
import collections
import json
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse
import webbrowser

import tornado.ioloop
import tornado.web

from hitl.replay_data import (
    ReplayDataManager,
    SYMBOL_CATALOG,
    TIMEFRAME_SECONDS,
)
from hitl.replay_forensics import (
    run_bot_scan,
    simulate_custom_trade,
)
from hitl.replay_ledger import (
    CoBacktestLedger,
    AgentifyFeedbackStore,
)

DEFAULT_PORT = 8765
DEFAULT_HOST = "127.0.0.1"
MAX_BOT_SCAN_CACHE = 64


class BaseApiHandler(tornado.web.RequestHandler):
    """Base request handler providing CORS headers, JSON serialization, and error helpers."""

    def set_default_headers(self) -> None:
        origin = self.request.headers.get("Origin")
        if origin:
            try:
                parsed = urllib.parse.urlparse(origin)
                if parsed.hostname in ("localhost", "127.0.0.1"):
                    self.set_header("Access-Control-Allow-Origin", origin)
                    self.set_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
                    self.set_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
                    self.set_header("Access-Control-Allow-Credentials", "true")
            except Exception:
                pass

    def options(self, *args, **kwargs) -> None:
        self.set_status(204)
        self.finish()

    def write_json(self, data: Any, status_code: int = 200) -> None:
        self.set_status(status_code)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(json.dumps(data, ensure_ascii=False, default=str))
        self.finish()

    def write_error_json(self, message: str, status_code: int = 400) -> None:
        self.set_status(status_code)
        self.set_header("Content-Type", "application/json; charset=utf-8")
        self.write(json.dumps({"error": message}))
        self.finish()

    def read_json_body(self) -> Dict[str, Any]:
        try:
            body = self.request.body.decode("utf-8")
            if not body or not body.strip():
                return {}
            data = json.loads(body)
            if not isinstance(data, dict):
                raise ValueError("JSON root must be an object")
            return data
        except Exception as e:
            raise ValueError(f"Malformed JSON body: {e}")


class CatalogHandler(BaseApiHandler):
    """Serves registered symbol catalog, cached date ranges, engine modes, and system risk limits."""

    async def get(self) -> None:
        data_mgr: ReplayDataManager = self.settings["data_mgr"]
        try:
            catalog = await asyncio.to_thread(data_mgr.get_catalog)
            self.write_json({
                "symbols": catalog,
                "system_risk_limits": {
                    "account_size_usd": 2000.0,
                    "max_risk_usd": 20.0,
                },
                "account_size_usd": 2000.0,
                "max_risk_usd": 20.0,
            })
        except Exception as e:
            self.write_error_json(f"Failed to load catalog: {e}", 500)


class CandlesHandler(BaseApiHandler):
    """Serves causally resampled candlesticks with strict zero-lookahead partial bar aggregation."""

    async def get(self) -> None:
        data_mgr: ReplayDataManager = self.settings["data_mgr"]
        symbol = self.get_argument("symbol", None)
        start_raw = self.get_argument("start", None)
        end_raw = self.get_argument("end", None)

        if not symbol or start_raw is None or end_raw is None:
            self.write_error_json("Missing required parameters: symbol, start, end", 400)
            return

        if symbol not in SYMBOL_CATALOG:
            self.write_error_json(f"Unknown symbol '{symbol}'", 400)
            return

        try:
            start_epoch = int(start_raw)
            end_epoch = int(end_raw)
        except ValueError:
            self.write_error_json("Invalid numeric format for start or end epoch", 400)
            return

        replay_to_raw = self.get_argument("replay_to", None)
        replay_to = None
        if replay_to_raw is not None and replay_to_raw.strip() != "":
            try:
                replay_to = int(replay_to_raw)
            except ValueError:
                self.write_error_json("Invalid numeric format for replay_to", 400)
                return

        max_bars_raw = self.get_argument("max_bars", "15000")
        try:
            max_bars = int(max_bars_raw)
            max_bars = max(1, min(max_bars, 15000))
        except ValueError:
            self.write_error_json("Invalid numeric format for max_bars", 400)
            return

        tf = self.get_argument("tf", "15M").upper()
        if tf not in TIMEFRAME_SECONDS:
            self.write_error_json(f"Unsupported timeframe '{tf}'. Valid options: {list(TIMEFRAME_SECONDS.keys())}", 400)
            return

        try:
            candles = await asyncio.to_thread(
                data_mgr.get_candles,
                symbol=symbol,
                tf=tf,
                start_epoch=start_epoch,
                end_epoch=end_epoch,
                replay_to=replay_to,
                max_bars=max_bars,
            )
            self.write_json(candles)
        except Exception as e:
            self.write_error_json(f"Failed to fetch candles: {e}", 400)


class BotScanHandler(BaseApiHandler):
    """Executes chronological SMC forensic session scan across 5M bars with LRU caching."""

    async def get(self) -> None:
        data_mgr: ReplayDataManager = self.settings["data_mgr"]
        symbol = self.get_argument("symbol", None)
        start_raw = self.get_argument("start", None)
        end_raw = self.get_argument("end", None)

        if not symbol or start_raw is None or end_raw is None:
            self.write_error_json("Missing required parameters: symbol, start, end", 400)
            return

        if symbol not in SYMBOL_CATALOG:
            self.write_error_json(f"Unknown symbol '{symbol}'", 400)
            return

        try:
            start_epoch = int(start_raw)
            end_epoch = int(end_raw)
        except ValueError:
            self.write_error_json("Invalid numeric format for start or end epoch", 400)
            return

        clock_mode = self.get_argument("clock_mode", "true_tehran")
        if clock_mode not in ("true_tehran", "live_legacy"):
            self.write_error_json("clock_mode must be 'true_tehran' or 'live_legacy'", 400)
            return

        account_size_raw = self.get_argument("account_size", None) or self.get_argument("account_size_usd", "2000.0")
        max_risk_raw = self.get_argument("max_risk", None) or self.get_argument("max_risk_usd", "20.0")
        horizon = self.get_argument("horizon", "window")

        try:
            account_size_usd = float(account_size_raw)
            max_risk_usd = float(max_risk_raw)
        except ValueError:
            self.write_error_json("Invalid numeric format for account_size or max_risk", 400)
            return

        cache_key = (symbol, start_epoch, end_epoch, clock_mode, account_size_usd, max_risk_usd, horizon)
        bot_scan_cache: collections.OrderedDict = self.settings["bot_scan_cache"]

        if cache_key in bot_scan_cache:
            bot_scan_cache.move_to_end(cache_key)
            self.write_json(bot_scan_cache[cache_key])
            return

        try:
            scan_res = await asyncio.to_thread(
                run_bot_scan,
                data_mgr=data_mgr,
                symbol=symbol,
                start_epoch=start_epoch,
                end_epoch=end_epoch,
                clock_mode=clock_mode,
                account_size_usd=account_size_usd,
                max_risk_usd=max_risk_usd,
                horizon=horizon,
            )

            # Insert into bounded LRU cache
            if len(bot_scan_cache) >= MAX_BOT_SCAN_CACHE:
                bot_scan_cache.popitem(last=False)
            bot_scan_cache[cache_key] = scan_res

            self.write_json(scan_res)
        except Exception as e:
            self.write_error_json(f"Bot scan execution failed: {e}", 400)


class SimulateTradeHandler(BaseApiHandler):
    """Simulates a human-proposed or edited trade setup against canonical M1 evaluator."""

    async def post(self) -> None:
        data_mgr: ReplayDataManager = self.settings["data_mgr"]
        try:
            body = self.read_json_body()
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
            return

        required_fields = ["symbol", "direction", "signal_time", "entry", "sl", "tp"]
        for field in required_fields:
            if field not in body:
                self.write_error_json(f"Missing required parameter '{field}'", 400)
                return

        symbol = str(body["symbol"])
        if symbol not in SYMBOL_CATALOG:
            self.write_error_json(f"Unknown symbol '{symbol}'", 400)
            return

        try:
            direction = str(body["direction"])
            signal_time = int(body["signal_time"])
            entry = float(body["entry"])
            sl = float(body["sl"])
            tp = float(body["tp"])
            be_rr = float(body["be_rr"]) if body.get("be_rr") is not None else None
            max_risk_usd = float(body["max_risk_usd"]) if body.get("max_risk_usd") is not None else None
            horizon_end = int(body["horizon_end"]) if body.get("horizon_end") is not None else None
            lot = float(body.get("lot", 0.01))
        except (ValueError, TypeError) as e:
            self.write_error_json(f"Invalid field format: {e}", 400)
            return

        try:
            sim_res = await asyncio.to_thread(
                simulate_custom_trade,
                data_mgr=data_mgr,
                symbol=symbol,
                direction=direction,
                signal_time=signal_time,
                entry=entry,
                sl=sl,
                tp=tp,
                be_rr=be_rr,
                max_risk_usd=max_risk_usd,
                horizon_end=horizon_end,
                lot=lot,
            )
            self.write_json(sim_res)
        except Exception as e:
            self.write_error_json(f"Trade simulation failed: {e}", 400)


class CoTradesHandler(BaseApiHandler):
    """Handles list and creation of shared CoBacktestLedger trade records."""

    def get(self) -> None:
        ledger: CoBacktestLedger = self.settings["ledger"]
        symbol = self.get_argument("symbol", None)
        trades = ledger.list_trades(symbol=symbol)
        scorecard = ledger.get_scorecard(symbol=symbol)
        self.write_json({"trades": trades, "scorecard": scorecard})

    def post(self) -> None:
        ledger: CoBacktestLedger = self.settings["ledger"]
        try:
            body = self.read_json_body()
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
            return

        origin = body.get("origin")
        if origin not in ("BOT", "HUMAN_PROPOSED", "HUMAN_EDITED_BOT"):
            self.write_error_json(
                f"Invalid trade origin '{origin}'. Must be one of ('BOT', 'HUMAN_PROPOSED', 'HUMAN_EDITED_BOT')",
                400,
            )
            return

        try:
            trade = ledger.add_trade(body)
            trade.setdefault("id", trade.get("trade_id"))
            self.write_json(trade, status_code=201)
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
        except Exception as e:
            self.write_error_json(f"Failed to add trade: {e}", 400)


class CoTradeItemHandler(BaseApiHandler):
    """Handles updating and deleting single CoBacktestLedger trade records."""

    def patch(self, trade_id: str) -> None:
        ledger: CoBacktestLedger = self.settings["ledger"]
        try:
            patch = self.read_json_body()
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
            return

        try:
            updated = ledger.update_trade(trade_id, patch)
            if updated is None:
                self.write_error_json(f"Trade '{trade_id}' not found", 404)
            else:
                updated.setdefault("id", updated.get("trade_id"))
                self.write_json(updated, status_code=200)
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
        except Exception as e:
            self.write_error_json(f"Failed to update trade: {e}", 400)

    def delete(self, trade_id: str) -> None:
        ledger: CoBacktestLedger = self.settings["ledger"]
        deleted = ledger.delete_trade(trade_id)
        if not deleted:
            self.write_error_json(f"Trade '{trade_id}' not found", 404)
        else:
            self.write_json({"success": True, "trade_id": trade_id}, status_code=200)


class FeedbackHandler(BaseApiHandler):
    """Handles listing and creating Agentify forensic cases and prompt bundles."""

    def get(self) -> None:
        fb_store: AgentifyFeedbackStore = self.settings["fb_store"]
        cases = fb_store.list_cases()
        self.write_json({"cases": cases})

    def post(self) -> None:
        fb_store: AgentifyFeedbackStore = self.settings["fb_store"]
        try:
            body = self.read_json_body()
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
            return

        try:
            case = fb_store.add_case(body)
            case.setdefault("id", case.get("case_id"))
            self.write_json({
                "case": case,
                "prompt_markdown": case.get("prompt_markdown", ""),
            }, status_code=201)
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
        except Exception as e:
            self.write_error_json(f"Failed to create feedback case: {e}", 400)


class FeedbackItemHandler(BaseApiHandler):
    """Handles deleting single Agentify forensic cases."""

    def delete(self, case_id: str) -> None:
        fb_store: AgentifyFeedbackStore = self.settings["fb_store"]
        deleted = fb_store.delete_case(case_id)
        if not deleted:
            self.write_error_json(f"Feedback case '{case_id}' not found", 404)
        else:
            self.write_json({"success": True, "case_id": case_id}, status_code=200)


class SyncMt5Handler(BaseApiHandler):
    """Syncs recent M1 rates from MetaTrader 5 terminal and invalidates symbol cache."""

    async def post(self) -> None:
        data_mgr: ReplayDataManager = self.settings["data_mgr"]
        try:
            body = self.read_json_body()
        except ValueError as ve:
            self.write_error_json(str(ve), 400)
            return

        symbol = body.get("symbol")
        if not symbol:
            self.write_error_json("Missing required parameter 'symbol'", 400)
            return

        if symbol not in SYMBOL_CATALOG:
            self.write_error_json(f"Unknown symbol '{symbol}'", 400)
            return

        try:
            days_back = int(body.get("days_back", 5))
        except ValueError:
            self.write_error_json("Invalid numeric format for days_back", 400)
            return

        try:
            res = await asyncio.to_thread(data_mgr.sync_symbol_from_mt5, symbol=symbol, days_back=days_back)

            if res.get("success"):
                # Invalidate cached bot-scan entries for this symbol
                bot_scan_cache: collections.OrderedDict = self.settings["bot_scan_cache"]
                sym_clean = symbol.upper()
                keys_to_purge = [k for k in list(bot_scan_cache.keys()) if k[0].upper() == sym_clean]
                for k in keys_to_purge:
                    bot_scan_cache.pop(k, None)

            self.write_json(res, status_code=200)
        except Exception as e:
            self.write_error_json(f"MT5 sync failed: {e}", 500)


class SpaFallbackHandler(BaseApiHandler):
    """Serves compiled frontend SPA assets from web_replayer/dist/ or a friendly fallback page."""

    def get(self, path: str = "") -> None:
        static_dir = Path(self.settings.get("static_dir", ""))
        requested_file = (static_dir / path.lstrip("/")).resolve()

        # Serve static file if it physically exists inside static_dir
        if static_dir.exists() and path and requested_file.is_file() and static_dir in requested_file.parents:
            content_type, _ = mimetypes.guess_type(str(requested_file))
            self.set_header("Content-Type", content_type or "application/octet-stream")
            with open(requested_file, "rb") as f:
                self.write(f.read())
            return

        # Serve dist/index.html if built
        index_file = static_dir / "index.html"
        if index_file.exists():
            with open(index_file, "r", encoding="utf-8") as f:
                html_content = f.read()
            self.set_header("Content-Type", "text/html; charset=utf-8")
            self.write(html_content)
            return

        # Fallback informative HTML page when frontend is not yet built
        fallback_html = (
            "<!DOCTYPE html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "  <meta charset=\"UTF-8\" />\n"
            "  <title>TradingGuard Visual Co-Backtester</title>\n"
            "  <style>\n"
            "    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; "
            "background: #121418; color: #d1d4dc; padding: 40px; text-align: center; }\n"
            "    .card { background: #1e222d; border: 1px solid #2a2e39; border-radius: 8px; max-width: 600px; "
            "margin: 0 auto; padding: 32px; }\n"
            "    h1 { color: #f0b90b; margin-top: 0; }\n"
            "    code { background: #2a2e39; padding: 2px 6px; border-radius: 4px; color: #4ba3e3; }\n"
            "  </style>\n"
            "</head>\n"
            "<body>\n"
            "  <div class=\"card\">\n"
            "    <h1>TradingGuard Visual Co-Backtester</h1>\n"
            "    <p>API server is active and running cleanly on <code>127.0.0.1</code>.</p>\n"
            "    <p>Frontend assets are not yet compiled. Build via <code>npm run build</code> inside <code>web_replayer/</code> "
            "or start the Vite dev server via <code>npm run dev</code> on <code>http://localhost:5173</code>.</p>\n"
            "  </div>\n"
            "</body>\n"
            "</html>"
        )
        self.set_header("Content-Type", "text/html; charset=utf-8")
        self.write(fallback_html)


def make_app(
    data_mgr: Optional[ReplayDataManager] = None,
    ledger: Optional[CoBacktestLedger] = None,
    fb_store: Optional[AgentifyFeedbackStore] = None,
    static_dir: Optional[Path] = None,
) -> tornado.web.Application:
    """Factory creating the Tornado Application with all API routes and persistent ledger bindings."""
    if data_mgr is None:
        data_mgr = ReplayDataManager()
    if ledger is None:
        ledger = CoBacktestLedger()
    if fb_store is None:
        fb_store = AgentifyFeedbackStore()
    if static_dir is None:
        static_dir = Path(__file__).resolve().parent.parent / "web_replayer" / "dist"
    static_dir = Path(static_dir)

    assets_dir = static_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    bot_scan_cache = collections.OrderedDict()

    handlers = [
        (r"/api/catalog/?", CatalogHandler),
        (r"/api/candles/?", CandlesHandler),
        (r"/api/bot-scan/?", BotScanHandler),
        (r"/api/simulate-trade/?", SimulateTradeHandler),
        (r"/api/co-trades/?", CoTradesHandler),
        (r"/api/co-trades/([^/]+)/?", CoTradeItemHandler),
        (r"/api/feedback/?", FeedbackHandler),
        (r"/api/feedback/([^/]+)/?", FeedbackItemHandler),
        (r"/api/sync-mt5/?", SyncMt5Handler),
        (r"/assets/(.*)", tornado.web.StaticFileHandler, {"path": str(assets_dir)}),
        (r"/(.*)", SpaFallbackHandler),
    ]

    return tornado.web.Application(
        handlers,
        data_mgr=data_mgr,
        ledger=ledger,
        fb_store=fb_store,
        static_dir=static_dir,
        bot_scan_cache=bot_scan_cache,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TradingGuard Visual Co-Backtesting Server")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"Server port (default: {DEFAULT_PORT})")
    parser.add_argument("--host", type=str, default=DEFAULT_HOST, help=f"Bind host (default: {DEFAULT_HOST})")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically launch web browser")
    args = parser.parse_args()

    app = make_app()
    app.listen(args.port, address=args.host)
    url = f"http://{args.host}:{args.port}"
    print(f"[TradingGuard] Replay Server running at {url}")
    print("[TradingGuard] Bound strictly to localhost/127.0.0.1. Press Ctrl+C to terminate.")

    if not args.no_browser:
        webbrowser.open(url)

    tornado.ioloop.IOLoop.current().start()
