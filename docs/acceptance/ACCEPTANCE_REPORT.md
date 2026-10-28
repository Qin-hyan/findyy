# Findy MVP 验收报告

- 验收日期：2026-10-28（Asia/Shanghai）
- 验收范围：阶段一调研结论落地情况、阶段二 MVP 核心闭环、阶段三端到端与异常/安全/文档检查
- 验收对象：本仓库 `D:\Findyy`（MVP 代码 + 配置 + 测试 + 文档）
- 关联硬件：ESP32-S3-EYE v2.2 + OV2640，M1 固件独立仓库 `D:\Findy-Firmware`（实机 100/100 拍摄证据见其 `docs/M1_RESULTS.md`）

---

## 1. 结论摘要

| 结论 | 数量 | 说明 |
|---|---|---|
| ✅ 通过 | 13 | 核心闭环、自动化测试、浏览器交互、异常输入、时间语义、持久化、安全检查等 |
| 🟡 部分通过 | 4 | 关联准确率只有演示数据、误检存在、硬件适配器仅 mock 验证、位置仅画面区域 |
| ❌ 失败 | 0 | 未发现验收标准内的失败项 |
| ⛔ 未验证 | 5 | 真实 ESP32 端到端、真实场景精度、同款多件、长期稳定性、多用户/鉴权 |

**总体判断**：Findy MVP 在「本机 + 公开演示数据」范围内完成了可运行、可验证的物品记忆闭环，功能、异常处理与文档达到可验收状态；**真实硬件与真实场景精度未完成验证，不能声称已通过**。阻塞原因（设备未连接）与所需操作在 §8 明确列出。

---

## 2. 验收环境

| 项目 | 值 |
|---|---|
| 操作系统 | Windows 11 家庭中文版 10.0.26100 |
| CPU / 内存 | Intel Core i7-14650HX（16 核 / 24 线程）/ 15.7 GB |
| Python | 3.14.3（`D:\python\python1` 为基础，`D:\Findyy\.venv314` 继承其 torch 等站点包） |
| 关键依赖 | torch 2.10.0+cpu、transformers 5.2.0、fastapi 0.115.6、uvicorn 0.41.0、pydantic 2.12.5、httpx 0.28.1、pytest 8.3.4、pillow 11.3.0、numpy 2.4.2、PyYAML 6.0.3、jinja2 3.1.6、python-multipart 0.0.20、tzdata 2026.5 |
| 模型 | OWLv2 `google/owlv2-base-patch16-ensemble`（本地 591.2 MB safetensors）、DINOv2 `facebook/dinov2-small`（84.2 MB） |
| 浏览器验收 | 本机 Chrome（Playwright 1.64.0，`channel=chrome`，headless） |
| 采集方式 | 图片回放（公开 COCO val2017 图片 + 变换模拟多时刻）；ESP32 适配器用本地 mock 固件服务单测 |

> 环境说明：本机 Anaconda Python 3.11 自带的 torch 2.11 出现 `c10.dll` 初始化失败（环境问题，非本项目代码），因此验收使用可正常加载的 Python 3.14 + torch 2.10 CPU 环境；`requirements.txt` 对 Python 3.11+ 通用，未绑定该机器。

---

## 3. 核心功能验收矩阵（阶段二 7 项闭环）

| # | 验收项 | 结果 | 证据 |
|---|---|---|---|
| 1 | 获取摄像头图像 | ✅ 通过（回放源）/ 🟡 部分（真机未验） | `findy/sources.py`；回放 6 帧全部入库；ESP32 HTTP 适配器（`POST /api/capture` → `GET /api/photo?seq=N`）由 `tests/test_sources.py` 的 mock 固件服务验证 seq/时间/未同步/过期图拒绝 |
| 2 | 检测/识别图像中的物品 | ✅ 通过（开放词表） | OWLv2 在 6 帧演示图上每帧识别 4–5 个物品（29 次检测）；词表 23 类可配置；逐类阈值与 NMS 有单测 |
| 3 | 保存观测记录、图像、时间、区域 | ✅ 通过 | SQLite `captures/detections/tracks` + `data/images`/`data/crops`；时间双字段（`captured_at`/`received_at`）+ `time_source`；区域多边形判定有单测 |
| 4 | 跨时刻关联同一实物、处理不确定 | ✅ 通过（演示数据） | 6 帧 29 次检测中 23 次自动关联、1 次灰区待确认、5 次新物品；三态阈值与候选表、人工合并接口；**真实精度未测** |
| 5 | 自然语言查询最后位置 | ✅ 通过 | 11 条查询用例（`docs/evidence/query_battery.txt`）：最后位置/历史/移动/数量/清单/存在/查不到/帮助均返回合理中文回答 |
| 6 | 展示匹配物品、图像、时间、依据 | ✅ 通过 | 浏览器验收 12 项全过；回答含区域、时间、置信度、关联相似度、证据图；证据卡片可点击回看原帧与检测框 |
| 7 | 可实际使用的界面与运行状态 | ✅ 通过 | 单页界面：状态栏、最近画面与检测框、物品库、时间线、抓拍/自动采集、查询；`/api/status` 暴露模型/数据库/采集源/自动采集状态 |

