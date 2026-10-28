import io

from PIL import Image


def test_status_endpoint(api_client):
    r = api_client.get("/api/status")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["source"]["type"] == "replay"
    assert data["config"]["detector"] == "mock"
    assert isinstance(data["classes"], list) and data["classes"]


def test_capture_replay_and_image(api_client):
    r = api_client.post("/api/capture")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["capture_id"] == 1
    assert len(data["detections"]) == 2
    assert data["capture"]["time_synced"] is True

    img = api_client.get(f"/api/captures/{data['capture_id']}/image")
    assert img.status_code == 200
    assert img.headers["content-type"] == "image/jpeg"
    assert img.content.startswith(b"\xff\xd8")

    thumb = api_client.get(f"/api/captures/{data['capture_id']}/image?thumb=1")
    assert thumb.status_code == 200

    det = data["detections"][0]
    crop = api_client.get(det["crop_url"])
    assert crop.status_code == 200


def test_captures_list_and_detail(api_client):
    api_client.post("/api/capture")
    r = api_client.get("/api/captures?limit=5")
    assert r.status_code == 200
    assert len(r.json()["captures"]) == 1
    detail = api_client.get("/api/captures/1")
    assert detail.status_code == 200
    assert len(detail.json()["detections"]) == 2
    assert api_client.get("/api/captures/999").status_code == 404


def test_query_endpoint(api_client):
    api_client.post("/api/capture")
    r = api_client.post("/api/query", json={"text": "杯子在哪？"})
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "found"
    assert "桌面左侧" in data["answer"]
    assert data["parsed"]["class_zh"] == "杯子"

    empty = api_client.post("/api/query", json={"text": ""})
    assert empty.status_code == 422


def test_objects_and_track_endpoints(api_client):
    api_client.post("/api/capture")
    objects = api_client.get("/api/objects")
    assert objects.status_code == 200
    items = objects.json()["objects"]
    assert len(items) == 2
    track_id = items[0]["track_id"]
    detail = api_client.get(f"/api/tracks/{track_id}")
    assert detail.status_code == 200
    label = api_client.post(f"/api/tracks/{track_id}/label", json={"label": "我的杯子"})
    assert label.status_code == 200
    assert api_client.get(f"/api/tracks/{track_id}").json()["track"]["label"] == "我的杯子"


def test_upload_observe_endpoint(api_client):
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (120, 40, 40)).save(buf, format="JPEG")
    r = api_client.post(
        "/api/observe",
        files={"file": ("frame.jpg", buf.getvalue(), "image/jpeg")},
        data={"captured_at_utc": "2026-10-28T03:00:00Z"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    # 上传未提供本地时间，但 UTC 时间已给出
    assert data["capture"]["time_synced"] is True

    bad = api_client.post(
        "/api/observe",
        files={"file": ("bad.jpg", b"not-a-jpeg", "image/jpeg")},
    )
    assert bad.status_code == 400


def test_service_start_stop(api_client):
    start = api_client.post("/api/service/start")
    assert start.status_code == 200 and start.json()["ok"] is True
    stop = api_client.post("/api/service/stop")
    assert stop.status_code == 200 and stop.json()["ok"] is True


def test_health_and_index(api_client):
    health = api_client.get("/api/health")
    assert health.status_code == 200 and health.json()["db"] is True
    index = api_client.get("/")
    assert index.status_code == 200
    assert "Findy" in index.text