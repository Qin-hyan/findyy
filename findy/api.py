"""FastAPI 应用：HTTP API + 单页界面。"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .classes import load_catalog
from .config import REPO_ROOT, Config, load_config
from .db import Database
from .detector import MockDetector, Owlv2Detector
from .embedder import create_embedder
from .pipeline import FindyPipeline
from .query import answer as answer_query
from .query import parse_query
from .service import AutoCaptureService
from .sources import CaptureMeta
from .util import to_iso, utc_now
from .zones import load_regions

log = logging.getLogger(__name__)
WEB_DIR = REPO_ROOT / "web"
THUMB_DIR = REPO_ROOT / "data" / "cache" / "thumbs"


class QueryRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=200)


class LabelRequest(BaseModel):
    label: str = Field(..., min_length=1, max_length=40)


class MergeRequest(BaseModel):
    source_track_id: int
    target_track_id: int


class FeedbackRequest(BaseModel):
    action: str
    detection_id: int | None = None
    track_id: int | None = None
    payload: dict | None = None


def create_app(config_path: str | None = None) -> FastAPI:
    cfg = load_config(config_path)
    cfg.ensure_dirs()
    catalog = load_catalog(cfg.objects_file)
    regions = load_regions(cfg.zones_file)
    db = Database(cfg.db_path)

    if cfg.detector.backend == "mock":
        annotations = None
        raw_annotations = os.environ.get("FINDY_MOCK_ANNOTATIONS")
        if raw_annotations:
            try:
                annotations = json.loads(raw_annotations)
            except json.JSONDecodeError:
                log.warning("FINDY_MOCK_ANNOTATIONS 不是合法 JSON，按空注释处理")
        detector = MockDetector(catalog, annotations)
    elif cfg.detector.backend in {"owlv2", "auto"}:
        detector = Owlv2Detector(cfg.detector, catalog, REPO_ROOT)
    else:
        raise ValueError(f"未知检测后端: {cfg.detector.backend}")
    embedder = create_embedder(cfg.embedder, REPO_ROOT)

    pipeline = FindyPipeline(cfg, db, catalog, detector, embedder, regions)
    pipeline.initialize()
    service = AutoCaptureService(pipeline, cfg.capture.interval_seconds)

    app = FastAPI(title="Findy 物品记忆助手", version="0.1.0")
    app.state.cfg = cfg
    app.state.catalog = catalog
    app.state.regions = regions
    app.state.db = db
    app.state.pipeline = pipeline
    app.state.service = service
    app.state.warmup_done = threading.Event()
    app.state.warmup_error = None

    def _warmup() -> None:
        try:
            pipeline.warmup()
        finally:
            app.state.warmup_done.set()

    @app.on_event("startup")
    def _startup() -> None:
        threading.Thread(target=_warmup, name="findy-model-warmup", daemon=True).start()
        THUMB_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------- 页面与静态资源 ----------------
    if (WEB_DIR / "static").exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

    @app.get("/")
    def index():
        page = WEB_DIR / "index.html"
        if not page.exists():
            return JSONResponse({"ok": False, "error": "web/index.html 不存在"}, status_code=500)
        return FileResponse(page, media_type="text/html; charset=utf-8")

    # ---------------- 状态 ----------------
    @app.get("/api/health")
    def health():
        return {"ok": True, "db": db.ping(), "time": to_iso(utc_now())}

    @app.get("/api/status")
    def status():
        return {
            "ok": True,
            "app": {"name": "Findy", "version": "0.1.0", "time": to_iso(utc_now())},
            "config": cfg.public_dict(),
            "pipeline": pipeline.status(),
            "service": service.state.to_dict(),
            "source": {
                "type": cfg.capture.source,
                "esp32_url": cfg.capture.esp32.base_url if cfg.capture.source == "esp32" else None,
                "replay_remaining": _replay_remaining(service),
            },
            "classes": [
                {"zh": c.zh, "en": c.en, "threshold": c.threshold, "context_only": c.context_only}
                for c in catalog.classes
            ],
            "zones": [{"name": r.name, "kind": r.kind} for r in regions if len(r.polygon) >= 3],
            "examples": catalog.example_queries,
            "warmup_done": app.state.warmup_done.is_set(),
        }

    # ---------------- 抓拍 ----------------
    @app.post("/api/capture")
    def capture():
        result = service.capture_once()
        if not result.ok:
            return JSONResponse(
                {"ok": False, "error": result.error, "capture": result.capture}, status_code=503
            )
        return result.to_dict()

    @app.post("/api/observe")
    async def observe(
        file: UploadFile = File(...),
        captured_at_utc: str | None = Form(None),
        captured_at_local: str | None = Form(None),
    ):
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="上传文件为空")
        if len(data) > 20 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="图片超过 20MB 限制")
        synced = bool(captured_at_utc)
        meta = CaptureMeta(
            source="upload",
            source_ref=file.filename or "upload",
            camera_name="upload",
            time_synced=synced,
            time_source="client" if synced else "client_unsynced",
            captured_at_utc=captured_at_utc,
            captured_at_local=captured_at_local,
            epoch_s=None,
        )
        try:
            result = pipeline.observe(data, meta)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"图片无效: {exc}")
        return result.to_dict()

    # ---------------- 查询 ----------------
    @app.post("/api/query")
    def query(req: QueryRequest):
        text = req.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="查询不能为空")
        return answer_query(db, cfg, catalog, regions, text)

    @app.get("/api/query/parse")
    def parse(text: str = Query(..., min_length=1, max_length=200)):
        return parse_query(text, catalog, regions, cfg.app.tz).to_dict()

    # ---------------- 物品与历史 ----------------
    @app.get("/api/objects")
    def objects(limit: int = 100, status: str = "active"):
        rows = db.list_tracks(status=status, limit=limit)
        out = []
        for track in rows:
            dets = db.detections_for_track(int(track["id"]), limit=1)
            last = dets[0] if dets else None
            from .query import _result_from_track

            out.append(_result_from_track(db, cfg, track, last) if last else {
                "track_id": track["id"], "label": track.get("label") or track.get("name_zh"),
                "class_zh": track.get("name_zh"), "zone": track.get("last_region_name") or "未分区",
                "time_local": None, "time_synced": False, "sightings": 0,
            })
        return {"ok": True, "objects": out}

    @app.get("/api/tracks/{track_id}")
    def track_detail(track_id: int):
        track = db.get_track(track_id)
        if track is None:
            raise HTTPException(status_code=404, detail="物品不存在")
        dets = db.detections_for_track(track_id, limit=50)
        return {
            "ok": True,
            "track": {
                "id": track["id"],
                "label": track.get("label"),
                "class_zh": track.get("name_zh"),
                "color": track.get("color"),
                "status": track.get("status"),
                "first_seen_utc": track.get("first_seen_utc"),
                "last_seen_utc": track.get("last_seen_utc"),
                "sightings": db.track_sighting_count(track_id),
                "region_history": db.track_region_history(track_id),
            },
            "detections": [
                {
                    "detection_id": d["id"],
                    "capture_id": d["capture_id"],
                    "time_local": d.get("captured_at_local"),
                    "time_utc": d.get("captured_at_utc"),
                    "time_synced": bool(d.get("time_synced")),
                    "zone": d.get("region_name"),
                    "confidence": d.get("conf"),
                    "link_score": d.get("link_score"),
                    "link_status": d.get("link_status"),
                    "bbox_norm": [float(v) for v in str(d.get("bbox_norm") or "0,0,1,1").split(",")],
                    "image_url": f"/api/captures/{d['capture_id']}/image",
                    "crop_url": f"/api/detections/{d['id']}/crop",
                }
                for d in dets
            ],
        }

    @app.post("/api/tracks/{track_id}/label")
    def set_label(track_id: int, req: LabelRequest):
        if db.get_track(track_id) is None:
            raise HTTPException(status_code=404, detail="物品不存在")
        db.update_track_label(track_id, req.label.strip())
        return {"ok": True, "track_id": track_id, "label": req.label.strip()}

    @app.post("/api/tracks/merge")
    def merge_tracks(req: MergeRequest):
        if db.get_track(req.source_track_id) is None or db.get_track(req.target_track_id) is None:
            raise HTTPException(status_code=404, detail="物品不存在")
        db.merge_tracks(req.source_track_id, req.target_track_id)
        db.add_feedback(None, req.target_track_id, "confirm", {"merged_from": req.source_track_id})
        return {"ok": True, "target_track_id": req.target_track_id}

    @app.post("/api/feedback")
    def feedback(req: FeedbackRequest):
        if req.action not in {"confirm", "wrong_object", "wrong_region"}:
            raise HTTPException(status_code=400, detail="未知反馈类型")
        fid = db.add_feedback(req.detection_id, req.track_id, req.action, req.payload)
        return {"ok": True, "feedback_id": fid}

    @app.get("/api/queries")
    def queries(limit: int = 10):
        rows = db.recent_queries(limit)
        for row in rows:
            row.pop("plan_json", None)
        return {"ok": True, "queries": rows}

    @app.get("/api/captures")
    def captures(limit: int = 20):
        rows = db.list_captures(limit)
        return {
            "ok": True,
            "captures": [
                {
                    "id": r["id"],
                    "captured_at_utc": r.get("captured_at_utc"),
                    "captured_at_local": r.get("captured_at_local"),
                    "time_synced": bool(r.get("time_synced")),
                    "time_source": r.get("time_source"),
                    "detections_count": r.get("det_count", r.get("detections_count")),
                    "image_url": f"/api/captures/{r['id']}/image",
                    "thumbnail_url": f"/api/captures/{r['id']}/image?thumb=1",
                    "status": r.get("status"),
                }
                for r in rows
            ],
        }

    @app.get("/api/captures/{capture_id}")
    def capture_detail(capture_id: int):
        row = db.get_capture(capture_id)
        if row is None:
            raise HTTPException(status_code=404, detail="抓拍不存在")
        dets = db.detections_for_capture(capture_id)
        return {
            "ok": True,
            "capture": {
                "id": row["id"],
                "captured_at_utc": row.get("captured_at_utc"),
                "captured_at_local": row.get("captured_at_local"),
                "time_synced": bool(row.get("time_synced")),
                "time_source": row.get("time_source"),
                "width": row.get("image_width"),
                "height": row.get("image_height"),
                "status": row.get("status"),
                "image_url": f"/api/captures/{capture_id}/image",
            },
            "detections": [
                {
                    "detection_id": d["id"],
                    "track_id": d.get("track_id"),
                    "class_zh": d.get("name_zh"),
                    "confidence": d.get("conf"),
                    "bbox_norm": [float(v) for v in str(d.get("bbox_norm") or "0,0,1,1").split(",")],
                    "region": d.get("region_name"),
                    "link_status": d.get("link_status"),
                    "link_score": d.get("link_score"),
                    "crop_url": f"/api/detections/{d['id']}/crop",
                }
                for d in dets
            ],
        }

    # ---------------- 图像 ----------------
    @app.get("/api/captures/{capture_id}/image")
    def capture_image(capture_id: int, thumb: int = 0):
        row = db.get_capture(capture_id)
        if row is None:
            raise HTTPException(status_code=404, detail="抓拍不存在")
        path = Path(row["file_path"])
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            raise HTTPException(status_code=404, detail="图像文件已被清理")
        if thumb:
            cache = THUMB_DIR / f"{capture_id}.jpg"
            if not cache.exists():
                try:
                    from PIL import Image

                    with Image.open(path) as im:
                        im.thumbnail((480, 480))
                        cache.parent.mkdir(parents=True, exist_ok=True)
                        im.convert("RGB").save(cache, format="JPEG", quality=82)
                except Exception:
                    return FileResponse(path, media_type="image/jpeg")
            return FileResponse(cache, media_type="image/jpeg")
        return FileResponse(path, media_type="image/jpeg")

    @app.get("/api/detections/{detection_id}/crop")
    def detection_crop(detection_id: int):
        with db.connect() as conn:
            row = conn.execute("SELECT crop_path FROM detections WHERE id=?", (detection_id,)).fetchone()
        if row is None or not row["crop_path"]:
            raise HTTPException(status_code=404, detail="裁剪图不存在")
        path = Path(row["crop_path"])
        if not path.is_absolute():
            path = REPO_ROOT / path
        if not path.exists():
            raise HTTPException(status_code=404, detail="裁剪图文件已被清理")
        return FileResponse(path, media_type="image/jpeg")

    # ---------------- 自动采集控制 ----------------
    @app.post("/api/service/start")
    def service_start():
        if cfg.capture.source == "replay":
            service.source()
        started = service.start()
        return {"ok": True, "started": started, "service": service.state.to_dict()}

    @app.post("/api/service/stop")
    def service_stop():
        stopped = service.stop()
        return {"ok": True, "stopped": stopped, "service": service.state.to_dict()}

    return app


def _replay_remaining(service: AutoCaptureService) -> int | None:
    try:
        src = service.source()
        remaining = getattr(src, "remaining", None)
        return int(remaining()) if callable(remaining) else None
    except Exception:
        return None