---

## 4. 自动化测试结果

命令：`python -m pytest tests -q`（日志：[`docs/evidence/pytest_run.log`](evidence/pytest_run.log)）

```
73 passed, 486 warnings in 7.26s
```

- **0 失败、0 跳过**；486 条 warning 全部为第三方库弃用提示（FastAPI `on_event`、starlette/anyio 对 Python 3.16 的弃用警告），不影响功能。
- 覆盖模块：图像处理与颜色特征、关联打分与三态、区域多边形、中文意图解析、SQLite 幂等/合并/统计、主流水线（检测失败、时间未同步、重复 seq、移动检测）、HTTP API（状态/抓拍/上传/查询/物品/抓拍图/裁剪图/服务开关/异常 503/404/422）、ESP32 适配器（mock 固件服务）、配置加载与环境变量覆盖、时间/哈希工具。
- 关键断言示例：同一物品重复观测绑定同一 track；移动后区域变化可被 `moved` 查询发现；未同步帧的时间字段为 NULL 且回答明确提示；检测器崩溃时抓拍返回失败并把 capture 标记为 `detect_failed`，图片仍保留排障。

---

## 5. 浏览器端到端验收

命令：`python tools/browser_acceptance.py http://127.0.0.1:8765`（Chrome + Playwright，headless）
证据：[`docs/evidence/browser_report.json`](evidence/browser_report.json)、[截图目录](evidence/screenshots/)

**12/12 通过，控制台错误 0，失败请求 0。**

| # | 检查 | 结果 |
|---|---|---|
| 1 | 状态栏显示数据库统计（6 帧 / 6 物品） | ✅ |
| 2 | 状态栏显示模型就绪（OWLv2 + DINOv2） | ✅ |
| 3 | 物品库渲染卡片（6 件） | ✅ |
| 4 | 时间线渲染缩略图（6 帧） | ✅ |
| 5 | 查询「笔记本电脑最后出现在哪里？」返回「桌面左侧」+ 时间 + 依据 | ✅ |
| 6 | 查询结果渲染证据卡片 | ✅ |
| 7 | 查询「鼠标移动过吗？」返回 4 次区域迁移及时间 | ✅ |
| 8 | 查询「钥匙在哪？」明确说明没有记录，并提示可能原因 | ✅ |
| 9 | 点击「立即抓拍」触发真实流水线（本次识别到 5 个物品） | ✅ |
| 10 | 抓拍后图像可见（naturalWidth > 0） | ✅ |
| 11 | 抓拍后在画面上绘制检测框 | ✅ |
| 12 | 点击时间线可回看历史帧并绘制检测框 | ✅ |

界面截图：

| 首页 | 查询结果 |
|---|---|
| ![首页](evidence/screenshots/01_home.png) | ![查询](evidence/screenshots/02_query_last_seen.png) |

---

## 6. 演示数据指标（如实口径）

数据来源：`docs/evidence/demo_replay_default.json`（6 帧回放）、`docs/evidence/demo_metrics.json`。
**重要限制**：演示帧是**同一张公开 COCO 书桌图片**经亮度/平移/轻微旋转变换生成，模拟「不同时间、不同取景」，不是真实设备录像；场景中真实实物为同一批 5 件（手机、笔记本、2 个键盘、鼠标）。

| 指标 | 实测值 |
|---|---|
| 帧数 | 6 |
| 检测总数 | 29（每帧 5 / 5 / 5 / 5 / 4 / 5） |
| 关联判定 | matched 23、ambiguous 1、new 5 |
| 手机 | 6/6 帧关联到同一轨迹，平均关联分 0.765 |
| 笔记本电脑 | 6/6 帧，平均 0.756 |
| 鼠标 | 6/6 帧，平均 0.761 |
| 键盘（两个实物） | track 3：5/6 帧，平均 0.713；track 4：5/6 帧；另有 1 次灰区重复记录（frame 4） |
| 误合并 | **本演示中未观察到**（无实例级 ground truth，因此不能给出关联精确率/召回率） |
| 位置变化查询 | 鼠标 4 次区域迁移被正确检出（中央→右→左→右→中央） |

