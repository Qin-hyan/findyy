import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw

from findy.query import answer
from findy.sources import CaptureMeta

TZ = ZoneInfo("Asia/Shanghai")


def make_frame(cup_box=(20, 100, 100, 190), color=(150, 60, 50), size=(320, 240)) -> bytes:
    im = Image.new("RGB", size, (25, 25, 28))
    d = ImageDraw.Draw(im)
    d.rectangle(cup_box, fill=color)
    d.rectangle((180, 100, 230, 190), fill=(60, 60, 150))
    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def meta(iso: str | None = "2026-10-28T02:00:00Z", synced: bool = True, seq: int | None = None) -> CaptureMeta:
    local = None
    if synced and iso:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        local = dt.astimezone(TZ).strftime("%Y-%m-%d %H:%M:%S")
    return CaptureMeta(
        source="upload",
        source_ref="unit-test.jpg",
        camera_name="test",
        time_synced=synced,
        time_source="client" if synced else "client_unsynced",
        captured_at_utc=iso if synced else None,
        captured_at_local=local,
        epoch_s=None,
        device_seq=seq,
    )


def test_observe_creates_capture_detections_and_tracks(pipeline, config):
    result = pipeline.observe(make_frame(), meta())
    assert result.ok and not result.duplicate
    assert result.capture_id > 0
    assert len(result.detections) == 2
    classes = {d["class"] for d in result.detections}
    assert classes == {"杯子", "手机"}
    cup = next(d for d in result.detections if d["class"] == "杯子")
    assert cup["link_status"] == "new"
    assert cup["region"] == "桌面左侧"
    assert cup["crop_url"].startswith("/api/detections/")

    capture = pipeline.db.get_capture(result.capture_id)
    assert capture["time_synced"] == 1
    assert capture["captured_at_utc"] == "2026-10-28T02:00:00Z"
    assert (config.images_dir / "2026/10/28").exists()
    assert (config.crops_dir / str(result.capture_id)).exists()


def test_same_object_across_observations_is_linked(pipeline, config, catalog, regions):
    first = pipeline.observe(make_frame(), meta("2026-10-28T02:00:00Z"))
    cup_id = next(d["track_id"] for d in first.detections if d["class"] == "杯子")
    second = pipeline.observe(make_frame(), meta("2026-10-28T02:05:00Z"))
    cup2 = next(d for d in second.detections if d["class"] == "杯子")
    assert cup2["track_id"] == cup_id
    assert cup2["link_status"] == "matched"
    assert pipeline.db.track_sighting_count(cup_id) == 2

    result = answer(pipeline.db, config, catalog, regions, "杯子在哪？")
    assert result["status"] == "found"
    assert "桌面左侧" in result["answer"]
    assert "2026-10-28 10:05" in result["answer"]
    assert result["results"][0]["sightings"] == 2
    assert result["results"][0]["evidence_image_url"].startswith("/api/captures/")


def test_moved_query_detects_region_change(pipeline, config, catalog, regions):
    pipeline.detector.annotations = [
        {"class_zh": "杯子", "confidence": 0.9, "bbox_px": [30.0, 100.0, 70.0, 140.0]}
    ]
    pipeline.observe(make_frame(cup_box=(30, 100, 70, 140)), meta("2026-10-28T02:00:00Z"))
    # 杯子真的被挪到画面右侧：图像内容与检测框一起变化（不是只改框）
    pipeline.detector.annotations = [
        {"class_zh": "杯子", "confidence": 0.9, "bbox_px": [250.0, 100.0, 290.0, 140.0]}
    ]
    pipeline.observe(make_frame(cup_box=(250, 100, 290, 140)), meta("2026-10-28T02:05:00Z"))
    result = answer(pipeline.db, config, catalog, regions, "杯子移动过吗？")
    assert result["intent"] == "moved"
    assert "移动过" in result["answer"]
    assert "桌面左侧" in result["answer"] and "桌面右侧" in result["answer"]


def test_unsynced_time_is_reported_not_faked(pipeline, config, catalog, regions):
    pipeline.observe(make_frame(), meta("2026-10-28T02:00:00Z"))
    pipeline.observe(make_frame(), meta(None, synced=False))
    capture = pipeline.db.list_captures(1)[0]
    assert capture["time_synced"] == 0
    assert capture["captured_at_utc"] is None
    result = answer(pipeline.db, config, catalog, regions, "杯子在哪？")
    assert "未同步" in result["answer"]
    assert result["results"][0]["time_synced"] is False


def test_duplicate_device_seq_is_idempotent(pipeline):
    first = pipeline.observe(make_frame(), meta(seq=42))
    second = pipeline.observe(make_frame(), meta("2026-10-28T02:05:00Z", seq=42))
    assert first.capture_id == second.capture_id
    assert second.duplicate is True
    assert second.warnings
    assert pipeline.db.count_captures() == 1


def test_not_found_and_help_answers(pipeline, config, catalog, regions):
    pipeline.observe(make_frame(), meta())
    not_found = answer(pipeline.db, config, catalog, regions, "钥匙在哪？")
    assert not_found["status"] == "not_found"
    assert "没有找到" in not_found["answer"]
    help_answer = answer(pipeline.db, config, catalog, regions, "你好")
    assert help_answer["status"] == "help"
    assert "我可以" in help_answer["answer"]


def test_list_and_count_queries(pipeline, config, catalog, regions):
    pipeline.observe(make_frame(), meta())
    listed = answer(pipeline.db, config, catalog, regions, "桌上都有哪些东西？")
    assert listed["status"] == "found"
    assert "杯子" in listed["answer"] and "手机" in listed["answer"]
    counted = answer(pipeline.db, config, catalog, regions, "杯子有几个？")
    assert counted["status"] == "found"
    assert "1 个" in counted["answer"]


def test_history_prefers_latest_events(pipeline, config, catalog, regions):
    for i in range(3):
        pipeline.observe(make_frame(), meta(f"2026-10-28T02:0{i}:00Z"))
    result = answer(pipeline.db, config, catalog, regions, "杯子是什么时候最后一次看到的？")
    assert result["intent"] == "history"
    assert result["results"][0]["events"][0]["time_local"] == "2026-10-28 10:02:00"
    assert len(result["results"][0]["events"]) == 3


def test_detector_failure_is_recorded_not_swallowed(pipeline, monkeypatch):
    def boom(image):
        raise RuntimeError("model crashed")

    monkeypatch.setattr(pipeline.detector, "detect", boom)
    result = pipeline.observe(make_frame(), meta())
    assert result.ok is False
    assert "检测失败" in (result.error or "")
    capture = pipeline.db.get_capture(result.capture_id)
    assert capture["status"] == "detect_failed"
    # 图片仍被保存，便于事后排障
    assert (pipeline.cfg.images_dir / "2026" / "10" / "28").exists()


def test_every_detection_has_zone_and_evidence(pipeline):
    result = pipeline.observe(make_frame(), meta())
    zones = {d["region"] for d in result.detections}
    assert zones.issubset({"桌面左侧", "桌面中央", "桌面右侧"})
    with pipeline.db.connect() as conn:
        rows = conn.execute("SELECT crop_path, embedding, region_name FROM detections").fetchall()
    assert len(rows) == 2
    for row in rows:
        assert row["crop_path"] and row["embedding"] and row["region_name"]