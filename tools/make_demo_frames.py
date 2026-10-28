"""生成演示用抓拍序列。

重要：演示数据来自公开 COCO val2017 图片（000000001503.jpg，书桌场景），
使用亮度/平移/轻微旋转等变换模拟"不同时间、不同取景"的抓拍，**不是真实设备录像**。
同一张底图里的物体在变换后仍是同一批实物，可以用来验证：
- 跨帧检测是否稳定；
- 同一实物能否被外观 embedding 关联到同一条轨迹；
- 物体在画面中移动后，"位置变化"查询是否成立。
真实硬件采集路径由 ESP32 适配器承担，需设备在线时验证。
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance

COCO_URL = "http://images.cocodataset.org/val2017/000000001503.jpg"

FRAMES = [
    # (时间, 水平位移占宽比例, 垂直位移, 亮度, 对比度, 旋转角度)
    ("10-00-00", 0.00, 0.00, 1.00, 1.00, 0.0),
    ("10-05-00", 0.18, 0.00, 1.06, 1.02, 0.6),
    ("10-10-00", 0.34, 0.01, 0.92, 1.05, -0.8),
    ("10-15-00", -0.10, 0.00, 1.02, 0.98, 0.0),
    ("10-20-00", 0.40, -0.01, 1.10, 1.03, 1.0),
    ("10-25-00", 0.05, 0.01, 0.96, 1.00, -0.5),
]


def shift(image: Image.Image, dx_ratio: float, dy_ratio: float) -> Image.Image:
    w, h = image.size
    dx, dy = int(w * dx_ratio), int(h * dy_ratio)
    canvas = Image.new("RGB", (w, h), (18, 20, 24))
    canvas.paste(image, (dx, dy))
    return canvas


def main() -> int:
    base = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(r"D:\Findyy\data\raw_coco\000000001503.jpg")
    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(r"D:\Findyy\data\demo_frames")
    day = sys.argv[3] if len(sys.argv) > 3 else "2026-10-28"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not base.exists():
        base.parent.mkdir(parents=True, exist_ok=True)
        print(f"底图不存在，下载公开演示图：{COCO_URL}", flush=True)
        req = urllib.request.Request(COCO_URL, headers={"User-Agent": "FindyMVP/0.1"})
        with urllib.request.urlopen(req, timeout=60) as r, open(base, "wb") as f:
            f.write(r.read())
    for f in out_dir.glob("*.jpg"):
        f.unlink()
    image = Image.open(base).convert("RGB")
    # 放大 2 倍再输出，避免 320x240 的公开底图在页面里过糊（不改变语义）
    image = image.resize((image.width * 2, image.height * 2), Image.Resampling.LANCZOS)
    for stamp, dx, dy, bright, contrast, angle in FRAMES:
        frame = shift(image, dx, dy)
        if angle:
            frame = frame.rotate(angle, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(18, 20, 24))
        frame = ImageEnhance.Brightness(frame).enhance(bright)
        frame = ImageEnhance.Contrast(frame).enhance(contrast)
        name = f"{day}T{stamp}_demo.jpg"
        frame.save(out_dir / name, format="JPEG", quality=92)
        print("wrote", out_dir / name, frame.size, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())