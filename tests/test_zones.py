import pytest

from findy.zones import assign_region, describe_position, load_regions, point_in_polygon


def test_point_in_polygon_square():
    square = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    assert point_in_polygon(0.5, 0.5, square)
    assert not point_in_polygon(1.5, 0.5, square)
    assert not point_in_polygon(0.5, -0.1, square)
    assert not point_in_polygon(0.5, 0.5, [])  # 空多边形（未标定）


def test_load_regions_skips_empty_polygon(tmp_path):
    path = tmp_path / "zones.yaml"
    path.write_text(
        """
regions:
  - name: 左
    polygon: [[0,0],[0.5,0],[0.5,1],[0,1]]
  - name: 未标定
    polygon: []
""",
        encoding="utf-8",
    )
    regions = load_regions(path)
    assert len(regions) == 2
    assert regions[1].contains(0.5, 0.5) is False


def test_assign_region_by_bbox_center(regions):
    left_box = (10, 100, 90, 180)      # 中心 x≈0.16
    center_box = (150, 100, 210, 180)  # 中心 x≈0.56
    right_box = (250, 100, 310, 180)   # 中心 x≈0.87
    assert assign_region(left_box, 320, 240, regions).name == "桌面左侧"
    assert assign_region(center_box, 320, 240, regions).name == "桌面中央"
    assert assign_region(right_box, 320, 240, regions).name == "桌面右侧"


def test_assign_region_fallback_when_uncalibrated():
    no_regions = load_regions(__import__("pathlib").Path("config/zones.yaml"))
    no_regions = [r for r in no_regions if len(r.polygon) < 3]
    assert assign_region((10, 10, 90, 60), 320, 240, no_regions) is None
    label, kind = describe_position((10, 10, 90, 60), 320, 240, no_regions)
    assert label.startswith("画面") and kind == "frame_grid"


def test_default_zones_cover_full_frame(regions):
    calibrated = [r for r in regions if len(r.polygon) >= 3]
    assert {r.name for r in calibrated} == {"桌面左侧", "桌面中央", "桌面右侧"}
    # 每一列都能命中某个区域
    for x in (0.1, 0.5, 0.9):
        box = (x * 320 - 5, 100, x * 320 + 5, 120)
        assert assign_region(box, 320, 240, regions) is not None