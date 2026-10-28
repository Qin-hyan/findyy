# Findy · 物品记忆助手（MVP）

Findy 用固定摄像头观察桌面环境，识别物品并记录**图像 / 时间 / 画面区域**，尽量把不同时刻出现的**同一件实物**关联起来，最后让你用一句中文问出「我的东西最后在哪」。

本仓库是 Findy 项目的**阶段二/三交付物**：在已验证的 ESP32-S3-EYE M1 采集固件之上，实现完整的本机视觉记忆闭环（检测 → 记录 → 关联 → 查询 → 展示）。全部推理与数据都留在本机。

![Findy 界面](docs/evidence/screenshots/01_home.png)

---

## 1. 当前状态（2026-10-28）

| 阶段 | 状态 | 说明 |
|---|---|---|
| 阶段一：调研 | ✅ 完成 | 市场/需求证据、检测与 re-ID、检索/存储/查询技术路线；见 [`docs/research/`](docs/research/) |
| 阶段二：MVP 研发 | ✅ 完成（本机可运行） | 检测、实例关联、历史存储、中文查询、Web 界面、自动采集、测试 |
| 阶段三：验收 | ✅ 完成（小样本真机） | 真机 6/6 抓拍、38 次检测、75 项自动化与浏览器验收通过；长期稳定性/精度量化未验，详见 [`docs/acceptance/ACCEPTANCE_REPORT.md`](docs/acceptance/ACCEPTANCE_REPORT.md) |

**已验证**：真实 ESP32 6/6 抓拍、38 次检测、8 条轨迹，5 类主物品 6/6 帧关联同一轨迹；演示 6 帧闭环；75 个自动化测试通过；Chrome/Playwright 演示 12/12、真机 7/7；异常路径有测试或实测记录。

**未验证/限制**：真实场景量化精度（无 ground truth）、同款多件区分、长期运行稳定性未测；开放词表仍有误检/漏检；位置是「画面区域」而非三维坐标。所有细节见验收报告与 [架构决策](docs/research/C_architecture_decision.md)。

---

## 2. 它具体能做什么

1. **采集**：从 ESP32-S3-EYE M1 固件 HTTP 接口抓拍（也支持图片回放/上传），记录真实 SNTP 时间；未同步时明确标记、绝不伪造。
2. **识别**：OWLv2 开放词表检测，词表在 [`config/objects.yaml`](config/objects.yaml) 可配置（钥匙、钱包、眼镜、耳机、充电器、杯子、手机、笔记本、鼠标、键盘……），每个类别有独立阈值。
3. **记忆**：SQLite 保存每次观测的图片、时间、画面区域、检测框、置信度与外观向量；图片/裁剪图存本地文件系统。
4. **关联**：DINOv2 外观 embedding + 颜色直方图 + 区域先验 + 时间衰减打分，输出 `matched / ambiguous / new` 三态；灰区会保留候选并提示人工确认，而不是硬猜。
5. **查询**：中文规则解析（意图 + 物品别名 + 颜色/区域/时间），支持「最后位置 / 历史记录 / 是否移动 / 数量 / 区域清单 / 是否存在 / 帮助」。
6. **展示**：单页界面显示最近画面与检测框、带证据图的中文回答、物品库、观测时间线、运行状态；回答附带时间、区域、置信度、关联相似度和限制说明。

---

## 3. 快速开始（Windows，Python 3.11+）

```powershell
# 0) 进入仓库
cd D:\Findyy

# 1) 建虚拟环境并安装依赖（CPU 版 torch 即可，不需要显卡）
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt

# 2) 下载两个本地模型（OWLv2 约 620MB + DINOv2-small 约 88MB；国内会自动用 hf-mirror）
python tools\download_models.py

# 3) 生成演示抓拍序列（首次会从 COCO 官方地址下载一张公开书桌图片）
python tools\make_demo_frames.py

# 4) 回放演示序列，写入本地数据库（首次约 1 分钟，CPU 推理）
python -m findy replay --dir data/demo_frames

# 5) 启动界面
python -m findy serve
# 浏览器打开 http://127.0.0.1:8765
```

> 想清空重来：删除 `data/findy.sqlite*`、`data/images/`、`data/crops/` 即可（都在 `.gitignore` 内）。
> 若 `pip install` 后 `import torch` 报 DLL 初始化失败（本机 Anaconda 曾出现），请改装 CPU 版 torch（`pip install torch --index-url https://download.pytorch.org/whl/cpu`），或使用一个能正常加载 torch 的 Python 环境；验收环境说明见 [验收报告 §2](docs/acceptance/ACCEPTANCE_REPORT.md)。
> 模型也可以改成 HuggingFace 仓库 id（`config/findy.yaml` 的 `detector.model` / `embedder.model`），或设置环境变量 `FINDY_DETECTOR_MODEL` / `FINDY_EMBEDDER_MODEL`。

### 接真实设备（ESP32-S3-EYE）

1. 设备烧录并启动 Findy M1 固件（独立仓库 `D:\Findy-Firmware`），连上同一 Wi-Fi，记下串口打印的设备 IP。
2. 修改 `config/findy.yaml`：

```yaml
capture:
  source: esp32
  esp32:
    base_url: "http://<设备IP>"
```

3. 自检设备接口：`python -m findy esp32 --url http://<设备IP>`（会调用 `/api/status`）。
4. 启动服务，点「立即抓拍」；或点「开始自动采集」，按 `capture.interval_seconds` 定时抓拍。

> 设备接口语义与 seq 校验见 [架构决策](docs/research/C_architecture_decision.md) 与固件仓库 README。设备离线时抓拍会返回 503 并显示明确错误，不会静默失败。

