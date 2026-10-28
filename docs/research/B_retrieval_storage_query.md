# B. 检索、存储与自然语言查询：技术选型调研

> 项目：Findy（桌面物品记忆助手）｜阶段：一（技术调研）｜撰写：research-b
> 日期：2026-10-28｜范围：仅覆盖任务书 B 部分（特征检索 / 存储与时空语义 / 中文 NL 查询 / 采集与成本 / 近邻案例）
> 约束：普通 Windows 笔记本、低成本、优先复用预训练模型、可离线
> **证据分级**：A＝本次直接抓取的一手页面/论文摘要/仓库 README；B＝官方文档或团队既有台账（带来源链接，本次未逐段复核）；C＝由 A/B 推导的判断、估算、行业常识；D＝未核实、仅方向性参考。全文凡估算均标"C"或"D"并写依据。

---

## 结论摘要

1. **特征与检索：两套 embedding 分工，而不是一套 CLIP 打天下。** 语义检索用中文 CLIP（`chinese-clip-vit-base-patch16`，188M 参数、224px、512 维）做"文本→物品裁切图"；同一实物跨时间的关联用 DINOv2 ViT-S/14（384 维、约 21M 参数）做实例特征，因其是自监督通用视觉特征、对实例外观更敏感 [R3][R5][R6]。两者都是预训练、可直接 CPU 推理、可导出 ONNX，符合"优先复用"约束。
2. **10 万条以内不要上向量数据库。** 10 万 × 512 维 float32 仅 205MB，numpy/BLAS 暴力内积一次 10k 条 <5ms、100k 条约 5–30ms（C，按 BLAS sgemm 吞吐推算，未在本机实测），且精确、100% 召回、零运维。`sqlite-vec` 适合"单文件部署"（C）；FAISS/hnswlib 留到 >10 万条或查询 >50ms 再引入 [R7][R8][R9]。
3. **存储：SQLite 元数据 + 文件系统图像 + 向量存 SQLite 扩展表，三者分离。** 元数据必须区分 `captured_at_utc`（设备 SNTP 时间）与 `received_at_utc`（笔记本收到时间），并带 `time_source` 字段；SNTP 未同步时**不要伪造时间**，记 `unsynced` + 设备 seq，同步后回填。区域用归一化多边形 + 命名区域，不做 3D/深度（单目 2D 无法获得真实深度，且成本翻倍）——schema 草案见 §2.4。
4. **中文查询：规则为主干、LLM 为增强、两者共用同一 QueryPlan 执行器。** 规则解析（jieba 自定义词典 + 别名表 + 意图模板）能覆盖"X 在哪/桌上有什么/有几个 X"这类 80% 高频问法且完全离线、可解释；LLM function calling（本地 0.5B–1.5B 或云端 API）只处理口语化/多条件句，失败即降级到规则。查询文本不外传，图像永不外传。
5. **采集：固定摄像头 + 30–120s 轮询 + 变化检测落盘，是成本与覆盖的最优折中。** 60s 一帧约 0.4–2.6GB/月原始帧（C，按 640×480 JPEG 30–60KB 计算）；常驻笔记本电费约 ¥12–26/月（C，30–60W × 24h × 0.5–0.6 元/kWh）。不建议云台/机器人，不建议常开视频。
6. **近邻案例的真空是真实的：没有任何量产产品同时具备"摄像头 + 物品级识别 + 长期记忆 + 中文自然语言检索"。** 最接近的 Camtells 只有 24 名众筹支持者且未发货；MemPal 是 N=15 的研究原型；Apple HomeView/Ugreen HomeAgent 是"家庭视频 + 事件检索"，不是"物品记忆"；Find My Everything 是免费 App 手动拍照建档 [R17][R19][R20][R21][R23]。差异点不在硬件，在"同一实物跨时刻关联 + 证据帧 + 口语查询"。

**推荐路线（一句话）**：SQLite 单文件 + 文件系统缩略图 + numpy 精确检索（后续换 sqlite-vec）+ 中文 CLIP 语义 / DINOv2 实例双塔 + 规则优先的中文 QueryPlan + ESP32-S3-EYE 定时变化触发采集。全程本地、无云依赖；M2 阶段先实测**中文 CLIP 在桌面小物体上的召回率**，这是全案最大技术不确定性。

---

## 0. 调研方法与本次局限（先读这一节，避免误引）

- **工具限制（重要）**：本会话 `web_search` 不可用（无搜索 API Key），改为**直接抓取指定 URL**（arXiv abs 页、GitHub README、jsDelivr 镜像的仓库 README、官方文档）。因此本报告**没有做穷尽式检索**，只覆盖了任务书点名的技术点；§5 的近邻案例能力表**复用团队既有证据台账**（[竞品与市场数据 2026-10-22](../../桌面记忆相机_竞品与市场数据_2026-10-22.md)、`research/notes.md`）并回填了其来源链接，未重新抓取每条竞品页面。
- **未做实测**：本机未运行任何基准、未训练/微调任何模型、未在 ESP32 上测延迟。所有延迟/精度/成本数字均为**推算或区间**，标 C/D；M2 必须实测校准（§6 列了必测清单）。
- **抓取失败记录（诚实披露）**：`export.arxiv.org` API、`raw.githubusercontent.com`、`html.duckduckgo.com`、ESP-IDF 的 ESP32-S3-EYE 用户指南页均抓取失败或 404；竞品页面未逐条重抓。凡依赖这些来源的陈述，不标 A。

---

## 1. 特征提取与相似度检索选型

### 1.1 模型候选对照

| 候选 | 维度 | 规模/分辨率 | 中文文本侧 | CPU 可行性 | 证据 |
|---|---|---|---|---|---|
| **中文 CLIP ViT-B/16**（`OFA-Sys/chinese-clip-vit-base-patch16`） | 512 | 总 188M；视觉 86M + 文本(RoBERTa-wwm-Base) 102M；224px | **原生中文**（约 2 亿中文图文对训练） | 单帧约 80–200ms（C，按参数量/分辨率推算） | A：README 给了参数量表、模型下载、ONNX/TensorRT 部署脚本 [R3][R4] |
| 中文 CLIP RN50 | 512 | 77M（视觉 38M），224px | 原生中文 | 更快，精度低于 ViT-B/16 | A：同上 |
| 中文 CLIP ViT-L/14 | 768 | 406M，224px | 原生中文 | 笔记本 CPU 偏重（约 0.3–1s/帧，C） | A |
| **CLIP（英文）ViT-B/32** | 512 | ~151M，224px | 弱（中英对齐差） | 快，约 30–80ms（C） | A：论文摘要（ResNet-50 级零样本）[R1]；维度/参数为 B（模型卡常识，未逐条核对） |
| **SigLIP**（base / SO400M） | 768 / 1152 | patch16 / patch14 | 弱（同 CLIP 系） | 中 | A：论文（sigmoid 损失、可小 batch、ICCV'23 Oral）[R6]；具体维度 B |
| **DINOv2 ViT-S/14** | 384 | ~21M，518px（可 224） | 无文本塔（纯视觉） | 快，约 20–60ms（C） | A：论文摘要（1B 教师蒸馏出小模型）[R5]；参数/维度 B |
| DINOv2 ViT-B/14 | 768 | ~86M | 无 | 中 | B |
| 传统特征（SIFT/ORB/颜色直方图） | — | — | — | 极快 | 无来源，属常识（C）：仅适合"同一视角下同一物体"的极简匹配与变化检测辅助，不适合语义查询 |

