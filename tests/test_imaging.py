import io

import numpy as np
import pytest
from PIL import Image

from findy.imaging import (
    bbox_area_ratio,
    color_features,
    color_similarity,
    crop_with_margin,
    is_valid_jpeg,
    load_image,
    nms,
)


def jpeg_bytes(color, size=(120, 90)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="JPEG", quality=95)
    return buf.getvalue()


def test_valid_jpeg_detection():
    data = jpeg_bytes((10, 20, 30))
    assert is_valid_jpeg(data)
    assert not is_valid_jpeg(b"not a jpeg")
    assert not is_valid_jpeg(b"\xff\xd8truncated")


def test_load_image_rejects_non_jpeg():
    with pytest.raises(ValueError):
        load_image(b"GIF89a....")


def test_crop_with_margin_and_small_box():
    image = Image.new("RGB", (200, 100), (0, 0, 0))
    crop = crop_with_margin(image, (50, 20, 150, 80), margin_ratio=0.1)
    assert crop is not None
    assert crop.width > 100 and crop.height > 60
    assert crop_with_margin(image, (10, 10, 14, 14), min_side=12) is None
    assert crop_with_margin(image, (60, 20, 60, 80)) is None


def test_bbox_area_ratio():
    assert bbox_area_ratio((0, 0, 100, 50), 200, 100) == pytest.approx(0.25)
    assert bbox_area_ratio((10, 10, 5, 5), 200, 100) == 0.0


def test_red_vs_blue_color_features_differ():
    red = Image.new("RGB", (60, 60), (200, 30, 30))
    blue = Image.new("RGB", (60, 60), (30, 30, 200))
    hex_r, name_r, hist_r = color_features(red)
    hex_b, name_b, hist_b = color_features(blue)
    assert name_r == "红色"
    assert name_b == "蓝色"
    assert hex_r != hex_b
    assert color_similarity(hist_r, hist_b) < 0.6
    assert color_similarity(hist_r, hist_r) == pytest.approx(1.0)


def test_gray_classification():
    white = Image.new("RGB", (40, 40), (245, 245, 245))
    black = Image.new("RGB", (40, 40), (8, 8, 8))
    gray = Image.new("RGB", (40, 40), (128, 128, 128))
    assert color_features(white)[1] == "白色"
    assert color_features(black)[1] == "黑色"
    assert color_features(gray)[1] == "灰色"


def test_nms_filters_overlapping_boxes():
    boxes = [(0, 0, 100, 100), (5, 5, 100, 100), (200, 200, 300, 300)]
    scores = [0.9, 0.8, 0.7]
    keep = nms(boxes, scores, iou_threshold=0.4)
    assert keep == [0, 2]


def test_color_similarity_handles_missing():
    assert color_similarity(None, None) == 0.5
    assert color_similarity(np.zeros(15), np.zeros(15)) == 1.0