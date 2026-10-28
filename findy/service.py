"""Findy 自动采集服务：按固定间隔从采集源抓拍并入库。"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field

from .pipeline import FindyPipeline, ObserveResult
from .sources import SourceError, create_source

log = logging.getLogger(__name__)


@dataclass
class ServiceState:
    running: bool = False
    started_at: float | None = None
    interval_seconds: float = 60.0
    cycles: int = 0
    failures: int = 0
    last_error: str | None = None
    last_result: dict | None = None
    last_cycle_at: float | None = None
    consecutive_failures: int = 0

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "cycles": self.cycles,
            "failures": self.failures,
            "last_error": self.last_error,
            "last_cycle_at": self.last_cycle_at,
            "consecutive_failures": self.consecutive_failures,
            "last_result": self.last_result,
        }


class AutoCaptureService:
    def __init__(self, pipeline: FindyPipeline, interval_seconds: float):
        self.pipeline = pipeline
        self.interval = max(5.0, float(interval_seconds))
        self.state = ServiceState(interval_seconds=self.interval)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._source = None
        self._source_error: str | None = None

    # ---------------- 采集源 ----------------
    def source(self):
        if self._source is not None:
            return self._source
        try:
            cfg = self.pipeline.cfg
            from .config import REPO_ROOT

            self._source = create_source(cfg.capture, cfg.app, REPO_ROOT)
            self._source_error = None
        except SourceError as exc:
            self._source_error = str(exc)
            raise
        return self._source

    def capture_once(self) -> ObserveResult:
        """执行一次抓拍 + 入库；异常转成 ObserveResult，不抛出未处理错误。"""
        try:
            frame = self.source().capture()
        except SourceError as exc:
            return ObserveResult(ok=False, capture_id=0, duplicate=False, error=str(exc))
        except Exception as exc:
            log.exception("采集源异常")
            return ObserveResult(ok=False, capture_id=0, duplicate=False, error=f"{type(exc).__name__}: {exc}")
        try:
            return self.pipeline.observe(frame.jpeg, frame.meta)
        except Exception as exc:
            log.exception("流水线异常")
            return ObserveResult(ok=False, capture_id=0, duplicate=False, error=f"{type(exc).__name__}: {exc}")

    # ---------------- 后台循环 ----------------
    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = threading.Thread(target=self._loop, name="findy-auto-capture", daemon=True)
            self._thread.start()
            self.state.running = True
            self.state.started_at = time.time()
            return True

    def stop(self) -> bool:
        with self._lock:
            if not (self._thread and self._thread.is_alive()):
                self.state.running = False
                return False
            self._stop.set()
            self._thread.join(timeout=max(5.0, self.interval + 5))
            self.state.running = False
            return True

    def _loop(self) -> None:
        log.info("自动采集启动，间隔 %.0fs", self.interval)
        while not self._stop.is_set():
            result = self.capture_once()
            self.state.cycles += 1
            self.state.last_cycle_at = time.time()
            if result.ok:
                self.state.consecutive_failures = 0
                self.state.last_error = None
                self.state.last_result = result.to_dict()
            else:
                self.state.failures += 1
                self.state.consecutive_failures += 1
                self.state.last_error = result.error
                log.warning("自动采集失败: %s", result.error)
            self._stop.wait(self.interval)
        self.state.running = False
        log.info("自动采集停止")