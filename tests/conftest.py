"""pytest 共享 fixture：不依赖真实模型，全部使用 MockDetector + HashEmbedder。"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from findy.classes import load_catalog  # noqa: E402
from findy.config import Config  # noqa: E402
from findy.db import Database  # noqa: E402
from findy.detector import MockDetector  # noqa: E402
from findy.embedder import HashEmbedder  # noqa: E402
from findy.pipeline import FindyPipeline  # noqa: E402
from findy.zones import load_regions  # noqa: E402

CATALOG_PATH = REPO_ROOT / "config" / "objects.yaml"
ZONES_PATH = REPO_ROOT / "config" / "zones.yaml"

# 一个杯子的 bbox：中心在画面左侧 (x≈0.2)，落在「桌面左侧」区域
CUP_BBOX = [20.0, 100.0, 100.0, 190.0]
PHONE_BBOX = [180.0, 100.0, 230.0, 190.0]  # 中心 x≈0.64 → 桌面中央


def make_image(color=(90, 110, 130), draw: list[dict] | None = None, size=(320, 240)) -> bytes:
    im = Image.new("RGB", size, (30, 30, 34))
    d = ImageDraw.Draw(im)
    for item in draw or []:
        d.rectangle(item["box"], fill=item.get("fill", color))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


@pytest.fixture()
def catalog():
    return load_catalog(CATALOG_PATH)


@pytest.fixture()
def regions():
    return load_regions(ZONES_PATH)


@pytest.fixture()
def config(tmp_path):
    cfg = Config()
    cfg.app.data_dir = str(tmp_path / "data")
    cfg.app.db_path = str(tmp_path / "data" / "findy.sqlite")
    cfg.app.images_dir = str(tmp_path / "data" / "images")
    cfg.app.crops_dir = str(tmp_path / "data" / "crops")
    cfg.detector.backend = "mock"
    cfg.embedder.backend = "hash"
    cfg.capture.source = "replay"
    cfg.capture.replay.dir = str(tmp_path / "frames")
    return cfg


@pytest.fixture()
def db(config):
    database = Database(config.db_path)
    database.init_schema()
    return database


@pytest.fixture()
def pipeline(config, db, catalog, regions):
    annotations = [
        {"class_zh": "杯子", "confidence": 0.9, "bbox_px": CUP_BBOX},
        {"class_zh": "手机", "confidence": 0.85, "bbox_px": PHONE_BBOX},
    ]
    detector = MockDetector(catalog, annotations)
    pipe = FindyPipeline(config, db, catalog, detector, HashEmbedder(), regions)
    pipe.initialize()
    return pipe


@pytest.fixture()
def api_config(tmp_path, catalog):
    """供 create_app 使用的临时 YAML 配置（图片回放 + mock 检测）。"""
    frames = tmp_path / "frames"
    frames.mkdir(parents=True, exist_ok=True)
    for i, stamp in enumerate(["2026-10-28T10-00-00", "2026-10-28T10-05-00"]):
        data = make_image(draw=[{"box": CUP_BBOX, "fill": (160, 60, 50)}])
        (frames / f"{stamp}_frame.jpg").write_bytes(data)

    cfg_text = f"""
app:
  data_dir: "{tmp_path.as_posix()}/data"
  db_path: "{tmp_path.as_posix()}/data/findy.sqlite"
  images_dir: "{tmp_path.as_posix()}/data/images"
  crops_dir: "{tmp_path.as_posix()}/data/crops"
  tz: Asia/Shanghai
  host: 127.0.0.1
  port: 8765
capture:
  source: replay
  interval_seconds: 30
  replay:
    dir: "{frames.as_posix()}"
    loop: false
detector:
  backend: mock
  model: mock
embedder:
  backend: hash
  model: hash
matching:
  accept_threshold: 0.82
  uncertain_threshold: 0.70
files:
  objects: "{CATALOG_PATH.as_posix()}"
  zones: "{ZONES_PATH.as_posix()}"
"""
    path = tmp_path / "findy_test.yaml"
    path.write_text(cfg_text, encoding="utf-8")
    return path


@pytest.fixture()
def api_client(api_config, monkeypatch):
    monkeypatch.setenv(
        "FINDY_MOCK_ANNOTATIONS",
        json.dumps(
            [
                {"class_zh": "杯子", "confidence": 0.9, "bbox_px": CUP_BBOX},
                {"class_zh": "手机", "confidence": 0.8, "bbox_px": PHONE_BBOX},
            ],
            ensure_ascii=False,
        ),
    )
    from fastapi.testclient import TestClient

    from findy.api import create_app

    app = create_app(str(api_config))
    with TestClient(app) as client:
        yield client