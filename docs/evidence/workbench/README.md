# 端到端验收工作台证据（2026-10-29）

本目录记录 Findy `/workbench` 在**隔离实例**上的 replay 演示验收结果。

## 环境与隔离方式

- 现有服务 `127.0.0.1:8765` 保持原进程、原数据库、原回放索引，未停止/未重启。
- 工作台验证实例：`127.0.0.1:8766`，使用同一仓库代码与真实 OWLv2/DINOv2 模型。
- 独立数据库/图像目录：`data/acceptance_workbench/evidence_*`（gitignored）。
- 回放帧：从 `data/demo_frames` **复制** 6 帧到独立目录；原目录未消耗。
- 未连接真实 ESP32，因此工作台真机项为 `NOT VERIFIED`，未伪造设备在线。

## 文件

| 文件 | 内容 |
|---|---|
| `workbench_report.json` | Chrome + Playwright 浏览器验收报告（38 项检查、console error、失败请求、运行与六项状态） |
| `acceptance_export.json` | 本轮验收导出（脱敏；不含图像数据） |
| `pytest_summary.txt` | 全量自动化测试摘要（89 passed） |
| `01_workbench_home.png` | 工作台首页/运行状态/操作引导 |
| `02_capture_detection.png` | 回放抓拍原图、检测框、置信度、耗时、来源 |
| `03_tracks.png` | 轨迹列表与跨帧关联详情 |
| `04_query.png` | “笔记本电脑最后出现在哪里？”查询回答与证据卡片 |
| `05_acceptance_overview.png` | 六项验收总览与证据 |
| `06_acceptance_finished.png` | 结束本轮验收后的状态 |

## 结果摘要

- 浏览器检查：**38/38 PASS**；失败请求 0；唯一 console error 是负向探测用例预期产生的 HTTP 400，已在报告 `expected_console_errors` 中单独记录。
- 六项（replay 演示）：设备连接 `NOT VERIFIED`；真实抓拍/检测/存储/轨迹关联/查询 `PASS`；总体 `NOT VERIFIED` 且 `simulated=true`，明确不计入真机验收。
- 自动化测试：`89 passed`（原 75 项未放宽断言）。
- `acceptance_export.json` 不含图像、真实设备地址或本地绝对路径。

## 隐私说明

上述截图均来自 `data/demo_frames` 的公开演示书桌图片（COCO 公开素材）经变换后的回放帧，不含真实桌面、真实设备图像或私人查询。真机图像与真机 UI 截图只应保存在本机 `data/`，不得提交仓库。

## 真机复验步骤（待办）

设备通电并连同一 Wi-Fi → 打开 `/workbench` → 输入 `http://<设备IP>` → “检查连接” → “使用此设备采集（仅本次会话）” → “立即抓拍”两次（移动物品后再抓拍）→ 找物查询 → 开始“真实设备验收”并结束 → 导出证据。此前真机项不得标记 `PASS`。