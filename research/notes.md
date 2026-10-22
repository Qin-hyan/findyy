# Findyy 市场调研原始笔记（采集日期 2026-10-22）

## A. 直接同类 / 邻近产品

### A1. Camtells（香港，Kickstarter）
- 定位：The First AI Camera That Understands Your Space；AI Event Search、Auto Camera Director、360° Panoramic Coverage、Local Storage、No Subscription、Smart Object Library。
- 众筹：2026-06-02 至 2026-07-17，46 天；24 名支持者；认筹 HK$113,167 / 目标 HK$100,000（113%）；客单价均值 HK$4,715。
- 来源：https://www.kicktraq.com/projects/948304531/camtells-the-first-ai-camera-that-understands-your-space/
- 判断：概念最接近，但 24 个支持者说明“空间理解相机”在众筹层面拉力很弱；需核实是否已交付、真实评价。

### A2. Prompt AI / Seemour（美国，2023）
- 定位：Ambient AI / 家庭空间理解；连接 Ring 等安防摄像头，识别人、宠物、物体，生成文字提醒，支持对摄像头画面提问。
- 融资：2023 年 500 万美元种子轮（AIX、Abstract Ventures 领投）；11 名员工。
- 结局：不向用户收授权费，商业模式难成立；Seemour App 已从 App Store 下架，用户数据将删除；2025-10 苹果进入收购后期谈判（acqui-hire），技术/团队并入 HomeKit/智能家居。
- 来源：https://www.163.com/dy/article/KBJCM4VD0514R9OJ.html ；https://www.c114.net.cn/industry/27670.html
- 判断：技术可行、需求存在，但“给摄像头加 AI”本身难收费；苹果收购说明大厂认可能力，也说明独立产品难活。

### A3. MemPal（MIT Media Lab，研究原型）
- 定位：可穿戴相机 + 多模态 LLM + 语音问答，为老人提供物品查找与记忆支持；自动生成活动文字日记。
- 研究：N=15 老人，在自己家中测试；有音频辅助时找物表现优于无辅助；任务负荷 RTLX 有显著差异（p=.031）；整体用户感知积极。
- 来源：https://www.media.mit.edu/publications/mempal/ ；https://dl.acm.org/doi/full/10.1145/3708359.3712151（摘要页 403，MIT 页可读）
- 判断：交互范式被学术验证；但可穿戴、研究阶段，不是桌面商品。

### A4. Find My Everything（iOS App，2026）
- 定位：AI Camera Finds Everything；实时 YOLO-World 识别，拍照后用 Gemini 2.5 Flash 分析，保存物体 + GPS + 时间戳，按物体名搜索“何时何地最后看到”；点物品可在原照片高亮。
- 价格：免费；v1.0.1（2026-03-11）；9 种语言；无评分/评论（截至采集）。
- 来源：https://apps.apple.com/cn/app/find-my-everything/id6759879201
- 判断：App 端“拍照建档 + 时间/地点 + 搜索”已经被免费实现，说明纯 App 方案壁垒低；持续自动记录才是硬件差异点。

### A5. OOrion（法国，iOS）
- 定位：面向盲人/低视力用户的物体与文字识别、实时引导；支持个人物品注册、语音/文字搜索、AI 助手。
- 价格：免费；App Store 可下载。
- 来源：https://www.oorion.fr/en/the-app
- 判断：无障碍场景的“即时找物”已有成熟免费方案；与 Findyy 的“历史记忆”不同，但会分流老人/视障人群。

