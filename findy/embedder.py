"""实例外观 embedding。

默认：DINOv2 ViT-S/14（Apache-2.0 系），取 CLS token 作为实例向量并 L2 归一化。
DINOv2 是纯视觉自监督特征，官方将其图像检索（最近邻）列为直接用途，
比图文对齐的 CLIP 更适合"是不是同一件实物"的细粒度判断（推断，需本项目实测校准）。
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Protocol

import numpy as np
from PIL import Image

from .config import EmbedderConfig
from .detector import resolve_model_path

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, crops: list[Image.Image]) -> np.ndarray: ...

    def status(self) -> dict: ...


class Dinov2Embedder:
    name = "dinov2"

    def __init__(self, cfg: EmbedderConfig, repo_root: Path):
        self.cfg = cfg
        self.model_id = resolve_model_path(cfg.model, repo_root)
        self._processor = None
        self._model = None
        self._load_error: str | None = None
        self.dim = 0

    def _load(self) -> None:
        if self._model is not None:
            return
        import torch
        from transformers import AutoImageProcessor, AutoModel

        torch.set_num_threads(max(1, min(4, (os.cpu_count() or 4))))
        log.info("loading DINOv2 from %s", self.model_id)
        self._processor = AutoImageProcessor.from_pretrained(self.model_id)
        self._model = AutoModel.from_pretrained(self.model_id)
        self._model.eval()
        self._model.to(self.cfg.device)
        self.dim = int(getattr(self._model.config, "hidden_size", 0) or 0)
        log.info("DINOv2 ready: dim=%s", self.dim)

    def load(self) -> None:
        try:
            self._load()
        except Exception as exc:  # pragma: no cover - 依赖真实模型文件
            self._load_error = f"{type(exc).__name__}: {exc}"
            log.exception("DINOv2 加载失败: %s", self._load_error)
            raise

    def status(self) -> dict:
        return {
            "backend": self.name,
            "model": self.model_id,
            "loaded": self._model is not None,
            "dim": self.dim,
            "error": self._load_error,
        }

    def embed(self, crops: list[Image.Image]) -> np.ndarray:
        import torch

        if not crops:
            return np.zeros((0, self.dim or 1), dtype=np.float32)
        self._load()
        assert self._processor is not None and self._model is not None
        if self.dim == 0:
            self.dim = int(self._model.config.hidden_size)

        vectors: list[np.ndarray] = []
        batch_size = 8
        for start in range(0, len(crops), batch_size):
            batch = [c.convert("RGB") for c in crops[start : start + batch_size]]
            inputs = self._processor(images=batch, return_tensors="pt")
            inputs = {k: v.to(self.cfg.device) for k, v in inputs.items()}
            with torch.no_grad():
                outputs = self._model(**inputs)
            hidden = outputs.last_hidden_state
            cls = hidden[:, 0, :].detach().cpu().numpy().astype(np.float32)
            vectors.append(cls)
        arr = np.concatenate(vectors, axis=0)
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return arr / norms


class HashEmbedder:
    """确定性测试替身：由裁剪图的平均哈希（average hash）生成单位向量。

    仅用于单测/无模型环境，不代表任何语义；生产路径必须使用 Dinov2Embedder。
    与逐字节哈希不同，平均哈希对整体位置/曝光变化更稳定，适合验证关联逻辑本身。
    """

    name = "hash"
    dim = 64

    def __init__(self):
        self._load_error = None

    def load(self) -> None:
        return None

    def status(self) -> dict:
        return {"backend": self.name, "loaded": True, "dim": self.dim, "error": None}

    def embed(self, crops: list[Image.Image]) -> np.ndarray:
        out = np.zeros((len(crops), self.dim), dtype=np.float32)
        for i, crop in enumerate(crops):
            small = crop.convert("L").resize((8, 8), Image.Resampling.BILINEAR)
            values = np.asarray(small, dtype=np.float32).reshape(-1)
            bits = (values > values.mean()).astype(np.float32) * 2.0 - 1.0
            norm = float(np.linalg.norm(bits))
            out[i] = bits / (norm or 1.0)
        return out


def create_embedder(cfg: EmbedderConfig, repo_root: Path) -> Embedder:
    backend = cfg.backend.lower()
    if backend in {"dinov2", "auto"}:
        return Dinov2Embedder(cfg, repo_root)
    if backend in {"hash", "mock"}:
        return HashEmbedder()
    raise ValueError(f"未知 embedding 后端: {cfg.backend}")