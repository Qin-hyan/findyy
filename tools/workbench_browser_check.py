"""用本机 Chrome + Playwright 对 Findy 端到端验收工作台做真实浏览器验收。

用法（需服务已在运行，建议使用隔离验收实例；需要装有 Playwright 的 Python）：
    python tools/workbench_browser_check.py http://127.0.0.1:8766

输出：
    docs/evidence/workbench/workbench_report.json（默认）
    docs/evidence/workbench/*.png（仅 replay/公开演示数据截图）

注意：本脚本不启动/停止服务，不修改数据库；只通过页面真实点击同源 API。
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"
OUT = (
    Path(sys.argv[2])
    if len(sys.argv) > 2
    else Path(__file__).resolve().parent.parent / "docs" / "evidence" / "workbench"
)
OUT.mkdir(parents=True, exist_ok=True)

report = {
    "base": BASE,
    "started_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    "checks": [],
    "console_errors": [],
    "failed_requests": [],
    "run": None,
    "acceptance_items": [],
}


def check(name: str, ok: bool, detail: str = "") -> bool:
    report["checks"].append({"name": name, "ok": bool(ok), "detail": str(detail)[:500]})
    print(("PASS " if ok else "FAIL ") + name + (f" :: {detail}" if detail else ""), flush=True)
    return bool(ok)


def wait_text(page, selector: str, needle: str, timeout: int = 20000) -> str:
    page.wait_for_function(
        "(args) => { const el = document.querySelector(args.sel);"
        " return !!el && el.innerText.includes(args.needle); }",
        arg={"sel": selector, "needle": needle},
        timeout=timeout,
    )
    return page.inner_text(selector)


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    ctx = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="zh-CN")
    page = ctx.new_page()
    page.on("console", lambda m: report["console_errors"].append(m.text) if m.type == "error" else None)
    page.on("requestfailed", lambda r: report["failed_requests"].append(f"{r.url} :: {r.failure}"))

    page.goto(BASE.rstrip("/") + "/workbench", wait_until="networkidle", timeout=60000)
    page.wait_for_selector("#acceptance-items .wb-accept-item", timeout=60000)
    page.wait_for_function(
        "() => { const m = document.getElementById('pill-model');"
        " return !!m && m.innerText.includes('就绪'); }",
        timeout=120000,
    )
    time.sleep(1)

    check("页面标题为验收工作台", "验收工作台" in page.title(), page.title())
    check("状态栏显示采集源", "采集源" in page.inner_text("#pill-source"), page.inner_text("#pill-source"))
    check("模型显示就绪", "就绪" in page.inner_text("#pill-model"), page.inner_text("#pill-model"))
    check("数据库状态已加载", "帧" in page.inner_text("#db-status"), page.inner_text("#db-status"))
    check("验收总览固定六行", page.locator("#acceptance-items .wb-accept-item").count() == 6)
    check(
        "操作引导含设备 IP 步骤",
        "设备 IP" in page.inner_text(".wb-guide") or "设备IP" in page.inner_text(".wb-guide"),
    )
    check("隐私说明声明仅本机", "不上传" in page.inner_text(".wb-guide") or "本机" in page.inner_text(".wb-guide"))
    page.screenshot(path=str(OUT / "01_workbench_home.png"), full_page=True)

    # 1) replay 模式下“检查连接”必须如实失败，不能假成功
    page.fill("#device-ip", "")
    page.click("#probe-btn")
    page.wait_for_function(
        "() => { const el = document.getElementById('capture-status');"
        " return !!el && (el.innerText.includes('设备检查失败') || el.innerText.includes('正常')); }",
        timeout=30000,
    )
    probe_text = page.inner_text("#capture-status")
    check(
        "回放模式检查连接不伪造成功",
        "设备检查失败" in probe_text,
        probe_text,
    )
    check("检查连接失败后给出原因", len(probe_text) > 10, probe_text)

    # 2) 开始回放演示验收（明确标注模拟，不计入真机验收）
    page.click("#run-start-demo")
    run_info = wait_text(page, "#run-info", "回放演示", timeout=20000)
    check("开始回放演示运行", "进行中" in run_info or "回放演示" in run_info, run_info[:200])

    # 3) 真实点击抓拍两次（使用副本回放帧，真实 OWLv2 检测）
    capture_ok = True
    for index in range(2):
        page.click("#capture-btn")
        page.wait_for_function(
            "() => { const b = document.getElementById('capture-btn'); const s = document.getElementById('capture-status');"
            " return (b && b.innerText.includes('抓拍与识别中'))"
            " || (s && s.innerText.includes('已等待')); }",
            timeout=10000,
        )
        page.wait_for_function(
            "() => { const el = document.getElementById('capture-status');"
            " if (!el) return false; const t = el.innerText;"
            " return t.includes('抓拍完成') || t.includes('抓拍失败') || t.includes('超时'); }",
            timeout=180000,
        )
        status = page.inner_text("#capture-status")
        check(f"第 {index + 1} 次抓拍完成", "抓拍完成" in status, status)
        capture_ok = capture_ok and "抓拍完成" in status
        time.sleep(0.6)

    page.wait_for_function(
        "() => { const img = document.getElementById('capture-img'); return !!img && !img.hidden && img.naturalWidth > 0; }",
        timeout=30000,
    )
    check("抓拍原图可见", True)
    check("图片上绘制检测框", page.locator("#overlay .bbox").count() >= 1, f"{page.locator('#overlay .bbox').count()} 个框")
    check("检测结果表有物品", page.locator("#detection-rows tr").count() >= 1)
    capture_meta = page.inner_text("#capture-meta")
    check("显示检测/处理耗时", ("ms" in capture_meta) or ("耗时" in capture_meta), capture_meta[:260])
    badge = page.inner_text("#capture-source-badge")
    check("检测结果标注回放来源", "回放" in badge, badge)
    page.screenshot(path=str(OUT / "02_capture_detection.png"), full_page=True)

    # 4) 轨迹关联列表与跨帧详情
    page.wait_for_selector("#tracks .wb-track-item", timeout=30000)
    check("轨迹列表有记录", page.locator("#tracks .wb-track-item").count() >= 1)
    page.locator("#tracks .wb-track-item").first.click()
    page.wait_for_function(
        "() => { const el = document.getElementById('track-detail');"
        " return !!el && (el.innerText.includes('关联分') || el.innerText.includes('轨迹 #')); }",
        timeout=20000,
    )
    track_text = page.inner_text("#track-detail")
    check("轨迹详情显示关联分", "关联分" in track_text or "关联" in track_text, track_text[:220])
    check("轨迹详情有跨帧证据", "抓拍 #" in track_text or "观测" in track_text or "次" in track_text)
    page.screenshot(path=str(OUT / "03_tracks.png"), full_page=True)

    # 5) 找物查询：真实结果 + 图片/时间/区域
    page.fill("#query-input", "笔记本电脑最后出现在哪里？")
    page.click("#query-submit")
    page.wait_for_function(
        "() => { const a = document.getElementById('answer');"
        " if (!a) return false; const t = a.innerText;"
        " return t.length > 10 && !t.includes('正在检索'); }",
        timeout=60000,
    )
    answer = page.inner_text("#answer")
    check("查询返回最后位置", "最后出现" in answer, answer[:220])
    check("查询结果含画面区域", "桌面" in answer, answer[:220])
    check("查询结果渲染证据卡片", page.locator("#results .result").count() >= 1,
          f"{page.locator('#results .result').count()} 张")
    check("查询显示延迟/意图", "意图" in page.inner_text("#query-meta") or "延迟" in page.inner_text("#query-meta"),
          page.inner_text("#query-meta")[:160])
    page.screenshot(path=str(OUT / "04_query.png"), full_page=True)

    # 6) 验收总览与后端状态一致，且设备连接不得假 PASS
    page.wait_for_function(
        "() => { const c = document.getElementById('overall-counts'); const rows = document.querySelectorAll('#acceptance-items .wb-accept-item');"
        " return !!c && rows.length === 6 && !c.innerText.includes('—'); }",
        timeout=30000,
    )
    backend = page.evaluate(
        "async () => { const r = await fetch('/api/acceptance', {cache: 'no-store'}); return await r.json(); }"
    )
    overview = backend.get("overview") or {}
    backend_items = {i["key"]: i["status"] for i in (overview.get("items") or [])}
    counts = overview.get("counts") or {}
    expected_counts = (
        "PASS " + str(counts.get("pass"))
        + " · FAIL " + str(counts.get("fail"))
        + " · NOT VERIFIED " + str(counts.get("not_verified"))
    )
    page.wait_for_function(
        "(t) => { const el = document.getElementById('overall-counts'); return !!el && el.innerText.trim() === t; }",
        arg=expected_counts,
        timeout=20000,
    )
    ui_items = {}
    ui_statuses = []
    for row in page.locator("#acceptance-items .wb-accept-item").all():
        title = row.locator(".wb-accept-title").inner_text()
        status = row.locator(".wb-status").inner_text()
        ui_items[title] = status
        ui_statuses.append(status)
        report["acceptance_items"].append({"title": title, "status": status})
    check("六项验收状态渲染", len(report["acceptance_items"]) == 6, str(report["acceptance_items"]))
    check("设备连接为 NOT VERIFIED", ui_items.get("设备连接") == "NOT VERIFIED", str(ui_items))
    statuses = [i["status"] for i in (overview.get("items") or [])]

    def normalize_status(value):
        # 后端用 NOT_VERIFIED（机器码），界面显示 NOT VERIFIED（人类可读）；比较时统一。
        return str(value or "").replace("_", " ").strip().upper()

    check(
        "UI 与后端验收状态一致",
        [normalize_status(s) for s in ui_statuses] == [normalize_status(s) for s in statuses],
        f"UI={ui_statuses} 后端={statuses}",
    )
    check("回放演示无 FAIL 项", "FAIL" not in statuses, str(statuses))
    check("回放演示至少 4 项 PASS", statuses.count("PASS") >= 4, str(statuses))
    check("回放演示标记 simulated", overview.get("simulated") is True,
          str(overview.get("simulated")))
    check("总体状态不冒充真机通过", overview.get("status") == "NOT_VERIFIED",
          str(overview.get("status")))
    check("整体横幅含回放演示说明", "回放演示" in page.inner_text("#overall-banner"),
          page.inner_text("#overall-banner")[:200])
    page.screenshot(path=str(OUT / "05_acceptance_overview.png"), full_page=True)

    # 7) 结束运行 + 导出证据脱敏
    run_id = (backend.get("run") or {}).get("id")
    if run_id:
        page.click("#run-finish")
        page.wait_for_function(
            "() => { const el = document.getElementById('run-info');"
            " return !!el && (el.innerText.includes('结束：') || el.innerText.includes('finished')); }",
            timeout=30000,
        )
        final_backend = page.evaluate(
            "async () => { const r = await fetch('/api/acceptance', {cache: 'no-store'}); return await r.json(); }"
        )
        report["run"] = final_backend.get("run")
        check("本轮验收已结束", (final_backend.get("run") or {}).get("status") == "finished",
              str((final_backend.get("run") or {}).get("status")))
        finished = page.evaluate(
            "async (runId) => { const r = await fetch('/api/acceptance/run/' + runId + '/export', {cache: 'no-store'});"
            " const t = await r.text(); return {status: r.status, text: t}; }",
            run_id,
        )
        check("结束本轮验收", True)
        check("导出证据接口可用", finished["status"] == 200, str(finished["status"]))
        try:
            export_payload = json.loads(finished["text"])
        except Exception:
            export_payload = {}
        check("导出包含验收结论", bool(export_payload.get("overview")), list(export_payload.keys()))
        check("导出含隐私说明", "privacy_note" in export_payload)
        check("导出已脱敏绝对路径", "D:\\\\Findyy" not in finished["text"] and "D:/Findyy" not in finished["text"])
        report["export_ok"] = bool(export_payload.get("overview"))
        page.screenshot(path=str(OUT / "06_acceptance_finished.png"), full_page=True)
    else:
        check("结束本轮验收", False, "后端未返回运行 ID")

    browser.close()

report["console_errors"] = report["console_errors"][:20]
report["failed_requests"] = report["failed_requests"][:20]
# 负向探测测试会得到预期的 HTTP 400，Chrome 会把它记为一条 console error。
# 只有这一条是预期内的；其余 console error / 失败请求都算问题。
expected_console = [e for e in report["console_errors"] if "status of 400" in e]
unexpected_console = [e for e in report["console_errors"] if e not in expected_console]
report["expected_console_errors"] = expected_console
report["ok"] = (
    all(c["ok"] for c in report["checks"])
    and not unexpected_console
    and not report["failed_requests"]
)
report["finished_at_utc"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
(OUT / "workbench_report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
)
print(
    json.dumps(
        {
            "ok": report["ok"],
            "checks": len(report["checks"]),
            "failed": [c["name"] for c in report["checks"] if not c["ok"]],
            "console_errors": report["console_errors"][:5],
            "failed_requests": report["failed_requests"][:5],
            "items": report["acceptance_items"],
        },
        ensure_ascii=False,
        indent=2,
    ),
    flush=True,
)
sys.exit(0 if report["ok"] else 1)