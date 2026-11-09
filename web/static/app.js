const PAGE = document.body.dataset.page || "observe";

const state = {
  status: null,
  currentCapture: null,
  autoRunning: false,
  warmupDone: false,
  busy: false,
  highlightedDetectionId: null,
  summaryPinned: false,
  summaryTimer: null,
  objects: [],
  objectsSignature: null,
  itemsHoverCapable: true,
  itemsMode: "orb",
  timelineSignature: null,
  timelineEntered: false,
  itemsSwitching: false,
  itemsSwitchTimer: 0,
  itemsEnteringTimer: 0,
  gridEntrancePending: false,
  gridAnimationTimer: 0,
  itemsOrb: null,
  searchBase: [],
  searchItems: [],
  searchCategory: "all",
  searchRange: "all",
  searchQuery: "",
  itemDetailTrackId: null,
  itemDetailReturnFocus: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function stripPeriods(text) {
  return String(text ?? "").replaceAll("\u3002", "");
}

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = stripPeriods(text);
}

function setPill(id, text, cls) {
  const el = $(id);
  if (!el) return;
  el.textContent = text;
  el.className = "pill " + (cls || "");
}

function toast(message, ok = false) {
  const el = $("toast");
  if (!el) return;
  el.textContent = stripPeriods(message);
  el.classList.toggle("ok", ok);
  el.classList.remove("hidden");
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.add("hidden"), 5200);
}

async function api(path, options = {}) {
  const resp = await fetch(path, options);
  let data = null;
  try {
    data = await resp.json();
  } catch (e) {
    data = { ok: false, error: `HTTP ${resp.status}` };
  }
  if (!resp.ok && data && data.ok === undefined) data.ok = false;
  return data;
}

function sourceLabel(kind) {
  return {
    esp32: "真机",
    replay: "回放",
    upload: "上传",
    webcam: "摄像头",
    unknown: "未知",
  }[kind] || "未知";
}

function sourceBadge(kind) {
  const key = ["esp32", "replay", "upload", "webcam"].includes(kind) ? kind : "unknown";
  return `<span class="source-badge src-${key}">${sourceLabel(key)}</span>`;
}

function sourceName(kind) {
  return {
    esp32: "ESP32 真机",
    replay: "图片回放",
    upload: "上传图片",
    webcam: "本机摄像头",
    unknown: "未知来源",
  }[kind] || "未知来源";
}

function splitLocalTime(value) {
  const parts = captureDateParts(value);
  if (!parts) return null;
  return parts;
}

function localDateLabel(value) {
  const parts = splitLocalTime(value);
  if (!parts) return "时间未知";
  return `${parts.month}月${parts.day}日 ${pad2(parts.hour)}:${pad2(parts.minute)}`;
}

function localShortDate(value) {
  const parts = splitLocalTime(value);
  if (!parts) return "时间未知";
  return `${parts.month}月${parts.day}日`;
}

function categoryFor(item) {
  if (!item) return "其他";
  if (item.class_zh) return item.class_zh;
  const known = state.status?.classes?.map((c) => c.zh).filter(Boolean) || [];
  return known.find((name) => String(item.label || "").includes(name)) || "其他";
}

function objectSearchHref(label) {
  return `/search?q=${encodeURIComponent(`${label}在哪？`)}&autorun=1`;
}

function objectImage(object) {
  return object?.evidence_crop_url || object?.crop_url || "";
}

function linkStatusLabel(status) {
  return {
    ambiguous: "关联待确认",
    new: "新轨迹",
    matched: "已关联",
  }[status] || "已关联";
}

function captureTime(cap) {
  if (!cap) return "—";
  if (!cap.time_synced) return "时间未同步";
  return cap.captured_at_local || cap.captured_at_utc || "时间未知";
}

function observeTimeLabel(cap) {
  if (!cap) return "正在读取…";
  if (!cap.time_synced) return "时间未同步";
  const parts = splitLocalTime(cap.captured_at_local || cap.captured_at_utc);
  if (!parts) return "时间未知";
  const now = new Date();
  const sameDay =
    now.getFullYear() === parts.year &&
    now.getMonth() + 1 === parts.month &&
    now.getDate() === parts.day;
  const clock = `${pad2(parts.hour)}:${pad2(parts.minute)}:${pad2(parts.second)}`;
  return sameDay ? `今天 ${clock}` : `${parts.month}月${parts.day}日 ${clock}`;
}

function renderObserveFeature(cap, detections) {
  const list = $("observe-detected-list");
  const count = $("observe-detected-count");
  const time = $("observe-time");
  const zone = $("observe-zone");
  const id = $("observe-capture-id");
  const source = $("observe-feature-source");

  if (!cap) {
    if (list) list.innerHTML = '<span class="muted small">还没有检测结果</span>';
    if (count) count.textContent = "—";
    if (time) time.textContent = "还没有抓拍记录";
    if (zone) zone.textContent = "点击“立即抓拍”开始记录";
    if (id) id.textContent = "—";
    if (source) {
      source.className = "source-badge src-unknown";
      source.textContent = "未知来源";
    }
    return;
  }

  if (time) time.textContent = observeTimeLabel(cap);
  if (zone) {
    const zones = [...new Set((detections || []).map((d) => d.region).filter(Boolean))];
    zone.textContent = zones.length ? `${zones.slice(0, 2).join(" / ")} · 最近一次观察` : "最近一次观察";
  }
  if (id) id.textContent = `#${cap.id}`;
  if (count) count.textContent = `${(detections || []).length} 个`;
  if (source) {
    const kind = ["esp32", "replay", "upload", "webcam"].includes(cap.source_kind)
      ? cap.source_kind
      : "unknown";
    source.className = `source-badge src-${kind}`;
    source.textContent = sourceName(kind);
  }
  if (!list) return;
  if (!detections?.length) {
    list.innerHTML = '<span class="muted small">这一帧没有识别到词表内物品</span>';
    return;
  }
  list.innerHTML = detections
    .slice(0, 4)
    .map((detection) => {
      const label = escapeHtml(detection.class_zh || "物品");
      const thumb = detection.crop_url
        ? `<img src="${escapeHtml(detection.crop_url)}" alt="" loading="lazy" decoding="async" />`
        : '<span class="is-empty">无图</span>';
      return `<span class="observe-object">
        ${thumb}
        <span class="observe-object-copy">
          <strong>${label}</strong>
          <span>${escapeHtml(detection.region || "未分区")} · ${Math.round(Number(detection.confidence || 0) * 100)}%</span>
        </span>
      </span>`;
    })
    .join("");
}

