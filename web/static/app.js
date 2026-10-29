const PAGE = document.body.dataset.page || "observe";

const DEFAULT_EXAMPLES = [
  "我的钥匙最后出现在哪里？",
  "红色杯子在哪？",
  "手机是什么时候最后一次看到的？",
  "桌上都有哪些东西？",
];

const state = {
  status: null,
  currentCapture: null,
  autoRunning: false,
  warmupDone: false,
  busy: false,
  highlightedDetectionId: null,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function setText(id, text) {
  const el = $(id);
  if (el) el.textContent = text;
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
  el.textContent = message;
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

function linkStatusLabel(status) {
  return {
    ambiguous: "关联待确认",
    new: "新轨迹",
    matched: "已关联",
  }[status] || "已关联";
}

function captureTime(cap) {
  if (!cap) return "—";
  if (!cap.time_synced) {
    return cap.captured_at_local ? `时间未同步（${cap.captured_at_local}）` : "时间未同步";
  }
  return cap.captured_at_local || cap.captured_at_utc || "时间未知";
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

    const stats = data.pipeline?.stats || {};
    setPill("pill-db", `数据库 · ${stats.captures ?? 0} 帧 / ${stats.active_tracks ?? 0} 物品`, "ok");

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

    const examples = data.examples?.length ? data.examples : DEFAULT_EXAMPLES;
    renderExampleChips(examples);
    const input = $("query-input");
    if (input && examples[0]) input.placeholder = `例如：${examples[0]}`;
  } catch (err) {
    setPill("pill-db", "服务不可用", "bad");
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
    list.innerHTML = '<p class="empty-note">这一帧没有识别到词表内物品。</p>';
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
  const recognized = labels.length
    ? `识别到 ${labels.length} 类物品：${labels.slice(0, 6).join("、")}${labels.length > 6 ? " 等" : ""}。`
    : "这一帧没有识别到词表内物品。";
  const source = `来源：${sourceLabel(cap.source_kind)}。`;
  const time = cap.time_synced
    ? `时间：${cap.captured_at_local || cap.captured_at_utc || "未知"}。`
    : "时间未同步，当前时间不可信。";
  return recognized + source + time;
}

function showEmptyCapture() {
  state.currentCapture = null;
  const placeholder = $("viewport-placeholder");
  if (placeholder) placeholder.classList.remove("hidden");
  const img = $("capture-img");
  if (img) {
    img.hidden = true;
    img.removeAttribute("src");
  }
  clearOverlay();
  setText("capture-time", "—");
  setText("capture-meta", "尚无抓拍");
  setText("capture-summary", "还没有抓拍记录。点击“立即抓拍”，或运行演示数据脚本后再回来。");
  const source = $("capture-source");
  if (source) {
    source.className = "source-badge src-unknown";
    source.textContent = "未知来源";
  }
  const list = $("detections-list");
  if (list) list.innerHTML = '<p class="empty-note">还没有检测结果。</p>';
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
  const img = $("capture-img");
  if (img) {
    const base = cap.image_url || `/api/captures/${cap.id}/image`;
    img.src = `${base}${base.includes("?") ? "&" : "?"}t=${Date.now()}`;
    img.hidden = false;
  }

  setText("capture-time", captureTime(cap));
  setText(
    "capture-meta",
    `抓拍 #${cap.id} · ${cap.width || "?"}×${cap.height || "?"} · ${detections.length} 个检测 · ` +
      `${sourceLabel(cap.source_kind)} · ${cap.time_synced ? "时间已同步" : "时间未同步"}`
  );
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
  setText("capture-status", "正在抓拍并运行检测（CPU 上约需数秒）…");
  try {
    const data = await api("/api/capture", { method: "POST" });
    if (!data.ok) {
      const msg = data.error || "未知错误";
      setText("capture-status", `抓拍失败：${msg}`);
      toast(`抓拍失败：${msg}`);
      return;
    }
    setText(
      "capture-status",
      `本次识别到 ${(data.detections || []).length} 个物品` +
        (data.warnings?.length ? ` · ${data.warnings.join("；")}` : "")
    );
    await Promise.all([showCapture(data.capture_id), loadStatus()]);
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
function renderExampleChips(examples) {
  const box = $("example-chips");
  if (!box || box.dataset.ready === "1") return;
  box.dataset.ready = "1";
  box.innerHTML = "";
  (examples || []).slice(0, 4).forEach((q) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = q;
    chip.onclick = () => {
      const input = $("query-input");
      const form = $("query-form");
      if (input) input.value = q;
      if (form) form.requestSubmit();
    };
    box.appendChild(chip);
  });
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
  if (results) results.innerHTML = "";
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
  }
}

function renderAnswer(data) {
  const answer = $("answer");
  if (!answer) return;
  answer.classList.remove("hidden", "notfound", "help");
  if (data.status === "not_found" || data.status === "empty") answer.classList.add("notfound");
  if (data.status === "help") answer.classList.add("help");
  answer.textContent = data.answer || "（没有回答）";
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
      p.textContent = "⚠ " + n;
      nb.appendChild(p);
    });
    answer.after(nb);
  }

  const results = $("results");
  if (!results) return;
  results.innerHTML = "";
  (data.results || []).forEach((r) => {
    if (r.events) {
      renderEventResult(r);
      return;
    }
    if (r.items) {
      r.items.forEach((item) => {
        results.appendChild(
          buildResultCard({
            label: item.class_zh,
            class_zh: item.class_zh,
            zone: item.zone,
            time_local: null,
            time_synced: r.time_synced,
            confidence: item.confidence,
            crop_url: item.crop_url,
            capture_id: r.capture_id,
            detection_id: item.detection_id,
            source_kind: item.source_kind || r.source_kind,
            link_status: "matched",
            sightings: null,
          })
        );
      });
      return;
    }
    results.appendChild(buildResultCard(r));
  });
}

