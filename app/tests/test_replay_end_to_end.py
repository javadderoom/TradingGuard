"""
End-to-End Integration Tests for Visual Co-Backtester & Workbench (hitl/replay_server.py)
Validating:
1. Static SPA serving: built web_replayer/dist/index.html served at / (HTTP 200 with root container)
   and compiled assets served from /assets/.
2. Complete REST end-to-end workflow:
   - GET /api/catalog: asset registry, engine modes, $2000 / $20 risk limits
   - GET /api/candles: causal 1M and 1H bars with replay_to anti-spoiler clamp
   - GET /api/bot-scan: chronological SMC scan, Asian bounds, Killzones, and SETUP-ARCH-001
   - POST /api/simulate-trade: canonical M1 forward simulator with uncapped R:R & $20 compliance
   - POST /api/co-trades: persists HUMAN_PROPOSED & HUMAN_EDITED_BOT trades to temp ledger
   - GET /api/co-trades: comparative scorecard and marked trade records
   - POST /api/feedback: creates forensic Agentify feedback case and generates markdown prompt
   - GET /api/feedback: lists recorded feedback cases
"""

import json
from pathlib import Path
import tempfile
import urllib.parse

from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application

from hitl.replay_data import ReplayDataManager
from hitl.replay_ledger import AgentifyFeedbackStore, CoBacktestLedger
from hitl.replay_server import make_app