function initNav() {
  document.querySelectorAll(".app-nav a[data-nav]").forEach((link) => {
    const active = link.dataset.nav === PAGE;
    link.classList.toggle("is-active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
}

// ---------------- 全局状态 ----------------
async function loadStatus() {
  try {
    const data = await api("/api/status");
    if (!data.ok) throw new Error(data.error || "状态读取失败");
    state.status = data;
    state.warmupDone = !!data.warmup_done;
    state.autoRunning = !!(data.service && data.service.running);

    const deviceChip = $("header-device");
    if (deviceChip) {
      deviceChip.classList.remove("is-warn");
      const label = deviceChip.querySelector("span");
      if (label) label.textContent = "本机在线";
    }

    const stats = data.pipeline?.stats || {};
    setPill("pill-db", `数据库 · ${stats.captures ?? 0} 帧 / ${stats.active_tracks ?? 0} 物品`, "ok");

    const sourceKind = data.source?.type || "unknown";
    setText(
      "home-source-state",
      { replay: "图片回放", esp32: "ESP32 真机", webcam: "本机摄像头", upload: "上传图片" }[sourceKind] ||
        "本地采集"
    );
    setText("home-source-note", `${stats.captures ?? 0} 帧观察 · 本地运行`);
    setText("home-capture-count", String(stats.captures ?? 0));
    const deviceState =
      data.device?.last_probe?.ok
        ? "在线"
        : { replay: "回放模式", esp32: "真机", webcam: "摄像头", upload: "上传模式" }[sourceKind] ||
          "未知";
    setText("home-device-state", deviceState);

    const det = data.pipeline?.detector || {};
    const emb = data.pipeline?.embedder || {};
    if (det.loaded && emb.loaded) {
      setPill("pill-model", "模型 · OWLv2 + DINOv2 就绪", "ok");
    } else if (data.warmup_done) {
      setPill("pill-model", "模型 · 加载失败", "bad");
    } else {
      setPill("pill-model", "模型 · 加载中…", "warn");
    }

    const src = data.source || {};
    if (src.type === "esp32") {
      setPill("pill-source", "采集源 · ESP32 真机", "");
      const el = $("pill-source");
      if (el) el.title = "真实设备采集";
    } else if (src.type === "replay") {
      setPill("pill-source", `采集源 · 图片回放（剩 ${src.replay_remaining ?? "?"} 张）`, "");
    } else {
      setPill("pill-source", `采集源 · ${src.type || "未知"}`, "");
    }

    setPill("pill-auto", `自动采集 · ${state.autoRunning ? "运行中" : "停止"}`, state.autoRunning ? "ok" : "");

    const btn = $("capture-btn");
    if (btn) {
      if (!state.warmupDone) {
        btn.disabled = true;
        btn.textContent = "模型加载中…";
      } else if (!state.busy) {
        btn.disabled = false;
        btn.textContent = "立即抓拍";
      }
    }

    const autoBtn = $("auto-btn");
    if (autoBtn) autoBtn.textContent = state.autoRunning ? "停止自动采集" : "开始自动采集";

    if (data.pipeline?.model_errors?.length) {
      setText("capture-status", "模型错误：" + data.pipeline.model_errors.join(" | "));
    }
  } catch (err) {
    setPill("pill-db", "服务不可用", "bad");
    const deviceChip = $("header-device");
    if (deviceChip) {
      deviceChip.classList.add("is-warn");
      const label = deviceChip.querySelector("span");
      if (label) label.textContent = "本机离线";
    }
    setText("home-source-state", "服务离线");
    setText("home-source-note", "请检查本地服务");
    setText("home-device-state", "离线");
  }
}

// ---------------- 最近观察 ----------------
function clearOverlay() {
  const overlay = $("overlay");
  if (overlay) overlay.innerHTML = "";
}

function drawDetections(detections, highlightId = null) {
  const overlay = $("overlay");
  if (!overlay) return;
  overlay.innerHTML = "";
  (detections || []).forEach((d) => {
    const b = d.bbox_norm || [0, 0, 1, 1];
    const box = document.createElement("div");
    box.className = "bbox" + (d.link_status === "ambiguous" ? " ambiguous" : "");
    box.style.left = `${b[0] * 100}%`;
    box.style.top = `${b[1] * 100}%`;
    box.style.width = `${Math.max(1, (b[2] - b[0]) * 100)}%`;
    box.style.height = `${Math.max(1, (b[3] - b[1]) * 100)}%`;
    box.style.opacity = highlightId && d.detection_id !== highlightId ? "0.28" : "1";
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.textContent = `${d.class_zh} ${Math.round((d.confidence || 0) * 100)}%`;
    box.appendChild(tag);
    overlay.appendChild(box);
  });
}

function renderDetectionList(detections, highlightId = null) {
  const list = $("detections-list");
  if (!list) return;
  list.innerHTML = "";
  if (!detections?.length) {
    list.innerHTML = '<p class="empty-note">这一帧没有识别到词表内物品</p>';
    return;
  }
  detections.forEach((d) => {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "detection-row" + (highlightId === d.detection_id ? " is-selected" : "");
    row.innerHTML = `
      <span class="detection-row-main">
        <strong>${escapeHtml(d.class_zh || "物品")}</strong>
        <span class="confidence">${Math.round((d.confidence || 0) * 100)}%</span>
      </span>
      <span class="detection-row-sub">${escapeHtml(d.region || "未分区")} · ${escapeHtml(linkStatusLabel(d.link_status))}${
        d.link_score != null ? ` · 关联分 ${Number(d.link_score).toFixed(2)}` : ""
      }</span>`;
    row.onclick = () => {
      state.highlightedDetectionId = state.highlightedDetectionId === d.detection_id ? null : d.detection_id;
      renderDetectionList(detections, state.highlightedDetectionId);
      drawDetections(detections, state.highlightedDetectionId);
    };
    list.appendChild(row);
  });
}

function summarizeCapture(cap, detections) {
  const labels = [...new Set((detections || []).map((d) => d.class_zh).filter(Boolean))];
  if (!labels.length) return "这一帧没有识别到词表内物品";
  return `识别到 ${labels.length} 类物品：${labels.slice(0, 6).join("、")}${labels.length > 6 ? " 等" : ""}`;
}

function setSummaryOpen(open) {
  const panel = $("summary-panel");
  const trigger = $("summary-trigger");
  const pin = $("summary-pin");
  if (!panel || !trigger) return;
  panel.classList.toggle("is-open", open);
  panel.setAttribute("aria-hidden", open ? "false" : "true");
  trigger.setAttribute("aria-expanded", open ? "true" : "false");
  trigger.setAttribute("aria-label", open ? "收起识别摘要" : "展开识别摘要");
  trigger.classList.toggle("is-pinned", state.summaryPinned && open);
  if (pin) pin.setAttribute("aria-pressed", state.summaryPinned ? "true" : "false");
}

function openSummary(pin = false) {
  clearTimeout(state.summaryTimer);
  state.summaryTimer = null;
  if (pin) state.summaryPinned = true;
  setSummaryOpen(true);
}

function closeSummary() {
  clearTimeout(state.summaryTimer);
  state.summaryTimer = null;
  state.summaryPinned = false;
  setSummaryOpen(false);
}

function scheduleSummaryClose() {
  if (state.summaryPinned) return;
  clearTimeout(state.summaryTimer);
  state.summaryTimer = setTimeout(() => {
    state.summaryTimer = null;
    setSummaryOpen(false);
  }, 520);
}

function bindSummaryOverlay() {
  const hotzone = $("summary-hotzone");
  const trigger = $("summary-trigger");
  const panel = $("summary-panel");
  const pin = $("summary-pin");
  if (!trigger || !panel) return;
  const hoverCapable = window.matchMedia("(hover: hover) and (pointer: fine)").matches;

  const enter = () => {
    if (!hoverCapable) return;
    clearTimeout(state.summaryTimer);
    state.summaryTimer = null;
    setSummaryOpen(true);
  };
  const leave = () => {
    if (!hoverCapable) return;
    scheduleSummaryClose();
  };

  [hotzone, trigger, panel].forEach((el) => {
    if (!el) return;
    el.addEventListener("mouseenter", enter);
    el.addEventListener("mouseleave", leave);
  });

  trigger.addEventListener("click", (event) => {
    event.stopPropagation();
    const open = panel.classList.contains("is-open");
    if (!open) openSummary(true);
    else if (!state.summaryPinned) openSummary(true);
    else closeSummary();
  });

  if (pin) {
    pin.addEventListener("click", (event) => {
      event.stopPropagation();
      state.summaryPinned = !state.summaryPinned;
      setSummaryOpen(true);
    });
  }

  document.addEventListener("pointerdown", (event) => {
    if (!panel.classList.contains("is-open")) return;
    const target = event.target;
    if (!(target instanceof Element)) return;
    if (target.closest("#summary-panel, #summary-trigger, #summary-hotzone")) return;
    closeSummary();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && panel.classList.contains("is-open")) closeSummary();
  });

  trigger.addEventListener("focus", () => {
    if (hoverCapable) openSummary(false);
  });
}

function setStageCount(count) {
  setText("stage-detections", `${count} 检测`);
  setText("summary-trigger-count", String(count));
}

function showEmptyCapture() {
  state.currentCapture = null;
  state.highlightedDetectionId = null;
  const placeholder = $("viewport-placeholder");
  if (placeholder) placeholder.classList.remove("hidden");
  const viewport = $("viewport");
  if (viewport) viewport.style.aspectRatio = "4 / 3";
  const img = $("capture-img");
  if (img) {
    img.hidden = true;
    img.removeAttribute("src");
  }
  clearOverlay();
  setText("capture-time", "—");
  setStageCount(0);
  setText("capture-summary", "还没有抓拍记录");
  const source = $("capture-source");
  if (source) {
    source.className = "source-badge src-unknown";
    source.textContent = "未知来源";
  }
  const list = $("detections-list");
  if (list) list.innerHTML = '<p class="empty-note">还没有检测结果</p>';
  renderObserveFeature(null, []);
  closeSummary();
}

async function showCapture(captureId) {
  const detail = await api(`/api/captures/${captureId}`);
  if (!detail.ok) {
    toast(detail.error || "读取抓拍详情失败");
    return false;
  }
  state.currentCapture = detail;
  const cap = detail.capture;
  const detections = detail.detections || [];
  state.highlightedDetectionId = null;

  const placeholder = $("viewport-placeholder");
  if (placeholder) placeholder.classList.add("hidden");
  const viewport = $("viewport");
  if (viewport) {
    const ratioWidth = Number(cap.width);
    const ratioHeight = Number(cap.height);
    viewport.style.aspectRatio =
      ratioWidth > 0 && ratioHeight > 0 ? `${ratioWidth} / ${ratioHeight}` : "4 / 3";
  }
  const img = $("capture-img");
  if (img) {
    const base = cap.image_url || `/api/captures/${cap.id}/image`;
    img.src = `${base}${base.includes("?") ? "&" : "?"}t=${Date.now()}`;
    img.alt = `抓拍 #${cap.id}`;
    img.hidden = false;
  }

  setText("capture-time", captureTime(cap));
  setStageCount(detections.length);
  setText("capture-summary", summarizeCapture(cap, detections));

  const source = $("capture-source");
  if (source) {
    const key = ["esp32", "replay", "upload", "webcam"].includes(cap.source_kind)
      ? cap.source_kind
      : "unknown";
    source.className = `source-badge src-${key}`;
    source.textContent = sourceLabel(key);
  }

  renderDetectionList(detections);
  drawDetections(detections);
  renderObserveFeature(cap, detections);
  return true;
}

async function loadLatestCapture() {
  const data = await api("/api/captures?limit=1");
  if (!data.ok) {
    showEmptyCapture();
    return;
  }
  const captures = data.captures || [];
  if (!captures.length) {
    showEmptyCapture();
    return;
  }
  await showCapture(captures[0].id);
}

async function doCapture() {
  if (state.busy) return;
  state.busy = true;
  const btn = $("capture-btn");
  if (btn) {
    btn.disabled = true;
    btn.textContent = "抓拍与识别中…";
  }
  setText("capture-status", "正在抓拍…");
  try {
    const data = await api("/api/capture", { method: "POST" });
    if (!data.ok) {
      const msg = data.error || "未知错误";
      setText("capture-status", `抓拍失败：${msg}`);
      toast(`抓拍失败：${msg}`);
      return;
    }
    setText("capture-status", `本次识别到 ${(data.detections || []).length} 个物品` +
        (data.warnings?.length ? ` · ${data.warnings.join("；")}` : "")
    );
    await Promise.all([showCapture(data.capture_id), loadStatus()]);
    await loadObserveRecent();
    toast("抓拍完成，已写入本地记忆", true);
  } catch (err) {
    toast(`抓拍失败：${err}`);
  } finally {
    state.busy = false;
    if (btn) {
      btn.disabled = false;
      btn.textContent = "立即抓拍";
    }
  }
}

async function toggleAuto() {
  const path = state.autoRunning ? "/api/service/stop" : "/api/service/start";
  const data = await api(path, { method: "POST" });
  if (!data.ok) {
    toast(data.error || "操作失败");
    return;
  }
  await loadStatus();
  toast(state.autoRunning ? "自动采集已启动" : "自动采集已停止", true);
}

// ---------------- 找找物品 ----------------
function normalizeSearchItem(r, fallbackLabel = "") {
  const label = r.label || r.class_zh || fallbackLabel || "物品";
  return {
    label,
    category: categoryFor({ ...r, label }),
    zone: r.zone || "未分区",
    time_local: r.time_local || null,
    time_synced: r.time_synced !== false,
    time_ago: r.time_ago || "",
    source_kind: r.source_kind || "unknown",
    confidence: Number(r.confidence || 0),
    capture_id: r.capture_id || null,
    track_id: r.track_id || null,
    crop_url: r.crop_url || r.evidence_crop_url || "",
    link_status: r.link_status || "matched",
    link_score: r.link_score,
    sightings: r.sightings,
    uncertainty: r.uncertainty || "",
  };
}

function searchTimestamp(item) {
  if (!item.time_local) return Number.NEGATIVE_INFINITY;
  const parts = splitLocalTime(item.time_local);
  if (!parts) return Number.NEGATIVE_INFINITY;
  return new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second).getTime();
}

function searchRangeMatches(item) {
  if (state.searchRange === "all") return true;
  if (!item.time_synced) return false;
  const timestamp = searchTimestamp(item);
  if (!Number.isFinite(timestamp)) return false;
  const days = state.searchRange === "7" ? 7 : 30;
  return Date.now() - timestamp <= days * 86400000;
}

function renderFilterCategories() {
  const box = $("filter-categories");
  if (!box) return;
  const source = state.searchQuery ? state.searchItems : state.searchBase;
  const counts = new Map();
  source.forEach((object) => {
    const category = object.category || categoryFor(object);
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  const categories = [...counts.entries()].sort((a, b) => b[1] - a[1]);
  const allActive = state.searchCategory === "all" ? " is-active" : "";
  box.innerHTML = `
    <button class="filter-btn${allActive}" type="button" data-filter-category="all">
      <span>全部</span><span class="filter-count">${source.length}</span>
    </button>
    ${categories
      .map(
        ([category, count]) => `<button class="filter-btn${
          state.searchCategory === category ? " is-active" : ""
        }" type="button" data-filter-category="${escapeHtml(category)}">
          <span>${escapeHtml(category)}</span><span class="filter-count">${count}</span>
        </button>`
      )
      .join("")}`;
}

function updateFilterButtonState() {
  document.querySelectorAll("[data-filter-category]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.filterCategory === state.searchCategory);
  });
  document.querySelectorAll("[data-filter-range]").forEach((button) => {
    button.classList.toggle("is-active", button.dataset.filterRange === state.searchRange);
  });
}

function resultLink(item, label = "查看详情") {
  if (!item.capture_id) {
    return `<span class="result-link" aria-disabled="true">${label}</span>`;
  }
  return `<a class="result-link" href="/observe?capture=${encodeURIComponent(item.capture_id)}">${label} <span aria-hidden="true">›</span></a>`;
}

function buildSearchCard(item) {
  const label = escapeHtml(item.label);
  const category = escapeHtml(item.category || "物品");
  const image = item.crop_url
    ? `<img src="${escapeHtml(item.crop_url)}" alt="${label}" loading="lazy" decoding="async" data-fallback-class="thumb-empty" data-fallback-text="无图" />`
    : '<span class="thumb-empty">无图</span>';
  const timeLabel = item.time_synced === false ? "时间未同步" : localDateLabel(item.time_local);
  const relation =
    item.link_status === "ambiguous"
      ? "关联待确认"
      : item.link_status === "new"
        ? "新轨迹"
        : "已关联到我的物品";
  const evidence =
    item.sightings != null
      ? `识别到${category}，${relation} · 共 ${item.sightings} 次观测`
      : `识别到${category}，${relation}`;
  const media = item.capture_id
    ? `<a class="thumb" href="/observe?capture=${encodeURIComponent(item.capture_id)}" aria-label="查看${label}的观察详情">${image}</a>`
    : `<span class="thumb">${image}</span>`;
  return `<article class="result" data-category="${category}">
    ${media}
    <div class="result-copy">
      <div class="result-top">
        <span class="result-label">${category}</span>
        ${sourceBadge(item.source_kind)}
      </div>
      <h3>${timeLabel}</h3>
      <span class="result-meta-row">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M12 21s6-5.3 6-10a6 6 0 1 0-12 0c0 4.7 6 10 6 10Z"/><circle cx="12" cy="11" r="2"/></svg>
        ${escapeHtml(item.zone)}
      </span>
      <span class="result-evidence">${escapeHtml(evidence)}</span>
    </div>
    ${resultLink(item)}
  </article>`;
}

function renderSearchItems() {
  const results = $("results");
  if (!results) return;
  const visible = state.searchItems.filter(
    (item) =>
      (state.searchCategory === "all" || item.category === state.searchCategory) &&
      searchRangeMatches(item)
  );
  updateFilterButtonState();
  const label = $("result-count");
  if (label) {
    label.textContent = state.searchQuery
      ? `找到 ${visible.length} 条相关结果`
      : `最近记住的 ${visible.length} 件物品`;
  }
  if (!visible.length) {
    results.innerHTML =
      '<p class="search-empty">没有符合条件的记录</p>';
    return;
  }
  results.innerHTML = visible.map(buildSearchCard).join("");
}

async function loadSearchBase() {
  const results = $("results");
  if (results) results.innerHTML = '<p class="empty-note">正在读取本地物品库…</p>';
  try {
    const data = await api("/api/objects");
    if (!data.ok) throw new Error(data.error || "读取失败");
    state.searchBase = data.objects || [];
    state.searchItems = state.searchBase.map((object) => normalizeSearchItem(object));
    state.searchQuery = "";
    state.searchCategory = "all";
    state.searchRange = "all";
    const heroImage = $("search-hero-img");
    const heroArt = document.querySelector(".search-hero-art");
    const heroSource = state.searchBase.find((object) => object.evidence_image_url);
    if (heroImage && heroSource) {
      heroImage.src = heroSource.evidence_image_url;
      heroImage.alt = "最近一次真实抓拍";
      heroImage.hidden = false;
      heroImage.addEventListener(
        "error",
        () => {
          heroImage.hidden = true;
          if (heroArt) heroArt.hidden = true;
        },
        { once: true }
      );
    } else if (heroArt) {
      heroArt.hidden = true;
    }
    const answer = $("answer");
    if (answer) {
      answer.classList.add("hidden");
      answer.textContent = "";
    }
    setText("query-intent", "");
    renderFilterCategories();
    renderSearchItems();
  } catch (error) {
    if (results) {
      results.innerHTML = '<p class="search-empty">读取本地物品库失败，请确认本地服务正常</p>';
    }
  }
}

async function runQuery(text) {
  const input = $("query-input");
  const q = ((text ?? input?.value) || "").trim();
  if (!q) return;
  if (input) input.value = q;
  const answer = $("answer");
  const results = $("results");
  if (answer) {
    answer.classList.remove("hidden", "notfound", "help");
    answer.textContent = "正在检索本地记忆…";
  }
  if (results) results.innerHTML = '<p class="empty-note">正在检索本地记忆…</p>';
  try {
    const data = await api("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: q }),
    });
    if (!data.ok) throw new Error(data.error || data.detail || "查询失败");
    renderAnswer(data);
  } catch (err) {
    if (answer) answer.textContent = `查询失败：${err}`;
    if (results) results.innerHTML = '<p class="search-empty">查询失败，请确认本地服务正常</p>';
  }
}

