"""命令行入口：python -m findy <command>"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .classes import load_catalog
from .config import REPO_ROOT, load_config
from .db import Database
from .query import answer as answer_query
from .sources import CaptureMeta, Esp32Source, ReplaySource, SourceError


def _print(data) -> None:
    print(json.dumps(data, ensure_ascii=False, indent=2))


def cmd_status(args) -> int:
    cfg = load_config(args.config)
    db = Database(cfg.db_path)
    catalog = load_catalog(cfg.objects_file)
    data = {
        "config": cfg.public_dict(),
        "db_ping": db.ping(),
        "stats": db.stats() if db.ping() else None,
        "classes": len(catalog.detectable),
        "models": {
            "detector": str(cfg.resolve(cfg.detector.model)),
            "detector_exists": cfg.resolve(cfg.detector.model).exists(),
            "embedder": str(cfg.resolve(cfg.embedder.model)),
            "embedder_exists": cfg.resolve(cfg.embedder.model).exists(),
        },
    }
    _print(data)
    return 0


def cmd_capture(args) -> int:
    cfg = load_config(args.config)
    from .api import create_app  # 复用完整初始化（DB/模型/区域）

    app = create_app(args.config)
    service = app.state.service
    result = service.capture_once()
    _print(result.to_dict())
    return 0 if result.ok else 1


def cmd_query(args) -> int:
    cfg = load_config(args.config)
    catalog = load_catalog(cfg.objects_file)
    from .zones import load_regions

    db = Database(cfg.db_path)
    regions = load_regions(cfg.zones_file)
    result = answer_query(db, cfg, catalog, regions, args.text)
    _print(result)
    return 0


def cmd_replay(args) -> int:
    """把目录里的图片按顺序回放一遍（验收/演示用）。"""
    import os

    cfg = load_config(args.config)
    cfg.capture.source = "replay"
    cfg.capture.replay.dir = args.dir or cfg.capture.replay.dir
    os.environ["FINDY_CAPTURE_SOURCE"] = "replay"
    os.environ["FINDY_REPLAY_DIR"] = cfg.capture.replay.dir
    if args.db:
        os.environ["FINDY_DB_PATH"] = args.db
    from .api import create_app

    app = create_app(args.config)
    service = app.state.service
    results = []
    while True:
        try:
            frame = service.source().capture()
        except SourceError as exc:
            if "已用尽" in str(exc):
                break
            print(f"[ERROR] {exc}", file=sys.stderr)
            return 2
        except Exception as exc:
            print(f"[ERROR] {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        result = app.state.pipeline.observe(frame.jpeg, frame.meta)
        results.append(
            {
                "ok": result.ok,
                "capture_id": result.capture_id,
                "detections": result.detections,
                "warnings": result.warnings,
                "error": result.error,
            }
        )
        print(
            f"[{len(results)}] {frame.meta.source_ref}: {len(result.detections)} 个物品"
            + (f" | {result.error}" if result.error else ""),
            file=sys.stderr,
        )
        if args.limit and len(results) >= args.limit:
            break
    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已写入 {args.out}", file=sys.stderr)
    return 0 if all(r["ok"] for r in results) else 1


def cmd_serve(args) -> int:
    import uvicorn

    cfg = load_config(args.config)
    host = args.host or cfg.app.host
    port = args.port or cfg.app.port
    from .api import create_app

    app = create_app(args.config)
    print(f"Findy 启动：http://{host}:{port}", file=sys.stderr)
    uvicorn.run(app, host=host, port=port, log_level=args.log_level, access_log=False)
    return 0


def cmd_esp32(args) -> int:
    cfg = load_config(args.config)
    source = Esp32Source(args.url or cfg.capture.esp32.base_url, cfg.capture.esp32.timeout_seconds)
    try:
        status = source.probe()
        _print({"ok": True, "status": status})
        return 0
    except SourceError as exc:
        _print({"ok": False, "error": str(exc)})
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="findy", description="Findy 物品记忆助手")
    parser.add_argument("--config", default=None, help="配置文件路径（默认 config/findy.yaml）")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("serve", help="启动 Web 服务")
    p.add_argument("--host", default=None)
    p.add_argument("--port", type=int, default=None)
    p.add_argument("--log-level", default="info")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("status", help="打印配置与数据库状态")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("capture", help="从当前采集源抓拍一次并入库")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("query", help="执行一次自然语言查询")
    p.add_argument("text")
    p.set_defaults(func=cmd_query)

    p = sub.add_parser("replay", help="回放图片目录")
    p.add_argument("--dir", default=None)
    p.add_argument("--db", default=None, help="临时数据库路径（默认 data/findy.sqlite）")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--out", default=None)
    p.set_defaults(func=cmd_replay)

    p = sub.add_parser("esp32", help="探测 ESP32 设备状态")
    p.add_argument("--url", default=None)
    p.set_defaults(func=cmd_esp32)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())