**结论**
- **语义塔选中文 CLIP ViT-B/16**：中文查询是其原生长处；README 明确给出 ONNX/TensorRT 部署路径与特征提取 API [R3]，对"Windows 笔记本 + 以后可能换 CPU/GPU"都友好；RN50 可作极低配回退。
- **实例塔选 DINOv2 ViT-S/14**：文本无关、纯视觉自监督特征，适合判断"这是不是昨天那把钥匙"（实例级），与语义塔互补 [R5]。
- **SigLIP/英文 CLIP 不作为中文主塔**：中文文本侧弱，需要翻译或改用中文塔，反而增加复杂度；可作为未来替换语义塔的候选（SigLIP 在小 batch 上更友好，训练/微调成本低 [R6]）。
- **是否微调**：MVP 不微调（数据不足），只用零样本 + 提示词集成（如"一张{物品}的照片""桌上的{物品}"）。桌面小物体是 CLIP 的已知弱项（物体占比小、遮挡、反光），**必须靠检测裁切把物体放大后再编码**，这是流水线设计而非模型问题（C）。

### 1.2 推荐检索流水线（两阶段：召回 → 排序）

```
采集帧 → 变化检测 → 物体检测/开放词表候选（YOLO-World [R15] 或 GroundingDINO [R16]）
       → 裁切 + 归一化（固定 224/518）
       → 双 embedding：CLIP语义(512) / DINOv2实例(384)
       → 写 detection + vec 表（同一事务）
查询 → 中文 QueryPlan（§3）
     → 候选集：先按 class/alias/region/time 过滤（SQL 索引，§2.4）
     → 语义召回：CLIP 文本嵌入 × 候选裁切图嵌入，top-K（K=30~50）
     → 重排：sim + 检测分 + 区域先验 + 时间新鲜度 + 用户确认标记
     → 实例去重：同 track 的连续帧合并（避免"同一把钥匙出现 40 次"）
     → 取"最后一次满足阈值"的 detection 作为答案 + 证据帧
```

- **检测不必一步到位**：MVP 可以只用固定命名区域 + 整帧 CLIP 召回（"桌上有什么"），确认需求后再加开放词表检测器。检测器是**精度放大器**，不是必需品。
- **开放词表的价值**：桌面物品多为 COCO 80 类之外（钥匙、门禁卡、耳机、充电器、眼镜盒），闭集检测器覆盖不住；开放词表（YOLO-World / GroundingDINO）可用自定词表（"keys, access card, earbuds, charger, glasses case"）现配现用 [R15][R16]（B）。

### 1.3 向量检索选型（规模 <10 万条）

| 方案 | 部署 | 10k/100k 查询延迟（C，未实测） | 精度 | 运维 | 结论 |
|---|---|---|---|---|---|
| **numpy/BLAS 暴力内积** | 无依赖，内存驻留 ndarray | <5ms / 5–30ms | 精确 100% 召回 | 需自己管内存与持久化（从 SQLite BLOB 加载） | **MVP 首选** |
| **sqlite-vec**（`vec0` 虚表） | SQLite 扩展，单文件，纯 C，Windows/WASM/树莓派均可 | 与暴力同级（C；README 自称 "fast enough"，未给出基准） | 精确（无 ANN，需自行验证） | 最低：与元数据同库同事务，无需同步两份数据 | **次选/生产单文件方案** [R7] |
| FAISS（`IndexFlatIP` / `IndexHNSWFlat`） | 独立 C++ 库，Python 绑定 | Flat 同暴力；HNSW 约 0.1–1ms | Flat 精确；HNSW 近似（召回 ~95–99%） | 需单独落盘/版本管理 | >10 万条或延迟敏感时引入 [R8]（B） |
| hnswlib | header-only C++，极轻 | 约 0.1–1ms（C） | 近似 | 需自己维护索引文件、删除支持弱 | 规模上来后的备选 [R9]（B） |
| Chroma | 独立服务/嵌入式 DB，偏"RAG 全家桶" | 未实测 | 近似/精确可配 | 重（自带 collection、服务进程），与"单文件桌面应用"不匹配 | 不选 [R10]（B） |

**判断依据（为什么"小规模暴力即最优"）**
- 规模：桌面场景 20–50 件常用物品、每天 100–500 次"出现"（变化触发），**一年也就 3.6 万–18 万条**；10 万条是 6–12 个月量级。
- 内存：10 万 × 512 float32 = 205MB；加 DINOv2 384 维再 +154MB；float16 减半、int8 约 1/4。笔记本 8–16GB 完全可驻留（可精确计算）。
- 精确性：物品记忆的查询必须"不漏"，近似索引的 1–5% 漏召回在这个场景里等于"东西明明在却说没看见"，**宁可慢 20ms 也不要漏**。
- 运维：一个 SQLite 文件 + 一个 `images/` 目录 = 用户可备份、可搬移、可删除；FAISS/Chroma 多一套索引文件与版本兼容问题，对"桌面小工具"是负担。

> 论证强度：规模/内存为算术事实（C→确定性）；延迟为推算（C）；"sqlite-vec 无 ANN"依据其 README 只描述 `vec0` 虚表 + KNN 查询、未提 HNSW/IVF（A 的内容 + C 的推断）。若 M2 需要，应实测 `sqlite-vec` 与 numpy 在 10 万条上的差异。

### 1.4 归一化、阈值与"同一实物"关联

- **归一化**：所有 embedding 入库存**L2 归一化后的向量**，余弦相似度 = 内积，可直接用 BLAS/sqlite-vec 的 L2 或内积距离；若用 L2 距离，注意 `d² = 2 - 2·cos`，别把距离当相似度。CLIP 类模型的相似度是**相对量**，跨模型/跨提示词不可比。
- **阈值必须每机型每用户校准，不能照抄论文**：中文 CLIP 的文本-图像余弦在"对"与"错"之间常常重叠（正确约 0.20–0.35，错误约 0.10–0.28，C，示意区间；实际随模型、提示词、裁切质量大幅漂移）。因此不要设单一"magic threshold"，而应：
  1. 收集 30–50 组标注（每物 2–3 张正样本 + 若干负样本）；
  2. 扫阈值取**精确率优先**的工作点（目标 P ≥ 0.9，宁可答"没找到/不确定"）；
  3. 用**分档**回报给用户（高/中/低），而不是给一个假精确的概率；
  4. 每次用户纠错都进 `feedback` 表，用于按物品类别调阈值。
- **同实例关联（"这是不是昨天那把钥匙"）**：`sim_instance(DINOv2) ≥ 0.80–0.90` 且**时空连续**（同一区域或相邻区域、时间接近）才并到同一 `track`；DINOv2 相似度的高分区间比 CLIP 更集中，但受视角/遮挡影响大，**阈值同样要校准**（C）。设备移动/重启后 track 会断，允许"人工合并"与"自动合并建议"。
- **召回/排序三条硬规则**：
  1. 精确过滤先行（class/alias、region、时间窗）——把候选从 10 万降到几百，再算 embedding；
  2. 召回 K=30–50 后用"检测分 + 区域先验 + 时间新鲜度"重排，而不是只看余弦；
  3. 答案取"时间上最后一次满足阈值"的 detection，并**同时给出倒数第二次**（用户常问"它什么时候离开这块区域的"）。

---

## 2. 存储与时间/区域语义

### 2.1 三层分离（强烈建议）