function renderAnswer(data) {
  const answer = $("answer");
  if (!answer) return;
  answer.classList.remove("hidden", "notfound", "help");
  if (data.status === "not_found" || data.status === "empty") answer.classList.add("notfound");
  if (data.status === "help") answer.classList.add("help");
  answer.textContent = stripPeriods(data.answer || "（没有回答）");
  setText("query-intent", data.intent_zh ? `意图：${data.intent_zh}` : "");

  const oldNotes = document.getElementById("answer-notes");
  if (oldNotes) oldNotes.remove();
  if (data.notes?.length) {
    const nb = document.createElement("div");
    nb.id = "answer-notes";
    nb.className = "notes";
    data.notes.forEach((n) => {
      const p = document.createElement("div");
      p.className = "note";
      p.textContent = "⚠ " + stripPeriods(n);
      nb.appendChild(p);
    });
    answer.after(nb);
  }

  const items = [];
  (data.results || []).forEach((r) => {
    if (r.events) {
      r.events.forEach((event) => items.push(normalizeSearchItem(event, r.label || r.class_zh)));
      return;
    }
    if (r.items) {
      r.items.forEach((item) => items.push(normalizeSearchItem(item, r.label || r.class_zh)));
      return;
    }
    items.push(normalizeSearchItem(r));
  });
  state.searchItems = items;
  state.searchQuery = data.query || "";
  state.searchCategory = "all";
  state.searchRange = "all";
  renderFilterCategories();
  renderSearchItems();
}

// ---------------- 我的物品 ----------------
const ITEMS_AUTO_SPEED = 4.2;
const ITEMS_DRAG_SPEED = 0.28;
const ITEMS_PITCH_LIMIT = 74;
const ITEMS_GOLDEN_ANGLE = 2.399963229728653;

function objectLabel(o) {
  return o.label || o.class_zh || "物品";
}

function objectWhen(o) {
  if (o.time_synced === false) return "时间未同步";
  return o.time_ago || o.time_local || "—";
}

