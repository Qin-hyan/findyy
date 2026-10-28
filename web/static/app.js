const state = {
  status: null,
  currentCapture: null,
  autoRunning: false,
  warmupDone: false,
  busy: false,
};

const $ = (id) => document.getElementById(id);

function escapeHtml(text) {
  return String(text ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function toast(message, ok = false) {
  const el = $("toast");
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

function setPill(id, text, cls) {
  const el = $(id);
  el.textContent = text;
  el.className = "pill " + (cls || "");
}

// ---------------- 状态 ----------------
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
      setPill("pill-model", `模型 · OWLv2 + DINOv2 就绪`, "ok");
    } else if (data.warmup_done) {
      setPill("pill-model", `模型 · 加载失败`, "bad");
    } else {
      setPill("pill-model", `模型 · 加载中…`, "warn");
    }

    const src = data.source || {};
    if (src.type === "esp32") setPill("pill-source", `采集源 · ESP32 ${src.esp32_url || ""}`, "");
    else if (src.type === "replay") setPill("pill-source", `采集源 · 图片回放（剩 ${src.replay_remaining ?? "?"} 张）`, "");
    else setPill("pill-source", `采集源 · ${src.type}`, "");

    setPill("pill-auto", `自动采集 · ${state.autoRunning ? "运行中" : "停止"}`, state.autoRunning ? "ok" : "");

    const btn = $("capture-btn");
    if (!state.warmupDone) {
      btn.disabled = true;
      btn.textContent = "模型加载中…";
    } else if (!state.busy) {
      btn.disabled = false;
      btn.textContent = "立即抓拍";
    }
    $("auto-btn").textContent = state.autoRunning ? "停止自动采集" : "开始自动采集";

    if (data.pipeline?.model_errors?.length) {
      $("capture-status").textContent = "模型错误：" + data.pipeline.model_errors.join(" | ");
    }

    const examples = data.examples || [];
    renderExampleChips(examples);
    $("query-input").placeholder = examples[0] ? `例如：${examples[0]}` : "例如：我的钥匙最后出现在哪里？";
  } catch (err) {
    setPill("pill-db", "服务不可用", "bad");
  }
}

function renderExampleChips(examples) {
  const box = $("example-chips");
  if (box.dataset.ready === "1") return;
  box.dataset.ready = "1";
  box.innerHTML = "";
  examples.slice(0, 4).forEach((q) => {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = q;
    chip.onclick = () => {
      $("query-input").value = q;
      $("query-form").requestSubmit();
    };
    box.appendChild(chip);
  });
}

// ---------------- 最近抓拍 ----------------
async function loadLatestCapture() {
  const data = await api("/api/captures?limit=1");
  if (!data.ok || !data.captures?.length) {
    $("capture-time").textContent = "—";
    return;
  }
  const cap = data.captures[0];
  await showCapture(cap.id);
}

