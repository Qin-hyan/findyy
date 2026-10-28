# Findy MVP 验收报告

- 验收日期：2026-10-28（演示数据） / 2026-10-29（真实 ESP32 硬件）
- 验收范围：阶段一调研结论落地情况、阶段二 MVP 核心闭环、阶段三端到端与异常/安全/文档检查
- 验收对象：本仓库 `D:\Findyy`（MVP 代码 + 配置 + 测试 + 文档）
- 关联硬件：ESP32-S3-EYE v2.2 + OV2640，Findy M1 固件独立仓库 `D:\Findy-Firmware`（其自身实机 100/100 拍摄证据见 `docs/M1_RESULTS.md`）

---

## 1. 结论摘要

| 结论 | 数量 | 说明 |
|---|---|---|
| ✅ 通过 | 16 | 核心闭环（含真机）、自动化测试、演示与真机浏览器交互、异常输入、时间语义、持久化、安全检查等 |
| 🟡 部分通过 | 3 | 真实场景精度只有 6 帧小样本且无 ground truth；开放词表仍有误检/漏检；位置仅画面区域 |
| ❌ 失败 | 0 | 未发现验收标准内的失败项 |
| ⛔ 未验证 | 3 | 同款多件区分、长期运行/断线重连/容量清理、多用户/鉴权 |

**总体判断**：Findy MVP 已在本机完成「真实 ESP32 抓拍 → 开放词表检测 → 同一实物跨帧关联 → 本地历史存储 → 中文自然语言查询 → 带证据界面展示」的闭环，**真机 6/6 次抓拍成功、38 次检测、8 条轨迹，主要物品 6/6 帧关联到同一轨迹**；自动化测试与浏览器验收全部通过。仍需如实说明：真实场景精度缺少 ground truth、同款多件与长期稳定性未验证。

---

## 2. 验收环境

| 项目 | 值 |
|---|---|
| 操作系统 | Windows 11 家庭中文版 10.0.26100 |
| CPU / 内存 | Intel Core i7-14650HX（16 核 / 24 线程）/ 15.7 GB |
| Python | 3.14.3（`D:\python\python1` 为基础，`D:\Findyy\.venv314` 继承其 torch 等站点包） |
| 关键依赖 | torch 2.10.0+cpu、transformers 5.2.0、fastapi 0.115.6、uvicorn 0.41.0、pydantic 2.12.5、httpx 0.28.1、pytest 8.3.4、pillow 11.3.0、numpy 2.4.2、PyYAML 6.0.3、jinja2 3.1.6、python-multipart 0.0.20、tzdata 2026.5 |
| 检测模型 | OWLv2 `google/owlv2-base-patch16-ensemble`（本地 591.2 MB safetensors） |
| 实例特征 | DINOv2 `facebook/dinov2-small`（84.2 MB） |
| 硬件 | ESP32-S3-EYE v2.2 + OV2640，Findy M1 固件，SVGA 800×600，SNTP 已同步，Wi-Fi RSSI −27 dBm |
| 浏览器验收 | 本机 Chrome（Playwright 1.64.0，`channel=chrome`，headless） |

> 环境说明：本机 Anaconda Python 3.11 自带的 torch 2.11 出现 `c10.dll` 初始化失败（环境问题，非本项目代码），因此验收使用可正常加载的 Python 3.14 + torch 2.10 CPU 环境；`requirements.txt` 对 Python 3.11+ 通用，未绑定该机器。

---