### A6. 海康威视专利 CN109993045A（重点 IP 风险）
- 名称：物品查找方法及查找装置、查找系统和机器可读存储介质。
- 申请人：杭州海康威视系统技术有限公司；申请日 2018-04-26；优先权 2017-12-29；公开日 2019-07-09。
- 内容（从 PDF 权利要求/摘要提取）：摄像设备采集视频并识别物品，保存物品信息；接收客户端对目标物品的查找指令，匹配物品信息；判断物品位置是否变化并更新；向客户端发送目标物品位置信息和目标图片（目标图片为包含目标物品所在位置的图片，可从视频帧/图片库获取），可带时间信息；支持多摄像设备、地图分布展示。
- 来源：https://patents.google.com/patent/CN109993045A/zh ；PDF 已下载 research/raw/CN109993045A.pdf
- 判断：与“摄像头识别物品 + 保存帧 + 按查询返回位置/图片/时间”的核心流程高度重叠；需查同族/授权状态并做 FTO，不能据此直接判断侵权。

## B. 替代方案

### B1. Apple AirTag 2（2026-01-26 发布）
- 价格：¥249 单件，¥849 四件；国补后曾见 ¥198。
- 升级：第二代 UWB 芯片，查找范围最高 +50%；扬声器音量 +50%，可听距离最远翻倍；支持 Apple Watch 精确查找；共享物品位置（航司等 50+ 家）。
- 隐私：设备端不存储位置数据或历史；查找网络端到端加密。
- 来源：https://www.ithome.com/0/916/622.htm
- 判断：成熟、便宜、生态强；Findyy 必须回答“没有标签的物品”与“最后出现画面”这两个差异点。

### B2. Samsung Ballie（家庭机器人）
- 2025-07-02 报道：上市从 2025 夏季推迟；4K 前摄 + 2K 后摄、LiDAR、投影、Gemini + 三星自研 LLM；强光下投影响应延迟率 17%，嘈杂环境语音识别 82%，未达内部 95% 阈值；供应链消息称定价或超 2,000 美元。
- 来源：https://m.163.com/dy/article/K3F6E3NB0514R9OJ.html
- 判断：大厂做“空间智能”也会被成本/可靠性/定价拖住；高价机器人不是 Findyy 的直接价格带。

### B3. Ring Always Home Cam
- 公开报道：$249.99 室内飞行相机，截至 2025-09 仍未向公众发售（来自搜索摘要，待更可靠来源）。
- 判断：巡逻相机是邻近形态，但不做物品级记忆与自然语言检索。

## C. 需求侧

### C1. Zippo 2014 全球调查（品牌委托，方向性）
- 10 个国家/地区；中国用户平均每月 154 分钟找东西，10 国最高；香港 129 分钟；印度 118 分钟；日本 76 分钟/月，一生约 75,322 分钟（约 52 天）。
- 来源：https://www.thepaper.cn/newsDetail_forward_1267701
- 注意：2014 年、打火机品牌委托、样本口径未披露；只能作方向性参考。

### C2. 抖音样本（2026-10-22 采集）
- 视频：https://www.douyin.com/shipin/7264040483012298815
- 标题：钥匙丢了怎么找最快；发布 2026-10-19；页面公开数据 1.7 万赞、1321 评论、2612 转发、1113 收藏（字段顺序待复核）。
- 内容：找东西“玄学”（剪刀挂门、喊洋葱等），高互动；相关推荐出现“钥匙找不到？有 airtag 就行啦！”（195 赞）。
- 判断：痛点内容有强传播力，但大量是娱乐/玄学/技巧，不是购买意图；AirTag 已被当作默认答案。

## B4. 国产/其他追踪器

### Xiaomi Tag（2026-03 国行上架）
- BLE 版 ¥69；UWB 版 ¥129；四件组合装；10g、7.2mm、IP67、CR2032、续航 1 年。
- 兼容安卓 Find Hub 与苹果 Find My 双生态；UWB 功能仅支持小米 17 Pro/Pro Max/Ultra，分米级。
- 来源：https://www.chongdiantou.com/archives/1772503084341.html
- 判断：价格锚点极低；“跨生态”是卖点，进一步压缩专用硬件的定价空间。