| 层 | 载体 | 内容 | 理由 |
|---|---|---|---|
| 元数据 | **SQLite 单文件** `findy.db` | 相机、采集、检测、物品、轨迹、区域、别名、查询日志 | 事务、索引、可查询、可备份；单文件便于"一个文件夹拷走" |
| 图像 | 文件系统 `images/YYYY/MM/DD/{seq}.jpg` + `thumbs/` | 原始帧 + 缩略图 + 物品裁切 | BLOB 塞进 SQLite 会让库膨胀、备份变慢、VACUUM 痛苦；文件系统更利于用户直接看/删 |
| 向量 | `vec_semantic` / `vec_instance`（sqlite-vec `vec0`）**或** SQLite BLOB + 进程内 ndarray | 512/384 维向量 | 与元数据同库同事务，避免"元数据删了向量还在"；规模大时改外置索引 |

- **图像与元数据分离原则**：DB 只存 `file_path` + `bytes` + `md5`；删除策略由 DB 驱动（`status='pruned'`），**不要**只删文件不更新 DB（会产生悬空引用）。
- **事务边界**：一帧入库 = 一个事务（`capture` + N 个 `detection` + N 条向量 + 可能的 `track` 更新）。SQLite 开 WAL 模式让"采集写入"与"查询读取"并发不互斥（WAL 文档：https://www.sqlite.org/wal.html ，B）。

### 2.2 时间语义（最容易埋雷的地方）

必须区分的四个时间：

| 字段 | 含义 | 缺失时怎么办 |
|---|---|---|
| `captured_at_utc` | 设备 SNTP 同步后确定的**拍摄时刻**（UTC epoch 秒） | SNTP 未同步 → **NULL**，绝不填收到时间冒充 |
| `received_at_utc` | 笔记本 HTTP 收到该帧的时刻 | 永远有值（本机时钟） |
| `device_seq` | M1 固件的 `seq`（`GET /api/photo?seq=N` 的 N） | 单调递增，用于**幂等去重**与顺序恢复 |
| `time_source` | `sntp` / `manual` / `unsynced` | 用于界面提示"该时刻为估算" |

- **时区**：DB 内一律存 UTC epoch 秒，只在显示层用 `settings.tz_name`（默认 `Asia/Shanghai`）转本地；**不要**存本地时间字符串当主键/排序键（夏令时/换时区会错乱）。SQLite 的 `date(ts,'unixepoch','+8 hours')` 硬编码偏移不可取，应用层用 `zoneinfo` 转换更稳 [R11]（B）。
- **SNTP 未同步的补救**：先用 `received_at_utc - 网络/处理延迟` 标记为估算值；SNTP 同步成功后，按 `device_seq` 邻近关系与 `received_at` 计算 `clock_offset_ms`，批量回填并把 `time_source` 改为 `sntp`。**回填操作要写审计**，否则"最后出现时间"会静默变化，用户会不信。
- **"最后出现"的口径**：`max(captured_at_utc)` where 匹配物品且 `status='ok'`；若该 track 最后一次出现早于 `now - 阈值`，界面应说"最后一次看到是 X，可能已被移出画面/视野外"，而不是断言"在桌上"。
- **设备与本机时钟都不可信时**：`device_seq` 是唯一可靠单调量，用它构建相对顺序，时间只作为展示（C，工程建议）。

### 2.3 区域表示：图像坐标 + 命名区域（不做 3D）

| 方案 | 成本 | 精度 | 判断 |
|---|---|---|---|
| **归一化 bbox/多边形 + 命名区域表** | 极低（画一次框） | 与视角绑定；相机不动就稳定 | **MVP 推荐** |
| 网格分块（3×3/4×4）+ 区域名映射 | 低 | 粗但够用，便于"桌子左半边" | 可与上一行叠加 |
| 深度相机 / 3D 重建 | 高（硬件+标定+算力） | 真实空间位置 | 明确不做（单目 OV2640 无深度；多相机需标定，成本翻倍） |
| 多相机/云台 | 高 | 覆盖更大 | 二期评估，MVP 单机固定视角 |

- 坐标一律**归一化到 [0,1]**（相对图像宽高），使 640×480 的 ESP32 帧与未来 2.5K 帧共用同一区域定义，也便于前端在任意缩放的缩略图上画框。
- 命名区域（`region` 表）支持父子（"桌面" → "显示器下方""键盘右侧"），检测入库时用 bbox 中心点做点在多边形内判定，**把 `region_id` 冗余写进 `detection`**，以便"桌上有什么"直接走 `(region_id, captured_at_utc)` 索引，避免每次 join。
- 视角会变（用户移动相机）→ 区域定义与旧 detection 的 `region_id` 会失真：用 `camera.calibration_version` 版本号，改视角时升版本，旧数据保留旧区域归属并在界面标注（C）。

### 2.4 推荐 schema 草案（SQLite 3）

> 说明：下面是**可执行的草案**，不是最终迁移脚本。`vec0` 表需要加载 sqlite-vec 扩展；若暂不引入，把 `embedding` 改成 `BLOB`（numpy `.tobytes()`）并进程内暴力检索，其余表不变。

