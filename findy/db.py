"""SQLite 数据访问层。

所有时间字段用 UTC ISO8601 字符串（'YYYY-MM-DDTHH:MM:SSZ'）存储；
未同步时间一律存 NULL 并记录 time_source，绝不伪造墙钟时间。
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import numpy as np

from .classes import ObjectCatalog, ObjectClass
from .util import utc_now_iso
from .zones import Region

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---------------- 连接 ----------------
    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path, timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def init_schema(self) -> None:
        sql = SCHEMA_PATH.read_text(encoding="utf-8")
        with self.connect() as conn:
            conn.executescript(sql)
            # 轻量迁移：老库补列，避免用户必须删库重来
            self._ensure_column(conn, "tracks", "last_bbox_norm", "TEXT")
            self._ensure_column(conn, "tracks", "color", "TEXT")
            self._ensure_column(conn, "captures", "source_kind", "TEXT")
            self._ensure_column(conn, "captures", "detect_ms", "INTEGER")
            self._ensure_column(conn, "captures", "embed_ms", "INTEGER")
            self._ensure_column(conn, "captures", "process_ms", "INTEGER")
            self._ensure_column(conn, "captures", "detect_error", "TEXT")
            # 老数据的来源回填：只依据既有 time_source 语义，绝不猜测为真机。
            # 明确已有 source_kind 的记录不覆盖。
            conn.execute(
                "UPDATE captures SET source_kind = CASE"
                " WHEN time_source LIKE 'sntp%' THEN 'esp32'"
                " WHEN time_source IN ('client', 'client_unsynced') THEN 'upload'"
                " WHEN time_source IN ('file_mtime', 'manual') THEN 'replay'"
                " ELSE 'unknown' END"
                " WHERE source_kind IS NULL OR source_kind = ''"
            )

    @staticmethod
    def _ensure_column(conn: sqlite3.Connection, table: str, column: str, ddl: str) -> None:
        if table not in {"tracks", "captures"}:
            raise ValueError(f"不允许迁移未知表: {table}")
        cols = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")

    def ping(self) -> bool:
        try:
            with self.connect() as conn:
                conn.execute("SELECT 1").fetchone()
            return True
        except sqlite3.Error:
            return False

    # ---------------- 基础实体 ----------------
    def ensure_camera(
        self, name: str, source: str, model: str, width: int, height: int, tz_name: str
    ) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM cameras WHERE name = ?", (name,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE cameras SET source=?, model=?, width=?, height=?, tz_name=? WHERE id=?",
                    (source, model, width, height, tz_name, row["id"]),
                )
                return int(row["id"])
            cur = conn.execute(
                "INSERT INTO cameras(name, source, model, width, height, tz_name, created_at_utc)"
                " VALUES (?,?,?,?,?,?,?)",
                (name, source, model, width, height, tz_name, utc_now_iso()),
            )
            return int(cur.lastrowid)

    def sync_regions(self, camera_id: int, regions: list[Region]) -> dict[str, int]:
        """以 YAML 为准同步区域配置；返回 name -> id。空多边形区域跳过（未标定）。"""
        mapping: dict[str, int] = {}
        with self.connect() as conn:
            for r in regions:
                if len(r.polygon) < 3:
                    continue
                row = conn.execute(
                    "SELECT id FROM regions WHERE camera_id=? AND name=?", (camera_id, r.name)
                ).fetchone()
                payload = json.dumps(r.polygon)
                if row:
                    conn.execute(
                        "UPDATE regions SET polygon_norm=?, kind=? WHERE id=?",
                        (payload, r.kind, row["id"]),
                    )
                    mapping[r.name] = int(row["id"])
                else:
                    cur = conn.execute(
                        "INSERT INTO regions(camera_id, name, polygon_norm, kind) VALUES (?,?,?,?)",
                        (camera_id, r.name, payload, r.kind),
                    )
                    mapping[r.name] = int(cur.lastrowid)
        return mapping

    def sync_catalog(self, catalog: ObjectCatalog) -> dict[str, int]:
        """把 YAML 词表同步进 DB（类与别名），返回 zh -> class_id。"""
        mapping: dict[str, int] = {}
        with self.connect() as conn:
            for c in catalog.classes:
                row = conn.execute(
                    "SELECT id FROM object_classes WHERE name_zh = ?", (c.zh,)
                ).fetchone()
                if row:
                    class_id = int(row["id"])
                    conn.execute(
                        "UPDATE object_classes SET name_en=?, threshold=?, context_only=? WHERE id=?",
                        (c.en, c.threshold, int(c.context_only), class_id),
                    )
                else:
                    cur = conn.execute(
                        "INSERT INTO object_classes(name_zh, name_en, is_open_vocab, threshold, context_only)"
                        " VALUES (?,?,?,?,?)",
                        (c.zh, c.en, int(not c.context_only), c.threshold, int(c.context_only)),
                    )
                    class_id = int(cur.lastrowid)
                mapping[c.zh] = class_id
                for alias in c.all_names():
                    conn.execute(
                        "INSERT OR IGNORE INTO aliases(class_id, alias, lang) VALUES (?,?, 'zh')",
                        (class_id, alias),
                    )
        return mapping

    def class_id_map(self) -> dict[str, int]:
        with self.connect() as conn:
            rows = conn.execute("SELECT id, name_zh FROM object_classes").fetchall()
        return {r["name_zh"]: int(r["id"]) for r in rows}

    def class_name(self, class_id: int) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT name_zh FROM object_classes WHERE id=?", (class_id,)
            ).fetchone()
        return row["name_zh"] if row else f"class#{class_id}"

    def region_name(self, region_id: int | None) -> str | None:
        if region_id is None:
            return None
        with self.connect() as conn:
            row = conn.execute("SELECT name FROM regions WHERE id=?", (region_id,)).fetchone()
        return row["name"] if row else None

    # ---------------- 抓拍 ----------------
    def add_capture(self, record: dict[str, Any]) -> tuple[int, bool]:
        """插入一帧；同相机同 device_seq 幂等。返回 (id, 是否新建)。"""
        cols = [
            "camera_id", "device_seq", "captured_at_utc", "captured_at_local", "epoch_s",
            "time_synced", "time_source", "uptime_ms", "received_at_utc", "file_path",
            "image_width", "image_height", "image_bytes", "sha256", "source_ref", "source_kind",
            "status", "detect_ms", "embed_ms", "process_ms", "detect_error",
        ]
        values = [record.get(c) for c in cols]
        with self.connect() as conn:
            if record.get("device_seq") is not None:
                row = conn.execute(
                    "SELECT id FROM captures WHERE camera_id=? AND device_seq=?",
                    (record["camera_id"], record["device_seq"]),
                ).fetchone()
                if row:
                    return int(row["id"]), False
            cur = conn.execute(
                f"INSERT INTO captures({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                values,
            )
            return int(cur.lastrowid), True

    def set_capture_status(self, capture_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE captures SET status=? WHERE id=?", (status, capture_id))

    def set_capture_detections_count(self, capture_id: int, count: int) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE captures SET detections_count=? WHERE id=?", (count, capture_id))

    def set_capture_metrics(
        self,
        capture_id: int,
        *,
        detect_ms: int | None = None,
        embed_ms: int | None = None,
        process_ms: int | None = None,
        detect_error: str | None = None,
    ) -> None:
        """记录检测/embedding 耗时与检测失败原因（真实测量值，不伪造）。"""
        with self.connect() as conn:
            conn.execute(
                "UPDATE captures SET detect_ms=?, embed_ms=?, process_ms=?, detect_error=? WHERE id=?",
                (detect_ms, embed_ms, process_ms, detect_error, capture_id),
            )

    def get_capture(self, capture_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM captures WHERE id=?", (capture_id,)).fetchone()
        return dict(row) if row else None

    def list_captures(self, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM detections d WHERE d.capture_id=c.id) AS det_count"
                " FROM captures c ORDER BY COALESCE(c.captured_at_utc, c.received_at_utc) DESC, c.id DESC"
                " LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]

    def count_captures(self) -> int:
        with self.connect() as conn:
            return int(conn.execute("SELECT COUNT(*) AS n FROM captures").fetchone()["n"])

    # ---------------- 检测 ----------------
    def add_detection(self, record: dict[str, Any]) -> int:
        cols = [
            "capture_id", "track_id", "class_id", "region_id", "region_name", "bbox_norm",
            "bbox_px", "conf", "crop_path", "embedding", "color_hex", "link_score",
            "link_method", "link_status", "captured_at_utc", "created_at_utc",
        ]
        values = [record.get(c) for c in cols]
        with self.connect() as conn:
            cur = conn.execute(
                f"INSERT INTO detections({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
                values,
            )
            return int(cur.lastrowid)

    def attach_detection(self, detection_id: int, track_id: int, score: float, method: str, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE detections SET track_id=?, link_score=?, link_method=?, link_status=? WHERE id=?",
                (track_id, score, method, status, detection_id),
            )

    def add_link_candidate(self, detection_id: int, track_id: int, score: float) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO link_candidates(detection_id, candidate_track_id, score, created_at_utc)"
                " VALUES (?,?,?,?)",
                (detection_id, track_id, score, utc_now_iso()),
            )

    def link_candidates(self, detection_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT lc.score, t.id AS track_id, t.label, oc.name_zh"
                " FROM link_candidates lc JOIN tracks t ON t.id=lc.candidate_track_id"
                " JOIN object_classes oc ON oc.id=t.class_id"
                " WHERE lc.detection_id=? ORDER BY lc.score DESC",
                (detection_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def detections_for_capture(self, capture_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT d.*, oc.name_zh, oc.name_en, c.source_kind AS source_kind"
                " FROM detections d"
                " JOIN object_classes oc ON oc.id=d.class_id"
                " JOIN captures c ON c.id=d.capture_id"
                " WHERE d.capture_id=? ORDER BY d.conf DESC",
                (capture_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def detections_for_track(self, track_id: int, limit: int = 20) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT d.*, c.file_path, c.captured_at_local, c.time_synced, c.source_kind AS source_kind"
                " FROM detections d JOIN captures c ON c.id=d.capture_id"
                " WHERE d.track_id=? ORDER BY COALESCE(c.captured_at_utc, c.received_at_utc) DESC, d.id DESC"
                " LIMIT ?",
                (track_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 物品轨迹 ----------------
    def create_track(
        self,
        class_id: int,
        label: str | None,
        color: str | None,
        color_hex: str | None,
        prototype: np.ndarray,
        color_hist: np.ndarray,
        seen_iso: str | None,
        capture_id: int,
        region_id: int | None,
        bbox_norm: str | None = None,
        user_confirmed: bool = False,
    ) -> int:
        now = utc_now_iso()
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO tracks(class_id, label, color, color_hex, prototype, color_hist, prototype_n,"
                " first_seen_utc, last_seen_utc, last_bbox_norm, last_capture_id, last_region_id, status,"
                " user_confirmed, created_at_utc)"
                " VALUES (?,?,?,?,?,?,1,?,?,?,?,?,'active',?,?)",
                (
                    class_id, label, color, color_hex,
                    prototype.astype(np.float32).tobytes(),
                    color_hist.astype(np.float32).tobytes(),
                    seen_iso, seen_iso, bbox_norm, capture_id, region_id, int(user_confirmed), now,
                ),
            )
            return int(cur.lastrowid)

    def update_track(
        self,
        track_id: int,
        prototype: np.ndarray,
        color_hist: np.ndarray,
        color: str | None,
        color_hex: str | None,
        seen_iso: str | None,
        capture_id: int,
        region_id: int | None,
        bbox_norm: str | None = None,
        alpha: float = 0.2,
    ) -> None:
        now = utc_now_iso()
        with self.connect() as conn:
            row = conn.execute("SELECT prototype, color_hist, prototype_n FROM tracks WHERE id=?", (track_id,)).fetchone()
            if row is None:
                raise KeyError(f"track 不存在: {track_id}")
            old = np.frombuffer(row["prototype"], dtype=np.float32) if row["prototype"] else None
            if old is not None and old.size == prototype.size:
                merged = (1 - alpha) * old + alpha * prototype.astype(np.float32)
                norm = float(np.linalg.norm(merged))
                if norm > 0:
                    merged = merged / norm
            else:
                merged = prototype.astype(np.float32)
            old_hist = np.frombuffer(row["color_hist"], dtype=np.float32) if row["color_hist"] else None
            if old_hist is not None and old_hist.size == color_hist.size:
                hist = (1 - alpha) * old_hist + alpha * color_hist.astype(np.float32)
            else:
                hist = color_hist.astype(np.float32)
            conn.execute(
                "UPDATE tracks SET prototype=?, color_hist=?, color=COALESCE(?, color),"
                " color_hex=COALESCE(?, color_hex),"
                " prototype_n=prototype_n+1, last_seen_utc=COALESCE(?, last_seen_utc),"
                " last_bbox_norm=COALESCE(?, last_bbox_norm),"
                " last_capture_id=?, last_region_id=COALESCE(?, last_region_id) WHERE id=?",
                (merged.tobytes(), hist.tobytes(), color, color_hex, seen_iso, bbox_norm, capture_id, region_id, track_id),
            )

    def get_track(self, track_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT t.*, oc.name_zh, oc.name_en, r.name AS last_region_name"
                " FROM tracks t JOIN object_classes oc ON oc.id=t.class_id"
                " LEFT JOIN regions r ON r.id=t.last_region_id WHERE t.id=?",
                (track_id,),
            ).fetchone()
        return dict(row) if row else None

    def list_tracks(self, status: str = "active", limit: int = 100) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT t.*, oc.name_zh, oc.name_en, r.name AS last_region_name,"
                " (SELECT COUNT(*) FROM detections d WHERE d.track_id=t.id) AS sightings"
                " FROM tracks t JOIN object_classes oc ON oc.id=t.class_id"
                " LEFT JOIN regions r ON r.id=t.last_region_id"
                " WHERE t.status=? ORDER BY COALESCE(t.last_seen_utc, t.created_at_utc) DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def active_tracks_for_class(self, class_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT t.* FROM tracks t WHERE t.class_id=? AND t.status='active'"
                " ORDER BY COALESCE(t.last_seen_utc, t.created_at_utc) DESC",
                (class_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def update_track_label(self, track_id: int, label: str | None, user_confirmed: bool = True) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE tracks SET label=?, user_confirmed=? WHERE id=?",
                (label, int(user_confirmed), track_id),
            )

    def track_sighting_count(self, track_id: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM detections WHERE track_id=?", (track_id,)
            ).fetchone()
        return int(row["n"])

    def track_region_history(self, track_id: int, limit: int = 50) -> list[dict]:
        """按时间正序返回某物品出现过的区域变化（用于"是否移动过"）。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT d.region_id, d.region_name, COALESCE(c.captured_at_utc, c.received_at_utc) AS seen_at,"
                " c.time_synced, d.capture_id"
                " FROM detections d JOIN captures c ON c.id=d.capture_id"
                " WHERE d.track_id=? ORDER BY d.id ASC LIMIT ?",
                (track_id, limit),
            ).fetchall()
        return [dict(r) for r in rows]

    def merge_tracks(self, source_track_id: int, target_track_id: int) -> int:
        """人工确认关联：把 source 的观测并入 target，source 标记 merged。"""
        if source_track_id == target_track_id:
            return target_track_id
        with self.connect() as conn:
            conn.execute(
                "UPDATE detections SET track_id=? WHERE track_id=?",
                (target_track_id, source_track_id),
            )
            conn.execute(
                "UPDATE tracks SET status='merged' WHERE id=?", (source_track_id,)
            )
            return target_track_id

    # ---------------- 查询日志 / 反馈 / 统计 ----------------
    def log_query(
        self, raw_text: str, plan: dict, parser: str, result_count: int, answer: str, latency_ms: int
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO query_log(raw_text, plan_json, parser, result_count, answer, latency_ms, created_at_utc)"
                " VALUES (?,?,?,?,?,?,?)",
                (raw_text, json.dumps(plan, ensure_ascii=False), parser, result_count, answer, latency_ms, utc_now_iso()),
            )
            return int(cur.lastrowid)

    def add_feedback(self, detection_id: int | None, track_id: int | None, action: str, payload: dict | None = None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO feedback(detection_id, track_id, action, payload, created_at_utc)"
                " VALUES (?,?,?,?,?)",
                (detection_id, track_id, action, json.dumps(payload or {}, ensure_ascii=False), utc_now_iso()),
            )
            return int(cur.lastrowid)

    def recent_queries(self, limit: int = 10) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM query_log ORDER BY id DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    # ---------------- 端到端验收运行 ----------------
    def create_acceptance_run(self, mode: str, source_kind: str, source_ref: str | None) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO acceptance_runs(mode, source_kind, source_ref, started_at_utc, status)"
                " VALUES (?,?,?,?, 'running')",
                (mode, source_kind, source_ref, utc_now_iso()),
            )
            return int(cur.lastrowid)

    def get_acceptance_run(self, run_id: int) -> dict | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM acceptance_runs WHERE id=?", (run_id,)).fetchone()
        return dict(row) if row else None

    def latest_acceptance_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM acceptance_runs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def active_acceptance_run(self) -> dict | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM acceptance_runs WHERE status='running' ORDER BY id DESC LIMIT 1"
            ).fetchone()
        return dict(row) if row else None

    def finish_acceptance_run(self, run_id: int, summary: dict) -> None:
        with self.connect() as conn:
            conn.execute(
                "UPDATE acceptance_runs SET status='finished', finished_at_utc=?, summary_json=? WHERE id=?",
                (utc_now_iso(), json.dumps(summary, ensure_ascii=False), run_id),
            )

    def add_acceptance_event(
        self,
        run_id: int,
        kind: str,
        ok: bool,
        *,
        source_kind: str | None = None,
        detail: dict | None = None,
        capture_id: int | None = None,
        query_log_id: int | None = None,
        latency_ms: int | None = None,
    ) -> int:
        with self.connect() as conn:
            cur = conn.execute(
                "INSERT INTO acceptance_events(run_id, kind, ok, source_kind, detail_json,"
                " capture_id, query_log_id, latency_ms, created_at_utc)"
                " VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    kind,
                    int(ok),
                    source_kind,
                    json.dumps(detail or {}, ensure_ascii=False),
                    capture_id,
                    query_log_id,
                    latency_ms,
                    utc_now_iso(),
                ),
            )
            return int(cur.lastrowid)

    def acceptance_events(self, run_id: int) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM acceptance_events WHERE run_id=? ORDER BY id ASC", (run_id,)
            ).fetchall()
        return [dict(r) for r in rows]

    def captures_for_run(self, run_id: int) -> list[dict]:
        """本轮验收实际成功关联的抓拍（按事件顺序去重）。"""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT c.* FROM captures c WHERE c.id IN ("
                " SELECT capture_id FROM acceptance_events"
                " WHERE run_id=? AND kind='capture' AND capture_id IS NOT NULL"
                ") ORDER BY c.id ASC",
                (run_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        with self.connect() as conn:
            captures = conn.execute("SELECT COUNT(*) AS n FROM captures").fetchone()["n"]
            detections = conn.execute("SELECT COUNT(*) AS n FROM detections").fetchone()["n"]
            tracks = conn.execute("SELECT COUNT(*) AS n FROM tracks WHERE status='active'").fetchone()["n"]
            ambiguous = conn.execute(
                "SELECT COUNT(*) AS n FROM detections WHERE link_status='ambiguous'"
            ).fetchone()["n"]
            last = conn.execute(
                "SELECT COALESCE(captured_at_utc, received_at_utc) AS t FROM captures ORDER BY id DESC LIMIT 1"
            ).fetchone()
            unsynced = conn.execute(
                "SELECT COUNT(*) AS n FROM captures WHERE time_synced=0"
            ).fetchone()["n"]
            source_rows = conn.execute(
                "SELECT COALESCE(NULLIF(source_kind, ''), 'unknown') AS k, COUNT(*) AS n"
                " FROM captures GROUP BY k"
            ).fetchall()
        return {
            "captures": int(captures),
            "detections": int(detections),
            "active_tracks": int(tracks),
            "ambiguous_links": int(ambiguous),
            "unsynced_captures": int(unsynced),
            "last_capture_at": last["t"] if last else None,
            "captures_by_source": {str(r["k"]): int(r["n"]) for r in source_rows},
        }

    def class_counts(self) -> list[dict]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT oc.name_zh, t.status, COUNT(*) AS n FROM tracks t"
                " JOIN object_classes oc ON oc.id=t.class_id GROUP BY oc.name_zh, t.status"
            ).fetchall()
        return [dict(r) for r in rows]