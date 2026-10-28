"""采集源：ESP32 M1 固件 HTTP 接口 / 本地图片回放 / 上传图像。

设计原则：
- 时间必须来自可信来源；设备未同步时 time_synced=False 且时间字段为 None，绝不伪造；
- 设备接口严格对 seq 校验，避免拿旧图冒充新图；
- 设备不可达时抛出明确错误，由调用方如实展示（不静默失败）。
"""

from __future__ import annotations

import json
import logging
import re
import socket
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import AppConfig, CaptureConfig
from .util import is_valid_jpeg, to_iso

log = logging.getLogger(__name__)


class SourceError(RuntimeError):
    """采集源不可用/返回异常。"""


@dataclass
class CaptureMeta:
    source: str                 # esp32 | webcam | replay | upload
    source_ref: str
    camera_name: str
    time_synced: bool
    time_source: str            # sntp | sntp_unsynced | file_mtime | client | manual
    captured_at_utc: str | None = None
    captured_at_local: str | None = None
    epoch_s: float | None = None
    uptime_ms: int | None = None
    device_seq: int | None = None


@dataclass
class Frame:
    jpeg: bytes
    meta: CaptureMeta


def _open_direct(url: str, timeout: float, data: bytes | None = None, headers: dict | None = None):
    """局域网直连：绕过系统代理（M1 验收时已确认 urllib 会走 127.0.0.1 代理导致极慢）。"""
    req = urllib.request.Request(url, data=data, headers=headers or {})
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    return opener.open(req, timeout=timeout)


