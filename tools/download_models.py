"""统一下载 Findy 所需的两个本地模型（OWLv2 检测 + DINOv2 实例特征）。

用法：
    python tools/download_models.py                # 默认下载到 models/
    python tools/download_models.py --out D:\\models

网络受限时自动使用 hf-mirror.com；下载完成后可用 tools/smoke_models.py 自检。
模型许可：OWLv2（Apache-2.0，HuggingFace 实现）、DINOv2（官方 model card 标注 Apache-2.0）。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

MIRROR = os.environ.get("HF_ENDPOINT", "https://hf-mirror.com").rstrip("/")
OFFICIAL = "https://huggingface.co"

MODELS = {
    "owlv2-base": {
        "repo": "google/owlv2-base-patch16-ensemble",
        "files": [
            "config.json",
            "preprocessor_config.json",
            "tokenizer.json",
            "tokenizer_config.json",
            "vocab.json",
            "merges.txt",
            "special_tokens_map.json",
            "model.safetensors",
        ],
    },
    "dinov2-small": {
        "repo": "facebook/dinov2-small",
        "files": ["config.json", "preprocessor_config.json", "model.safetensors"],
    },
}


def download(repo: str, fname: str, dest: Path, retries: int = 4) -> None:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"SKIP {dest.name} ({dest.stat().st_size} bytes)")
        return
    last_error: Exception | None = None
    for base in (MIRROR, OFFICIAL):
        url = f"{base}/{repo}/resolve/main/{fname}"
        for attempt in range(1, retries + 1):
            try:
                tmp = dest.with_suffix(dest.suffix + ".part")
                req = urllib.request.Request(url, headers={"User-Agent": "findy-downloader/1.0"})
                with urllib.request.urlopen(req, timeout=120) as r, open(tmp, "wb") as f:
                    while True:
                        chunk = r.read(1024 * 256)
                        if not chunk:
                            break
                        f.write(chunk)
                tmp.replace(dest)
                print(f"OK   {dest.name} <- {base} ({dest.stat().st_size/1e6:.1f} MB)")
                return
            except urllib.error.HTTPError as exc:
                if exc.code == 404:
                    print(f"SKIP {fname} (404)")
                    return
                last_error = exc
            except Exception as exc:  # noqa: BLE001
                last_error = exc
            time.sleep(min(8, attempt * 2))
    raise RuntimeError(f"下载失败 {repo}/{fname}: {last_error}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(Path(__file__).resolve().parent.parent / "models"))
    parser.add_argument("--only", default=None, help="只下载某个模型（owlv2-base / dinov2-small）")
    args = parser.parse_args()
    out_root = Path(args.out)
    for name, spec in MODELS.items():
        if args.only and args.only != name:
            continue
        target = out_root / name
        target.mkdir(parents=True, exist_ok=True)
        print(f"== {name} ({spec['repo']}) -> {target}")
        for fname in spec["files"]:
            download(spec["repo"], fname, target / fname)
    print("\n全部完成。自检：python tools/smoke_models.py <任意图片>")
    return 0


if __name__ == "__main__":
    sys.exit(main())