import numpy as np
import pytest

from findy.matcher import (
    bbox_iou,
    combined_score,
    cosine_similarity,
    decide,
    pick_best,
    recency_score,
    zone_prior,
)

WEIGHTS = {"embedding": 0.70, "color": 0.15, "zone": 0.10, "recency": 0.05}


def test_cosine_similarity_edge_cases():
    a = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    b = np.array([1.0, 0.0, 0.0], dtype=np.float32)
    c = np.array([0.0, 1.0, 0.0], dtype=np.float32)
    assert cosine_similarity(a, b) == 1.0
    assert cosine_similarity(a, c) == 0.0
    assert cosine_similarity(None, b) == 0.0
    assert cosine_similarity(a, np.zeros(3, dtype=np.float32)) == 0.0


def test_zone_prior_values():
    assert zone_prior(1, 1) == 1.0
    assert zone_prior(1, 2) == 0.35
    assert zone_prior(None, 2) == 0.6


def test_recency_score_decays():
    from findy.util import utc_now_iso

    now_score = recency_score(utc_now_iso(), tau_hours=24)
    old_score = recency_score("2020-01-01T00:00:00Z", tau_hours=24)
    assert now_score > 0.9
    assert old_score < 0.01
    assert recency_score(None) == 0.5


def test_combined_score_bounds_and_weights():
    perfect = combined_score(1.0, 1.0, 1.0, 1.0, WEIGHTS)
    worst = combined_score(0.0, 0.0, 0.0, 0.0, WEIGHTS)
    assert perfect == 1.0
    assert worst == 0.0
    # 权重之和不为 1 时也要归一化
    assert combined_score(1.0, 1.0, 1.0, 1.0, {"embedding": 2.0}) == 1.0


def test_decide_thresholds():
    assert decide(0.9) == "matched"
    assert decide(0.82) == "matched"
    assert decide(0.75) == "ambiguous"
    assert decide(0.70) == "ambiguous"
    assert decide(0.69) == "new"
    assert decide(0.0) == "new"


def test_bbox_iou():
    a = (0.0, 0.0, 0.5, 0.5)
    assert bbox_iou(a, a) == pytest.approx(1.0)
    assert bbox_iou(a, (0.5, 0.5, 1.0, 1.0)) == pytest.approx(0.0)
    assert bbox_iou(a, (0.25, 0.0, 0.75, 0.5)) == pytest.approx(1.0 / 3.0)
    assert bbox_iou(None, a) == 0.0
    assert bbox_iou((0, 0, 0, 0), a) == 0.0


def test_combined_score_spatial_bonus():
    base = combined_score(0.8, 1.0, 1.0, 1.0, WEIGHTS, spatial_iou=0.0, spatial_bonus=0.0)
    boosted = combined_score(0.8, 1.0, 1.0, 1.0, WEIGHTS, spatial_iou=1.0, spatial_bonus=0.15)
    assert boosted > base
    assert boosted <= 1.0
    # 关闭加分时与旧行为一致
    off = combined_score(0.8, 1.0, 1.0, 1.0, WEIGHTS, spatial_iou=1.0, spatial_bonus=0.0)
    assert off == pytest.approx(base)


def test_pick_best_three_states():
    matched = pick_best([(1, 0.91, "ok"), (2, 0.72, "weak")])
    assert matched.status == "matched" and matched.best_track_id == 1
    assert matched.candidates == [(1, 0.91), (2, 0.72)]

    ambiguous = pick_best([(1, 0.78, "gray")])
    assert ambiguous.status == "ambiguous" and ambiguous.best_track_id is None

    new = pick_best([(1, 0.4, "far")])
    assert new.status == "new" and new.candidates == []

    none = pick_best([])
    assert none.status == "new" and none.best_score == 0.0