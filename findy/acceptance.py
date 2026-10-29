"""Findy 端到端验收运行：事件记录、证据判定与脱敏导出。

设计原则（与验收要求一致）：
- 结论只依据本机实际发生的事件与数据库记录计算，没有操作就是 NOT_VERIFIED；
- replay 数据可以作为“明确标注的模拟演示”参与演示运行，但绝不让真机项通过；
- 设备离线、模型未就绪、检测失败、查询无结果时如实区分 FAIL / NOT_VERIFIED；
- 导出内容不含图像数据，设备地址与绝对路径脱敏。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

from .config import REPO_ROOT, Config
from .db import Database
from .util import utc_now_iso

PASS = "PASS"
FAIL = "FAIL"
NOT_VERIFIED = "NOT_VERIFIED"

# 判定逻辑版本：重复帧/来源规则变化时递增，让旧的 summary 重新计算而不是沿用错误结论。
EVALUATOR_VERSION = 2

MODES = {"real_device", "replay_demo"}
SOURCE_KINDS = {"esp32", "replay", "upload", "webcam", "unknown"}

ITEM_TITLES = {
    "device_connection": "设备连接",
    "capture": "真实抓拍",
    "detection": "检测",
    "storage": "存储",
    "track_link": "轨迹关联",
    "query": "查询",
}

_STATUS_ZH = {PASS: "通过", FAIL: "失败", NOT_VERIFIED: "未验证"}


# ---------------- 基础工具 ----------------
def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _as_list(value) -> list:
    return value if isinstance(value, list) else []


def _load_detail(event: dict) -> dict:
    raw = event.get("detail_json")
    if not raw:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return {}


def public_run(run: dict | None) -> dict | None:
    if not run:
        return None
    # 前端/页面只展示可读的来源标记，不暴露本机绝对路径或真实设备 IP。
    ref = run.get("source_ref")
    if ref:
        ref = mask_device_url(str(ref)) if "://" in str(ref) else Path(str(ref)).name
    return {
        "id": int(run["id"]),
        "mode": run.get("mode"),
        "source_kind": run.get("source_kind"),
        "source_ref": ref,
        "started_at_utc": run.get("started_at_utc"),
        "finished_at_utc": run.get("finished_at_utc"),
        "status": run.get("status"),
    }


def normalize_base_url(raw: str) -> str:
    """允许输入裸 IP；只接受 http(s)，拒绝账号密码/路径/查询串。"""
    text = (raw or "").strip()
    if not text:
        raise ValueError("设备地址不能为空")
    if not text.lower().startswith(("http://", "https://")):
        text = "http://" + text
    parts = urlsplit(text)
    if parts.scheme not in {"http", "https"}:
        raise ValueError("只支持 http:// 或 https:// 地址")
    if not parts.hostname:
        raise ValueError("设备地址缺少主机名/IP")
    if parts.username or parts.password:
        raise ValueError("设备地址不允许携带账号密码")
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        raise ValueError("设备地址只填写到主机和端口，例如 http://<设备IP>")
    host = parts.hostname
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = f":{parts.port}" if parts.port else ""
    return f"{parts.scheme}://{host}{port}"


def mask_device_url(url: str | None) -> str | None:
    if not url:
        return url
    try:
        parts = urlsplit(str(url))
        if not parts.scheme or not parts.hostname:
            return str(url)
        port = f":{parts.port}" if parts.port else ""
        return f"{parts.scheme}://<device-ip>{port}"
    except ValueError:
        return "<device-ip>"


def summarize_device_status(status: dict) -> dict:
    """把固件 /api/status 提炼成界面可读摘要（不包含 MAC 等无关信息）。"""
    status = _as_dict(status)
    wifi = _as_dict(status.get("wifi"))
    time_info = _as_dict(status.get("time"))
    camera = _as_dict(status.get("camera"))
    stats = _as_dict(status.get("stats"))
    return {
        "device": status.get("device"),
        "firmware": status.get("firmware"),
        "build": status.get("build"),
        "uptime_ms": status.get("uptime_ms"),
        "wifi": {
            "connected": wifi.get("connected"),
            "configured": wifi.get("configured"),
            "ip": wifi.get("ip"),
            "rssi": wifi.get("rssi"),
            "rssi_valid": wifi.get("rssi_valid"),
        },
        "time": {
            "synced": time_info.get("synced"),
            "local": time_info.get("local"),
            "utc": time_info.get("utc"),
            "timezone": time_info.get("timezone"),
        },
        "camera": {
            "ready": camera.get("ready"),
            "sensor": camera.get("sensor"),
            "pid": camera.get("pid"),
            "width": camera.get("width"),
            "height": camera.get("height"),
        },
        "capture_stats": {
            "total": stats.get("total"),
            "ok": stats.get("ok"),
            "fail": stats.get("fail"),
        },
    }


def _device_evidence(summary: dict | None, url: str | None) -> list[dict]:
    summary = _as_dict(summary)
    wifi = _as_dict(summary.get("wifi"))
    time_info = _as_dict(summary.get("time"))
    camera = _as_dict(summary.get("camera"))
    evidence: list[dict] = []
    if url:
        evidence.append({"label": "设备地址", "value": mask_device_url(url) or url})
    if summary.get("device") or summary.get("firmware"):
        evidence.append(
            {
                "label": "设备",
                "value": " ".join(
                    str(v) for v in (summary.get("device"), summary.get("firmware")) if v
                ),
            }
        )
    if camera:
        evidence.append(
            {
                "label": "摄像头",
                "value": (
                    f"ready={camera.get('ready')} · 传感器={camera.get('sensor') or '未知'}"
                    f" · {camera.get('width') or '?'}×{camera.get('height') or '?'}"
                ),
            }
        )
    if wifi:
        evidence.append(
            {
                "label": "Wi-Fi",
                "value": (
                    f"connected={wifi.get('connected')} · 信号 {wifi.get('rssi')} dBm"
                    if wifi.get("rssi") is not None
                    else f"connected={wifi.get('connected')}"
                ),
            }
        )
    if time_info:
        evidence.append(
            {
                "label": "设备时间",
                "value": f"synced={time_info.get('synced')} · {time_info.get('local') or '—'}",
            }
        )
    return evidence


def _capture_time_text(capture: dict) -> str:
    if bool(capture.get("time_synced")):
        return str(capture.get("captured_at_local") or capture.get("captured_at_utc") or "时间未知")
    return "时间未同步"


def _capture_provenance_text(capture: dict) -> str:
    kind = capture.get("source_kind") or "unknown"
    mapping = {"esp32": "真实设备", "replay": "回放演示", "upload": "上传", "unknown": "未知来源"}
    return f"{mapping.get(kind, kind)} ({kind})"


def _resolve_path(path_str: str | None) -> Path | None:
    if not path_str:
        return None
    path = Path(str(path_str))
    return path if path.is_absolute() else REPO_ROOT / path


def _relative_path(path_str: str | None) -> str | None:
    path = _resolve_path(path_str)
    if path is None:
        return None
    try:
        return path.relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return path.name


# ---------------- 运行事件记录 ----------------
class AcceptanceRecorder:
    """把本机真实操作写入当前验收运行；没有进行中的运行时静默跳过。"""

    def __init__(self, db: Database, cfg: Config):
        self.db = db
        self.cfg = cfg

    def _active(self) -> dict | None:
        try:
            return self.db.active_acceptance_run()
        except Exception:
            return None

    def record_probe(self, ok: bool, url: str, summary: dict | None, error: str | None) -> None:
        run = self._active()
        if not run:
            return
        self.db.add_acceptance_event(
            int(run["id"]),
            "probe",
            ok,
            source_kind="esp32" if ok else None,
            detail={"url": url, "summary": summary, "error": error},
        )

    def record_connect(self, ok: bool, url: str, summary: dict | None, error: str | None) -> None:
        run = self._active()
        if not run:
            return
        self.db.add_acceptance_event(
            int(run["id"]),
            "connect",
            ok,
            source_kind="esp32" if ok else None,
            detail={"url": url, "summary": summary, "error": error},
        )

    def record_capture(self, result, latency_ms: int) -> None:
        run = self._active()
        if not run:
            return
        capture = getattr(result, "capture", None) or {}
        source_kind = capture.get("source_kind") or self.cfg.capture.source
        if source_kind not in SOURCE_KINDS:
            source_kind = "unknown"
        detail = {
            "duplicate": bool(getattr(result, "duplicate", False)),
            "detections_count": len(getattr(result, "detections", None) or []),
            "error": getattr(result, "error", None),
            "warnings": list(getattr(result, "warnings", None) or []),
            "capture": {
                "id": capture.get("id"),
                "captured_at_local": capture.get("captured_at_local"),
                "captured_at_utc": capture.get("captured_at_utc"),
                "time_synced": capture.get("time_synced"),
                "time_source": capture.get("time_source"),
                "source_kind": source_kind,
                "width": capture.get("width"),
                "height": capture.get("height"),
                "detections_count": capture.get("detections_count"),
                "status": capture.get("status"),
                "detect_ms": capture.get("detect_ms"),
                "embed_ms": capture.get("embed_ms"),
                "process_ms": capture.get("process_ms"),
                "detect_error": capture.get("detect_error"),
            },
        }
        capture_id = getattr(result, "capture_id", None) or None
        self.db.add_acceptance_event(
            int(run["id"]),
            "capture",
            bool(getattr(result, "ok", False)),
            source_kind=source_kind,
            detail=detail,
            capture_id=int(capture_id) if capture_id else None,
            latency_ms=int(latency_ms),
        )

    def record_query(self, payload: dict) -> None:
        run = self._active()
        if not run:
            return
        detail = normalize_query_evidence(payload)
        self.db.add_acceptance_event(
            int(run["id"]),
            "query",
            True,
            source_kind=(detail.get("evidence") or {}).get("source_kind"),
            detail=detail,
            query_log_id=payload.get("query_log_id"),
            latency_ms=int(payload.get("latency_ms") or 0),
        )

    def record_query_failure(self, text: str, error: str) -> None:
        run = self._active()
        if not run:
            return
        self.db.add_acceptance_event(
            int(run["id"]),
            "query",
            False,
            detail={"query": text, "error": error},
        )

    def record_service(self, action: str, state: dict, ok: bool = True) -> None:
        run = self._active()
        if not run:
            return
        self.db.add_acceptance_event(
            int(run["id"]),
            action,
            ok,
            source_kind=self.cfg.capture.source,
            detail={"service": state},
        )


def normalize_query_evidence(payload: dict) -> dict:
    """把不同查询意图的结果压平成验收可核验的证据摘要。"""
    results = _as_list(payload.get("results"))
    evidence: dict | None = None
    first = results[0] if results else {}
    first = _as_dict(first)
    if _as_list(first.get("events")):
        ev = _as_dict(_as_list(first.get("events"))[0])
        evidence = {
            "capture_id": ev.get("capture_id"),
            "track_id": first.get("track_id"),
            "zone": ev.get("zone"),
            "time_local": ev.get("time_local"),
            "time_synced": ev.get("time_synced"),
            "source_kind": ev.get("source_kind") or "unknown",
            "confidence": ev.get("confidence"),
            "evidence_image_url": ev.get("evidence_image_url"),
            "evidence_crop_url": ev.get("evidence_crop_url"),
        }
    elif _as_list(first.get("items")):
        item = _as_dict(_as_list(first.get("items"))[0])
        evidence = {
            "capture_id": first.get("capture_id"),
            "zone": item.get("zone"),
            "time_local": first.get("time_local"),
            "time_synced": None,
            "source_kind": item.get("source_kind") or "unknown",
            "confidence": item.get("confidence"),
            "evidence_image_url": first.get("evidence_image_url"),
            "evidence_crop_url": item.get("crop_url"),
        }
    elif first.get("capture_id"):
        evidence = {
            "capture_id": first.get("capture_id"),
            "detection_id": first.get("detection_id"),
            "track_id": first.get("track_id"),
            "zone": first.get("zone"),
            "time_local": first.get("time_local"),
            "time_synced": first.get("time_synced"),
            "source_kind": first.get("source_kind") or "unknown",
            "confidence": first.get("confidence"),
            "evidence_image_url": first.get("evidence_image_url"),
            "evidence_crop_url": first.get("evidence_crop_url"),
        }
    return {
        "query": payload.get("query"),
        "status": payload.get("status"),
        "intent": payload.get("intent"),
        "intent_zh": payload.get("intent_zh"),
        "answer": payload.get("answer"),
        "latency_ms": payload.get("latency_ms"),
        "query_log_id": payload.get("query_log_id"),
        "result_count": len(results),
        "notes": _as_list(payload.get("notes")),
        "evidence": evidence,
    }


# ---------------- 判定 ----------------
def _item(key: str, status: str, reason: str, evidence: list[dict] | None = None, title: str | None = None) -> dict:
    return {
        "key": key,
        "title": title or ITEM_TITLES[key],
        "status": status,
        "reason": reason,
        "evidence": evidence or [],
    }


def _counts(items: list[dict]) -> dict:
    return {
        "pass": sum(1 for i in items if i["status"] == PASS),
        "fail": sum(1 for i in items if i["status"] == FAIL),
        "not_verified": sum(1 for i in items if i["status"] == NOT_VERIFIED),
    }


def _empty_overview(reason: str) -> dict:
    items = [_item(key, NOT_VERIFIED, reason) for key in ITEM_TITLES]
    counts = _counts(items)
    return {
        "status": NOT_VERIFIED,
        "counts": counts,
        "simulated": False,
        "banner": f"尚无验收运行：{reason}",
        "warnings": [],
        "items": items,
        "generated_at_utc": utc_now_iso(),
        "evaluator_version": EVALUATOR_VERSION,
    }


def evaluate_run(
    db: Database,
    cfg: Config,
    run: dict | None,
    events: list[dict] | None,
    *,
    detector_status: dict | None = None,
    embedder_status: dict | None = None,
    model_errors: list[str] | None = None,
) -> dict:
    if not run:
        return _empty_overview("请先开始一轮验收（真实设备或回放演示）")

    events = list(events or [])
    for ev in events:
        ev["detail"] = _load_detail(ev)

    mode = run.get("mode")
    real = mode == "real_device"
    demo = mode == "replay_demo"
    model_errors = list(model_errors or [])
    det_status = _as_dict(detector_status)
    emb_status = _as_dict(embedder_status)

    try:
        all_captures = db.captures_for_run(int(run["id"]))
    except Exception:
        all_captures = []

    capture_events = [e for e in events if e.get("kind") == "capture"]
    failed_capture_events = [e for e in capture_events if not e.get("ok")]
    duplicate_capture_events = [
        e for e in capture_events if e.get("capture_id") and _as_dict(e.get("detail")).get("duplicate") is True
    ]
    # duplicate=true 表示设备返回了已入库的旧帧（典型原因：设备重启后 seq 归零）。
    # 旧帧不能作为“本轮真实抓拍/检测/存储/轨迹”的证据，否则会把运行前画面算成本轮结果。
    new_capture_ids = {
        int(e["capture_id"])
        for e in capture_events
        if e.get("capture_id") and not _as_dict(e.get("detail")).get("duplicate")
    }
    captures = [c for c in all_captures if int(c["id"]) in new_capture_ids]
    duplicate_captures = [c for c in all_captures if int(c["id"]) not in new_capture_ids]
    query_events = [e for e in events if e.get("kind") == "query"]
    probe_events = [e for e in events if e.get("kind") == "probe"]

    real_captures = [c for c in captures if (c.get("source_kind") or "unknown") == "esp32"]
    if real:
        relevant_captures = real_captures
        non_real_captures = [c for c in captures if (c.get("source_kind") or "unknown") != "esp32"]
    else:
        relevant_captures = [
            c for c in captures if (c.get("source_kind") or "unknown") in {"replay", "esp32"}
        ]
        non_real_captures = []

    provenance_mismatch = real and bool(non_real_captures)

    items: list[dict] = []

    # 1) 设备连接
    if not real:
        items.append(
            _item(
                "device_connection",
                NOT_VERIFIED,
                "回放演示模式不验证真实设备连接；真实设备请在“开始真实设备验收”中检查。",
            )
        )
    elif not probe_events:
        items.append(
            _item(
                "device_connection",
                NOT_VERIFIED,
                "本轮尚未执行“检查连接”。请输入设备地址并点击“检查连接”。",
            )
        )
    else:
        last = probe_events[-1]
        summary = _as_dict(last["detail"].get("summary"))
        camera = _as_dict(summary.get("camera"))
        wifi = _as_dict(summary.get("wifi"))
        url = last["detail"].get("url") or run.get("source_ref")
        evidence = _device_evidence(summary, url)
        if not last.get("ok"):
            error = last["detail"].get("error") or "未知错误"
            items.append(_item("device_connection", FAIL, f"最近一次连接检查失败：{error}", evidence))
        elif camera.get("ready") is False:
            items.append(_item("device_connection", FAIL, "设备可达，但摄像头尚未就绪（camera.ready=false）。", evidence))
        elif wifi.get("connected") is False:
            items.append(_item("device_connection", FAIL, "设备可达，但 Wi-Fi 未连接。", evidence))
        else:
            items.append(
                _item(
                    "device_connection",
                    PASS,
                    "设备探测成功，摄像头与 Wi-Fi 状态正常。",
                    evidence,
                )
            )

    # 2) 抓拍
    capture_title = "真实抓拍" if real else "抓拍（回放演示）"
    if real:
        if relevant_captures:
            latest = max(relevant_captures, key=lambda c: int(c["id"]))
            evidence = [
                {
                    "label": f"抓拍 #{latest['id']}",
                    "value": (
                        f"{_capture_time_text(latest)} · {_capture_provenance_text(latest)}"
                        f" · {latest.get('image_width')}×{latest.get('image_height')}"
                        f" · seq={latest.get('device_seq_raw') or latest.get('device_seq')}"
                    ),
                    "url": f"/api/captures/{latest['id']}/image",
                },
                {
                    "label": "设备时间来源",
                    "value": f"{latest.get('time_source')} · 时间已同步={bool(latest.get('time_synced'))}",
                },
            ]
            items.append(
                _item(
                    "capture",
                    PASS,
                    f"本轮已从真实设备成功抓拍 {len(relevant_captures)} 帧。",
                    evidence,
                    title=capture_title,
                )
            )
        elif failed_capture_events:
            last = failed_capture_events[-1]
            error = last["detail"].get("error") or "抓拍失败"
            items.append(_item("capture", FAIL, f"真实设备抓拍失败：{error}", [], title=capture_title))
        elif duplicate_captures:
            items.append(
                _item(
                    "capture",
                    NOT_VERIFIED,
                    f"本轮 {len(duplicate_capture_events)} 次抓拍都返回了设备中已存在的旧帧"
                    "（duplicate=true），没有产生新画面。常见原因是设备重启后 seq 归零；"
                    "请确认设备未重启，再重新抓拍。",
                    [
                        {
                            "label": f"重复帧 #{c['id']}",
                            "value": f"{_capture_time_text(c)} · seq={c.get('device_seq_raw') or c.get('device_seq')}",
                            "url": f"/api/captures/{c['id']}/image",
                        }
                        for c in duplicate_captures[-3:]
                    ],
                    title=capture_title,
                )
            )
        elif non_real_captures:
            items.append(
                _item(
                    "capture",
                    NOT_VERIFIED,
                    "本轮只有 replay/upload 数据，没有真实设备抓拍；请先连接 ESP32 再抓拍。",
                    [
                        {
                            "label": f"抓拍 #{c['id']}",
                            "value": _capture_provenance_text(c),
                        }
                        for c in non_real_captures[-3:]
                    ],
                    title=capture_title,
                )
            )
        else:
            items.append(_item("capture", NOT_VERIFIED, "本轮尚未抓拍。", [], title=capture_title))
    else:
        if relevant_captures:
            latest = max(relevant_captures, key=lambda c: int(c["id"]))
            evidence = [
                {
                    "label": f"回放抓拍 #{latest['id']}",
                    "value": (
                        f"{_capture_time_text(latest)} · {_capture_provenance_text(latest)}"
                        f" · {latest.get('image_width')}×{latest.get('image_height')}"
                    ),
                    "url": f"/api/captures/{latest['id']}/image",
                }
            ]
            items.append(
                _item(
                    "capture",
                    PASS,
                    f"回放演示抓拍 {len(relevant_captures)} 帧（模拟数据，不计入真机验收）。",
                    evidence,
                    title=capture_title,
                )
            )
        elif failed_capture_events:
            last = failed_capture_events[-1]
            items.append(
                _item(
                    "capture",
                    FAIL,
                    f"回放抓拍失败：{last['detail'].get('error') or '未知错误'}",
                    [],
                    title=capture_title,
                )
            )
        elif duplicate_captures:
            items.append(
                _item(
                    "capture",
                    NOT_VERIFIED,
                    f"本轮 {len(duplicate_capture_events)} 次抓拍均返回旧帧（duplicate=true），"
                    "没有产生新画面；回放帧不能作为本轮抓拍证据。",
                    [
                        {
                            "label": f"重复帧 #{c['id']}",
                            "value": _capture_time_text(c),
                            "url": f"/api/captures/{c['id']}/image",
                        }
                        for c in duplicate_captures[-3:]
                    ],
                    title=capture_title,
                )
            )
        else:
            items.append(_item("capture", NOT_VERIFIED, "本轮尚未抓拍。", [], title=capture_title))

    # 3) 检测
    if model_errors:
        items.append(_item("detection", FAIL, "模型错误：" + " | ".join(model_errors)))
    elif det_status and det_status.get("loaded") is False and not relevant_captures:
        items.append(_item("detection", NOT_VERIFIED, "检测模型尚未加载完成，请等待模型就绪。"))
    elif not relevant_captures:
        items.append(
            _item(
                "detection",
                NOT_VERIFIED,
                "本轮没有可核验的真实抓拍，无法验证检测。" if real else "本轮没有可核验的抓拍，无法验证检测。",
            )
        )
    else:
        detect_failed = [c for c in relevant_captures if c.get("status") == "detect_failed"]
        with_det = [c for c in relevant_captures if int(c.get("detections_count") or 0) > 0]
        if detect_failed:
            last = detect_failed[-1]
            items.append(
                _item(
                    "detection",
                    FAIL,
                    f"检测失败：{last.get('detect_error') or '检测器返回错误'}",
                    [{"label": f"抓拍 #{last['id']}", "value": "原图已保存，可点击查看", "url": f"/api/captures/{last['id']}/image"}],
                )
            )
        elif with_det:
            latest = max(with_det, key=lambda c: int(c["id"]))
            dets = db.detections_for_capture(int(latest["id"]))
            detect_ms = latest.get("detect_ms")
            process_ms = latest.get("process_ms")
            crop_missing = []
            for d in dets:
                path = _resolve_path(d.get("crop_path"))
                if path is None or not path.exists():
                    crop_missing.append(d.get("id"))
            classes = "、".join(sorted({str(d.get("name_zh")) for d in dets if d.get("name_zh")}))
            evidence = [
                {
                    "label": f"抓拍 #{latest['id']} 检测",
                    "value": f"{len(dets)} 个 · {classes or '未知类别'}",
                    "url": f"/api/captures/{latest['id']}/image",
                },
                {
                    "label": "检测/总耗时",
                    "value": f"{detect_ms} ms / {process_ms} ms"
                    if detect_ms is not None and process_ms is not None
                    else "未记录",
                },
            ]
            if dets:
                top = max(dets, key=lambda d: float(d.get("conf") or 0))
                evidence.append(
                    {
                        "label": f"最高置信度 · {top.get('name_zh') or '物品'}",
                        "value": f"{float(top.get('conf') or 0):.3f} · {top.get('region_name') or '未分区'}"
                        f" · {top.get('source_kind') or 'unknown'}",
                        "url": f"/api/detections/{top.get('id')}/crop",
                    }
                )
            if detect_ms is None or process_ms is None:
                items.append(_item("detection", FAIL, "检测已执行，但缺少检测耗时记录，无法核验处理耗时。", evidence))
            elif crop_missing:
                items.append(_item("detection", FAIL, "检测裁剪图缺失，证据不完整。", evidence))
            else:
                items.append(
                    _item(
                        "detection",
                        PASS,
                        f"检测成功：{len(dets)} 个物品，检测耗时 {detect_ms} ms，总处理 {process_ms} ms。",
                        evidence,
                    )
                )
        else:
            latest = max(relevant_captures, key=lambda c: int(c["id"]))
            items.append(
                _item(
                    "detection",
                    NOT_VERIFIED,
                    "抓拍成功，但未检出词表内物品；可能是画面无物品或漏检，不能判为通过。",
                    [
                        {
                            "label": f"抓拍 #{latest['id']}",
                            "value": "0 个检测",
                            "url": f"/api/captures/{latest['id']}/image",
                        }
                    ],
                )
            )

    # 4) 存储
    if not relevant_captures:
        items.append(
            _item(
                "storage",
                NOT_VERIFIED,
                "本轮没有可核验的抓拍记录，无法验证存储。",
            )
        )
    else:
        verified = []
        problems = []
        for c in relevant_captures:
            path = _resolve_path(c.get("file_path"))
            if path is None or not path.exists():
                problems.append(f"抓拍 #{c['id']} 原图文件缺失")
                continue
            actual = path.stat().st_size
            expected = int(c.get("image_bytes") or 0)
            if expected and actual != expected:
                problems.append(f"抓拍 #{c['id']} 文件字节数不一致（{actual} != {expected}）")
                continue
            verified.append(c)
        evidence = [
            {
                "label": f"抓拍 #{c['id']}",
                "value": (
                    f"{_relative_path(c.get('file_path'))} · {int(c.get('image_bytes') or 0)} bytes"
                    f" · {c.get('image_width')}×{c.get('image_height')}"
                    f" · detections={int(c.get('detections_count') or 0)}"
                ),
                "url": f"/api/captures/{c['id']}/image",
            }
            for c in verified[-2:]
        ]
        if problems:
            items.append(_item("storage", FAIL, "；".join(problems), evidence))
        else:
            items.append(
                _item("storage", PASS, f"本轮 {len(verified)} 帧均已入库且原图文件可读。", evidence)
            )

    # 5) 轨迹关联
    if not relevant_captures:
        items.append(_item("track_link", NOT_VERIFIED, "本轮没有可核验的抓拍，无法验证轨迹关联。"))
    else:
        det_rows = []
        for c in relevant_captures:
            for d in db.detections_for_capture(int(c["id"])):
                d = dict(d)
                d["_capture_id"] = int(c["id"])
                det_rows.append(d)
        grouped: dict[int, list[dict]] = {}
        for d in det_rows:
            track_id = d.get("track_id")
            if track_id is None:
                continue
            grouped.setdefault(int(track_id), []).append(d)
        linked = []
        ambiguous_count = sum(1 for d in det_rows if d.get("link_status") == "ambiguous")
        for track_id, rows in grouped.items():
            capture_ids = {r["_capture_id"] for r in rows}
            statuses = {r.get("link_status") for r in rows}
            if len(capture_ids) >= 2 and statuses & {"matched", "manual"}:
                linked.append((track_id, rows))
        if linked:
            track_id, rows = max(linked, key=lambda item: len(item[1]))
            track = db.get_track(track_id) or {}
            label = track.get("label") or track.get("name_zh") or f"track #{track_id}"
            all_scores = [float(r.get("link_score") or 0) for r in rows]
            matched_scores = [
                float(r.get("link_score") or 0)
                for r in rows
                if r.get("link_status") in {"matched", "manual"}
            ]
            scores = matched_scores or all_scores
            score_text = f"{min(scores):.2f}–{max(scores):.2f}"
            evidence = [
                {
                    "label": f"轨迹 #{track_id} · {label}",
                    "value": (
                        f"{len(rows)} 次观测 / {len({r['_capture_id'] for r in rows})} 帧"
                        f" · 关联分 {score_text}"
                    ),
                },
                {
                    "label": "观测抓拍",
                    "value": "、".join(f"#{cid}" for cid in sorted({r['_capture_id'] for r in rows})),
                },
            ]
            reason = (
                f"同一物品在本轮 {len({r['_capture_id'] for r in rows})} 帧中关联到同一轨迹，"
                f"关联分 {score_text}。"
            )
            if len(scores) < len(rows):
                reason += "（首次观测为新轨迹，不计入关联分区间。）"
            if ambiguous_count:
                reason += f"另有 {ambiguous_count} 次灰区待确认，已在轨迹详情中标注。"
            items.append(_item("track_link", PASS, reason, evidence))
        elif det_rows:
            max_frames = max((len({r["_capture_id"] for r in rows}) for rows in grouped.values()), default=0)
            items.append(
                _item(
                    "track_link",
                    NOT_VERIFIED,
                    f"尚未形成跨帧关联（同一轨迹最多出现在 {max_frames} 帧）。"
                    "请保持物品在同一画面、间隔几秒后再抓拍一帧。"
                    + (f" 另有 {ambiguous_count} 次灰区待确认。" if ambiguous_count else ""),
                )
            )
        else:
            items.append(_item("track_link", NOT_VERIFIED, "本轮没有检测记录，无法验证轨迹关联。"))

    # 6) 查询
    if not query_events:
        items.append(_item("query", NOT_VERIFIED, "本轮尚未执行找物查询。"))
    else:
        failed = [e for e in query_events if not e.get("ok")]
        successes = [e for e in query_events if e.get("ok")]
        matching = []
        mismatch_evidence = []
        for event in successes:
            detail = event["detail"]
            evidence = _as_dict(detail.get("evidence"))
            if not evidence:
                continue
            source_kind = evidence.get("source_kind") or "unknown"
            source_ok = (source_kind == "esp32") if real else (source_kind in {"replay", "esp32"})
            if not source_ok:
                mismatch_evidence.append((detail, evidence))
                continue
            if detail.get("status") in {"found", "ambiguous"}:
                matching.append((event, detail, evidence))
        if failed:
            last = failed[-1]
            error = last["detail"].get("error") or "查询失败"
            items.append(_item("query", FAIL, f"查询接口失败：{error}"))
        elif matching:
            event, detail, evidence = matching[-1]
            answer = str(detail.get("answer") or "")
            short_answer = answer[:180] + ("…" if len(answer) > 180 else "")
            ev = [
                {"label": "查询", "value": str(detail.get("query") or "")},
                {"label": "意图/延迟", "value": f"{detail.get('intent_zh') or detail.get('intent')} · {detail.get('latency_ms')} ms"},
                {"label": "回答", "value": short_answer},
                {
                    "label": "画面区域/时间",
                    "value": (
                        f"{evidence.get('zone') or '未分区'} · "
                        f"{evidence.get('time_local') or ('时间未同步' if evidence.get('time_synced') is False else '时间未知')}"
                    ),
                },
                {
                    "label": "来源",
                    "value": evidence.get("source_kind") or "unknown",
                },
            ]
            if evidence.get("evidence_image_url"):
                ev.append(
                    {
                        "label": "最后出现图片",
                        "value": f"抓拍 #{evidence.get('capture_id')}",
                        "url": evidence["evidence_image_url"],
                    }
                )
            if evidence.get("evidence_crop_url"):
                ev.append({"label": "物品裁剪图", "value": "证据裁剪", "url": evidence["evidence_crop_url"]})
            items.append(_item("query", PASS, "查询返回了可核验的最后出现位置、时间与画面区域。", ev))
        elif mismatch_evidence:
            detail, evidence = mismatch_evidence[-1]
            items.append(
                _item(
                    "query",
                    NOT_VERIFIED,
                    "查询结果证据来自 replay 数据，不能作为真实设备查询验收；"
                    "请先用真实设备抓拍并重新查询。",
                    [
                        {"label": "查询", "value": str(detail.get("query") or "")},
                        {"label": "证据来源", "value": evidence.get("source_kind") or "unknown"},
                    ],
                )
            )
        else:
            last = successes[-1]["detail"] if successes else {}
            items.append(
                _item(
                    "query",
                    NOT_VERIFIED,
                    f"查询已执行，但未返回可核验结果（status={last.get('status') or '未知'}）；"
                    "请查询已记录过的物品，例如“笔记本电脑最后出现在哪里？”。",
                    [{"label": "查询", "value": str(last.get("query") or "")}],
                )
            )

    counts = _counts(items)
    if counts["fail"]:
        overall = FAIL
    elif counts["pass"] == len(items):
        overall = PASS
    else:
        overall = NOT_VERIFIED

    warnings: list[str] = []
    if model_errors:
        warnings.append("模型错误：" + " | ".join(model_errors))
    if real and run.get("source_kind") != "esp32":
        warnings.append(
            "本轮开始时采集源不是 ESP32；只有在“设备连接 → 使用此设备采集”后抓到的帧才会进入真机结论。"
        )
    if provenance_mismatch:
        warnings.append("本轮包含非真实设备抓拍，相关真机项已保持 NOT VERIFIED，没有混入真机结论。")
    if real and not real_captures:
        warnings.append("本轮还没有真实设备抓拍，请连接 ESP32 后点击“立即抓拍”。")
    if duplicate_capture_events:
        warnings.append(
            f"本轮有 {len(duplicate_capture_events)} 次抓拍返回了已存在的旧帧（duplicate=true），"
            "可能设备重启后 seq 归零；旧帧不计入本轮抓拍/检测/存储/轨迹证据。"
        )
    if not captures and not query_events and not probe_events:
        warnings.append("本轮尚未执行任何操作；请按操作引导依次检查连接、抓拍、查询。")

    if demo:
        banner = (
            f"回放演示（模拟数据，不计入真机验收）：通过 {counts['pass']}/6，"
            f"未验证 {counts['not_verified']}/6。"
        )
    elif overall == PASS:
        banner = "真机验收通过：六项均有本轮可核验证据。"
    elif overall == FAIL:
        banner = "真机验收未通过：存在失败项，请查看下方原因与证据。"
    else:
        banner = (
            f"真机验收未完成：通过 {counts['pass']}/6，失败 {counts['fail']}/6，"
            f"未验证 {counts['not_verified']}/6。"
        )

    return {
        "status": overall,
        "counts": counts,
        "simulated": demo,
        "banner": banner,
        "warnings": warnings,
        "items": items,
        "generated_at_utc": utc_now_iso(),
        "evaluator_version": EVALUATOR_VERSION,
        "captures_considered": [int(c["id"]) for c in relevant_captures],
        "real_capture_count": len(real_captures),
        "duplicate_capture_count": len(duplicate_captures),
        "duplicate_capture_ids": [int(c["id"]) for c in duplicate_captures],
    }


# ---------------- 导出脱敏 ----------------
_ABS_PATH_RE = re.compile(r"[A-Za-z]:\\[^\s\"']+")
_IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_MAC_RE = re.compile(r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b")


def _sanitize_value(value, key: str = ""):
    if isinstance(value, dict):
        return {k: _sanitize_value(v, k) for k, v in value.items() if k not in {"summary_json", "raw"}}
    if isinstance(value, list):
        return [_sanitize_value(v, key) for v in value]
    if isinstance(value, str):
        repo = str(REPO_ROOT)
        text = value.replace(repo + "\\", "").replace(repo + "/", "").replace(repo, "")
        text = _ABS_PATH_RE.sub("<local-path>", text)
        text = _IPV4_RE.sub("<device-ip>", text)
        text = _MAC_RE.sub("<device-mac>", text)
        if key in {"url", "source_ref"} and text.lower().startswith(("http://", "https://")):
            text = mask_device_url(text) or text
        return text
    return value


def build_export(
    run: dict,
    events: list[dict],
    overview: dict,
    *,
    note: str | None = None,
) -> dict:
    payload = {
        "exported_at_utc": utc_now_iso(),
        "privacy_note": (
            "由 Findy 本机验收工作台生成；不包含图像数据。"
            "设备地址与本地绝对路径已脱敏；文件仅应保存在本机。"
        ),
        "run": public_run(run),
        "events": [
            {
                "id": e.get("id"),
                "kind": e.get("kind"),
                "ok": bool(e.get("ok")),
                "source_kind": e.get("source_kind"),
                "capture_id": e.get("capture_id"),
                "query_log_id": e.get("query_log_id"),
                "latency_ms": e.get("latency_ms"),
                "created_at_utc": e.get("created_at_utc"),
                "detail": _sanitize_value(e.get("detail") or _load_detail(e)),
            }
            for e in events
        ],
        "overview": _sanitize_value(overview),
    }
    if note:
        payload["note"] = note
    return payload