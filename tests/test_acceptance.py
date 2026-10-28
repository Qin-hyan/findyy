"""端到端验收工作台：来源、耗时、验收运行、设备探测与导出脱敏。

全部使用 MockDetector + HashEmbedder + 回放帧，不依赖真实模型/设备。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from findy.config import REPO_ROOT
from findy.db import Database
from findy.sources import Esp32Source, SourceError

PASS = "PASS"
FAIL = "FAIL"
NOT_VERIFIED = "NOT_VERIFIED"


def start_run(client, mode="replay_demo"):
    resp = client.post("/api/acceptance/run/start", json={"mode": mode})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    return body["run"]


def finish_run(client, run_id):
    resp = client.post(f"/api/acceptance/run/{run_id}/finish")
    assert resp.status_code == 200, resp.text
    return resp.json()


def item_map(overview):
    return {item["key"]: item for item in overview["items"]}


def test_workbench_page_served(api_client):
    page = api_client.get("/workbench")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "工作台" in page.text
    for static_path in ("/static/workbench.js", "/static/workbench.css"):
        static = api_client.get(static_path)
        assert static.status_code == 200, static_path


def test_acceptance_without_run_is_not_verified(api_client):
    data = api_client.get("/api/acceptance").json()
    assert data["run"] is None
    overview = data["overview"]
    assert overview["status"] == NOT_VERIFIED
    assert len(overview["items"]) == 6
    assert all(item["status"] == NOT_VERIFIED for item in overview["items"])


def test_capture_records_provenance_and_timing(api_client):
    resp = api_client.post("/api/capture")
    assert resp.status_code == 200
    body = resp.json()
    capture = body["capture"]
    assert capture["source_kind"] == "replay"
    assert capture["detect_ms"] is not None and capture["detect_ms"] >= 0
    assert capture["process_ms"] is not None and capture["process_ms"] >= 0
    assert body["elapsed_ms"] >= 0

    detail = api_client.get(f"/api/captures/{body['capture_id']}").json()
    assert detail["capture"]["source_kind"] == "replay"
    assert detail["capture"]["detect_ms"] is not None
    assert detail["capture"]["status"] == "ok"
    assert detail["detections"][0]["source_kind"] == "replay"

    stats = api_client.get("/api/status").json()["pipeline"]["stats"]
    assert stats["captures_by_source"].get("replay", 0) >= 1


def test_replay_demo_run_passes_replay_items_but_not_device(api_client):
    run = start_run(api_client, "replay_demo")
    for _ in range(2):
        assert api_client.post("/api/capture").status_code == 200
    query = api_client.post("/api/query", json={"text": "杯子在哪？"})
    assert query.status_code == 200
    assert query.json()["status"] == "found"
    finished = finish_run(api_client, run["id"])

    overview = finished["overview"]
    items = item_map(overview)
    assert overview["simulated"] is True
    assert "回放演示" in overview["banner"]
    assert items["device_connection"]["status"] == NOT_VERIFIED
    for key in ("capture", "detection", "storage", "track_link", "query"):
        assert items[key]["status"] == PASS, (key, items[key])
    assert overview["status"] == NOT_VERIFIED
    assert overview["counts"] == {"pass": 5, "fail": 0, "not_verified": 1}

    # 每项 PASS 必须至少带一条可核验证据
    for key in ("capture", "detection", "storage", "track_link", "query"):
        assert items[key]["evidence"], key


def test_real_device_mode_never_passes_replay_data(api_client):
    run = start_run(api_client, "real_device")
    for _ in range(2):
        assert api_client.post("/api/capture").status_code == 200
    assert api_client.post("/api/query", json={"text": "杯子在哪？"}).status_code == 200
    finished = finish_run(api_client, run["id"])
    overview = finished["overview"]
    items = item_map(overview)

    assert overview["simulated"] is False
    assert overview["status"] == NOT_VERIFIED
    assert all(item["status"] == NOT_VERIFIED for item in overview["items"])
    assert any("非真实设备" in w for w in overview["warnings"])


def test_start_conflict_and_finish_idempotent(api_client):
    run = start_run(api_client)
    conflict = api_client.post("/api/acceptance/run/start", json={"mode": "replay_demo"})
    assert conflict.status_code == 409
    assert conflict.json()["ok"] is False

    first = finish_run(api_client, run["id"])
    assert first["run"]["status"] == "finished"
    second = finish_run(api_client, run["id"])
    assert second["run"]["status"] == "finished"
    assert second["run"]["finished_at_utc"] == first["run"]["finished_at_utc"]
    assert second["overview"]["status"] == first["overview"]["status"]


def test_export_is_sanitized(api_client):
    run = start_run(api_client, "replay_demo")
    api_client.post("/api/capture")
    finish_run(api_client, run["id"])
    resp = api_client.get(f"/api/acceptance/run/{run['id']}/export")
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    text = resp.content.decode("utf-8")
    payload = json.loads(text)
    assert payload["run"]["id"] == run["id"]
    assert "privacy_note" in payload
    assert "events" in payload and payload["events"]
    assert str(REPO_ROOT) not in text
    assert "<device-ip>" not in text  # 本轮全是回放，不应出现设备地址


def test_probe_without_url_in_replay_is_rejected(api_client):
    resp = api_client.post("/api/device/probe", json={})
    assert resp.status_code == 400
    assert "图片回放" in resp.json()["detail"]


def test_device_probe_and_connect_runtime(api_client, monkeypatch):
    def fake_probe(self):
        return {
            "device": "ESP32-S3-EYE",
            "firmware": "Findy M1",
            "wifi": {"configured": True, "connected": True, "ip": "10.0.0.5", "rssi": -42},
            "time": {"synced": True, "local": "2026-10-29 10:00:00", "utc": "2026-10-29T02:00:00Z"},
            "camera": {"ready": True, "sensor": "OV2640", "width": 800, "height": 600},
            "stats": {"total": 3, "ok": 3, "fail": 0},
        }

    monkeypatch.setattr(Esp32Source, "probe", fake_probe)
    run = start_run(api_client, "real_device")

    probe = api_client.post("/api/device/probe", json={"base_url": "10.0.0.5"})
    assert probe.status_code == 200
    assert probe.json()["device"]["camera"]["ready"] is True
    overview = api_client.get("/api/acceptance").json()["overview"]
    assert item_map(overview)["device_connection"]["status"] == PASS

    connect = api_client.post("/api/device/connect", json={"base_url": "10.0.0.5"})
    assert connect.status_code == 200
    assert connect.json()["source"]["type"] == "esp32"
    status = api_client.get("/api/status").json()
    assert status["source"]["type"] == "esp32"
    assert status["source"]["runtime_override"] is True

    reset = api_client.post("/api/source/reset")
    assert reset.status_code == 200
    assert api_client.get("/api/status").json()["source"]["type"] == "replay"
    finish_run(api_client, run["id"])


def test_device_probe_failure_marks_device_fail(api_client, monkeypatch):
    def broken_probe(self):
        raise SourceError("无法连接设备")

    monkeypatch.setattr(Esp32Source, "probe", broken_probe)
    run = start_run(api_client, "real_device")
    resp = api_client.post("/api/device/probe", json={"base_url": "http://10.0.0.9"})
    assert resp.status_code == 503
    assert resp.json()["ok"] is False
    overview = api_client.get("/api/acceptance").json()["overview"]
    assert item_map(overview)["device_connection"]["status"] == FAIL
    assert overview["status"] == FAIL
    finish_run(api_client, run["id"])


def test_query_failure_is_recorded_as_fail(api_client, monkeypatch):
    run = start_run(api_client, "replay_demo")
    monkeypatch.setattr("findy.api.answer_query", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("query boom")))
    resp = api_client.post("/api/query", json={"text": "杯子在哪？"})
    assert resp.status_code == 500
    overview = api_client.get("/api/acceptance").json()["overview"]
    assert item_map(overview)["query"]["status"] == FAIL
    finish_run(api_client, run["id"])


def test_detection_failure_reason_is_visible_and_fails(api_client, monkeypatch):
    pipeline = api_client.app.state.pipeline

    def boom(image):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(pipeline.detector, "detect", boom)
    run = start_run(api_client, "replay_demo")
    resp = api_client.post("/api/capture")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ok"] is False
    assert "检测失败" in body["error"]
    capture_id = body["capture"]["id"]
    detail = api_client.get(f"/api/captures/{capture_id}").json()
    assert detail["capture"]["status"] == "detect_failed"
    assert "model crashed" in (detail["capture"]["detect_error"] or "")

    overview = finish_run(api_client, run["id"])["overview"]
    items = item_map(overview)
    assert items["capture"]["status"] == PASS  # 原图抓拍成功
    assert items["detection"]["status"] == FAIL
    assert "model crashed" in items["detection"]["reason"]
    assert overview["status"] == FAIL


def test_track_detail_has_link_evidence_and_sources(api_client):
    for _ in range(2):
        api_client.post("/api/capture")
    objects = api_client.get("/api/objects").json()["objects"]
    assert objects
    track = max(objects, key=lambda o: int(o.get("sightings") or 0))
    detail = api_client.get(f"/api/tracks/{track['track_id']}").json()
    assert detail["ok"] is True
    assert detail["track"]["source_kinds"] == ["replay"]
    assert detail["track"]["mixed_sources"] is False
    assert detail["detections"]
    for det in detail["detections"]:
        assert det["source_kind"] == "replay"
        assert det["link_score"] is not None
        assert "candidates" in det


def test_source_kind_backfill_does_not_override(tmp_path):
    db = Database(tmp_path / "legacy.sqlite")
    db.init_schema()
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    base = {
        "camera_id": 1,
        "device_seq": None,
        "captured_at_utc": "2026-10-28T02:00:00Z",
        "captured_at_local": "2026-10-28 10:00:00",
        "epoch_s": 1.0,
        "time_synced": 1,
        "uptime_ms": 1,
        "received_at_utc": "2026-10-28T02:00:01Z",
        "file_path": "data/images/x.jpg",
        "image_width": 320,
        "image_height": 240,
        "image_bytes": 10,
        "sha256": "abc",
        "source_ref": "legacy",
        "status": "ok",
    }
    old_id, _ = db.add_capture({**base, "time_source": "file_mtime"})
    explicit_id, _ = db.add_capture({**base, "time_source": "file_mtime", "source_kind": "esp32"})

    db.init_schema()  # 再次初始化触发回填

    assert db.get_capture(old_id)["source_kind"] == "replay"
    assert db.get_capture(explicit_id)["source_kind"] == "esp32"