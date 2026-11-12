import json
from pathlib import Path
from hitl.backtest.export_visual_replay import server_epoch_to_zones, compile_visual_replay


def test_server_epoch_to_zones_winter_and_summer():
    # Nov 11, 2026 10:00 Server (Winter EET = UTC+2 -> 08:00 UTC -> 11:30 Tehran)
    # Construct UTC-encoded epoch representing 2026-11-11 10:00:00
    import datetime
    ep_winter = int(datetime.datetime(2026, 11, 11, 10, 0, tzinfo=datetime.timezone.utc).timestamp())
    z_w = server_epoch_to_zones(ep_winter)
    assert z_w["srv_str"] == "10:00"
    assert z_w["utc_str"] == "08:00"
    assert z_w["tehran_str"] == "11:30"
    assert z_w["offset_sec"] == 7200

    # July 15, 2026 10:00 Server (Summer EEST = UTC+3 -> 07:00 UTC -> 10:30 Tehran)
    ep_summer = int(datetime.datetime(2026, 7, 15, 10, 0, tzinfo=datetime.timezone.utc).timestamp())
    z_s = server_epoch_to_zones(ep_summer)
    assert z_s["srv_str"] == "10:00"
    assert z_s["utc_str"] == "07:00"
    assert z_s["tehran_str"] == "10:30"
    assert z_s["offset_sec"] == 10800


def test_compile_visual_replay_generates_valid_html(tmp_path, monkeypatch):
    import hitl.backtest.export_visual_replay as evr
    test_html = tmp_path / "test_replayer.html"
    monkeypatch.setattr(evr, "ARTIFACT_HTML", test_html)

    out = compile_visual_replay(["2026-11-11", "2026-11-10"], symbol="XAUUSD_o", refresh_live=False)
    assert out.exists()
    content = out.read_text(encoding="utf-8")
    assert "window.REPLAY_DATASET = " in content

    payload_str = content.split("window.REPLAY_DATASET = ")[1].split(";\n\nlet currentDateKey")[0]
    data = json.loads(payload_str)
    assert "2026-11-11" in data
    assert "2026-11-10" in data
    assert len(data["2026-11-11"]["bars_m5"]) > 100
    assert len(data["2026-11-11"]["bars_m1"]) > 500
    assert len(data["2026-11-11"]["trades"]) == 1
    assert data["2026-11-11"]["trades"][0]["archetype"] == "SETUP-ARCH-001"
    assert data["2026-11-11"]["trades"][0]["outcome"] == "WIN"
