"""生成单文件 HTML 可视化报告：把 SQLite 里的抓拍/检测/轨迹渲染成可交互页面。

产物完全自包含（图片以 base64 内嵌），双击即可离线打开，不需要起服务。

用法：
    python tools/make_visual_report.py                 # 默认读 data/findy.sqlite
    python tools/make_visual_report.py --db data/demo.sqlite --out docs/evidence/demo_visual.html
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]


def rel(path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else ROOT / p


def frame_data_uri(path: Path) -> str:
    """原图已经是 JPEG，直接内嵌，不重编码。"""
    raw = path.read_bytes()
    return "data:image/jpeg;base64," + base64.b64encode(raw).decode("ascii")


def crop_data_uri(path: Path, max_side: int = 180, quality: int = 72) -> str:
    """缩略图：控制 HTML 体积，同时保证细节可辨认。"""
    with Image.open(path) as im:
        im = im.convert("RGB")
        im.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        im.save(buf, format="JPEG", quality=quality)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")


def parse_bbox(text: str) -> list[float]:
    return [round(float(v), 4) for v in text.split(",")]


def fmt_time(c: sqlite3.Row) -> str:
    if c["captured_at_local"]:
        return c["captured_at_local"]
    if c["captured_at_utc"]:
        return c["captured_at_utc"].replace("T", " ").replace("Z", " UTC")
    return "时间未知"


def load(db_path: Path) -> dict:
    if not db_path.exists():
        raise SystemExit(f"数据库不存在：{db_path}")

    db = sqlite3.connect(db_path)
    db.row_factory = sqlite3.Row

    cam = db.execute("SELECT * FROM cameras ORDER BY id LIMIT 1").fetchone()
    regions = [
        {"id": r["id"], "name": r["name"], "poly": json.loads(r["polygon_norm"])}
        for r in db.execute("SELECT * FROM regions ORDER BY id")
    ]

    caps = db.execute("SELECT * FROM captures ORDER BY id").fetchall()
    if not caps:
        raise SystemExit("数据库里还没有抓拍，先用 findy capture / replay / serve 采集一批数据。")

    # 同一张图片可能被采集成多条抓拍（重放/幂等边界），图片只内嵌一次
    uri_cache: dict[str, str] = {}
    captures = []
    for c in caps:
        p = rel(c["file_path"])
        if not p.exists():
            continue
        key = str(p)
        if key not in uri_cache:
            uri_cache[key] = frame_data_uri(p)
        captures.append(
            {
                "id": c["id"],
                "time": fmt_time(c),
                "synced": bool(c["time_synced"]),
                "timeSource": c["time_source"],
                "w": c["image_width"],
                "h": c["image_height"],
                "image": key,
                "detections": c["detections_count"],
                "status": c["status"],
            }
        )
    if not captures:
        raise SystemExit("抓拍记录存在，但图片文件都不在本地，未生成报告。")

    # 图片地址单独给一份，避免重复
    images = uri_cache

    det_rows = db.execute(
        """SELECT d.id, d.capture_id, d.track_id, d.region_name, d.bbox_norm, d.conf,
                  d.crop_path, d.color_hex, d.link_score, d.link_method, d.link_status,
                  d.captured_at_utc, oc.name_zh AS label
           FROM detections d JOIN object_classes oc ON oc.id = d.class_id
           ORDER BY d.id"""
    ).fetchall()

    detections = []
    for d in det_rows:
        item = {
            "id": d["id"],
            "capture": d["capture_id"],
            "track": d["track_id"],
            "label": d["label"],
            "region": d["region_name"],
            "bbox": parse_bbox(d["bbox_norm"]),
            "conf": round(float(d["conf"]), 4),
            "score": round(float(d["link_score"] or 0.0), 4),
            "status": d["link_status"] or "new",
            "method": d["link_method"] or "new",
            "colorHex": d["color_hex"],
            "time": (d["captured_at_utc"] or "").replace("T", " ").replace("Z", ""),
            "crop": None,
        }
        cp = rel(d["crop_path"]) if d["crop_path"] else None
        if cp and cp.exists():
            item["crop"] = crop_data_uri(cp)
        detections.append(item)

    # 轨迹汇总：出现帧数、平均关联分、首末时间、位置
    tracks = []
    tracks_raw = db.execute(
        """SELECT t.id, t.label, t.color, t.color_hex, t.status, t.last_region_id
           FROM tracks t ORDER BY t.id"""
    ).fetchall()
    for t in tracks_raw:
        ds = [d for d in detections if d["track"] == t["id"]]
        scores = [d["score"] for d in ds if d["score"] > 0]
        region = None
        if t["last_region_id"]:
            region = next((r["name"] for r in regions if r["id"] == t["last_region_id"]), None)
        tracks.append(
            {
                "id": t["id"],
                "label": t["label"],
                "color": t["color"],
                "colorHex": t["color_hex"],
                "status": t["status"],
                "region": region,
                "sightings": len(ds),
                "frames": len({d["capture"] for d in ds}),
                "avgScore": round(sum(scores) / len(scores), 3) if scores else None,
                "first": d0["time"] if ds and (d0 := min(ds, key=lambda d: d["id"])) else None,
                "last": d0["time"] if ds and (d0 := max(ds, key=lambda d: d["id"])) else None,
            }
        )

    status_count: dict[str, int] = {}
    for d in detections:
        status_count[d["status"]] = status_count.get(d["status"], 0) + 1

    n_matched = status_count.get("matched", 0)
    n_total = len(detections)
    return {
        "generatedAt": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "title": "Findy 物品记忆 · 可视化报告",
        "camera": {
            "name": cam["name"] if cam else "unknown",
            "source": cam["source"] if cam else "?",
            "model": cam["model"] if cam else "",
            "tz": cam["tz_name"] if cam else "Asia/Shanghai",
        },
        "db": str(db_path),
        "regions": regions,
        "captures": captures,
        "images": images,
        "tracks": tracks,
        "detections": detections,
        "stats": {
            "captures": len(captures),
            "detections": n_total,
            "tracks": len(tracks),
            "matched": n_matched,
            "ambiguous": status_count.get("ambiguous", 0),
            "new": status_count.get("new", 0),
            "matchRate": round(n_matched / n_total, 3) if n_total else 0.0,
        },
    }


TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
  :root{
    --bg:#0e1014; --panel:#151922; --panel-2:#1b202b; --line:#242b38;
    --text:#dfe5ee; --muted:#8b94a3; --accent:#4da3ff;
    --ok:#3ecf8e; --warn:#f0b429; --bad:#ff6b6b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--text);
       font:14px/1.55 "Segoe UI","Microsoft YaHei",system-ui,sans-serif}
  header{padding:18px 24px;border-bottom:1px solid var(--line);
         display:flex;flex-wrap:wrap;gap:28px;align-items:flex-end}
  h1{font-size:18px;margin:0;font-weight:600}
  .sub{color:var(--muted);font-size:12px;margin-top:3px}
  .kpis{display:flex;gap:30px;flex-wrap:wrap;margin-left:auto}
  .kpi b{display:block;font-size:22px;line-height:1.2}
  .kpi span{font-size:12px;color:var(--muted)}
  .kpi.rate b{color:var(--ok)}
  main{display:grid;grid-template-columns:minmax(0,1fr) 330px;gap:18px;padding:18px 24px 8px}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px}
  .card h2{font-size:13px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);
           margin:0;padding:12px 14px;border-bottom:1px solid var(--line);font-weight:600}
  .stage{position:relative;overflow:hidden;border-radius:10px 10px 0 0;background:#000;line-height:0}
  .stage img{display:block;width:100%;height:auto}
  .zone{position:absolute;top:0;bottom:0;border-left:1px dashed rgba(120,200,255,.35);pointer-events:none}
  .zone-label{position:absolute;top:0;pointer-events:none}
  .zone-label span{position:absolute;top:6px;left:0;transform:translateX(-50%);white-space:nowrap;
             font-size:11px;color:rgba(180,220,255,.85);background:rgba(6,10,16,.6);
             padding:1px 7px;border-radius:4px;line-height:1.4;border:1px solid rgba(120,200,255,.25)}
  .box{position:absolute;border:2px solid var(--accent);border-radius:4px;cursor:pointer;
       line-height:1.4;transition:box-shadow .12s,background .12s}
  .box.matched{border-style:solid}
  .box.ambiguous{border-style:dashed;border-color:var(--warn)}
  .box.new{border-style:dotted;border-color:var(--bad)}
  .box.dim{opacity:.18}
  .box.hit{box-shadow:0 0 0 2px #fff inset,0 0 12px rgba(255,255,255,.55);background:rgba(255,255,255,.10)}
  .box b{position:absolute;left:-2px;bottom:100%;margin-bottom:2px;display:flex;gap:5px;align-items:center;
         background:rgba(9,12,18,.88);border:1px solid var(--line);border-radius:4px;padding:1px 6px;
         font-size:11px;font-weight:600;white-space:nowrap;color:#fff}
  .box b i{width:7px;height:7px;border-radius:50%;display:inline-block}
  .box b.in{bottom:auto;top:0;margin-top:-2px}
  .box b.right{left:auto;right:-2px}
  .strip{display:flex;gap:8px;padding:10px 12px;overflow-x:auto;border-top:1px solid var(--line)}
  .thumb{flex:0 0 auto;width:96px;border:2px solid transparent;border-radius:6px;overflow:hidden;
         cursor:pointer;background:#000;opacity:.6;transition:opacity .12s,border-color .12s}
  .thumb:hover{opacity:1}
  .thumb.on{opacity:1;border-color:var(--accent)}
  .thumb img{display:block;width:100%;height:auto}
  .thumb span{display:block;font-size:10px;color:var(--muted);text-align:center;padding:2px 0}
  aside{display:flex;flex-direction:column;gap:18px;min-width:0}
  .tracks{max-height:300px;overflow:auto}
  .track{display:flex;align-items:center;gap:10px;padding:9px 14px;border-bottom:1px solid var(--line);
         cursor:pointer}
  .track:last-child{border-bottom:0}
  .track:hover,.track.on{background:var(--panel-2)}
  .dot{width:10px;height:10px;border-radius:50%;flex:0 0 auto}
  .track .name{font-weight:600}
  .track .meta{font-size:11px;color:var(--muted)}
  .track .pct{margin-left:auto;font-size:12px;color:var(--ok)}
  .detail{padding:14px;min-height:210px}
  .detail img{width:100%;max-height:150px;object-fit:contain;background:#0a0d12;border-radius:6px}
  .detail .empty{color:var(--muted);font-size:13px}
  .kv{display:grid;grid-template-columns:78px 1fr;gap:3px 8px;margin-top:10px;font-size:12px}
  .kv dt{color:var(--muted)}
  .kv dd{margin:0}
  .pill{display:inline-block;padding:0 7px;border-radius:99px;font-size:11px;line-height:18px}
  .pill.matched{background:rgba(62,207,142,.15);color:var(--ok)}
  .pill.ambiguous{background:rgba(240,180,41,.15);color:var(--warn)}
  .pill.new{background:rgba(255,107,107,.15);color:var(--bad)}
  .matrix-wrap{padding:0 24px 18px}
  table.matrix{width:100%;border-collapse:collapse;font-size:12px}
  table.matrix th,table.matrix td{padding:5px 6px;border-bottom:1px solid var(--line);text-align:center}
  table.matrix th{color:var(--muted);font-weight:500}
  table.matrix th:first-child,table.matrix td:first-child{text-align:left;white-space:nowrap}
  td.cell{cursor:pointer;border-radius:4px}
  td.cell:hover{outline:1px solid var(--accent)}
  td.cell i{display:block;width:100%;height:16px;border-radius:3px;background:#1d2430}
  td.cell.on i{outline:2px solid #fff}
  .bar{display:flex;gap:10px;align-items:center;padding:4px 0;font-size:12px}
  .bar .lbl{width:64px;color:var(--muted)}
  .bar .track-line{flex:1;height:8px;border-radius:99px;background:#1d2430;overflow:hidden}
  .bar .track-line i{display:block;height:100%;border-radius:99px;background:var(--accent)}
  .bar .val{width:48px;text-align:right;color:var(--muted)}
  .legend{display:flex;gap:16px;flex-wrap:wrap;padding:10px 14px;font-size:12px;color:var(--muted)}
  .legend s{text-decoration:none}
  .legend .sw{display:inline-block;width:14px;height:10px;border:2px solid var(--accent);border-radius:2px;
              margin-right:5px;vertical-align:-1px}
  footer{padding:8px 24px 22px;color:#6b7482;font-size:11px}
  @media (max-width:1080px){ main{grid-template-columns:1fr} }
</style>
</head>
<body>
<header>
  <div>
    <h1>__TITLE__</h1>
    <div class="sub">相机 __CAMERA__ · 数据源 __SOURCE__ · 生成于 __GENERATED__</div>
  </div>
  <div class="kpis" id="kpis"></div>
</header>

<main>
  <section class="card" style="overflow:hidden">
    <div class="stage" id="stage">
      <img id="frame" alt="抓拍画面">
      <div id="zones"></div>
      <div id="boxes"></div>
    </div>
    <div class="strip" id="strip"></div>
    <div class="legend">
      <span><i class="sw" style="border-style:solid"></i>已关联</span>
      <span><i class="sw" style="border-style:dashed;border-color:var(--warn)"></i>不确定</span>
      <span><i class="sw" style="border-style:dotted;border-color:var(--bad)"></i>新物体</span>
      <span>虚线竖线 = 区域边界</span>
    </div>
  </section>

  <aside>
    <div class="card">
      <h2>轨迹（同一物理物品）</h2>
      <div class="tracks" id="tracks"></div>
    </div>
    <div class="card">
      <h2>检测详情</h2>
      <div class="detail" id="detail"><div class="empty">点选画面中的检测框，或点击右侧轨迹。</div></div>
    </div>
  </aside>
</main>

<div class="matrix-wrap">
  <div class="card">
    <h2>轨迹 × 抓拍 出现矩阵（颜色越亮关联分越高，点击跳转）</h2>
    <table class="matrix" id="matrix"></table>
  </div>
</div>

<div class="matrix-wrap" style="display:grid;grid-template-columns:1fr 1fr;gap:18px">
  <div class="card">
    <h2>区域分布（按检测数）</h2>
    <div style="padding:8px 14px" id="regionBars"></div>
  </div>
  <div class="card">
    <h2>关联状态</h2>
    <div style="padding:8px 14px" id="statusBars"></div>
  </div>
</div>

<footer id="foot"></footer>

<script>
const DATA = __DATA__;

const PALETTE = ["#4da3ff","#f0b429","#3ecf8e","#e06c9f","#9b7ff0","#f2764b","#38bdf8","#a3e635","#fb7185","#c084fc"];
const caps = DATA.captures.slice().sort((a,b)=>a.id-b.id);
const dets = DATA.detections;
const tracks = DATA.tracks;
const pal = {};
tracks.forEach((t,i)=>pal[t.id]=PALETTE[i%PALETTE.length]);

let curId = caps[caps.length-1].id;
let selectedDet = null;
let tracked = null;   // 当前聚焦的轨迹

const $ = (id)=>document.getElementById(id);

function selectDet(id){
  selectedDet = id;
  const d = dets.find(x=>x.id===id);
  if(d){ tracked = d.track; }
  renderAll();
}

/* 聚焦一条轨迹：优先选中当前帧里的那条检测，否则跳到它最近一次出现 */
function focusTrack(id){
  tracked = id;
  const own = dets.filter(x=>x.track===id);
  if(!own.length){ selectedDet = null; return; }
  const here = own.find(x=>x.capture===curId) || own[own.length-1];
  curId = here.capture;
  selectedDet = here.id;
}

function byCapture(cid){ return dets.filter(d=>d.capture===cid); }
function capIndex(cid){ return caps.findIndex(c=>c.id===cid); }

/* ---------- 顶部 KPI ---------- */
(function kpis(){
  const s = DATA.stats;
  const items = [
    [s.captures,"抓拍帧数"],
    [s.detections,"检测总数"],
    [s.tracks,"轨迹数"],
    [Math.round(s.matchRate*100)+"%","已关联比例"],
  ];
  $("kpis").innerHTML = items.map(([v,k])=>`<div class="kpi${k==="已关联比例"?" rate":""}"><b>${v}</b><span>${k}</span></div>`).join("");
})();

/* ---------- 区域分隔线 ---------- */
(function zones(){
  const out = [];
  // 区域名居中显示
  DATA.regions.forEach(r=>{
    const xs = r.poly.map(p=>p[0]);
    const x = (Math.min(...xs)+Math.max(...xs))/2;
    out.push(`<div class="zone-label" style="left:${(x*100).toFixed(2)}%"><span>${r.name}</span></div>`);
  });
  // 区域边界虚线
  const xs = [...new Set(DATA.regions.flatMap(r=>r.poly.map(p=>p[0])))].sort((a,b)=>a-b);
  xs.slice(1,-1).forEach(x=>out.push(`<div class="zone" style="left:${(x*100).toFixed(2)}%"></div>`));
  $("zones").innerHTML = out.join("");
})();

/* ---------- 画面 + 检测框 ---------- */
function renderStage(){
  const cap = caps.find(c=>c.id===curId);
  $("frame").src = DATA.images[cap.image];
  const list = byCapture(curId);
  $("boxes").innerHTML = list.map(d=>{
    const [x1,y1,x2,y2] = d.bbox;
    const dim = tracked && d.track!==tracked ? " dim" : "";
    const hit = selectedDet===d.id ? " hit" : "";
    const cls = y1 < 0.08 ? " in" : "";
    return `<div class="box ${d.status}${dim}${hit}" data-det="${d.id}"
      style="left:${x1*100}%;top:${y1*100}%;width:${(x2-x1)*100}%;height:${(y2-y1)*100}%;border-color:${pal[d.track]||"#4da3ff"}">
      <b class="${(x1>0.72?"right ":"")+cls}"><i style="background:${pal[d.track]||"#4da3ff"}"></i>${d.label} · ${(d.conf*100).toFixed(0)}%</b>
    </div>`;
  }).join("");
  document.querySelectorAll(".box").forEach(el=>{
    el.addEventListener("click",(ev)=>{ ev.stopPropagation(); selectDet(+el.dataset.det); });
  });
  if(selectedDet!==null){
    const d = dets.find(d=>d.id===selectedDet);
    if(!d || d.capture!==curId){ selectedDet = null; renderDetail(); }
  }
}

/* ---------- 抓拍胶片条 ---------- */
function renderStrip(){
  $("strip").innerHTML = caps.map((c,i)=>{
    const label = c.time.length>16 ? c.time.slice(11,16) : c.time;
    return `<div class="thumb${c.id===curId?" on":""}" data-cap="${c.id}" title="${c.time} · ${c.timeSource}">
      <img src="${DATA.images[c.image]}" alt="">
      <span>#${c.id} ${label}</span>
    </div>`;
  }).join("");
  document.querySelectorAll(".thumb").forEach(el=>{
    el.addEventListener("click",()=>{ curId=+el.dataset.cap; selectedDet=null; renderAll(); });
  });
}

/* ---------- 轨迹列表 ---------- */
function renderTracks(){
  $("tracks").innerHTML = tracks.map(t=>{
    const pct = t.avgScore!==null ? Math.round(t.avgScore*100)+"%" : "新";
    return `<div class="track${tracked===t.id?" on":""}" data-track="${t.id}">
      <span class="dot" style="background:${pal[t.id]}"></span>
      <div>
        <div class="name">${t.label}${t.color?` · ${t.color}`:""}</div>
        <div class="meta">出现 ${t.frames}/${DATA.stats.captures} 帧 · ${t.sightings} 次 · ${t.region||"未知区域"}</div>
      </div>
      <span class="pct">${pct}</span>
    </div>`;
  }).join("");
  document.querySelectorAll(".track").forEach(el=>{
    el.addEventListener("click",()=>{
      const id = +el.dataset.track;
      if(tracked===id){ tracked = null; } else { focusTrack(id); }
      renderAll();
    });
  });
}

/* ---------- 详情 ---------- */
function renderDetail(){
  const d = selectedDet!==null ? dets.find(x=>x.id===selectedDet) : null;
  if(!d){ $("detail").innerHTML = `<div class="empty">点选画面中的检测框，或点击右侧轨迹。</div>`; return; }
  const t = tracks.find(x=>x.id===d.track);
  const pct = d.score>0 ? (d.score*100).toFixed(1)+"%" : "—";
  $("detail").innerHTML = `
    ${d.crop?`<img src="${d.crop}" alt="${d.label}">`:""}
    <dl class="kv">
      <dt>物品</dt><dd>${d.label}</dd>
      <dt>所属轨迹</dt><dd>#${d.track} ${t?`· 出现 ${t.frames} 帧`:""}</dd>
      <dt>检测置信度</dt><dd>${(d.conf*100).toFixed(1)}%</dd>
      <dt>关联分</dt><dd>${pct}</dd>
      <dt>关联状态</dt><dd><span class="pill ${d.status}">${statusText(d.status)}</span></dd>
      <dt>位置</dt><dd>${d.region||"未知"}</dd>
      <dt>时间</dt><dd>${d.time||"未同步"}</dd>
    </dl>`;
}
function statusText(s){ return s==="matched"?"已关联":s==="ambiguous"?"不确定":"新物体"; }

/* ---------- 出现矩阵 ---------- */
function renderMatrix(){
  const rows = tracks.map(t=>{
    const cells = caps.map(c=>{
      const d = dets.find(x=>x.capture===c.id && x.track===t.id);
      let bg = "#1d2430", txt="";
      if(d){
        const a = d.score>0 ? 0.35+0.65*d.score : 0.18;
        bg = `rgba(77,163,255,${a.toFixed(2)})`;
        txt = d.score>0 ? (d.score*100).toFixed(0) : "新";
      }
      const on = d && d.id===selectedDet ? " on" : "";
      return `<td class="cell${on}" data-det="${d?d.id:""}" data-cap="${c.id}"><i style="background:${bg}" title="${d?t.label+' · '+(d.score>0?(d.score*100).toFixed(1)+'%':'新物体'):'未出现'}">${txt}</i></td>`;
    }).join("");
    return `<tr><th>${t.label}${t.color?` · ${t.color}`:""}</th>${cells}</tr>`;
  }).join("");
  $("matrix").innerHTML =
    `<tr><th>轨迹 \\ 抓拍</th>${caps.map(c=>`<th>#${c.id} ${c.time.slice(11,16)}</th>`).join("")}</tr>` + rows;
  document.querySelectorAll("td.cell").forEach(el=>{
    el.addEventListener("click",()=>{
      curId = +el.dataset.cap;
      selectedDet = el.dataset.det ? +el.dataset.det : null;
      tracked = selectedDet!==null ? dets.find(d=>d.id===selectedDet).track : tracked;
      renderAll();
    });
  });
}

/* ---------- 分布条 ---------- */
function renderBars(){
  const reg = {};
  dets.forEach(d=>{ const k=d.region||"未知区域"; reg[k]=(reg[k]||0)+1; });
  const max = Math.max(1,...Object.values(reg));
  $("regionBars").innerHTML = Object.entries(reg).sort((a,b)=>b[1]-a[1]).map(([k,v])=>
    `<div class="bar"><span class="lbl">${k}</span>
      <span class="track-line"><i style="width:${(v/max*100).toFixed(0)}%"></i></span>
      <span class="val">${v}</span></div>`).join("") || `<div class="empty">暂无数据</div>`;

  const st = [["matched","已关联","var(--ok)"],["ambiguous","不确定","var(--warn)"],["new","新物体","var(--bad)"]];
  const total = Math.max(1,DATA.stats.detections);
  $("statusBars").innerHTML = st.map(([k,label,color])=>
    `<div class="bar"><span class="lbl">${label}</span>
      <span class="track-line"><i style="width:${(DATA.stats[k]/total*100).toFixed(0)}%;background:${color}"></i></span>
      <span class="val">${DATA.stats[k]}</span></div>`).join("");
}

function renderAll(){
  renderStage(); renderStrip(); renderTracks(); renderDetail(); renderMatrix();
}

/* ---------- 深链：visual_report.html#cap=3&det=12 直接打开某一帧/某个检测 ---------- */
(function applyHash(){
  const h = new URLSearchParams(location.hash.slice(1));
  const c = +(h.get("cap")||0), d = +(h.get("det")||0), t = +(h.get("track")||0);
  if(c && caps.some(x=>x.id===c)) curId = c;
  if(d && dets.some(x=>x.id===d)){
    selectedDet = d; tracked = dets.find(x=>x.id===d).track; curId = dets.find(x=>x.id===d).capture;
  } else if(t && tracks.some(x=>x.id===t)){
    focusTrack(t);
  }
})();

renderBars();
renderAll();
$("foot").textContent = `数据：${DATA.db} · 相机时区 ${DATA.camera.tz} · 本页由 tools/make_visual_report.py 生成，图片内嵌，可离线打开。`;
</script>
</body>
</html>
"""


def build(db_path: Path, out_path: Path) -> None:
    payload = load(db_path)
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    html = (
        TEMPLATE.replace("__TITLE__", payload["title"])
        .replace("__CAMERA__", f'{payload["camera"]["name"]}（{payload["camera"]["model"] or payload["camera"]["source"]}）')
        .replace("__SOURCE__", payload["camera"]["source"])
        .replace("__GENERATED__", payload["generatedAt"])
        .replace("__DATA__", data)
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html, encoding="utf-8")
    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"已生成 {out_path}  ({size_mb:.2f} MB, 抓拍 {len(payload['captures'])} / 检测 {len(payload['detections'])} / 轨迹 {len(payload['tracks'])})")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="生成 Findy 单文件 HTML 可视化报告")
    ap.add_argument("--db", default=str(ROOT / "data" / "findy.sqlite"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "evidence" / "visual_report.html"))
    args = ap.parse_args(argv)
    build(Path(args.db), Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())