function clampNumber(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function orbCopiesFor(n) {
  if (n <= 1) return 24;
  if (n === 2) return 12;
  if (n <= 5) return 6;
  if (n <= 8) return 5;
  if (n <= 12) return 4;
  if (n <= 20) return 3;
  if (n <= 30) return 2;
  return 1;
}

function orbPointFor(index, tileCount) {
  const y = 1 - (2 * (index + 0.5)) / tileCount;
  const ring = Math.sqrt(Math.max(0, 1 - y * y));
  const theta = index * ITEMS_GOLDEN_ANGLE;
  return {
    x: Math.cos(theta) * ring,
    y,
    z: Math.sin(theta) * ring,
  };
}

function createItemsOrb(stage) {
  const sphere = $("orb-sphere");
  const selection = $("orb-selection");
  const reducedQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
  const orb = {
    yaw: -16,
    pitch: -7,
    velYaw: 0,
    velPitch: 0,
    active: false,
    pageVisible: !document.hidden,
    hovering: null,
    selected: null,
    pressing: false,
    dragging: false,
    pointerId: null,
    pendingTile: null,
    startX: 0,
    startY: 0,
    lastX: 0,
    lastY: 0,
    lastAt: 0,
    suppressHoverUntil: 0,
    frameId: 0,
    lastFrameAt: 0,
  };
  let reducedMotion = reducedQuery.matches;
  let orbRadius = 0;

  function measureRadius() {
    if (!stage.clientWidth) return;
    const raw = getComputedStyle(stage).getPropertyValue("--orb-radius-ratio").trim();
    const ratio = Number.parseFloat(raw);
    orbRadius = stage.clientWidth * (Number.isFinite(ratio) && ratio > 0 ? ratio : 0.38);
  }

  function applyProjection() {
    if (!sphere) return;
    orb.yaw = ((orb.yaw % 360) + 360) % 360;
    if (!orbRadius) {
      measureRadius();
      if (!orbRadius) return;
    }
    const yaw = (orb.yaw * Math.PI) / 180;
    const pitch = (orb.pitch * Math.PI) / 180;
    const cosY = Math.cos(yaw);
    const sinY = Math.sin(yaw);
    const cosP = Math.cos(pitch);
    const sinP = Math.sin(pitch);
    for (const tile of sphere.children) {
      const point = tile._orbPoint;
      if (!point) continue;
      const x1 = point.x * cosY + point.z * sinY;
      const z1 = -point.x * sinY + point.z * cosY;
      const y2 = point.y * cosP - z1 * sinP;
      const z2 = point.y * sinP + z1 * cosP;
      const perspective = 1 + z2 * 0.06;
      const x = x1 * orbRadius * perspective;
      const y = -y2 * orbRadius * perspective;
      const scale = 0.78 + ((z2 + 1) / 2) * 0.3;
      const opacity = z2 >= 0 ? 1 : 0;
      const lifted = z2 > 0.02 && (tile === orb.hovering || tile === orb.selected);
      tile.style.transform = `translate3d(${x.toFixed(2)}px, ${y.toFixed(2)}px, 0) scale(${scale.toFixed(3)})`;
      tile.style.opacity = opacity.toFixed(3);
      tile.style.zIndex = lifted ? "260" : String(Math.round(100 + z2 * 100));
      tile.style.pointerEvents = z2 > 0.02 ? "auto" : "none";
      const isBack = z2 < 0;
      if (tile._isBack !== isBack) {
        tile.classList.toggle("is-back", isBack);
        tile._isBack = isBack;
      }
    }
    stage.dataset.yaw = orb.yaw.toFixed(3);
    stage.dataset.pitch = orb.pitch.toFixed(3);
  }

  function stopLoop() {
    if (orb.frameId) cancelAnimationFrame(orb.frameId);
    orb.frameId = 0;
  }

  function canIdle() {
    return (
      orb.active &&
      orb.pageVisible &&
      !orb.pressing &&
      !orb.dragging &&
      !orb.hovering &&
      !orb.selected
    );
  }

  function startLoop(resetClock = true) {
    if (orb.frameId || !canIdle()) return;
    if (resetClock || !orb.lastFrameAt) orb.lastFrameAt = performance.now();
    orb.frameId = requestAnimationFrame(step);
  }

  function step(timestamp) {
    orb.frameId = 0;
    if (!canIdle()) return;
    const dt = Math.min(64, Math.max(0, timestamp - (orb.lastFrameAt || timestamp)));
    orb.lastFrameAt = timestamp;
    const spinning = Math.abs(orb.velYaw) > 0.4 || Math.abs(orb.velPitch) > 0.4;
    if (spinning) {
      orb.yaw += (orb.velYaw * dt) / 1000;
      orb.pitch = clampNumber(orb.pitch + (orb.velPitch * dt) / 1000, -ITEMS_PITCH_LIMIT, ITEMS_PITCH_LIMIT);
      const decay = Math.exp((-3.1 * dt) / 1000);
      orb.velYaw = Math.abs(orb.velYaw) < 0.6 ? 0 : orb.velYaw * decay;
      orb.velPitch = Math.abs(orb.velPitch) < 0.6 ? 0 : orb.velPitch * decay;
      if (Math.abs(orb.pitch) >= ITEMS_PITCH_LIMIT) orb.velPitch = 0;
    } else {
      orb.velYaw = 0;
      orb.velPitch = 0;
      if (!reducedMotion) orb.yaw += (ITEMS_AUTO_SPEED * dt) / 1000;
    }
    applyProjection();
    if (!reducedMotion) startLoop(false);
  }

  function clearHover() {
    if (orb.hovering) orb.hovering.classList.remove("is-hovered");
    orb.hovering = null;
  }

  function setHovered(tile) {
    if (orb.hovering === tile) return;
    clearHover();
    if (!tile) {
      applyProjection();
      if (!orb.selected) startLoop(true);
      return;
    }
    orb.hovering = tile;
    tile.classList.add("is-hovered");
    orb.velYaw = 0;
    orb.velPitch = 0;
    stopLoop();
    applyProjection();
  }

  function clearSelection() {
    if (orb.selected) orb.selected.classList.remove("is-selected");
    orb.selected = null;
    if (selection) selection.textContent = "";
    applyProjection();
    if (orb.active) startLoop(true);
  }

  function selectTile(tile) {
    if (!tile || !stage.contains(tile)) {
      clearSelection();
      return;
    }
    if (orb.selected === tile) {
      clearSelection();
      return;
    }
    clearHover();
    if (orb.selected) orb.selected.classList.remove("is-selected");
    orb.selected = tile;
    tile.classList.add("is-selected");
    orb.velYaw = 0;
    orb.velPitch = 0;
    stopLoop();
    updateSelectionText(tile);
    applyProjection();
  }

  function updateSelectionText(tile) {
    if (!selection || !tile) return;
    const object = state.objects[Number(tile.dataset.objectIndex)];
    if (!object) {
      selection.textContent = "";
      return;
    }
    const sightings = object.sightings ?? 0;
    selection.textContent =
      `${objectLabel(object)} · ${object.zone || "未分区"} · ` +
      `最后出现 ${objectWhen(object)} · ${sightings} 次观测`;
  }

  function finishPointer(event, cancelled) {
    if (!orb.pressing) return;
    if (event && event.pointerId !== orb.pointerId) return;
    const tile = orb.pendingTile;
    const wasDragging = orb.dragging;
    if (wasDragging) {
      orb.suppressHoverUntil = performance.now() + 260;
      if (performance.now() - orb.lastAt > 140) {
        orb.velYaw = 0;
        orb.velPitch = 0;
      }
    }
    orb.pressing = false;
    orb.dragging = false;
    orb.pointerId = null;
    orb.pendingTile = null;
    stage.classList.remove("is-pressing", "is-dragging");
    if (stage.hasPointerCapture?.(event?.pointerId)) {
      try {
        stage.releasePointerCapture(event.pointerId);
      } catch (error) {
        // 指针已释放时无需处理
      }
    }
    if (cancelled) {
      orb.velYaw = 0;
      orb.velPitch = 0;
      clearHover();
      if (orb.active) startLoop(true);
      return;
    }
    if (wasDragging) {
      if (reducedMotion) {
        orb.velYaw = 0;
        orb.velPitch = 0;
      }
      if (orb.active) startLoop(true);
      return;
    }
    selectTile(tile);
  }

  function onPointerDown(event) {
    if (event.pointerType === "mouse" && event.button !== 0) return;
    if (orb.pressing || orb.pointerId !== null) return;
    orb.pressing = true;
    orb.dragging = false;
    orb.pointerId = event.pointerId;
    orb.pendingTile = event.target.closest(".orb-tile");
    orb.startX = event.clientX;
    orb.startY = event.clientY;
    orb.lastX = event.clientX;
    orb.lastY = event.clientY;
    orb.lastAt = performance.now();
    orb.velYaw = 0;
    orb.velPitch = 0;
    clearHover();
    stopLoop();
    stage.classList.add("is-pressing");
    try {
      stage.setPointerCapture(event.pointerId);
    } catch (error) {
      // 触屏浏览器可能不支持捕获，指针事件仍可继续
    }
    event.preventDefault();
  }

  function onPointerMove(event) {
    if (!orb.pressing || event.pointerId !== orb.pointerId) return;
    if (event.pointerType === "mouse" && event.buttons === 0) {
      finishPointer(event, true);
      return;
    }
    const dx = event.clientX - orb.lastX;
    const dy = event.clientY - orb.lastY;
    const total = Math.hypot(event.clientX - orb.startX, event.clientY - orb.startY);
    if (!orb.dragging && total >= 4) {
      orb.dragging = true;
      stage.classList.add("is-dragging");
      clearHover();
      clearSelection();
      stopLoop();
    }
    if (!orb.dragging) {
      orb.lastX = event.clientX;
      orb.lastY = event.clientY;
      orb.lastAt = performance.now();
      return;
    }
    event.preventDefault();
    const now = performance.now();
    const dt = Math.max(8, now - orb.lastAt);
    orb.yaw += dx * ITEMS_DRAG_SPEED;
    orb.pitch = clampNumber(orb.pitch + dy * ITEMS_DRAG_SPEED, -ITEMS_PITCH_LIMIT, ITEMS_PITCH_LIMIT);
    orb.velYaw = clampNumber(
      orb.velYaw * 0.6 + ((dx * ITEMS_DRAG_SPEED) / dt) * 1000 * 0.4,
      -520,
      520
    );
    orb.velPitch = clampNumber(
      orb.velPitch * 0.6 + ((dy * ITEMS_DRAG_SPEED) / dt) * 1000 * 0.4,
      -520,
      520
    );
    if (Math.abs(orb.pitch) >= ITEMS_PITCH_LIMIT) orb.velPitch = 0;
    orb.lastX = event.clientX;
    orb.lastY = event.clientY;
    orb.lastAt = now;
    applyProjection();
  }

  function onPointerOver(event) {
    if (event.pointerType === "touch") return;
    if (orb.pressing || orb.dragging || orb.selected) return;
    if (performance.now() < orb.suppressHoverUntil) return;
    const tile = event.target.closest(".orb-tile");
    if (tile && stage.contains(tile)) setHovered(tile);
  }

  function onPointerOut(event) {
    const tile = event.target.closest(".orb-tile");
    if (!tile || orb.hovering !== tile) return;
    if (event.relatedTarget && tile.contains(event.relatedTarget)) return;
    setHovered(null);
  }

  function onPointerLeave() {
    if (!orb.pressing && !orb.dragging) setHovered(null);
  }

  function onVisibilityChange() {
    orb.pageVisible = !document.hidden;
    if (!orb.pageVisible) {
      finishPointer(null, true);
      stopLoop();
      return;
    }
    if (orb.active) startLoop(true);
  }

  function onReducedMotionChange(event) {
    reducedMotion = event.matches;
    if (reducedMotion) {
      orb.velYaw = 0;
      orb.velPitch = 0;
      stopLoop();
    } else if (orb.active) {
      startLoop(true);
    }
  }

  function onKeyDown(event) {
    const step = event.shiftKey ? 28 : 12;
    let handled = true;
    if (event.key === "ArrowLeft") orb.yaw -= step;
    else if (event.key === "ArrowRight") orb.yaw += step;
    else if (event.key === "ArrowUp") orb.pitch = clampNumber(orb.pitch - step, -ITEMS_PITCH_LIMIT, ITEMS_PITCH_LIMIT);
    else if (event.key === "ArrowDown") orb.pitch = clampNumber(orb.pitch + step, -ITEMS_PITCH_LIMIT, ITEMS_PITCH_LIMIT);
    else handled = false;
    if (!handled) return;
    event.preventDefault();
    applyProjection();
  }

  stage.addEventListener("pointerdown", onPointerDown);
  stage.addEventListener("pointermove", onPointerMove);
  stage.addEventListener("pointerup", (event) => finishPointer(event, false));
  stage.addEventListener("pointercancel", (event) => finishPointer(event, true));
  stage.addEventListener("lostpointercapture", (event) => finishPointer(event, true));
  window.addEventListener("blur", () => finishPointer(null, true));
  stage.addEventListener("pointerover", onPointerOver);
  stage.addEventListener("pointerout", onPointerOut);
  stage.addEventListener("pointerleave", onPointerLeave);
  stage.addEventListener("keydown", onKeyDown);
  document.addEventListener("visibilitychange", onVisibilityChange);
  if (reducedQuery.addEventListener) reducedQuery.addEventListener("change", onReducedMotionChange);
  else if (reducedQuery.addListener) reducedQuery.addListener(onReducedMotionChange);
  measureRadius();
  if (typeof ResizeObserver !== "undefined") {
    const resizeObserver = new ResizeObserver(() => {
      measureRadius();
      applyProjection();
    });
    resizeObserver.observe(stage);
  } else {
    window.addEventListener("resize", () => {
      measureRadius();
      applyProjection();
    });
  }
  applyProjection();

  return {
    setActive(active) {
      orb.active = !!active;
      if (!orb.active) {
        stopLoop();
        clearHover();
        clearSelection();
        orb.pressing = false;
        orb.dragging = false;
        orb.pointerId = null;
        orb.pendingTile = null;
        stage.classList.remove("is-pressing", "is-dragging");
        return;
      }
      measureRadius();
      applyProjection();
      startLoop(true);
    },
    resetForRender() {
      stopLoop();
      clearHover();
      orb.selected = null;
      if (selection) selection.textContent = "";
    },
    refresh() {
      measureRadius();
      applyProjection();
      if (orb.active) startLoop(true);
    },
    refreshSelection() {
      if (orb.selected) updateSelectionText(orb.selected);
    },
  };
}

function renderOrb(objects) {
  const sphere = $("orb-sphere");
  const empty = $("orb-empty");
  if (!sphere) return;
  state.itemsOrb?.resetForRender();
  sphere.innerHTML = "";
  if (empty) {
    empty.hidden = !!objects.length;
    empty.textContent = "还没有记录到物品";
  }
  const stage = $("orb-stage");
  if (stage) {
    stage.setAttribute(
      "aria-label",
      objects.length
        ? `可拖动物品图片球，共 ${objects.length} 件`
        : "物品图片球，暂无物品"
    );
  }
  const n = objects.length;
  if (!n) {
    state.itemsOrb?.setActive(false);
    state.itemsOrb?.refresh();
    return;
  }

  const copies = orbCopiesFor(n);
  const tileCount = n > 64 ? n : Math.min(64, n * copies);
  for (let i = 0; i < tileCount; i += 1) {
    const objectIndex = i % n;
    const o = objects[objectIndex];
    const label = objectLabel(o);
    const tile = document.createElement("div");
    tile.className = "orb-tile" + (o.evidence_crop_url ? "" : " no-image");
    tile.dataset.objectIndex = String(objectIndex);
    tile.setAttribute("aria-hidden", "true");
    tile._orbPoint = orbPointFor(i, tileCount);
    const face = document.createElement("div");
    face.className = "orb-face";
    if (o.evidence_crop_url) {
      const img = document.createElement("img");
      img.src = o.evidence_crop_url;
      img.alt = "";
      img.decoding = "async";
      img.draggable = false;
      img.dataset.fallbackClass = "tile-no-image";
      img.dataset.fallbackText = "无图";
      face.appendChild(img);
    } else {
      face.textContent = label.slice(0, 1) || "物";
    }
    tile.appendChild(face);
    sphere.appendChild(tile);
  }
  state.itemsOrb?.setActive(state.itemsMode === "orb");
  state.itemsOrb?.refresh();
}

function renderObjectGrid(objects) {
  const grid = $("objects");
  if (!grid) return;
  grid.innerHTML = "";
  setText("grid-count", `（${objects.length}）`);
  if (!objects.length) {
    grid.innerHTML = '<p class="empty-note">还没有记录到物品</p>';
    return;
  }
  objects.forEach((o, index) => {
    const label = objectLabel(o);
    const when = objectWhen(o);
    const zone = o.zone || "未分区";
    const sightings = o.sightings ?? 0;
    const tile = document.createElement("button");
    tile.type = "button";
    tile.className = "object-tile";
    tile.dataset.objectIndex = String(index);
    if (o.track_id != null) tile.dataset.trackId = String(o.track_id);
    tile.setAttribute(
      "aria-label",
      `查看${label}详情，${zone}，最后出现 ${when}，${sightings} 次观测`
    );
    tile.innerHTML = `
      <span class="tile-media">
        ${
          o.evidence_crop_url
            ? `<img alt="${escapeHtml(label)}" src="${escapeHtml(o.evidence_crop_url)}" loading="lazy" decoding="async" data-fallback-class="tile-no-image" data-fallback-text="图片不可用" />`
            : '<span class="tile-no-image">暂无图片</span>'
        }
      </span>
      <span class="tile-info">
        <span class="tile-copy">
          <span class="tile-name">${escapeHtml(label)}</span>
          <span class="tile-time">${escapeHtml(when)} · ${sightings} 次观测</span>
        </span>
        <span class="tile-chevron" aria-hidden="true">›</span>
      </span>`;
    tile.addEventListener("click", () => {
      if (o.track_id != null) openItemDetail(o.track_id, tile);
    });
    grid.appendChild(tile);
  });
}

function animateGridRows() {
  const grid = $("objects");
  if (!grid) return;
  const cols = getComputedStyle(grid).gridTemplateColumns.split(" ").filter(Boolean).length || 1;
  const tiles = [...grid.querySelectorAll(".object-tile")];
  if (!tiles.length) return;
  state.gridEntrancePending = false;
  clearTimeout(state.gridAnimationTimer);
  tiles.forEach((tile, i) => {
    const row = Math.floor(i / cols);
    tile.style.setProperty("--tile-delay", `${row * 110 + (i % cols) * 16}ms`);
    tile.classList.remove("is-entering");
  });
  void grid.offsetWidth;
  tiles.forEach((tile) => tile.classList.add("is-entering"));
  const maxDelay = Math.floor((tiles.length - 1) / cols) * 110 + (cols - 1) * 16;
  state.gridAnimationTimer = window.setTimeout(() => {
    tiles.forEach((tile) => tile.classList.remove("is-entering"));
  }, maxDelay + 560);
}

function refreshObjectTimes(objects) {
  const grid = $("objects");
  if (grid) {
    grid.querySelectorAll(".object-tile").forEach((tile) => {
      const object = objects[Number(tile.dataset.objectIndex)];
      if (!object) return;
      const when = objectWhen(object);
      const sightings = object.sightings ?? 0;
      const time = tile.querySelector(".tile-time");
      if (time) time.textContent = `${when} · ${sightings} 次观测`;
      tile.setAttribute(
        "aria-label",
        `查看${objectLabel(object)}详情，${object.zone || "未分区"}，最后出现 ${when}，${sightings} 次观测`
      );
    });
  }
  state.itemsOrb?.refreshSelection();
}

function objectSignature(objects) {
  return objects
    .map((o) =>
      [
        o.track_id,
        objectLabel(o),
        o.zone,
        o.sightings,
        o.evidence_crop_url,
        o.source_kind,
        o.time_synced,
        o.time_local,
      ].join("|")
    )
    .join("~");
}

function closeItemDetail() {
  const dialog = $("item-dialog");
  if (!dialog || dialog.hidden) return;
  dialog.hidden = true;
  document.body.style.overflow = "";
  state.itemDetailTrackId = null;
  const target = state.itemDetailReturnFocus;
  state.itemDetailReturnFocus = null;
  if (target && typeof target.focus === "function") target.focus({ preventScroll: true });
}

async function openItemDetail(trackId, origin) {
  const dialog = $("item-dialog");
  const body = $("item-dialog-body");
  if (!dialog || !body) return;
  state.itemDetailTrackId = trackId;
  state.itemDetailReturnFocus = origin || document.activeElement;
  dialog.hidden = false;
  document.body.style.overflow = "hidden";
  body.innerHTML = '<p class="empty-note">正在读取物品详情…</p>';
  const close = dialog.querySelector(".item-dialog-close");
  close?.focus({ preventScroll: true });
  try {
    const detail = await api(`/api/tracks/${trackId}`);
    if (state.itemDetailTrackId !== trackId) return;
    if (!detail.ok) throw new Error(detail.error || "读取失败");
    const track = detail.track || {};
    const detections = detail.detections || [];
    const label = track.label || track.class_zh || "物品";
    const latest = detections[0] || {};
    const image = latest.crop_url || latest.image_url || "";
    const sources = (track.source_kinds || []).map(sourceName).filter(Boolean);
    const history = detections
      .slice(0, 8)
      .map((detection) => {
        const thumb = detection.crop_url
          ? `<img src="${escapeHtml(detection.crop_url)}" alt="" loading="lazy" decoding="async" data-fallback-class="item-history-empty" data-fallback-text="无图" />`
          : '<span class="item-history-empty" aria-hidden="true"></span>';
        return `<li>
          ${thumb}
          <span class="item-history-copy">
            <strong>${escapeHtml(localDateLabel(detection.time_local))}</strong>
            <span>${escapeHtml(detection.zone || "未分区")} · ${sourceName(detection.source_kind)}</span>
          </span>
          <span class="item-history-score">${Math.round(Number(detection.confidence || 0) * 100)}%</span>
        </li>`;
      })
      .join("");
    body.innerHTML = `
      <div class="item-detail-media">
        ${image ? `<img src="${escapeHtml(image)}" alt="${escapeHtml(label)} 的真实裁剪图" data-fallback-class="thumb-empty" data-fallback-text="图片不可用" />` : '<span class="thumb-empty">暂无图片</span>'}
      </div>
      <div class="item-detail-copy">
        <h2 id="item-dialog-title">${escapeHtml(label)}</h2>
        <p class="item-detail-sub" id="item-dialog-sub">${escapeHtml(latest.zone || "未分区")} · ${escapeHtml(sources.join(" / ") || "来源未知")}</p>
        <div class="item-detail-stats">
          <div class="item-stat"><strong>${track.sightings ?? detections.length}</strong><span>次观测</span></div>
          <div class="item-stat"><strong>${escapeHtml(localShortDate(latest.time_local))}</strong><span>最近出现</span></div>
          <div class="item-stat"><strong>${sources.length || 0}</strong><span>种来源</span></div>
        </div>
        <div class="item-detail-actions">
          <a class="primary-link" href="${escapeHtml(objectSearchHref(label))}">查找这个物品 <span aria-hidden="true">→</span></a>
          <a href="/timeline">观察时间线</a>
        </div>
        <p class="item-history-title">最近观测记录</p>
        <ul class="item-history">${history || '<li class="timeline-detail-empty">还没有观测记录</li>'}</ul>
      </div>`;
    const title = $("item-dialog-title");
    if (title) title.setAttribute("tabindex", "-1");
  } catch (error) {
    if (state.itemDetailTrackId === trackId) {
      body.innerHTML = `<p class="empty-note">读取物品详情失败：${escapeHtml(stripPeriods(error.message || error))}</p>`;
    }
  }
}

function updateItemsModeButtons(mode) {
  document.querySelectorAll(".items-mode-btn").forEach((button) => {
    const active = button.dataset.itemsMode === mode;
    button.classList.toggle("is-active", active);
    button.setAttribute("aria-pressed", String(active));
  });
}

function applyItemsMode(mode) {
  const page = $("items-page");
  const orbView = $("orb-view");
  const gridView = $("grid-view");
  if (!page || !orbView || !gridView) return;
  state.itemsMode = mode;
  const isGrid = mode === "grid";
  page.classList.toggle("is-mode-grid", isGrid);
  orbView.setAttribute("aria-hidden", String(isGrid));
  orbView.inert = isGrid;
  gridView.removeAttribute("aria-hidden");
  gridView.inert = false;
  updateItemsModeButtons(mode);
  if (isGrid) {
    state.itemsOrb?.setActive(false);
    state.gridEntrancePending = true;
  } else {
    state.itemsOrb?.setActive(true);
  }
}

function setItemsMode(mode) {
  if (mode !== "orb" && mode !== "grid") return;
  const page = $("items-page");
  if (!page || state.itemsSwitching || state.itemsMode === mode) return;
  const currentView = state.itemsMode === "grid" ? $("grid-view") : $("orb-view");
  const nextView = mode === "grid" ? $("grid-view") : $("orb-view");
  if (!currentView || !nextView) return;
  const buttons = [...document.querySelectorAll(".items-mode-btn")];
  const focused = document.activeElement;
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  state.itemsSwitching = true;
  clearTimeout(state.itemsSwitchTimer);
  clearTimeout(state.itemsEnteringTimer);
  buttons.forEach((button) => {
    button.setAttribute("aria-disabled", "true");
  });
  const finish = () => {
    currentView.classList.remove("is-view-leaving");
    applyItemsMode(mode);
    nextView.classList.remove("is-view-entering");
    void nextView.offsetWidth;
    nextView.classList.add("is-view-entering");
    clearTimeout(state.itemsEnteringTimer);
    state.itemsEnteringTimer = window.setTimeout(() => {
      nextView.classList.remove("is-view-entering");
    }, 340);
    buttons.forEach((button) => {
      button.removeAttribute("aria-disabled");
    });
    state.itemsSwitching = false;
    if (focused && currentView.contains(focused)) {
      const activeButton = document.querySelector(`.items-mode-btn[data-items-mode="${mode}"]`);
      activeButton?.focus({ preventScroll: true });
    }
  };
  if (reducedMotion) {
    finish();
    return;
  }
  currentView.classList.add("is-view-leaving");
  state.itemsSwitchTimer = window.setTimeout(finish, 165);
}

function initItems() {
  const hoverQuery = window.matchMedia("(hover: hover) and (pointer: fine)");
  state.itemsHoverCapable = hoverQuery.matches;
  const stage = $("orb-stage");
  const hint = $("orb-hint");
  if (hint) hint.textContent = "拖动旋转 · 点击查看";
  if (hoverQuery.addEventListener) {
    hoverQuery.addEventListener("change", (event) => {
      state.itemsHoverCapable = event.matches;
    });
  }
  if (stage) state.itemsOrb = createItemsOrb(stage);
  document.querySelectorAll(".items-mode-btn").forEach((button) => {
    button.addEventListener("click", () => setItemsMode(button.dataset.itemsMode));
  });
  const dialog = $("item-dialog");
  dialog?.querySelectorAll("[data-item-close]").forEach((element) => {
    element.addEventListener("click", closeItemDetail);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") closeItemDetail();
  });
  applyItemsMode("orb");
  // 首屏动画结束后移除类名，避免球体/平铺切换时重播
  window.setTimeout(() => {
    document.querySelectorAll(".items-page .wm-enter").forEach((el) => {
      el.classList.remove("wm-enter");
    });
  }, 850);
}

async function loadObjects() {
  let data;
  try {
    data = await api("/api/objects");
  } catch (error) {
    data = { ok: false };
  }
  const grid = $("objects");
  if (!data.ok) {
    const message = "读取物品库失败，请确认本地服务正常";
    if (grid) grid.innerHTML = `<p class="empty-note">${message}</p>`;
    if (!state.objects.length) {
      setText("objects-count", "0");
      const empty = $("orb-empty");
      if (empty) {
        empty.hidden = false;
        empty.textContent = message;
      }
      state.itemsOrb?.setActive(false);
    }
    return;
  }
  const objects = data.objects || [];
  state.objects = objects;
  const signature = objectSignature(objects);
  if (signature === state.objectsSignature) {
    refreshObjectTimes(objects);
    return;
  }
  state.objectsSignature = signature;

  setText("objects-count", String(objects.length));
  renderOrb(objects);
  renderObjectGrid(objects);
  requestAnimationFrame(() => requestAnimationFrame(animateGridRows));
}

// ---------------- 首页 ----------------
function initHeroCarousel() {
  const hero = $("home-hero");
  if (!hero || hero.dataset.carouselBound) return;
  const slides = [...hero.querySelectorAll("[data-hero-slide]")];
  const dots = [...hero.querySelectorAll("[data-hero-dot]")];
  if (slides.length < 2 || dots.length < 2) return;
  hero.dataset.carouselBound = "1";
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");
  let index = 0;
  let timer = 0;

  const show = (next) => {
    index = (next + slides.length) % slides.length;
    slides.forEach((slide, slideIndex) => {
      slide.classList.toggle("is-active", slideIndex === index);
    });
    dots.forEach((dot, dotIndex) => {
      const active = dotIndex === index;
      dot.classList.toggle("is-active", active);
      dot.setAttribute("aria-pressed", String(active));
    });
  };

  const stop = () => {
    if (timer) window.clearInterval(timer);
    timer = 0;
  };

  const start = () => {
    stop();
    if (reduced.matches) return;
    timer = window.setInterval(() => show(index + 1), 6000);
  };

  dots.forEach((dot, dotIndex) => {
    dot.addEventListener("click", () => {
      show(dotIndex);
      start();
    });
  });
  hero.addEventListener("mouseenter", stop);
  hero.addEventListener("mouseleave", start);
  hero.addEventListener("focusin", stop);
  hero.addEventListener("focusout", (event) => {
    if (!hero.contains(event.relatedTarget)) start();
  });
  show(0);
  start();
}

function renderHomeObjects(objects, excludeCaptureId = null) {
  const box = $("home-objects");
  if (!box) return;
  const distinct = objects.filter((object) => object.capture_id !== excludeCaptureId);
  const seen = new Set();
  const items = distinct
    .filter((object) => {
      const label = objectLabel(object);
      if (seen.has(label)) return false;
      seen.add(label);
      return true;
    })
    .slice(0, 4);
  if (!items.length) {
    box.innerHTML = '<p class="empty-note">还没有记录到物品</p>';
    return;
  }
  box.innerHTML = items
    .map((object) => {
      const label = objectLabel(object);
      const image = objectImage(object)
        ? `<img src="${escapeHtml(objectImage(object))}" alt="${escapeHtml(label)}" loading="lazy" decoding="async" data-fallback-class="tile-no-image" data-fallback-text="暂无图片" />`
        : '<span class="tile-no-image">暂无图片</span>';
      return `<a class="mini-object" href="${escapeHtml(objectSearchHref(label))}">
        <span class="mini-object-media">${image}</span>
        <span class="mini-object-copy">
          <strong>${escapeHtml(label)}</strong>
          <span>${escapeHtml(objectWhen(object))}</span>
        </span>
      </a>`;
    })
    .join("");
}

function renderHomeCapture(capture, detail) {
  const image = $("home-capture-img");
  const empty = $("home-capture-empty");
  const link = $("home-capture");
  const detections = detail?.detections || [];
  const labels = [...new Set(detections.map((detection) => detection.class_zh).filter(Boolean))];
  if (!capture) {
    if (empty) empty.hidden = false;
    if (image) image.hidden = true;
    return;
  }
  if (link) link.href = `/observe?capture=${encodeURIComponent(capture.id)}`;
  if (image) {
    image.src = capture.image_url || `/api/captures/${capture.id}/image`;
    image.alt = `抓拍 #${capture.id}，${observeTimeLabel(capture)}`;
    image.hidden = false;
    if (empty) empty.hidden = true;
    image.addEventListener(
      "error",
      () => {
        image.hidden = true;
        if (empty) empty.hidden = false;
      },
      { once: true }
    );
  }
  setText("home-capture-time", observeTimeLabel(capture));
  const source = $("home-capture-source");
  if (source) {
    const kind = ["esp32", "replay", "upload", "webcam"].includes(capture.source_kind)
      ? capture.source_kind
      : "unknown";
    source.className = `source-badge src-${kind}`;
    source.textContent = sourceName(kind);
  }
  const objects = $("home-capture-objects");
  if (objects) {
    objects.innerHTML = labels.length
      ? labels
          .slice(0, 3)
          .map((label) => `<span class="object-pill">${escapeHtml(label)}</span>`)
          .join("")
      : '<span class="muted small">没有识别结果</span>';
  }
}

async function loadHome() {
  const form = $("home-search-form");
  const input = $("home-search-input");
  if (form && !form.dataset.bound) {
    form.dataset.bound = "1";
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const q = (input?.value || "").trim();
      if (q) location.href = `/search?q=${encodeURIComponent(q)}&autorun=1`;
      else input?.focus();
    });
  }
  initHeroCarousel();
  const [objectsData, capturesData] = await Promise.all([
    api("/api/objects").catch(() => ({ ok: false })),
    api("/api/captures?limit=1").catch(() => ({ ok: false })),
  ]);
  const objects = objectsData.ok ? objectsData.objects || [] : [];
  const capture = capturesData.ok ? (capturesData.captures || [])[0] : null;
  setText("home-object-count", String(objects.length));
  setText("home-capture-count", String(state.status?.pipeline?.stats?.captures ?? "—"));
  renderHomeObjects(objects, capture?.id);
  if (!capture) {
    renderHomeCapture(null);
    return;
  }
  let detail = null;
  try {
    const response = await api(`/api/captures/${capture.id}`);
    if (response.ok) detail = response;
  } catch (error) {
    detail = null;
  }
  renderHomeCapture(capture, detail);
}

