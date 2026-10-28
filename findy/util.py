"""时间、哈希与图像基础工具。"""

from __future__ import annotations

import hashlib
import io
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return to_iso(utc_now())


def to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def local_display(iso_utc: str | None, tz_name: str = "Asia/Shanghai") -> str | None:
    dt = parse_iso(iso_utc)
    if dt is None:
        return None
    return dt.astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d %H:%M:%S")


def humanize_delta(iso_utc: str | None, tz_name: str = "Asia/Shanghai") -> str | None:
    dt = parse_iso(iso_utc)
    if dt is None:
        return None
    delta = utc_now() - dt
    seconds = delta.total_seconds()
    if seconds < 0:
        return "时间异常（记录时间在未来）"
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{int(seconds // 60)} 分钟前"
    if seconds < 86400:
        return f"{int(seconds // 3600)} 小时前"
    days = int(seconds // 86400)
    if days < 30:
        return f"{days} 天前"
    return f"{days // 30} 个月前"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_valid_jpeg(data: bytes) -> bool:
    return len(data) > 4 and data.startswith(JPEG_SOI) and data.endswith(JPEG_EOI)


def image_size(data: bytes) -> tuple[int, int]:
    from PIL import Image

    with Image.open(io.BytesIO(data)) as im:
        return im.size


def fmt_bbox(bbox: tuple[float, float, float, float]) -> str:
    return ",".join(f"{v:.2f}" for v in bbox)


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    parts = [float(v) for v in text.split(",")]
    if len(parts) != 4:
        raise ValueError(f"无效 bbox: {text}")
    return parts[0], parts[1], parts[2], parts[3]


def epoch_to_iso(epoch_s: float) -> str:
    return to_iso(datetime.fromtimestamp(epoch_s, tz=timezone.utc))


def iso_to_epoch(iso: str | None) -> float | None:
    dt = parse_iso(iso)
    return dt.timestamp() if dt else None