## 3. 核心功能验收矩阵（阶段二 7 项闭环）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 获取摄像头图像 | ✅ 通过（真机 + 回放） | 真机 6/6 次抓拍成功（800×600 JPEG，seq 递增）；回放 6 帧；`Esp32Source` 的 seq/时间/过期图拒绝有单测 |
| 2 | 检测/识别图像中的物品 | ✅ 通过 | 真机 6 帧共 38 次检测（充电器、笔记本、耳机、键盘、鼠标、钥匙）；演示 6 帧 29 次检测；词表 23 类可配置 |
| 3 | 保存观测记录、图像、时间、区域 | ✅ 通过 | SQLite + 文件系统；真实 SNTP 时间（`2026-10-29 01:00–01:01`）；区域多边形；双时间字段与 `time_source` |
| 4 | 跨时刻关联同一实物、处理不确定 | ✅ 通过（小样本） | 真机：充电器/笔记本/耳机/键盘/鼠标 5 类主物品均 6/6 帧关联同一轨迹（相似度 1.00）；1 次鼠标灰区待确认；演示：23 matched / 1 ambiguous / 5 new |
| 5 | 自然语言查询最后位置 | ✅ 通过 | 8 条真机查询 + 11 条演示查询：最后位置、历史、移动、数量、清单、存在、查不到、帮助均返回合理中文回答 |
| 6 | 展示匹配物品、图像、时间、依据 | ✅ 通过 | 演示浏览器 12/12、真机浏览器 7/7；回答含区域、时间、置信度、关联相似度、证据图与检测框 |
| 7 | 可实际使用的界面与运行状态 | ✅ 通过 | 单页界面 + `/api/status`（模型/数据库/采集源/自动采集）；真机 UI 点击抓拍成功 |

---

## 4. 自动化测试结果

命令：`python -m pytest tests -q`（日志：[`docs/evidence/pytest_run.log`](evidence/pytest_run.log)）

```
75 passed, 486 warnings in 6.54s
```

- **0 失败、0 跳过**；warning 全部为第三方库弃用提示，不影响功能。
- 覆盖模块：图像与颜色特征、关联打分/三态/空间 IoU、区域多边形、中文意图解析、SQLite 幂等/合并/统计、主流水线（检测失败、时间未同步、重复 seq、移动检测）、HTTP API（状态/抓拍/上传/查询/物品/抓拍图/裁剪图/服务开关/异常 503/404/422）、ESP32 适配器（mock 固件服务）、配置加载与环境变量覆盖、时间/哈希工具。

---

## 5. 浏览器端到端验收

### 5.1 演示数据（Chrome + Playwright）

命令：`python tools/browser_acceptance.py http://127.0.0.1:8765`
证据：[`browser_report.json`](evidence/browser_report.json)、[截图](evidence/screenshots/)

**12/12 通过，控制台错误 0，失败请求 0。**

覆盖：状态栏（数据库/模型/采集源）、物品库、时间线、三类中文查询（最后位置/移动历史/查不到）、证据卡片、点击抓拍、图像可见、检测框绘制、点击时间线回看历史帧。

| 首页 | 查询结果 |
|---|---|
| ![首页](evidence/screenshots/01_home.png) | ![查询](evidence/screenshots/02_query_last_seen.png) |

### 5.2 真实 ESP32 硬件（Chrome + Playwright）

命令：`python tools/hardware_browser_check.py http://127.0.0.1:8766`
证据：[`hw_browser_report.json`](evidence/hardware/hw_browser_report.json)

**7/7 通过，控制台错误 0。** 覆盖：状态栏显示 `采集源 · ESP32`、6 帧 / 8 物品、模型就绪、物品库有真机识别结果、真机数据查询「笔记本电脑」返回「桌面中央」与真实时间、界面点击抓拍从真机取图并识别 7 个物品、抓拍帧可见。

> 隐私说明：真机原始图像与 UI 截图含用户真实桌面，仅保存在本机 `data/` 用于验证，**未提交仓库，验证后已删除**；仓库只保留脱敏后的元数据证据（设备 IP 替换为 `<device-ip>`）。

---

## 6. 数据指标（如实口径）

### 6.1 真实 ESP32 硬件（2026-10-29，6 帧，证据 [`hardware_result.json`](evidence/hardware/hardware_result.json)）

