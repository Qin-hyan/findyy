"""实测检测/embedding 在 CPU 上的单帧耗时（写进验收报告，不估算）。"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image

from findy.classes import load_catalog
from findy.config import REPO_ROOT, load_config
from findy.detector import Owlv2Detector
from findy.embedder import Dinov2Embedder
from findy.imaging import crop_with_margin

cfg = load_config()
catalog = load_catalog(cfg.objects_file)
frame_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "demo_frames" / "2026-10-28T10-00-00_demo.jpg"
image = Image.open(frame_path).convert("RGB")

lines = [f"frame={frame_path.name} size={image.size}"]

t0 = time.perf_counter()
detector = Owlv2Detector(cfg.detector, catalog, REPO_ROOT)
detector.load()
lines.append(f"owlv2_load_s={time.perf_counter()-t0:.2f}")

times = []
for _ in range(3):
    t0 = time.perf_counter()
    detections = detector.detect(image)
    times.append(time.perf_counter() - t0)
lines.append(f"owlv2_detect_s={[round(t,2) for t in times]} avg={sum(times)/len(times):.2f} detections={len(detections)}")

t0 = time.perf_counter()
embedder = Dinov2Embedder(cfg.embedder, REPO_ROOT)
embedder.load()
lines.append(f"dinov2_load_s={time.perf_counter()-t0:.2f}")
crops = [c for c in (crop_with_margin(image, d.bbox_px) for d in detections) if c is not None]
t0 = time.perf_counter()
vecs = embedder.embed(crops)
lines.append(f"dinov2_embed_n={len(crops)} total_s={time.perf_counter()-t0:.3f} dim={vecs.shape[1] if len(vecs) else 0}")

text = "\n".join(lines)
Path(__file__).resolve().parent.parent / "data" / "perf_measurements.txt".write_text(text, encoding="utf-8")
print(text)