```sql
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA foreign_keys = ON;

-- 相机 / 采集源
CREATE TABLE camera (
  id              INTEGER PRIMARY KEY,
  name            TEXT NOT NULL,               -- '书桌正上方'
  source          TEXT NOT NULL,               -- 'esp32_http' | 'usb_webcam'
  model           TEXT,                        -- 'ESP32-S3-EYE v2.2 + OV2640'
  base_url        TEXT,                        -- http://<ip>
  width           INTEGER NOT NULL,
  height          INTEGER NOT NULL,
  tz_name         TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  calibration_version INTEGER NOT NULL DEFAULT 1,
  created_at_utc  INTEGER NOT NULL
);

-- 一帧 = 一行；captured 与 received 严格分离
CREATE TABLE capture (
  id              INTEGER PRIMARY KEY,
  camera_id       INTEGER NOT NULL REFERENCES camera(id),
  device_seq      INTEGER,                     -- /api/photo?seq=N
  captured_at_utc INTEGER,                     -- NULL = SNTP 未同步
  received_at_utc INTEGER NOT NULL,
  time_source     TEXT NOT NULL CHECK (time_source IN ('sntp','manual','unsynced')),
  clock_offset_ms INTEGER,
  file_path       TEXT NOT NULL,
  thumb_path      TEXT,
  bytes           INTEGER,
  md5             TEXT,
  scene_change    REAL,                        -- 0..1 与上一帧差异
  status          TEXT NOT NULL DEFAULT 'ok' CHECK (status IN ('ok','corrupt','pruned')),
  UNIQUE (camera_id, device_seq)               -- 幂等：重复拉取同一 seq 不新增
);
CREATE INDEX idx_capture_time ON capture(captured_at_utc DESC, id DESC);
CREATE INDEX idx_capture_recv ON capture(received_at_utc DESC);
CREATE INDEX idx_capture_pending ON capture(id) WHERE captured_at_utc IS NULL;

-- 命名区域（归一化多边形，JSON：[[x,y],...]）
CREATE TABLE region (
  id              INTEGER PRIMARY KEY,
  camera_id       INTEGER NOT NULL REFERENCES camera(id),
  parent_id       INTEGER REFERENCES region(id),
  name            TEXT NOT NULL,               -- '桌面' / '显示器下方' / '抽屉'
  polygon_norm    TEXT NOT NULL,
  kind            TEXT,                        -- 'surface' | 'container' | 'out_of_view'
  calibration_version INTEGER NOT NULL DEFAULT 1,
  UNIQUE (camera_id, name, calibration_version)
);

-- 物品类别 + 中文别名（实体对齐的词典）
CREATE TABLE object_class (
  id              INTEGER PRIMARY KEY,
  name_zh         TEXT NOT NULL,               -- '钥匙'
  name_en         TEXT,                        -- 'keys'（开放词表提示词用）
  is_open_vocab   INTEGER NOT NULL DEFAULT 1,
  UNIQUE (name_zh)
);
CREATE TABLE alias (
  id              INTEGER PRIMARY KEY,
  class_id        INTEGER NOT NULL REFERENCES object_class(id),
  alias           TEXT NOT NULL,               -- '门钥匙' / '家门钥匙'
  lang            TEXT NOT NULL DEFAULT 'zh',
  source          TEXT NOT NULL DEFAULT 'seed',-- 'seed' | 'user'
  UNIQUE (alias, lang)
);

-- 同一实物跨时间的实体（"这把钥匙"）
CREATE TABLE track (
  id              INTEGER PRIMARY KEY,
  class_id        INTEGER NOT NULL REFERENCES object_class(id),
  label           TEXT,                        -- 用户可命名"我的车钥匙"
  embed_instance  BLOB,                        -- 384*4 float32，代表性实例向量
  embed_model     TEXT NOT NULL DEFAULT 'dinov2_vits14',
  first_seen_utc  INTEGER,
  last_seen_utc   INTEGER,
  last_region_id  INTEGER REFERENCES region(id),
  status          TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','merged','deleted')),
  user_confirmed  INTEGER NOT NULL DEFAULT 0,
  created_at_utc  INTEGER NOT NULL
);
CREATE INDEX idx_track_recent ON track(last_seen_utc DESC) WHERE status = 'active';
CREATE INDEX idx_track_class ON track(class_id, last_seen_utc DESC);

-- 一次"出现" = 一行 detection（sighting）
CREATE TABLE detection (
  id              INTEGER PRIMARY KEY,
  capture_id      INTEGER NOT NULL REFERENCES capture(id) ON DELETE CASCADE,
  track_id        INTEGER REFERENCES track(id),
  class_id        INTEGER REFERENCES object_class(id),
  region_id       INTEGER REFERENCES region(id),   -- 冗余：加速区域查询
  captured_at_utc INTEGER,                         -- 冗余自 capture：用于时间索引
  bbox_norm       TEXT NOT NULL,                   -- 'x1,y1,x2,y2' 归一化
  crop_path       TEXT,
  det_score       REAL NOT NULL DEFAULT 0,
  embed_semantic  BLOB,                            -- 512*4
  embed_instance  BLOB,                            -- 384*4
  embed_model_sem TEXT NOT NULL DEFAULT 'chinese-clip-vit-b16',
  embed_model_ins TEXT NOT NULL DEFAULT 'dinov2_vits14',
  is_primary      INTEGER NOT NULL DEFAULT 1       -- 同一 track 同一帧只保留主检测
);
CREATE INDEX idx_det_capture ON detection(capture_id);
CREATE INDEX idx_det_track   ON detection(track_id, captured_at_utc DESC);
CREATE INDEX idx_det_region  ON detection(region_id, captured_at_utc DESC);
CREATE INDEX idx_det_class   ON detection(class_id, captured_at_utc DESC);

-- 检索用的向量表（sqlite-vec）；不可用时改为 BLOB + 进程内暴力
CREATE VIRTUAL TABLE vec_semantic USING vec0(
  detection_id INTEGER PRIMARY KEY,
  embedding    float[512]
);
CREATE VIRTUAL TABLE vec_instance USING vec0(
  detection_id INTEGER PRIMARY KEY,
  embedding    float[384]
);

-- 用户纠错（阈值校准与别名扩充的燃料）
CREATE TABLE feedback (
  id              INTEGER PRIMARY KEY,
  detection_id    INTEGER REFERENCES detection(id),
  action          TEXT NOT NULL,                -- 'confirm' | 'wrong_object' | 'wrong_region' | 'merge_track'
  payload         TEXT,
  created_at_utc  INTEGER NOT NULL
);

-- 查询日志（离线评估 + 意图模板迭代）
CREATE TABLE query_log (
  id              INTEGER PRIMARY KEY,
  raw_text        TEXT NOT NULL,
  plan_json       TEXT,                          -- 解析出的 QueryPlan
  parser          TEXT NOT NULL,                 -- 'rule' | 'llm_local' | 'llm_cloud'
  latency_ms      INTEGER,
  result_count    INTEGER,
  created_at_utc  INTEGER NOT NULL
);

-- 保留策略（按种类设 TTL，采集/查询共用）
CREATE TABLE retention_policy (
  kind            TEXT PRIMARY KEY,              -- 'raw_frame' | 'thumb' | 'evidence'
  ttl_days        INTEGER NOT NULL
);
```

**索引理由一览（逐条对应查询）**

| 索引 | 支撑的查询 | 不建会怎样 |
|---|---|---|
| `capture(camera_id, device_seq) UNIQUE` | 拉帧幂等（同一 seq 重试） | 断网重试会产生重复帧，统计与"出现次数"全错 |
| `capture(captured_at_utc DESC)` | "最后出现"、时间窗筛选、按天聚合 | 全表扫 + 内存排序；10 万行后可感知变慢 |
| `capture(id) WHERE captured_at_utc IS NULL`（部分索引） | 回填待办扫描 | 回填任务每次扫全表 |
| `detection(track_id, captured_at_utc DESC)` | 轨迹回溯、去重合并、"动过几次" | 需 join capture 再排序，多一次随机 IO |
| `detection(region_id, captured_at_utc DESC)` | "桌上有什么""抽屉里有什么" | 空间查询退化为逐帧遍历 |
| `detection(capture_id)` | 帧 ↔ 物体联查 | 同上 |
| `track(last_seen_utc) WHERE status='active'`（部分索引） | 物品库首页（最近出现排序） | 索引进 deleted/merged 噪声 |
| `alias(alias, lang) UNIQUE` | 中文实体对齐（"门钥匙"→类别） | 每次查询线性扫词典（小，但会掩盖缺索引的设计问题） |
| `region(camera_id, name, calibration_version)` | 区域名唯一性、视角变更后的归属 | 同名区域混用 |

**为什么把 `captured_at_utc` 和 `region_id` 冗余进 `detection`**：物品查询的 90% 都是"某物 + 时间 + 区域"的组合过滤，冗余两列可让过滤+排序走同一个复合索引，避免 `detection`↔`capture` 的 join 后再排序。代价是写入时多赋值两列、`capture` 时间回填时要级联更新（用触发器或应用层事务保证一致）。

### 2.5 容量、迁移与隐私

- **容量**：10 万 detection ≈ 元数据（含两套向量 BLOB）约 0.5–1GB（C，按行宽粗估）；`images/` 按 §4 估 0.4–2.6GB/月原始帧。SQLite 单库到数 GB 无压力，但**建议把图像留在文件系统**（§2.1）。
- **保留策略（默认值，可配）**：原始帧 7 天；缩略图 90 天；"证据帧"（每个 track 每天最后一次出现 + 用户点开过的）永久；元数据永久（体积小、是记忆本体）。**删帧不删记忆**：帧被清理后，detection 仍保留时间/区域/向量，界面显示"原图已按保留策略清理"。
- **隐私**：全部本地；无云上传；查询文本与图像都不外传（若接云端 LLM，只发查询文本，不发图像，且默认关闭）；提供"一键清空某天/某物品"；相机对着桌面而非床/卫生间，从产品定义上规避；如需更强，可用 SQLCipher 加密 DB（B，未在本项目验证），图像目录可交给 Windows EFS/BitLocker（B）。
- **迁移**：`PRAGMA user_version` 做版本号，启动时顺序执行迁移脚本；`embed_model` 字段记录每条向量的模型名，**换模型必须重算而非混用**（不同模型向量空间不可比，混用会得到无意义相似度——这是最常见的隐性 bug，C）。