| 指标 | 实测值 |
|---|---|
| 抓拍成功 | **6/6**，设备 seq 连续，时间来自设备 SNTP（`2026-10-29 01:00:12`–`01:01:03`） |
| 检测总数 | 38（每帧 6 / 6 / 7 / 6 / 7 / 6） |
| 物品轨迹 | 8 条；主要 5 类物品均 **6/6 帧关联同一轨迹** |
| 主物品关联分 | 充电器、笔记本、耳机、键盘、鼠标 = 1.00（含空间 IoU 加分，封顶 1.0） |
| 钥匙 | 2 次观测（帧 3/5），关联分 0.99；其他帧未被检出（置信度仅 0.22，属漏检） |
| 灰区 | 1 次鼠标检测 `ambiguous`（0.77），另产生 1 条单次鼠标轨迹（误检/遮挡导致） |
| 未同步时间 | 0 帧 |
| 端到端节奏 | 6 帧约 51 秒（含每次检测约 7–8 秒 CPU 推理 + 3 秒间隔） |
| 设备状态 | 摄像头 OV2640 就绪、800×600、Wi-Fi 连接、RSSI −27 dBm、SNTP synced=true |

### 6.2 演示回放（2026-10-28，6 帧，证据 [`demo_metrics.json`](evidence/demo_metrics.json)）

演示帧是**同一张公开 COCO 书桌图片**经亮度/平移/轻微旋转变换生成，模拟「不同时间、不同取景」，不是真实设备录像；场景实物为 5 件（手机、笔记本、2 个键盘、鼠标）。

| 指标 | 实测值 |
|---|---|
| 帧数 / 检测总数 | 6 帧 / 29 次（每帧 5 / 5 / 5 / 5 / 4 / 5） |
| 关联判定 | matched 23、ambiguous 1、new 5 |
| 手机 / 笔记本 / 鼠标 | 各 6/6 帧关联同一轨迹，平均关联分 0.765 / 0.755 / 0.760 |
| 键盘（两个实物） | track 3、track 4 各 5/6 帧；另有 1 次灰区重复记录 |
| 位置变化查询 | 鼠标 4 次区域迁移被正确检出 |

### 6.3 性能实测（CPU，[`perf_measurements.txt`](evidence/perf_measurements.txt)）

| 项目 | 实测 |
|---|---|
| OWLv2 模型加载 | 13.96 s（冷启动一次） |
| OWLv2 单帧检测（640×480，3 次） | 10.62 / 6.64 / 6.24 s，均值 7.83 s |
| DINOv2 模型加载 | 0.40 s |
| DINOv2 5 个裁剪图 embedding | 0.532 s（384 维） |
| 结论 | 满足 30–60 s 低频抓拍；不适合实时视频流 |

---

## 7. 异常与边界场景检查

| 场景 | 预期行为 | 结果 | 证据 |
|---|---|---|---|
| 上传非 JPEG | 400 + 明确原因 | ✅ | `tests/test_api.py::test_upload_observe_endpoint` |
| 空查询 / 超长查询 | 422 参数校验 | ✅ | `test_api_failures.py` |
| 查询不存在的抓拍/裁剪图 | 404 | ✅ | `test_api_failures.py` |
| 采集源不可用（回放目录为空/设备离线） | 503 + 错误原因，不静默成功 | ✅ | `test_api_failures.py`；实际运行中观察到明确错误 JSON |
| 设备重复 seq（重试） | 幂等，不重复入库 | ✅ | `test_pipeline.py`、`test_db.py` |
| 设备照片 seq 过期 | 拒绝旧图冒充新图 | ✅ | `test_sources.py::test_esp32_stale_seq_is_rejected` |
| 设备时间未同步 | 时间字段 NULL，界面/回答明确标注 | ✅ | `test_pipeline.py`、`test_sources.py` |
| 记录时间在未来 | 提示「时间异常」而非负数 | ✅ | `test_config_util.py` |
| 检测器崩溃 | 抓拍失败但不丢图，capture 标 `detect_failed` | ✅ | `test_pipeline.py` |
| 关联处于灰区 | 新建轨迹 + 候选表 + 界面「关联待确认」 | ✅ | 真机 frame4 鼠标（0.77）；演示 frame4 键盘；`link_candidates` |
| 查询词表外物品 | 明确「没有找到」并列出已记录物品与可能原因 | ✅ | 浏览器检查；真机/演示 `query_battery` |
| 未同步帧的时间排序 | 查询按入库顺序，不按伪造时间 | ✅ | `findy/query.py` 实现与注释 |

---

## 8. 硬件验收状态（已通过小样本真机验收）

