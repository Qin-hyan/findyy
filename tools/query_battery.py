import os, sys
sys.path.insert(0, r"D:\Findyy")
from pathlib import Path

os.environ.setdefault("FINDY_DB_PATH", r"D:\Findyy\data\demo.sqlite")
from findy.classes import load_catalog
from findy.config import load_config
from findy.db import Database
from findy.query import answer
from findy.zones import load_regions

cfg = load_config()
catalog = load_catalog(cfg.objects_file)
regions = load_regions(cfg.zones_file)
db = Database(Path(__file__).resolve().parent.parent / "data" / "demo.sqlite")

QUERIES = [
    "笔记本电脑最后出现在哪里？",
    "鼠标移动过吗？",
    "桌上都有哪些东西？",
    "手机是什么时候最后一次看到的？",
    "钥匙在哪？",
    "红色杯子在哪？",
    "今天鼠标动过吗？",
    "键盘有几个？",
    "我的电脑还在吗？",
    "你好",
    "手机最后在哪",
]
lines = []
for q in QUERIES:
    r = answer(db, cfg, catalog, regions, q)
    lines.append(f"### {q}")
    lines.append(f"intent={r['intent']}({r.get('intent_zh')}) status={r['status']} latency={r['latency_ms']}ms")
    lines.append(f"parsed={r['parsed']}")
    lines.append(f"answer={r['answer']}")
    for item in r.get("results", [])[:4]:
        if "events" in item:
            lines.append(f"  track={item.get('track_id')} label={item.get('label')} events={len(item['events'])}")
        elif "items" in item:
            lines.append(f"  items={[i.get('class_zh') for i in item['items']]}")
        else:
            lines.append(
                f"  track={item.get('track_id')} label={item.get('label')} zone={item.get('zone')} "
                f"time={item.get('time_local')} synced={item.get('time_synced')} conf={item.get('confidence')} "
                f"link={item.get('link_score')} status={item.get('link_status')} sightings={item.get('sightings')} "
                f"image={item.get('evidence_image_url')}"
            )
    if r.get("notes"):
        lines.append(f"notes={r['notes']}")
    lines.append("")
out = Path(__file__).resolve().parent.parent / "data" / "query_battery.txt"
out.write_text("\n".join(lines), encoding="utf-8")
print("\n".join(lines))

