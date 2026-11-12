"""
Tests for Tornado HTTP API Server & Shared Co-Backtest Ledger (hitl/replay_server.py).
Validating:
1. Catalog & Causal Candles API (/api/catalog, /api/candles)
2. Bot Scan, Simulate Trade, & Co-Trade CRUD (/api/bot-scan, /api/simulate-trade, /api/co-trades)
3. Agentify Feedback Endpoint & Markdown Generator (/api/feedback)
4. Bounded Large-Range & Weekend Invariant (/api/candles with 30d 1M and weekend window)
5. CORS Headers & Preflight OPTIONS Handler
6. Error Handling: 400 Bad Request on invalid inputs, 404 Not Found on unknown IDs
"""

import json
from pathlib import Path
import tempfile
import urllib.parse

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

from hitl.replay_server import make_app
from hitl.replay_data import ReplayDataManager
from hitl.replay_ledger import CoBacktestLedger, AgentifyFeedbackStore


class TestReplayServer(AsyncHTTPTestCase):
    """Integration test suite for Tornado HTTP API server and CoBacktestLedger."""

    def get_http_client_timeout(self) -> float:
        return 20.0

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.tmp_dir.name) / "test_ledger.json"
        self.feedback_file = Path(self.tmp_dir.name) / "test_feedback.json"
        super().setUp()

    def tearDown(self):
        super().tearDown()
        self.tmp_dir.cleanup()

    def get_app(self) -> Application:
        self.data_mgr = ReplayDataManager()
        self.ledger = CoBacktestLedger(file_path=self.ledger_file)
        self.fb_store = AgentifyFeedbackStore(file_path=self.feedback_file)
        return make_app(
            data_mgr=self.data_mgr,
            ledger=self.ledger,
            fb_store=self.fb_store,
            static_dir=Path(self.tmp_dir.name) / "dist",
        )

    def test_catalog_and_candles_endpoints(self):
        """Asserts GET /api/catalog returns 6 symbols and GET /api/candles returns causal candles."""
        # 1. Test /api/catalog
        resp = self.fetch("/api/catalog")
        assert resp.code == 200
        catalog_data = json.loads(resp.body.decode("utf-8"))
        symbols = catalog_data.get("symbols", catalog_data)
        assert isinstance(symbols, list)
        assert len(symbols) == 6
        sym_names = [s["symbol"] for s in symbols]
        assert "XAUUSD_o" in sym_names
        assert "GBPUSD_o" in sym_names
        assert "NQ" in sym_names
        assert "SPX" in sym_names
        assert "YM" in sym_names
        assert "BTCUSD" in sym_names

        # Verify BTCUSD is marked MANUAL_ONLY
        btc = next(s for s in symbols if s["symbol"] == "BTCUSD")
        assert btc["engine_mode"] == "MANUAL_ONLY"

        # Verify risk limits in catalog
        assert catalog_data.get("account_size_usd") == 2000.0 or catalog_data.get("system_risk_limits", {}).get("account_size_usd") == 2000.0
        assert catalog_data.get("max_risk_usd") == 20.0 or catalog_data.get("system_risk_limits", {}).get("max_risk_usd") == 20.0

        # 2. Test /api/candles with causal replay_to
        # 2026-11-11 bounds
        start_epoch = 1794355200
        end_epoch = 1794441540
        replay_to = 1794391500  # 10:05 server time

        params = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "tf": "15M",
            "start": start_epoch,
            "end": end_epoch,
            "replay_to": replay_to,
        })
        resp_candles = self.fetch(f"/api/candles?{params}")
        assert resp_candles.code == 200
        candles_data = json.loads(resp_candles.body.decode("utf-8"))
        assert "bars" in candles_data
        bars = candles_data["bars"]
        assert len(bars) > 0
        # All returned bars must be <= replay_to
        for bar in bars:
            assert bar["time"] <= replay_to

    def test_bot_scan_and_simulate_and_co_trade_crud(self):
        """
        Calls GET /api/bot-scan on 2026-11-11, posts a HUMAN_EDITED_BOT entry to /api/co-trades,
        verifies GET /api/co-trades persists origin="HUMAN_EDITED_BOT", deletes it, and checks 200 status codes.
        """
        # 1. GET /api/bot-scan for 2026-11-11
        scan_params = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "start": 1794355200,
            "end": 1794441540,
            "clock_mode": "true_tehran",
            "account_size": 2000.0,
            "max_risk": 20.0,
        })
        resp_scan = self.fetch(f"/api/bot-scan?{scan_params}")
        assert resp_scan.code == 200
        scan_res = json.loads(resp_scan.body.decode("utf-8"))
        assert "bot_trades" in scan_res
        assert "bot_scorecard" in scan_res
        assert "killzones" in scan_res
        assert "asian_ranges_by_day" in scan_res

        # 2. POST /api/simulate-trade
        sim_payload = {
            "symbol": "XAUUSD_o",
            "direction": "BUY",
            "signal_time": 1794391500,
            "entry": 4050.0,
            "sl": 4045.0,
            "tp": 4065.0,
            "be_rr": 1.5,
            "lot": 0.01,
        }
        resp_sim = self.fetch(
            "/api/simulate-trade",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(sim_payload),
        )
        assert resp_sim.code == 200
        sim_res = json.loads(resp_sim.body.decode("utf-8"))
        assert "status" in sim_res
        assert "realized_pnl_usd" in sim_res
        assert "exceeds_risk_cap" in sim_res

        # 3. POST /api/co-trades with HUMAN_EDITED_BOT
        trade_payload = {
            "origin": "HUMAN_EDITED_BOT",
            "symbol": "XAUUSD_o",
            "direction": "BUY",
            "entry": 4050.0,
            "sl": 4045.0,
            "tp": 4065.0,
            "decision_time": 1794391500,
            "parent_bot_ref": "BOT-XAU-1794391500",
            "status": "WIN",
            "realized_pnl_usd": 15.0,
            "rr_realized": 3.0,
            "user_rationale": "Tightened stop loss to structural breaker low",
        }
        resp_post = self.fetch(
            "/api/co-trades",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(trade_payload),
        )
        assert resp_post.code in (200, 201)
        created_trade = json.loads(resp_post.body.decode("utf-8"))
        trade_id = created_trade.get("trade_id") or created_trade.get("id")
        assert trade_id is not None
        assert created_trade.get("origin") == "HUMAN_EDITED_BOT"

        # 4. GET /api/co-trades
        resp_list = self.fetch("/api/co-trades?symbol=XAUUSD_o")
        assert resp_list.code == 200
        ledger_data = json.loads(resp_list.body.decode("utf-8"))
        assert "trades" in ledger_data
        assert "scorecard" in ledger_data
        trades = ledger_data["trades"]
        assert len(trades) == 1
        assert trades[0]["origin"] == "HUMAN_EDITED_BOT"
        assert ledger_data["scorecard"]["HUMAN_EDITED_BOT"]["total_trades"] == 1

        # 5. PATCH /api/co-trades/<trade_id>
        patch_payload = {"user_rationale": "Updated rationale after post-mortem"}
        resp_patch = self.fetch(
            f"/api/co-trades/{trade_id}",
            method="PATCH",
            headers={"Content-Type": "application/json"},
            body=json.dumps(patch_payload),
        )
        assert resp_patch.code == 200
        patched_trade = json.loads(resp_patch.body.decode("utf-8"))
        assert patched_trade.get("user_rationale") == "Updated rationale after post-mortem"

        # 6. DELETE /api/co-trades/<trade_id>
        resp_del = self.fetch(f"/api/co-trades/{trade_id}", method="DELETE")
        assert resp_del.code == 200

        # Verify deletion
        resp_after_del = self.fetch("/api/co-trades")
        assert resp_after_del.code == 200
        after_data = json.loads(resp_after_del.body.decode("utf-8"))
        assert len(after_data["trades"]) == 0

    def test_agentify_feedback_endpoint_persists_case(self):
        """Calls POST /api/feedback with a missed-setup payload and asserts response returns case.id + prompt_markdown."""
        feedback_payload = {
            "symbol": "XAUUSD_o",
            "timestamp": 1794409800,  # 15:10 Server / 16:40 Tehran
            "user_note": "Bot missed valid London continuation due to false session hour veto",
            "user_setup": {
                "direction": "SHORT",
                "entry": 4042.0,
                "sl": 4048.0,
                "tp": 4025.0,
            },
            "bot_trade": None,
            "screener_diagnostics": {
                "session_hour": 18,
                "has_setup": False,
                "reason": "Veto: Late NY PM / Silver Bullet window banned on XAUUSD_o per 1-year empirical audit",
                "phase": "EQUILIBRIUM",
            },
        }

        # 1. POST /api/feedback
        resp = self.fetch(
            "/api/feedback",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps(feedback_payload),
        )
        assert resp.code in (200, 201)
        data = json.loads(resp.body.decode("utf-8"))
        assert "case" in data
        assert "prompt_markdown" in data

        case = data["case"]
        case_id = case.get("case_id") or case.get("id")
        assert case_id is not None
        assert case.get("symbol") == "XAUUSD_o"

        prompt = data["prompt_markdown"]
        assert "XAUUSD_o" in prompt
        assert "Late NY PM / Silver Bullet window banned" in prompt
        assert "4042" in prompt

        # 2. GET /api/feedback
        resp_get = self.fetch("/api/feedback")
        assert resp_get.code == 200
        get_data = json.loads(resp_get.body.decode("utf-8"))
        cases = get_data.get("cases", get_data)
        assert len(cases) == 1

        # 3. DELETE /api/feedback/<case_id>
        resp_del = self.fetch(f"/api/feedback/{case_id}", method="DELETE")
        assert resp_del.code == 200

        # Verify deletion
        resp_after = self.fetch("/api/feedback")
        after_cases = json.loads(resp_after.body.decode("utf-8")).get("cases", [])
        assert len(after_cases) == 0

    def test_oversized_m1_range_returns_bounded_200(self):
        """Queries 30 days of 1M and weekend date range -> asserts HTTP 200 with truncated=True / empty array safely."""
        # 1. 30 days of 1M
        # From Jan 1, 2026 to Jan 31, 2026: 1767225600 to 1769817600 (~43,200 bars)
        params_30d = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "tf": "1M",
            "start": 1767225600,
            "end": 1769817600,
            "max_bars": 15000,
        })
        resp_30d = self.fetch(f"/api/candles?{params_30d}")
        assert resp_30d.code == 200
        data_30d = json.loads(resp_30d.body.decode("utf-8"))
        assert "bars" in data_30d
        assert data_30d.get("truncated") is True
        assert len(data_30d["bars"]) <= 15000

        # 2. Weekend date range: Saturday 2026-11-07 to Sunday 2026-11-08
        params_weekend = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "tf": "5M",
            "start": 1794009600,
            "end": 1794096000,
        })
        resp_weekend = self.fetch(f"/api/candles?{params_weekend}")
        assert resp_weekend.code == 200
        data_weekend = json.loads(resp_weekend.body.decode("utf-8"))
        assert "bars" in data_weekend
        assert isinstance(data_weekend["bars"], list)

    def test_cors_headers_and_options(self):
        """Verifies permissive localhost/127.0.0.1 CORS headers and OPTIONS preflight."""
        # OPTIONS request with Origin localhost
        resp = self.fetch(
            "/api/catalog",
            method="OPTIONS",
            headers={"Origin": "http://localhost:5173"},
        )
        assert resp.code == 204
        assert resp.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"
        assert "GET" in resp.headers.get("Access-Control-Allow-Methods", "")

        # GET request with 127.0.0.1 Origin
        resp_get = self.fetch(
            "/api/catalog",
            headers={"Origin": "http://127.0.0.1:3000"},
        )
        assert resp_get.code == 200
        assert resp_get.headers.get("Access-Control-Allow-Origin") == "http://127.0.0.1:3000"

    def test_error_handling_400_and_404(self):
        """Verifies clean 400 Bad Request on invalid parameters and 404 on missing resources."""
        # Missing required parameters for /api/candles
        resp_bad_candles = self.fetch("/api/candles?symbol=XAUUSD_o")
        assert resp_bad_candles.code == 400
        err_json = json.loads(resp_bad_candles.body.decode("utf-8"))
        assert "error" in err_json

        # Malformed JSON in POST /api/co-trades
        resp_bad_json = self.fetch(
            "/api/co-trades",
            method="POST",
            headers={"Content-Type": "application/json"},
            body="invalid-json-content",
        )
        assert resp_bad_json.code == 400

        # Invalid origin in POST /api/co-trades
        resp_bad_origin = self.fetch(
            "/api/co-trades",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"origin": "INVALID_ORIGIN"}),
        )
        assert resp_bad_origin.code == 400

        # 404 on deleting non-existent trade
        resp_missing_trade = self.fetch("/api/co-trades/NON_EXISTENT_ID", method="DELETE")
        assert resp_missing_trade.code == 404

        # 404 on deleting non-existent feedback case
        resp_missing_case = self.fetch("/api/feedback/NON_EXISTENT_ID", method="DELETE")
        assert resp_missing_case.code == 404

    def test_sync_mt5_endpoint(self):
        """Verifies POST /api/sync-mt5 handles requests cleanly (even when MT5 terminal is offline)."""
        resp = self.fetch(
            "/api/sync-mt5",
            method="POST",
            headers={"Content-Type": "application/json"},
            body=json.dumps({"symbol": "XAUUSD_o", "days_back": 1}),
        )
        assert resp.code == 200
        data = json.loads(resp.body.decode("utf-8"))
        assert "symbol" in data
        assert data["symbol"] == "XAUUSD_o"
        assert "success" in data

    def test_spa_fallback_and_static(self):
        """Verifies GET / returns 200 with HTML fallback when dist/index.html is not yet built."""
        resp = self.fetch("/")
        assert resp.code == 200
        html = resp.body.decode("utf-8")
        assert "TradingGuard Visual Co-Backtester" in html