### 全球 UWB-Tag 出货（产业研究口径）
- AirTag 约 3,000 万 PCS/年；Samsung SmartTag 约 2,000 万/年（2025 预计）；两者合计约 5,000 万。
- BLE Tag 平替规模约为 AirTag 的 2 倍。
- MOTO Tag 2025 约 100 万；小米 UWB-Tag 2026 预计“大几百万”，生态潜力千万级。
- 来源：https://www.iotworld.com.cn/html/News/202603/949dd7a7e4c69bfc.shtml
- 判断：找东西是成熟大市场，但主流支付意愿在 ¥69–249；专用相机必须证明“无标签物品 + 视觉证据”的增量价值。

### AirTag 2 局限
- 精确查找依赖 iPhone 15 及以上（第二代 UWB）；旧机型只能使用旧距离；iPhone 16e 不支持第二代 UWB。
- 精确查找距离约 30 米/100 英尺；定位依赖 Find My 网络，不是持续实时定位；对移动物体/被遮挡物品不可靠。
- 来源：https://www.macrumors.com/2026/01/26/new-airtag-longer-precision-finding/ ；https://www.bgr.com/2069071/are-apple-airtags-reliable-according-users/
- 判断：AirTag 解决“带标签物品的最后已知位置”，不解决“没标签、被盖住、需要看见画面”的场景。

### 低端防丢器风险案例
- 摩米士防丢器 ¥42/¥39.9，宣传“GPS 定位神器/宠物防走丢”，实际依赖 10 米内苹果设备蓝牙刷新；宠物狗走失后中暑死亡；商家删去 GPS/宠物关键词。
- 来源：http://www.qdxin.com.cn/xin/2026/390771.html
- 判断：低端市场存在虚假宣传与信任危机；Findyy 若定位“可靠记忆”，准确率与宣传合规是生命线。

## B5. 智能摄像头 / 智能屏价格锚点

- 2025 年中国消费级监控摄像头全渠道销量 5,507 万台，同比 +3.0%；线上占 63.6%；抖音/拼多多/快手等新兴电商销量同比 +90%，份额 16.2%；线上在售品牌 >1,000 家，年内 500+ 新入局、260+ 白牌退出；TOP4 销额份额 43.7%。
- 品牌：小米销额 16.8%（第一）、萤石 11.2%、海康 8.4%、乔安 7.3%。
- 趋势：800 万像素单目占传统电商 19.5%；AI 大模型深度融合，萤石/360/小度/乔安/海雀等已支持自然语言查询与交互；2026 年预计 5,436 万台（-1.3%）。
- 来源：http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html
- 价格：小米智能摄像机 3 ¥179（500 万像素/3K）；小米智能摄像机 5 Pro ¥499（双摄 4K）；萤石 C6c 4K 约 ¥200；小度智能屏 X9 Ultra 上市 ¥839、首销 ¥629–699（8 英寸屏、2MP 云台、AI 主动看护）；天猫精灵 CC6 预售 ¥294。
- 判断：带云台+语音+AI 的摄像头/智能屏已在 ¥179–699 区间高度竞争；“桌面物品记忆”不能只卖硬件参数。

## B6. Apple HomeView / Home Collection（2026-10-13）
- Apple 联合 LG、施耐德电气推出 Home Collection：室内外摄像头、恒温器、温湿度传感器、视频门铃、智能锁；2026-12 起发售，部分 2027 初。
- 摄像头 2.5K；识别人、熟悉面孔、宠物、车辆、包裹；视频历史存 iCloud+（10 天）；Apple Intelligence 自动生成视频描述，支持自然语言/描述性语言搜索视频；家庭中枢本地处理或私有云计算；端到端加密。
- 来源：https://www.sohu.com/a/1087332571_100106801 ；https://www.apple.com/au/newsroom/2026/10/introducing-apple-home-collection-a-new-lineup-of-smart-home-accessories/
- 判断：这是最大平台威胁——Apple 把“家庭摄像头 + 物体识别 + 自然语言视频搜索 + 隐私”打包进 HomeKit，且 2026-12 上市；Findyy 的“物品记忆”必须比 Apple 更聚焦、更便宜或更专业。