// ---------------- 最近观察 · 历史列表 ----------------
function renderObserveRecent(captures, details) {
  const box = $("observe-recent");
  if (!box) return;
  if (!captures.length) {
    box.innerHTML = '<p class="empty-note">还没有历史抓拍</p>';
    return;
  }
  const detailById = new Map();
  captures.forEach((capture, index) => detailById.set(capture.id, details[index] || null));
  const ordered = [...captures].sort((a, b) => captureTimestamp(b) - captureTimestamp(a));
  const groups = new Map();
  ordered.forEach((capture) => {
    const key = timelineDayKey(capture);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(capture);
  });
  box.innerHTML = [...groups.entries()]
    .map(([key, items]) => {
      const meta = timelineDayMeta(key);
      const rows = items
        .map((capture) => {
          const detail = detailById.get(capture.id);
          const detections = detail?.detections || [];
          const labels = [...new Set(detections.map((d) => d.class_zh).filter(Boolean))];
          const zones = [...new Set(detections.map((d) => d.region).filter(Boolean))];
          const clock = timelineClock(capture);
          const thumb = capture.thumbnail_url
            ? `<img src="${escapeHtml(capture.thumbnail_url)}" alt="抓拍 #${capture.id} 缩略图" loading="lazy" decoding="async" data-fallback-class="observe-row-empty" data-fallback-text="无图" />`
            : '<span class="observe-row-empty">无图</span>';
          return `<button class="observe-row" type="button" data-capture-id="${capture.id}">
            ${thumb}
            <span class="observe-row-copy">
              <span class="observe-row-top">
                <time>${escapeHtml(clock.text)}</time>
                ${timelineSourceBadge(capture.source_kind)}
              </span>
              <span class="observe-row-objects">${labels.length ? labels.map(escapeHtml).join("、") : "没有识别到词表内物品"}</span>
              <span class="observe-row-meta">${zones.length ? escapeHtml(zones.slice(0, 2).join(" / ")) : "未分区"} · ${capture.detections_count ?? detections.length} 个识别结果</span>
            </span>
            <span class="observe-row-chevron" aria-hidden="true">›</span>
          </button>`;
        })
        .join("");
      return `<div class="observe-day">
        <h2 class="observe-day-head">${escapeHtml(meta.main)}<span>${escapeHtml(meta.sub)}</span></h2>
        ${rows}
      </div>`;
    })
    .join("");
  box.querySelectorAll("[data-capture-id]").forEach((row) => {
    row.addEventListener("click", async () => {
      const id = Number(row.dataset.captureId);
      if (!Number.isFinite(id)) return;
      const ok = await showCapture(id);
      if (ok) window.scrollTo({ top: 0, behavior: "smooth" });
    });
  });
}