- **设备连接**：ESP32-S3-EYE v2.2 通过 USB（COM10）连接，M1 固件运行，串口确认 `Web UI ready`；设备 IP `<device-ip>`，SNTP 同步成功。
- **真机端到端**：6 次抓拍 → 检测 → 关联 → 入库 → 中文查询 → UI 展示全部跑通（见 §5.2、§6.1）。
- **覆盖能力**：真实桌面物品（鼠标、键盘、手机/笔记本、充电器、耳机、钥匙）被检测并记录；固定机位下主要物品稳定关联到同一轨迹。
- **仍不覆盖**：多天/长时间关联、设备断线重连、镜头被移动后的重新标定、同款多件区分；这些需要后续运行与实验，不在本次验收结论内。

> 未连接时曾以 mock 固件服务验证适配器语义（seq、时间、过期图、未同步），该部分单测保留在 `tests/test_sources.py`。

---

## 9. 安全、依赖与配置检查

| 检查 | 结果 | 说明 |
|---|---|---|
| 仓库密钥扫描 | ✅ 无命中 | 扫描 `password/api_key/secret/token` 模式，0 命中；设备 IP 在证据中已脱敏 |
| 敏感数据入库 | ✅ 已忽略 | `.gitignore` 覆盖 `.venv*`、`data/`、`models/`、`*.sqlite*`、`config/*.local.yaml`、`.tmp/`、日志 |
| 真机图像隐私 | ✅ 未入库 | 原始帧/裁剪图/UI 截图仅本机验证，验证后删除；仓库只保留脱敏元数据 |
| 网络暴露面 | ✅ 仅本机 | 验收服务均监听 `127.0.0.1`；运行期只与局域网设备通信，不调用云端 API |
| 依赖许可 | ✅ 已核对 | torch BSD-3、transformers Apache-2.0、pillow HPND、numpy BSD-3、fastapi MIT、uvicorn BSD-3、pydantic MIT、httpx BSD-3、PyYAML MIT、jinja2 BSD-3、pytest MIT、python-multipart Apache-2.0、tzdata Apache-2.0；**刻意不使用 Ultralytics（AGPL-3.0）** |
| 模型许可 | ✅ 已记录 | OWLv2：HF 实现 Apache-2.0 系；DINOv2：官方 model card 标注 Apache-2.0（商用前建议再核对拉取当次仓库说明） |
| 配置完整性 | ✅ | `config/findy.yaml` 无凭据；ESP32 IP 为占位符；词表/阈值/区域在版本控制内 |
| 日志 | ✅ | 运行日志写 `data/server.log`（gitignored）；不向外部发送图像/查询 |
| Git 工作区 | ✅ | 本轮改动提交在当前分支 `feature/local-workers-bundle`；未 push、未合并、未做破坏性操作 |

---

## 10. 验收过程中发现并修复的问题

| # | 问题 | 影响 | 修复 |
|---|---|---|---|
| 1 | `web/static/app.js` 中 `text ?? x || ""` 混用导致整页 JS 语法错误 | 界面完全无法工作 | 加括号修正；`node --check` 通过 |
| 2 | 默认配置回放目录为不存在的 `samples/frames` | 抓拍 503 | 改为 `data/demo_frames` 并在 README 说明 |
| 3 | `crops/<capture_id>` 目录未创建 | 首次抓拍崩溃 | 检测前 `mkdir` |
| 4 | Python 3.14 缺 `tzdata` | `ZoneInfoNotFoundError` | 安装并加入 `requirements.txt` |
| 5 | 「最后位置」按 `time_synced` 优先排序 | 未同步的新帧可能排到旧帧之后 | 改为按 `detection_id` 入库顺序排序 |
| 6 | 历史记录把显示条数当总次数 | 回答不准确 | 用 `track_sighting_count` 显示总次数并注明最近 N 次 |
| 7 | 数量查询不区分灰区重复轨迹 | 数量虚高且无解释 | 增加「其中 N 个关联不确定」说明 |
| 8 | 开发环境 pip 因临时目录不可用而挂起 | 环境搭建受阻 | 将 TMP/TEMP 指向 `data/tmp` 后恢复（环境问题，已记录） |
| 9 | **真机首轮关联大量重复轨迹**（同一手机/笔记本/充电器被记成多条） | 查询出现「找到 3 个可能…」 | 增加**固定机位空间先验**：当前 bbox 与轨迹最近 bbox 的 IoU 作为加分项（`matching.spatial_bonus=0.15`）；真机复测主要物品 6/6 帧关联、相似度 1.00；单测覆盖 `bbox_iou` |
| 10 | 颜色标签出现「天蓝/橙色」等不准确描述 | 物品命名不够自然 | 记录为已知限制（颜色受背景/白平衡影响）；不影响按类别查询与定位 |

