"""物品检测后端。

默认实现：OWLv2 开放词表检测（Apache-2.0 系，非 AGPL），中文物品词表映射为英文提示词。
设计要点：
- 低频抓拍场景，单帧 1–3 秒可接受；
- 每个类别有独立阈值（开放词表模型分数普遍偏低）；
- 过滤过小框与超大框，再做逐类 NMS。
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from .classes import ObjectCatalog
from .config import DetectorConfig
from .imaging import bbox_area_ratio, nms

log = logging.getLogger(__name__)


@dataclass
class Detection:
    class_zh: str
    class_en: str
    confidence: float
    bbox_px: tuple[float, float, float, float]
    raw_label: str = ""

    def bbox_norm(self, width: int, height: int) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = self.bbox_px
        return (
            max(0.0, x1 / width),
            max(0.0, y1 / height),
            min(1.0, x2 / width),
            min(1.0, y2 / height),
        )


class Detector(Protocol):
    name: str

    def detect(self, image: Image.Image) -> list[Detection]: ...

    def status(self) -> dict: ...


def resolve_model_path(value: str, repo_root: Path) -> str:
    """配置既可以是本地目录，也可以是 HuggingFace 仓库 id。"""
    p = Path(value)
    cand = p if p.is_absolute() else repo_root / p
    if cand.is_dir() and (cand / "config.json").exists():
        return str(cand)
    return value


class Owlv2Detector:
    name = "owlv2"

    def __init__(self, cfg: DetectorConfig, catalog: ObjectCatalog, repo_root: Path):
        self.cfg = cfg
        self.catalog = catalog
        self.repo_root = repo_root
        self.model_id = resolve_model_path(cfg.model, repo_root)
        self.classes = catalog.detectable
        self.prompts = [c.en for c in self.classes]
        self._processor = None
        self._model = None
        self._load_error: str | None = None

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoProcessor, Owlv2ForObjectDetection

        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4))))
        log.info("loading OWLv2 from %s", self.model_id)
        self._processor = AutoProcessor.from_pretrained(self.model_id)
        self._model = Owlv2ForObjectDetection.from_pretrained(self.model_id)
        self._model.eval()
        self._model.to(self.cfg.device)
        log.info("OWLv2 ready: %d prompts", len(self.prompts))

    def load(self) -> None:
        """显式预热（启动时调用，失败时记录错误而不是让整个服务崩溃）。"""
        try:
            self._load()
        except Exception as exc:  # pragma: no cover - 依赖真实模型文件
            self._load_error = f"{type(exc).__name__}: {exc}"
            log.exception("OWLv2 加载失败: %s", self._load_error)
            raise

    def status(self) -> dict:
        return {
            "backend": self.name,
            "model": self.model_id,
            "loaded": self._model is not None,
            "error": self._load_error,
            "classes": len(self.classes),
            "thresholds": {c.zh: c.threshold for c in self.classes},
        }

    def detect(self, image: Image.Image) -> list[Detection]:
        import torch

        self._load()
        assert self._processor is not None and self._model is not None
        w, h = image.size
        inputs = self._processor(images=image, text=[self.prompts], return_tensors="pt")
        inputs = {k: v.to(self.cfg.device) for k, v in inputs.items()}
        with torch.no_grad():
            outputs = self._model(**inputs)
        results = self._processor.post_process_grounded_object_detection(
            outputs=outputs,
            threshold=0.02,
            target_sizes=[(h, w)],
            text_labels=[self.prompts],
        )[0]

        boxes = results["boxes"].detach().cpu().numpy()
        scores = results["scores"].detach().cpu().numpy()
        labels = results["labels"].detach().cpu().numpy()

        raw: list[Detection] = []
        for box, score, label in zip(boxes, scores, labels):
            idx = int(label)
            if idx < 0 or idx >= len(self.classes):
                continue
            cls = self.classes[idx]
            if float(score) < cls.threshold:
                continue
            bbox = (float(box[0]), float(box[1]), float(box[2]), float(box[3]))
            ratio = bbox_area_ratio(bbox, w, h)
            if ratio < cls.min_area or ratio > 0.9:
                continue
            raw.append(
                Detection(
                    class_zh=cls.zh,
                    class_en=cls.en,
                    confidence=float(score),
                    bbox_px=bbox,
                    raw_label=self.prompts[idx],
                )
            )

        # 逐类 NMS，避免不同类互相抑制
        kept: list[Detection] = []
        by_class: dict[str, list[Detection]] = {}
        for d in raw:
            by_class.setdefault(d.class_zh, []).append(d)
        for cls_zh, items in by_class.items():
            idxs = nms(
                [d.bbox_px for d in items],
                [d.confidence for d in items],
                iou_threshold=self.cfg.nms_iou,
            )
            kept.extend(items[i] for i in idxs)
        kept.sort(key=lambda d: d.confidence, reverse=True)
        return kept[: self.cfg.max_detections]


class MockDetector:
    """测试/无模型演示用：从 JSON 读取固定检测结果。

    annotations 格式：[{"class_zh": "杯子", "confidence": 0.9,
                       "bbox_px": [x1, y1, x2, y2]}, ...]
    未提供注释时返回空列表（诚实表示"没有检测到"）。
    """

    name = "mock"

    def __init__(self, catalog: ObjectCatalog, annotations: list[dict] | None = None):
        self.catalog = catalog
        self.annotations = annotations or []

    def status(self) -> dict:
        return {"backend": self.name, "loaded": True, "error": None, "annotations": len(self.annotations)}

    def detect(self, image: Image.Image) -> list[Detection]:
        out: list[Detection] = []
        for item in self.annotations:
            cls = self.catalog.by_zh(str(item["class_zh"]))
            if cls is None:
                continue
            out.append(
                Detection(
                    class_zh=cls.zh,
                    class_en=cls.en,
                    confidence=float(item.get("confidence", 0.9)),
                    bbox_px=tuple(float(v) for v in item["bbox_px"]),
                )
            )
        return out