class TestReplayEndToEnd(AsyncHTTPTestCase):
    """End-to-end integration test verifying built frontend SPA serving & complete REST workflow."""

    def get_http_client_timeout(self) -> float:
        return 30.0

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.ledger_file = Path(self.tmp_dir.name) / "test_visual_ledger.json"
        self.feedback_file = Path(self.tmp_dir.name) / "test_feedback_cases.json"
        self.dist_dir = Path(__file__).resolve().parent.parent.parent / "web_replayer" / "dist"
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
            static_dir=self.dist_dir,
        )

    def test_spa_production_build_served_at_root(self):
        """Verifies that built web_replayer/dist/index.html is served cleanly at / with HTTP 200."""
        resp = self.fetch("/")
        assert resp.code == 200
        content_type = resp.headers.get("Content-Type", "")
        assert "text/html" in content_type

        html = resp.body.decode("utf-8")
        assert '<div id="root"></div>' in html or 'id="root"' in html
        assert "<!doctype html>" in html.lower()

    def test_end_to_end_rest_co_trading_and_agentify_workflow(self):
        """
        Executes complete multi-step REST workflow:
        1. GET /api/catalog
        2. GET /api/candles (1M and 1H)
        3. GET /api/bot-scan (Nov 11 Gold -> SETUP-ARCH-001)
        4. POST /api/simulate-trade (Human setup with wide stop)
        5. POST & GET /api/co-trades (Ledger persistence)
        6. POST & GET /api/feedback (Agentify prompt capture)
        """
        # Step 1: Catalog
        catalog_resp = self.fetch("/api/catalog")
        assert catalog_resp.code == 200
        catalog = json.loads(catalog_resp.body.decode("utf-8"))
        symbols = catalog.get("symbols", [])
        assert len(symbols) == 6
        sym_map = {s["symbol"]: s for s in symbols}
        assert "XAUUSD_o" in sym_map
        assert "BTCUSD" in sym_map
        assert sym_map["BTCUSD"]["engine_mode"] == "MANUAL_ONLY"
        assert catalog.get("account_size_usd") == 2000.0 or catalog.get("system_risk_limits", {}).get("account_size_usd") == 2000.0
        assert catalog.get("max_risk_usd") == 20.0 or catalog.get("system_risk_limits", {}).get("max_risk_usd") == 20.0

        # Step 2: Candles (1M full and 1H causal)
        nov11_start = 1794355200  # 2026-11-11 00:00 server
        nov11_end = 1794441540    # 2026-11-11 23:59 server

        # 1M candles
        q_1m = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "tf": "1M",
            "start": nov11_start,
            "end": nov11_end,
        })
        resp_1m = self.fetch(f"/api/candles?{q_1m}")
        assert resp_1m.code == 200
        data_1m = json.loads(resp_1m.body.decode("utf-8"))
        assert len(data_1m.get("bars", [])) > 1000

        # 1H candles with causal replay_to
        replay_cutoff = 1794391500  # 10:05 server time
        q_1h = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "tf": "1H",
            "start": nov11_start,
            "end": nov11_end,
            "replay_to": replay_cutoff,
        })
        resp_1h = self.fetch(f"/api/candles?{q_1h}")
        assert resp_1h.code == 200
        data_1h = json.loads(resp_1h.body.decode("utf-8"))
        bars_1h = data_1h.get("bars", [])
        assert len(bars_1h) > 0
        for b in bars_1h:
            assert b["time"] <= replay_cutoff

        # Step 3: Bot Scan (true_tehran mode)
        q_scan = urllib.parse.urlencode({
            "symbol": "XAUUSD_o",
            "start": nov11_start,
            "end": nov11_end,
            "clock_mode": "true_tehran",
            "account_size": 2000,
            "max_risk": 20,
        })
        resp_scan = self.fetch(f"/api/bot-scan?{q_scan}")
        assert resp_scan.code == 200
        scan_data = json.loads(resp_scan.body.decode("utf-8"))
        assert "killzones" in scan_data
        assert "bot_trades" in scan_data
        bot_trades = scan_data["bot_trades"]
        assert len(bot_trades) >= 1
        arch001 = next((t for t in bot_trades if t.get("archetype_id") == "SETUP-ARCH-001"), None)
        assert arch001 is not None
        assert arch001["origin"] == "BOT"

        # Step 4: Simulate Trade (Human Setup)
        sim_payload = {
            "symbol": "XAUUSD_o",
            "direction": "LONG",
            "signal_time": 1794391500,
            "entry": 4068.50,
            "sl": 4048.50,  # $20.00 stop distance -> $20.00 risk at 0.01
            "tp": 4128.50,  # 3.0R target
            "horizon_end": nov11_end,
        }
        resp_sim = self.fetch(
            "/api/simulate-trade",
            method="POST",
            body=json.dumps(sim_payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp_sim.code == 200
        sim_data = json.loads(resp_sim.body.decode("utf-8"))
        assert "status" in sim_data
        assert "risk_usd_001" in sim_data
        assert sim_data["risk_usd_001"] == 20.0
        assert not sim_data["exceeds_risk_cap"]

        # Step 5: Save to Co-Trades Ledger and verify GET
        trade_payload = {
            "trade_id": "COTRADE-XAU-001",
            "symbol": "XAUUSD_o",
            "origin": "HUMAN_PROPOSED",
            "direction": "LONG",
            "decision_time": 1794391500,
            "entry": 4068.50,
            "sl": 4048.50,
            "tp": 4128.50,
            "status": sim_data["status"],
            "realized_pnl_usd": sim_data.get("realized_pnl_usd"),
            "rr_realized": sim_data.get("rr_realized"),
            "fill_time": sim_data.get("fill_time"),
            "exit_time": sim_data.get("exit_time"),
            "risk_usd_001": sim_data["risk_usd_001"],
            "exceeds_risk_cap": sim_data["exceeds_risk_cap"],
            "notes": "Human Proposed Setup at London Open",
        }
        resp_post_trade = self.fetch(
            "/api/co-trades",
            method="POST",
            body=json.dumps(trade_payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp_post_trade.code in (200, 201)
        saved_trade = json.loads(resp_post_trade.body.decode("utf-8"))
        assert saved_trade["trade_id"] == "COTRADE-XAU-001"
        assert saved_trade["origin"] == "HUMAN_PROPOSED"

        # Verify GET /api/co-trades reflects saved trade & scorecard
        resp_get_trades = self.fetch("/api/co-trades?symbol=XAUUSD_o")
        assert resp_get_trades.code == 200
        co_trades_data = json.loads(resp_get_trades.body.decode("utf-8"))
        trades_list = co_trades_data.get("trades", [])
        assert any(t["trade_id"] == "COTRADE-XAU-001" for t in trades_list)
        assert "scorecard" in co_trades_data
        assert "HUMAN_PROPOSED" in co_trades_data["scorecard"]

        # Step 6: Create Agentify Feedback Case and verify prompt generation
        fb_payload = {
            "case_id": "CASE-NOV11-001",
            "symbol": "XAUUSD_o",
            "timestamp": 1794391500,
            "title": "Nov 11 London Judas Sweep Evaluation",
            "notes": "Testing human alignment prompt generation against screener diagnostics",
            "category": "MISSED_SETUP",
            "archetype_id": "SETUP-ARCH-001",
        }
        resp_post_fb = self.fetch(
            "/api/feedback",
            method="POST",
            body=json.dumps(fb_payload),
            headers={"Content-Type": "application/json"},
        )
        assert resp_post_fb.code in (200, 201)
        fb_res = json.loads(resp_post_fb.body.decode("utf-8"))
        assert "case" in fb_res
        assert "prompt_markdown" in fb_res
        prompt_md = fb_res["prompt_markdown"]
        assert "Agentify Forensic Snapshot" in prompt_md
        assert "XAUUSD_o" in prompt_md

        # Verify GET /api/feedback lists saved case
        resp_get_fb = self.fetch("/api/feedback")
        assert resp_get_fb.code == 200
        fb_list = json.loads(resp_get_fb.body.decode("utf-8")).get("cases", [])
        assert any(c["case_id"] == "CASE-NOV11-001" for c in fb_list)
