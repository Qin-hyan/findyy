import os, sys, urllib.request, shutil
from pathlib import Path

IDS = """000000000139 000000000285 000000000632 000000000724 000000000776 000000000785
000000000802 000000000872 000000000885 000000001000 000000001268 000000001296
000000001353 000000001425 000000001503 000000001532 000000001584 000000001675
000000001761 000000001818 000000001993 000000002006 000000002149 000000002153
000000002157 000000002261 000000002299 000000002431 000000002473 000000002532""".split()

out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "raw_coco"
out.mkdir(parents=True, exist_ok=True)
ok = 0
for i in IDS:
    dest = out / f"{i}.jpg"
    if dest.exists():
        ok += 1
        continue
    url = f"http://images.cocodataset.org/val2017/{i}.jpg"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "FindyMVP/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r, open(dest, "wb") as f:
            shutil.copyfileobj(r, f)
        ok += 1
        print("OK", i, dest.stat().st_size, flush=True)
    except Exception as e:
        print("MISS", i, type(e).__name__, e, flush=True)
print(f"downloaded {ok}/{len(IDS)}")