function resultThumb(url, alt) {
  if (!url) return '<span class="thumb-empty">无图</span>';
  return `<img alt="${escapeHtml(alt)}" src="${escapeHtml(url)}" />`;
}

function buildResultCard(r) {
  const card = document.createElement(r.capture_id ? "a" : "div");
  card.className = "result";
  if (r.capture_id) card.href = `/observe?capture=${encodeURIComponent(r.capture_id)}`;

  const label = r.label || r.class_zh || "物品";
  const statusBadge =
    r.link_status === "ambiguous"
      ? '<span class="badge warn">关联待确认</span>'
      : r.link_status === "new"
        ? '<span class="badge warn">新轨迹</span>'
        : '<span class="badge">已关联</span>';
  const synced =
    r.time_synced === false
      ? '<span class="badge warn">时间未同步</span>'
      : `<span class="badge dim">${escapeHtml(r.time_local || "时间未知")}</span>`;

  card.innerHTML = `
    <div class="thumb">${resultThumb(r.crop_url || r.evidence_crop_url, label)}</div>
    <div class="meta">
      <strong>${escapeHtml(label)}</strong>
      <div class="row">${statusBadge}${sourceBadge(r.source_kind)}${synced}</div>
      <div class="row">
        <span class="badge dim">置信度 ${Math.round((r.confidence || 0) * 100)}%</span>
        <span class="badge dim">区域 ${escapeHtml(r.zone || "未分区")}</span>
      </div>
      ${r.time_ago ? `<div>${escapeHtml(r.time_ago)}</div>` : ""}
      ${r.sightings != null ? `<div>共记录 ${r.sightings} 次</div>` : ""}
      ${r.link_score != null ? `<div>外观关联相似度 ${Number(r.link_score).toFixed(2)}</div>` : ""}
      ${r.uncertainty ? `<div class="note">⚠ ${escapeHtml(r.uncertainty)}</div>` : ""}
    </div>`;
  return card;
}

function renderEventResult(r) {
  const results = $("results");
  if (!results) return;
  (r.events || []).forEach((e) => {
    const card = document.createElement(e.capture_id ? "a" : "div");
    card.className = "result";
    if (e.capture_id) card.href = `/observe?capture=${encodeURIComponent(e.capture_id)}`;
    card.innerHTML = `
      <div class="thumb">${resultThumb(e.evidence_crop_url, "证据")}</div>
      <div class="meta">
        <strong>${escapeHtml(r.label || r.class_zh || "物品")} · ${escapeHtml(e.zone || "未分区")}</strong>
        <div class="row">
          ${sourceBadge(e.source_kind || r.source_kind)}
          <span class="badge dim">${escapeHtml(e.time_synced ? e.time_local : "时间未同步")}</span>
          <span class="badge dim">置信度 ${Math.round((e.confidence || 0) * 100)}%</span>
        </div>
      </div>`;
    results.appendChild(card);
  });
}

