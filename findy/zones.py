"""命名区域：归一化多边形 + 检测框归属判定。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Region:
    name: str
    polygon: list[tuple[float, float]]
    kind: str = "surface"

    def contains(self, x: float, y: float) -> bool:
        return point_in_polygon(x, y, self.polygon)

    def to_row(self) -> dict:
        return {
            "name": self.name,
            "kind": self.kind,
            "polygon_norm": json.dumps(self.polygon),
        }


def point_in_polygon(x: float, y: float, polygon: list[tuple[float, float]]) -> bool:
    """射线法；polygon 为归一化坐标，点 (x,y) 同样归一化。"""
    if len(polygon) < 3:
        return False
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def load_regions(path: str | Path) -> list[Region]:
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"区域配置不存在: {p}")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    regions: list[Region] = []
    for item in data.get("regions") or []:
        poly = [tuple(map(float, pt)) for pt in (item.get("polygon") or [])]
        regions.append(Region(name=str(item["name"]), polygon=poly, kind=str(item.get("kind", "surface"))))
    return regions


def assign_region(
    bbox_px: tuple[float, float, float, float],
    width: int,
    height: int,
    regions: list[Region],
) -> Region | None:
    """用检测框中心点判定区域；都未命中时返回 None（由调用方给出画面方位兜底）。"""
    x1, y1, x2, y2 = bbox_px
    cx = ((x1 + x2) / 2.0) / max(width, 1)
    cy = ((y1 + y2) / 2.0) / max(height, 1)
    for r in regions:
        if r.contains(cx, cy):
            return r
    return None


def describe_position(
    bbox_px: tuple[float, float, float, float],
    width: int,
    height: int,
    regions: list[Region],
) -> tuple[str | None, str | None]:
    """返回 (region_name, region_id 由 db 补) 的语义位置描述。

    没有标定区域时，用九宫格方位给出人类可读描述（不谎称精确坐标）。
    """
    region = assign_region(bbox_px, width, height, regions)
    if region is not None:
        return region.name, region.kind
    x1, y1, x2, y2 = bbox_px
    cx = ((x1 + x2) / 2.0) / max(width, 1)
    cy = ((y1 + y2) / 2.0) / max(height, 1)
    horiz = "左侧" if cx < 1 / 3 else ("右侧" if cx > 2 / 3 else "中央")
    vert = "上方" if cy < 1 / 3 else ("下方" if cy > 2 / 3 else "")
    label = f"画面{vert}{horiz}" if vert else f"画面{horiz}"
    return label, "frame_grid"