---

## 11. 未验证 / 已知限制

1. **真实场景精度没有 ground truth**：真机仅 6 帧小样本，未测 Acc@1/FAR/UR；需按 [A 文档 §4](../research/A_detection_reid.md) 做 1–2 天多物品、多时段实验后校准阈值。
2. **同款多件**：两支一样的笔/同款鼠标可能被记为多条轨迹；界面标「关联待确认」，支持人工合并；用户注册照功能未实现。
3. **开放词表误检/漏检**：真实桌面仍有误检（如把线缆/白物识别成充电器/鼠标）与漏检（钥匙仅 2 帧、置信度 0.22）；界面显示置信度，不隐藏。
4. **位置粒度**：仅画面命名区域（桌面左/中/右等），不是三维坐标；区域需手写 `zones.yaml` 标定。
5. **单帧延迟**：CPU 上 OWLv2 6.2–10.6 s，自动采集间隔需 ≥30–60 s；未做量化/ONNX/GPU 优化。
6. **未实现**：变化检测触发、保留/清理策略、断线重连、NTP 漂移处理、鉴权与局域网访问控制、多相机、中文 CLIP 语义召回、SIFT 几何校验、可视化区域标定页。
7. **长期运行**：未做 >1000 帧、跨天、设备重启后的容量/稳定性测试。

---

## 12. 复现命令

```powershell
cd D:\Findyy
.\.venv\Scripts\Activate.ps1          # 或使用你本机可用的 Python 3.11+ 环境
python -m pip install -r requirements.txt
python tools\download_models.py       # OWLv2 + DINOv2
python tools\make_demo_frames.py      # 生成 6 帧演示序列（首次会下载 COCO 公开图）

# 清空后重新灌入演示数据
Remove-Item data\findy.sqlite* -Force -ErrorAction SilentlyContinue
python -m findy replay --dir data/demo_frames

# 自动化测试
python -m pytest tests -q             # 期望 75 passed

# 演示数据浏览器验收（需本机 Chrome；Playwright 已安装）
python -m findy serve
python tools\browser_acceptance.py http://127.0.0.1:8765

# 真机验收（设备在线时）
$env:FINDY_CAPTURE_SOURCE='esp32'
$env:FINDY_ESP32_URL='http://<设备IP>'
$env:FINDY_DB_PATH='data/hardware.sqlite'
$env:FINDY_IMAGES_DIR='data/hardware_images'
$env:FINDY_CROPS_DIR='data/hardware_crops'
python tools\hardware_acceptance.py --count 6 --interval 3 --queries
python -m findy serve --port 8766
python tools\hardware_browser_check.py http://127.0.0.1:8766

# 命令行查询示例
python -m findy query "笔记本电脑最后出现在哪里？"
python -m findy query "鼠标移动过吗？"
```

---

## 13. 附件

- [`docs/evidence/hardware/`](evidence/hardware/) — 真机验收证据（脱敏）：6 帧结果、汇总、UI 报告
- [`docs/evidence/`](evidence/) — pytest 日志、演示浏览器报告与截图、演示回放原始结果、指标与性能实测、查询用例
- [`docs/research/A_detection_reid.md`](../research/A_detection_reid.md) — 检测与实例关联调研
- [`docs/research/B_retrieval_storage_query.md`](../research/B_retrieval_storage_query.md) — 检索/存储/查询调研
- [`docs/research/C_architecture_decision.md`](../research/C_architecture_decision.md) — 架构决策与风险
- [`docs/PROJECT_STATUS.md`](../PROJECT_STATUS.md) — 项目状态与下一步
