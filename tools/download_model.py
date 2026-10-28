import os, sys, time
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HOME", r"D:\Findyy\models\hf")
from huggingface_hub import snapshot_download

repo = sys.argv[1] if len(sys.argv) > 1 else "facebook/dinov2-small"
allow = ["*.json", "*.safetensors", "*.txt", "*.model"]
t0 = time.time()
print(f"downloading {repo} from {os.environ['HF_ENDPOINT']} to {os.environ['HF_HOME']}", flush=True)
path = snapshot_download(
    repo_id=repo,
    allow_patterns=allow,
    max_workers=4,
)
print("DONE", path, f"{time.time()-t0:.1f}s", flush=True)
for root, dirs, files in os.walk(path):
    for f in files:
        p = os.path.join(root, f)
        print(f"{os.path.getsize(p)/1e6:8.2f} MB  {os.path.relpath(p, path)}", flush=True)