async function loadObserveRecent() {
  const box = $("observe-recent");
  if (!box) return;
  const data = await api("/api/captures?limit=6");
  if (!data.ok) {
    box.innerHTML = '<p class="empty-note">读取历史抓拍失败，请确认本地服务正常</p>';
    return;
  }
  const captures = data.captures || [];
  const details = await Promise.all(
    captures.map(async (capture) => {
      try {
        const detail = await api(`/api/captures/${capture.id}`);
        return detail.ok ? detail : null;
      } catch (error) {
        return null;
      }
    })
  );
  renderObserveRecent(captures, details);
}
function pad2(value) {
  return String(value).padStart(2, "0");
}

function captureDateParts(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(
    String(value || "")
  );
  if (!match) return null;
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
    hour: Number(match[4] || 0),
    minute: Number(match[5] || 0),
    second: Number(match[6] || 0),
  };
}

function captureTimestamp(capture) {
  if (!capture || capture.time_synced === false) return Number.NEGATIVE_INFINITY;
  const parts = captureDateParts(capture.captured_at_local || capture.captured_at_utc);
  if (!parts) return Number.NEGATIVE_INFINITY;
  return new Date(parts.year, parts.month - 1, parts.day, parts.hour, parts.minute, parts.second).getTime();
}

function timelineDayKey(capture) {
  if (!capture || capture.time_synced === false) return "unsynced";
  const parts = captureDateParts(capture.captured_at_local || capture.captured_at_utc);
  if (!parts) return "unsynced";
  return `${parts.year}-${pad2(parts.month)}-${pad2(parts.day)}`;
}