// ---------------- 我的物品 ----------------
async function loadObjects() {
  const data = await api("/api/objects");
  const box = $("objects");
  if (!box) return;
  if (!data.ok) {
    box.innerHTML = '<p class="empty-note">读取物品库失败，请确认本地服务正常。</p>';
    return;
  }
  const objects = data.objects || [];
  setText("objects-count", `${objects.length} 件`);
  box.innerHTML = "";
  if (!objects.length) {
    box.innerHTML = '<p class="empty-note">还没有记录到物品。先到“最近观察”抓拍一张。</p>';
    return;
  }
  objects.forEach((o) => {
    const label = o.label || o.class_zh || "物品";
    const when = o.time_synced === false ? "时间未同步" : o.time_ago || o.time_local || "—";
    const card = document.createElement("a");
    card.className = "object-card";
    card.href = `/search?q=${encodeURIComponent(`${label}在哪？`)}&autorun=1`;
    card.innerHTML = `
      <div class="pic ${o.evidence_crop_url ? "" : "no-image"}">${
        o.evidence_crop_url
          ? `<img alt="${escapeHtml(label)}" src="${escapeHtml(o.evidence_crop_url)}" />`
          : "暂无图片"
      }</div>
      <div class="info">
        <div class="name-row">
          <div class="name">${escapeHtml(label)}</div>
          ${sourceBadge(o.source_kind)}
        </div>
        <div class="sub">${escapeHtml(o.zone || "未分区")}</div>
        <div class="sub">最后出现：${escapeHtml(when)}</div>
        <div class="sub">${o.sightings ?? 0} 次观测</div>
      </div>`;
    box.appendChild(card);
  });
}

// ---------------- 观察时间线 ----------------
async function loadTimeline() {
  const data = await api("/api/captures?limit=12");
  const box = $("timeline");
  if (!box) return;
  if (!data.ok) {
    box.innerHTML = '<p class="empty-note">读取历史抓拍失败，请确认本地服务正常。</p>';
    return;
  }
  const caps = data.captures || [];
  setText("timeline-count", `${caps.length} 帧`);
  if (!caps.length) {
    box.innerHTML = '<p class="empty-note">还没有抓拍帧。先到“最近观察”抓拍一张。</p>';
    return;
  }

  const details = await Promise.all(
    caps.map(async (c) => {
      try {
        const d = await api(`/api/captures/${c.id}`);
        return d.ok ? d : null;
      } catch (e) {
        return null;
      }
    })
  );

  box.innerHTML = "";
  caps.forEach((c, i) => {
    const detail = details[i];
    const detections = detail?.detections || [];
    const labels = [...new Set(detections.map((d) => d.class_zh).filter(Boolean))];
    const when = c.time_synced ? c.captured_at_local || c.captured_at_utc : "时间未同步";
    const summary = labels.length
      ? `识别：${labels.slice(0, 4).join("、")}${labels.length > 4 ? " 等" : ""}`
      : "这一帧没有识别到词表内物品";
    const card = document.createElement("a");
    card.className = "timeline-card";
    card.href = `/observe?capture=${encodeURIComponent(c.id)}`;
    card.innerHTML = `
      <img class="timeline-thumb" alt="抓拍 #${c.id}" src="${escapeHtml(c.thumbnail_url || "")}" />
      <div class="timeline-main">
        <div class="timeline-when">
          ${escapeHtml(when || "时间未知")}
          ${sourceBadge(c.source_kind)}
          ${c.time_synced === false ? '<span class="badge warn">时间未同步</span>' : ""}
        </div>
        <div class="timeline-summary">${escapeHtml(summary)}</div>
        <div class="timeline-badges">
          <span>抓拍 #${c.id}</span>
          <span>${c.detections_count ?? detections.length} 个物品</span>
          <span>查看观察详情 →</span>
        </div>
      </div>`;
    box.appendChild(card);
  });
}

// ---------------- 页面初始化 ----------------
function initObserve() {
  const captureBtn = $("capture-btn");
  if (captureBtn) captureBtn.onclick = doCapture;
  const autoBtn = $("auto-btn");
  if (autoBtn) autoBtn.onclick = toggleAuto;
}

function initSearch() {
  const form = $("query-form");
  if (form) {
    form.onsubmit = (e) => {
      e.preventDefault();
      runQuery();
    };
  }
}

async function loadPageData() {
  if (PAGE === "observe") {
    const params = new URLSearchParams(location.search);
    const requested = Number.parseInt(params.get("capture") || "", 10);
    if (Number.isFinite(requested) && requested > 0) {
      const ok = await showCapture(requested);
      if (!ok) await loadLatestCapture();
    } else {
      await loadLatestCapture();
    }
    return;
  }
  if (PAGE === "search") {
    const box = $("example-chips");
    if (box && !box.children.length) renderExampleChips(DEFAULT_EXAMPLES);
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
  initNav();
  if (PAGE === "observe") initObserve();
  if (PAGE === "search") initSearch();
  await loadStatus();
  await loadPageData();

  setInterval(async () => {
    await loadStatus();
    if (!state.autoRunning) return;
    if (PAGE === "observe") await loadLatestCapture();
    if (PAGE === "items") await loadObjects();
    if (PAGE === "timeline") await loadTimeline();
  }, 6000);
}

document.addEventListener("DOMContentLoaded", initPage);
