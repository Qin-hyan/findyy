/* Findy 端到端验收工作台前端逻辑
 * 约束：不使用 ES module、不使用任何外部资源；所有请求同源相对路径。
 * 所有动态文本均通过 textContent / DOM 节点写入，避免 XSS。
 */
(function () {
  "use strict";

  var POLL_INTERVAL_MS = 4000;
  var CAPTURE_TIMEOUT_MS = 240000;
  var STATUS_TIMEOUT_MS = 12000;
  var SOURCE_LABELS = {
    esp32: "真实设备",
    replay: "回放演示",
    upload: "上传",
    unknown: "未知来源",
  };
  var DEFAULT_ACCEPTANCE_ITEMS = [
    ["device", "真实设备连接与探测"],
    ["capture", "抓拍与图像质量"],
    ["detection", "词表内物品检测"],
    ["association", "跨帧轨迹关联"],
    ["query", "找物查询回答与证据"],
    ["evidence", "证据导出与可复现性"],
  ];
  var FALLBACK_EXAMPLES = [
    "笔记本电脑最后出现在哪里？",
    "鼠标移动过吗？",
    "桌上都有哪些东西？",
    "我的钥匙最后出现在哪里？",
  ];

  var state = {
    status: null,
    acceptance: null,
    latestCaptureId: null,
    latestCapture: null,
    latestDetections: [],
    trackDetailId: null,
    busy: false,
    captureBusy: false,
    queryBusy: false,
    autoRunning: false,
    warmupDone: false,
    modelsReady: false,
    detector: null,
    embedder: null,
    examplesRendered: false,
    deviceIpTouched: false,
    statusInFlight: false,
    acceptanceInFlight: false,
    tracksInFlight: false,
    captureInFlight: false,
    pollInFlight: false,
  };

  // ---------------- 基础工具 ----------------
  function $(id) {
    return document.getElementById(id);
  }

  function node(tag, cls, text) {
    var el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text !== undefined && text !== null) el.textContent = String(text);
    return el;
  }

  function clear(el) {
    if (!el) return;
    while (el.firstChild) el.removeChild(el.firstChild);
  }

  function clockNow() {
    try {
      return new Date().toLocaleTimeString("zh-CN", { hour12: false });
    } catch (e) {
      return new Date().toTimeString().slice(0, 8);
    }
  }

  function dateTimeNow() {
    try {
      return new Date().toLocaleString("zh-CN", { hour12: false });
    } catch (e) {
      return new Date().toISOString();
    }
  }

  function textOr(value, fallback) {
    if (value === undefined || value === null || value === "") return fallback;
    return String(value);
  }

  function fmtScore(value) {
    var n = Number(value);
    if (value === undefined || value === null || value === "" || isNaN(n)) return "—";
    return n.toFixed(2);
  }

  function pct(value) {
    var n = Number(value);
    if (value === undefined || value === null || value === "" || isNaN(n)) return "—";
    return Math.round(n * 100) + "%";
  }

  function fmtMs(value) {
    var n = Number(value);
    if (value === undefined || value === null || value === "" || isNaN(n)) return "—";
    if (n >= 1000) return (n / 1000).toFixed(2) + " 秒";
    return (Math.round(n * 10) / 10) + " ms";
  }

  function normalizeSource(kind) {
    var k = String(kind === undefined || kind === null ? "" : kind).toLowerCase();
    if (k.indexOf("esp32") >= 0) return "esp32";
    if (k.indexOf("replay") >= 0) return "replay";
    if (k.indexOf("upload") >= 0) return "upload";
    return "unknown";
  }

  function sourceLabel(kind) {
    return SOURCE_LABELS[normalizeSource(kind)];
  }

  function sourceTitle(type) {
    var k = normalizeSource(type);
    if (k === "esp32") return "ESP32 真机";
    if (k === "replay") return "回放演示";
    if (k === "upload") return "上传";
    return type ? String(type) : "未知来源";
  }

  function sourceBadge(kind) {
    var k = normalizeSource(kind);
    return node("span", "src-badge " + k, SOURCE_LABELS[k]);
  }

  function setSourceBadge(container, kind) {
    if (!container) return;
    clear(container);
    container.appendChild(sourceBadge(kind));
  }

  function linkStatusLabel(status) {
    var s = String(status === undefined || status === null ? "" : status).toLowerCase();
    if (s === "matched" || s === "linked" || s === "confirmed") return "已关联";
    if (s === "ambiguous" || s === "gray" || s === "grey") return "灰区待确认";
    if (s === "new" || s === "new_track") return "新轨迹";
    if (s === "weak") return "弱关联";
    if (s === "unmatched" || s === "none" || s === "") return "未关联";
    return String(status);
  }

  function awardClass(status) {
    var s = String(status === undefined || status === null ? "" : status).toLowerCase();
    if (s === "pass" || s === "passed" || s === "ok" || s === "success") return "pass";
    if (s === "fail" || s === "failed" || s === "error") return "fail";
    return "nv";
  }

  function awardText(status) {
    var c = awardClass(status);
    if (c === "pass") return "PASS";
    if (c === "fail") return "FAIL";
    return "NOT VERIFIED";
  }

  function timeText(local, synced, fallback) {
    var v = local || fallback || "";
    if (!v) return "时间未知";
    if (synced === false) return v + "（时间未同步）";
    return String(v);
  }

  function isSafeUrl(url) {
    if (typeof url !== "string") return false;
    var u = url.trim();
    if (!u) return false;
    return u.charAt(0) === "/" || u.charAt(0) === "#";
  }

  function pickError(data, fallback) {
    if (data === undefined || data === null) return fallback;
    if (typeof data === "string") return data;
    var detail = data.detail;
    if (typeof detail === "string" && detail) return detail;
    if (Array.isArray(detail)) {
      try {
        return detail
          .map(function (d) {
            return d && (d.msg || d.message) ? d.msg || d.message : JSON.stringify(d);
          })
          .join("；");
      } catch (e) {
        /* ignore */
      }
    }
    if (typeof data.error === "string" && data.error) return data.error;
    if (typeof data.message === "string" && data.message) return data.message;
    return fallback;
  }

  function errMessage(err) {
    if (!err) return "未知错误";
    if (err.isTimeout) {
      return "请求超时（" + Math.round((err.timeoutMs || 0) / 1000) + " 秒）";
    }
    if (err.status !== undefined && err.status !== null) {
      return "HTTP " + err.status + "：" + (err.message || "请求失败");
    }
    return err.message || String(err);
  }

  // ---------------- HTTP ----------------
  function api(path, options) {
    options = options || {};
    var method = options.method || "GET";
    var timeoutMs = options.timeoutMs || 15000;
    var controller = new AbortController();
    var timer = setTimeout(function () {
      controller.abort();
    }, timeoutMs);
    var init = {
      method: method,
      headers: {},
      signal: controller.signal,
      cache: "no-store",
    };
    if (options.body !== undefined && options.body !== null) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    return fetch(path, init)
      .catch(function (netErr) {
        if (netErr && netErr.name === "AbortError") {
          var te = new Error("请求超时");
          te.isTimeout = true;
          te.timeoutMs = timeoutMs;
          throw te;
        }
        var ne = new Error("网络请求失败：" + (netErr && netErr.message ? netErr.message : String(netErr)));
        ne.isNetwork = true;
        throw ne;
      })
      .then(function (resp) {
        return resp
          .json()
          .catch(function () {
            return null;
          })
          .then(function (data) {
            if (!resp.ok) {
              var he = new Error(pickError(data, "HTTP " + resp.status));
              he.status = resp.status;
              he.payload = data;
              throw he;
            }
            return data;
          });
      })
      .finally(function () {
        clearTimeout(timer);
      });
  }

  // ---------------- 提示 / 日志 ----------------
  function toast(message, ok) {
    var el = $("toast");
    if (!el) return;
    el.textContent = message;
    el.classList.toggle("ok", !!ok);
    el.classList.remove("hidden");
    clearTimeout(el._timer);
    el._timer = setTimeout(function () {
      el.classList.add("hidden");
    }, 5200);
  }

  function logAction(action, outcome, ok) {
    var box = $("action-log");
    if (!box) return;
    var empty = box.querySelector(".wb-log-empty");
    if (empty) empty.remove();
    var cls = ok === true ? "ok" : ok === false ? "bad" : "pending";
    var row = node("div", "wb-log-row " + cls);
    row.appendChild(node("span", "wb-log-time", clockNow()));
    var body = node("span", "wb-log-body");
    body.appendChild(node("span", "wb-log-action", String(action)));
    body.appendChild(node("span", "wb-log-out", ok === true ? "OK" : String(outcome)));
    row.appendChild(body);
    box.appendChild(row);
    box.scrollTop = box.scrollHeight;
  }

  function setCaptureStatus(text, cls) {
    var el = $("capture-status");
    if (!el) return;
    el.textContent = text;
    el.className = "wb-live-status" + (cls ? " " + cls : "");
  }

  function setRunHint(text, bad) {
    var el = $("run-hint");
    if (!el) return;
    el.textContent = text;
    el.classList.toggle("bad", !!bad);
  }

  function setPill(id, text, cls) {
    var el = $(id);
    if (!el) return;
    el.textContent = text;
    el.className = "pill" + (cls ? " " + cls : "");
  }

  function setPlaceholder(title, sub) {
    var box = $("capture-placeholder");
    if (!box) return;
    clear(box);
    box.appendChild(node("p", "", title));
    if (sub) box.appendChild(node("p", "muted small", sub));
    box.classList.remove("hidden");
  }

  // ---------------- busy / 按钮状态 ----------------
  function captureBlockedReason() {
    if (!state.status) return "尚未读取到服务状态";
    if (!state.warmupDone) return "模型加载中（服务端 warmup 未完成）";
    if (!state.modelsReady) {
      var errs = [];
      if (state.detector && state.detector.error) errs.push("检测器：" + state.detector.error);
      if (state.embedder && state.embedder.error) errs.push("关联器：" + state.embedder.error);
      return "模型未就绪" + (errs.length ? "（" + errs.join("；") + "）" : "");
    }
    return "";
  }

  function currentRun() {
    return state.acceptance && state.acceptance.run ? state.acceptance.run : null;
  }

  function setDisabled(id, disabled, titleText) {
    var btn = $(id);
    if (!btn) return;
    btn.disabled = !!disabled;
    if (titleText !== undefined) btn.title = titleText || "";
  }

  function refreshControls() {
    var busy = state.busy || state.captureBusy;
    var run = currentRun();
    var runRunning = !!(run && run.status === "running");
    var blocked = captureBlockedReason();

    setDisabled("probe-btn", busy, busy ? "已有操作进行中" : "");
    setDisabled("connect-btn", busy, busy ? "已有操作进行中" : "");
    setDisabled("reset-source-btn", busy, busy ? "已有操作进行中" : "");
    setDisabled("capture-btn", busy || !!blocked, blocked || "");
    setDisabled("auto-start-btn", busy || (state.status ? state.autoRunning : false));
    setDisabled("auto-stop-btn", busy || (state.status ? !state.autoRunning : true));
    setDisabled("run-start-real", busy || runRunning, runRunning ? "本轮验收进行中" : "");
    setDisabled("run-start-demo", busy || runRunning, runRunning ? "本轮验收进行中" : "");
    setDisabled("run-finish", busy || !runRunning);

    var finish = $("run-finish");
    if (finish) finish.hidden = !runRunning;
    var exportBtn = $("export-evidence");
    if (exportBtn) exportBtn.hidden = !(run && !runRunning);

    var reasonEl = $("capture-reason");
    if (reasonEl) reasonEl.textContent = blocked ? "抓拍不可用：" + blocked : "";

    var captureBtn = $("capture-btn");
    if (captureBtn) captureBtn.textContent = state.captureBusy ? "抓拍与识别中…" : "立即抓拍";
    var autoStart = $("auto-start-btn");
    if (autoStart && !state.autoRunning) autoStart.textContent = "开始采集";
    var autoStop = $("auto-stop-btn");
    if (autoStop && state.autoRunning) autoStop.textContent = "停止采集";
  }

  function withBusy(task) {
    if (state.busy || state.captureBusy) {
      logAction("操作被忽略", "已有操作进行中", false);
      toast("已有操作进行中，请稍候", false);
      return Promise.resolve();
    }
    state.busy = true;
    refreshControls();
    return Promise.resolve()
      .then(task)
      .catch(function (err) {
        logAction("未处理异常", errMessage(err), false);
      })
      .finally(function () {
        state.busy = false;
        refreshControls();
      });
  }

  // ---------------- 状态轮询 ----------------
  function loadStatus(options) {
    options = options || {};
    if (state.statusInFlight) return Promise.resolve();
    state.statusInFlight = true;
    return api("/api/status", { timeoutMs: STATUS_TIMEOUT_MS })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error(pickError(data, "状态读取失败"));
        var prevStats = state.status && state.status.pipeline && state.status.pipeline.stats;
        var prevCaptures = prevStats && prevStats.captures !== undefined ? Number(prevStats.captures) : null;
        state.status = data;
        renderStatus(data);
        var stats = (data.pipeline && data.pipeline.stats) || {};
        var curCaptures = stats.captures !== undefined ? Number(stats.captures) : null;
        if (
          !state.captureBusy &&
          curCaptures !== null &&
          (prevCaptures === null ? curCaptures > 0 : curCaptures > prevCaptures)
        ) {
          loadLatestCapture(false);
          loadTracks(true);
        }
      })
      .catch(function (err) {
        if (!options.quiet) renderStatusFailure(err);
        else if (!state.status) renderStatusFailure(err);
      })
      .finally(function () {
        state.statusInFlight = false;
      });
  }

  function renderStatus(data) {
    var service = data.service || {};
    var pipeline = data.pipeline || {};
    var detector = pipeline.detector || {};
    var embedder = pipeline.embedder || {};
    var stats = pipeline.stats || {};
    var source = data.source || {};
    var device = data.device || {};
    var config = data.config || {};

    state.warmupDone = !!data.warmup_done;
    state.modelsReady = !!(detector.loaded && embedder.loaded);
    state.detector = detector;
    state.embedder = embedder;
    state.autoRunning = !!service.running;

    // --- pills ---
    setPill("pill-service", "服务 · 在线", "ok");

    var srcType = source.type || (config.capture && config.capture.source);
    var srcText = "采集源 · " + sourceTitle(srcType);
    if (normalizeSource(srcType) === "esp32") {
      var espUrl = source.esp32_url || device.configured_url;
      if (espUrl) srcText += " " + espUrl;
    } else if (normalizeSource(srcType) === "replay") {
      srcText += source.replay_remaining !== undefined && source.replay_remaining !== null ? "（剩 " + source.replay_remaining + " 张）" : "";
    }
    setPill("pill-source", srcText, "");

    if (state.modelsReady) {
      setPill("pill-model", "模型 · OWLv2 + DINOv2 就绪", "ok");
    } else if (state.warmupDone) {
      setPill("pill-model", "模型 · 加载失败", "bad");
    } else {
      setPill("pill-model", "模型 · 加载中…", "warn");
    }
    $("pill-model").title = (pipeline.model_errors || []).join("\n") || "";

    setPill("pill-db", "数据库 · " + (stats.captures !== undefined ? stats.captures : "?") + " 帧 / " + (stats.active_tracks !== undefined ? stats.active_tracks : "?") + " 轨迹", "ok");
    setPill("pill-auto", "自动采集 · " + (state.autoRunning ? "运行中" : "停止"), state.autoRunning ? "ok" : "");

    // --- 运行状态面板 ---
    var configured = source.configured_type || (config.capture && config.capture.source);
    $("src-configured").textContent = sourceTitle(configured);
    var runtimeText = sourceTitle(srcType);
    if (source.runtime_override) runtimeText += "（本次会话覆盖配置）";
    $("src-runtime").textContent = runtimeText;
    $("src-override").textContent = source.runtime_override
      ? "是 · 仅本次会话生效，重启后恢复配置"
      : "否";
    $("src-replay").textContent =
      normalizeSource(srcType) === "replay" && source.replay_remaining !== undefined && source.replay_remaining !== null
        ? source.replay_remaining + " 张"
        : normalizeSource(configured) === "replay"
        ? "不适用（当前会话非回放）"
        : "不适用";
    $("src-provenance").textContent = provenanceText(source.provenance);
    $("last-probe").textContent = probeSummaryText(device.last_probe);

    $("model-detector").textContent = modelText(detector, "OWLv2 检测器");
    $("model-embedder").textContent = modelText(embedder, "DINOv2 关联器");
    $("db-status").textContent =
      "已连接 · 帧 " + numText(stats.captures) +
      " · 检测 " + numText(stats.detections) +
      " · 轨迹 " + numText(stats.active_tracks) +
      " · 灰区关联 " + numText(stats.ambiguous_links) +
      " · 未同步帧 " + numText(stats.unsynced_captures);
    $("db-source-stats").textContent = sourceStatsText(stats.captures_by_source);
    $("last-capture-at").textContent = textOr(stats.last_capture_at, "尚无抓拍");
    $("auto-status").textContent = autoStatusText(service);
    $("service-error").textContent = serviceErrorsText(service, pipeline);
    $("status-updated").textContent = "更新于 " + clockNow();

    // 设备地址默认值：仅在用户从未编辑过输入框时填充
    var ipInput = $("device-ip");
    if (ipInput) {
      var fallbackUrl = device.configured_url || source.esp32_url || "";
      if (!ipInput.value && fallbackUrl && !state.deviceIpTouched && document.activeElement !== ipInput) {
        ipInput.value = fallbackUrl;
      }
    }

    // 示例查询
    var examples = Array.isArray(data.examples) ? data.examples : [];
    var clean = examples
      .map(function (e) {
        return typeof e === "string" ? e : e && (e.text || e.query) ? e.text || e.query : "";
      })
      .filter(Boolean);
    if (!state.examplesRendered && clean.length) {
      renderExampleChips(clean);
      state.examplesRendered = true;
    }

    refreshControls();
  }

  function numText(v) {
    return v === undefined || v === null ? "?" : String(v);
  }

  function modelText(model, title) {
    var parts = [];
    if (model.backend) parts.push(String(model.backend));
    if (model.model) parts.push(String(model.model));
    parts.push(model.loaded ? "已加载" : "未加载");
    if (model.classes && model.classes.length) parts.push("词表 " + model.classes.length + " 类");
    if (model.error) parts.push("错误：" + model.error);
    if (!parts.length) return title;
    return parts.join(" · ");
  }

  function sourceStatsText(bySource) {
    if (!bySource || typeof bySource !== "object") return "—";
    var keys = Object.keys(bySource);
    if (!keys.length) return "尚无抓拍";
    return keys
      .map(function (k) {
        return sourceTitle(k) + " " + numText(bySource[k]);
      })
      .join(" · ");
  }

  function provenanceText(value) {
    if (value === undefined || value === null || value === "") return "—";
    if (typeof value === "string") return value;
    if (typeof value === "number" || typeof value === "boolean") return String(value);
    if (Array.isArray(value)) {
      return value.length
        ? value
            .map(function (v) {
              return typeof v === "object" && v ? JSON.stringify(v) : String(v);
            })
            .join(" · ")
        : "—";
    }
    if (typeof value === "object") {
      var keys = Object.keys(value);
      if (!keys.length) return "—";
      return keys
        .map(function (k) {
          return sourceTitle(k) + " " + numText(value[k]);
        })
        .join(" · ");
    }
    return String(value);
  }

  function shortSourceRef(ref) {
    if (ref === undefined || ref === null || ref === "") return "";
    var s = String(ref);
    if (/^https?:\/\//i.test(s)) return s;
    var isPath = /^[A-Za-z]:[\\/]/.test(s) || s.indexOf("\\\\") === 0 || s.charAt(0) === "/";
    if (!isPath && s.indexOf("\\") < 0) return s;
    var parts = s.split(/[\\/]+/).filter(Boolean);
    if (parts.length > 2) return "…/" + parts.slice(-2).join("/");
    return parts.join("/") || s;
  }

  function autoStatusText(service) {
    var interval = service.interval_seconds !== undefined && service.interval_seconds !== null ? service.interval_seconds : "?";
    var base = service.running ? "运行中" : "已停止";
    var parts = [
      base,
      "周期 " + interval + " 秒",
      "循环 " + numText(service.cycles),
      "失败 " + numText(service.failures),
    ];
    if (service.consecutive_failures) parts.push("连续失败 " + service.consecutive_failures);
    if (service.capture_in_progress) parts.push("抓拍进行中");
    if (service.last_error) {
      parts.push("最近错误" + (service.last_error_at ? "（" + service.last_error_at + "）" : "") + "：" + service.last_error);
    }
    return parts.join(" · ");
  }

  function serviceErrorsText(service, pipeline) {
    var lines = [];
    if (service.last_error) {
      lines.push(
        "服务最近错误" +
          (service.last_error_at ? "（" + service.last_error_at + "）" : "") +
          "：" +
          service.last_error
      );
    }
    if (service.last_cycle_at) lines.push("最近采集周期：" + service.last_cycle_at);
    var modelErrors = (pipeline && pipeline.model_errors) || [];
    modelErrors.forEach(function (e) {
      lines.push("模型错误：" + e);
    });
    if (!lines.length) return "—";
    return lines.join("\n");
  }

  function probeSummaryText(probe) {
    if (!probe) return "—";
    var hasInfo =
      typeof probe.ok === "boolean" ||
      probe.at ||
      probe.url ||
      probe.error ||
      (probe.summary && Object.keys(probe.summary).length);
    if (!hasInfo) return "尚未探测";
    if (probe.ok !== true) {
      return "失败" + (probe.error ? "：" + probe.error : "") + (probe.at ? "（" + probe.at + "）" : "");
    }
    var lines = [];
    var head = "成功";
    if (probe.at) head += " · " + probe.at;
    if (probe.url) head += " · " + probe.url;
    lines.push(head);
    var s = probe.summary || {};
    if (s.device || s.firmware) {
      lines.push("设备：" + textOr(s.device, "—") + " · 固件：" + textOr(s.firmware, "—"));
    }
    var wifi = s.wifi || {};
    if (Object.keys(wifi).length) {
      lines.push(
        "Wi-Fi：" +
          (wifi.connected === false ? "未连接" : "已连接") +
          (wifi.ip ? " · 设备 IP " + wifi.ip : "") +
          (wifi.rssi !== undefined && wifi.rssi !== null ? " · RSSI " + wifi.rssi : "")
      );
    }
    var cam = s.camera || {};
    if (Object.keys(cam).length) {
      lines.push(
        "摄像头：" +
          (cam.ready === false ? "未就绪" : "就绪") +
          (cam.sensor ? " · " + cam.sensor : "") +
          (cam.width ? " · " + cam.width + "×" + cam.height : "")
      );
    }
    var time = s.time || {};
    if (Object.keys(time).length) {
      lines.push("设备时间：" + (time.synced ? "已同步" : "未同步") + (time.local ? " · " + time.local : ""));
    }
    if (s.stats && Object.keys(s.stats).length) {
      lines.push(
        "统计：" +
          Object.keys(s.stats)
            .map(function (k) {
              var v = s.stats[k];
              return k + " " + (v && typeof v === "object" ? JSON.stringify(v) : String(v));
            })
            .join(" · ")
      );
    }
    return lines.join("\n");
  }

  function renderStatusFailure(err) {
    var msg = errMessage(err);
    setPill("pill-service", "服务 · 不可用", "bad");
    setPill("pill-db", "数据库 · 未知", "bad");
    setPill("pill-model", "模型 · 未知", "warn");
    setPill("pill-source", "采集源 · 未知", "");
    setPill("pill-auto", "自动采集 · 未知", "warn");
    $("status-updated").textContent = "状态读取失败（" + clockNow() + "）";
    $("service-error").textContent = "读取 /api/status 失败：" + msg;
    setCaptureStatus("服务状态读取失败：" + msg, "bad");
  }

  // ---------------- 设备操作 ----------------
  function doProbe() {
    var url = ($("device-ip").value || "").trim();
    return withBusy(function () {
      logAction("检查设备连接" + (url ? " " + url : ""), "进行中…", null);
      setCaptureStatus("正在检查设备连接…", "live");
      var body = url ? { base_url: url } : {};
      return api("/api/device/probe", { method: "POST", body: body, timeoutMs: 25000 })
        .then(function (data) {
          if (!data || data.ok === false) {
            var pe = new Error(pickError(data, "设备检查失败"));
            pe.payload = data;
            throw pe;
          }
          var probe = data.probe || null;
          $("last-probe").textContent = probeSummaryText(probe);
          if (probe && probe.ok === true) {
            logAction("检查设备连接", "OK · " + textOr(probe.summary && probe.summary.device, "设备在线"), true);
            setCaptureStatus("设备连接正常，可以抓拍。", "ok");
            toast("设备连接正常", true);
          } else {
            var failMsg = "设备检查失败：" + textOr(probe && probe.error, "未知错误");
            logAction("检查设备连接", textOr(probe && probe.error, "失败"), false);
            setCaptureStatus(failMsg, "bad");
            toast(failMsg, false);
          }
          return loadStatus({ quiet: true });
        })
        .catch(function (err) {
          var payload = err.payload;
          if (payload && payload.probe) $("last-probe").textContent = probeSummaryText(payload.probe);
          var msg = "设备检查失败：" + errMessage(err);
          logAction("检查设备连接", errMessage(err), false);
          setCaptureStatus(msg, "bad");
          toast(msg, false);
        });
    });
  }

  function doConnect() {
    var url = ($("device-ip").value || "").trim();
    return withBusy(function () {
      logAction("切换到设备采集（仅本次会话）", "进行中…", null);
      return api("/api/device/connect", { method: "POST", body: { base_url: url }, timeoutMs: 25000 })
        .then(function (data) {
          if (!data || data.ok === false) throw new Error(pickError(data, "连接设备失败"));
          var note = data.note ? " · " + data.note : "";
          var src = data.source || {};
          logAction("切换到设备采集", "OK · " + sourceTitle(src.type) + (src.esp32_url ? " " + src.esp32_url : "") + note, true);
          setCaptureStatus("已切换到本次会话的采集源：" + sourceTitle(src.type) + note, "ok");
          toast("已切换采集源（仅本次会话）", true);
          return loadStatus({ quiet: true });
        })
        .catch(function (err) {
          var payload = err.payload;
          if (payload && payload.probe) $("last-probe").textContent = probeSummaryText(payload.probe);
          var msg = "切换到设备采集失败：" + errMessage(err);
          logAction("切换到设备采集", errMessage(err), false);
          setCaptureStatus(msg, "bad");
          toast(msg, false);
        });
    });
  }

  function doResetSource() {
    return withBusy(function () {
      logAction("恢复配置采集源", "进行中…", null);
      return api("/api/source/reset", { method: "POST", body: {}, timeoutMs: 20000 })
        .then(function (data) {
          if (!data || data.ok === false) throw new Error(pickError(data, "恢复配置采集源失败"));
          var src = data.source || {};
          var note = data.note ? " · " + data.note : "";
          logAction("恢复配置采集源", "OK · " + sourceTitle(src.type) + note, true);
          setCaptureStatus("已恢复配置采集源：" + sourceTitle(src.type) + note, "ok");
          toast("已恢复配置采集源", true);
          return loadStatus({ quiet: true });
        })
        .catch(function (err) {
          var msg = "恢复配置采集源失败：" + errMessage(err);
          logAction("恢复配置采集源", errMessage(err), false);
          setCaptureStatus(msg, "bad");
          toast(msg, false);
        });
    });
  }

  function doAutoStart() {
    return withBusy(function () {
      logAction("开始自动采集", "进行中…", null);
      return api("/api/service/start", { method: "POST", body: {}, timeoutMs: 20000 })
        .then(function (data) {
          if (!data || data.ok === false) throw new Error(pickError(data, "启动自动采集失败"));
          logAction("开始自动采集", "OK", true);
          setCaptureStatus("自动采集已启动。", "ok");
          toast("自动采集已启动", true);
          return loadStatus({ quiet: true }).then(function () {
            return Promise.allSettled([loadLatestCapture(false), loadTracks(true)]);
          });
        })
        .catch(function (err) {
          var msg = "启动自动采集失败：" + errMessage(err);
          logAction("开始自动采集", errMessage(err), false);
          setCaptureStatus(msg, "bad");
          toast(msg, false);
        });
    });
  }

  function doAutoStop() {
    return withBusy(function () {
      logAction("停止自动采集", "进行中…", null);
      return api("/api/service/stop", { method: "POST", body: {}, timeoutMs: 20000 })
        .then(function (data) {
          if (!data || data.ok === false) throw new Error(pickError(data, "停止自动采集失败"));
          logAction("停止自动采集", "OK", true);
          setCaptureStatus("自动采集已停止。", "ok");
          toast("自动采集已停止", true);
          return loadStatus({ quiet: true });
        })
        .catch(function (err) {
          var msg = "停止自动采集失败：" + errMessage(err);
          logAction("停止自动采集", errMessage(err), false);
          setCaptureStatus(msg, "bad");
          toast(msg, false);
        });
    });
  }

  // ---------------- 抓拍 ----------------
  function doCapture() {
    if (state.captureBusy || state.busy) return;
    var blocked = captureBlockedReason();
    if (blocked) {
      var blockMsg = "抓拍未执行：" + blocked;
      logAction("立即抓拍", blockMsg, false);
      setCaptureStatus(blockMsg, "bad");
      toast(blockMsg, false);
      return;
    }
    state.captureBusy = true;
    refreshControls();
    var startedAt = performance.now();
    var timer = setInterval(function () {
      var seconds = (performance.now() - startedAt) / 1000;
      setCaptureStatus(
        "已等待 " + seconds.toFixed(1) + " 秒 · OWLv2 CPU 单帧通常 6–11 秒，请勿关闭页面",
        "live"
      );
    }, 250);
    logAction("立即抓拍", "进行中…", null);
    setCaptureStatus("已等待 0.0 秒 · OWLv2 CPU 单帧通常 6–11 秒，请勿关闭页面", "live");

    api("/api/capture", { method: "POST", body: {}, timeoutMs: CAPTURE_TIMEOUT_MS })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error(pickError(data, "抓拍失败"));
        var capture = data.capture || {};
        var detections = Array.isArray(data.detections) ? data.detections : [];
        var warnings = Array.isArray(data.warnings) ? data.warnings : [];
        logAction(
          "立即抓拍",
          "OK · 抓拍 #" + textOr(capture.id, "?") + " · " + detections.length + " 个检测" + (data.duplicate ? "（重复帧）" : ""),
          true
        );
        setCaptureStatus(
          "抓拍完成 · 抓拍 #" + textOr(capture.id, "?") + " · " + detections.length + " 个物品" +
            (warnings.length ? " · " + warnings.join("；") : ""),
          "ok"
        );
        toast("抓拍完成", true);
        renderCapture(capture, detections, { duplicate: data.duplicate });
        return loadStatus({ quiet: true }).then(function () {
          return loadTracks(true);
        });
      })
      .catch(function (err) {
        if (err && err.isTimeout) {
          var timeoutMsg =
            "抓拍请求超时（" + Math.round(CAPTURE_TIMEOUT_MS / 1000) + " 秒）：后台可能仍在处理，请稍后刷新状态。";
          logAction("立即抓拍", timeoutMsg, false);
          setCaptureStatus(timeoutMsg, "bad");
          toast(timeoutMsg, false);
        } else {
          var msg = "抓拍失败：" + errMessage(err);
          logAction("立即抓拍", errMessage(err), false);
          setCaptureStatus(msg, "bad");
          toast(msg, false);
          var cap = err.payload && err.payload.capture;
          if (cap) renderCaptureMetaOnly(cap);
        }
      })
      .finally(function () {
        clearInterval(timer);
        state.captureBusy = false;
        refreshControls();
      });
  }

  function renderCaptureMetaOnly(capture) {
    if (!capture) return;
    var lines = [];
    if (capture.status) lines.push("状态：" + capture.status);
    if (capture.detect_error) lines.push("检测失败原文：" + capture.detect_error);
    if (capture.error) lines.push("错误原文：" + capture.error);
    if (lines.length) $("capture-meta").textContent = lines.join("\n");
  }

  // ---------------- 抓拍详情渲染 ----------------
  function loadLatestCapture(force) {
    if (state.captureInFlight) return Promise.resolve();
    state.captureInFlight = true;
    return api("/api/captures?limit=1", { timeoutMs: 15000 })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error(pickError(data, "抓拍列表读取失败"));
        var caps = (data.captures || []).filter(Boolean);
        if (!caps.length) {
          state.latestCaptureId = null;
          setPlaceholder("还没有抓拍记录", "点击“立即抓拍”获取第一帧");
          $("capture-img").hidden = true;
          $("capture-img").removeAttribute("src");
          clear($("overlay"));
          $("capture-meta").textContent = "尚无抓拍";
          $("capture-meta").classList.remove("bad");
          clear($("detection-rows"));
          var emptyRow = node("tr", "");
          var emptyCell = node("td", "muted small", "尚无抓拍");
          emptyCell.colSpan = 7;
          emptyRow.appendChild(emptyCell);
          $("detection-rows").appendChild(emptyRow);
          setSourceBadge($("capture-source-badge"), null);
          return;
        }
        var cap = caps[0];
        if (!force && String(cap.id) === String(state.latestCaptureId)) return;
        return showCapture(cap.id);
      })
      .catch(function (err) {
        if (!state.latestCapture) {
          setPlaceholder("抓拍列表读取失败", errMessage(err));
          $("capture-meta").textContent = "读取抓拍失败：" + errMessage(err);
          $("capture-meta").classList.add("bad");
        }
      })
      .finally(function () {
        state.captureInFlight = false;
      });
  }

  function showCapture(captureId) {
    if (captureId === undefined || captureId === null) return Promise.resolve();
    return api("/api/captures/" + encodeURIComponent(captureId), { timeoutMs: 15000 })
      .then(function (data) {
        if (!data || data.ok === false || !data.capture) throw new Error(pickError(data, "抓拍详情读取失败"));
        state.latestCaptureId = data.capture.id !== undefined ? data.capture.id : captureId;
        renderCapture(data.capture, data.detections || [], {});
      })
      .catch(function (err) {
        setCaptureStatus("读取抓拍详情失败：" + errMessage(err), "bad");
        logAction("读取抓拍 #" + captureId, errMessage(err), false);
      });
  }

  function renderCapture(capture, detections, extra) {
    if (!capture) return;
    extra = extra || {};
    state.latestCapture = capture;
    state.latestDetections = detections || [];

    var img = $("capture-img");
    var url = capture.image_url || (capture.id !== undefined && capture.id !== null ? "/api/captures/" + capture.id + "/image" : "");
    if (url) {
      var full = url + (url.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
      img.onerror = function () {
        img.hidden = true;
        setPlaceholder("抓拍图片加载失败", "URL：" + url);
      };
      img.onload = function () {
        $("capture-placeholder").classList.add("hidden");
      };
      img.src = full;
      img.hidden = false;
      $("capture-placeholder").classList.add("hidden");
    } else {
      img.hidden = true;
      img.removeAttribute("src");
    }

    renderOverlay(detections);
    renderCaptureMeta(capture, detections, extra);
    renderDetectionTable(capture, detections);
    setSourceBadge($("capture-source-badge"), capture.source_kind);
  }

  function renderOverlay(detections) {
    var overlay = $("overlay");
    clear(overlay);
    (detections || []).forEach(function (d) {
      var b = d && d.bbox_norm;
      if (!Array.isArray(b) || b.length < 4) return;
      var x1 = Number(b[0]);
      var y1 = Number(b[1]);
      var x2 = Number(b[2]);
      var y2 = Number(b[3]);
      if ([x1, y1, x2, y2].some(function (v) { return !isFinite(v); })) return;
      x1 = Math.min(1, Math.max(0, x1));
      y1 = Math.min(1, Math.max(0, y1));
      x2 = Math.min(1, Math.max(0, x2));
      y2 = Math.min(1, Math.max(0, y2));
      var box = node("div", "bbox" + (String(d.link_status) === "ambiguous" ? " ambiguous" : ""));
      box.style.left = x1 * 100 + "%";
      box.style.top = y1 * 100 + "%";
      box.style.width = Math.max(0.5, (x2 - x1) * 100) + "%";
      box.style.height = Math.max(0.5, (y2 - y1) * 100) + "%";
      var tag = node(
        "span",
        "tag",
        textOr(d.class_zh, textOr(d.class, "物品")) + " " + pct(d.confidence)
      );
      box.appendChild(tag);
      overlay.appendChild(box);
    });
  }

  function renderCaptureMeta(capture, detections, extra) {
    var lines = [];
    var syncedNote = capture.time_synced === false ? "（设备时间未同步，时间不可信）" : "";
    lines.push("抓拍时间：" + textOr(capture.captured_at_local || capture.captured_at_utc, "未知") + syncedNote);
    lines.push("来源：" + sourceLabel(capture.source_kind));
    if (capture.width !== undefined && capture.height !== undefined && capture.width !== null) {
      lines.push("分辨率：" + capture.width + "×" + capture.height);
    }
    lines.push("检测耗时：" + fmtMs(capture.detect_ms) + " · 特征耗时：" + fmtMs(capture.embed_ms) + " · 总处理耗时：" + fmtMs(capture.process_ms));
    lines.push("状态：" + textOr(capture.status, "未知") + (capture.time_ago ? " · 距今 " + capture.time_ago : ""));
    if (capture.detect_error) lines.push("检测失败原文：" + capture.detect_error);
    if (capture.error) lines.push("错误原文：" + capture.error);
    if (extra && extra.duplicate) lines.push("提示：本次被判定为重复帧，复用了已有抓拍记录。");
    var meta = $("capture-meta");
    meta.textContent = lines.join("\n");
    meta.classList.toggle("bad", !!capture.detect_error || capture.status === "failed");
  }

  function renderDetectionTable(capture, detections) {
    var tbody = $("detection-rows");
    clear(tbody);
    var rows = Array.isArray(detections) ? detections : [];
    if (!rows.length) {
      var tr = node("tr", "");
      var td = node("td", "muted small", capture && capture.detect_error ? "检测失败，原文见上方" : "未检出词表内物品");
      td.colSpan = 7;
      tr.appendChild(td);
      tbody.appendChild(tr);
      return;
    }
    rows.forEach(function (d) {
      var tr = node("tr", "");
      tr.appendChild(node("td", "", textOr(d.class_zh, textOr(d.class, "未命名"))));
      tr.appendChild(node("td", "wb-num", pct(d.confidence)));
      tr.appendChild(node("td", "", textOr(d.region, "未分区")));
      tr.appendChild(node("td", "wb-num", fmtScore(d.link_score)));
      tr.appendChild(node("td", "", linkStatusLabel(d.link_status)));
      var srcCell = node("td", "");
      srcCell.appendChild(sourceBadge(d.source_kind));
      tr.appendChild(srcCell);
      var cropCell = node("td", "");
      if (d.crop_url) {
        var img = node("img", "wb-crop");
        img.src = d.crop_url;
        img.alt = textOr(d.class_zh, "裁剪图");
        img.loading = "lazy";
        cropCell.appendChild(img);
      } else {
        cropCell.textContent = "—";
      }
      tr.appendChild(cropCell);
      tbody.appendChild(tr);
    });
  }

  // ---------------- 轨迹 ----------------
  function loadTracks(quiet) {
    if (state.tracksInFlight) return Promise.resolve();
    state.tracksInFlight = true;
    return api("/api/objects", { timeoutMs: 15000 })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error(pickError(data, "轨迹列表读取失败"));
        renderTracks(Array.isArray(data.objects) ? data.objects : []);
      })
      .catch(function (err) {
        var box = $("tracks");
        clear(box);
        box.appendChild(node("p", "muted small", "读取轨迹失败：" + errMessage(err)));
        if (!quiet) logAction("读取轨迹", errMessage(err), false);
      })
      .finally(function () {
        state.tracksInFlight = false;
      });
  }

  function renderTracks(objects) {
    var box = $("tracks");
    clear(box);
    $("tracks-count").textContent = objects.length + " 条";
    if (!objects.length) {
      box.appendChild(node("p", "muted small", "还没有轨迹记录。先抓拍一张。"));
      return;
    }
    objects.forEach(function (o) {
      var item = node(
        "div",
        "wb-track-item" +
          (String(o.link_status) === "ambiguous" ? " ambiguous" : "") +
          (state.trackDetailId !== null && String(o.track_id) === String(state.trackDetailId) ? " selected" : "")
      );
      item.dataset.trackId = String(o.track_id);

      var row1 = node("div", "wb-track-row1");
      var label = o.label;
      var clsZh = o.class_zh;
      row1.appendChild(node("span", "wb-track-name", textOr(label, textOr(clsZh, "未命名轨迹"))));
      if (clsZh) {
        row1.appendChild(node("span", "badge dim", "类别 " + clsZh));
      } else if (!label) {
        row1.appendChild(node("span", "badge dim", "类别未知"));
      }
      row1.appendChild(sourceBadge(o.source_kind));
      if (String(o.link_status) === "ambiguous") row1.appendChild(node("span", "badge warn", "灰区候选"));
      row1.appendChild(node("span", "badge dim", "出现 " + numText(o.sightings) + " 次"));
      item.appendChild(row1);

      var row2 = node("div", "wb-track-sub");
      row2.appendChild(node("span", "", "最后区域：" + textOr(o.zone, "未分区")));
      row2.appendChild(node("span", "", "最后时间：" + timeText(o.time_local, o.time_synced, o.time_ago)));
      row2.appendChild(node("span", "", "最近关联分：" + fmtScore(o.link_score)));
      row2.appendChild(node("span", "", "状态：" + linkStatusLabel(o.link_status)));
      item.appendChild(row2);

      if (o.uncertainty) {
        item.appendChild(node("div", "note", "⚠ " + o.uncertainty));
      }

      item.onclick = function () {
        loadTrackDetail(o.track_id);
      };
      box.appendChild(item);
    });
  }

  function loadTrackDetail(trackId) {
    state.trackDetailId = trackId;
    var box = $("track-detail");
    clear(box);
    box.appendChild(node("p", "muted small", "加载轨迹详情…"));
    $("track-detail-title").textContent = "轨迹 #" + trackId;
    Array.prototype.forEach.call(document.querySelectorAll(".wb-track-item"), function (n) {
      n.classList.toggle("selected", n.dataset.trackId === String(trackId));
    });
    return api("/api/tracks/" + encodeURIComponent(trackId), { timeoutMs: 15000 })
      .then(function (data) {
        if (!data || data.ok === false || !data.track) throw new Error(pickError(data, "轨迹详情读取失败"));
        renderTrackDetail(data.track, Array.isArray(data.detections) ? data.detections : []);
      })
      .catch(function (err) {
        clear(box);
        box.appendChild(node("p", "muted small", "读取轨迹详情失败：" + errMessage(err)));
        logAction("读取轨迹 #" + trackId, errMessage(err), false);
      });
  }

  function renderTrackDetail(track, detections) {
    var box = $("track-detail");
    clear(box);
    $("track-detail-title").textContent = "轨迹 #" + textOr(track.id, "?") + " · " + textOr(track.class_zh, textOr(track.label, "未命名"));

    var head = node("div", "wb-track-head");
    head.appendChild(node("strong", "", textOr(track.class_zh, textOr(track.label, "未命名轨迹"))));
    head.appendChild(node("span", "badge dim", "出现 " + numText(track.sightings) + " 次"));
    if (track.status) head.appendChild(node("span", "badge dim", "状态 " + track.status));
    (track.source_kinds || []).forEach(function (k) {
      head.appendChild(sourceBadge(k));
    });
    box.appendChild(head);

    if (track.mixed_sources) {
      box.appendChild(
        node(
          "div",
          "wb-track-warn",
          "mixed_sources：该轨迹包含多个来源（" +
            (track.source_kinds || []).map(sourceLabel).join("、") +
            "），跨来源关联结果可能不可靠，请人工核对。"
        )
      );
    }

    var regions = (track.region_history || [])
      .map(function (r) {
        if (typeof r === "string") return r;
        return r && (r.name || r.region || r.zone) ? r.name || r.region || r.zone : "";
      })
      .filter(Boolean);
    if (regions.length) {
      box.appendChild(node("div", "muted small", "区域历史：" + regions.join(" → ")));
    }
    var seen = [];
    if (track.first_seen_utc) seen.push("首次：" + track.first_seen_utc);
    if (track.last_seen_utc) seen.push("最近：" + track.last_seen_utc);
    if (seen.length) box.appendChild(node("div", "muted small", seen.join(" · ")));

    var timeline = node("div", "wb-timeline");
    if (!detections.length) {
      timeline.appendChild(node("p", "muted small", "该轨迹暂无跨帧记录。"));
    } else {
      detections.forEach(function (d) {
        var row = node("div", "wb-timeline-item");
        var pic = node("div", "thumb");
        var imgUrl = d.crop_url || d.image_url;
        if (imgUrl) {
          var img = node("img", "wb-crop-lg");
          img.src = imgUrl;
          img.alt = "帧证据";
          img.loading = "lazy";
          pic.appendChild(img);
        } else {
          pic.appendChild(node("span", "muted small", "无图片"));
        }
        row.appendChild(pic);

        var meta = node("div", "wb-timeline-meta");
        meta.appendChild(node("div", "wb-timeline-time", timeText(d.time_local, d.time_synced, d.time_utc)));
        var tags = node("div", "wb-timeline-tags");
        tags.appendChild(node("span", "", "区域 " + textOr(d.zone, "未分区")));
        tags.appendChild(node("span", "", "置信度 " + pct(d.confidence)));
        tags.appendChild(node("span", "", "关联分 " + fmtScore(d.link_score)));
        tags.appendChild(node("span", "", "关联状态 " + linkStatusLabel(d.link_status)));
        var srcWrap = node("span", "");
        srcWrap.appendChild(sourceBadge(d.source_kind));
        tags.appendChild(srcWrap);
        meta.appendChild(tags);

        if (Array.isArray(d.candidates) && d.candidates.length) {
          var cands = node("div", "wb-candidates");
          cands.appendChild(node("span", "muted small", "灰区候选："));
          d.candidates.forEach(function (c) {
            cands.appendChild(
              node(
                "span",
                "chip plain",
                "#" + textOr(c.track_id, "?") + " " + textOr(c.class_zh, textOr(c.label, "")) + " " + fmtScore(c.score)
              )
            );
          });
          meta.appendChild(cands);
        }
        row.appendChild(meta);

        if (d.capture_id !== undefined && d.capture_id !== null) {
          row.onclick = function () {
            showCapture(d.capture_id).then(function () {
              scrollToEl("detection-card");
            });
          };
        }
        timeline.appendChild(row);
      });
    }
    box.appendChild(timeline);
  }

  // ---------------- 查询 ----------------
  function renderExampleChips(examples) {
    var box = $("query-examples");
    if (!box) return;
    clear(box);
    (examples || []).slice(0, 4).forEach(function (q) {
      var chip = node("span", "chip", q);
      chip.onclick = function () {
        $("query-input").value = q;
        runQuery(q);
      };
      box.appendChild(chip);
    });
  }

  function runQuery(text) {
    var q = String(text !== undefined && text !== null ? text : $("query-input").value || "").trim();
    if (!q) {
      $("answer").className = "answer help";
      $("answer").textContent = "请输入要查询的内容。";
      return;
    }
    if (state.queryBusy) return;
    state.queryBusy = true;
    var submit = $("query-submit");
    if (submit) submit.disabled = true;
    $("query-input").value = q;
    clear($("results"));
    clear($("query-suggestions"));
    removeNode("query-notes");
    $("query-meta").textContent = "—";
    $("query-intent").textContent = "—";
    $("answer").className = "answer";
    $("answer").textContent = "正在检索本地记忆…";

    api("/api/query", { method: "POST", body: { text: q }, timeoutMs: 60000 })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error(pickError(data, "查询失败"));
        renderQuery(data);
      })
      .catch(function (err) {
        var answer = $("answer");
        answer.className = "answer notfound";
        answer.textContent = "查询失败：" + errMessage(err);
        $("query-meta").textContent = "错误原文：" + errMessage(err);
        logAction("找物查询", errMessage(err), false);
      })
      .finally(function () {
        state.queryBusy = false;
        if (submit) submit.disabled = false;
      });
  }

  function removeNode(id) {
    var existing = $(id);
    if (existing && existing.parentNode) existing.parentNode.removeChild(existing);
  }

  function renderQuery(data) {
    var answer = $("answer");
    var status = String(data.status || "").toLowerCase();
    answer.className = "answer";
    if (status === "not_found" || status === "empty" || status === "notfound") answer.classList.add("notfound");
    else if (status === "help") answer.classList.add("help");
    answer.textContent = textOr(data.answer, "（没有回答）");

    $("query-intent").textContent = "意图：" + textOr(data.intent_zh, textOr(data.intent, "—"));
    var metaParts = [];
    metaParts.push("延迟：" + (data.latency_ms !== undefined && data.latency_ms !== null ? data.latency_ms + " ms" : "—"));
    metaParts.push("状态：" + textOr(data.status, "—"));
    if (data.query_log_id !== undefined && data.query_log_id !== null) metaParts.push("查询记录 #" + data.query_log_id);
    $("query-meta").textContent = metaParts.join(" · ");

    removeNode("query-notes");
    if (Array.isArray(data.notes) && data.notes.length) {
      var notes = node("div", "");
      notes.id = "query-notes";
      notes.className = "notes";
      data.notes.forEach(function (n) {
        notes.appendChild(node("div", "note", "⚠ " + n));
      });
      answer.parentNode.insertBefore(notes, answer.nextSibling);
    }

    var results = $("results");
    clear(results);
    var list = Array.isArray(data.results) ? data.results : [];
    list.forEach(function (r) {
      renderResultEntry(r, results);
    });
    if (!results.children.length && status !== "not_found" && status !== "empty") {
      results.appendChild(node("p", "muted small", "本次查询没有可展示的证据。"));
    }

    var suggestions = $("query-suggestions");
    clear(suggestions);
    (Array.isArray(data.suggestions) ? data.suggestions : []).slice(0, 4).forEach(function (s) {
      var text = typeof s === "string" ? s : s && (s.text || s.query) ? s.text || s.query : "";
      if (!text) return;
      var chip = node("span", "chip", text);
      chip.onclick = function () {
        $("query-input").value = text;
        runQuery(text);
      };
      suggestions.appendChild(chip);
    });

    logAction("找物查询", "OK · " + (data.latency_ms !== undefined ? data.latency_ms + " ms · " : "") + "状态 " + textOr(data.status, "—"), true);
  }

  function renderResultEntry(r, container) {
    if (!r || typeof r !== "object") return;
    if (Array.isArray(r.events)) {
      r.events.forEach(function (ev) {
        var merged = Object.assign({}, r, ev);
        delete merged.events;
        delete merged.items;
        container.appendChild(buildEvidenceCard(merged));
      });
      return;
    }
    if (Array.isArray(r.items)) {
      r.items.forEach(function (item) {
        var merged = Object.assign({}, r, item);
        delete merged.events;
        delete merged.items;
        if (merged.capture_id === undefined) merged.capture_id = r.capture_id;
        container.appendChild(buildEvidenceCard(merged));
      });
      return;
    }
    if (r.track && typeof r.track === "object") {
      var mergedTrack = Object.assign({}, r.track, r);
      delete mergedTrack.track;
      container.appendChild(buildEvidenceCard(mergedTrack));
      return;
    }
    container.appendChild(buildEvidenceCard(r));
  }

  function buildEvidenceCard(r) {
    var card = node("div", "result");
    var cardSource = r.source_kind !== undefined ? r.source_kind : r.source;

    var thumb = node("div", "thumb");
    var primary = r.evidence_image_url || r.image_url || r.evidence_crop_url || r.crop_url || "";
    if (primary) {
      var img = node("img", "");
      img.src = primary;
      img.alt = textOr(r.label, textOr(r.class_zh, "证据图片"));
      img.loading = "lazy";
      img.onerror = function () {
        img.style.display = "none";
        thumb.appendChild(node("span", "muted small", "图片加载失败"));
      };
      thumb.appendChild(img);
    } else {
      thumb.appendChild(node("span", "muted small", "无图片"));
    }
    card.appendChild(thumb);

    var meta = node("div", "meta");
    meta.appendChild(node("strong", "", textOr(r.label, textOr(r.class_zh, "物品"))));

    var row = node("div", "row");
    row.appendChild(sourceBadge(cardSource));
    row.appendChild(node("span", "badge" + (String(r.link_status) === "ambiguous" ? " warn" : ""), linkStatusLabel(r.link_status)));
    var when = r.time_local || r.time_utc || "";
    var whenText = when
      ? r.time_synced === false
        ? when + "（时间未同步）"
        : when
      : r.time_synced === false
      ? "时间未同步"
      : "时间未知";
    row.appendChild(node("span", "badge dim", whenText));
    row.appendChild(node("span", "badge dim", "置信度 " + pct(r.confidence)));
    row.appendChild(node("span", "badge dim", "区域 " + textOr(r.zone, "未分区")));
    meta.appendChild(row);

    var lines = [];
    if (r.time_ago) lines.push(r.time_ago);
    if (r.link_score !== undefined && r.link_score !== null) lines.push("关联分 " + fmtScore(r.link_score) + " · " + linkStatusLabel(r.link_status));
    if (r.sightings !== undefined && r.sightings !== null) lines.push("共记录 " + r.sightings + " 次");
    lines.forEach(function (line) {
      meta.appendChild(node("div", "", line));
    });
    if (r.uncertainty) meta.appendChild(node("div", "note", "⚠ " + r.uncertainty));

    var crop = r.evidence_crop_url || r.crop_url;
    if (crop && crop !== primary) {
      var cropWrap = node("div", "wb-evidence-crop");
      var cropImg = node("img", "wb-crop");
      cropImg.src = crop;
      cropImg.alt = "裁剪图";
      cropImg.loading = "lazy";
      cropWrap.appendChild(cropImg);
      cropWrap.appendChild(node("span", "muted small", "裁剪图"));
      meta.appendChild(cropWrap);
    }
    card.appendChild(meta);

    var captureId = r.capture_id !== undefined && r.capture_id !== null ? r.capture_id : r.capture && r.capture.id;
    if (captureId !== undefined && captureId !== null) {
      card.style.cursor = "pointer";
      card.onclick = function () {
        showCapture(captureId).then(function () {
          scrollToEl("detection-card");
        });
      };
    }
    return card;
  }

  function scrollToEl(id) {
    var el = $(id);
    if (el && el.scrollIntoView) el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  // ---------------- 验收总览 ----------------
  function loadAcceptance(options) {
    options = options || {};
    if (state.acceptanceInFlight) return Promise.resolve();
    state.acceptanceInFlight = true;
    return api("/api/acceptance", { timeoutMs: STATUS_TIMEOUT_MS })
      .then(function (data) {
        if (!data || data.ok === false) throw new Error(pickError(data, "验收状态读取失败"));
        renderAcceptance(data);
      })
      .catch(function (err) {
        renderAcceptanceFailure(err);
      })
      .finally(function () {
        state.acceptanceInFlight = false;
      });
  }

  function renderAcceptance(data) {
    state.acceptance = data;
    var run = data.run || null;
    var ov = data.overview || {};
    var cls = awardClass(ov.status);

    var statusEl = $("overall-status");
    statusEl.textContent = awardText(ov.status);
    statusEl.className = "wb-big-status " + cls;
    $("overall-section").className = "card wb-banner " + cls;
    $("overall-banner").textContent = textOr(
      ov.banner,
      run ? "本轮验收状态： " + awardText(ov.status) : "尚无验收运行，所有项为 NOT VERIFIED"
    );
    $("overall-title").textContent =
      cls === "pass"
        ? "本轮验收通过（PASS）"
        : cls === "fail"
        ? "本轮验收未通过（FAIL）"
        : run
        ? "本轮验收尚未完成验证（NOT VERIFIED）"
        : "尚无验收运行";

    var counts = ov.counts || {};
    $("overall-counts").textContent =
      "PASS " + numText(counts.pass) + " · FAIL " + numText(counts.fail) + " · NOT VERIFIED " + numText(counts.not_verified);

    var simulatedEl = $("overall-simulated");
    if (ov.simulated === true) {
      simulatedEl.textContent = "simulated：是（包含回放/模拟来源，不能当作真实设备验收证据）";
      simulatedEl.className = "wb-simulated warn";
    } else if (ov.simulated === false) {
      simulatedEl.textContent = "simulated：否（全部来自真实设备数据）";
      simulatedEl.className = "wb-simulated";
    } else {
      simulatedEl.textContent = "simulated：未知";
      simulatedEl.className = "wb-simulated";
    }

    var warnings = $("overall-warnings");
    clear(warnings);
    (Array.isArray(ov.warnings) ? ov.warnings : []).forEach(function (w) {
      if (w === undefined || w === null || w === "") return;
      warnings.appendChild(node("div", "note", "⚠ " + String(w)));
    });

    $("run-info").textContent = formatRunInfo(run);
    $("acceptance-updated").textContent = "更新于 " + textOr(ov.generated_at_utc, clockNow());

    renderAcceptanceItems(Array.isArray(ov.items) ? ov.items : []);
    renderRunControls(run, ov);
    refreshControls();
  }

  function formatRunInfo(run) {
    if (!run) return "尚无验收运行 · 可点击“开始真实设备验收”或“开始回放演示”";
    var parts = [];
    parts.push("本轮 #" + textOr(run.id, "?"));
    parts.push("模式：" + (run.mode === "real_device" ? "真实设备验收" : run.mode === "replay_demo" ? "回放演示" : textOr(run.mode, "未知")));
    parts.push("来源：" + sourceLabel(run.source_kind));
    if (run.source_ref) parts.push("来源标记：" + shortSourceRef(run.source_ref));
    parts.push("开始：" + textOr(run.started_at_utc, "—"));
    parts.push(run.finished_at_utc ? "结束：" + run.finished_at_utc : "状态：进行中");
    if (run.status) parts.push("run.status：" + run.status);
    return parts.join(" · ");
  }

  function renderAcceptanceItems(items) {
    var box = $("acceptance-items");
    clear(box);
    var list = (items || []).filter(Boolean);
    if (!list.length) {
      DEFAULT_ACCEPTANCE_ITEMS.forEach(function (pair) {
        box.appendChild(
          buildAcceptanceRow({
            key: pair[0],
            title: pair[1],
            status: "not_verified",
            reason: "尚无验收运行，所有项为 NOT VERIFIED。",
            evidence: [],
          })
        );
      });
      return;
    }
    var seenKeys = {};
    list.forEach(function (item) {
      seenKeys[String(item.key || "")] = true;
      box.appendChild(buildAcceptanceRow(item));
    });
    // 若后端返回项少于六项，用固定的 NOT VERIFIED 行补齐，避免"六行"缺失。
    if (box.children.length < 6) {
      DEFAULT_ACCEPTANCE_ITEMS.forEach(function (pair) {
        if (box.children.length >= 6) return;
        if (seenKeys[pair[0]]) return;
        box.appendChild(
          buildAcceptanceRow({
            key: pair[0],
            title: pair[1],
            status: "not_verified",
            reason: "后端未返回该验收项结果（NOT VERIFIED）。",
            evidence: [],
          })
        );
      });
    }
  }

  function buildAcceptanceRow(item) {
    var row = node("div", "wb-accept-item");
    var cls = awardClass(item.status);
    row.appendChild(node("span", "wb-status " + cls, awardText(item.status)));

    var body = node("div", "wb-accept-body");
    body.appendChild(node("div", "wb-accept-title", textOr(item.title, textOr(item.key, "验收项"))));
    body.appendChild(node("div", "wb-accept-reason", textOr(item.reason, "未提供理由")));

    var evidence = node("div", "wb-evidence");
    var links = Array.isArray(item.evidence) ? item.evidence : [];
    links.forEach(function (e) {
      if (!e) return;
      var label = [e.label, e.value]
        .filter(function (v) {
          return v !== undefined && v !== null && v !== "";
        })
        .join("：");
      if (!label) label = "证据";
      if (isSafeUrl(e.url)) {
        var a = node("a", "", label);
        a.href = e.url;
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        evidence.appendChild(a);
      } else {
        evidence.appendChild(node("span", "", label));
      }
    });
    if (!evidence.children.length) evidence.appendChild(node("span", "", "无证据链接"));
    body.appendChild(evidence);
    row.appendChild(body);
    return row;
  }

  function renderAcceptanceFailure(err) {
    var msg = errMessage(err);
    state.acceptance = null;
    $("overall-status").textContent = "NOT VERIFIED";
    $("overall-status").className = "wb-big-status nv";
    $("overall-section").className = "card wb-banner nv";
    $("overall-title").textContent = "验收状态读取失败";
    $("overall-banner").textContent = "读取 /api/acceptance 失败：" + msg;
    $("overall-counts").textContent = "PASS — · FAIL — · NOT VERIFIED —";
    $("overall-simulated").textContent = "simulated：未知";
    $("overall-simulated").className = "wb-simulated";
    clear($("overall-warnings"));
    $("run-info").textContent = "验收状态不可用";
    $("acceptance-updated").textContent = "更新失败（" + clockNow() + "）";
    setRunHint("读取验收总览失败：" + msg, true);

    var box = $("acceptance-items");
    clear(box);
    DEFAULT_ACCEPTANCE_ITEMS.forEach(function (pair) {
      box.appendChild(
        buildAcceptanceRow({
          key: pair[0],
          title: pair[1],
          status: "not_verified",
          reason: "读取验收总览失败（NOT VERIFIED）：" + msg,
          evidence: [],
        })
      );
    });
    refreshControls();
  }

  function renderRunControls(run, ov) {
    var running = !!(run && run.status === "running");
    if (!run) {
      setRunHint("尚无验收运行，所有项为 NOT VERIFIED", false);
      return;
    }
    if (running) {
      setRunHint("本轮验收进行中：请完成证据采集后点击“结束本轮验收”。", false);
      return;
    }
    setRunHint(
      "本轮验收已结束：" + awardText(ov && ov.status) + " · 可导出证据 JSON",
      false
    );
  }

  function startRun(mode) {
    var label = mode === "real_device" ? "开始真实设备验收" : "开始回放演示";
    return withBusy(function () {
      logAction(label, "进行中…", null);
      setRunHint("正在启动本轮验收…", false);
      return api("/api/acceptance/run/start", { method: "POST", body: { mode: mode }, timeoutMs: 30000 })
        .then(function (data) {
          if (!data || data.ok === false) throw new Error(pickError(data, "启动验收失败"));
          logAction(label, "OK · 本轮 #" + textOr(data.run && data.run.id, "?"), true);
          toast("本轮验收已开始", true);
          if (data.overview) {
            renderAcceptance({ ok: true, run: data.run || null, overview: data.overview });
          } else {
            return loadAcceptance();
          }
          return loadStatus({ quiet: true });
        })
        .catch(function (err) {
          var msg = "启动验收失败：" + errMessage(err);
          logAction(label, errMessage(err), false);
          setRunHint(msg, true);
          toast(msg, false);
          return loadAcceptance();
        });
    });
  }

  function finishRun() {
    var run = currentRun();
    if (!run || run.id === undefined || run.id === null) {
      setRunHint("没有进行中的验收运行。", true);
      return Promise.resolve();
    }
    return withBusy(function () {
      logAction("结束本轮验收", "进行中…", null);
      return api("/api/acceptance/run/" + encodeURIComponent(run.id) + "/finish", {
        method: "POST",
        body: {},
        timeoutMs: 30000,
      })
        .then(function (data) {
          if (!data || data.ok === false) throw new Error(pickError(data, "结束验收失败"));
          logAction("结束本轮验收", "OK", true);
          toast("本轮验收已结束", true);
          if (data.overview) {
            renderAcceptance({ ok: true, run: data.run || null, overview: data.overview });
          } else {
            return loadAcceptance();
          }
          return loadStatus({ quiet: true });
        })
        .catch(function (err) {
          var msg = "结束验收失败：" + errMessage(err);
          logAction("结束本轮验收", errMessage(err), false);
          setRunHint(msg, true);
          toast(msg, false);
          return loadAcceptance();
        });
    });
  }

  function exportEvidence() {
    var run = currentRun();
    if (!run || run.id === undefined || run.id === null) {
      setRunHint("没有可导出的验收运行。", true);
      logAction("导出证据 JSON", "没有可导出的验收运行", false);
      return;
    }
    var url = "/api/acceptance/run/" + encodeURIComponent(run.id) + "/export";
    var a = document.createElement("a");
    a.href = url;
    a.download = "findy-acceptance-run-" + run.id + ".json";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    logAction("导出证据 JSON", "OK · 已请求下载 " + url, true);
    toast("已请求下载证据 JSON", true);
  }

  // ---------------- 轮询 ----------------
  function pollTick() {
    if (state.pollInFlight) return;
    state.pollInFlight = true;
    loadStatus()
      .then(function () {
        return loadAcceptance();
      })
      .then(function () {
        if (state.autoRunning && !state.captureBusy && !state.busy) {
          return Promise.allSettled([loadLatestCapture(false), loadTracks(true)]);
        }
      })
      .catch(function () {
        /* 各加载函数内部已自行呈现错误 */
      })
      .finally(function () {
        state.pollInFlight = false;
      });
  }

  function updateClock() {
    var el = $("page-clock");
    if (el) el.textContent = dateTimeNow();
  }

  // ---------------- 初始化 ----------------
  function bindEvents() {
    $("probe-btn").onclick = doProbe;
    $("connect-btn").onclick = doConnect;
    $("reset-source-btn").onclick = doResetSource;
    $("capture-btn").onclick = doCapture;
    $("auto-start-btn").onclick = doAutoStart;
    $("auto-stop-btn").onclick = doAutoStop;
    $("run-start-real").onclick = function () {
      startRun("real_device");
    };
    $("run-start-demo").onclick = function () {
      startRun("replay_demo");
    };
    $("run-finish").onclick = finishRun;
    $("export-evidence").onclick = exportEvidence;
    $("query-form").addEventListener("submit", function (e) {
      e.preventDefault();
      runQuery();
    });
    var clearLog = $("clear-log-btn");
    if (clearLog) {
      clearLog.onclick = function () {
        var box = $("action-log");
        clear(box);
        box.appendChild(node("div", "wb-log-empty muted small", "暂无操作记录"));
      };
    }
    var ipInput = $("device-ip");
    if (ipInput) {
      ipInput.addEventListener("input", function () {
        state.deviceIpTouched = true;
      });
    }
  }

  function init() {
    bindEvents();
    renderExampleChips(FALLBACK_EXAMPLES);
    updateClock();
    setInterval(updateClock, 1000);
    refreshControls();
    Promise.allSettled([loadStatus(), loadAcceptance(), loadLatestCapture(true), loadTracks()]).then(function () {
      setInterval(pollTick, POLL_INTERVAL_MS);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();