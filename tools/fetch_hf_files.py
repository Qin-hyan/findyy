import json, os, sys, time, urllib.request, urllib.error

BASE = "https://hf-mirror.com"
REPO = sys.argv[1]
OUTDIR = sys.argv[2]
FILES = sys.argv[3:]
os.makedirs(OUTDIR, exist_ok=True)

def url_for(repo, fname):
    return f"{BASE}/{repo}/resolve/main/{fname}"

for fname in FILES:
    dest = os.path.join(OUTDIR, fname)
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        print(f"SKIP {fname} ({os.path.getsize(dest)} bytes)", flush=True)
        continue
    url = url_for(REPO, fname)
    tmp = dest + ".part"
    for attempt in range(1, 6):
        try:
            t0 = time.time()
            req = urllib.request.Request(url, headers={"User-Agent": "findy-downloader/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
                total = 0
                while True:
                    chunk = r.read(1024 * 256)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
                    if total % (5 * 1024 * 1024) < 1024 * 256:
                        print(f"  {fname}: {total/1e6:.1f} MB", flush=True)
            os.replace(tmp, dest)
            print(f"OK {fname} {total/1e6:.2f} MB in {time.time()-t0:.1f}s", flush=True)
            break
        except urllib.error.HTTPError as e:
            if e.code == 404 and not fname.startswith(("model", "config")):
                print(f"SKIP404 {fname}", flush=True)
                break
            print(f"RETRY {attempt} {fname}: HTTP {e.code}", flush=True)
            time.sleep(2 * attempt)
        except Exception as e:
            print(f"RETRY {attempt} {fname}: {type(e).__name__}: {e}", flush=True)
            time.sleep(2 * attempt)
    else:
        print(f"FAILED {fname}", flush=True)
        sys.exit(1)
print("ALL DONE", flush=True)