---

## 3. 中文自然语言查询方案

### 3.1 意图类型（先定义产品语言，再谈技术）

| 意图 | 示例 | 槽位 | 期望输出 |
|---|---|---|---|
| `LAST_SEEN` 最后位置 | "我的钥匙在哪""钥匙最后放哪了""车钥匙呢" | object | 物品名 + 最后出现时间 + 区域 + 证据帧 + 置信度 |
| `LOCATE_NOW` 当前判断 | "钥匙现在在桌上吗""眼镜还在显示器旁边吗" | object, region(可选) | 是/否/不确定 + 最后证据 |
| `HISTORY` 轨迹 | "钥匙今天动过几次""钥匙什么时候离开桌面的" | object, time_range, region | 时间线（进入/离开区域）+ 次数 |
| `LIST_REGION` 区域清单 | "桌上有什么""抽屉里有什么" | region, time_range | 该区域最近出现过的物品列表（按时间） |
| `COUNT` 计数 | "桌上有几个杯子" | object, region, time | 数量 + 判定依据（同一 track 去重后计数） |
| `ATTRIBUTE` 属性检索 | "红色的东西在哪""找我的充电器" | color/attr/用途 | 候选列表 + 相似度分档 |
| `MISSING` 丢失判定 | "钥匙不见了""我找不到钱包了" | object | 最后一次出现 + 是否已出画面 + 建议动作 |
| `TIME_FACT` 时间事实 | "我上午把眼镜放哪了""昨天最后看到钥匙是什么时候" | object, time_range | 指定时间窗内的最后位置 |

- 边界情况必须显式定义：**问的东西从未登记**（"你没记过这个东西"）、**问的东西在画面外**（"最后一次看到是 3 小时前，之后相机视野里没再出现"）、**同名多实例**（"我有两串钥匙，你问哪串"→ 列出 track 让用户选）。

### 3.2 规则解析（主干，默认路径）

- **分词**：`jieba` 精确模式 + **自定义词典**（`add_word`）加入领域词：`门禁卡`、`充电宝`、`钥匙串`、`显示器下方`、`airpods`…（B，jieba 支持自定义词典 [R14]）。不加载自定义词典时"门禁卡"会被切成"门/禁/卡"，实体对齐直接失效。
- **实体对齐**：`alias` 最长匹配优先 → `object_class`；区域名同法匹配 `region.name` + 用户口语别名（"桌子"→"桌面"）；颜色/材质词单独成槽，用于 `ATTRIBUTE` 排序权重，不参与硬过滤。
- **时间解析**：正则覆盖 `刚才/刚刚/今天/昨天/前天/上午/中午/下午/晚上/上周/最近 N 天/YYYY-MM-DD`，转成 `[start_utc, end_utc)`；无法解析的（"那会儿"）→ 默认最近 24h 并**显式告知**用户"按最近 24 小时查"。
- **意图判定**：按关键词/句式优先级匹配，例如 `(.+?)(在|放)(哪|哪儿)` → `LAST_SEEN`；`(.+?)有什么` → `LIST_REGION`；`(几个|多少)(.+?)` → `COUNT`；`(.+?)(动过|挪过|离开)` → `HISTORY`。规则命中率靠 100–200 条真实问法样本迭代（本项目尚无真实语料，**必须做** 30–50 条自测集）。
- **未登录词兜底**：整句直接作为 CLIP 文本查询做语义召回（不依赖实体识别），返回候选让用户确认——这是"规则失败但仍能给出有用结果"的关键兜底。
- **输出统一为 QueryPlan**（JSON，执行器唯一入口）：

```json
{"intent":"LAST_SEEN","object":{"class":"钥匙","alias_hit":"门钥匙","track_id":null},
 "region":null,"time_range":[null,null],"color":null,"limit":5,"parser":"rule","confidence":"high"}
```

### 3.3 LLM function calling（增强，非默认）

- **工具集**（与 QueryPlan 执行器一一对应，模型只负责"选工具 + 填槽"，不负责算相似度）：
  - `get_last_seen(object_name, region_name?, before_ts?)`
  - `search_objects(description, region_name?, time_range?, limit)`
  - `list_region(region_name, time_range?)`
  - `count_objects(object_name, region_name?, at_ts?)`
  - `get_history(object_name, time_range, granularity)`
  - `find_moved(object_name, since_ts)`
- **为什么用 function calling 而不是"让 LLM 直接答"**：答案必须来自数据库证据帧；LLM 只做语言→结构化意图的翻译，幻觉无法污染事实（C，设计判断）。
- **本地小模型（推荐给隐私/离线）**：Qwen2.5-0.5B/1.5B-Instruct 的 GGUF 走 llama.cpp/Ollama（B，工具链成熟 [R26]）。CPU 单次 JSON 输出约 200–800ms（C，按 0.5B 模型 CPU 20–60ms/token × 数十 token 估算），需实测；0.5B 的中文指令/工具调用可靠性存疑（C），建议 1.5B 起步并强制 schema 校验。
- **云端 API（可选，默认关闭）**：DeepSeek/通义等支持 function calling。只上传**查询文本 + 类别名列表**（不上传图像、不上传时间线细节），并做显式开关与提示。成本见 §4。
- **健壮性**：schema 校验失败 → 重试 1 次（温度 0）→ 仍失败降级规则；LLM 返回的槽位必须能在本地词典/区域表里对齐，对不上就丢弃该槽位并标记"部分理解"。

### 3.4 降级策略（决策树）

```
用户输入
 ├─ 能解析出实体 + 意图（规则） ──────────────→ 直接执行（0ms，离线，可解释）
 ├─ 规则部分命中（有实体无意图 / 有意图无实体）
 │    ├─ 本地 LLM 可用 → function calling 补槽 → schema 校验 → 执行
 │    └─ 本地 LLM 不可用 → 降级：整句 CLIP 语义召回 + 让用户在候选里选
 └─ 完全无法解析
      ├─ 联网且用户开启云端 → 云端 function calling（文本外传需提示）
      └─ 否则 → 明确告知"没听懂"，给出 3 个示例问法 + 物品库直选入口
```

- **降级必须"可用"而不是"报错"**：任何路径都要能返回"候选物品 + 证据帧"，即使只是模糊召回。用户对"没听懂"的容忍度远低于"给个不完美但能点的答案"（C，产品判断）。
- **可观测**：`query_log.parser` 记录走了哪条路径，每周看 `llm_*` 占比与失败率，决定是否值得常驻加载小模型。

### 3.5 结果展示要素（缺一不可）

1. **匹配物品**：类别名 + 用户自定义名/别名（"钥匙（门钥匙）"）；
2. **证据图**：整帧缩略图 + 物品裁切放大 + 框选高亮（用户要"眼见为实"）；
3. **时间**：本地时间（`2026-10-28 14:32`）+ 相对时间（"3 小时前"）；时间来源非 SNTP 时标注"约"；
4. **区域**：命名区域（"桌面 · 显示器下方"）；若已不在当前画面，明说"当前画面中未见"；
5. **置信度**：三档 + 依据文案（"相似度 0.31（高）｜检测 0.82｜用户确认过"），**不给假精确概率**；
6. **纠错入口**：对/错、改区域、这是同一物品、改名——每次纠错进 `feedback`，直接改善下次结果；
7. **备选**：top-3 候选（"也可能是：钥匙扣"）。

