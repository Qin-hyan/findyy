# 端到端验收工作台证据（2026-10-29）

本目录记录 Findy `/workbench` 在**隔离实例**上的 replay 演示验收结果，以及真机复验状态。

## 环境与隔离方式

- 现有服务 `127.0.0.1:8765` 保持原进程、原数据库、原回放索引，未停止/未重启。
- 工作台验证实例：`127.0.0.1:8766`，使用同一仓库代码与真实 OWLv2/DINOv2 模型。
- 回放演示数据库/图像目录：`data/acceptance_workbench/evidence_*`（gitignored）。
- 真机验证数据库/图像目录：`data/acceptance_workbench/real_*`（gitignored；真机图像不提交）。
- 回放帧：从 `data/demo_frames` **复制** 6 帧到独立目录；原目录未消耗。
- 真机已找到并连接（IP/MAC 不写入仓库）；物理调整镜头后 run #3 六项 `PASS`，真机证据见 `real_device_acceptance_summary.json`。真机图像、IP/MAC、查询文本与本地路径均未提交。

## 文件

| 文件 | 内容 |
|---|---|
| `workbench_report.json` | Chrome + Playwright 浏览器验收报告（38 项检查、console error、失败请求、运行与六项状态） |
| `acceptance_export.json` | 本轮验收导出（脱敏；不含图像数据） |
| `real_device_acceptance_summary.json` | 2026-10-29 真机 run #3 六项 PASS 的脱敏摘要（不含图像/IP/MAC/查询文本/本地路径；含原始导出 SHA256） |
| `pytest_summary.txt` | 全量自动化测试摘要（92 passed） |
| `01_workbench_home.png` | 工作台首页/运行状态/操作引导 |
| `02_capture_detection.png` | 回放抓拍原图、检测框、置信度、耗时、来源 |
| `03_tracks.png` | 轨迹列表与跨帧关联详情 |
| `04_query.png` | “笔记本电脑最后出现在哪里？”查询回答与证据卡片 |
| `05_acceptance_overview.png` | 六项验收总览与证据 |
| `06_acceptance_finished.png` | 结束本轮验收后的状态 |

## 结果摘要

- 浏览器检查：**38/38 PASS**；失败请求 0；唯一 console error 是负向探测用例预期产生的 HTTP 400，已在报告 `expected_console_errors` 中单独记录。
- 六项（replay 演示）：设备连接 `NOT VERIFIED`；真实抓拍/检测/存储/轨迹关联/查询 `PASS`；总体 `NOT VERIFIED` 且 `simulated=true`，明确不计入真机验收。
- 自动化测试：`92 passed`（原 75 项未放宽断言；新增重复旧帧排除、设备重启 seq 冲突、导出 IP/MAC 脱敏测试）。
- `acceptance_export.json` 不含图像、真实设备地址或本地绝对路径。

## 真机复验状态（2026-10-29）

- 设备已通过 USB COM10 找到并连接，`/api/status`、`/api/capture`、`/api/photo?seq` 均兼容；未修改固件。
- 首次真机运行 #1 的抓拍事件均为 `duplicate=true` 的运行前旧帧（设备重启导致 seq 归零），旧判定曾误报 `PASS`；修复后已纠正为 `NOT_VERIFIED`，该导出**未提交仓库**。
- 修正后运行 #2 产生了 3 帧新真实画面，但相机视角未对准桌面，检测 0，保持 `NOT_VERIFIED`。
- **物理复位镜头后 run #3（13:59:38–14:01:47）六项 PASS**：`simulated=false`、2 帧运行内新抓拍（#8/#9，`duplicate=false`）、检测 2 个物品（键盘，检测 7423 ms）、轨迹关联 0.88、查询返回真实 esp32 证据（桌面左侧、置信度约 0.43）；另有 2 次灰区待确认。
- 原始完整导出 `findy-acceptance-run-3.json` 只保存在本机，SHA256 `2598f8781cc8fb3b29443979e89a6a508193ccfa50b404c5a03d7b9c0b06a543`；提交版摘要不含查询文本/本地路径/设备 IP/MAC/图像。
- 用户下载的 `findy-acceptance-run-*.json` 已被 `.gitignore` 排除，避免真实 IP/隐私数据误提交。
- 限制：单桌面、单次会话、小样本；检测仅命中键盘等少量物品，查询出现 6 个可能键盘的灰区，不代表真实场景精度。

## 隐私说明

上述截图均来自 `data/demo_frames` 的公开演示书桌图片（COCO 公开素材）经变换后的回放帧，不含真实桌面、真实设备图像或私人查询。真机图像与真机 UI 截图只应保存在本机 `data/`，不得提交仓库。

## 真机复验步骤（已完成一次）

物理调整 ESP32 镜头对准桌面物品 → 打开 `/workbench` → 点击“开始真实设备验收” → 确认设备地址并“检查连接” → “立即抓拍”两次（移动物品后再抓拍）→ 查询画面中实际检出的物品 → “结束本轮验收” → 导出证据。后续多场景/多时段复验沿用同一顺序。