## B7. 视觉记忆/桌面 AI 硬件新玩家

### Violoop（深圳，2025-12 成立）
- 桌面 AI 硬件盒子，HDMI/Type-C 读取电脑屏幕，本地长期记忆 + Agent 操作电脑；26 TOPS；海外建议零售价 $699，Kickstarter/国内首发 $399。
- 2026-09 Kickstarter 上线 20 小时破 $100 万；截至 9/17 13:00 总额 $1,143,837、1,971 名支持者；全球约 1.2 万人付订金。
- 来源：https://m.sohu.com/a/1077272112_122014422/
- 判断：证明“桌面 + AI 看见/记住 + 本地隐私”的付费意愿可以很高（$399–699），但它是屏幕记忆，不是物理物品记忆；是定价与叙事的重要对标。

### Ugreen HomeAgent（2026-09）
- 本地 AI 家庭 hub：存储摄像头素材、端侧 AI 识别人/车/宠物/包裹、事件摘要、按关键词搜索录像、语音助手 Uliya；Matter 控制器；三档 $899/$2,999/$9,999；Kickstarter 2026-10-27。
- 来源：https://www.macrumors.com/2026/09/04/ugreen-launches-homeagent-hubs-qi2-chargers/
- 判断：本地 AI + 视频检索正在成为高端 hub 的标配；价格带远高于 Findyy，但会教育市场。

### Memories.ai（旧金山，2026-06）
- Large Visual Memory Model（LVMM），让 AI 长期记住并检索数百万小时视频；2025-07 索引 100 万小时，两个月后 1,000 万+；客户为安防/营销；种子轮累计 $1,600 万，Samsung Next 参投。
- 来源：https://dealroom.co/news/135651-memories-ai-raises-8m-seed-extension-for-visual-memory-ai/
- 判断：“视觉记忆”正成为基础设施层；Findyy 若只做应用层，可能被平台/基础设施商品化。

### 威视达康 CS997A（AI 桌面监控机器人）
- 355° 水平 / 90° 垂直云台；200 万像素；电池；双向语音；AI 对话（豆包/通义千问/Gemini）；唤醒词“你好，小鹰”；万物识图；人形检测/区域检测；TF 卡 256GB。
- 来源：https://www.vstarcam.cn/wifi-units/56276.html
- 判断：桌面云台+语音+AI 识图的硬件形态已被深圳厂商做到低成本的“监控机器人”；缺的是“物品级记忆 + 时间戳检索”。这是 Findyy 最接近的形态竞品，也说明硬件本身不是壁垒。

## B8. 机器人/巡逻相机
- LG Q9：CES 2025 移动式 AI 家居 hub，双轮、视觉识别、自主移动、生成式 AI 对话、情感支持、家电语音控制；2025-02/03 面向研究者首發，2025 年底正式销售；价格未公布。来源：https://www.fnnews.com/news/202501100556558933
- Samsung Ballie：2025-07 报道上市从夏季推迟；4K 前摄 + 2K 后摄、LiDAR、投影、Gemini；强光投影响应延迟 17%、嘈杂语音识别 82%，未达 95% 内部阈值；定价或超 $2,000。来源：https://m.163.com/dy/article/K3F6E3NB0514R9OJ.html
- Ring Always Home Cam：$249.99 室内飞行相机，公开报道截至 2025-09 仍未向公众发售（待更可靠来源）。
- Amazon Astro：Astro for Business 上市约 7 个月即停产；消费版未成为大众产品。来源：https://www.163.com/dy/article/J67GASH205198CJN.html
- 判断：机器人形态解决“移动覆盖”，但成本/可靠性/价格是硬约束；Findyy 的固定桌面形态更便宜、更聚焦，但也受覆盖范围限制。

