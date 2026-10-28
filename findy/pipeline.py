"""抓拍 → 检测 → 关联 → 入库 的主流水线。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .classes import ObjectCatalog
from .config import Config
from .db import Database
from .detector import Detection, Detector
from .embedder import Embedder
from .imaging import (
    bbox_area_ratio,
    color_features,
    color_similarity,
    crop_with_margin,
    load_image,
    save_bytes,
)
from .matcher import combined_score, decide, recency_score, zone_prior
from .sources import CaptureMeta
from .util import fmt_bbox, sha256_bytes, to_iso, utc_now, utc_now_iso
from .zones import Region, assign_region

log = logging.getLogger(__name__)


@dataclass
class ObserveResult:
    ok: bool
    capture_id: int
    duplicate: bool
    capture: dict = field(default_factory=dict)
    detections: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "capture_id": self.capture_id,
            "duplicate": self.duplicate,
            "capture": self.capture,
            "detections": self.detections,
            "warnings": self.warnings,
            "error": self.error,
        }


class FindyPipeline:
    def __init__(
        self,
        cfg: Config,
        db: Database,
        catalog: ObjectCatalog,
        detector: Detector,
        embedder: Embedder,
        regions: list[Region],
    ):
        self.cfg = cfg
        self.db = db
        self.catalog = catalog
        self.detector = detector
        self.embedder = embedder
        self.regions = regions
        self.camera_id = 0
        self.region_ids: dict[str, int] = {}
        self.class_ids: dict[str, int] = {}
        self.model_errors: list[str] = []

    # ---------------- 初始化 ----------------
    def initialize(self) -> None:
        self.cfg.ensure_dirs()
        self.db.init_schema()
        self.class_ids = self.db.sync_catalog(self.catalog)
        self.camera_id = self.db.ensure_camera(
            name="default",
            source=self.cfg.capture.source,
            model="ESP32-S3-EYE v2.2 + OV2640" if self.cfg.capture.source == "esp32" else self.cfg.capture.source,
            width=0,
            height=0,
            tz_name=self.cfg.app.tz,
        )
        self.region_ids = self.db.sync_regions(self.camera_id, self.regions)

    def warmup(self) -> None:
        """提前加载模型；失败记录到 model_errors，由界面如实展示。"""
        for component in (self.detector, self.embedder):
            load = getattr(component, "load", None)
            if load is None:
                continue
            try:
                load()
            except Exception as exc:
                self.model_errors.append(f"{component.name}: {type(exc).__name__}: {exc}")

    def status(self) -> dict:
        return {
            "camera_id": self.camera_id,
            "detector": self.detector.status(),
            "embedder": self.embedder.status(),
            "model_errors": self.model_errors,
            "stats": self.db.stats(),
        }

    # ---------------- 主流程 ----------------
    def observe(self, jpeg: bytes, meta: CaptureMeta) -> ObserveResult:
        image = load_image(jpeg)
        width, height = image.size
        received = utc_now_iso()
        sha = sha256_bytes(jpeg)

        day = (meta.captured_at_utc or received)[:10].replace("-", "/")
        stamp = (meta.captured_at_utc or received).replace(":", "").replace("-", "")
        image_path = self.cfg.images_dir / day / f"{stamp}_{sha[:8]}.jpg"
        save_bytes(image_path, jpeg)

        capture_id, created = self.db.add_capture(
            {
                "camera_id": self.camera_id,
                "device_seq": meta.device_seq,
                "captured_at_utc": meta.captured_at_utc,
                "captured_at_local": meta.captured_at_local,
                "epoch_s": meta.epoch_s,
                "time_synced": int(meta.time_synced),
                "time_source": meta.time_source,
                "uptime_ms": meta.uptime_ms,
                "received_at_utc": received,
                "file_path": str(image_path.relative_to(Path.cwd()) if image_path.is_relative_to(Path.cwd()) else image_path),
                "image_width": width,
                "image_height": height,
                "image_bytes": len(jpeg),
                "sha256": sha,
                "source_ref": meta.source_ref,
                "status": "ok",
            }
        )
        if not created:
            existing = self.db.get_capture(capture_id) or {}
            dets = self.db.detections_for_capture(capture_id)
            return ObserveResult(
                ok=True,
                capture_id=capture_id,
                duplicate=True,
                capture=self._capture_view(existing, dets),
                detections=[self._detection_view(d) for d in dets],
                warnings=["同一设备 seq 的抓拍已存在，未重复入库（幂等）"],
            )

        # 检测
        try:
            detections = sorted(
                self.detector.detect(image),
                key=lambda d: (d.class_zh, -d.confidence, d.bbox_px[0]),
            )
        except Exception as exc:
            log.exception("检测失败")
            self.db.set_capture_status(capture_id, "detect_failed")
            return ObserveResult(
                ok=False,
                capture_id=capture_id,
                duplicate=False,
                capture=self._capture_view(self.db.get_capture(capture_id) or {}, []),
                error=f"检测失败: {type(exc).__name__}: {exc}",
            )

        crops = []
        crop_boxes: list[tuple] = []
        for det in detections:
            crop = crop_with_margin(image, det.bbox_px)
            crops.append(crop if crop is not None else image.resize((64, 64)))
            crop_boxes.append(det.bbox_px)

        embeddings = self.embedder.embed(crops) if crops else np.zeros((0, 1), dtype=np.float32)

        used_track_ids: set[int] = set()
        track_cache: dict[str, list[dict]] = {}
        results: list[dict] = []
        warnings: list[str] = []
        crop_dir = self.cfg.crops_dir / str(capture_id)
        crop_dir.mkdir(parents=True, exist_ok=True)

        for idx, (det, crop, emb) in enumerate(zip(detections, crops, embeddings)):
            if crop is None:
                continue
            color_hex, color_name, color_hist = color_features(crop)
            region = assign_region(det.bbox_px, width, height, self.regions)
            region_id = self.region_ids.get(region.name) if region else None
            region_name = region.name if region else self._fallback_position(det.bbox_px, width, height)

            class_id = self.class_ids[det.class_zh]
            if det.class_zh not in track_cache:
                track_cache[det.class_zh] = self.db.active_tracks_for_class(class_id)

            scored: list[tuple[int, float, str]] = []
            for track in track_cache[det.class_zh]:
                if int(track["id"]) in used_track_ids:
                    continue
                proto = (
                    np.frombuffer(track["prototype"], dtype=np.float32)
                    if track.get("prototype")
                    else None
                )
                if proto is None or proto.size != emb.size:
                    continue
                hist = (
                    np.frombuffer(track["color_hist"], dtype=np.float32)
                    if track.get("color_hist")
                    else None
                )
                emb_sim = float(np.clip(np.dot(proto, emb), -1.0, 1.0))
                c_sim = color_similarity(hist, color_hist)
                z_prior = zone_prior(track.get("last_region_id"), region_id)
                r_prior = recency_score(track.get("last_seen_utc"), self.cfg.matching.recency_tau_hours)
                score = combined_score(
                    emb_sim, c_sim, z_prior, r_prior, self.cfg.matching.weights.__dict__
                )
                reason = f"外观 {emb_sim:.2f} / 颜色 {c_sim:.2f} / 区域 {'同区' if z_prior == 1.0 else ('异区' if z_prior == 0.35 else '未知')} / 时间 {r_prior:.2f}"
                scored.append((int(track["id"]), score, reason))

            ranked = sorted(scored, key=lambda x: x[1], reverse=True)
            best_id: int | None = None
            best_score = ranked[0][1] if ranked else 0.0
            best_reason = ranked[0][2] if ranked else "没有同类历史物品"
            status = decide(
                best_score,
                self.cfg.matching.accept_threshold,
                self.cfg.matching.uncertain_threshold,
            ) if ranked else "new"
            candidates = [
                {"track_id": int(tid), "score": round(float(s), 4)}
                for tid, s, _ in ranked
                if s >= self.cfg.matching.uncertain_threshold
            ][:3]

            crop_path = crop_dir / f"d{idx:02d}_{det.class_zh}.jpg"
            crop.save(crop_path, format="JPEG", quality=90)

            if status == "matched" and ranked:
                best_id = ranked[0][0]
                used_track_ids.add(best_id)
                method, link_status = "prototype", "matched"
                self.db.update_track(
                    best_id,
                    emb,
                    color_hist,
                    color_name,
                    color_hex,
                    meta.captured_at_utc,
                    capture_id,
                    region_id,
                    alpha=self.cfg.matching.prototype_alpha,
                )
            else:
                label = self._track_label(det.class_zh, color_name, class_id)
                new_track_id = self.db.create_track(
                    class_id=class_id,
                    label=label,
                    color=color_name,
                    color_hex=color_hex,
                    prototype=emb,
                    color_hist=color_hist,
                    seen_iso=meta.captured_at_utc,
                    capture_id=capture_id,
                    region_id=region_id,
                )
                track_cache.setdefault(det.class_zh, []).append(self.db.get_track(new_track_id) or {})
                used_track_ids.add(new_track_id)
                best_id = new_track_id
                method = "new" if status == "new" else "ambiguous"
                link_status = status
                if candidates:
                    warnings.append(
                        f"{det.class_zh} 可能与已有物品重复（最高相似度 {best_score:.2f}），已标为待确认"
                    )

            detection_id = self.db.add_detection(
                {
                    "capture_id": capture_id,
                    "track_id": best_id,
                    "class_id": class_id,
                    "region_id": region_id,
                    "region_name": region_name,
                    "bbox_norm": fmt_bbox(det.bbox_norm(width, height)),
                    "bbox_px": fmt_bbox(det.bbox_px),
                    "conf": det.confidence,
                    "crop_path": str(crop_path),
                    "embedding": emb.astype(np.float32).tobytes(),
                    "color_hex": color_hex,
                    "link_score": best_score,
                    "link_method": method,
                    "link_status": link_status,
                    "captured_at_utc": meta.captured_at_utc,
                    "created_at_utc": received,
                }
            )
            if status == "ambiguous" and candidates:
                for cand in candidates:
                    self.db.add_link_candidate(detection_id, int(cand["track_id"]), float(cand["score"]))

            results.append(
                {
                    "detection_id": detection_id,
                    "track_id": best_id,
                    "class": det.class_zh,
                    "confidence": round(det.confidence, 4),
                    "bbox_norm": [round(v, 4) for v in det.bbox_norm(width, height)],
                    "bbox_px": [round(v, 1) for v in det.bbox_px],
                    "color": color_name,
                    "color_hex": color_hex,
                    "region": region_name,
                    "link_status": link_status,
                    "link_method": method,
                    "link_score": round(best_score, 4),
                    "link_reason": best_reason,
                    "candidates": candidates,
                    "crop_url": f"/api/detections/{detection_id}/crop",
                    "area_ratio": round(bbox_area_ratio(det.bbox_px, width, height), 5),
                }
            )

        self.db.set_capture_detections_count(capture_id, len(results))
        capture = self.db.get_capture(capture_id) or {}
        return ObserveResult(
            ok=True,
            capture_id=capture_id,
            duplicate=False,
            capture=self._capture_view(capture, []),
            detections=results,
            warnings=warnings,
        )

    # ---------------- 视图辅助 ----------------
    def _track_label(self, class_zh: str, color_name: str | None, class_id: int) -> str:
        base = f"{color_name}{class_zh}" if color_name and color_name != "灰色" else class_zh
        return base

    def _fallback_position(self, bbox_px, width: int, height: int) -> str:
        x1, y1, x2, y2 = bbox_px
        cx = ((x1 + x2) / 2) / max(width, 1)
        cy = ((y1 + y2) / 2) / max(height, 1)
        horiz = "左侧" if cx < 1 / 3 else ("右侧" if cx > 2 / 3 else "中央")
        vert = "上方" if cy < 1 / 3 else ("下方" if cy > 2 / 3 else "")
        return f"画面{vert}{horiz}"

    def _capture_view(self, capture: dict, detections: list[dict]) -> dict:
        from .util import humanize_delta, local_display

        cid = capture.get("id")
        return {
            "id": cid,
            "captured_at_utc": capture.get("captured_at_utc"),
            "captured_at_local": capture.get("captured_at_local")
            or local_display(capture.get("captured_at_utc"), self.cfg.app.tz),
            "received_at_utc": capture.get("received_at_utc"),
            "time_synced": bool(capture.get("time_synced")),
            "time_source": capture.get("time_source"),
            "time_ago": humanize_delta(capture.get("captured_at_utc"), self.cfg.app.tz)
            if capture.get("time_synced")
            else None,
            "width": capture.get("image_width"),
            "height": capture.get("image_height"),
            "detections_count": capture.get("detections_count", len(detections)),
            "source": capture.get("source_ref"),
            "image_url": f"/api/captures/{cid}/image",
            "thumbnail_url": f"/api/captures/{cid}/image?thumb=1",
        }

    def _detection_view(self, row: dict) -> dict:
        return {
            "detection_id": row.get("id"),
            "track_id": row.get("track_id"),
            "class": row.get("name_zh") or row.get("class_name"),
            "confidence": row.get("conf"),
            "bbox_norm": row.get("bbox_norm"),
            "bbox_px": row.get("bbox_px"),
            "region": row.get("region_name"),
            "color_hex": row.get("color_hex"),
            "link_status": row.get("link_status"),
            "link_method": row.get("link_method"),
            "link_score": row.get("link_score"),
            "crop_url": f"/api/detections/{row.get('id')}/crop",
        }