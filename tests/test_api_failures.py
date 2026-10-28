"""API 异常路径：采集源不可用、未知路由等。"""

from pathlib import Path

from fastapi.testclient import TestClient

from findy.api import create_app

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_capture_returns_503_when_source_unavailable(tmp_path):
    """回放目录为空：抓拍必须返回 503 与明确原因，而不是静默成功。"""
    empty_dir = tmp_path / "empty_frames"
    empty_dir.mkdir()
    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        f"""
app:
  data_dir: "{tmp_path.as_posix()}/data"
  db_path: "{tmp_path.as_posix()}/data/f.sqlite"
  images_dir: "{tmp_path.as_posix()}/data/images"
  crops_dir: "{tmp_path.as_posix()}/data/crops"
capture:
  source: replay
  replay:
    dir: "{empty_dir.as_posix()}"
detector:
  backend: mock
  model: mock
embedder:
  backend: hash
  model: hash
files:
  objects: "{(REPO_ROOT / 'config/objects.yaml').as_posix()}"
  zones: "{(REPO_ROOT / 'config/zones.yaml').as_posix()}"
""",
        encoding="utf-8",
    )
    with TestClient(create_app(str(cfg))) as client:
        resp = client.post("/api/capture")
        assert resp.status_code == 503
        body = resp.json()
        assert body["ok"] is False
        assert "回放目录" in body["error"] or "图片" in body["error"]


def test_unknown_routes_return_404(api_client):
    assert api_client.get("/api/nope").status_code == 404
    assert api_client.get("/api/detections/999/crop").status_code == 404
    assert api_client.post("/api/query", json={"text": "x" * 300}).status_code == 422