async function showCapture(captureId, highlight = null) {
  const detail = await api(`/api/captures/${captureId}`);
  if (!detail.ok) return;
  state.currentCapture = detail;
  const cap = detail.capture;
  $("viewport-placeholder").classList.add("hidden");
  const img = $("capture-img");
  img.src = `/api/captures/${captureId}/image?t=${Date.now()}`;
  img.hidden = false;

  const when = cap.time_synced
    ? cap.captured_at_local || cap.captured_at_utc || "时间未知"
    : `时间未同步（采集于 ${cap.captured_at_local || "未知"}）`;
  $("capture-time").textContent = when;
  $("capture-meta").textContent =
    `抓拍 #${cap.id} · ${cap.width}×${cap.height} · ${detail.detections.length} 个检测` +
    (cap.time_synced ? "" : " · 该帧时间不可信");

  drawDetections(detail.detections, highlight);

  const list = $("detections-list");
  list.innerHTML = "";
  const names = new Set(detail.detections.map((d) => d.class_zh));
  if (names.size === 0) {
    const chip = document.createElement("span");
    chip.className = "chip plain";
    chip.textContent = "这一帧没有识别到词表内物品";
    list.appendChild(chip);
  }
  detail.detections.slice(0, 12).forEach((d) => {
    const chip = document.createElement("span");
    chip.className = "chip" + (d.link_status === "ambiguous" ? " warn" : "");
    chip.textContent = `${d.class_zh} ${(d.confidence * 100).toFixed(0)}% · ${d.region || "未分区"}`;
    chip.title = `关联相似度 ${(d.link_score ?? 0).toFixed(2)} · ${d.link_status || ""}`;
    chip.onclick = () => {
      drawDetections(detail.detections, d.detection_id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    };
    list.appendChild(chip);
  });
}

function drawDetections(detections, highlightId = null) {
  const overlay = $("overlay");
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

// ---------------- 抓拍 / 自动采集 ----------------
async function doCapture() {
  if (state.busy) return;
  state.busy = true;
  const btn = $("capture-btn");
  btn.disabled = true;
  btn.textContent = "抓拍与识别中…";
  $("capture-status").textContent = "正在抓拍并运行检测（CPU 上约需数秒）…";
  try {
    const data = await api("/api/capture", { method: "POST" });
    if (!data.ok) {
      $("capture-status").textContent = `抓拍失败：${data.error || "未知错误"}`;
      toast(`抓拍失败：${data.error || "未知错误"}`);
      return;
    }
    $("capture-status").textContent = `本次识别到 ${data.detections.length} 个物品` +
      (data.warnings?.length ? ` · ${data.warnings.join("；")}` : "");
    await Promise.all([loadLatestCapture(), loadObjects(), loadTimeline(), loadStatus()]);
    toast("抓拍完成，已写入本地记忆", true);
  } catch (err) {
    toast(`抓拍失败：${err}`);
  } finally {
    state.busy = false;
    btn.disabled = false;
    btn.textContent = "立即抓拍";
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

// ---------------- 查询 ----------------
async function runQuery(text) {
  const q = ((text ?? $("query-input").value) || "").trim();
  if (!q) return;
  $("query-input").value = q;
  $("answer").classList.remove("hidden", "notfound", "help");
  $("answer").textContent = "正在检索本地记忆…";
  $("results").innerHTML = "";
  try {
    const data = await api("/api/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: q }),
    });
    if (!data.ok) throw new Error(data.error || "查询失败");
    renderAnswer(data);
  } catch (err) {
    $("answer").textContent = `查询失败：${err}`;
  }
}

function renderAnswer(data) {
  const answer = $("answer");
  answer.classList.remove("hidden", "notfound", "help");
  if (data.status === "not_found" || data.status === "empty") answer.classList.add("notfound");
  if (data.status === "help") answer.classList.add("help");
  answer.textContent = data.answer || "（没有回答）";
  $("query-intent").textContent = data.intent_zh ? `意图：${data.intent_zh}` : "";

  const notesBox = document.getElementById("answer-notes");
  if (notesBox) notesBox.remove();
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
  results.innerHTML = "";
  (data.results || []).forEach((r) => {
    if (r.events) {
      renderEventResult(r);
      return;
    }
    if (r.items) {
      r.items.forEach((item) => {
        results.appendChild(buildResultCard({
          label: item.class_zh,
          class_zh: item.class_zh,
          zone: item.zone,
          time_local: null,
          confidence: item.confidence,
          crop_url: item.crop_url,
          capture_id: r.capture_id,
          bbox_norm: item.bbox_norm,
          link_status: "matched",
          sightings: null,
        }));
      });
      return;
    }
    results.appendChild(buildResultCard(r));
  });

  (data.suggestions || []).slice(0, 4).forEach((s) => {});
}

function buildResultCard(r) {
  const card = document.createElement("div");
  card.className = "result";
  const statusBadge = r.link_status === "ambiguous"
    ? '<span class="badge warn">关联待确认</span>'
    : '<span class="badge">已关联</span>';
  const synced = r.time_synced === false
    ? '<span class="badge warn">时间未同步</span>'
    : `<span class="badge dim">${escapeHtml(r.time_local || "时间未知")}</span>`;
  card.innerHTML = `
    <div class="thumb"><img alt="${escapeHtml(r.label || r.class_zh)}" src="${r.crop_url || ""}" /></div>
    <div class="meta">
      <strong>${escapeHtml(r.label || r.class_zh || "物品")}</strong>
      <div class="row">${statusBadge}${synced}
        <span class="badge dim">置信度 ${((r.confidence || 0) * 100).toFixed(0)}%</span>
        <span class="badge dim">区域 ${escapeHtml(r.zone || "未分区")}</span>
      </div>
      ${r.time_ago ? `<div>${escapeHtml(r.time_ago)}</div>` : ""}
      ${r.sightings ? `<div>共记录 ${r.sightings} 次</div>` : ""}
      ${r.link_score ? `<div>外观关联相似度 ${r.link_score.toFixed(2)}</div>` : ""}
      ${r.uncertainty ? `<div class="note">⚠ ${escapeHtml(r.uncertainty)}</div>` : ""}
    </div>`;
  if (r.capture_id) {
    card.style.cursor = "pointer";
    card.onclick = () => {
      showCapture(r.capture_id, r.detection_id);
      window.scrollTo({ top: 0, behavior: "smooth" });
    };
  }
  return card;
}

function renderEventResult(r) {
  const box = $("results");
  (r.events || []).forEach((e) => {
    const card = document.createElement("div");
    card.className = "result";
    card.innerHTML = `
      <div class="thumb"><img alt="证据" src="${e.evidence_crop_url}" /></div>
      <div class="meta">
        <strong>${escapeHtml(r.label || r.class_zh || "物品")} · ${escapeHtml(e.zone)}</strong>
        <div class="row">
          <span class="badge dim">${escapeHtml(e.time_synced ? e.time_local : "时间未同步")}</span>
          <span class="badge dim">置信度 ${((e.confidence || 0) * 100).toFixed(0)}%</span>
        </div>
      </div>`;
    card.onclick = () => {
      showCapture(e.capture_id, null);
      window.scrollTo({ top: 0, behavior: "smooth" });
    };
    box.appendChild(card);
  });
}

// ---------------- 物品库 ----------------
async function loadObjects() {
  const data = await api("/api/objects");
  if (!data.ok) return;
  const box = $("objects");
  box.innerHTML = "";
  const objects = data.objects || [];
  $("objects-count").textContent = `${objects.length} 件`;
  if (!objects.length) {
    box.innerHTML = '<p class="muted small">还没有记录到物品。先抓拍一张。</p>';
    return;
  }
  objects.forEach((o) => {
    const card = document.createElement("div");
    card.className = "object-card";
    const time = o.time_synced === false ? "时间未同步" : (o.time_ago || o.time_local || "—");
    card.innerHTML = `
      <div class="pic"><img alt="" src="${o.evidence_crop_url || ""}" /></div>
      <div class="info">
        <div class="name">${escapeHtml(o.label || o.class_zh || "物品")}</div>
        <div class="sub">${escapeHtml(o.zone || "未分区")} · ${escapeHtml(time)}</div>
        <div class="sub">${o.sightings ?? 0} 次观测</div>
      </div>`;
    card.onclick = () => {
      $("query-input").value = `${o.label || o.class_zh}在哪？`;
      $("query-form").requestSubmit();
      window.scrollTo({ top: 260, behavior: "smooth" });
    };
    box.appendChild(card);
  });
}

// ---------------- 时间线 ----------------
async function loadTimeline() {
  const data = await api("/api/captures?limit=12");
  if (!data.ok) return;
  const box = $("timeline");
  box.innerHTML = "";
  const caps = data.captures || [];
  $("timeline-count").textContent = `${caps.length} 帧`;
  if (!caps.length) {
    box.innerHTML = '<p class="muted small">还没有抓拍帧。</p>';
    return;
  }
  caps.forEach((c) => {
    const item = document.createElement("div");
    item.className = "timeline-item";
    const when = c.time_synced ? (c.captured_at_local || c.captured_at_utc) : "时间未同步";
    item.innerHTML = `
      <img alt="" src="${c.thumbnail_url}" />
      <div>
        <div class="when">${escapeHtml(when)}</div>
        <div class="what">${c.detections_count ?? 0} 个物品 · 抓拍 #${c.id}</div>
      </div>`;
    item.onclick = () => showCapture(c.id);
    box.appendChild(item);
  });
}

// ---------------- 事件绑定 ----------------
window.addEventListener("DOMContentLoaded", async () => {
  $("capture-btn").onclick = doCapture;
  $("auto-btn").onclick = toggleAuto;
  $("query-form").onsubmit = (e) => {
    e.preventDefault();
    runQuery();
  };
  await loadStatus();
  await Promise.all([loadLatestCapture(), loadObjects(), loadTimeline()]);
  setInterval(async () => {
    await loadStatus();
    if (state.autoRunning) {
      await Promise.all([loadLatestCapture(), loadObjects(), loadTimeline()]);
    }
  }, 6000);
});