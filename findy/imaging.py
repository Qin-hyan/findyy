"""图像处理：校验、裁剪、主色/颜色直方图、NMS。全部纯 PIL + numpy 实现。"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from .util import is_valid_jpeg

# 15 维颜色直方图：12 个色相桶 + 白/黑/灰 三个无彩色桶
COLOR_HIST_DIM = 15

COLOR_NAMES = [
    "红色", "橙色", "黄色", "黄绿", "绿色", "青绿",
    "青色", "天蓝", "蓝色", "蓝紫", "紫色", "粉色",
]


def load_image(data: bytes) -> Image.Image:
    if not is_valid_jpeg(data):
        raise ValueError("不是有效的 JPEG（缺少 SOI/EOI 标记）")
    with Image.open(io.BytesIO(data)) as im:
        return im.convert("RGB")


def save_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)


def crop_with_margin(
    image: Image.Image,
    bbox_px: tuple[float, float, float, float],
    margin_ratio: float = 0.08,
    min_side: int = 12,
) -> Image.Image | None:
    """按检测框裁图（带边距）。框太小或越界严重时返回 None。"""
    w, h = image.size
    x1, y1, x2, y2 = bbox_px
    if x2 <= x1 or y2 <= y1:
        return None
    bw, bh = x2 - x1, y2 - y1
    mx, my = bw * margin_ratio, bh * margin_ratio
    x1 = max(0, int(round(x1 - mx)))
    y1 = max(0, int(round(y1 - my)))
    x2 = min(w, int(round(x2 + mx)))
    y2 = min(h, int(round(y2 + my)))
    if x2 - x1 < min_side or y2 - y1 < min_side:
        return None
    return image.crop((x1, y1, x2, y2))


def bbox_area_ratio(bbox_px, width: int, height: int) -> float:
    x1, y1, x2, y2 = bbox_px
    return max(0.0, (x2 - x1)) * max(0.0, (y2 - y1)) / float(max(width * height, 1))


def color_features(crop: Image.Image) -> tuple[str | None, str | None, np.ndarray]:
    """返回 (主色 hex, 主色中文名, 15 维颜色直方图)。

    无彩色（白/黑/灰）与高饱和色分开统计，避免把浅色桌面误判成彩色。
    """
    small = crop.convert("RGB").resize((48, 48), Image.Resampling.BILINEAR)
    arr = np.asarray(small, dtype=np.float32) / 255.0
    hsv = np.asarray(small.convert("HSV"), dtype=np.float32)
    h = hsv[..., 0] / 255.0 * 360.0
    s = hsv[..., 1] / 255.0
    v = hsv[..., 2] / 255.0

    hist = np.zeros(COLOR_HIST_DIM, dtype=np.float32)
    pixels = h.size
    chromatic = (s > 0.22) & (v > 0.14)
    n_chroma = int(chromatic.sum())

    if n_chroma >= max(4, int(pixels * 0.12)):
        hue = h[chromatic]
        bins = np.mod(np.floor(hue / 30.0).astype(int), 12)  # 每 30° 一个桶
        counts = np.bincount(bins, minlength=12).astype(np.float32)
        chroma_frac = n_chroma / float(pixels)
        hist[0:12] = counts / max(n_chroma, 1) * chroma_frac
        dom_bin = int(counts.argmax())
        name = COLOR_NAMES[dom_bin]
        # 区分棕色（橙色调 + 低亮度）
        if dom_bin in (1, 2) and float(v[chromatic].mean()) < 0.45:
            name = "棕色"
        # 主色 hex 用该桶像素平均色
        mask = chromatic & (np.mod(np.floor(h / 30.0).astype(int), 12) == dom_bin)
        if mask.sum() > 0:
            mean_rgb = (arr[mask].mean(axis=0) * 255).astype(int)
            hex_color = "#{:02x}{:02x}{:02x}".format(*mean_rgb)
        else:
            hex_color = "#808080"
    else:
        name = None
        hex_color = "#{:02x}{:02x}{:02x}".format(*((arr.mean(axis=(0, 1)) * 255).astype(int)))

    # 无彩色三桶：白 / 黑 / 中灰
    white = float(((v > 0.78) & (s < 0.18)).sum()) / pixels
    black = float(((v < 0.20)).sum()) / pixels
    gray = max(0.0, 1.0 - white - black - n_chroma / float(pixels))
    hist[12] = white
    hist[13] = black
    hist[14] = gray

    if name is None:
        total_gray = hist[12] + hist[13] + hist[14]
        if total_gray > 0:
            if white >= max(black, gray):
                name = "白色"
            elif black >= max(white, gray):
                name = "黑色"
            else:
                name = "灰色"
    return hex_color, name, hist


def color_similarity(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None:
        return 0.5
    if a.size != b.size:
        return 0.5
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    sa, sb = float(a.sum()), float(b.sum())
    if sa > 0:
        a = a / sa
    if sb > 0:
        b = b / sb
    return float(max(0.0, 1.0 - 0.5 * np.abs(a - b).sum()))


def nms(
    boxes: list[tuple[float, float, float, float]],
    scores: list[float],
    iou_threshold: float = 0.4,
) -> list[int]:
    """纯 numpy NMS，返回保留框下标（按分数降序）。"""
    if not boxes:
        return []
    b = np.asarray(boxes, dtype=np.float32)
    s = np.asarray(scores, dtype=np.float32)
    x1, y1, x2, y2 = b[:, 0], b[:, 1], b[:, 2], b[:, 3]
    areas = np.maximum(0, x2 - x1) * np.maximum(0, y2 - y1)
    order = s.argsort()[::-1]
    keep: list[int] = []
    while order.size > 0:
        i = int(order[0])
        keep.append(i)
        if order.size == 1:
            break
        rest = order[1:]
        xx1 = np.maximum(x1[i], x1[rest])
        yy1 = np.maximum(y1[i], y1[rest])
        xx2 = np.minimum(x2[i], x2[rest])
        yy2 = np.minimum(y2[i], y2[rest])
        inter = np.maximum(0, xx2 - xx1) * np.maximum(0, yy2 - yy1)
        iou = inter / np.maximum(areas[i] + areas[rest] - inter, 1e-9)
        order = rest[iou <= iou_threshold]
    return keep