"""ESP32 M1 固件 HTTP 适配器的集成测试（用本地 mock 服务器，不依赖真实硬件）。"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from findy.sources import Esp32Source, ReplaySource, SourceError


def jpeg_bytes(size=(32, 24)) -> bytes:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, (120, 80, 40)).save(buf, format="JPEG", quality=90)
    return buf.getvalue()


class MockFirmwareHandler(BaseHTTPRequestHandler):
    """模拟 Findy M1 固件的三个接口语义。"""

    jpeg = jpeg_bytes()
    seq = 0
    synced = True
    stale_seq = False

    def log_message(self, *args):  # 静默
        return

    def _json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.startswith("/api/status"):
            self._json({"device": "ESP32-S3-EYE", "wifi": {"connected": True}})
        elif self.path.startswith("/api/photo"):
            if "seq=" in self.path:
                want = int(self.path.split("seq=")[1].split("&")[0])
                if want != type(self).seq:
                    self._json({"error": "photo_expired", "available_seq": type(self).seq}, status=404)
                    return
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("X-Capture-Seq", str(type(self).seq))
            self.send_header("Content-Length", str(len(type(self).jpeg)))
            self.end_headers()
            self.wfile.write(type(self).jpeg)
        else:
            self._json({"error": "not_found"}, status=404)

    def do_POST(self):
        if self.path.startswith("/api/capture"):
            type(self).seq += 1
            response_seq = type(self).seq - 1 if type(self).stale_seq else type(self).seq
            rec = {
                "seq": response_seq,
                "ok": True,
                "jpeg_valid": True,
                "bytes": len(type(self).jpeg),
                "width": 32,
                "height": 24,
                "latency_ms": 60,
                "uptime_ms": 5000,
                "time_synced": type(self).synced,
                "epoch_s": 1793000000 if type(self).synced else None,
                "local_time": "2026-10-28 10:00:00" if type(self).synced else None,
                "error": None,
            }
            self._json({"capture": rec, "stats": {"total": type(self).seq, "ok": type(self).seq, "fail": 0}})
        else:
            self._json({"error": "not_found"}, status=404)


@pytest.fixture()
def firmware_server():
    MockFirmwareHandler.seq = 0
    MockFirmwareHandler.synced = True
    MockFirmwareHandler.stale_seq = False
    server = ThreadingHTTPServer(("127.0.0.1", 0), MockFirmwareHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()
    thread.join(timeout=3)


def test_esp32_probe(firmware_server):
    source = Esp32Source(firmware_server, timeout=5)
    status = source.probe()
    assert status["device"] == "ESP32-S3-EYE"


def test_esp32_capture_roundtrip(firmware_server):
    from datetime import datetime, timezone

    source = Esp32Source(firmware_server, timeout=5)
    frame = source.capture()
    assert frame.meta.source == "esp32"
    assert frame.meta.device_seq == 1
    assert frame.meta.time_synced is True
    expected = datetime.fromtimestamp(1793000000, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    assert frame.meta.captured_at_utc == expected
    assert frame.jpeg.startswith(b"\xff\xd8") and frame.jpeg.endswith(b"\xff\xd9")


def test_esp32_unsynced_time_is_null(firmware_server):
    MockFirmwareHandler.synced = False
    source = Esp32Source(firmware_server, timeout=5)
    frame = source.capture()
    assert frame.meta.time_synced is False
    assert frame.meta.captured_at_utc is None
    assert frame.meta.time_source == "sntp_unsynced"
    assert frame.meta.uptime_ms == 5000


def test_esp32_unreachable_raises_source_error():
    source = Esp32Source("http://127.0.0.1:1", timeout=1, retries=0)
    with pytest.raises(SourceError):
        source.capture()


def test_esp32_stale_seq_is_rejected(firmware_server):
    MockFirmwareHandler.stale_seq = True
    source = Esp32Source(firmware_server, timeout=5, retries=0)
    with pytest.raises(SourceError):
        source.capture()


def test_replay_source_time_from_filename(tmp_path):
    img = jpeg_bytes()
    (tmp_path / "2026-10-28T10-00-00_a.jpg").write_bytes(img)
    (tmp_path / "no-time.jpg").write_bytes(img)
    source = ReplaySource(tmp_path, "Asia/Shanghai")
    first = source.capture()
    assert first.meta.time_synced is True
    assert first.meta.captured_at_utc == "2026-10-28T02:00:00Z"
    second = source.capture()
    assert second.meta.time_synced is False
    assert second.meta.captured_at_utc is None


def test_replay_source_sidecar_metadata(tmp_path):
    img = jpeg_bytes()
    (tmp_path / "frame.jpg").write_bytes(img)
    (tmp_path / "frame.json").write_text(
        json.dumps({"captured_at_utc": "2026-10-27T23:30:00Z"}), encoding="utf-8"
    )
    source = ReplaySource(tmp_path)
    frame = source.capture()
    assert frame.meta.time_synced is True
    assert frame.meta.captured_at_utc == "2026-10-27T23:30:00Z"
    with pytest.raises(SourceError):
        source.capture()  # 非 loop 模式第二次即用尽