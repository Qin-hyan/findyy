"""同一实物关联的打分与三态判定（纯函数，便于单测与调参）。

分数 = w_embedding * 外观相似度 + w_color * 颜色相似度 + w_zone * 区域先验 + w_recency * 时间新鲜度

判定三态（不把不确定硬说成确定）：
- matched:   score >= accept_threshold    → 直接归入已有物品
- ambiguous: uncertain_threshold <= score < accept_threshold → 新建物品但记录候选关联，界面提示"待确认"
- new:       score < uncertain_threshold   → 视为新物品
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from .util import parse_iso, utc_now


@dataclass
class MatchDecision:
    status: str            # matched | ambiguous | new
    best_track_id: int | None
    best_score: float
    candidates: list[tuple[int, float]]
    reason: str


def cosine_similarity(a: np.ndarray | None, b: np.ndarray | None) -> float:
    if a is None or b is None or a.size == 0 or b.size == 0 or a.size != b.size:
        return 0.0
    a = a.astype(np.float32)
    b = b.astype(np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0 or nb == 0:
        return 0.0
    return float(np.clip(np.dot(a, b) / (na * nb), -1.0, 1.0))


def recency_score(last_seen_iso: str | None, tau_hours: float = 24.0) -> float:
    """越近越接近 1，指数衰减；未知时间取中性 0.5。"""
    dt = parse_iso(last_seen_iso)
    if dt is None:
        return 0.5
    hours = max(0.0, (utc_now() - dt).total_seconds() / 3600.0)
    if tau_hours <= 0:
        return 0.5
    return float(math.exp(-hours / tau_hours))


def zone_prior(last_region_id: int | None, region_id: int | None) -> float:
    """固定机位下位置是强先验：同区域 1.0，不同区域 0.35，未知 0.6。"""
    if last_region_id is None or region_id is None:
        return 0.6
    return 1.0 if int(last_region_id) == int(region_id) else 0.35


def bbox_iou(a: tuple[float, float, float, float] | None, b: tuple[float, float, float, float] | None) -> float:
    """归一化 bbox 的 IoU；用于固定机位下"物体还在原处"的空间先验。"""
    if a is None or b is None:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter
    if union <= 0:
        return 0.0
    return float(min(1.0, inter / union))


def combined_score(
    embedding_sim: float,
    color_sim: float,
    zone: float,
    recency: float,
    weights: dict[str, float],
    spatial_iou: float = 0.0,
    spatial_bonus: float = 0.15,
) -> float:
    """外观/颜色/区域/时间加权平均，再叠加固定机位下的空间 IoU 奖励。

    IoU 只做"加分项"而不是替换外观：物体被挪走后 IoU 变 0，仍可靠外观与颜色匹配；
    物体留在原处时 IoU 加分能显著抵抗光照/裁剪抖动导致的 embedding 波动。
    """
    w = {
        "embedding": float(weights.get("embedding", 0.70)),
        "color": float(weights.get("color", 0.15)),
        "zone": float(weights.get("zone", 0.10)),
        "recency": float(weights.get("recency", 0.05)),
    }
    total = sum(w.values()) or 1.0
    base = (
        w["embedding"] * float(np.clip(embedding_sim, 0.0, 1.0))
        + w["color"] * float(np.clip(color_sim, 0.0, 1.0))
        + w["zone"] * float(np.clip(zone, 0.0, 1.0))
        + w["recency"] * float(np.clip(recency, 0.0, 1.0))
    ) / total
    bonus = float(np.clip(spatial_bonus, 0.0, 1.0)) * float(np.clip(spatial_iou, 0.0, 1.0))
    return float(min(1.0, base + bonus))


def decide(score: float, accept_threshold: float = 0.82, uncertain_threshold: float = 0.70) -> str:
    if score >= accept_threshold:
        return "matched"
    if score >= uncertain_threshold:
        return "ambiguous"
    return "new"


def pick_best(
    scored: list[tuple[int, float, str]],
    accept_threshold: float = 0.82,
    uncertain_threshold: float = 0.70,
) -> MatchDecision:
    """scored: [(track_id, score, reason)]，返回三态决策与候选列表。"""
    if not scored:
        return MatchDecision("new", None, 0.0, [], "没有同类物品可比对")
    ranked = sorted(scored, key=lambda x: x[1], reverse=True)
    best_id, best_score, reason = ranked[0]
    candidates = [(tid, s) for tid, s, _ in ranked if s >= uncertain_threshold][:3]
    status = decide(best_score, accept_threshold, uncertain_threshold)
    if status == "ambiguous":
        return MatchDecision("ambiguous", None, best_score, candidates, f"相似度处于灰区：{reason}")
    if status == "new":
        return MatchDecision("new", None, best_score, [], f"最高相似度 {best_score:.2f} 低于不确定阈值，视为新物品")
    return MatchDecision("matched", best_id, best_score, candidates, reason)