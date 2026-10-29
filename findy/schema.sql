PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS cameras (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL UNIQUE,
  source          TEXT NOT NULL,
  model           TEXT,
  width           INTEGER NOT NULL,
  height          INTEGER NOT NULL,
  tz_name         TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  created_at_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS regions (
  id              INTEGER PRIMARY KEY,
  camera_id       INTEGER NOT NULL REFERENCES cameras(id),
  name            TEXT NOT NULL,
  polygon_norm    TEXT NOT NULL,
  kind            TEXT NOT NULL DEFAULT 'surface',
  UNIQUE (camera_id, name)
);

CREATE TABLE IF NOT EXISTS object_classes (
  id              INTEGER PRIMARY KEY,
  name_zh         TEXT NOT NULL UNIQUE,
  name_en         TEXT NOT NULL,
  is_open_vocab   INTEGER NOT NULL DEFAULT 1,
  threshold       REAL,
  context_only    INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS aliases (
  id              INTEGER PRIMARY KEY,
  class_id        INTEGER NOT NULL REFERENCES object_classes(id) ON DELETE CASCADE,
  alias           TEXT NOT NULL,
  lang            TEXT NOT NULL DEFAULT 'zh',
  UNIQUE (alias, lang)
);
CREATE INDEX IF NOT EXISTS idx_alias_class ON aliases(class_id);

CREATE TABLE IF NOT EXISTS captures (
  id              INTEGER PRIMARY KEY,
  camera_id       INTEGER NOT NULL REFERENCES cameras(id),
  device_seq      INTEGER,                       -- 数据库内唯一序号；设备重启 seq 归零时会分配新值
  device_seq_raw  INTEGER,                       -- 设备本次启动报告的原始 seq（用于证据展示）
  captured_at_utc TEXT,                          -- NULL = 时间未同步/未知（绝不伪造）
  captured_at_local TEXT,
  epoch_s         REAL,
  time_synced     INTEGER NOT NULL DEFAULT 0,
  time_source     TEXT NOT NULL,                 -- sntp | sntp_unsynced | file_mtime | manual | client
  uptime_ms       INTEGER,
  received_at_utc TEXT NOT NULL,
  file_path       TEXT NOT NULL,
  image_width     INTEGER NOT NULL,
  image_height    INTEGER NOT NULL,
  image_bytes     INTEGER NOT NULL,
  sha256          TEXT,
  source_ref      TEXT,
  source_kind     TEXT,                          -- esp32 | replay | upload | webcam | unknown（数据来源凭据）
  detections_count INTEGER NOT NULL DEFAULT 0,
  status          TEXT NOT NULL DEFAULT 'ok',
  detect_ms       INTEGER,                       -- OWLv2 检测耗时（毫秒）
  embed_ms        INTEGER,                       -- DINOv2 embedding 耗时（毫秒）
  process_ms      INTEGER,                       -- 本帧检测+关联+入库总耗时（毫秒）
  detect_error    TEXT,                          -- 检测失败原因（成功时为 NULL）
  UNIQUE (camera_id, device_seq)
);
CREATE INDEX IF NOT EXISTS idx_captures_time ON captures(captured_at_utc DESC, id DESC);
CREATE INDEX IF NOT EXISTS idx_captures_recv ON captures(received_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_captures_pending ON captures(id) WHERE captured_at_utc IS NULL;

CREATE TABLE IF NOT EXISTS tracks (
  id              INTEGER PRIMARY KEY,
  class_id        INTEGER NOT NULL REFERENCES object_classes(id),
  label           TEXT,
  color           TEXT,                          -- 标准中文色名（红色/黑色…）
  color_hex       TEXT,
  prototype       BLOB,                          -- float32 DINOv2 原型向量（L2 归一化）
  color_hist      BLOB,                          -- float32 HSV 颜色直方图
  prototype_n     INTEGER NOT NULL DEFAULT 0,
  first_seen_utc  TEXT,
  last_seen_utc   TEXT,
  last_bbox_norm  TEXT,                          -- 最近一次检测框（归一化），用于固定机位 IoU 先验
  last_capture_id INTEGER REFERENCES captures(id),
  last_region_id  INTEGER REFERENCES regions(id),
  status          TEXT NOT NULL DEFAULT 'active',
  user_confirmed  INTEGER NOT NULL DEFAULT 0,
  created_at_utc  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tracks_recent ON tracks(last_seen_utc DESC) WHERE status = 'active';
CREATE INDEX IF NOT EXISTS idx_tracks_class ON tracks(class_id, last_seen_utc DESC);

CREATE TABLE IF NOT EXISTS detections (
  id              INTEGER PRIMARY KEY,
  capture_id      INTEGER NOT NULL REFERENCES captures(id) ON DELETE CASCADE,
  track_id        INTEGER REFERENCES tracks(id),
  class_id        INTEGER NOT NULL REFERENCES object_classes(id),
  region_id       INTEGER REFERENCES regions(id),
  region_name     TEXT,
  bbox_norm       TEXT NOT NULL,                 -- 'x1,y1,x2,y2' 归一化
  bbox_px         TEXT NOT NULL,                 -- 'x1,y1,x2,y2' 像素
  conf            REAL NOT NULL DEFAULT 0,
  crop_path       TEXT,
  embedding       BLOB,
  color_hex       TEXT,
  link_score      REAL,
  link_method     TEXT,                          -- new | prototype | ambiguous | manual
  link_status     TEXT,                          -- matched | new | ambiguous
  captured_at_utc TEXT,
  created_at_utc  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_det_capture ON detections(capture_id);
CREATE INDEX IF NOT EXISTS idx_det_track ON detections(track_id, captured_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_det_region ON detections(region_id, captured_at_utc DESC);
CREATE INDEX IF NOT EXISTS idx_det_class ON detections(class_id, captured_at_utc DESC);

CREATE TABLE IF NOT EXISTS link_candidates (
  id              INTEGER PRIMARY KEY,
  detection_id    INTEGER NOT NULL REFERENCES detections(id) ON DELETE CASCADE,
  candidate_track_id INTEGER NOT NULL REFERENCES tracks(id),
  score           REAL NOT NULL,
  created_at_utc  TEXT NOT NULL,
  UNIQUE (detection_id, candidate_track_id)
);

CREATE TABLE IF NOT EXISTS feedback (
  id              INTEGER PRIMARY KEY,
  detection_id    INTEGER REFERENCES detections(id),
  track_id        INTEGER REFERENCES tracks(id),
  action          TEXT NOT NULL,                 -- confirm | wrong_object | wrong_region
  payload         TEXT,
  created_at_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS query_log (
  id              INTEGER PRIMARY KEY,
  raw_text        TEXT NOT NULL,
  plan_json       TEXT,
  parser          TEXT NOT NULL DEFAULT 'rule',
  result_count    INTEGER,
  answer          TEXT,
  latency_ms      INTEGER,
  created_at_utc  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
  key             TEXT PRIMARY KEY,
  value           TEXT
);

-- 端到端验收运行：只记录本机真实操作与证据，供 /workbench 计算 PASS/FAIL/NOT VERIFIED。
CREATE TABLE IF NOT EXISTS acceptance_runs (
  id              INTEGER PRIMARY KEY,
  mode            TEXT NOT NULL,                 -- real_device | replay_demo
  source_kind     TEXT NOT NULL,                 -- 启动时的采集源
  source_ref      TEXT,
  started_at_utc  TEXT NOT NULL,
  finished_at_utc TEXT,
  status          TEXT NOT NULL DEFAULT 'running', -- running | finished
  summary_json    TEXT
);
CREATE INDEX IF NOT EXISTS idx_acceptance_runs_status ON acceptance_runs(status, id DESC);

CREATE TABLE IF NOT EXISTS acceptance_events (
  id              INTEGER PRIMARY KEY,
  run_id          INTEGER NOT NULL REFERENCES acceptance_runs(id) ON DELETE CASCADE,
  kind            TEXT NOT NULL,                 -- probe | capture | query | connect | service_start | service_stop
  ok              INTEGER NOT NULL,
  source_kind     TEXT,
  detail_json     TEXT,
  capture_id      INTEGER REFERENCES captures(id),
  query_log_id    INTEGER REFERENCES query_log(id),
  latency_ms      INTEGER,
  created_at_utc  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_acceptance_events_run ON acceptance_events(run_id, id);

PRAGMA user_version = 2;