# Findy 技术调研 A：物品检测与"同一实物跨时刻关联"（re-ID）技术路线

| 项目 | 内容 |
|---|---|
| 文档编号 | Findy-RES-A |
| 版本 / 日期 | v1.0 / 2026-10-28 |
| 作者 | research-a（技术调研员） |
| 范围 | 检测模型选型 + 实例级 re-ID 路线 + 精度预期 + 低成本验证实验设计 |
| 前置事实 | M1 固件已验证：ESP32-S3-EYE v2.2 + OV2640 可拍照、Wi-Fi、SNTP、HTTP（`POST /api/capture`、`GET /api/photo?seq=N`） |
| 目标平台 | 普通 Windows 笔记本，CPU 推理为主，优先复用预训练权重 |
| 检索方式说明 | 本次调研 `web_search` 因运行环境缺少搜索 API key 不可用，全部证据改用 `web_fetch` 直接抓取论文页 / 官方文档 / 仓库原始文件获得；共 21 次抓取（3 次因域名或路径失败，已在正文标注）。**没有做任何模型实测，文中所有精度数字要么来自公开来源并已标注，要么明确标为"推断"。** |

**证据强度标记约定**（全文使用）：
`【论文】`= 经同行评议或 arXiv 正式论文；`【官方文档】`= 项目/厂商官方文档或仓库原始文件（本轮已抓取原文）；`【厂商】`= 厂商宣传性材料；`【博客】`= 第三方博客/社区/百科；`【推断】`= 本调研的分析与推断，**未经验证**。

---

## 0. 结论摘要