---

## 4. 采集策略与成本估算

### 4.1 采集模式对比

| 模式 | 覆盖 | 存储/算力 | 实现复杂度 | 建议 |
|---|---|---|---|---|
| **固定视角 + 定时间隔（30–120s）** | 稳定覆盖桌面 | 低 | 极低（定时 HTTP 拉一帧） | **MVP 主策略** |
| 固定视角 + **变化检测触发落盘** | 同上，省 70% 存储 | 低（降采样帧差/SSIM，<1ms） | 低 | **叠加在定时上**（推荐组合） |
| 事件触发（用户说"我放好了"/按键） | 高质量建档点 | 极低 | 低（M1 已能 POST 触发） | 二期：提升"建档时刻"质量 |
| 移动云台 / 机器人 | 覆盖整个房间 | 高（电机、标定、算力） | 高 | 不做（成本与可靠性不匹配 MVP） |
| 常开视频流 | 全时段 | 高（编码/存储/解码） | 中 | 不做（存储与隐私都不划算） |

- **为什么"定时 + 变化触发"最优**：物品记忆要的是"物品何时出现在哪"，不是连续视频；变化帧才携带新信息。60s 间隔对"找东西"场景足够（人离开桌面的动作以分钟计），且把电费/存储/算力压到最低。
- **变化检测实现**：把帧降采样到 64×48 灰度，与上一帧做平均绝对差 + 分块阈值；`scene_change` 存 DB，用于回看与阈值调参。光照突变（开灯）会误触发 → 加"全画面均匀变化"过滤（C，工程细节）。

### 4.2 ESP32-S3-EYE（HTTP 拉帧）vs 本机 webcam

| 维度 | ESP32-S3-EYE + OV2640（M1 已验证） | 笔记本 webcam |
|---|---|---|
| 视角 | **固定**（符合"桌面记忆"叙事，区域定义稳定） | 随笔记本移动/开合，区域定义漂移 |
| 分辨率/画质 | 640×480 JPEG（可更高但 PSRAM/带宽受限）；OV2640 定焦、弱光差（B，器件常识） | 720p–1080p、自动曝光更好 |
| 延迟 | 抓一帧 + HTTP 传输约 0.1–1s（C，未实测；Wi-Fi 局域网） | <50ms |
| 成本 | 硬件已有；常驻功耗 <1W（C，USB 供电） | ¥0（已有），但占用 USB/隐私感强 |
| 隐私感知 | 独立小设备、可遮挡，叙事上是"记忆相机" | 笔记本摄像头，用户心理抵触更强 |
| 可靠性 | 依赖 Wi-Fi；断网需本地缓冲（固件已有 seq，可补拉） | 稳定 |

**结论**：**ESP32 为主采集端**（产品形态与叙事一致、视角固定、成本已沉没），**webcam 只用于开发调试与 A/B 对照**。M1 已验证 `POST /api/capture`、`GET /api/photo?seq=N`、Wi-Fi、SNTP（**本项目一手验证，A 级但属内部证据**）；M2 需补测：单帧延迟、连续抓帧稳定性、断网重连后 seq 补齐。

### 4.3 推荐 MVP 采集策略（可直接排期）

1. 每 60s `POST /api/capture` → `GET /api/photo?seq=N` 拉帧（或固件端定时推送，待定）；
2. 帧入临时目录，做变化检测；`scene_change < 阈值` 且非"建档帧"→ 只写 `capture` 元数据、不保留原图（或直接丢弃，只保留心跳）；
3. 变化帧：保留原图 + 缩略图 → 检测/裁切 → 双 embedding → 写库；
4. 每 30min 跑一次轻量整理：合并同 track 连续帧（只留 `is_primary`）、清理超 TTL 原图、回填未同步时间；
5. 每天 02:00 做 `VACUUM`（或 `PRAGMA incremental_vacuum`）+ 统计报表（帧数/物品数/存储占用），供产品与成本观测。

### 4.4 成本估算（全部标注依据与不确定度）

| 项目 | 估算值 | 依据 / 计算 | 不确定度 |
|---|---|---|---|
| 硬件增量 | ¥0（ESP32-S3-EYE 与笔记本均为已有） | 任务书背景；ESP32-S3-EYE 单板市价约 ¥300–500（D，未核实采购价） | 高 |
| 电费（笔记本常驻） | **¥12–26 / 月** | 30–60W × 24h = 0.72–1.44 kWh/日 → 21.6–43.2 kWh/月；居民电价 0.5–0.6 元/kWh（C，全国均值区间，未逐地核对） | 中（电价与机型功耗） |
| 原始帧存储 | **0.4–2.6 GB / 月**（变化过滤后 0.1–0.8 GB） | 640×480 JPEG q75 ≈ 30–60KB；60s/帧 = 1440 帧/日 = 43–86MB/日；保留率按 20–30% 估计 | 中（JPEG 大小随场景纹理变化） |
| 证据帧/缩略图 | <0.2 GB / 月 | 每 track 每日 1 张全帧 + 裁切，几十个 track | 低 |
| 元数据+向量 | 10 万条 ≈ 0.5–1 GB | 每行约 5–10KB（两套 float32 向量 3.6KB + 文本字段）（可精确计算部分） | 低 |
| 推理算力 | 每帧 30–200ms 单核；60s 间隔占用 **<0.4% 单核** | 按参数量/分辨率推算（CLIP ViT-B/16 80–200ms、DINOv2 ViT-S/14 20–60ms），未实测 | 低（务必 M2 实测） |
| 检索延迟 | 10k 条 <5ms；100k 条 5–30ms；1M 条需换 ANN | BLAS sgemm 吞吐推算（C），未实测 | 低 |
| 云 LLM（可选） | 单次查询 **<¥0.01–0.03** | 1–3k tokens × ¥1–4/百万 tokens 的国产 API 价位（D，价格随供应商/时段变化，未核对当前价目） | 高 |
| 本地小模型（可选） | 0 元边际 + 200–800ms/次 | GGUF 量化模型常驻内存约 0.5–1.5GB（C） | 中 |
| 订阅/云存储 | **0** | 全本地设计 | — |

**成本结论**：全案运行成本 ≈ **¥12–26/月（电费）**，边际成本几乎只有电费与磁盘；这是"桌面小工具"定价（¥599–999 一次性，见团队既有定价结论）能够成立的硬前提。**唯一可能超支的是"想当然上云端多模态大模型"**——凡是逐帧调用云 VLM 的方案，成本会高 1–2 个数量级，且违背本地隐私叙事，不建议。

---

## 5. 近邻产品与开源案例能力对照

> 数据来源：团队既有证据台账（[竞品与市场数据 2026-10-22](../../桌面记忆相机_竞品与市场数据_2026-10-22.md)、`research/notes.md`）及其回填的原始链接；MemPal 另经 arXiv 摘要核实 [R17]。**未逐条重抓竞品页面**，故本表整体标 B（台账级），非 A。

