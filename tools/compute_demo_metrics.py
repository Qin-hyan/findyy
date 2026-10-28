"""从回放结果计算演示数据上的检测/关联统计（如实输出，不修饰）。"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data" / "demo_replay_default.json"
frames = json.loads(path.read_text(encoding="utf-8"))

per_frame = []
class_frames: dict[str, list[dict]] = defaultdict(list)
track_ids: dict[str, set[int]] = defaultdict(set)
link_counts = defaultdict(int)
status_counts = defaultdict(int)

for idx, frame in enumerate(frames, 1):
    counts = defaultdict(int)
    for d in frame["detections"]:
        counts[d["class"]] += 1
        class_frames[d["class"]].append({"frame": idx, "track": d["track_id"], "status": d["link_status"], "score": d["link_score"]})
        track_ids[d["class"]].add(d["track_id"])
        link_counts[d["link_status"]] += 1
        status_counts[d["link_status"]] += 1
    per_frame.append({"frame": idx, "detections": len(frame["detections"]), "classes": dict(counts)})

out = {
    "source": str(path),
    "frames": len(frames),
    "total_detections": sum(f["detections"] for f in per_frame),
    "detections_per_frame": [f["detections"] for f in per_frame],
    "per_frame": per_frame,
    "link_status_counts": dict(link_counts),
    "classes": {},
}
for cls, rows in class_frames.items():
    # 每个类别：出现在几帧、创建了几个 track、其中同一 track 覆盖了多少帧
    by_track = defaultdict(list)
    for r in rows:
        by_track[r["track"]].append(r["frame"])
    best_track = max(by_track.items(), key=lambda kv: len(kv[1]))
    out["classes"][cls] = {
        "frames_present": sorted({r["frame"] for r in rows}),
        "tracks": sorted(by_track),
        "track_frame_counts": {str(k): len(v) for k, v in by_track.items()},
        "best_track": best_track[0],
        "best_track_frames": best_track[1],
        "matched_ratio_best_track": round(len(best_track[1]) / len(rows), 3),
        "avg_link_score": round(
            sum(r["score"] for r in rows if r["track"] == best_track[0])
            / max(1, len([r for r in rows if r["track"] == best_track[0]])),
            3,
        ),
    }

text = json.dumps(out, ensure_ascii=False, indent=2)
Path(__file__).resolve().parent.parent / "data" / "demo_metrics.json".write_text(text, encoding="utf-8")
print(text)

