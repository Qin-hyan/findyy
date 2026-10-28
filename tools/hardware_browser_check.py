"""真机 UI 验收：对真实 ESP32 采集源跑浏览器关键交互（截图仅存本机 data/，不入库）。

前置：
  $env:FINDY_CAPTURE_SOURCE='esp32'
  $env:FINDY_ESP32_URL='http://<设备IP>'
  $env:FINDY_DB_PATH='data/hardware.sqlite'
  $env:FINDY_IMAGES_DIR='data/hardware_images'
  $env:FINDY_CROPS_DIR='data/hardware_crops'
  python -m findy serve --port 8766
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "data" / "hardware_screenshots"
OUT.mkdir(parents=True, exist_ok=True)
report = {"base": BASE, "checks": [], "console_errors": []}


def check(name: str, ok: bool, detail: str = "") -> None:
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""), flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    page.on("console", lambda m: report["console_errors"].append(m.text) if m.type == "error" else None)
    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("#objects .object-card, #objects p", timeout=30000)
    time.sleep(1)

    check("状态栏显示 ESP32 采集源", "ESP32" in page.inner_text("#pill-source"), page.inner_text("#pill-source"))
    check("状态栏显示动态数据库统计", "帧" in page.inner_text("#pill-db"), page.inner_text("#pill-db"))
    check("模型就绪", "就绪" in page.inner_text("#pill-model"), page.inner_text("#pill-model"))
    check("物品库有真机识别结果", page.locator("#objects .object-card").count() >= 1,
          f"{page.locator('#objects .object-card').count()} 件")
    page.screenshot(path=str(OUT / "hw_home.png"), full_page=True)

    page.fill("#query-input", "笔记本电脑最后出现在哪里？")
    page.click("#query-form button")
    page.wait_for_function(
        "() => { const a=document.getElementById('answer'); return a && a.innerText.length>10 && !a.innerText.includes('正在检索'); }",
        timeout=20000,
    )
    answer = page.inner_text("#answer")
    check("真机数据查询最后位置", "桌面" in answer and "2026-10-29" in answer, answer[:140])
    page.screenshot(path=str(OUT / "hw_query.png"), full_page=True)

    page.click("#capture-btn")
    page.wait_for_function(
        "() => { const s=document.getElementById('capture-status'); return s && (s.innerText.includes('本次识别到') || s.innerText.includes('失败')); }",
        timeout=180000,
    )
    status = page.inner_text("#capture-status")
    check("界面触发真机抓拍成功", "本次识别到" in status, status)
    check("真机抓拍帧可见", page.evaluate("() => { const i=document.getElementById('capture-img'); return !!i && !i.hidden && i.naturalWidth>0; }"))
    page.screenshot(path=str(OUT / "hw_capture.png"), full_page=True)
    browser.close()

report["ok"] = all(c["ok"] for c in report["checks"])
OUT.joinpath("hw_browser_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"ok": report["ok"], "failed": [c["name"] for c in report["checks"] if not c["ok"]],
                  "console_errors": report["console_errors"][:3]}, ensure_ascii=False))
sys.exit(0 if report["ok"] else 1)