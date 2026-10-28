"""真机验收辅助：用 ESP32 M1 固件抓拍 N 次，走完整 MVP 流水线，输出证据 JSON。

用法（Windows PowerShell）：
    $env:FINDY_CAPTURE_SOURCE='esp32'
    $env:FINDY_ESP32_URL='http://<设备IP>'
    $env:FINDY_DB_PATH='data/hardware.sqlite'
    $env:FINDY_IMAGES_DIR='data/hardware_images'
    $env:FINDY_CROPS_DIR='data/hardware_crops'
    python tools/hardware_acceptance.py --count 6 --interval 4 --out data/hardware_result.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from findy.classes import load_catalog
from findy.config import REPO_ROOT, load_config
from findy.query import answer


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=6)
    parser.add_argument("--interval", type=float, default=4.0)
    parser.add_argument("--out", default=str(REPO_ROOT / "data" / "hardware_result.json"))
    parser.add_argument("--queries", action="store_true", help="抓拍后对识别到的类别执行查询")
    args = parser.parse_args()

    if os.environ.get("FINDY_CAPTURE_SOURCE") != "esp32":
        print("请先设置 FINDY_CAPTURE_SOURCE=esp32 与 FINDY_ESP32_URL", file=sys.stderr)
        return 2

    from findy.api import create_app

    app = create_app(None)
    db = app.state.db
    cfg = app.state.cfg
    catalog = app.state.catalog
    regions = app.state.regions
    service = app.state.service
    pipeline = app.state.pipeline
    pipeline.warmup()

    device = service.source().probe()
    report = {
        "device": {
            "ip": cfg.capture.esp32.base_url,
            "firmware": None,
            "camera": device.get("camera"),
            "wifi": {k: device.get("wifi", {}).get(k) for k in ("connected", "ip", "rssi")},
            "time": device.get("time"),
        },
        "captures": [],
        "queries": [],
    }

    t0 = time.time()
    for i in range(args.count):
        result = service.capture_once()
        row = {
            "ok": result.ok,
            "capture_id": result.capture_id,
            "duplicate": result.duplicate,
            "error": result.error,
            "capture": result.capture,
            "detections": [
                {
                    "class": d["class"],
                    "confidence": d["confidence"],
                    "region": d["region"],
                    "track_id": d["track_id"],
                    "link_status": d["link_status"],
                    "link_score": d["link_score"],
                    "bbox_norm": d["bbox_norm"],
                }
                for d in result.detections
            ],
            "warnings": result.warnings,
            "elapsed_s": round(time.time() - t0, 2),
        }
        report["captures"].append(row)
        classes = "、".join(sorted({d["class"] for d in result.detections})) or "（无）"
        print(f"[{i + 1}/{args.count}] ok={result.ok} detections={len(result.detections)} {classes}", flush=True)
        if i < args.count - 1:
            time.sleep(args.interval)

    stats = db.stats()
    report["stats"] = stats
    report["tracks"] = [
        {
            "id": t["id"],
            "label": t.get("label"),
            "class": t.get("name_zh"),
            "sightings": db.track_sighting_count(int(t["id"])),
            "last_seen_utc": t.get("last_seen_utc"),
            "last_region": t.get("last_region_name"),
        }
        for t in db.list_tracks(limit=50)
    ]

    if args.queries:
        seen = []
        for cap in report["captures"]:
            for d in cap["detections"]:
                if d["class"] not in seen:
                    seen.append(d["class"])
        for cls in seen[:6]:
            q = f"{cls}最后出现在哪里？"
            res = answer(db, cfg, catalog, regions, q)
            report["queries"].append({"query": q, "status": res["status"], "answer": res["answer"]})
            print(f"Q: {q}\nA: {res['answer']}\n", flush=True)
        res = answer(db, cfg, catalog, regions, "桌上都有哪些东西？")
        report["queries"].append({"query": "桌上都有哪些东西？", "status": res["status"], "answer": res["answer"]})
        print(f"Q: 桌上都有哪些东西？\nA: {res['answer']}\n", flush=True)

    out = Path(args.out)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"证据已写入 {out}", flush=True)
    return 0 if all(c["ok"] for c in report["captures"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())