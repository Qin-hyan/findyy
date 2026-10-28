"""Findy 配置加载。

配置优先级：默认值 < YAML 文件 < 环境变量（FINdy_* 只支持少量覆盖）。
相对路径统一相对仓库根目录（findy 包的上一级）解析，保证任意工作目录下行为一致。
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "findy.yaml"


@dataclass
class AppConfig:
    data_dir: str = "data"
    db_path: str = "data/findy.sqlite"
    images_dir: str = "data/images"
    crops_dir: str = "data/crops"
    tz: str = "Asia/Shanghai"
    host: str = "127.0.0.1"
    port: int = 8765


@dataclass
class Esp32Config:
    base_url: str = "http://192.168.1.50"
    timeout_seconds: float = 8.0


@dataclass
class WebcamConfig:
    device_index: int = 0
    width: int = 1280
    height: int = 720


@dataclass
class ReplayConfig:
    dir: str = "samples/frames"
    loop: bool = False


@dataclass
class CaptureConfig:
    source: str = "replay"
    interval_seconds: float = 60.0
    esp32: Esp32Config = field(default_factory=Esp32Config)
    webcam: WebcamConfig = field(default_factory=WebcamConfig)
    replay: ReplayConfig = field(default_factory=ReplayConfig)


@dataclass
class DetectorConfig:
    backend: str = "owlv2"
    model: str = "google/owlv2-base-patch16-ensemble"
    score_threshold: float = 0.12
    nms_iou: float = 0.4
    max_detections: int = 30
    device: str = "cpu"


@dataclass
class EmbedderConfig:
    backend: str = "dinov2"
    model: str = "vit_small_patch14_dinov2.lvd142m"
    image_size: int = 224
    device: str = "cpu"


@dataclass
class MatchingWeights:
    embedding: float = 0.70
    color: float = 0.15
    zone: float = 0.10
    recency: float = 0.05


@dataclass
class MatchingConfig:
    accept_threshold: float = 0.82
    uncertain_threshold: float = 0.70
    weights: MatchingWeights = field(default_factory=MatchingWeights)
    recency_tau_hours: float = 24.0
    prototype_alpha: float = 0.2


@dataclass
class FilesConfig:
    objects: str = "config/objects.yaml"
    zones: str = "config/zones.yaml"


@dataclass
class Config:
    app: AppConfig = field(default_factory=AppConfig)
    capture: CaptureConfig = field(default_factory=CaptureConfig)
    detector: DetectorConfig = field(default_factory=DetectorConfig)
    embedder: EmbedderConfig = field(default_factory=EmbedderConfig)
    matching: MatchingConfig = field(default_factory=MatchingConfig)
    files: FilesConfig = field(default_factory=FilesConfig)
    source_path: Path | None = None

    # ---- 路径 ----
    def resolve(self, value: str) -> Path:
        p = Path(value)
        return p if p.is_absolute() else (REPO_ROOT / p)

    @property
    def data_dir(self) -> Path:
        return self.resolve(self.app.data_dir)

    @property
    def db_path(self) -> Path:
        return self.resolve(self.app.db_path)

    @property
    def images_dir(self) -> Path:
        return self.resolve(self.app.images_dir)

    @property
    def crops_dir(self) -> Path:
        return self.resolve(self.app.crops_dir)

    @property
    def objects_file(self) -> Path:
        return self.resolve(self.files.objects)

    @property
    def zones_file(self) -> Path:
        return self.resolve(self.files.zones)

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.images_dir, self.crops_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def public_dict(self) -> dict[str, Any]:
        """可安全返回给前端的配置快照（无密钥类字段）。"""
        return {
            "host": self.app.host,
            "port": self.app.port,
            "tz": self.app.tz,
            "capture_source": self.capture.source,
            "capture_interval_seconds": self.capture.interval_seconds,
            "esp32_base_url": self.capture.esp32.base_url,
            "detector": self.detector.backend,
            "detector_model": self.detector.model,
            "embedder": self.embedder.backend,
            "embedder_model": self.embedder.model,
            "accept_threshold": self.matching.accept_threshold,
            "uncertain_threshold": self.matching.uncertain_threshold,
            "db_path": str(self.db_path),
        }


def _merge_dict(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge_dict(out[key], value)
        else:
            out[key] = value
    return out


def _as_dict(obj: Any) -> dict:
    # dataclass -> dict（嵌套 dataclass 递归展开）
    import dataclasses

    return dataclasses.asdict(obj)


def _from_dict(cls, data: dict):
    """递归构造 dataclass：支持嵌套 dataclass 与 list/dict。"""
    import dataclasses
    import typing

    hints = typing.get_type_hints(cls)
    fields = {f.name: f for f in dataclasses.fields(cls)}
    kwargs = {}
    for name, value in data.items():
        if name not in fields:
            continue
        ftype = hints.get(name, fields[name].type)
        kwargs[name] = _coerce(ftype, value)
    return cls(**kwargs)


def _coerce(ftype: Any, value: Any):
    import dataclasses
    import typing

    if value is None:
        return None
    origin = typing.get_origin(ftype)
    if dataclasses.is_dataclass(ftype):
        if isinstance(value, dict):
            return _from_dict(ftype, value)
        return value
    if origin is list:
        return value
    if origin is dict:
        return value
    # 基本类型
    if isinstance(ftype, type) and ftype in (int, float, str, bool):
        return ftype(value)
    return value


def load_config(path: str | os.PathLike | None = None) -> Config:
    """加载配置；文件不存在时抛出明确错误（避免静默使用错误配置）。"""
    cfg_path = Path(path) if path else Path(
        os.environ.get("FINDY_CONFIG", str(DEFAULT_CONFIG_PATH))
    )
    if not cfg_path.is_absolute():
        cfg_path = REPO_ROOT / cfg_path
    if not cfg_path.exists():
        raise FileNotFoundError(f"配置文件不存在: {cfg_path}")

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    defaults = _as_dict(Config())
    merged = _merge_dict(defaults, raw)

    cfg = Config(
        app=_from_dict(AppConfig, merged.get("app", {})),
        capture=_from_dict(CaptureConfig, merged.get("capture", {})),
        detector=_from_dict(DetectorConfig, merged.get("detector", {})),
        embedder=_from_dict(EmbedderConfig, merged.get("embedder", {})),
        matching=_from_dict(MatchingConfig, merged.get("matching", {})),
        files=_from_dict(FilesConfig, merged.get("files", {})),
        source_path=cfg_path,
    )
    if cfg.capture.source not in {"esp32", "webcam", "replay"}:
        raise ValueError(f"未知采集源: {cfg.capture.source}")
    # 少量环境变量覆盖（便于部署与测试，不需要改动配置文件）
    if os.environ.get("FINDY_CAPTURE_SOURCE"):
        cfg.capture.source = os.environ["FINDY_CAPTURE_SOURCE"]
    if os.environ.get("FINDY_DETECTOR_BACKEND"):
        cfg.detector.backend = os.environ["FINDY_DETECTOR_BACKEND"]
    if os.environ.get("FINDY_DETECTOR_MODEL"):
        cfg.detector.model = os.environ["FINDY_DETECTOR_MODEL"]
    if os.environ.get("FINDY_EMBEDDER_BACKEND"):
        cfg.embedder.backend = os.environ["FINDY_EMBEDDER_BACKEND"]
    if os.environ.get("FINDY_EMBEDDER_MODEL"):
        cfg.embedder.model = os.environ["FINDY_EMBEDDER_MODEL"]
    if os.environ.get("FINDY_ESP32_URL"):
        cfg.capture.esp32.base_url = os.environ["FINDY_ESP32_URL"]
    if os.environ.get("FINDY_DB_PATH"):
        cfg.app.db_path = os.environ["FINDY_DB_PATH"]
    if os.environ.get("FINDY_REPLAY_DIR"):
        cfg.capture.replay.dir = os.environ["FINDY_REPLAY_DIR"]
    return cfg