function timelineDayMeta(key) {
  if (key === "unsynced") return { main: "时间未同步", sub: "设备时间不可用" };
  const parts = captureDateParts(key);
  if (!parts) return { main: "时间未知", sub: "日期不可用" };
  const date = new Date(parts.year, parts.month - 1, parts.day);
  const weekday = ["周日", "周一", "周二", "周三", "周四", "周五", "周六"][date.getDay()];
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const diff = Math.round((today.getTime() - date.getTime()) / 86400000);
  if (diff === 0) return { main: "今天", sub: `${parts.month}月${parts.day}日 · ${weekday}` };
  if (diff === 1) return { main: "昨天", sub: `${parts.month}月${parts.day}日 · ${weekday}` };
  return { main: `${parts.month}月${parts.day}日`, sub: `${parts.year} · ${weekday}` };
}

function timelineClock(capture) {
  if (!capture || capture.time_synced === false) {
    return { text: "时间未同步", iso: "", unsynced: true };
  }
  const parts = captureDateParts(capture.captured_at_local || capture.captured_at_utc);
  if (!parts) return { text: "时间未知", iso: "", unsynced: true };
  return {
    text: `${pad2(parts.hour)}:${pad2(parts.minute)}:${pad2(parts.second)}`,
    iso: capture.captured_at_utc || capture.captured_at_local || "",
    unsynced: false,
  };
}

function timelineSourceBadge(kind) {
  const key = ["esp32", "replay", "upload", "webcam"].includes(kind) ? kind : "unknown";
  const text = {
    esp32: "来自 · ESP32",
    replay: "来自 · 图片回放",
    upload: "来自 · 上传图片",
    webcam: "来自 · 摄像头",
    unknown: "来源未知",
  }[key];
  const title = key === "esp32" ? "真实设备采集" : `采集来源：${text}`;
  return `<span class="source-badge src-${key}" title="${title}">${text}</span>`;
}

function timelineEvidenceBoxes(detections) {
  return (detections || [])
    .map((detection) => {
      const box = detection.bbox_norm;
      if (!Array.isArray(box) || box.length < 4) return "";
      const x1 = Math.max(0, Math.min(1, Number(box[0]) || 0));
      const y1 = Math.max(0, Math.min(1, Number(box[1]) || 0));
      const x2 = Math.max(0, Math.min(1, Number(box[2]) || 0));
      const y2 = Math.max(0, Math.min(1, Number(box[3]) || 0));
      const width = Math.max(0.01, x2 - x1);
      const height = Math.max(0.01, y2 - y1);
      const ambiguous = detection.link_status === "ambiguous" ? " is-ambiguous" : "";
      const label = `${detection.class_zh || "物品"} ${Math.round((Number(detection.confidence) || 0) * 100)}%`;
      return `<span class="timeline-evidence-box${ambiguous}" style="left:${(x1 * 100).toFixed(2)}%;top:${(y1 * 100).toFixed(2)}%;width:${(width * 100).toFixed(2)}%;height:${(height * 100).toFixed(2)}%" title="${escapeHtml(label)}"></span>`;
    })
    .join("");
}

function timelineDetectionList(detections) {
  if (!detections?.length) {
    return '<p class="timeline-detail-empty">这一帧没有识别到词表内物品</p>';
  }
  return `<ul class="timeline-detections">${detections
    .map((detection) => {
      const label = escapeHtml(detection.class_zh || "物品");
      const meta = [
        detection.region || "未分区",
        linkStatusLabel(detection.link_status),
        detection.link_score != null ? `关联分 ${Number(detection.link_score).toFixed(2)}` : "",
      ]
        .filter(Boolean)
        .join(" · ");
      const thumb = detection.crop_url
        ? `<img class="timeline-detection-thumb" src="${escapeHtml(detection.crop_url)}" alt="" loading="lazy" decoding="async" data-fallback-class="timeline-detection-thumb is-empty" data-fallback-text="无图" />`
        : '<span class="timeline-detection-thumb is-empty" aria-hidden="true"></span>';
      return `<li class="timeline-detection">
        ${thumb}
        <span class="timeline-detection-copy">
          <strong>${label}</strong>
          <span>${escapeHtml(meta)}</span>
        </span>
        <span class="timeline-detection-score">${Math.round((Number(detection.confidence) || 0) * 100)}%</span>
      </li>`;
    })
    .join("")}</ul>`;
}

function buildTimelineDetail(capture, detail) {
  const detections = detail?.detections || [];
  const media = detail?.capture || {};
  const width = Number(media.width || capture.width || 0);
  const height = Number(media.height || capture.height || 0);
  const imageUrl = capture.image_url || media.image_url || capture.thumbnail_url || "";
  const count = capture.detections_count ?? detections.length;
  const boxes = imageUrl ? timelineEvidenceBoxes(detections) : "";
  const note = `抓拍 #${capture.id} · ${width && height ? `${width} × ${height}` : "本地图像"}`;
  const image = imageUrl
    ? `<img class="timeline-evidence-img" data-src="${escapeHtml(imageUrl)}" alt="抓拍 #${capture.id} 的完整画面" loading="lazy" decoding="async" data-fallback-class="timeline-evidence-empty" data-fallback-text="图像不可用" />`
    : '<span class="timeline-evidence-empty">图像不可用</span>';
  return `<div class="timeline-detail-inner">
    <div class="timeline-evidence">
      <div class="timeline-evidence-frame">
        ${image}
        <div class="timeline-evidence-boxes" aria-hidden="true">${boxes}</div>
      </div>
      <div class="timeline-evidence-caption">
        <span>抓拍证据</span>
        <span>${width && height ? `${width} × ${height}` : "本地图像"}</span>
      </div>
    </div>
    <div class="timeline-detail-body">
      <div class="timeline-detail-head">
        <strong>识别证据</strong>
        <span>${count} 个物品</span>
      </div>
      ${timelineDetectionList(detections)}
      <div class="timeline-detail-actions">
        <span class="timeline-detail-note">${escapeHtml(note)}</span>
        <a class="timeline-detail-link" href="/observe?capture=${encodeURIComponent(capture.id)}">打开完整观察 →</a>
      </div>
    </div>
  </div>`;
}