### 性能实测（`docs/evidence/perf_measurements.txt`，CPU）

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
| 空查询 / 超长查询 | 422 参数校验 | ✅ | `tests/test_api.py`、`test_api_failures.py` |
| 查询不存在的抓拍/裁剪图 | 404 | ✅ | `test_api_failures.py` |
| 采集源不可用（回放目录为空） | 503 + 错误原因，不静默成功 | ✅ | `test_api_failures.py::test_capture_returns_503_when_source_unavailable`；实际运行中也观察到 `{"error":"回放目录中没有图片: ..."}` |
| 设备重复 seq（重试） | 幂等，不重复入库 | ✅ | `test_pipeline.py::test_duplicate_device_seq_is_idempotent`、`test_db.py` |
| 设备照片 seq 过期 | 拒绝旧图冒充新图（SourceError） | ✅ | `test_sources.py::test_esp32_stale_seq_is_rejected` |
| 设备时间未同步 | 时间字段为 NULL，界面/回答明确标注「未同步」 | ✅ | `test_pipeline.py::test_unsynced_time_is_reported_not_faked`、`test_sources.py` |
| 记录时间在未来 | 提示「时间异常」而非负数 | ✅ | `test_config_util.py`（humanize） |
| 检测器崩溃 | 抓拍失败但不丢图，capture 标 `detect_failed` | ✅ | `test_pipeline.py::test_detector_failure_is_recorded_not_swallowed` |
| 关联处于灰区 | 新建轨迹 + 候选表 + 界面「关联待确认」提示 | ✅ | 演示 frame 4 键盘；`link_candidates` 表；`test_matcher.py` |
| 查询词表外物品 | 明确「没有找到」并列出已记录物品与可能原因 | ✅ | 浏览器检查 8；`query_battery.txt` |
| 时间单调性（未同步帧） | 查询按入库顺序排序，不按伪造时间 | ✅ | `findy/query.py` 排序注释与实现 |

---

## 8. 硬件验收状态（未验证，阻塞原因明确）

- 验收时 ESP32-S3-EYE **未连接到本机**：串口列表中没有 `COM10`/`VID_303A` 设备，局域网 ARP 中也没有设备地址。
- 因此**无法执行**：真实设备抓拍 → 真实时间 → MVP 入库 → 查询的端到端验证；也没有做真机长时间运行。
- 已完成替代验证：`Esp32Source` 对 M1 固件 API 的语义（`POST /api/capture` 返回记录、`GET /api/photo?seq=N` + `X-Capture-Seq`、未同步时间、503/异常）用本地 mock 固件服务做了集成测试；M1 固件自身的实机 100/100 连拍证据在其独立仓库 `D:\Findy-Firmware\docs\M1_RESULTS.md`（2026-10-26，COM10，100/100 成功）。
- **复验所需操作（需用户执行）**：设备上电 → USB 连接 → 烧录/确认运行 M1 固件 → 同一 Wi-Fi 下记录设备 IP → 在 `config/findy.yaml` 设 `capture.source: esp32`、`esp32.base_url: http://<IP>` → `python -m findy esp32 --url http://<IP>` 自检 → `python -m findy serve` 后点击抓拍/自动采集复验。

---

## 9. 安全、依赖与配置检查

| 检查 | 结果 | 说明 |
|---|---|---|
| 仓库密钥扫描 | ✅ 无命中 | 对 `.py/.yaml/.md/.html/.js/.json/.txt`（排除虚拟环境/数据/模型）扫描 password/api-key/secret/token 模式，0 命中 |
| 敏感数据入库 | ✅ 已忽略 | `.gitignore` 覆盖 `.venv*`、`data/`、`models/`、`*.sqlite*`、`config/*.local.yaml`、`.tmp/`、日志 |
| 网络暴露面 | ✅ 仅本机 | 服务默认/验收均监听 `127.0.0.1:8765`；运行期不调用云端 API；仅模型下载阶段访问 HF/镜像 |
| 依赖许可 | ✅ 已核对 | torch BSD-3、transformers Apache-2.0、pillow HPND、numpy BSD-3、fastapi MIT、uvicorn BSD-3、pydantic MIT、httpx BSD-3、PyYAML MIT、jinja2 BSD-3、pytest MIT、python-multipart Apache-2.0、tzdata Apache-2.0；**刻意不使用 Ultralytics（AGPL-3.0）** |
| 模型许可 | ✅ 已记录 | OWLv2：HF 实现 Apache-2.0 系；DINOv2：官方 model card 标注 Apache-2.0（商用前建议再核对拉取当次仓库说明） |
| 配置完整性 | ✅ | `config/findy.yaml` 无凭据；ESP32 IP 为占位符；词表/阈值/区域均在版本控制内 |
| 日志 | ✅ | 运行日志写 `data/server.log`（gitignored）；不记录图像内容与查询明文到外部 |
| Git 工作区 | ✅ | 本轮改动提交在当前分支 `feature/local-workers-bundle`；未 push、未合并、未做破坏性操作 |

