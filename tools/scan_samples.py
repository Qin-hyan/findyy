import json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image

from findy.classes import load_catalog
from findy.config import load_config, REPO_ROOT
from findy.detector import Owlv2Detector

cfg = load_config()
catalog = load_catalog(cfg.objects_file)
det = Owlv2Detector(cfg.detector, catalog, REPO_ROOT)
det.load()
src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "raw_coco"
out_path = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "data" / "raw_coco" / "_scan.json"
results = {}
for p in sorted(src.glob("*.jpg")):
    t0 = time.time()
    try:
        dets = det.detect(Image.open(p).convert("RGB"))
    except Exception as e:
        print("ERR", p.name, e, flush=True)
        continue
    dt = time.time() - t0
    results[p.name] = [
        {"class": d.class_zh, "conf": round(d.confidence, 3), "bbox": [round(v, 1) for v in d.bbox_px]}
        for d in dets
    ]
    summary = ", ".join(f"{d['class']}:{d['conf']}" for d in results[p.name][:8]) or "(none)"
    print(f"{p.name} {dt:4.1f}s -> {summary}", flush=True)
out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
print("saved", out_path, flush=True)