---

## 4. 常用命令

| 命令 | 作用 |
|---|---|
| `python -m findy serve` | 启动 Web 服务（默认 `127.0.0.1:8765`） |
| `python -m findy status` | 打印配置、模型文件是否存在、数据库统计 |
| `python -m findy capture` | 从当前采集源抓拍一次并入库 |
| `python -m findy query "我的鼠标最后在哪？"` | 命令行执行一次自然语言查询 |
| `python -m findy replay --dir data/demo_frames` | 回放一个图片目录（验收/演示） |
| `python -m findy esp32 --url http://<IP>` | 探测设备状态 |
| `python -m pytest tests -q` | 运行 75 个自动化测试 |
| `python tools\browser_acceptance.py http://127.0.0.1:8765` | 用本机 Chrome 做 12 项真实浏览器验收并截图 |

---

## 5. HTTP API（界面使用的同一套接口）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/status` | 配置、模型状态、数据库统计、采集源、自动采集状态 |
| POST | `/api/capture` | 从配置的采集源抓拍一次 → 检测/关联/入库 |
| POST | `/api/observe` | 上传一张图片入库（可带 `captured_at_utc`） |
| POST | `/api/query` | `{"text": "..."}` → 中文回答 + 结果 + 证据 |
| GET | `/api/objects` | 物品库（轨迹 + 最近一次观测） |
| GET | `/api/tracks/{id}` | 单件物品详情与观测时间线 |
| POST | `/api/tracks/{id}/label` | 给物品改名 |
| POST | `/api/tracks/merge` | 人工确认「这是同一件」并合并轨迹 |
| GET | `/api/captures?limit=N` | 最近抓拍列表 |
| GET | `/api/captures/{id}/image?thumb=1` | 抓拍原图/缩略图 |
| GET | `/api/detections/{id}/crop` | 检测裁剪图 |
| POST | `/api/service/start` / `stop` | 启动/停止自动采集 |
| GET | `/api/health` | 存活与数据库连通性 |

---

## 6. 目录结构

```
Findyy/
├── findy/                  # MVP Python 包（采集源、检测、embedding、关联、存储、查询、API）
├── web/                    # 单页界面（HTML/CSS/JS，无构建步骤）
├── config/
│   ├── findy.yaml          # 运行配置（采集源、模型、阈值）
│   ├── objects.yaml        # 物品词表 + 中文别名 + 逐类阈值
│   └── zones.yaml          # 画面区域（归一化多边形）
├── tools/                  # 模型下载、演示数据、验收脚本
├── tests/                  # pytest（75 项）
├── docs/
│   ├── research/           # 阶段一调研 A/B + 架构决策 C
│   ├── acceptance/         # 验收报告
│   └── evidence/           # 测试/浏览器/指标证据
├── data/                   # 运行数据（gitignored：图片、数据库、模型缓存）
└── models/                 # 本地模型权重（gitignored）
```

历史遗留的 `report.md`、`assets/`、顶层的竞品/调研文档是阶段一市场调研产物，与本 MVP 代码无关。

---

## 7. 隐私、安全与许可

- **全部本地**：图像、向量、查询文本都不出本机；默认只监听 `127.0.0.1`。若改为局域网监听，必须自行补鉴权（当前没有）。
- **不启用本机摄像头**：`capture.source` 只提供 `esp32 / replay` 实际路径；`webcam` 需要额外安装 OpenCV 且有隐私风险，MVP 不启用。演示数据来自公开 COCO 图片。
- **凭据不入库**：仓库不含任何 Wi-Fi 密码/令牌；`config/*.local.yaml`、`data/`、`models/`、`.venv/` 均已忽略。
- **模型许可**：检测用 OWLv2（HuggingFace 实现，Apache-2.0 系）、实例特征用 DINOv2（官方 model card 标注 Apache-2.0）；**刻意不依赖 Ultralytics（AGPL-3.0）**，避免闭源分发的传染风险。依赖清单与许可见验收报告。
- **位置表述**：界面只声称「画面区域」，不声称三维坐标；时间未同步时明确标注。

---

## 8. 已知限制（如实列出）

1. 演示数据是「一张公开书桌图片 + 变化模拟」，**不代表真实场景精度**；真实检测召回率、关联准确率需要现场小样本实验（方法见 [`docs/research/A_detection_reid.md`](docs/research/A_detection_reid.md) §4）。
2. 开放词表检测存在误检/漏检；小物品（钥匙、U 盘）在低分辨率下尤其明显，词表阈值需按现场重新校准。
3. 实例关联没有公开基准，当前阈值是演示数据下的初始值；同款多件可能被记为多条轨迹（界面会标「关联待确认」，可人工合并）。
4. 单帧 CPU 推理约 6–11 秒（本机 i7-14650HX），自动采集间隔需 ≥30–60 秒。
5. 未实现：变化检测触发、保留策略/清理、用户注册照、SIFT 几何校验、鉴权、多相机、三维定位。
6. 真实 ESP32 硬件端到端尚未验证（验收时设备未连接）；适配器语义已用 mock 固件服务单测覆盖。

---

## 9. 文档

- 调研：[A 检测与实例关联](docs/research/A_detection_reid.md) · [B 检索/存储/查询](docs/research/B_retrieval_storage_query.md) · [C 架构决策](docs/research/C_architecture_decision.md)
- 验收：[验收报告](docs/acceptance/ACCEPTANCE_REPORT.md) · [证据目录](docs/evidence/)
- 项目状态：[PROJECT_STATUS](docs/PROJECT_STATUS.md)