| 产品/项目 | 形态 | 物品级识别 | 长期记忆 | 自然语言检索 | 本地/隐私 | 价格 | 状态 | 与本项目的差距 |
|---|---|---|---|---|---|---|---|---|
| **Camtells** | 桌面/空间 AI 相机（360° 全景） | 宣称"Smart Object Library" | 有限（事件） | 宣称 AI 事件搜索 | 未明 | 众筹价人均 ≈HK$4,715 | 众筹 HK$113,167、**24 名支持者、未发货** [R21] | 概念最接近，但需求验证极弱、交付未验证 |
| **MemPal**（MIT） | 可穿戴相机 + 多模态 LLM + 语音 | 依赖 VLM 场景描述 | 是（自动文字日记） | 语音问答 | 研究原型 | — | 论文 N=15 居家实验 [R17][R18] | 交互范式被验证；非商品、可穿戴形态不适合桌面 |
| **Apple HomeView / Home Collection**（2026-10-13） | 家庭摄像头 + HomeKit | 人/熟悉面孔/宠物/车辆/包裹 | 是（iCloud+ 10 天视频） | **自然语言搜索视频** | 家庭中枢本地/私有云 + E2E 加密 | 未公布（生态级） | 2026-12 起开售 [R19] | 最大平台威胁，但不是"物品记忆"（不回答"我的钥匙在哪"） |
| **Ugreen HomeAgent**（2026-09） | 本地 AI 家庭 hub | 人/车/宠物/包裹 | 是（录像存储） | 关键词搜索录像 | 本地 AI | $899 / $2,999 / $9,999 | 2026-10-27 Kickstarter [R20] | 价格带远高；仍是"事件/录像检索" |
| **Memories.ai** | 视觉记忆基础设施（API） | 视频级索引 | 是（百万小时级） | 语义检索 | 云 | B 端 | 累计 $1,600 万种子 [R22] | 基础设施层，非消费产品；提示"应用层可能被商品化" |
| **Find My Everything**（iOS App） | 手机 App | 实时 YOLO-World + Gemini 2.5 Flash 拍照分析 | 部分（手动/拍照建档） | 按物体名搜"何时何地最后看到" | 云（Gemini） | 免费 | v1.0.1，无评分 [R23] | 证明"拍照+时间+搜索"零壁垒；缺**持续自动记录**与硬件形态 |
| **Prompt AI / Seemour**（已失败） | 接入安防摄像头 | 人/宠物/物体 | 有限 | 对画面提问 | 云 | 曾免费 | App 下架，团队被苹果收编（台账 B） | 技术可行但商业模型不成立的反面教材 |
| **Violoop**（桌面 AI 盒子） | 桌面硬件，读屏幕 | 屏幕内容（非物理物品） | 是（本地长期记忆） | Agent 对话 | 本地 | $399–699 | Kickstarter 20 小时破 $100 万（台账 B） | 形态/定价对标；但记的是屏幕不是桌面实物 |
| **威视达康 CS997A** | 桌面云台监控机器人 | 万物识图（通用 VLM） | 无物品记忆 | AI 对话 | 云（豆包/通义/Gemini） | 低（消费级） | 在售（台账 B） | 形态最接近的深圳竞品，证明硬件不是壁垒，缺"记忆+检索" |
| 追踪器阵营（AirTag 2 / 小米 Tag 等） | 标签 | 无（不识别物品） | 无 | 无 | 端侧 | ¥69–249 | 成熟在售 | 只能定位"标签"，不能回答"我的东西是什么/在哪" |

**能力缺口总结（对本项目的直接含义）**

1. **四要素同时成立的产品不存在**：摄像头（有）+ 物品级识别（少数有）+ 长期记忆（少数有）+ 自然语言物品检索（几乎没有）。这是真实空位，但**空位的原因要么是需求弱（Camtells 24 人），要么是商业模型不成立（Prompt AI），要么是大厂正用"视频检索"绕过去（Apple/Ugreen）**——本项目必须验证"物品记忆"相对"视频检索/标签"的增量价值，而不是假设它成立。
2. **平台正在从上方覆盖**：Apple 的 NL 视频搜索 + Ugreen 的本地 AI hub 已经吃掉"问家里发生过什么"这一层；Findy 必须**聚焦到"我的某件具体物品最后一次在哪"**，并给出裁切证据帧，这是大平台当前不做的颗粒度。
3. **App 侧已无壁垒**：Find My Everything 免费实现了"拍照建档 + 时间 + 搜索"，所以硬件差异点只能是**持续自动记录 + 固定视角 + 无需用户操作**。
4. **可借鉴的技术范式**：MemPal 证明"多模态 LLM 自动写日记 + 语音问答"在老人场景有效（N=15）[R17]，但其成本模型（云 VLM 逐帧）在消费级不可行；本项目应取其"日记/时间线"交互，弃其"逐帧大模型"实现。
5. **IP 提醒**：海康 CN109993045A 覆盖"摄像设备识别物品→保存→接收查询→匹配→返回位置信息与目标图片"的流程 [R24]，与本项目核心流程高度重叠；技术选型不受影响，但**产品化前必须做 FTO**（团队既有结论）。

---

## 6. 已验证 vs 推断（诚实清单）

### 6.1 已验证（A 级，本次抓取/项目内一手）

| 结论 | 证据 |
|---|---|
| 中文 CLIP 有 5 个规模，ViT-B/16 总 188M（视觉 86M）、224px、约 2 亿中文图文对；提供 ONNX/TensorRT 部署与特征提取 API；README 要求对特征做 L2 归一化 | A：[R3]（本次抓取 README 全文），模型页 [R4] |
| 中文 CLIP 在 MUGE 文→图检索零样本 R@1=63.0、Flickr30K-CN R@1=71.2 | A：[R3] 表格 |
| CLIP 用 4 亿图文对、零样本可匹配 ResNet-50 ImageNet 精度 | A：[R1] 摘要 |
| DINOv2 用 1B 教师蒸馏小模型，通用视觉特征在多数基准超 OpenCLIP | A：[R5] 摘要 |
| SigLIP 用 sigmoid 损失、小 batch 更友好、ICCV'23 Oral | A：[R6] 摘要 |
| sqlite-vec 是纯 C 的 SQLite 扩展，`vec0` 虚表支持 float/int8/二进制向量、metadata/辅助列/分区键，pre-v1 会有破坏性变更 | A：[R7] README |
| MemPal 是 MIT 可穿戴 + 多模态 LLM 原型，N=15 居家实验，音频辅助提升找物表现 | A：[R17] 摘要 |
| 本项目 M1 固件可拍照/Wi-Fi/SNTP/HTTP（`POST /api/capture`、`GET /api/photo?seq=N`） | A：项目内一手验证（任务书背景） |
| 存储/延迟/成本的算术部分（如 100k×512×4B=205MB、1440 帧/日×40KB≈58MB/日） | 确定性计算 |

### 6.2 推断/估算（C/D，需 M2 实测）

