"""FastAPI 应用：HTTP API + 单页界面。"""

from __future__ import annotations

import io
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .acceptance import (
    EVALUATOR_VERSION,
    AcceptanceRecorder,
    build_export,
    evaluate_run,
    normalize_base_url,
    public_run,
    summarize_device_status,
)
from .classes import load_catalog
from .config import REPO_ROOT, Config, load_config
from .db import Database
from .detector import MockDetector, Owlv2Detector
from .embedder import create_embedder
from .pipeline import FindyPipeline
from .query import answer as answer_query
from .query import parse_query
from .service import AutoCaptureService
from .sources import CaptureMeta, Esp32Source, SourceError
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


class ProbeRequest(BaseModel):
    base_url: str | None = Field(default=None, max_length=250)


class ConnectRequest(BaseModel):
    base_url: str = Field(..., min_length=1, max_length=250)


class AcceptanceStartRequest(BaseModel):
    mode: Literal["real_device", "replay_demo"]


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
    recorder = AcceptanceRecorder(db, cfg)
    service.on_result = recorder.record_capture
    # 启动时配置文件里的采集源（用于“恢复配置采集源”，会话级切换不改文件）
    original_capture = {
        "source": cfg.capture.source,
        "esp32_url": cfg.capture.esp32.base_url,
    }

    app = FastAPI(title="Findy 物品记忆助手", version="0.1.0")
    app.state.cfg = cfg
    app.state.catalog = catalog
    app.state.regions = regions
    app.state.db = db
    app.state.pipeline = pipeline
    app.state.service = service
    app.state.recorder = recorder
    app.state.original_capture = original_capture
    app.state.last_probe = None
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

    def _static_page(filename: str, label: str):
        page = WEB_DIR / filename
        if not page.exists():
            return JSONResponse(
                {"ok": False, "error": f"{label}页面文件不存在（{filename}）"},
                status_code=500,
            )
        return FileResponse(page, media_type="text/html; charset=utf-8")

    @app.get("/observe")
    def observe_page():
        return _static_page("index.html", "最近观察")

    @app.get("/search")
    def search_page():
        return _static_page("search.html", "找找物品")

    @app.get("/items")
    def items_page():
        return _static_page("items.html", "我的物品")

    @app.get("/timeline")
    def timeline_page():
        return _static_page("timeline.html", "观察时间线")

    @app.get("/workbench")
    def workbench():
        page = WEB_DIR / "workbench.html"
        if not page.exists():
            return JSONResponse(
                {"ok": False, "error": "web/workbench.html 不存在（工作台尚未部署）"},
                status_code=500,
            )
        return FileResponse(page, media_type="text/html; charset=utf-8")

    # ---------------- 状态 ----------------
    @app.get("/api/health")
    def health():
        return {"ok": True, "db": db.ping(), "time": to_iso(utc_now())}

    @app.get("/api/status")
    def status():
        pipe = pipeline.status()
        runtime_override = (
            cfg.capture.source != original_capture["source"]
            or cfg.capture.esp32.base_url != original_capture["esp32_url"]
        )
        return {
            "ok": True,
            "app": {"name": "Findy", "version": "0.1.0", "time": to_iso(utc_now())},
            "config": cfg.public_dict(),
            "pipeline": pipe,
            "service": service.state.to_dict(),
            "source": {
                "type": cfg.capture.source,
                "configured_type": original_capture["source"],
                "runtime_override": runtime_override,
                "esp32_url": cfg.capture.esp32.base_url if cfg.capture.source == "esp32" else None,
                "configured_esp32_url": original_capture["esp32_url"],
                "replay_remaining": _replay_remaining(service),
                "provenance": (pipe.get("stats") or {}).get("captures_by_source") or {},
            },
            "device": {
                "configured_url": cfg.capture.esp32.base_url,
                "last_probe": app.state.last_probe,
            },
            "limits": {
                "capture_timeout_seconds": 240,
                "model_latency_note": "OWLv2 CPU 单帧检测约 6.2–10.6 秒，属正常速度",
                "auto_interval_seconds": cfg.capture.interval_seconds,
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
        started = time.perf_counter()
        result = service.capture_once()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        try:
            recorder.record_capture(result, elapsed_ms)
        except Exception:
            log.exception("写入验收事件失败")
        if not result.ok:
            return JSONResponse(
                {
                    "ok": False,
                    "error": result.error,
                    "capture": result.capture,
                    "elapsed_ms": elapsed_ms,
                },
                status_code=503,
            )
        payload = result.to_dict()
        payload["elapsed_ms"] = elapsed_ms
        return payload

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
        try:
            payload = answer_query(db, cfg, catalog, regions, text)
        except Exception as exc:
            log.exception("查询失败")
            try:
                recorder.record_query_failure(text, f"{type(exc).__name__}: {exc}")
            except Exception:
                log.exception("写入查询失败验收事件失败")
            raise HTTPException(status_code=500, detail=f"查询失败: {type(exc).__name__}: {exc}")
        try:
            recorder.record_query(payload)
        except Exception:
            log.exception("写入查询验收事件失败")
        return payload

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
        det_rows = []
        for d in dets:
            row = {
                "detection_id": d["id"],
                "capture_id": d["capture_id"],
                "time_local": d.get("captured_at_local"),
                "time_utc": d.get("captured_at_utc"),
                "time_synced": bool(d.get("time_synced")),
                "zone": d.get("region_name"),
                "confidence": d.get("conf"),
                "link_score": d.get("link_score"),
                "link_status": d.get("link_status"),
                "source_kind": d.get("source_kind") or "unknown",
                "bbox_norm": [float(v) for v in str(d.get("bbox_norm") or "0,0,1,1").split(",")],
                "image_url": f"/api/captures/{d['capture_id']}/image",
                "crop_url": f"/api/detections/{d['id']}/crop",
                "candidates": db.link_candidates(d["id"])
                if d.get("link_status") == "ambiguous"
                else [],
            }
            det_rows.append(row)
        source_kinds = sorted({str(r["source_kind"]) for r in det_rows})
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
                "source_kinds": source_kinds,
                "mixed_sources": len(source_kinds) > 1,
            },
            "detections": det_rows,
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
                    "source_kind": r.get("source_kind") or "unknown",
                    "device_seq": r.get("device_seq"),
                    "device_seq_raw": r.get("device_seq_raw"),
                    "detect_ms": r.get("detect_ms"),
                    "process_ms": r.get("process_ms"),
                    "detect_error": r.get("detect_error"),
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
                "source_kind": row.get("source_kind") or "unknown",
                "source_ref": row.get("source_ref"),
                "device_seq": row.get("device_seq"),
                "device_seq_raw": row.get("device_seq_raw"),
                "detect_ms": row.get("detect_ms"),
                "embed_ms": row.get("embed_ms"),
                "process_ms": row.get("process_ms"),
                "detect_error": row.get("detect_error"),
                "image_url": f"/api/captures/{capture_id}/image",
                "thumbnail_url": f"/api/captures/{capture_id}/image?thumb=1",
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
                    "link_method": d.get("link_method"),
                    "source_kind": d.get("source_kind") or "unknown",
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
        try:
            recorder.record_service("service_start", service.state.to_dict())
        except Exception:
            log.exception("写入自动采集启动验收事件失败")
        return {"ok": True, "started": started, "service": service.state.to_dict()}

    @app.post("/api/service/stop")
    def service_stop():
        stopped = service.stop()
        try:
            recorder.record_service("service_stop", service.state.to_dict())
        except Exception:
            log.exception("写入自动采集停止验收事件失败")
        return {"ok": True, "stopped": stopped, "service": service.state.to_dict()}

    # ---------------- 真实设备探测 / 会话级切换 ----------------
    def _probe_device(url: str) -> dict:
        return Esp32Source(url, cfg.capture.esp32.timeout_seconds).probe()

    def _last_probe(ok: bool, url: str, summary: dict | None, error: str | None) -> dict:
        current = {
            "ok": bool(ok),
            "at": to_iso(utc_now()),
            "url": url,
            "summary": summary,
            "error": error,
        }
        app.state.last_probe = current
        return current

    @app.post("/api/device/probe")
    def device_probe(req: ProbeRequest):
        if req.base_url:
            try:
                url = normalize_base_url(req.base_url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))
        elif cfg.capture.source != "esp32":
            raise HTTPException(
                status_code=400,
                detail=(
                    "当前采集源为图片回放（replay），没有可检查的真实设备。"
                    "请输入 ESP32 设备地址（例如 http://<设备IP>）后再检查连接，"
                    "或按页面“操作引导”配置 config/findy.local.yaml。"
                ),
            )
        else:
            try:
                url = normalize_base_url(cfg.capture.esp32.base_url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=f"配置的设备地址无效: {exc}")

        try:
            raw = _probe_device(url)
        except SourceError as exc:
            probe = _last_probe(False, url, None, str(exc))
            try:
                recorder.record_probe(False, url, None, str(exc))
            except Exception:
                log.exception("写入设备探测失败验收事件失败")
            return JSONResponse({"ok": False, "error": str(exc), "probe": probe}, status_code=503)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            probe = _last_probe(False, url, None, error)
            try:
                recorder.record_probe(False, url, None, error)
            except Exception:
                log.exception("写入设备探测失败验收事件失败")
            return JSONResponse({"ok": False, "error": error, "probe": probe}, status_code=503)

        summary = summarize_device_status(raw)
        probe = _last_probe(True, url, summary, None)
        try:
            recorder.record_probe(True, url, summary, None)
        except Exception:
            log.exception("写入设备探测验收事件失败")
        return {"ok": True, "probe": probe, "device": summary}

    @app.post("/api/device/connect")
    def device_connect(req: ConnectRequest):
        if service.state.running:
            raise HTTPException(status_code=409, detail="自动采集运行中，请先停止自动采集再切换设备")
        try:
            url = normalize_base_url(req.base_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        try:
            raw = _probe_device(url)
        except SourceError as exc:
            probe = _last_probe(False, url, None, str(exc))
            try:
                recorder.record_probe(False, url, None, str(exc))
                recorder.record_connect(False, url, None, str(exc))
            except Exception:
                log.exception("写入设备连接失败验收事件失败")
            return JSONResponse({"ok": False, "error": str(exc), "probe": probe}, status_code=503)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            probe = _last_probe(False, url, None, error)
            try:
                recorder.record_probe(False, url, None, error)
                recorder.record_connect(False, url, None, error)
            except Exception:
                log.exception("写入设备连接失败验收事件失败")
            return JSONResponse({"ok": False, "error": error, "probe": probe}, status_code=503)

        summary = summarize_device_status(raw)
        camera = summary.get("camera") or {}
        if camera.get("ready") is False:
            error = "设备可达，但摄像头未就绪（camera.ready=false），未切换采集源。"
            probe = _last_probe(False, url, summary, error)
            try:
                recorder.record_probe(False, url, summary, error)
                recorder.record_connect(False, url, summary, error)
            except Exception:
                log.exception("写入设备连接失败验收事件失败")
            return JSONResponse({"ok": False, "error": error, "probe": probe}, status_code=503)

        probe = _last_probe(True, url, summary, None)
        cfg.capture.source = "esp32"
        cfg.capture.esp32.base_url = url
        service.reset_source()
        try:
            recorder.record_probe(True, url, summary, None)
            recorder.record_connect(True, url, summary, None)
        except Exception:
            log.exception("写入设备连接验收事件失败")
        return {
            "ok": True,
            "probe": probe,
            "device": summary,
            "source": {
                "type": cfg.capture.source,
                "esp32_url": cfg.capture.esp32.base_url,
                "configured_type": original_capture["source"],
                "runtime_override": True,
            },
            "note": (
                "已切换到真实设备采集，仅本次服务进程有效，不写入配置文件；"
                "重启服务后恢复 config/findy.yaml 的设置。"
            ),
        }

    @app.post("/api/source/reset")
    def source_reset():
        if service.state.running:
            raise HTTPException(status_code=409, detail="自动采集运行中，请先停止自动采集再恢复采集源")
        cfg.capture.source = original_capture["source"]
        cfg.capture.esp32.base_url = original_capture["esp32_url"]
        service.reset_source()
        return {
            "ok": True,
            "source": {
                "type": cfg.capture.source,
                "esp32_url": cfg.capture.esp32.base_url if cfg.capture.source == "esp32" else None,
                "configured_type": original_capture["source"],
                "runtime_override": False,
            },
            "note": "已恢复为启动时配置文件中的采集源。",
        }

    # ---------------- 端到端验收运行 ----------------
    def _system_snapshot() -> dict:
        pipe = pipeline.status()
        return {
            "warmup_done": app.state.warmup_done.is_set(),
            "detector": pipe.get("detector"),
            "embedder": pipe.get("embedder"),
            "model_errors": pipe.get("model_errors") or [],
            "db_ok": db.ping(),
            "service": service.state.to_dict(),
            "source": {
                "type": cfg.capture.source,
                "configured_type": original_capture["source"],
                "esp32_url": cfg.capture.esp32.base_url,
                "runtime_override": (
                    cfg.capture.source != original_capture["source"]
                    or cfg.capture.esp32.base_url != original_capture["esp32_url"]
                ),
            },
            "device": {"last_probe": app.state.last_probe},
        }

    def _compute_overview(run: dict | None) -> dict:
        if not run:
            return evaluate_run(db, cfg, None, [])
        events = db.acceptance_events(int(run["id"]))
        pipe = pipeline.status()
        return evaluate_run(
            db,
            cfg,
            run,
            events,
            detector_status=pipe.get("detector"),
            embedder_status=pipe.get("embedder"),
            model_errors=pipe.get("model_errors") or [],
        )

    def _overview_for(run: dict | None) -> dict:
        if run and run.get("status") == "finished" and run.get("summary_json"):
            try:
                summary = json.loads(run["summary_json"])
                # 旧版本判定可能把 duplicate 旧帧误算为 PASS；版本不一致时重新计算，
                # 避免继续展示错误结论（历史 summary 仍保留在数据库中，不删除）。
                if summary.get("evaluator_version") == EVALUATOR_VERSION:
                    return summary
                log.info(
                    "验收运行 #%s 的判定版本为 %s，与当前 %s 不一致，重新计算",
                    run.get("id"),
                    summary.get("evaluator_version"),
                    EVALUATOR_VERSION,
                )
            except (TypeError, ValueError):
                log.warning("验收运行 #%s 的 summary_json 无法解析，改为实时计算", run.get("id"))
        return _compute_overview(run)

    def _acceptance_payload(run: dict | None = None) -> dict:
        current = run if run is not None else db.latest_acceptance_run()
        return {
            "ok": True,
            "run": public_run(current),
            "overview": _overview_for(current),
            "system": _system_snapshot(),
        }

    @app.get("/api/acceptance")
    def acceptance():
        return _acceptance_payload()

    @app.post("/api/acceptance/run/start")
    def acceptance_start(req: AcceptanceStartRequest):
        active = db.active_acceptance_run()
        if active:
            return JSONResponse(
                {
                    "ok": False,
                    "error": f"已有进行中的验收运行 #{active['id']}，请先结束本轮验收。",
                    "run": public_run(active),
                },
                status_code=409,
            )
        if req.mode not in {"real_device", "replay_demo"}:
            raise HTTPException(status_code=400, detail=f"未知验收模式: {req.mode}")
        source_ref = (
            cfg.capture.esp32.base_url
            if cfg.capture.source == "esp32"
            else cfg.capture.replay.dir
        )
        run_id = db.create_acceptance_run(req.mode, cfg.capture.source, source_ref)
        run = db.get_acceptance_run(run_id)
        return _acceptance_payload(run)

    @app.post("/api/acceptance/run/{run_id}/finish")
    def acceptance_finish(run_id: int):
        run = db.get_acceptance_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="验收运行不存在")
        if run.get("status") == "running":
            overview = _compute_overview(run)
            db.finish_acceptance_run(run_id, overview)
            run = db.get_acceptance_run(run_id)
        return _acceptance_payload(run)

    @app.get("/api/acceptance/run/{run_id}/export")
    def acceptance_export(run_id: int):
        run = db.get_acceptance_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="验收运行不存在")
        events = db.acceptance_events(run_id)
        overview = _overview_for(run)
        payload = build_export(run, events, overview)
        body = json.dumps(payload, ensure_ascii=False, indent=2)
        filename = f"findy-acceptance-run-{run_id}.json"
        return Response(
            content=body,
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


def _replay_remaining(service: AutoCaptureService) -> int | None:
    try:
        src = service.source()
        remaining = getattr(src, "remaining", None)
        return int(remaining()) if callable(remaining) else None
    except Exception:
        return None