function buildTimelineEvent(capture, detail, isLatest, delay, enter) {
  const detections = detail?.detections || [];
  const labels = [...new Set(detections.map((detection) => detection.class_zh).filter(Boolean))];
  const zones = [...new Set(detections.map((detection) => detection.region).filter(Boolean))];
  const count = capture.detections_count ?? detections.length;
  const clock = timelineClock(capture);
  const objects = labels.length
    ? `${labels
        .slice(0, 3)
        .map((label) => `<span class="timeline-object">${escapeHtml(label)}</span>`)
        .join("")}${
        labels.length > 3 ? `<span class="timeline-object is-more">+${labels.length - 3}</span>` : ""
      }`
    : '<span class="timeline-object is-empty">无识别结果</span>';
  const summary = labels.length
    ? `${zones.length ? `${zones.slice(0, 2).join(" / ")} · ` : ""}${count} 个识别结果`
    : "这一帧没有识别到词表内物品";
  const thumb = capture.thumbnail_url
    ? `<img class="timeline-thumb" src="${escapeHtml(capture.thumbnail_url)}" alt="抓拍 #${capture.id} 缩略图" loading="lazy" decoding="async" data-fallback-class="timeline-thumb-empty" data-fallback-text="无图" />`
    : '<span class="timeline-thumb-empty">无图</span>';
  const event = document.createElement("li");
  event.className = `timeline-event${isLatest ? " is-latest" : ""}${enter ? " is-entering" : ""}`;
  if (enter) event.style.setProperty("--enter-delay", `${delay}ms`);
  event.innerHTML = `
    <span class="timeline-node" aria-hidden="true"></span>
    <div class="timeline-entry">
      <button class="timeline-event-card" type="button" aria-expanded="false" aria-controls="timeline-detail-${capture.id}">
        <span class="timeline-thumb-wrap">
          ${thumb}
          ${isLatest ? '<span class="timeline-latest-mark">最新</span>' : ""}
        </span>
        <span class="timeline-event-body">
          <span class="timeline-event-top">
            <time class="timeline-clock${clock.unsynced ? " is-unsynced" : ""}"${
              clock.iso ? ` datetime="${escapeHtml(clock.iso)}"` : ""
            }>${escapeHtml(clock.text)}</time>
            ${timelineSourceBadge(capture.source_kind)}
            <span class="timeline-capture-id">#${capture.id}</span>
          </span>
          <span class="timeline-objects">${objects}</span>
          <span class="timeline-event-summary">${escapeHtml(summary)}</span>
        </span>
        <span class="timeline-chevron" aria-hidden="true">⌄</span>
      </button>
      <div class="timeline-detail" id="timeline-detail-${capture.id}" role="region" aria-label="抓拍 #${capture.id} 识别证据" hidden>
        ${buildTimelineDetail(capture, detail)}
      </div>
    </div>`;
  event.querySelector(".timeline-event-card")?.addEventListener("click", (clickEvent) => {
    toggleTimelineEvent(clickEvent.currentTarget);
  });
  return event;
}

function closeTimelineEvent(event) {
  const button = event?.querySelector(".timeline-event-card");
  const detail = event?.querySelector(".timeline-detail");
  if (!button || !detail) return;
  button.setAttribute("aria-expanded", "false");
  event.classList.remove("is-open");
  detail.hidden = true;
}

function toggleTimelineEvent(button) {
  const event = button?.closest(".timeline-event");
  const detail = event?.querySelector(".timeline-detail");
  if (!event || !detail) return;
  const opening = button.getAttribute("aria-expanded") !== "true";
  if (opening) {
    document.querySelectorAll("#timeline .timeline-event.is-open").forEach((other) => {
      if (other !== event) closeTimelineEvent(other);
    });
  }
  button.setAttribute("aria-expanded", String(opening));
  event.classList.toggle("is-open", opening);
  detail.hidden = !opening;
  if (opening) {
    detail.querySelectorAll("img[data-src]").forEach((image) => {
      if (!image.getAttribute("src")) image.setAttribute("src", image.dataset.src);
    });
  }
}

function renderTimeline(captures, details) {
  const box = $("timeline");
  if (!box) return;
  const detailById = new Map();
  captures.forEach((capture, index) => detailById.set(capture.id, details[index] || null));
  const ordered = [...captures].sort((a, b) => captureTimestamp(b) - captureTimestamp(a));
  const groups = new Map();
  ordered.forEach((capture) => {
    const key = timelineDayKey(capture);
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(capture);
  });
  const enter = !state.timelineEntered;
  const fragment = document.createDocumentFragment();
  let order = 0;
  groups.forEach((items, key) => {
    const meta = timelineDayMeta(key);
    const section = document.createElement("section");
    section.className = "timeline-day";
    const head = document.createElement("h2");
    head.className = `timeline-day-head${enter ? " is-entering" : ""}`;
    if (enter) head.style.setProperty("--enter-delay", `${100 + order * 55}ms`);
    head.innerHTML = `<span class="timeline-day-main">${escapeHtml(meta.main)}</span>
      <span class="timeline-day-sub">${escapeHtml(meta.sub)}</span>
      <span class="timeline-day-count">${items.length} 次观察</span>`;
    const list = document.createElement("ol");
    list.className = "timeline-events";
    items.forEach((capture) => {
      const isLatest = order === 0;
      list.appendChild(buildTimelineEvent(capture, detailById.get(capture.id), isLatest, 140 + order * 55, enter));
      order += 1;
    });
    section.append(head, list);
    fragment.appendChild(section);
  });
  box.replaceChildren(fragment);
  box.querySelectorAll(".timeline-day-head.is-entering, .timeline-event.is-entering").forEach((element) => {
    element.addEventListener("animationend", () => element.classList.remove("is-entering"), {
      once: true,
    });
  });
  state.timelineEntered = true;
  const end = $("timeline-end");
  if (end) end.hidden = false;
}

function renderTimelineEmpty(message, detail) {
  const box = $("timeline");
  if (!box) return;
  const end = $("timeline-end");
  if (end) end.hidden = true;
  box.innerHTML = `<div class="timeline-empty">
    <span class="timeline-empty-mark" aria-hidden="true"></span>
    <div><p>${escapeHtml(message)}</p><span>${escapeHtml(detail)}</span></div>
  </div>`;
}

async function loadTimeline() {
  const data = await api("/api/captures?limit=12");
  const box = $("timeline");
  if (!box) return;
  if (!data.ok) {
    state.timelineSignature = null;
    renderTimelineEmpty("读取历史抓拍失败", "请确认本地服务正常后稍后重试");
    return;
  }
  const captures = data.captures || [];
  setText("timeline-count", `${captures.length} 帧`);
  if (!captures.length) {
    state.timelineSignature = "";
    renderTimelineEmpty("还没有抓拍记录", "先去最近观察抓拍一张");
    return;
  }

  const signature = captures
    .map((capture) => `${capture.id}:${capture.detections_count ?? 0}:${capture.thumbnail_url || ""}`)
    .join("|");
  if (signature === state.timelineSignature) return;

  const details = await Promise.all(
    captures.map(async (capture) => {
      try {
        const detail = await api(`/api/captures/${capture.id}`);
        return detail.ok ? detail : null;
      } catch (error) {
        return null;
      }
    })
  );
  state.timelineSignature = signature;
  renderTimeline(captures, details);
  const end = $("timeline-end");
  if (end) end.textContent = captures.length < 12 ? "已加载全部记录" : "显示最近 12 条观察";
}

// ---------------- 页面初始化 ----------------
function initObserve() {
  const captureBtn = $("capture-btn");
  if (captureBtn) captureBtn.onclick = doCapture;
  const autoBtn = $("auto-btn");
  if (autoBtn) autoBtn.onclick = toggleAuto;
  const detailBtn = $("observe-detail-btn");
  if (detailBtn) {
    detailBtn.addEventListener("click", () => {
      const summarize = $("summary-trigger");
      openSummary(true);
      summarize?.focus({ preventScroll: true });
    });
  }
  bindSummaryOverlay();
}

function initSearch() {
  const form = $("query-form");
  if (form) {
    form.onsubmit = (e) => {
      e.preventDefault();
      runQuery();
    };
  }
  $("filter-categories")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter-category]");
    if (!button) return;
    state.searchCategory = button.dataset.filterCategory || "all";
    renderSearchItems();
  });
  $("filter-ranges")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-filter-range]");
    if (!button || button.disabled) return;
    state.searchRange = button.dataset.filterRange || "all";
    renderSearchItems();
  });
}

function restartSearchEntrance() {
  document.querySelectorAll(".search-page .search-reveal, .search-page .wm-enter").forEach((el) => {
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "";
  });
}

function restartWarmEntrance() {
  document.querySelectorAll(".app-main .wm-enter").forEach((el) => {
    el.style.animation = "none";
    void el.offsetWidth;
    el.style.animation = "";
  });
}

function restartTimelineEntrance() {
  const nodes = document.querySelectorAll("#timeline .timeline-day-head, #timeline .timeline-event");
  nodes.forEach((el) => {
    el.style.animation = "none";
  });
  void document.body.offsetWidth;
  nodes.forEach((el) => {
    el.style.animation = "";
  });
}

window.addEventListener("pageshow", (event) => {
  if (!event.persisted) return;
  if (PAGE === "search") {
    restartSearchEntrance();
    return;
  }
  restartWarmEntrance();
  if (PAGE === "timeline") restartTimelineEntrance();
  if (PAGE === "items") animateGridRows();
});

async function loadPageData() {
  if (PAGE === "home") {
    await loadHome();
    return;
  }
  if (PAGE === "observe") {
    const params = new URLSearchParams(location.search);
    const requested = Number.parseInt(params.get("capture") || "", 10);
    if (Number.isFinite(requested) && requested > 0) {
      const ok = await showCapture(requested);
      if (!ok) await loadLatestCapture();
    } else {
      await loadLatestCapture();
    }
    await loadObserveRecent();
    return;
  }
  if (PAGE === "search") {
    await loadSearchBase();
    const params = new URLSearchParams(location.search);
    const q = params.get("q");
    const input = $("query-input");
    if (q && input) input.value = q;
    if (q && params.get("autorun") === "1") {
      await runQuery(q);
      history.replaceState(null, "", `/search?q=${encodeURIComponent(q)}`);
    }
    return;
  }
  if (PAGE === "items") {
    await loadObjects();
    return;
  }
  if (PAGE === "timeline") {
    await loadTimeline();
  }
}

async function initPage() {
  document.addEventListener(
    "error",
    (event) => {
      if (!(event.target instanceof HTMLImageElement)) return;
      const image = event.target;
      const fallbackClass = image.dataset.fallbackClass;
      if (fallbackClass) {
        const fallback = document.createElement("span");
        fallback.className = fallbackClass;
        fallback.textContent = image.dataset.fallbackText || "无图";
        image.replaceWith(fallback);
      } else {
        image.classList.add("is-broken");
      }
    },
    true
  );
  initNav();
  if (PAGE === "observe") initObserve();
  if (PAGE === "search") initSearch();
  if (PAGE === "items") initItems();
  await loadStatus();
  await loadPageData();

  setInterval(async () => {
    await loadStatus();
    if (PAGE === "items") await loadObjects();
    if (!state.autoRunning) return;
    if (PAGE === "observe") {
      await loadLatestCapture();
      await loadObserveRecent();
    }
    if (PAGE === "timeline") await loadTimeline();
  }, 6000);
}

document.addEventListener("DOMContentLoaded", initPage);
