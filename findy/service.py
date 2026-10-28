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
    last_error_at: float | None = None
    last_result: dict | None = None
    last_cycle_at: float | None = None
    consecutive_failures: int = 0
    capture_in_progress: bool = False

    def to_dict(self) -> dict:
        return {
            "running": self.running,
            "interval_seconds": self.interval_seconds,
            "cycles": self.cycles,
            "failures": self.failures,
            "last_error": self.last_error,
            "last_error_at": self.last_error_at,
            "last_cycle_at": self.last_cycle_at,
            "consecutive_failures": self.consecutive_failures,
            "capture_in_progress": self.capture_in_progress,
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
        self._capture_lock = threading.Lock()
        self._source = None
        self._source_error: str | None = None
        # 自动采集循环的结果回调（用于把真实事件写入当前验收运行；可为 None）
        self.on_result = None

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

    def reset_source(self) -> None:
        """丢弃缓存的采集源，下次抓拍按当前配置重建（用于会话级切换/恢复）。"""
        self._source = None
        self._source_error = None

    def capture_once(self) -> ObserveResult:
        """执行一次抓拍 + 入库；异常转成 ObserveResult，不抛出未处理错误。

        使用锁串行化手动抓拍与自动采集，避免同一设备/回放源被并发消费。
        """
        with self._capture_lock:
            self.state.capture_in_progress = True
            try:
                return self._capture_once_locked()
            finally:
                self.state.capture_in_progress = False

    def _capture_once_locked(self) -> ObserveResult:
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
            started = time.perf_counter()
            result = self.capture_once()
            elapsed_ms = int((time.perf_counter() - started) * 1000)
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
                self.state.last_error_at = time.time()
                log.warning("自动采集失败: %s", result.error)
            if self.on_result is not None:
                try:
                    self.on_result(result, elapsed_ms)
                except Exception:
                    log.exception("自动采集结果回调失败")
            self._stop.wait(self.interval)
        self.state.running = False
        log.info("自动采集停止")