1. **架构结论（强）**：ESP32-S3 端侧**不适合**承担 COCO 80 类通用检测。Espressif 官方 `esp-who` 仓库当前只提供人脸检测、人脸识别、行人检测、二维码识别这几类专用轻量示例，**没有通用物体检测示例**【官方文档：[esp-who README](https://github.com/espressif/esp-who)】。因此 Findy 的合理分工是：**端侧只负责"定时抓拍 + 上传"（M1 已验证），全部视觉推理放笔记本**。这一划分不依赖端侧算力升级，风险最低。
2. **检测结论（强）**：现有 COCO 80 类闭集模型**覆盖不了 Findy 的核心物品**——钥匙、钱包、眼镜、耳机、充电器、U 盘、工牌都不在 COCO 80 类内【官方文档：[COCO 数据集 80 类](https://docs.ultralytics.com/datasets/detect/coco/)】。因此"仅靠 YOLO + COCO 权重"的产品形态不成立；必须引入**开放词表检测**或**用户注册 + 类无关实例匹配**。这是本次调研对阶段一影响最大的单条结论。
3. **推荐检测栈（中）**：主路线用 **Grounding DINO 或 OWLv2（Apache-2.0 系）+ DINOv2 特征**以规避许可风险；把 **YOLO11n/s 仅作为内部快速基线**，因为 Ultralytics 仓库整体为 **AGPL-3.0**【官方文档-原始文件：[LICENSE](https://raw.githubusercontent.com/ultralytics/ultralytics/main/LICENSE)、[YOLO11 文档许可声明](https://docs.ultralytics.com/models/yolo11/)】。若产品要闭源分发，直接用 YOLO11/YOLOv8/YOLO-World(Ultralytics 实现)/RT-DETR(Ultralytics 实现) 都会触发 AGPL 传染，需要购买 Enterprise License 或换实现。
4. **关键可行性判断（中）**：Findy 是**低频抓拍**场景（每 10–60 秒一帧），不是 30 FPS 视频流。这使"用重模型"在工程上可行：即便单帧 CPU 推理需 1–3 秒也可接受【推断】。**不要用视频目标检测的 FPS 指标来筛选模型**，这是本项目最容易犯的选型错误。
5. **re-ID 结论（中）**：实例级"同一件实物"关联**没有现成可用模型**。现有公开 re-ID 研究主体是**行人**（Market-1501 / MOT17 等），其评测口径与本场景（固定机位、桌面、无行人运动模式）不同源，**不能据以承诺精度**【推断 + 论文：[BoT-SORT](https://arxiv.org/abs/2206.14651)、[ByteTrack](https://arxiv.org/abs/2110.06864) 均为行人/通用 MOT 设定】。推荐自建轻量方案：**DINOv2 ViT-S/14 全局 embedding 余弦最近邻 + 空间位置先验 + 时间衰减 + 双阈值三态判定**，并用 SIFT/ORB 几何校验做二次确认。
6. **产品捷径（强建议）**：把"同款多件区分"从算法难题降级为产品交互——**用户注册时给每件物品拍一张注册照**（gallery），运行期退化为"单样本检索"，同时天然拿到"这件是哪个"的标签。这比让模型零样本区分两支同款笔现实得多【推断】。
7. **最大现实瓶颈（中）**：OV2640 + 桌面视距下，小物品（钥匙、U 盘）在画面中可能只有 20–40 像素宽；**分辨率而非模型能力**很可能才是检测/关联精度的天花板。抓拍分辨率应取 UXGA(1600×1200) 而非 VGA【推断，基于像素投影估算】。
8. **精度承诺纪律（强）**：本调研**拒绝给出"Findy 能达到 XX% 正确率"的结论**。公开文献里没有"固定机位桌面物品实例关联"的基准数据集，任何具体数字都会是编造。必须先做第 4 节的 1–2 天小样本实验拿到自己的基线，再对外承诺。

---

## 1. 检测模型对比与推荐

### 1.1 场景约束（先定约束，再选模型）

| 约束 | 取值 | 对选型的影响 |
|---|---|---|
| 硬件 | 普通 Windows 笔记本，CPU 为主 | 单帧预算 0.05–3 s 都可接受；显存不构成约束（甚至可无独显） |
| 帧率需求 | 每 10–60 s 一帧（低频抓拍） | **FPS 不是筛选指标**；可用 1–3 s/帧的重模型 |
| 目标类别 | 桌面杂物，**大量超出 COCO 80 类** | 闭集模型只能做基线；主路线需开放词表或注册式 |
| 目标尺寸 | 小（钥匙 3–8 cm 实物，画面 20–60 px） | 需要高分辨率输入 + 输入尺寸不能一味降 |
| 部署形态 | 单机、离线、低成本 | 优先可本地跑的权重；避免依赖云 API 计费 |
| 分发形态 | 若商业化 → **闭源分发** | AGPL-3.0 是硬约束，必须提前决策 |

### 1.2 闭集（COCO 80 类）模型对比

数字均来自官方文档表格，**为本轮抓取到的原文数据**，非本项目实测。

| 模型 | COCO mAP<sup>50-95</sup> | CPU ONNX 延迟 | T4 TensorRT10 | 参数量 | 许可 | 证据 |
|---|---|---|---|---|---|---|
| YOLO11n | 39.5 | 56.1 ± 0.8 ms | 1.5 ms | 2.6 M | AGPL-3.0（或商业授权） |【官方文档】[YOLO11](https://docs.ultralytics.com/models/yolo11/) |
| YOLO11s | 47.0 | 90.0 ± 1.2 ms | 2.5 ms | 9.4 M | 同上 | 同上 |
| YOLO11m | 51.5 | 183.2 ± 2.0 ms | 4.7 ms | 20.1 M | 同上 | 同上 |
| YOLO11x | 54.7 | 462.8 ± 6.7 ms | 11.3 ms | 56.9 M | 同上 | 同上 |
| YOLOv8n | 37.3 | 80.4 ms | 0.99 ms (A100) | 3.2 M | AGPL-3.0 |【官方文档】[YOLOv8](https://docs.ultralytics.com/models/yolov8/) |
| YOLOv8s | 44.9 | 128.4 ms | 1.20 ms | 11.2 M | AGPL-3.0 | 同上 |
| YOLOv8m | 50.2 | 234.7 ms | 1.83 ms | 25.9 M | AGPL-3.0 | 同上 |
| RT-DETR-R50 | 53.1 | 未取得 CPU 数据 | 108 FPS（≈9.3 ms） | ~42 M（R50 骨干） | 实现 EM 差异大，须逐个核对 |【论文】[RT-DETR](https://arxiv.org/abs/2304.08069) |
| RT-DETR-R101 | 54.3 | 未取得 | 74 FPS（≈13.5 ms） | 更大 | 同上 | 同上 |
| DETR（原始） | ~42（R50，500 epoch 设定） | 慢，不适合 CPU | — | ~41 M | Apache-2.0（原始实现） |【论文】[DETR](https://arxiv.org/abs/2005.12872)（本轮未抓取原文，标为常见公开值，**待核**） |
| SSD-MobileNetV2 | 约 20–25 量级 | 很快（移动端毫秒级） | — | ~3–5 M | Apache-2.0（TF 官方实现） |【官方文档】[TFLite 目标检测](https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector)（**本轮抓取失败，数字未核验，仅作量级参考**） |

**解读（推断）**：
- YOLO11n 官方 CPU ONNX 56.1 ms/帧@640 —— 意味着**普通笔记本 CPU 上单张约 0.06–0.3 s（考虑实际 CPU 弱于基准机、Python 前后处理开销、JPEG 解码）**。哪怕放大到 1280 输入，单帧仍在秒级以内，对 10–60 s 一帧完全够用。
- SSD-MobileNet 这类极轻模型 mAP 只有 YOLO11n 的 1/2 左右，**在笔记本上没有任何理由为省算力选它**——它唯一的场域是端侧 MCU。这条结论对本项目很重要：**不要为了"看起来轻量"选 SSD-MobileNet**。
- RT-DETR 论文核心贡献是**去 NMS + 端到端**（"DETRs Beat YOLOs on Real-time Object Detection"），在 T4 上 53.1 AP @108 FPS。对 Findy 的低频场景，RT-DETR 的优势（无 NMS 调参、无重叠框后处理）比速度更有价值【论文】。

### 1.3 开放词表检测（本场景真正的主力方向）

| 模型 | 核心能力 | 公开指标 | 许可 | 证据 |
|---|---|---|---|---|
| YOLO-World（RepVL-PAN + 区域-文本对比） | 零样本按文本提示检测任意类别，实时 | LVIS 上 **35.4 AP @52 FPS（V100）** | Ultralytics 版为 AGPL-3.0；AILab-CVC 原仓库 LICENSE 本轮 `main/master` 均返回 **404 未取得**，**须自行核对** |【论文】[YOLO-World](https://arxiv.org/abs/2401.17270)；【官方文档-原始文件】许可证 404 实测 |
| Grounding DINO | 文本/指代表达驱动开放集检测，语言-视觉紧融合 | **COCO 零样本 52.5 AP**；ODinW 零样本均值 26.1 AP | Apache-2.0（业界通识，**本轮未抓取 LICENSE，待核**） |【论文】[Grounding DINO](https://arxiv.org/abs/2303.05499)；[仓库](https://github.com/IDEA-Research/GroundingDINO) |
| OWLv2 | 两阶段开放词表检测，类别可由**文字描述 / 图像样例 / 两者融合**指定 | LVIS 开放词表基准上文本分类器优于此前所有 OVOD 工作；多模态融合优于单模态 | Apache-2.0（HF Transformers 实现；**model card 本轮未抓取，待核**） |【论文】[OWLv2](https://arxiv.org/abs/2306.05493)；[HF 权重卡](https://huggingface.co/google/owlv2-base-patch16-ensemble) |

**关键洞察**：OWLv2 论文明确支持**用图像样例（image exemplars）指定类别**，而不只是文本【论文】。这对 Findy 极其关键——用户注册一件"我的钥匙"时给一张样例图，正好落在 OWLv2 的原生能力范围内。这是"文本提示 + 样例提示"双通道的产品化落点，比纯文本 prompt 工程稳健得多。

**开放词表的代价（推断，必须实验验证）**：Grounding DINO base 级模型参数量约 1.7 亿量级，笔记本 CPU 单帧推理通常在**秒级到十秒级**。低频抓拍能容忍，但要注意：**开放词表检测的框质量普遍不如同规模闭集模型**，且对 prompt 措辞敏感（"keys" vs "a bunch of keys" vs "keychain" 可能给出不同框）。这需要第 4 节的 prompt 稳定性实验来定。

### 1.4 许可风险（阶段一就必须决策的事）

**已核实事实**：Ultralytics 仓库 `LICENSE` 原文为 **GNU AFFERO GENERAL PUBLIC LICENSE Version 3**【官方文档-原始文件，本轮抓取】；YOLO11 与 YOLOv8 文档均声明权重"在 AGPL-3.0 与 Enterprise 许可下提供"【官方文档】。

AGPL-3.0 的实际含义（**法律判断，非技术结论，需法务确认**）：
- 若 Findy 以**闭源方式分发**（含打包进客户端、SaaS 远程提供），使用该代码/权重会要求以 AGPL 开放 Findy 相应源码。
- "内部研究/不分发"阶段通常风险低；但**阶段一的 Demo 一旦对外发布就进入灰色地带**。
- 规避路径三选一：(a) 购买 Ultralytics Enterprise License；(b) 换非 AGPL 实现（Grounding DINO / OWLv2 / PaddleDetection 版 RT-DETR / YOLOX 等）；(c) 保持开源。

**建议**：阶段一一律**只用 Apache-2.0 系栈做可以展示的成果**，AGPL 栈仅限本地内部实验并显式标注。这条建议几乎没有成本，却能避免后期返工。

### 1.5 推荐结论

| 层次 | 推荐 | 理由 | 强度 |
|---|---|---|---|
| **主检测器（可分发）** | Grounding DINO（或 OWLv2），文本 + 样例双提示 | 开放词表覆盖非 COCO 物品；Apache 系许可 | 中 |
| **快速基线（内部）** | YOLO11n / YOLO11s + COCO | 官方 CPU 56 ms；一天内能跑通全链路；**限于内部分析，不对外分发** | 强 |
| **候选框补充** | 用户注册样例 → OWLv2 样例通道 | 把"发现物品"变成"确认这个物品在不在" | 中 |
| **端侧（ESP32-S3）** | 只做抓拍 + 上传（M1 已实现） | 官方无通用检测示例；算力/内存不足【推断】 | 强（分工）/ 推断（不可行性细节） |
| **明确不推荐** | SSD-MobileNet 做主力；端侧跑 COCO 检测；用 FPS 指标选型 | 精度低且无算力收益；场景是低频抓拍 | 中 |

**关于"YOLO26"**：Ultralytics 文档已出现 YOLO26（宣称端到端 NMS-free、面向边缘部署）与 YOLO27 预告【官方文档，本轮抓取 YOLO11 页可见导航与内文提及】。**结论：不要现在锁死具体版本号**。Findy 的选型应锁定"能力档位（开放词表 / 闭集 / 注册式）"，因为 YOLO 系列每 6–12 个月换代一次，而 AGPL 与场景约束不会变。

### 1.6 ESP32-S3 端侧可行性（明确标注为推断）

- **已核实**：ESP-WHO 官方仓库支持 ESP32-S3-EYE 板卡（Camera / LCD / microSD / Audio），提供的示例为人脸检测、人脸识别、行人检测、二维码识别；模型部署走 ESP-DL【官方文档：[esp-who](https://github.com/espressif/esp-who)、[ESP-DL User Guide](https://docs.espressif.com/projects/esp-dl/en/latest/)】。
- **推断（未实测）**：ESP32-S3（Xtensa LX7 双核 @240 MHz，板载 PSRAM）上跑 COCO 80 类通用检测**不可行或精度不可用**；ESP-DL 的典型工作负载是 int8 量化的 1–3 类专用小模型（人脸、行人）。依据：官方示例集本身就是"只有这几类"，而不是"有 80 类但我们没找到"。
- **因此**：Findy 的端侧定位应固化为**采集终端**，不要在阶段一投入端侧推理。这与 M1 固件已验证的能力完全对齐，**零额外风险**。

---

## 2. 实例关联（re-ID）路线与证据

### 2.1 先把问题定义准

Findy 要的不是"这张图里有没有杯子"，而是"**这一帧里的杯子，和 3 天前记录的那个杯子，是不是同一只实物**"。这是 **instance-level re-identification（实例级重识别）**，与公开研究里占绝对主流的 **person re-ID（行人重识别）** 是两个问题：

| 维度 | 行人 re-ID（公开研究主体） | Findy 桌面物品 re-ID |
|---|---|---|
| 类别先验 | 全是人，类内差异靠衣着 | 类别杂，且**同款多件**（两支一样的笔）是主要难点 |
| 视角 | 跨摄像头、大视角变化 | **固定机位**，视角几乎不变（这是巨大红利） |
| 背景 | 复杂、变化 | 固定桌面，背景可用作位置先验 |
| 姿态 | 人体姿态变化 | 物品被移动/旋转/遮挡 |
| 数据 | Market-1501 / MSMT17 等成熟基准 | **无公开基准** |

**结论（强）**：**没有可以直接拿来用的公开"桌面物品实例 re-ID"基准或预训练模型**。公开 re-ID 论文的 mAP/Rank-1 数字**不能**作为 Findy 的精度依据。任何"用 Market-1501 上 95% mAP 所以我们也行"的推理都是错的。这一条是本调研最重要的诚实边界。

### 2.2 路线 A：全局外观 embedding（推荐主力）

| 编码器 | 输出维度 | 关键公开证据 | 许可 | 证据强度 |
|---|---|---|---|---|
| DINOv2 ViT-S/14 | 384 | 官方 model card：Oxford-H 检索（最近邻）**mAP 43.2**；ViT-B 49.5；ViT-L 54.0；k-NN ImageNet 79.0%（ViT-S） | 官方 model card 标注 **Apache-2.0**（本轮抓取原文）；**注意**：社区长期传闻早期版本权重为 CC-BY-NC-4.0，商用前必须以拉取当次仓库说明为准 |【官方文档-原始文件】[DINOv2 MODEL_CARD](https://raw.githubusercontent.com/facebookresearch/dinov2/main/MODEL_CARD.md)；【论文】[DINOv2](https://arxiv.org/abs/2304.07193) |
| CLIP（ViT-B/32 等） | 512 | 零样本 ImageNet 追平原版 ResNet-50；400M 图文对训练 | MIT（OpenAI 实现，**待核**） |【论文】[CLIP](https://arxiv.org/abs/2103.00020) |
| ResNet-50（ImageNet 预训练） | 2048 | 经典基线，参数量 25.6 M | 宽泛（torchvision 实现） |【论文】[ResNet](https://arxiv.org/abs/1512.03385)（本轮未抓取，常见公开值） |

**为什么优先 DINOv2 而不是 CLIP**（推断，但依据充分）：DINOv2 是**纯视觉自监督**训练，目标就是"通用视觉特征 + 检索"，官方 model card 直接把"image retrieval using nearest neighbors"列为直接用途；CLIP 是图文对齐特征，其空间对"这是我的钥匙 vs 这是另一支同款钥匙"这种**细粒度实例差异**并不特别优化。检索任务应对齐检索型特征。**但这只是先验，必须由第 4 节实验裁决**——实验里两条都要跑，成本几乎相同。

**工程要点**：
- 用 **CLS token**（或 CLS + patch 均值拼接）做实例向量，L2 归一化后用**余弦相似度**；对 10–50 件物品规模，暴力最近邻足够，无需 FAISS。
- 输入统一 resize 到 224（DINOv2 patch=14，边长须为 14 的倍数：224 合法）。
- **必须在物品框内裁剪后再编码**，不要整图编码——否则背景（固定桌面）会主导相似度，导致"同一位置的不同物品"被误判为同一件。这是本场景最容易踩的坑（推断，机理明确）。

### 2.3 路线 B：局部特征 + 几何校验（补充手段）

- **SIFT**（Lowe 2004，尺度不变特征）+ **RANSAC 单应/基础矩阵**：对纹理丰富的物品（钥匙齿形、包装盒印刷、笔记本贴纸）判别力很强；对**光滑无纹理物品（白色充电头、玻璃杯）会失效**。实现见 [OpenCV SIFT 文档](https://docs.opencv.org/4.x/da/df6/tutorial_py_sift_intro.html)（本轮未抓取，标为官方文档待核）。专利已过期，OpenCV 4.4+ 主库可直接用【博客/社区，待核】。
- **ORB**（Rublee 2011，[论文](https://www.cs.ubc.ca/~lowe/papers/rublee11.pdf) 未抓取待核）：速度远快于 SIFT，旋转不变，尺度不变性弱。适合做**粗筛**。
- **判据**：匹配点对 ≥ N_min 且 RANSAC 内点率 ≥ r_min → 强证据"同一件"；否则交给路线 A。

**定位**：B 不单独使用，而是作为**"高置信确认器"**——当路线 A 的相似度落在不确定区间时，若局部特征给出强几何一致，直接判"同一件"。这是把不确定案例压低成本处理的关键（推断）。

### 2.4 路线 C：低层描述子（快速排斥筛）

- **颜色直方图**（HSV，对光照有一定鲁棒性）/ 主色、尺寸比例、长宽比。
- 作用不是判定，而是**排除**：两件物品颜色分布差异极大且长宽比不兼容 → 直接判"不同"，省掉 embedding 计算。
- 风险：黑色钥匙 vs 黑色 U 盘颜色几乎相同 → C 只能排除，不能确认（推断）。

### 2.5 时空先验与 tracking-by-detection

- **空间先验（本场景红利）**：固定机位下，同一物品通常出现在同一桌面区域。可把画面划分为 K 个区域（如 3×3 网格 + 自定义"钥匙盘/笔筒/充电区"），跨时刻同一区域的事件给加分。这是 Findy 相对通用 re-ID 的**结构性优势**。
- **ByteTrack**：核心是"关联几乎每一个检测框"，用低分框与轨迹相似度恢复被遮挡的真实目标，在 9 个 SOTA 跟踪器上 IDF1 提升 1–10 点；MOT17 test 上 80.3 MOTA / 77.3 IDF1 / 63.1 HOTA，V100 30 FPS【论文】。
- **BoT-SORT**：融合运动 + 外观 + **相机运动补偿** + 改进 Kalman 状态向量；MOT17 上 80.5 MOTA / 80.2 IDF1 / 65.0 HOTA【论文】。

**但在 Findy 里 tracking 的作用要重新定位（推断，重要）**：
- Findy 是**低频抓拍**，帧间间隔 10–60 s，**运动连续性假设完全失效**——Kalman 运动模型在 60 秒间隔下毫无意义，ByteTrack/BoT-SORT 的核心机制（帧间 IoU/运动预测）不适用。
- tracking 在 Findy 里**只做两件事**：(1) **去重入库**——同一物品在连续几次抓拍里只记一条事件，避免事件流被同一物品刷屏；(2) **短暂遮挡桥接**——若抓拍间隔 < 2 s 的连拍序列存在。
- **结论：不要把 tracking 当作 re-ID 方案。** 时长跨度（小时/天）的关联必须靠外观 embedding + 空间先验，而不是 tracking。这是本调研对"常见方案直觉"的一次纠偏。

### 2.6 开放集判定：阈值、三态与"不确定"

实例关联本质是**开放集识别**：查询物品可能是数据库里从未记录过的新物品，必须允许"没有匹配"。

建议的**三态判定**（推断，工程方案）：

```
对查询 q，在 gallery 中取相似度 top-1 = s1，top-2 = s2：
  if s1 ≥ τ_high  且 (s1 − s2) ≥ τ_margin  →  ACCEPT（判定为同一实物）
  elif s1 <  τ_low                          →  REJECT（新物品 / 未记录过）
  else                                       →  UNCERTAIN（触发二次校验或问用户）
```

- `s1 − s2` 的 margin 用来对付**同款多件**：两支同款笔的 s1、s2 会非常接近，margin 判据能自动把这种"人类也难分"的情况推到 UNCERTAIN，而不是硬猜。
- 阈值不给默认值——**必须由第 4 节的阈值扫描在自采数据上确定**，并要求同时满足"误关联率 ≤ 目标值"。
- UNCERTAIN 的降级策略见 3.3。

### 2.7 推荐组合架构（阶段一落地形态）

```
端侧 ESP32-S3-EYE ──(定时抓拍, UXGA JPEG)──HTTP──> 笔记本
                                                      │
                                        ① 检测（Grounding DINO / OWLv2，文本+样例提示）
                                                      │  得到 bbox + 粗类标签
                                        ② 框内裁剪 → DINOv2 ViT-S/14 CLS embedding（L2 归一化）
                                                      │
                                        ③ 候选筛选：同粗类 + 位置先验（区域 ID）+ 时间衰减
                                                      │
                                        ④ 打分排序 → s1 / s2 → 三态判定
                                                      │
                              ⑤ UNCERTAIN → SIFT/ORB 几何校验 → 仍不确定则问用户
                                                      │
                                        ⑥ 写入事件库（物品ID / 时间 / 区域 / 图像 seq / 置信度）
                                                      │
                                        ⑦ 自然语言查询"我的钥匙最后在哪" → 按物品ID取最近事件
```

**打分函数建议**（推断，需消融）：

```
S(q, g) = w1·cos(e_q, e_g) + w2·1[region(q)=region(g)] + w3·exp(−Δt/τ) + w4·shape_compat(q,g)
```

- `w1` 为主项，`w2` 空间先验，`w3` 时间衰减（近期事件更可能是同一件），`w4` 形状/长宽比兼容性（0/1 硬约束更稳妥）。
- **消融实验**必做：只用 w1 / w1+w2 / 全量，看每一步增益。若 `w2` 无增益，说明位置先验假设不成立，产品逻辑要调整。

---

## 3. 本场景现实精度预期与不确定处理

> **本节性质声明**：以下**全部是推断与机制分析，没有任何实测数据支撑**。公开文献中不存在与 Findy 完全同构的基准（固定机位 + 桌面杂物 + 跨天 + 同款多件），因此**任何具体百分比都是不可靠的**。本节给出的是"影响因素 + 上下界逻辑 + 该做什么实验"，而不是"精度预测值"。

### 3.1 影响精度的因子（按影响量级排序，推断）

| 因子 | 影响机制 | 量级判断 | 缓解手段 |
|---|---|---|---|
| **画面像素不足** | 小物品 20–40 px，embedding 与检测框都不可靠 | **很可能最大瓶颈** | 抓拍取 UXGA；摄像头靠近桌面；对目标区域做数字变焦裁切 |
| **同款多件** | 两支同款笔的 embedding 几乎相同，理论上限就是 1/k | **第二大瓶颈，产品必须绕开** | 注册照 + 空间先验 + margin 判据 + 问用户 |
| **光照变化（白天/夜间/台灯）** | 颜色、纹理、阴影全变；DINOv2 有一定鲁棒性但非不变 | 大 | 固定白平衡/曝光（端侧可关 AWB/AE）；采集时覆盖多时段并做归一化 |
| **遮挡 / 堆叠** | 物品被别的物品压住，只露出局部 | 中 | 检测阶段允许多框；关联阶段用局部特征（SIFT）补 |
| **旋转 / 翻面** | 同一物品背面与正面外观差异大 | 中 | 多视角注册照（正/背各一张）；或用局部特征 |
| **背景主导 embedding** | 未裁剪就编码 → 固定桌面背景拉高相似度 | 中（但**易被误认为模型强**） | 严格框内裁剪；背景做测底评估 |
| **类别判定错误** | 开放词表把钱包认成笔记本 | 中 | 类别只用于候选筛选，不参与最终判定；保留"未知类" |

### 3.2 可辩护的精度推理（而非预测）

可以从**信息论与任务结构**给出几条可辩护的结论：

1. **上限存在且不高**：对 k 件外观相同的物品，任何纯外观方法的理论 top-1 上限是 `1/k`。所以"两支同款笔"场景**必须**引入注册照或空间先验，否则算法层面无解【推断，逻辑必然】。
2. **固定机位显著降低难度**：通用 re-ID 的主要难点是视角/光照/背景/姿态的联合变化。Findy 固定机位后只剩"光照 + 物品移动 + 遮挡"，**问题难度应显著低于通用 re-ID**【推断】。但"显著低于"不等于"准确率高"，仍需实测。
3. **DINOv2 的检索能力有官方证据但任务不对齐**：Oxford-H 最近邻检索 mAP 43.2–58.2（ViT-S→ViT-g）【官方文档-原始文件】说明"通用视觉检索有效"；但那是**建筑/地标级**检索，与"同类小物品实例区分"难度不同源。**只能作为"方法可行"的证据，不能作为"精度够用"的证据**【推断】。
4. **CLIP 零样本能力同样不对齐**：CLIP 论文的零样本 ImageNet 追平 ResNet-50 是**类别级**判别，不是实例级【论文】。用 CLIP 区分两支同款笔属于超出其训练目标的使用。

**因此，能给产品的最强承诺只能是**：*"固定机位、10–20 件、有注册照、光照稳定时表现良好；同款多件与强光照变化时需要用户确认。"* 具体阈值待 4 节实验量化。

### 3.3 不确定处理（产品级设计，比提升精度更划算）

1. **三态输出**：ACCEPT / REJECT / UNCERTAIN。UI 上把 UNCERTAIN 说成人话："我好像见过它，但不太确定"。
2. **证据链展示**：给出"最后见到时间 + 区域 + 缩略图"。**让用户看缩略图自己判断**，比模型输出一个错误的高置信答案伤害小得多。
3. **一问一答确认**：UNCERTAIN 时弹出 2 张候选图让用户选，选择结果**回写 gallery**（在线学习）。这是零成本精度提升。
4. **置信度校准**：不要直接暴露原始余弦相似度（用户无法理解）。用实验数据拟合一个分段映射（如 <τ_low 低 / τ_low–τ_high 中 / ≥τ_high 高），并**在文档里说明这是经验映射**。
5. **失败可解释**：查不到时给"最后一次见到它的时间"，而不是空结果——"我最后一次看到它是在 3 小时前的桌面左侧"本身就是有价值的回答。
6. **绝不静默错连**：若系统把 A 物品的事件连到 B 物品，对用户信任的破坏远大于"未找到"。**误关联率应比召回率更严格地控制**（建议 FAR 目标 ≤ 2%，见 4.4）。

---

## 4. 低成本验证实验设计（可执行）

> 目标：用 **2–3 人日、0 元额外硬件**（复用现有 ESP32-S3-EYE + 笔记本）拿到自己的第一组真实数字，用来裁决第 1、2 节的技术路线。**不做这一步就选型 = 赌博。**

### 4.1 要回答的 4 个问题（对应 go/no-go）

- **Q1 检测**：Grounding DINO / OWLv2 在本场景的**检出率**（能否稳定框出钥匙、钱包、眼镜、耳机、充电器）？prompt 换 3 种写法结果是否稳定？
- **Q2 关联**：DINOv2 / CLIP 两种 embedding 的 **top-1 关联准确率**谁高？差距是否显著？
- **Q3 同款多件**：两支同款笔能否被分开？（决定是否需要"注册照 + 问用户"）
- **Q4 阈值**：在目标误关联率下，τ_high / τ_low / τ_margin 取多少？

### 4.2 数据采集协议

**物品清单（12 件，覆盖不同难度）**

| 编号 | 物品 | 难度点 |
|---|---|---|
| O01 | 钥匙串 | 小、金属反光、不在 COCO |
| O02 | 钱包 | 不在 COCO、纹理丰富 |
| O03 | 眼镜 | 细结构、透明镜片 |
| O04 | 无线耳机盒 | 光滑、无纹理 |
| O05 | 充电器（白色） | 光滑、同款常见 |
| O06 | U 盘 | 极小 |
| O07 | 笔记本 A（黑封皮） | 大、平坦、无纹理 |
| O08 | 水杯 | 圆柱、透明/半透明 |
| O09–O10 | **两支同款笔** | **同款多件（关键对照）** |
| O11–O12 | 两个同款钥匙扣 | 同款多件 |

**摆放协议**
- 固定 3 个区域：左区（钥匙盘）/ 中区 / 右区（笔筒）。每次抓拍前按预设脚本决定每件物品放在哪个区域、正/背面。
- 每天 3 个时段：上午（自然光）、下午（自然光偏暖）、夜间（仅台灯）。**这是光照变量的最小可行覆盖。**
- 每天 4 次抓拍，连续 **5 天** → 共 60 次抓拍，每次抓拍 2 档分辨率（UXGA + VGA 各一张，用于验证"分辨率是瓶颈"的假设）。

**采集命令（复用 M1 已验证接口）**
```powershell
# 每轮抓拍：触发一次，取回图像，按 seq 落盘
Invoke-WebRequest -Method POST -Uri "http://<esp32-ip>/api/capture"
$seq = (Invoke-WebRequest -Uri "http://<esp32-ip>/api/status").Content  # 若固件无 status，改为本地累加计数器
Invoke-WebRequest -Uri "http://<esp32-ip>/api/photo?seq=$seq" -OutFile "D:\Findyy\.tmp\capture\day01_t0900_seq$seq.jpg"
```
> 若固件无"查询当前 seq"接口，用一个本地计数器文件自增即可（不改固件）。**标签文件 `labels.csv` 由人工填写**（`seq, object_id, region, orientation, period, day`），这是全套实验唯一的标注工作量，约 12 件 × 60 帧 ≈ 720 行，**约 1 小时**。

### 4.3 样本量与统计判据（先算清再采集）

- **Gallery / Query 划分**：Day1–Day3 全部抓拍做 **gallery**（每件物品约 3 天 × 4 次 × 3 时段 ≈ 36 条记录）；Day4–Day5 做 **query**（约 24 次抓拍 × 12 件 ≈ 280 个查询目标）。
- **最小可用规模**：每个"难度条件"至少 **50 个独立查询** 才能把 95% 置信区间压到 ±10 个百分点以内（Wilson 区间，见下）。低于 50 的结论只能当方向。
- **Wilson 95% 置信区间公式**（避免用正态近似在 p 接近 1 时失真）：

```
center = (p̂ + z²/(2n)) / (1 + z²/n)
half   = z·√( p̂(1−p̂)/n + z²/(4n²) ) / (1 + z²/n)
CI95  = center ± half,   z = 1.96
```

  例（**示例算数，非实测**）：p̂ = 0.80, n = 100 → CI95 ≈ **[0.711, 0.867]**（±7.8pp）；n = 50 → CI95 ≈ **[0.674, 0.883]**（±10.4pp）。
  参考：[Wilson score interval](https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval)【博客/百科】。

- **零失败事件的上界（Rule of Three）**：若在 n 次关联中**一次错都没有**，则真实错误率的 95% 上界约 `3/n`。n=100 → 3%；n=300 → 1%。
  **所以"我们的误关联率 < 1%"这句话至少需要约 300 次零错误关联才能支撑。** 阶段一若只采到 ~280 次查询且有个别错误，就**只能说"误关联率约 1%–3% 量级"**，不能说 "<1%"。
  参考：[Rule of three](https://en.wikipedia.org/wiki/Rule_of_three_(statistics))【博客/百科】。

### 4.4 指标定义（写进实验脚本，避免口径漂移）

设 gallery 中有 N 个物品实例；对每个 query 目标 q（其真实实例 ID 为 `id(q)`）：

| 指标 | 公式 | 说明 |
|---|---|---|
| **Top-1 关联准确率** | `Acc@1 = (1/Q)·Σ 1[ argmax_g S(q,g) = id(q) ]` | 主指标；只统计"该实例确实在 gallery 中"的 query |
| **误关联率 FAR** | `FAR = 错误ACCEPT数 / ACCEPT总数` | **比 Acc@1 更重要**；直接影响用户信任 |
| **漏关联率 / 拒识率** | `FRR = 应ACCEPT但被判REJECT或UNCERTAIN的比例` | 可容忍，用 UI 兜底 |
| **不确定率** | `UR = UNCERTAIN数 / 总query数` | 目标：≤ 15–20%（过高则产品不可用） |
| **Rank-k 命中率** | `Acc@k = 前k个候选含正确实例的比例` | 用于"给 2 个候选让用户选"的交互 |
| **阈值扫描曲线** | 对 τ 网格扫描，画 FAR–Acc@1 曲线，取 FAR≤目标值时的最大 Acc@1 | 定 τ_high / τ_low / τ_margin 的唯一正当方法 |
| **检测检出率** | `Recall_det = 被正确框出的目标数 / 目标总数`（IoU≥0.5） | Q1 的答案 |
| **prompt 稳定性** | 3 种 prompt 写法下检出率的最大差值 | 差值 > 15pp 说明方案脆弱 |

**注意**：`Acc@1` 与 `FAR` 必须**同时报告**。只报 Acc@1（例如 90%）而隐藏 FAR，是这类系统最常见的过度承诺方式。

### 4.5 执行步骤（1–2 天内可跑完）

**阶段 0：环境（0.5 天）**
1. 笔记本用 Python venv（工作区已有 `.venv`），`pip install` 只在虚拟环境内装：`torch`(CPU 版)、`transformers`、`opencv-python`、`numpy`、`pandas`。
2. 下载两组权重：Grounding DINO base（或 OWLv2 base）、DINOv2 ViT-S/14 + CLIP ViT-B/32。**记录下载时间点的仓库 LICENSE 原文**（许可核对，见 1.4）。
3. 冒烟测试：对 3 张已有抓拍图跑检测 + 编码，确认不报错、单帧耗时记录在案（这是第一个"实测替代推断"的数字）。

**阶段 1：采数（1 天，含人工摆放）**
4. 按 4.2 脚本连续 5 天（可用"压缩为 1 天 × 5 轮次"的加速版：把 5 天改成 5 个不同光照/摆放轮次，代价是失去真实跨天漂移）。
5. 填 `labels.csv`。**采集与标注必须分离**：先全采完再标，避免标注者影响摆放。

**阶段 2：评测（0.5 天）**
6. 检测评测：对每个 query 帧跑检测器，算 `Recall_det`；换 3 种 prompt 各跑一遍（如 `"keys"` / `"a set of keys"` / `"keychain"`）。
7. 关联评测：对每个检测框裁剪→ 编码 → 与 gallery 全量比余弦相似度 → 取 top-1/top-2 → 记录 `s1, s2`。
8. 阈值扫描：在 `s1` 上扫 0.50→0.95（步长 0.01），每个阈值算 Acc@1 / FAR / FRR / UR；同时扫 `τ_margin` ∈ {0.00, 0.03, 0.05, 0.08}。
9. 消融：仅 embedding / +区域先验 / +时间衰减 / +SIFT 校验，逐项看增益。
10. 分组统计：按物品（O01–O12）、按时段（上午/下午/夜间）、按分辨率（UXGA vs VGA）、按"是否同款多件"分别报 Acc@1 —— **分组结果比总平均更有决策价值**。

**阶段 3：结论（0.5 天）**
11. 输出一页表：路线 × (Acc@1, FAR, UR, 单帧耗时) → 填进本文第 5 节的"待验证项"。

### 4.6 判定标准（预先写死，避免事后解释）

| 观察结果 | 决策 |
|---|---|
| Acc@1 ≥ 0.80 且 FAR ≤ 0.03（且 UR ≤ 0.20） | **Go**：按 2.7 架构进入阶段二；把该组数字写入产品承诺上限 |
| 0.60 ≤ Acc@1 < 0.80 | **有条件 Go**：必须带"注册照 + 候选二选一"交互；同款多件场景强制人工确认 |
| Acc@1 < 0.60 或 FAR > 0.10 | **No-Go（当前方案）**：改走"用户全量注册 + 仅做存在/时间/区域记录"，把 re-ID 降级为辅助功能（此时产品价值仍在："告诉我钥匙最后出现在哪一区"） |
| 夜间组 Acc@1 比上午组低 > 20pp | 光照是主导因素 → 优先解决硬件（补光/固定曝光），而不是换模型 |
| UXGA 组显著优于 VGA 组 | 分辨率是瓶颈 → 抓拍一律 UXGA，并考虑裁切目标区域再编码 |
| 三种 prompt 检出率差异 > 15pp | 开放词表不稳定 → 改用"用户注册样例"通道（OWLv2 样例提示）或封闭词表 |

### 4.7 成本估算

| 项 | 成本 |
|---|---|
| 硬件 | **0 元**（ESP32-S3-EYE 现有 + 笔记本现有） |
| 软件 | **0 元**（全部开源权重，本地 CPU 推理） |
| 人力 | 采集 0.5 人日 + 标注 0.5 人日 + 评测 0.5 人日 + 分析 0.5 人日 ≈ **2 人日** |
| 主要风险 | 开放词表模型下载体积较大（数百 MB 至 GB 级）；若网络受限需提前准备离线权重 |

---

## 5. 已验证 vs 推断的边界

> 这张表是本文档的"可信度地图"。对外引用本文档时，**只能引用"已验证"列**。

### 5.1 本轮已由公开来源直接验证的结论

| # | 结论 | 证据 | 强度 |
|---|---|---|---|
| V1 | Ultralytics 仓库许可证为 AGPL-3.0（原文 "GNU AFFERO GENERAL PUBLIC LICENSE Version 3"） | [LICENSE 原始文件](https://raw.githubusercontent.com/ultralytics/ultralytics/main/LICENSE) | 强（原始文件） |
| V2 | YOLO11 权重在 AGPL-3.0 与 Enterprise 双许可下提供 | [YOLO11 文档](https://docs.ultralytics.com/models/yolo11/) | 强（官方文档） |
| V3 | YOLO11n/s/m/x COCO mAP = 39.5 / 47.0 / 51.5 / 54.7；CPU ONNX 延迟 56.1 / 90.0 / 183.2 / 462.8 ms | 同上 | 强（官方文档表格） |
| V4 | YOLOv8n/s/m COCO mAP = 37.3 / 44.9 / 50.2；CPU ONNX 80.4 / 128.4 / 234.7 ms | [YOLOv8 文档](https://docs.ultralytics.com/models/yolov8/) | 强（官方文档表格） |
| V5 | RT-DETR-R50/R101 COCO AP 53.1/54.3，T4 上 108/74 FPS；R50 比 DINO-R50 高 2.2 AP、快约 21 倍 | [RT-DETR 论文](https://arxiv.org/abs/2304.08069) | 强（论文摘要） |
| V6 | YOLO-World 在 LVIS 上 35.4 AP @52 FPS（V100），零样本实时开放词表 | [YOLO-World 论文](https://arxiv.org/abs/2401.17270) | 强（论文摘要） |
| V7 | Grounding DINO 零样本 COCO 52.5 AP、ODinW 均值 26.1 AP | [Grounding DINO 论文](https://arxiv.org/abs/2303.05499) | 强（论文摘要） |
| V8 | OWLv2 支持文本/图像样例/二者融合三种类别指定方式，多模态融合优于单模态 | [OWLv2 论文](https://arxiv.org/abs/2306.05493) | 强（论文摘要） |
| V9 | ByteTrack：MOT17 test 80.3 MOTA / 77.3 IDF1 / 63.1 HOTA @30FPS V100；对 9 个跟踪器 IDF1 提升 1–10 点 | [ByteTrack 论文](https://arxiv.org/abs/2110.06864) | 强（论文摘要） |
| V10 | BoT-SORT：MOT17 上 80.5 MOTA / 80.2 IDF1 / 65.0 HOTA | [BoT-SORT 论文](https://arxiv.org/abs/2206.14651) | 强（论文摘要） |
| V11 | DINOv2 model card：Oxford-H 最近邻检索 mAP ViT-S 43.2 / ViT-B 49.5 / ViT-L 54.0 / ViT-g 58.2（带 registers）；许可标注 Apache-2.0 | [DINOv2 MODEL_CARD](https://raw.githubusercontent.com/facebookresearch/dinov2/main/MODEL_CARD.md) | 强（官方原始文件） |
| V12 | DINOv2 官方将 "image retrieval using nearest neighbors" 列为直接用途；官方提示模型对西方富裕家庭场景有偏置 | 同上 | 强（官方原始文件） |
| V13 | CLIP：400M 图文对预训练；零样本 ImageNet 追平原版 ResNet-50 | [CLIP 论文](https://arxiv.org/abs/2103.00020) | 强（论文摘要） |
| V14 | ESP-WHO 官方仓库支持 ESP32-S3-EYE，提供示例为**人脸检测/人脸识别/行人检测/二维码识别**，无通用物体检测示例 | [esp-who README](https://github.com/espressif/esp-who) | 强（官方仓库原文） |
| V15 | ESP-DL 为 Espressif 端侧深度学习部署框架（用户指南文档版本 v3.3.x） | [ESP-DL User Guide](https://docs.espressif.com/projects/esp-dl/en/latest/) | 强（官方文档，但本次仅取得目录页） |
| V16 | Ultralytics 文档已出现 YOLO26（宣称端到端 NMS-free、面向边缘部署）与 YOLO27 预告 | [YOLO11 文档导航与正文](https://docs.ultralytics.com/models/yolo11/) | 强（官方文档，本轮抓取可见） |

### 5.2 明确属于推断、尚未验证的结论

| # | 推断 | 依据 | 验证方式 |
|---|---|---|---|
| I1 | 端侧 ESP32-S3 无法承载 COCO 80 类通用检测（精度不可用） | V14 的反向论证 + 芯片算力常识 | 若需实证：在 ESP-DL 跑任意开源检测模型测 FPS/mAP |
| I2 | 笔记本 CPU 上 YOLO11n 实际单帧 0.1–0.3 s（而非官方 56 ms） | 官方基准机 CPU 强于消费本 + 前后处理/解码开销 | 阶段 0 冒烟测试计时即可（1 小时） |
| I3 | 开放词表检测器在 CPU 上单帧秒级到十秒级，低频抓拍可接受 | 参数量量级估算 | 阶段 0 计时 |
| I4 | 分辨率（OV2640 + 视距）是精度主要瓶颈，小物品仅 20–40 px | 针孔模型 + 桌面几何粗算 | 阶段 2 的 UXGA vs VGA 对比 |
| I5 | 严格框内裁剪是必需的，否则固定背景主导相似度 | 相似度机理 | 阶段 2 消融（整图 vs 裁剪） |
| I6 | DINOv2 的实例区分力优于 CLIP | 训练目标对齐性（检索 vs 图文对齐） | 阶段 2 双编码器对照 |
| I7 | 固定机位使本场景难度显著低于通用 re-ID | 变化因子减少 | 无法直接验证，只能由绝对精度间接支持 |
| I8 | ByteTrack/BoT-SORT 的运动模型在 10–60 s 抓拍间隔下失效，不能用于跨天关联 | Kalman 假设 | 若要用，需实测；预期不通过 |
| I9 | 同款多件场景纯外观方法上限为 1/k，必须靠注册照/空间先验/问用户 | 信息论必然 | 阶段 2 的 O09–O12 分组结果 |
| I10 | 三态判定 + margin 能有效把同款多件推入 UNCERTAIN | 工程经验 | 阶段 2 阈值扫描的 UR/FAR 曲线 |
| I11 | 用户注册照 + OWLv2 样例提示可显著降低整体难度 | V8 的能力描述 + 产品推理 | 阶段二 A/B（注册 vs 不注册） |
| I12 | Grounding DINO / OWLv2 / DINOv2 的 Apache-2.0 许可 | 业界通识，**本轮 Grounding DINO 与 OWLv2 的 LICENSE 原文未抓取成功** | 下载权重时抓 LICENSE 存档 |

### 5.3 本项目**没有任何**公开证据的空白区

- **无公开的"桌面物品实例级 re-ID"基准**（固定机位 / 单一用户 / 跨天 / 同款多件）→ 无法给出行业公认精度。
- **无"小物品（<50 px）跨天实例关联"的公开评测数字** → I4 只能靠自测。
- **无 OV2640 在桌面记忆场景下的图像质量基准** → JPEG 压缩伪影对 embedding 的影响未知，需自测（可加做 JPEG quality 敏感性小实验）。
- **未取得** YOLO-World 仓库许可证（`main` / `master` 路径均 404）、MediaPipe 模型页（域名抓取失败）、TFLite 检测模型页（同上）→ 相关数字标为"待核"。

---

## 6. 参考文献

### 6.1 检测（Detection）

1. Zhao Y. et al. *DETRs Beat YOLOs on Real-time Object Detection*（RT-DETR）. arXiv:2304.08069. https://arxiv.org/abs/2304.08069 【论文】
2. Carion N. et al. *End-to-End Object Detection with Transformers*（DETR）. arXiv:2005.12872. https://arxiv.org/abs/2005.12872 【论文】（本轮未抓取原文）
3. Cheng T. et al. *YOLO-World: Real-Time Open-Vocabulary Object Detection*. arXiv:2401.17270. https://arxiv.org/abs/2401.17270 【论文】
4. Liu S. et al. *Grounding DINO: Marrying DINO with Grounded Pre-Training for Open-Set Object Detection*. arXiv:2303.05499. https://arxiv.org/abs/2303.05499 【论文】
5. Kaul P., Xie W., Zisserman A. *Multi-Modal Classifiers for Open-Vocabulary Object Detection*（OWLv2）. arXiv:2306.05493. https://arxiv.org/abs/2306.05493 【论文】
6. Huang J. et al. *Speed/accuracy trade-offs for modern convolutional object detectors*（SSD）. arXiv:1611.10012. https://arxiv.org/abs/1611.10012 【论文】（本轮未抓取，作为 SSD 系出处）
7. Howard A. et al. *MobileNets: Efficient Convolutional Neural Networks for Mobile Vision Applications*. arXiv:1704.04861. https://arxiv.org/abs/1704.04861 【论文】（本轮未抓取）

### 6.2 官方文档 / 仓库（本轮抓取原文）

8. Ultralytics. *LICENSE (GNU AGPL-3.0)*. https://raw.githubusercontent.com/ultralytics/ultralytics/main/LICENSE 【官方文档-原始文件】
9. Ultralytics. *YOLO11 Docs*（含 COCO 性能表、许可声明、YOLO26/YOLO27 导航）. https://docs.ultralytics.com/models/yolo11/ 【官方文档】
10. Ultralytics. *YOLOv8 Docs*（含 COCO 性能表）. https://docs.ultralytics.com/models/yolov8/ 【官方文档】
11. Ultralytics. *COCO 数据集（80 类）*. https://docs.ultralytics.com/datasets/detect/coco/ 【官方文档】（用于"COCO 80 类不含钥匙/钱包/眼镜"的类别清单核对）
12. Ultralytics. *RT-DETR Docs*. https://docs.ultralytics.com/models/rtdetr 【官方文档】
13. Ultralytics. *YOLO-World Docs*. https://docs.ultralytics.com/models/yolo-world 【官方文档】
14. Ultralytics. *Licensing（Enterprise）*. https://www.ultralytics.com/license 【厂商】
15. Meta AI. *DINOv2 MODEL_CARD.md*. https://raw.githubusercontent.com/facebookresearch/dinov2/main/MODEL_CARD.md 【官方文档-原始文件】
16. Meta AI. *DINOv2 仓库*. https://github.com/facebookresearch/dinov2 【官方文档】
17. IDEA-Research. *GroundingDINO 仓库*. https://github.com/IDEA-Research/GroundingDINO 【官方文档】
18. Hugging Face. *google/owlv2-base-patch16-ensemble 模型卡*. https://huggingface.co/google/owlv2-base-patch16-ensemble 【官方文档】
19. Espressif. *ESP-WHO README*（ESP32-S3-EYE 支持与示例清单）. https://github.com/espressif/esp-who 【官方文档-原始文件】
20. Espressif. *ESP-DL User Guide*. https://docs.espressif.com/projects/esp-dl/en/latest/ 【官方文档】
21. Espressif. *ESP32-S3-EYE 开发板用户指南*. https://docs.espressif.com/projects/esp-dev-kits/en/latest/esp32s3/esp32-s3-eye/user_guide.html 【官方文档】
22. Google. *MediaPipe Object Detector（EfficientDet-Lite 模型页）*. https://ai.google.dev/edge/mediapipe/solutions/vision/object_detector 【官方文档】（**本轮抓取失败，数据待核**）
23. TensorFlow. *TFLite Model Maker — Object Detection*. https://www.tensorflow.org/lite/models/modify/model_maker/object_detection 【官方文档】（本轮未抓取）
24. OpenCV. *SIFT 特征提取教程*. https://docs.opencv.org/4.x/da/df6/tutorial_py_sift_intro.html 【官方文档】（本轮未抓取）

### 6.3 表征学习 / re-ID / 跟踪

25. Oquab M. et al. *DINOv2: Learning Robust Visual Features without Supervision*. arXiv:2304.07193. https://arxiv.org/abs/2304.07193 【论文】
26. Radford A. et al. *Learning Transferable Visual Models From Natural Language Supervision*（CLIP）. arXiv:2103.00020. https://arxiv.org/abs/2103.00020 【论文】
27. He K. et al. *Deep Residual Learning for Image Recognition*（ResNet）. arXiv:1512.03385. https://arxiv.org/abs/1512.03385 【论文】（本轮未抓取）
28. Lowe D. G. *Distinctive Image Features from Scale-Invariant Keypoints*（SIFT）. IJCV 2004. https://www.cs.ubc.ca/~lowe/papers/ijcv04.pdf 【论文】（本轮未抓取）
29. Rublee E. et al. *ORB: An Efficient Alternative to SIFT or SURF*. ICCV 2011. https://www.cs.ubc.ca/~lowe/papers/rublee11.pdf 【论文】（本轮未抓取）
30. Zhang Y. et al. *ByteTrack: Multi-Object Tracking by Associating Every Detection Box*. arXiv:2110.06864. https://arxiv.org/abs/2110.06864 【论文】
31. Aharon N. et al. *BoT-SORT: Robust Associations Multi-Pedestrian Tracking*. arXiv:2206.14651. https://arxiv.org/abs/2206.14651 【论文】
32. Ye M. et al. *Deep Learning for Person Re-identification: A Survey and Outlook*. arXiv:2001.04193. https://arxiv.org/abs/2001.04193 【论文】（本轮未抓取；用于说明"re-ID 研究主体是行人"）

### 6.4 统计方法

33. *Binomial proportion confidence interval（Wilson score interval）*. https://en.wikipedia.org/wiki/Binomial_proportion_confidence_interval 【博客/百科】
34. *Rule of three (statistics)*. https://en.wikipedia.org/wiki/Rule_of_three_(statistics) 【博客/百科】

---

## 附：给其他成员的三个"请勿引用"提醒

1. **不要引用本文任何"百分比精度"作为 Findy 的能力承诺** —— 3.x 节全部是推断，且明确说明无同构基准。
2. **不要把 ByteTrack/BoT-SORT 的 MOT 数字当作 Findy 的关联精度** —— V9/V10 是视频帧间（33 ms 间隔）行人跟踪指标，与跨天物品关联不同任务。
3. **不要把"YOLO 很流行"当作选型理由** —— V1/V2 已确认 AGPL-3.0 传染性；如果 B/C 两位成员（市场/产品/架构）在对外材料里写了"基于 YOLO"，需要同步许可结论或改为"基于开放词表检测"。