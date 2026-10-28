from findy.db import Database
from findy.util import utc_now_iso


def make_capture(db: Database, device_seq: int | None, synced: bool = True) -> tuple[int, bool]:
    return db.add_capture(
        {
            "camera_id": 1,
            "device_seq": device_seq,
            "captured_at_utc": "2026-10-28T02:00:00Z" if synced else None,
            "captured_at_local": "2026-10-28 10:00:00" if synced else None,
            "epoch_s": 1.0 if synced else None,
            "time_synced": int(synced),
            "time_source": "sntp" if synced else "sntp_unsynced",
            "uptime_ms": 1000,
            "received_at_utc": utc_now_iso(),
            "file_path": "data/images/x.jpg",
            "image_width": 320,
            "image_height": 240,
            "image_bytes": 1234,
            "sha256": "abc",
            "source_ref": "unit-test",
            "status": "ok",
        }
    )


def test_capture_idempotent_by_device_seq(db):
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    first_id, created = make_capture(db, 7)
    assert created is True
    second_id, created_again = make_capture(db, 7)
    assert created_again is False
    assert first_id == second_id
    assert db.count_captures() == 1


def test_null_device_seq_allows_multiple(db):
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    id1, _ = make_capture(db, None)
    id2, _ = make_capture(db, None)
    assert id1 != id2
    assert db.count_captures() == 2


def test_catalog_and_regions_sync(db, catalog, regions):
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    class_map = db.sync_catalog(catalog)
    assert class_map["杯子"] > 0
    assert db.class_name(class_map["杯子"]) == "杯子"
    region_map = db.sync_regions(1, regions)
    assert "桌面左侧" in region_map
    assert db.region_name(region_map["桌面左侧"]) == "桌面左侧"


def test_track_lifecycle_and_stats(db, catalog):
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    class_map = db.sync_catalog(catalog)
    import numpy as np

    emb = np.ones(8, dtype=np.float32) / np.sqrt(8)
    hist = np.ones(15, dtype=np.float32) / 15
    track_id = db.create_track(
        class_id=class_map["杯子"],
        label="杯子",
        color="白色",
        color_hex="#ffffff",
        prototype=emb,
        color_hist=hist,
        seen_iso="2026-10-28T02:00:00Z",
        capture_id=None,
        region_id=None,
    )
    track = db.get_track(track_id)
    assert track is not None
    assert track["label"] == "杯子"
    assert track["prototype_n"] == 1
    db.update_track_label(track_id, "我的杯子")
    assert db.get_track(track_id)["label"] == "我的杯子"
    stats = db.stats()
    assert stats["active_tracks"] == 1
    assert stats["captures"] == 0


def test_merge_tracks_moves_detections(db, catalog):
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    class_map = db.sync_catalog(catalog)
    import numpy as np

    emb = np.ones(4, dtype=np.float32) / 2
    hist = np.ones(15, dtype=np.float32) / 15
    capture_id, _ = make_capture(db, 1)
    t1 = db.create_track(class_map["杯子"], "杯子", None, None, emb, hist, None, capture_id, None)
    t2 = db.create_track(class_map["杯子"], "杯子2", None, None, emb, hist, None, capture_id, None)
    det_id = db.add_detection(
        {
            "capture_id": capture_id,
            "track_id": t2,
            "class_id": class_map["杯子"],
            "region_id": None,
            "region_name": "桌面左侧",
            "bbox_norm": "0.1,0.1,0.3,0.3",
            "bbox_px": "10,10,30,30",
            "conf": 0.9,
            "crop_path": None,
            "embedding": emb.tobytes(),
            "color_hex": "#ffffff",
            "link_score": 0.5,
            "link_method": "new",
            "link_status": "new",
            "captured_at_utc": None,
            "created_at_utc": utc_now_iso(),
        }
    )
    db.merge_tracks(t2, t1)
    assert db.get_track(t2)["status"] == "merged"
    # merge 后 detection 归属目标 track
    with db.connect() as conn:
        row = conn.execute("SELECT track_id FROM detections WHERE id=?", (det_id,)).fetchone()
    assert row["track_id"] == t1


def test_query_log_and_feedback(db):
    db.ensure_camera("default", "replay", "test", 320, 240, "Asia/Shanghai")
    db.log_query("杯子在哪", {"intent": "last_seen"}, "rule", 1, "桌面左侧", 12)
    assert db.recent_queries(1)[0]["raw_text"] == "杯子在哪"
    fid = db.add_feedback(None, None, "confirm", {"note": "ok"})
    assert fid > 0