| 推断 | 依据 | 风险 |
|---|---|---|
| 10k/100k 条暴力检索延迟 <5ms / 5–30ms | BLAS sgemm 吞吐 + 向量维度推算 | 低（结论方向稳，数值可能差 2–3×） |
| CLIP ViT-B/16 单帧 CPU 80–200ms；DINOv2 ViT-S/14 20–60ms | 参数量×分辨率推算，未跑基准 | 中（不同 CPU 差异大） |
| **中文 CLIP 在"桌面小物体裁切图"上的零样本召回可用** | 通用 CLIP 常识 + 检测裁切能显著改善；**未验证** | **高：这是全案最大技术风险**，必须 M2 用 30–50 个真实物品测评 |
| 同实例 DINOv2 阈值 0.80–0.90 可合并同一实物 | 通用 embedding 相似度经验 | 高（视角/遮挡敏感，必须校准） |
| 60s 间隔足以覆盖"找东西"场景 | 人的动作时间尺度 | 中（漏掉快速一放一取） |
| 笔记本 30–60W、电价 0.5–0.6 元/kWh → ¥12–26/月 | 常见轻薄本/游戏本区间 + 居民电价均值 | 中（机型与地区差异） |
| 640×480 JPEG 30–60KB | 经验值 | 中（场景纹理影响大） |
| 云端 LLM 单次查询 <¥0.01–0.03 | 1–3k tokens × ¥1–4/百万价格带 | 高（价目未核对，且模型选择影响大） |
| 本地 0.5B 模型中文 function calling 可靠 | 模型能力常识 | 高（很可能不够，需 1.5B+ 或规则兜底） |
| 竞品能力对照表 | 团队台账（B） | 中（页面会变，未逐条重抓） |

### 6.3 M2 必测清单（把上面的高不确定项变成事实）

1. 本机（目标 Windows 笔记本）上：中文 CLIP ViT-B/16 与 DINOv2 ViT-S/14 的**单帧 CPU 延迟**（ONNX Runtime / PyTorch，含预处理）；
2. 30–50 个真实桌面物品的**零样本 top-1/top-3 召回率**（整帧 vs 裁切、不同提示词模板）；
3. 同一物品跨 24h/不同光照/不同摆放角度的**实例匹配 ROC**，定阈值；
4. 10k / 100k 条向量下 numpy 与 sqlite-vec 的**查询延迟与内存**；
5. ESP32 单帧端到端延迟、连续 24h 抓帧成功率、断网重连后 seq 补齐；
6. 规则解析在 30–50 条自拟中文问法上的**意图/槽位准确率**；本地小模型（1.5B）function calling 成功率与延迟；
7. 7 天真实运行的存储占用与电费（可用功率计量插座）校准 §4.4。

---

## 7. 参考文献

> 标注：URL 后可点；"本次抓取"= A 级；"团队台账"= B 级（未逐条重抓）。

**模型/论文**
1. [R1] Radford et al., *Learning Transferable Visual Models From Natural Language Supervision* (CLIP), arXiv:2103.00020 — https://arxiv.org/abs/2103.00020 （本次抓取摘要）
2. [R2] Yang et al., *Chinese CLIP: Contrastive Vision-Language Pretraining in Chinese*, arXiv:2211.01335 — https://arxiv.org/abs/2211.01335 （B，经 README 引用）
3. [R3] OFA-Sys, *Chinese-CLIP 中文 README*（模型规模表、MUGE/Flickr30K-CN/COCO-CN 结果、ONNX/TensorRT 部署、特征归一化要求）— https://github.com/OFA-Sys/Chinese-CLIP （本次抓取 jsDelivr 渲染的 README 全文）
4. [R4] Hugging Face 模型页 `OFA-Sys/chinese-clip-vit-base-patch16` — https://huggingface.co/OFA-Sys/chinese-clip-vit-base-patch16 （B）
5. [R5] Oquab et al., *DINOv2: Learning Robust Visual Features without Supervision*, arXiv:2304.07193 — https://arxiv.org/abs/2304.07193 （本次抓取摘要）
6. [R6] Zhai et al., *Sigmoid Loss for Language Image Pre-Training* (SigLIP), arXiv:2303.15343 — https://arxiv.org/abs/2303.15343 （本次抓取摘要）

**向量检索/数据库**
7. [R7] asg017, *sqlite-vec*（`vec0` 虚表、float/int8/bit 向量、metadata/partition 列、pre-v1 提示）— https://github.com/asg017/sqlite-vec （本次抓取 README）
8. [R8] Meta, *FAISS*（IndexFlatIP/IndexHNSWFlat 等）— https://github.com/facebookresearch/faiss （B）
9. [R9] nmslib, *hnswlib* — https://github.com/nmslib/hnswlib （B）
10. [R10] Chroma — https://github.com/chroma-core/chroma （B）
11. [R11] SQLite 官方文档：*Date And Time Functions* — https://www.sqlite.org/lang_datefunc.html ；*Write-Ahead Logging* — https://www.sqlite.org/wal.html （B）
12. [R12] SQLite 官方文档：*Query Optimizer Overview*（索引选择）— https://www.sqlite.org/optoverview.html （B）
13. [R13] SQLite 官方文档：*FTS5*（可选：物品名全文检索）— https://www.sqlite.org/fts5.html （B）

**中文 NLP / 检测 / 推理**
14. [R14] fxsjy, *jieba 中文分词*（自定义词典）— https://github.com/fxsjy/jieba （B）
15. [R15] Ultralytics, *YOLO-World*（开放词表检测）— https://docs.ultralytics.com/models/yolo-world/ （B）
16. [R16] IDEA-Research, *GroundingDINO* — https://github.com/IDEA-Research/GroundingDINO （B）
17. [R25] ONNX Runtime — https://onnxruntime.ai （B）
18. [R26] ggml-org, *llama.cpp*（本地 GGUF 推理）— https://github.com/ggml-org/llama.cpp （B）

**近邻案例（团队台账级，B）**
19. [R17] Maniar et al., *MemPal: Leveraging Multimodal AI and LLMs for Voice-Activated Object Retrieval in Homes of Older Adults*, arXiv:2502.01801 — https://arxiv.org/abs/2502.01801 （本次抓取摘要，A）
20. [R18] MIT Media Lab, *MemPal* 项目页 — https://www.media.mit.edu/publications/mempal/ （团队台账）
21. [R19] Apple Newsroom, *Introducing Apple Home Collection*（2026-10）— https://www.apple.com/au/newsroom/2026/10/introducing-apple-home-collection-a-new-lineup-of-smart-home-accessories/ （团队台账）
22. [R20] MacRumors, *Ugreen launches HomeAgent hubs*（2026-09）— https://www.macrumors.com/2026/09/04/ugreen-launches-homeagent-hubs-qi2-chargers/ （团队台账）
23. [R21] Kicktraq, *Camtells* 众筹数据 — https://www.kicktraq.com/projects/948304531/camtells-the-first-ai-camera-that-understands-your-space/ （团队台账）
24. [R22] Dealroom, *Memories.ai raises seed extension* — https://dealroom.co/news/135651-memories-ai-raises-8m-seed-extension-for-visual-memory-ai/ （团队台账）
25. [R23] App Store, *Find My Everything* — https://apps.apple.com/cn/app/find-my-everything/id6759879201 （团队台账）
26. [R24] 海康威视专利 CN109993045A（物品查找方法与装置）— https://patents.google.com/patent/CN109993045A/zh （团队台账；PDF 在 `research/raw/`）
27. [R27] 团队竞品台账：[桌面记忆相机_竞品与市场数据_2026-10-22.md](../../桌面记忆相机_竞品与市场数据_2026-10-22.md) 与 `research/notes.md` （B，本项目内部文档）

---

### 附：本文件未覆盖、但与本任务相邻的问题（留给其他分册/后续阶段）

- 检测器/开放词表的具体模型选型与中文提示词工程（属 A 部分：视觉识别）；
- 8–12 周 MVP 排期、里程碑与验收指标（属 C 部分：方案与排期）；
- 商业定价、市场验证、FTO（属团队既有市场报告与法务项，本文仅在 §5 引用结论）；
- 数据标注/自建桌面物品数据集与微调策略（M2 若零样本不达标再启动）。