---

## 10. 验收过程中发现并修复的问题

| # | 问题 | 影响 | 修复 |
|---|---|---|---|
| 1 | `web/static/app.js` 中 `text ?? x || ""` 混用导致整页 JS 语法错误 | 界面完全无法工作 | 加括号修正；`node --check` 通过 |
| 2 | 默认配置回放目录为不存在的 `samples/frames` | 抓拍 503 | 改为 `data/demo_frames` 并在 README 说明 |
| 3 | `crops/<capture_id>` 目录未创建 | 首次抓拍崩溃 | 检测前 `mkdir` |
| 4 | 自动采集/回放时 Python 3.14 缺 `tzdata` | `ZoneInfoNotFoundError` | 安装并加入 `requirements.txt` |
| 5 | 「最后位置」按 `time_synced` 优先排序，未同步的新帧可能排到旧帧之后 | 违反「最后出现」语义 | 改为按 `detection_id` 入库顺序排序 |
| 6 | 历史记录把「显示条数」当成「总次数」 | 回答不准确 | 用 `track_sighting_count` 显示总次数并注明最近 N 次 |
| 7 | 数量查询不区分灰区重复轨迹 | 数量可能虚高且无解释 | 增加「其中 N 个关联不确定」说明 |
| 8 | 开发环境 pip 因临时目录不可用而挂起 | 环境搭建受阻 | 将 TMP/TEMP 指向 `data/tmp` 后恢复（环境问题，已记录） |

---

## 11. 未验证 / 已知限制

1. **真实 ESP32 硬件端到端未验证**（设备未连接，见 §8）。
2. **真实场景精度未验证**：演示数据为公开图片变换；检测召回率、关联 Acc@1/FAR/UR 没有 ground truth，未测。需按 [A 文档 §4](../research/A_detection_reid.md) 做 1–2 天小样本实验后重新校准阈值。
3. **开放词表误检**：偶发把音箱/支架识别为「充电器/苹果」等；已通过逐类阈值压低，但仍存在。界面显示置信度，不隐藏。
4. **同款多件**：两支一样的笔可能被记为两条轨迹；界面标「关联待确认」并把候选写入 `link_candidates`，需人工合并；用户注册照功能未实现。
5. **位置粒度**：仅画面命名区域（桌面左/中/右等），不是三维坐标；区域需手写 `zones.yaml` 标定。
6. **单帧延迟**：CPU 上 OWLv2 6.2–10.6 s，自动采集间隔需 ≥30–60 s；未做模型量化/ONNX 优化。
7. **未实现**：变化检测触发、保留/清理策略、断线重连、NTP 漂移处理、鉴权与局域网访问控制、多相机、中文 CLIP 语义召回、SIFT 几何校验、可视化区域标定页。
8. **演示数据版权**：演示画面来自公开 COCO val2017 图片（`000000001503.jpg`），仅用于技术演示；`data/` 已忽略，不随仓库分发原图。

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
python -m pytest tests -q             # 期望 73 passed

# 启动并做浏览器验收（需本机 Chrome；Playwright 已安装）
python -m findy serve
python tools\browser_acceptance.py http://127.0.0.1:8765

# 命令行查询示例
python -m findy query "笔记本电脑最后出现在哪里？"
python -m findy query "鼠标移动过吗？"
```

---

## 13. 附件

- [`docs/research/A_detection_reid.md`](../research/A_detection_reid.md) — 检测与实例关联调研
- [`docs/research/B_retrieval_storage_query.md`](../research/B_retrieval_storage_query.md) — 检索/存储/查询调研
- [`docs/research/C_architecture_decision.md`](../research/C_architecture_decision.md) — 架构决策与风险
- [`docs/evidence/`](evidence/) — pytest 日志、浏览器报告与截图、演示回放原始结果、指标与性能实测
- [`docs/PROJECT_STATUS.md`](../PROJECT_STATUS.md) — 项目状态与下一步