## C3. 中国青年报 2020 调查（需求强度）
- 样本 2,002 人；35.2% 经常忘事，60.5% 偶尔，仅 4.3% 从不忘事；82.0% 觉得身边年轻人容易忘事（13.8% 非常多）；64.1% 归因心理压力，63.7% 工作压力，61.5% 作息不规律，55.2% 熬夜，48.1% 电子产品干扰。
- 来源：https://s.cyol.com/articles/2020-07/30/content_1VnGG0Sl.html
- 判断：年轻人“健忘/丢三落四”是普遍自述痛点；但“忘事”不等于“找不到物品”，需在报告中区分。

## C4. 人口与人群基数
- 2025-11-01 全国人口 140,545 万；家庭户 51,465 万户，户均 2.52 人；60+ 32,122 万（22.86%），65+ 22,309 万（15.87%）；城镇人口 95,208 万（67.74%）。
- 来源：https://stats.tj.gov.cn/sy_51953/jjxx/202606/t20260612_7316947.html（国家统计局公报）
- 2025 年末 60+ 32,338 万（23.0%），人均预期寿命 79.25 岁。来源：https://www.mca.gov.cn/n1288/n1290/n1316/c1662004999980012271/content.html
- 中国 MCI meta：393,525 名成人；需补具体患病率（PubMed 38870921 页面被拦，待查摘要）。
- 成人 ADHD：媒体口径“两千万成年人”；全球成人患病率约 2.5%–5%，中国诊断/治疗率低；需在报告中用区间并标注口径。来源：https://www.zhihu.com/question/1996005855066338526/answer/2017595354955147132（仅作线索）
- 城镇家庭户数推导：51,465 万户 × 67.74% ≈ 34,860 万户（粗略，未按城乡户规模差异校正）。

## C5. 需求侧其他信号
- AirTag 2 发布价 ¥249（单件）/¥849（四件），美国 $29/$99；AirTag 2 仍不支持 Android；精确查找依赖新 iPhone。来源：https://www.ithome.com/0/916/622.htm ；https://www.macrumors.com/2026/01/26/new-airtag-longer-precision-finding/
- 小红书“找不到常用物品？回溯法”等笔记；抖音“钥匙丢了怎么找最快”1.7 万赞；相关推荐 AirTag 视频。说明“找东西技巧”是稳定内容品类。
- 判断：内容热度集中在“技巧/玄学/收纳”，不是“购买设备”；需要把“内容共鸣”与“付费意图”分开。

## C6. 竞品失败/退场案例（用于风险章）
- Rabbit R1：4 天卖出 10 万台，但退货率极高、口碑崩塌，2025-11 资金链断裂、欠薪，团队 26 人。来源：https://eu.36kr.com/en/p/3672645585138436
- Humane AI Pin：手势误触、学习成本高、语音延迟 5–10 秒，停止销售；HP 以 1.16 亿美元收购部分资产。来源：https://www.nytimes.com/2025/02/18/technology/hp-humane-ai-pin.html
- Google Glass Enterprise：2023 停止销售/支持。来源：https://www.chinanews.com.cn/cj/2023/03-17/9973388.shtml
- Narrative Clip：2016 关闭。来源：https://www.bbc.com/news/technology-37497900
- 判断：AI 硬件“演示惊艳、日常吃灰”是常态；Findyy 必须用“每天都会发生的找东西”而不是“炫技”来定义产品。

## D. 待补
- AirTag/SmartTag/Tile/国产防丢器价格、销量/评论、差评主题。
- 智能安防摄像头（小米/萤石/Tapo/Aqara/Eufy）AI 能力与价格。
- 智能屏/语音助手（Echo Show、Nest Hub、小度、天猫精灵）。
- 家庭库存 App（Sortly、Itemtopia、Encircle）价格与用户。
- 机器人（LG AI Home Hub、Astro、Enabot、Looi、Loona）。
- 失败案例（Humane AI Pin、Rabbit R1、Google Glass、Narrative Clip、Pixie）。
- 市场规模（智能标签、安防摄像头、智能家居、中国城镇家庭/老龄化/ADHD/MCI）。
- 小红书/B站/快手/知乎/微博样本。
- 电商评论与价格带。
