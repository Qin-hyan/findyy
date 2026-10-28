"""中文自然语言查询：意图解析 + 执行 + 带证据的中文回答。

设计：规则解析为主干（零依赖、可预测、离线可用），LLM 只作为未来增强；
解析结果统一成 QueryPlan，执行器只认 QueryPlan，因此后续换解析器不影响查询逻辑。
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from .classes import ObjectCatalog
from .config import Config
from .db import Database
from .util import humanize_delta, local_display, parse_iso
from .zones import Region

INTENTS = {
    "last_seen": "最后位置",
    "history": "历史记录",
    "list": "区域清单",
    "count": "数量",
    "moved": "是否移动",
    "presence": "是否存在",
    "help": "帮助",
}

_LOC_WORDS = ("在哪", "哪里", "哪儿", "位置", "放哪", "找不到", "在什么地方", "在何处")
_HISTORY_WORDS = ("什么时候", "时间", "历史", "记录", "上次", "最后一次", "出现过", "几次", "轨迹", "时间线")
_MOVED_WORDS = ("移动过", "动过", "搬过", "换过地方", "位置变", "位置变化", "挪过")
_COUNT_WORDS = ("几个", "多少", "数量", "几件", "一共")
_PRESENCE_WORDS = ("在不在", "有没有", "还在吗", "还在不在", "是不是还在")
_LIST_WORDS = ("有哪些", "有什么", "都有啥", "列出", "清单", "都有什么", "都有些什么", "都有哪些")
_HELP_WORDS = ("帮助", "怎么用", "你能做什么", "能问什么", "怎么问")


@dataclass
class QueryPlan:
    raw_text: str
    intent: str = "help"
    class_zh: str | None = None
    color: str | None = None
    region: str | None = None
    time_window: str | None = None
    time_start_utc: str | None = None
    time_end_utc: str | None = None
    limit: int = 5
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "raw_text": self.raw_text,
            "intent": self.intent,
            "intent_zh": INTENTS.get(self.intent, self.intent),
            "class_zh": self.class_zh,
            "color": self.color,
            "region": self.region,
            "time_window": self.time_window,
            "time_start_utc": self.time_start_utc,
            "time_end_utc": self.time_end_utc,
            "limit": self.limit,
            "notes": self.notes,
        }


def _now_local(tz_name: str) -> datetime:
    return datetime.now(ZoneInfo(tz_name))


def _window_to_utc(start_local: datetime, end_local: datetime) -> tuple[str, str]:
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    return (
        start_local.astimezone(timezone.utc).strftime(fmt),
        end_local.astimezone(timezone.utc).strftime(fmt),
    )


def resolve_time_window(text: str, tz_name: str) -> tuple[str | None, str | None, str | None]:
    """返回 (window_name, start_utc_iso, end_utc_iso)。"""
    now = _now_local(tz_name)
    start_today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if any(w in text for w in ("今天", "今日", "当天")):
        start, end, name = start_today, start_today + timedelta(days=1), "today"
    elif any(w in text for w in ("昨天", "昨日")):
        start, end, name = start_today - timedelta(days=1), start_today, "yesterday"
    elif any(w in text for w in ("本周", "这周", "这个星期")):
        monday = start_today - timedelta(days=start_today.weekday())
        start, end, name = monday, monday + timedelta(days=7), "this_week"
    elif any(w in text for w in ("最近", "近期", "刚才", "刚刚", "这会儿")):
        start, end, name = now - timedelta(days=1), now + timedelta(minutes=5), "recent_24h"
    else:
        return None, None, None
    s, e = _window_to_utc(start, end)
    return name, s, e


def detect_intent(text: str) -> str:
    t = text.lower()
    if any(w in t for w in _HELP_WORDS):
        return "help"
    if any(w in t for w in _MOVED_WORDS):
        return "moved"
    has_loc = any(w in t for w in _LOC_WORDS)
    has_time = any(w in t for w in ("什么时候", "时间", "几点"))
    if has_loc and not has_time:
        return "last_seen"
    if has_time or any(w in t for w in _HISTORY_WORDS):
        return "history"
    if any(w in t for w in _COUNT_WORDS):
        return "count"
    if any(w in t for w in _PRESENCE_WORDS):
        return "presence"
    if any(w in t for w in _LIST_WORDS):
        return "list"
    if any(w in t for w in ("在哪儿", "在哪", "位置")):
        return "last_seen"
    return "last_seen"


def parse_query(text: str, catalog: ObjectCatalog, regions: list[Region] | None = None, tz_name: str = "Asia/Shanghai") -> QueryPlan:
    raw = (text or "").strip()
    plan = QueryPlan(raw_text=raw)
    if not raw:
        plan.intent = "help"
        plan.notes.append("查询为空")
        return plan

    plan.intent = detect_intent(raw)
    t = raw.lower()

    # 实体：只匹配非 context_only 的物品类别
    entity = catalog.match_alias(raw)
    if entity is not None and entity.context_only:
        entity = None
    if entity is not None:
        plan.class_zh = entity.zh

    plan.color = catalog.normalize_color(raw)

    for region in regions or []:
        if region.name in raw:
            plan.region = region.name
            break

    window, start, end = resolve_time_window(raw, tz_name)
    plan.time_window, plan.time_start_utc, plan.time_end_utc = window, start, end

    m = re.search(r"最近\s*(\d+)\s*(?:次|个|条|件)", raw)
    if m:
        plan.limit = max(1, min(50, int(m.group(1))))
    elif any(w in raw for w in ("所有", "全部", "都有")):
        plan.limit = 20

    if plan.intent == "list" and plan.class_zh and not plan.region:
        plan.region = None
    # 需要物品名的意图，如果没解析出物品，降级为帮助（而不是硬猜一个类别）
    if plan.intent in {"last_seen", "history", "presence", "count", "moved"} and not plan.class_zh:
        plan.intent = "help"
        plan.notes.append("没有识别出要查询的物品名称，已改为展示使用说明")
    return plan


# ---------------- 执行 ----------------
def _track_label(track: dict) -> str:
    label = track.get("label") or ""
    class_zh = track.get("name_zh") or track.get("class_zh") or "物品"
    if label:
        return label
    color = track.get("color")
    return f"{color}{class_zh}" if color else class_zh


def _last_detection(db: Database, track_id: int) -> dict | None:
    rows = db.detections_for_track(track_id, limit=1)
    return rows[0] if rows else None


def _in_window(observed_iso: str | None, start: str | None, end: str | None) -> bool:
    if not start or not end:
        return True
    dt = parse_iso(observed_iso)
    if dt is None:
        return False
    return parse_iso(start) <= dt < parse_iso(end)  # type: ignore[operator]


def _result_from_track(db: Database, cfg: Config, track: dict, last: dict) -> dict:
    synced = bool(last.get("time_synced"))
    region = last.get("region_name") or db.region_name(track.get("last_region_id")) or "未分区"
    local = last.get("captured_at_local") or local_display(last.get("captured_at_utc"), cfg.app.tz)
    ago = humanize_delta(last.get("captured_at_utc"), cfg.app.tz) if synced else None
    uncertainty = None
    if last.get("link_status") == "ambiguous":
        uncertainty = f"该次观测与历史记录的关联不确定（相似度 {float(last.get('link_score') or 0):.2f}）"
    bbox = [float(v) for v in str(last.get("bbox_norm") or "0,0,1,1").split(",")]
    return {
        "track_id": int(track["id"]),
        "label": _track_label(track),
        "class_zh": track.get("name_zh") or track.get("class_zh"),
        "color": track.get("color"),
        "zone": region,
        "time_local": local,
        "time_utc": last.get("captured_at_utc"),
        "time_synced": synced,
        "time_ago": ago,
        "source_kind": last.get("source_kind") or "unknown",
        "confidence": round(float(last.get("conf") or 0), 4),
        "link_score": round(float(last.get("link_score") or 0), 4),
        "link_status": last.get("link_status"),
        "uncertainty": uncertainty,
        "sightings": db.track_sighting_count(int(track["id"])),
        "evidence_image_url": f"/api/captures/{last.get('capture_id')}/image",
        "evidence_crop_url": f"/api/detections/{last.get('id')}/crop",
        "bbox_norm": bbox,
        "capture_id": last.get("capture_id"),
        "detection_id": last.get("id"),
    }


def _suggestions(catalog: ObjectCatalog, limit: int = 6) -> list[str]:
    examples = catalog.example_queries[:4] if catalog.example_queries else []
    names = [c.zh for c in catalog.detectable][: limit]
    return examples + ([f"{names[0]}在哪？"] if names else [])


def _answer_last_seen(db: Database, cfg: Config, catalog: ObjectCatalog, plan: QueryPlan) -> dict:
    class_map = db.class_id_map()
    class_id = class_map.get(plan.class_zh or "")
    results: list[dict] = []
    notes: list[str] = []
    if class_id is None:
        return _not_found(db, cfg, catalog, plan, reason="词表里没有这个物品，无法查询")

    tracks = db.active_tracks_for_class(class_id)
    colored_but_filtered = 0
    for track in tracks:
        if plan.color and track.get("color") and track.get("color") != plan.color:
            colored_but_filtered += 1
            continue
        last = _last_detection(db, int(track["id"]))
        if last is None:
            continue
        if not _in_window(last.get("captured_at_utc"), plan.time_start_utc, plan.time_end_utc):
            continue
        if plan.region and (last.get("region_name") or "") != plan.region:
            continue
        results.append(_result_from_track(db, cfg, track, last))

    # 按"最近一次入库的观测"排序：detection_id 单调递增，即使设备时间未同步也不会颠倒顺序
    results.sort(key=lambda r: int(r["detection_id"] or 0), reverse=True)

    if not results:
        reason = f"没有找到「{plan.color or ''}{plan.class_zh}」的记录"
        if colored_but_filtered:
            notes.append(f"数据库里有 {colored_but_filtered} 个同类物品，但颜色不是「{plan.color}」")
        return _not_found(db, cfg, catalog, plan, reason=reason, notes=notes)

    top = results[0]
    status = "found"
    answer_parts: list[str] = []
    if len(results) > 1:
        status = "ambiguous"
        answer_parts.append(
            f"找到 {len(results)} 个可能的「{plan.color or ''}{plan.class_zh}」，最可能是「{top['label']}」："
        )
    else:
        answer_parts.append(f"「{top['label']}」最后出现在「{top['zone']}」。")

    if top["time_synced"]:
        answer_parts.append(f"时间：{top['time_local']}（{top['time_ago']}）。")
    else:
        answer_parts.append("设备时间未同步，无法给出真实墙钟时间；只能确认这是最近一次记录（按采集顺序）。")

    answer_parts.append(
        f"依据：最近一次抓拍中检测到该物品（置信度 {top['confidence']:.2f}），"
        f"与历史外观关联相似度 {top['link_score']:.2f}，共记录到 {top['sightings']} 次。"
    )
    if top["uncertainty"]:
        answer_parts.append(f"注意：{top['uncertainty']}。")
        status = "ambiguous"

    return {
        "ok": True,
        "status": status,
        "answer": "".join(answer_parts),
        "results": results[: plan.limit],
        "notes": notes,
        "suggestions": _suggestions(catalog),
    }


def _answer_history(db: Database, cfg: Config, catalog: ObjectCatalog, plan: QueryPlan) -> dict:
    class_map = db.class_id_map()
    class_id = class_map.get(plan.class_zh or "")
    if class_id is None:
        return _not_found(db, cfg, catalog, plan, reason="词表里没有这个物品，无法查询")
    tracks = db.active_tracks_for_class(class_id)
    track = None
    for candidate in tracks:
        if plan.color and candidate.get("color") and candidate.get("color") != plan.color:
            continue
        if _last_detection(db, int(candidate["id"])) is not None:
            track = candidate
            break
    if track is None:
        return _not_found(db, cfg, catalog, plan, reason=f"没有找到「{plan.color or ''}{plan.class_zh}」的历史记录")

    total = db.track_sighting_count(int(track["id"]))
    dets = db.detections_for_track(int(track["id"]), limit=plan.limit)
    events = []
    for d in dets:
        synced = bool(d.get("time_synced"))
        events.append(
            {
                "time_local": d.get("captured_at_local") or local_display(d.get("captured_at_utc"), cfg.app.tz),
                "time_utc": d.get("captured_at_utc"),
                "time_synced": synced,
                "time_ago": humanize_delta(d.get("captured_at_utc"), cfg.app.tz) if synced else None,
                "zone": d.get("region_name") or "未分区",
                "confidence": round(float(d.get("conf") or 0), 4),
                "source_kind": d.get("source_kind") or "unknown",
                "evidence_image_url": f"/api/captures/{d.get('capture_id')}/image",
                "evidence_crop_url": f"/api/detections/{d.get('id')}/crop",
                "bbox_norm": [float(v) for v in str(d.get("bbox_norm") or "0,0,1,1").split(",")],
                "capture_id": d.get("capture_id"),
            }
        )

    if not events:
        return _not_found(db, cfg, catalog, plan, reason="没有可展示的历史记录")

    lines = [f"「{_track_label(track)}」共记录到 {total} 次，最近 {len(events)} 次如下："]
    for e in events[: plan.limit]:
        when = e["time_local"] if e["time_synced"] else "时间未同步"
        lines.append(f"- {when} 在「{e['zone']}」（置信度 {e['confidence']:.2f}）")
    return {
        "ok": True,
        "status": "found",
        "answer": "\n".join(lines),
        "results": [
            {
                "track_id": int(track["id"]),
                "label": _track_label(track),
                "class_zh": track.get("name_zh"),
                "events": events,
            }
        ],
        "notes": [],
        "suggestions": _suggestions(catalog),
    }


def _answer_count(db: Database, cfg: Config, catalog: ObjectCatalog, plan: QueryPlan) -> dict:
    class_map = db.class_id_map()
    class_id = class_map.get(plan.class_zh or "")
    if class_id is None:
        return _not_found(db, cfg, catalog, plan, reason="词表里没有这个物品，无法统计")
    tracks = db.active_tracks_for_class(class_id)
    if plan.color:
        tracks = [t for t in tracks if not t.get("color") or t.get("color") == plan.color]
    if not tracks:
        return _not_found(db, cfg, catalog, plan, reason=f"没有找到「{plan.color or ''}{plan.class_zh}」的记录")
    total_sightings = sum(db.track_sighting_count(int(t["id"])) for t in tracks)
    ambiguous = 0
    for t in tracks:
        last = _last_detection(db, int(t["id"]))
        if last and last.get("link_status") == "ambiguous":
            ambiguous += 1
    answer = f"已记录 {len(tracks)} 个「{plan.color or ''}{plan.class_zh}」实体，合计出现 {total_sightings} 次。"
    if ambiguous:
        answer += f"其中 {ambiguous} 个的关联还不确定（可能是同一件物品的重复记录），可在界面上确认。"
    return {
        "ok": True,
        "status": "found",
        "answer": answer,
        "results": [],
        "notes": [f"{ambiguous} 个实体为待确认关联"] if ambiguous else [],
        "suggestions": _suggestions(catalog),
    }


def _answer_moved(db: Database, cfg: Config, catalog: ObjectCatalog, plan: QueryPlan) -> dict:
    class_map = db.class_id_map()
    class_id = class_map.get(plan.class_zh or "")
    if class_id is None:
        return _not_found(db, cfg, catalog, plan, reason="词表里没有这个物品，无法判断")
    tracks = db.active_tracks_for_class(class_id)
    moved_lines: list[str] = []
    results: list[dict] = []
    for track in tracks:
        history = db.track_region_history(int(track["id"]))
        if len(history) < 2:
            continue
        transitions = []
        prev = history[0]
        for cur in history[1:]:
            if plan.time_start_utc and not _in_window(cur.get("seen_at"), plan.time_start_utc, plan.time_end_utc):
                prev = cur
                continue
            if (cur.get("region_id") or -1) != (prev.get("region_id") or -1) or (
                cur.get("region_name") != prev.get("region_name")
            ):
                transitions.append({"from": prev.get("region_name"), "to": cur.get("region_name"), "time_utc": cur.get("seen_at")})
            prev = cur
        if not transitions:
            continue
        readable_parts = []
        for t in transitions[:6]:
            when = local_display(t.get("time_utc"), cfg.app.tz) if t.get("time_utc") else None
            part = f"「{t['from']}」→「{t['to']}」"
            if when:
                part += f"（{when}）"
            readable_parts.append(part)
        moved_lines.append(f"「{_track_label(track)}」移动过 {len(transitions)} 次：" + "、".join(readable_parts))
        results.append(
            {
                "track_id": int(track["id"]),
                "label": _track_label(track),
                "class_zh": track.get("name_zh"),
                "transitions": transitions,
            }
        )
    if not moved_lines:
        label = f"{plan.color or ''}{plan.class_zh}"
        return {
            "ok": True,
            "status": "found",
            "answer": f"没有发现「{label}」的位置变化（已记录的出现都在同一区域，或记录次数不足）。",
            "results": [],
            "notes": [],
            "suggestions": _suggestions(catalog),
        }
    return {"ok": True, "status": "found", "answer": "\n".join(moved_lines), "results": results, "notes": [], "suggestions": _suggestions(catalog)}


def _answer_presence(db: Database, cfg: Config, catalog: ObjectCatalog, plan: QueryPlan) -> dict:
    class_map = db.class_id_map()
    class_id = class_map.get(plan.class_zh or "")
    if class_id is None:
        return _not_found(db, cfg, catalog, plan, reason="词表里没有这个物品，无法判断")
    tracks = db.active_tracks_for_class(class_id)
    if plan.color:
        tracks = [t for t in tracks if not t.get("color") or t.get("color") == plan.color]
    label = f"{plan.color or ''}{plan.class_zh}"
    if not tracks:
        return {
            "ok": True,
            "status": "not_found",
            "answer": f"没有「{label}」的记录，无法判断它现在是否还在。",
            "results": [],
            "notes": [],
            "suggestions": _suggestions(catalog),
        }
    last = _last_detection(db, int(tracks[0]["id"]))
    zone = (last or {}).get("region_name") or "未分区"
    when = local_display((last or {}).get("captured_at_utc"), cfg.app.tz) if last and last.get("time_synced") else "时间未同步"
    return {
        "ok": True,
        "status": "found",
        "answer": f"记录显示「{label}」上次出现在「{zone}」（{when}）。我无法判断此刻是否还在，只能确认最后一次看见的位置。",
        "results": [],
        "notes": ["这是历史记录判断，不是实时状态"],
        "suggestions": _suggestions(catalog),
    }


def _answer_list(db: Database, cfg: Config, catalog: ObjectCatalog, plan: QueryPlan) -> dict:
    captures = db.list_captures(limit=5)
    if not captures:
        return {
            "ok": True,
            "status": "empty",
            "answer": "还没有任何抓拍记录，先让摄像头拍一张或启动自动采集。",
            "results": [],
            "notes": [],
            "suggestions": _suggestions(catalog),
        }
    target = None
    for cap in captures:
        if int(cap.get("det_count") or 0) > 0:
            target = cap
            break
    if target is None:
        cap = captures[0]
        when = cap.get("captured_at_local") or local_display(cap.get("captured_at_utc"), cfg.app.tz) or "时间未知"
        return {
            "ok": True,
            "status": "empty",
            "answer": f"最近一次抓拍（{when}）没有识别到物品。可能是画面里没有词表内的物品，或光线/距离不理想。",
            "results": [],
            "notes": [],
            "suggestions": _suggestions(catalog),
        }
    dets = db.detections_for_capture(int(target["id"]))
    items = []
    seen = set()
    for d in dets:
        key = (d.get("name_zh"), d.get("region_name"))
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "class_zh": d.get("name_zh"),
                "confidence": round(float(d.get("conf") or 0), 4),
                "zone": d.get("region_name") or "未分区",
                "source_kind": d.get("source_kind") or "unknown",
                "crop_url": f"/api/detections/{d.get('id')}/crop",
                "bbox_norm": [float(v) for v in str(d.get("bbox_norm") or "0,0,1,1").split(",")],
            }
        )
    if plan.region:
        items = [i for i in items if i["zone"] == plan.region]
    when = target.get("captured_at_local") or local_display(target.get("captured_at_utc"), cfg.app.tz) or "时间未知"
    if not items:
        answer = f"最近一次有物品的抓拍（{when}）里没有符合条件的结果。"
    else:
        grouped: dict[str, list[str]] = {}
        for i in items:
            grouped.setdefault(i["class_zh"], [])
            if i["zone"] not in grouped[i["class_zh"]]:
                grouped[i["class_zh"]].append(i["zone"])
        parts = []
        for cls, zones in grouped.items():
            if len(zones) == 1:
                parts.append(f"{cls}（{zones[0]}）")
            else:
                parts.append(f"{cls}（{'、'.join(zones)}，共 {len(zones)} 处）")
        answer = f"最近一次抓拍（{when}）识别到：" + "、".join(parts) + "。"
    return {
        "ok": True,
        "status": "found",
        "answer": answer,
        "results": [
            {
                "capture_id": target["id"],
                "time_local": when,
                "evidence_image_url": f"/api/captures/{target['id']}/image",
                "items": items,
            }
        ],
        "notes": [],
        "suggestions": _suggestions(catalog),
    }


def _answer_help(catalog: ObjectCatalog) -> dict:
    examples = catalog.example_queries or ["我的钥匙最后出现在哪里？", "红色杯子在哪？", "桌上都有哪些东西？"]
    answer = (
        "我可以根据摄像头的历史记录回答：物品最后出现在哪个区域、什么时候出现过、是否移动过、某个区域有哪些东西。\n"
        "例如：\n" + "\n".join(f"- {q}" for q in examples[:6]) +
        "\n注意：我只能查询词表里已配置的物品；时间来自设备 SNTP，未同步时会明确标注。"
    )
    return {"ok": True, "status": "help", "answer": answer, "results": [], "notes": [], "suggestions": examples}


def _not_found(
    db: Database,
    cfg: Config,
    catalog: ObjectCatalog,
    plan: QueryPlan,
    reason: str,
    notes: list[str] | None = None,
) -> dict:
    existing = []
    if plan.class_zh:
        with db.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT oc.name_zh FROM tracks t JOIN object_classes oc ON oc.id=t.class_id"
                " WHERE t.status='active' ORDER BY oc.name_zh LIMIT 30"
            ).fetchall()
        existing = [r["name_zh"] for r in rows]
    hint = f"当前已记录：{'、'.join(existing[:8])}。" if existing else "当前还没有任何物品记录。"
    answer = f"{reason}。{hint}可能原因：物品不在摄像头视野内、词表未覆盖该物品，或还没有采集到。"
    return {
        "ok": True,
        "status": "not_found",
        "answer": answer,
        "results": [],
        "notes": notes or [],
        "suggestions": _suggestions(catalog),
    }


_EXECUTORS = {
    "last_seen": _answer_last_seen,
    "history": _answer_history,
    "count": _answer_count,
    "moved": _answer_moved,
    "presence": _answer_presence,
    "list": _answer_list,
}


def answer(
    db: Database,
    cfg: Config,
    catalog: ObjectCatalog,
    regions: list[Region],
    text: str,
) -> dict:
    started = time.perf_counter()
    plan = parse_query(text, catalog, regions, cfg.app.tz)
    if plan.intent == "help":
        payload = _answer_help(catalog)
    else:
        payload = _EXECUTORS[plan.intent](db, cfg, catalog, plan)
    elapsed = int((time.perf_counter() - started) * 1000)
    payload.update(
        {
            "query": text,
            "intent": plan.intent,
            "intent_zh": INTENTS.get(plan.intent, plan.intent),
            "parsed": plan.to_dict(),
            "latency_ms": elapsed,
        }
    )
    payload.setdefault("results", [])
    payload.setdefault("notes", [])
    payload.setdefault("suggestions", [])
    try:
        payload["query_log_id"] = db.log_query(
            raw_text=text,
            plan=plan.to_dict(),
            parser="rule",
            result_count=len(payload.get("results") or []),
            answer=str(payload.get("answer", "")),
            latency_ms=elapsed,
        )
    except Exception:
        payload["query_log_id"] = None
    return payload