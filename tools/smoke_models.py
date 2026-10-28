import os, sys, time
os.environ.setdefault("TEMP", r"D:\Findyy\data\tmp")
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from PIL import Image
from findy.config import load_config, REPO_ROOT
from findy.classes import load_catalog
from findy.detector import Owlv2Detector
from findy.embedder import Dinov2Embedder

cfg = load_config()
catalog = load_catalog(cfg.objects_file)
img_path = Path(sys.argv[1])
image = Image.open(img_path).convert("RGB")
print("image", image.size, flush=True)

t0 = time.time()
det = Owlv2Detector(cfg.detector, catalog, REPO_ROOT)
det.load()
print(f"OWLv2 loaded in {time.time()-t0:.1f}s", flush=True)
t0 = time.time()
dets = det.detect(image)
print(f"detect {time.time()-t0:.2f}s -> {len(dets)} detections", flush=True)
for d in dets[:15]:
    print(f"  {d.class_zh:8s} conf={d.confidence:.3f} bbox={[round(v,1) for v in d.bbox_px]}", flush=True)

t0 = time.time()
emb = Dinov2Embedder(cfg.embedder, REPO_ROOT)
emb.load()
print(f"DINOv2 loaded in {time.time()-t0:.1f}s dim={emb.dim}", flush=True)
if dets:
    from findy.imaging import crop_with_margin
    crops = [crop_with_margin(image, d.bbox_px) for d in dets[:3]]
    crops = [c for c in crops if c is not None]
    t0 = time.time()
    vecs = emb.embed(crops)
    print(f"embed {len(crops)} crops in {time.time()-t0:.2f}s shape={vecs.shape}", flush=True)
    print("norms", [round(float((v**2).sum()**0.5), 3) for v in vecs], flush=True)

