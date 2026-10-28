from pathlib import Path

import pytest

from findy.config import load_config
from findy.util import (
    fmt_bbox,
    humanize_delta,
    is_valid_jpeg,
    iso_to_epoch,
    local_display,
    parse_bbox,
    parse_iso,
    sha256_bytes,
    to_iso,
    utc_now_iso,
)

REPO_ROOT = Path(__file__).resolve().parent.parent


def write_config(tmp_path, source="replay", extra=""):
    path = tmp_path / "cfg.yaml"
    path.write_text(
        f"""
app:
  data_dir: "{tmp_path.as_posix()}/data"
  db_path: "{tmp_path.as_posix()}/data/f.sqlite"
capture:
  source: {source}
  replay:
    dir: "{tmp_path.as_posix()}/frames"
{extra}
""",
        encoding="utf-8",
    )
    return path


def test_load_config_from_yaml(tmp_path):
    cfg = load_config(write_config(tmp_path))
    assert cfg.capture.source == "replay"
    assert cfg.app.tz == "Asia/Shanghai"
    assert cfg.db_path == tmp_path / "data" / "f.sqlite"


def test_load_config_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_load_config_invalid_source_raises(tmp_path):
    with pytest.raises(ValueError):
        load_config(write_config(tmp_path, source="cloud"))


def test_load_config_env_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("FINDY_DETECTOR_MODEL", "models/custom-detector")
    monkeypatch.setenv("FINDY_CAPTURE_SOURCE", "esp32")
    cfg = load_config(write_config(tmp_path))
    assert cfg.detector.model == "models/custom-detector"
    assert cfg.capture.source == "esp32"


def test_local_display_and_humanize():
    local = local_display("2026-10-28T02:00:00Z", "Asia/Shanghai")
    assert local == "2026-10-28 10:00:00"
    assert humanize_delta("2026-10-28T02:00:00Z").endswith("前")
    assert "未来" in humanize_delta("2999-01-01T00:00:00Z")


def test_iso_epoch_roundtrip():
    iso = "2026-10-28T02:00:00Z"
    epoch = iso_to_epoch(iso)
    assert epoch is not None
    assert parse_iso(iso).year == 2026
    assert to_iso(parse_iso(iso)) == iso


def test_bbox_format_roundtrip():
    assert fmt_bbox((1, 2, 3.5, 4)) == "1.00,2.00,3.50,4.00"
    assert parse_bbox("1,2,3.5,4") == (1.0, 2.0, 3.5, 4.0)
    with pytest.raises(ValueError):
        parse_bbox("1,2,3")


def test_jpeg_and_sha():
    assert is_valid_jpeg(b"\xff\xd8abc\xff\xd9")
    assert not is_valid_jpeg(b"")
    assert sha256_bytes(b"abc").startswith("ba7816bf")


def test_utc_now_iso_is_iso():
    assert parse_iso(utc_now_iso()) is not None