class Esp32Source:
    """Findy M1 固件：POST /api/capture 后按 seq 下载 /api/photo。"""

    name = "esp32"

    def __init__(self, base_url: str, timeout: float = 8.0, retries: int = 1):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def probe(self) -> dict:
        try:
            with _open_direct(f"{self.base_url}/api/status", self.timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise SourceError(f"无法连接设备 {self.base_url}: {exc.reason}") from exc
        except Exception as exc:
            raise SourceError(f"读取设备状态失败: {type(exc).__name__}: {exc}") from exc

    def capture(self) -> Frame:
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            try:
                return self._capture_once()
            except SourceError as exc:
                last_error = exc
                log.warning("ESP32 抓拍失败（第 %d 次）: %s", attempt, exc)
        raise SourceError(f"ESP32 抓拍失败: {last_error}") from last_error

    def _capture_once(self) -> Frame:
        try:
            with _open_direct(
                f"{self.base_url}/api/capture",
                self.timeout,
                data=b"",
                headers={"Content-Type": "application/json"},
            ) as r:
                payload = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            raise SourceError(f"设备拍照返回 HTTP {exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise SourceError(f"无法连接设备 {self.base_url}: {exc.reason}") from exc

        rec = payload.get("capture") or {}
        if not rec.get("ok") or not rec.get("jpeg_valid"):
            raise SourceError(f"设备拍照未成功: {json.dumps(rec, ensure_ascii=False)[:200]}")
        seq = int(rec.get("seq") or 0)
        if seq <= 0:
            raise SourceError("设备未返回有效 seq")

        try:
            with _open_direct(f"{self.base_url}/api/photo?seq={seq}", self.timeout) as r:
                jpeg = r.read()
                header_seq = r.headers.get("X-Capture-Seq")
        except urllib.error.HTTPError as exc:
            raise SourceError(f"下载照片失败 HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise SourceError(f"下载照片失败: {exc.reason}") from exc

        if header_seq is not None and int(header_seq) != seq:
            raise SourceError(f"照片 seq 不匹配: 期望 {seq}, 实际 {header_seq}")
        if not is_valid_jpeg(jpeg):
            raise SourceError("下载的照片不是有效 JPEG")
        expected = rec.get("bytes")
        if isinstance(expected, int) and expected > 0 and len(jpeg) != expected:
            raise SourceError(f"照片字节数与设备记录不一致: {len(jpeg)} != {expected}")

        synced = bool(rec.get("time_synced"))
        epoch_s = rec.get("epoch_s")
        meta = CaptureMeta(
            source="esp32",
            source_ref=self.base_url,
            camera_name="ESP32-S3-EYE",
            time_synced=synced,
            time_source="sntp" if synced else "sntp_unsynced",
            captured_at_utc=to_iso(datetime.fromtimestamp(float(epoch_s), tz=timezone.utc)) if synced and epoch_s else None,
            captured_at_local=rec.get("local_time"),
            epoch_s=float(epoch_s) if synced and epoch_s else None,
            uptime_ms=int(rec.get("uptime_ms") or 0),
            device_seq=seq,
        )
        return Frame(jpeg=jpeg, meta=meta)


_TS_RE = re.compile(r"(\d{4})-?(\d{2})-?(\d{2})[T_ \-]?(\d{2})[-_:]?(\d{2})[-_:]?(\d{2})")
_IMG_EXT = {".jpg", ".jpeg"}


class ReplaySource:
    """按文件名顺序回放本地图片（用于演示与回归测试）。

    时间来源按优先级：同名 .json sidecar 的 captured_at_utc > 文件名中的时间戳（本地时区）
    > 文件修改时间；后两者都会显式标记 time_source，不冒充设备 SNTP 时间。
    """

    name = "replay"

    def __init__(self, directory: str | Path, tz_name: str = "Asia/Shanghai", loop: bool = False):
        self.dir = Path(directory)
        self.tz = ZoneInfo(tz_name)
        self.loop = loop
        self._files: list[Path] = []
        self._index = 0
        self.refresh()

    def refresh(self) -> None:
        if not self.dir.exists():
            self._files = []
            return
        self._files = sorted(
            p for p in self.dir.rglob("*") if p.is_file() and p.suffix.lower() in _IMG_EXT
        )
        self._index = 0

    def remaining(self) -> int:
        return max(0, len(self._files) - self._index)

    def reset(self) -> None:
        self._index = 0

    def capture(self) -> Frame:
        if not self._files:
            raise SourceError(f"回放目录中没有图片: {self.dir}")
        if self._index >= len(self._files):
            if not self.loop:
                raise SourceError("回放图片已用尽")
            self._index = 0
        path = self._files[self._index]
        self._index += 1
        jpeg = path.read_bytes()
        if not is_valid_jpeg(jpeg):
            raise SourceError(f"不是有效 JPEG: {path.name}")
        meta = self._meta_for(path)
        return Frame(jpeg=jpeg, meta=meta)

    def _meta_for(self, path: Path) -> CaptureMeta:
        sidecar = path.with_suffix(".json")
        if sidecar.exists():
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                iso = data.get("captured_at_utc")
                if iso:
                    dt = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return CaptureMeta(
                        source="replay",
                        source_ref=str(path),
                        camera_name="replay",
                        time_synced=True,
                        time_source="manual",
                        captured_at_utc=to_iso(dt),
                        captured_at_local=dt.astimezone(self.tz).strftime("%Y-%m-%d %H:%M:%S"),
                        epoch_s=dt.timestamp(),
                    )
            except Exception:
                log.warning("sidecar 解析失败: %s", sidecar)

        m = _TS_RE.search(path.stem)
        if m:
            parts = [int(x) for x in m.groups()]
            dt_local = datetime(*parts, tzinfo=self.tz)
            dt_utc = dt_local.astimezone(timezone.utc)
            return CaptureMeta(
                source="replay",
                source_ref=str(path),
                camera_name="replay",
                time_synced=True,
                time_source="file_mtime",
                captured_at_utc=to_iso(dt_utc),
                captured_at_local=dt_local.strftime("%Y-%m-%d %H:%M:%S"),
                epoch_s=dt_utc.timestamp(),
            )

        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        return CaptureMeta(
            source="replay",
            source_ref=str(path),
            camera_name="replay",
            time_synced=False,
            time_source="file_mtime",
            captured_at_utc=None,
            captured_at_local=mtime.astimezone(self.tz).strftime("%Y-%m-%d %H:%M:%S"),
            epoch_s=None,
        )


def create_source(cfg: CaptureConfig, app_cfg: AppConfig, repo_root: Path):
    source = cfg.source.lower()
    if source == "esp32":
        return Esp32Source(cfg.esp32.base_url, cfg.esp32.timeout_seconds)
    if source == "replay":
        return ReplaySource(cfg.replay.dir if Path(cfg.replay.dir).is_absolute() else repo_root / cfg.replay.dir, app_cfg.tz, cfg.replay.loop)
    if source == "webcam":
        raise SourceError("webcam 采集源需要 OpenCV，本 MVP 默认不启用（隐私优先，推荐 ESP32 或图片回放）")
    raise SourceError(f"未知采集源: {cfg.source}")


def local_ip() -> str:
    """获取本机局域网 IP（用于状态页展示，不对外发送）。"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"