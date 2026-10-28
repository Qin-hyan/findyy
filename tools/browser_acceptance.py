"""用本机 Chrome + Playwright 对 Findy 做真实浏览器验收（截图 + 交互断言）。"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
OUT = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parent.parent / "data" / "screenshots"
OUT.mkdir(parents=True, exist_ok=True)

report = {"base": BASE, "checks": [], "console_errors": [], "failed_requests": []}


def check(name: str, ok: bool, detail: str = "") -> None:
    report["checks"].append({"name": name, "ok": bool(ok), "detail": detail})
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""), flush=True)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
    page = ctx.new_page()
    page.on("console", lambda msg: report["console_errors"].append(msg.text) if msg.type == "error" else None)
    page.on("requestfailed", lambda req: report["failed_requests"].append(f"{req.url} :: {req.failure}"))

    page.goto(BASE, wait_until="networkidle", timeout=60000)
    page.wait_for_selector("#objects .object-card, #objects p", timeout=30000)
    time.sleep(1.0)

    # 1) 状态栏与物品库
    pill_db = page.inner_text("#pill-db")
    pill_model = page.inner_text("#pill-model")
    check("状态栏显示数据库统计", "数据库" in pill_db and "帧" in pill_db, pill_db)
    check("状态栏显示模型就绪", "就绪" in pill_model, pill_model)
    object_count = page.locator("#objects .object-card").count()
    check("物品库渲染卡片", object_count >= 3, f"{object_count} 张卡片")
    check("时间线渲染缩略图", page.locator("#timeline .timeline-item").count() >= 3)
    page.screenshot(path=str(OUT / "01_home.png"), full_page=True)

    # 2) 自然语言查询：最后位置
    page.fill("#query-input", "笔记本电脑最后出现在哪里？")
    page.click("#query-form button")
    page.wait_for_function(
        "() => { const a = document.getElementById('answer'); return a && !a.classList.contains('hidden') && a.innerText.length > 10 && !a.innerText.includes('正在检索'); }",
        timeout=20000,
    )
    answer = page.inner_text("#answer")
    check("查询返回最后位置", "桌面" in answer and "最后出现" in answer, answer[:120])
    check("查询结果渲染证据卡片", page.locator("#results .result").count() >= 1)
    page.screenshot(path=str(OUT / "02_query_last_seen.png"), full_page=True)

    # 3) 移动历史查询
    page.fill("#query-input", "鼠标移动过吗？")
    page.click("#query-form button")
    page.wait_for_function(
        "() => { const a = document.getElementById('answer'); return a && a.innerText.length > 10 && !a.innerText.includes('正在检索'); }",
        timeout=20000,
    )
    moved_answer = page.inner_text("#answer")
    check("移动查询返回轨迹", "移动过" in moved_answer and "桌面" in moved_answer, moved_answer[:140])
    page.screenshot(path=str(OUT / "03_query_moved.png"), full_page=True)

    # 4) 不存在的物品：明确说明
    page.fill("#query-input", "钥匙在哪？")
    page.click("#query-form button")
    page.wait_for_function(
        "() => { const a = document.getElementById('answer'); return a && a.innerText.length > 10 && !a.innerText.includes('正在检索'); }",
        timeout=20000,
    )
    notfound = page.inner_text("#answer")
    check("查不到时明确说明", "没有找到" in notfound, notfound[:120])
    page.screenshot(path=str(OUT / "04_query_not_found.png"), full_page=True)

    # 5) 真实点击抓拍（回放采集源）
    page.click("#capture-btn")
    page.wait_for_function(
        "() => { const s = document.getElementById('capture-status'); return s && (s.innerText.includes('本次识别到') || s.innerText.includes('失败')); }",
        timeout=180000,
    )
    capture_status = page.inner_text("#capture-status")
    check("抓拍按钮触发流水线", "本次识别到" in capture_status, capture_status)
    time.sleep(1.0)
    check("抓拍后图像可见", page.evaluate("() => { const i=document.getElementById('capture-img'); return !!i && !i.hidden && i.naturalWidth>0; }"))
    check("抓拍后绘制检测框", page.locator("#overlay .bbox").count() >= 1)
    page.screenshot(path=str(OUT / "05_capture.png"), full_page=True)

    # 6) 查看抓拍详情（时间线点击）
    first_timeline = page.locator("#timeline .timeline-item").first
    if first_timeline.count() > 0:
        first_timeline.click()
        time.sleep(1.5)
        check("时间线点击可回看历史帧", page.locator("#overlay .bbox").count() >= 1)

    browser.close()

report["ok"] = all(c["ok"] for c in report["checks"])
(OUT / "browser_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps({"ok": report["ok"], "checks": len(report["checks"]),
                  "failed": [c["name"] for c in report["checks"] if not c["ok"]],
                  "console_errors": report["console_errors"][:5]}, ensure_ascii=False, indent=2))
sys.exit(0 if report["ok"] else 1)
