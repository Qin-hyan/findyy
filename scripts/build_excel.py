# -*- coding: utf-8 -*-
"""Build the competitor matrix and evidence ledger XLSX files."""
import os
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from openpyxl.formatting.rule import ColorScaleRule, CellIsRule
from openpyxl.worksheet.datavalidation import DataValidation

OUT_DIR = r"D:\Findyy"
MATRIX = os.path.join(OUT_DIR, "Findyy_竞品对比矩阵_2026-10.xlsx")
EVIDENCE = os.path.join(OUT_DIR, "Findyy_需求证据台账_2026-10.xlsx")

NAVY = "1F3A5F"
TEAL = "2A9D8F"
LIGHT = "F4F7FA"
GRAY = "6B7280"
WHITE = "FFFFFF"

HEADER_FONT = Font(name="微软雅黑", size=9, bold=True, color=WHITE)
BODY_FONT = Font(name="微软雅黑", size=9, color="1F2937")
SMALL_FONT = Font(name="微软雅黑", size=8, color="4B5563")
HEADER_FILL = PatternFill("solid", fgColor=NAVY)
ALT_FILL = PatternFill("solid", fgColor=LIGHT)
THIN = Side(style="thin", color="D9E1EA")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def style_sheet(ws, headers, rows, widths, freeze="B2", url_col=None):
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    ws.row_dimensions[1].height = 32
    for r, row in enumerate(rows, start=2):
        ws.append(row)
        for c in range(1, len(headers) + 1):
            cell = ws.cell(row=r, column=c)
            cell.font = BODY_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
            if r % 2 == 1:
                cell.fill = ALT_FILL
        if url_col:
            cell = ws.cell(row=r, column=url_col)
            url = str(cell.value or "")
            if url.startswith("http"):
                cell.hyperlink = url
                cell.font = Font(name="微软雅黑", size=8, color="1F5FAF", underline="single")
    ws.freeze_panes = freeze
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{len(rows)+1}"
    ws.sheet_view.showGridLines = False


def build_matrix():
    wb = Workbook()
    ws = wb.active
    ws.title = "竞品矩阵"

    headers = [
        "编号", "产品", "公司/国家", "类别", "状态", "价格（原币）", "人民币约值",
        "形态", "摄像头/云台", "物品识别", "长期记忆", "自然语言检索", "时间戳/证据帧",
        "语音", "App", "隐私/本地", "订阅", "成熟度(1-5)", "威胁(H/M/L)",
        "优势", "劣势", "来源 URL", "核实日期",
    ]
    widths = [5, 17, 14, 11, 13, 14, 12, 14, 14, 12, 11, 12, 12, 8, 7, 14, 12, 9, 9, 26, 28, 38, 11]

    rows = [
        [1, "Camtells", "Camtells / 中国香港", "直接同类", "众筹未发货", "客单 HK$4,715", "≈¥4,290",
         "桌面/空间 AI 相机", "360° 全景", "物体库", "部分（事件）", "未证实", "未证实", "有", "有",
         "本地存储/无订阅", "无", 2, "M", "360°、物体库、无订阅", "24 名支持者、未发货、无自然语言证据",
         "https://www.kicktraq.com/projects/948304531/camtells-the-first-ai-camera-that-understands-your-space/", "2026-10-22"],
        [2, "Prompt AI / Seemour", "Prompt AI / 美国", "直接同类", "App 下架/被收编", "未向用户收费", "—",
         "安防摄像头 AI 层", "依赖第三方", "人/宠物/物体", "视频问答", "部分", "未证实", "未证实", "有", "有",
         "云端", "无", 1, "M", "多模态视频理解、真实场景", "无硬件、无商业模式、依赖第三方",
         "https://www.163.com/dy/article/KBJCM4VD0514R9OJ.html", "2026-10-22"],
        [3, "MemPal", "MIT Media Lab / 美国", "研究原型", "研究", "—", "—",
         "可穿戴相机", "可穿戴", "物体", "语音找物", "有（研究）", "有（研究）", "无", "无", "无",
         "研究", "无", 1, "L", "N=15 真实家庭验证", "可穿戴、研究阶段",
         "https://www.media.mit.edu/publications/mempal/", "2026-10-22"],
        [4, "Find My Everything", "独立开发者 / 美国", "App", "在售", "免费", "免费",
         "手机 App", "手机", "YOLO-World", "拍照建档", "有（GPS+时间）", "有", "有（照片）", "无", "有",
         "本地/云", "无", 2, "M", "免费、简单、9 语言", "手动、无连续记录",
         "https://apps.apple.com/cn/app/find-my-everything/id6759879201", "2026-10-22"],
        [5, "OOrion", "OOrion / 法国", "App（无障碍）", "在售", "免费", "免费",
         "手机 App", "手机", "物体/文字", "即时找物", "无（即时）", "有（语音/文字）", "无", "有", "有",
         "本地/云", "无", 3, "L", "无障碍、实时引导", "即时找物，不是记忆",
         "https://www.oorion.fr/en/the-app", "2026-10-22"],
        [6, "Vstarcam CS997A", "威视达康 / 中国", "桌面 AI 相机", "在售", "未核实", "未核实",
         "桌面云台", "355°/90°", "万物识图", "无", "无", "有（AI 对话）", "无", "有", "有",
         "本地/云", "云存储", 4, "M", "形态接近、低成本", "无物品记忆/检索",
         "https://www.vstarcam.cn/wifi-units/56276.html", "2026-10-22"],
        [7, "Violoop", "Violoop / 中国", "桌面 AI 记忆", "众筹/量产", "$399–699", "≈¥2,850–5,000",
         "桌面盒子", "无（读屏幕）", "屏幕内容", "长期记忆", "有（屏幕）", "有（Agent）", "有（屏幕）", "有", "有",
         "本地", "可选", 3, "M", "桌面记忆叙事、$1M/20h", "屏幕非物理物品、价格高",
         "https://m.sohu.com/a/1077272112_122014422/", "2026-10-22"],
        [8, "Apple HomeView", "Apple / 美国", "平台", "2026-12 开售", "未公布", "未公布",
         "家庭摄像头", "2.5K", "人/宠物/车辆/包裹", "视频事件", "有（10 天）", "有（自然语言）", "有（视频）", "有", "有",
         "本地/私有云+E2E", "iCloud+", 4, "H", "生态/隐私/自然语言", "非物品索引、非桌面",
         "https://www.sohu.com/a/1087332571_100106801", "2026-10-22"],
        [9, "Ugreen HomeAgent", "Ugreen / 中国", "本地 AI hub", "预售", "$899–9,999", "≈¥6,400–71,500",
         "家庭 hub", "摄像头存储", "人/车/宠物/包裹", "视频检索", "有", "有（关键词）", "有（视频）", "有", "有",
         "本地", "无", 3, "M", "本地 AI、视频检索", "贵、非桌面、非物品",
         "https://www.macrumors.com/2026/09/04/ugreen-launches-homeagent-hubs-qi2-chargers/", "2026-10-22"],
        [10, "LG Q9", "LG / 韩国", "机器人", "未上市", "未定价", "—",
         "双轮机器人", "有", "视觉识别", "未提", "未提", "有（生成式 AI）", "未提", "有", "有",
         "未公布", "未公布", 3, "L–M", "移动、视觉、语音", "未上市、价格高",
         "https://www.sohu.com/a/832827410_99900743", "2026-10-22"],
        [11, "Samsung Ballie", "Samsung / 韩国", "机器人", "未上市", "未公布", "—",
         "滚动机器人", "4K+2K/LiDAR", "视觉", "未提", "未提", "有", "未提", "有", "有",
         "未公布", "未公布", 2, "L", "投影/移动", "六年未发货",
         "https://www.forbes.com/sites/jonmarkman/2026/03/30/why-samsung-still-hasnt-shipped-ballie-after-six-years/", "2026-10-22"],
        [12, "Ring Always Home Cam", "Ring/Amazon / 美国", "巡逻相机", "未上市", "$249.99", "≈¥1,775",
         "飞行相机", "有", "巡检", "无", "无", "无", "有（巡检）", "有", "有",
         "云", "Ring Protect", 2, "L", "自动巡检", "未上市、非物品记忆",
         "https://tech.yahoo.com/home/articles/ring-always-home-cam-real-171437022.html", "2026-10-22"],
        [13, "Amazon Astro", "Amazon / 美国", "机器人", "停售", "$1,600", "≈¥11,360",
         "轮式机器人", "有", "人脸/巡逻", "无", "无", "有（Alexa）", "无", "有", "有",
         "云", "Ring Protect", 1, "L", "家庭机器人探索", "停售、价格高",
         "https://robotomated.com/explore/consumer/amazon-astro", "2026-10-22"],
        [14, "AirTag 2", "Apple / 美国", "追踪器", "在售", "¥249 / ¥849", "¥249",
         "纽扣 Tag", "无", "无", "无", "无", "无", "无", "有", "有",
         "端侧无历史/E2E", "无", 5, "H", "生态/精确查找", "仅带标签、无画面",
         "https://www.ithome.com/0/916/622.htm", "2026-10-22"],
        [15, "小米 Tag BLE", "小米 / 中国", "追踪器", "在售", "¥69", "¥69",
         "纽扣 Tag", "无", "无", "无", "无", "无", "无", "有", "有",
         "未公布", "无", 5, "H", "价格/双生态", "仅带标签",
         "https://www.ithome.com/0/925/181.htm", "2026-10-22"],
        [16, "小米 Tag UWB", "小米 / 中国", "追踪器", "在售", "¥129", "¥129",
         "纽扣 Tag", "无", "无", "无", "无", "无", "无", "有", "有",
         "未公布", "无", 5, "H", "UWB/双生态", "仅小米 17 系列",
         "https://www.ithome.com/0/925/181.htm", "2026-10-22"],
        [17, "HUAWEI Tag", "华为 / 中国", "追踪器", "在售", "¥99 起", "¥99",
         "卡片 Tag", "无", "无", "无", "无", "无", "无", "有", "有",
         "未公布", "无", 5, "M", "卡片/华为生态", "仅带标签",
         "https://www.smzdm.com/p/183321676/", "2026-10-22"],
        [18, "Samsung SmartTag2", "Samsung / 韩国", "追踪器", "在售", "$29.99", "≈¥213",
         "方形 Tag", "无", "无", "无", "无", "无", "无", "有", "有",
         "未公布", "无", 5, "M", "UWB/AR 指南针", "仅 Galaxy",
         "https://www.samsung.com/us/mobile-accessories/galaxy-smarttag2-black-sku-ei-t5600bbegus/", "2026-10-22"],
        [19, "Tile Mate", "Life360 / 美国", "追踪器", "在售", "未核实", "未核实",
         "方形 Tag", "无", "无", "无", "无", "无", "无", "有", "有",
         "未公布", "Life360 会员", 5, "L", "老牌/众包", "价格未核实",
         "https://www.life360.com/tile-trackers", "2026-10-22"],
        [20, "小米摄像机 3", "小米 / 中国", "安防摄像头", "在售", "¥179", "¥179",
         "室内云台", "3K", "人形/移动", "无", "无", "无", "无", "有", "有",
         "云/卡", "云存储", 5, "M", "便宜/生态", "无物品记忆",
         "https://tech.ifeng.com/c/8x5G22T5IgG", "2026-10-22"],
        [21, "小米摄像机 5 Pro", "小米 / 中国", "安防摄像头", "在售", "¥499 / 439", "¥499",
         "双摄 4K 云台", "4K", "人形/宠物/手势", "无", "无", "无", "无", "有", "有",
         "云/卡", "云存储", 5, "M", "双摄/算力", "无物品记忆",
         "https://m.ithome.com/html/1011605.htm", "2026-10-22"],
        [22, "萤石 C6c 4K", "萤石/海康 / 中国", "安防摄像头", "在售", "¥259 / 200", "¥259",
         "室内云台", "4K", "人形/哭声/异响", "无", "无", "无", "无", "有", "有",
         "云/卡", "云存储", 5, "M", "安防/渠道", "无物品记忆",
         "https://jd.zol.com.cn/1263/12632366.html", "2026-10-22"],
        [23, "小度 X9 Ultra", "百度 / 中国", "智能屏", "在售", "¥839 / 629", "¥839",
         "8 英寸屏+云台", "2MP", "主动看护", "无", "无", "有（语音）", "无", "有", "有",
         "云", "会员", 5, "M", "屏/语音/云台", "无物品记忆",
         "https://digi.ithome.com/archiver/0/999/707.htm", "2026-10-22"],
        [24, "天猫精灵 CC6", "阿里 / 中国", "智能屏", "在售（趋停）", "¥239", "¥239",
         "5.45 英寸屏", "2MP 定焦", "无", "无", "无", "有（语音）", "无", "有", "有",
         "云", "无", 5, "L", "便宜/语音", "老产品/无识别",
         "https://detail.zol.com.cn/1385/1384380/param.shtml", "2026-10-22"],
        [25, "Aqara G3", "Aqara / 中国", "安防摄像头", "在售", "$119.99", "≈¥850",
         "桌面云台", "2K", "人脸/手势/宠物", "无", "无", "无", "无", "有", "有",
         "本地卡", "无强制", 4, "L", "本地 AI/网关", "无物品记忆",
         "https://smarthomecompared.com/cameras/aqara-camera-hub-g3-vs-eufy-indoor-cam-e220", "2026-10-22"],
        [26, "Loona", "KEYi Tech / 中国", "桌面机器人", "在售", "$449", "≈¥3,190",
         "四足桌面", "有", "宠物陪伴", "无", "无", "有（GPT）", "无", "有", "有",
         "云", "未核实", 3, "L", "陪伴/语音", "非记忆",
         "https://whichbot.net/store/companion-robots", "2026-10-22"],
        [27, "Looi", "TangibleFuture / 中国", "桌面机器人", "众筹/量产", "≈₹10,000", "≈¥850",
         "手机底座", "手机", "表情/动作", "无", "无", "有（ChatGPT）", "无", "有", "有",
         "手机/云", "依赖手机", 3, "L", "手机复用/低价", "非记忆",
         "https://indianexpress.com/article/technology/artificial-intelligence/looi-desktop-robot-chatgpt-9240288/", "2026-10-22"],
        [28, "Sortly / Itemtopia / Encircle", "多家 / 美国·加拿大", "库存 App", "在售", "订阅", "订阅",
         "App", "无", "手动", "有（手动）", "无", "无", "有（照片）", "无", "有",
         "云", "订阅", 4, "L", "建档/保险", "手动/静态",
         "https://www.sortly.com/", "2026-10-22"],
    ]

    style_sheet(ws, headers, rows, widths, url_col=22)

    # conditional formatting
    ws.conditional_formatting.add(f"R2:R{len(rows)+1}",
        ColorScaleRule(start_type="num", start_value=1, start_color="F8696B",
                       mid_type="num", mid_value=3, mid_color="FFEB84",
                       end_type="num", end_value=5, end_color="63BE7B"))
    ws.conditional_formatting.add(f"S2:S{len(rows)+1}",
        CellIsRule(operator="equal", formula=['"H"'], fill=PatternFill("solid", fgColor="F4CCCC")))
    ws.conditional_formatting.add(f"S2:S{len(rows)+1}",
        CellIsRule(operator="equal", formula=['"M"'], fill=PatternFill("solid", fgColor="FCE5CD")))
    ws.conditional_formatting.add(f"S2:S{len(rows)+1}",
        CellIsRule(operator="equal", formula=['"L"'], fill=PatternFill("solid", fgColor="D9EAD3")))

    # notes sheet
    ws2 = wb.create_sheet("评分说明")
    notes = [
        ["项目", "说明"],
        ["成熟度（1–5）", "5=量产在售、有规模用户/评价；4=量产在售但小众/新；3=众筹交付/小批量；2=原型/预售未交付；1=概念/停售。"],
        ["威胁度（H/M/L）", "H=同场景+成熟+强渠道；M=邻近+可信；L=远邻/早期。"],
        ["状态", "在售/众筹/未上市/停售；核实日期 2026-10-22。"],
        ["价格", "当地币种原价 + 人民币约值；汇率见报告阅读说明。"],
        ["主竞品池", "只收“已量产在售/可实际购买/有真实用户评价”的产品；众筹未交付、研究原型、停售产品单列。"],
        ["数据缺口", "未从公开网页核实的项写“未核实”，不做估算填充。"],
    ]
    for r, row in enumerate(notes, start=1):
        for c, v in enumerate(row, start=1):
            cell = ws2.cell(row=r, column=c, value=v)
            cell.font = HEADER_FONT if r == 1 else BODY_FONT
            cell.fill = HEADER_FILL if r == 1 else PatternFill("solid", fgColor=WHITE)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
    ws2.column_dimensions["A"].width = 18
    ws2.column_dimensions["B"].width = 110
    ws2.sheet_view.showGridLines = False

    wb.save(MATRIX)
    print("saved", MATRIX)


def build_evidence():
    wb = Workbook()
    ws = wb.active
    ws.title = "证据台账"

    headers = ["编号", "主题", "数据/结论", "数值", "单位", "来源类型", "来源名称", "URL", "发布日期", "采集日期", "可信度", "备注/口径"]
    widths = [7, 14, 42, 12, 10, 12, 26, 42, 11, 11, 7, 34]

    rows = [
        ["E01", "城镇家庭", "城镇家庭户数（推导）", 34860, "万户", "官方公报+推导", "2025 全国 1% 人口抽样调查", "https://stats.tj.gov.cn/sy_51953/jjxx/202606/t20260612_7316947.html", "2026-06-12", "2026-10-22", "A", "51,465 万户 × 67.74%；非官方城镇家庭户数"],
        ["E02", "人口", "全国人口", 140545, "万人", "官方公报", "2025 全国 1% 人口抽样调查", "https://stats.tj.gov.cn/sy_51953/jjxx/202606/t20260612_7316947.html", "2026-06-12", "2026-10-22", "A", "2025-11-01 标准时点"],
        ["E03", "家庭", "全国家庭户", 51465, "万户", "官方公报", "2025 全国 1% 人口抽样调查", "https://stats.tj.gov.cn/sy_51953/jjxx/202606/t20260612_7316947.html", "2026-06-12", "2026-10-22", "A", "户均 2.52 人"],
        ["E04", "老龄化", "60 岁及以上人口", 32122, "万人", "官方公报", "2025 全国 1% 人口抽样调查", "https://stats.tj.gov.cn/sy_51953/jjxx/202606/t20260612_7316947.html", "2026-06-12", "2026-10-22", "A", "占 22.86%"],
        ["E05", "老龄化", "60 岁及以上人口（年末）", 32338, "万人", "官方公报", "2025 年度国家老龄事业发展公报", "https://www.mca.gov.cn/n1288/n1290/n1316/c1662004999980012271/content.html", "2026-08-04", "2026-10-22", "A", "占 23.0%"],
        ["E06", "老龄化", "65 岁及以上人口", 22365, "万人", "官方公报", "2025 年度国家老龄事业发展公报", "https://www.mca.gov.cn/n1288/n1290/n1316/c1662004999980012271/content.html", "2026-08-04", "2026-10-22", "A", "—"],
        ["E07", "痛点频率", "经常忘事", 0.352, "比例", "调查", "中国青年报 2020，N=2002", "https://s.cyol.com/articles/2020-07/30/content_1VnGG0Sl.html", "2020-07-30", "2026-10-22", "A", "自述，非物品丢失专指"],
        ["E08", "痛点频率", "偶尔忘事", 0.605, "比例", "调查", "中国青年报 2020，N=2002", "https://s.cyol.com/articles/2020-07/30/content_1VnGG0Sl.html", "2020-07-30", "2026-10-22", "A", "—"],
        ["E09", "痛点频率", "从不忘事", 0.043, "比例", "调查", "中国青年报 2020，N=2002", "https://s.cyol.com/articles/2020-07/30/content_1VnGG0Sl.html", "2020-07-30", "2026-10-22", "A", "—"],
        ["E10", "痛点归因", "心理压力大", 0.641, "比例", "调查", "中国青年报 2020，N=2002", "https://s.cyol.com/articles/2020-07/30/content_1VnGG0Sl.html", "2020-07-30", "2026-10-22", "A", "—"],
        ["E11", "找东西时间", "中国用户月均找东西", 154, "分钟/月", "品牌调查", "Zippo 2014，经澎湃转述", "https://www.thepaper.cn/newsDetail_forward_1267701", "2014-09-19", "2026-10-22", "B", "品牌委托、年代久，方向性"],
        ["E12", "找东西时间", "日本人一生找东西", 75322, "分钟", "品牌调查", "Zippo 2014，经澎湃转述", "https://www.thepaper.cn/newsDetail_forward_1267701", "2014-09-19", "2026-10-22", "B", "约 52 天"],
        ["E13", "短视频", "抖音 #看我怎么收拾你", 710000000, "次播放", "平台页面", "抖音话题页", "https://www.douyin.com/hashtag/1600535838578695", "—", "2026-10-22", "A", "品牌收纳活动"],
        ["E14", "短视频", "抖音 #超市找东西挑战", 77199000, "次播放", "平台页面", "抖音话题页", "https://www.douyin.com/hashtag/1772906993963016", "—", "2026-10-22", "A", "—"],
        ["E15", "短视频", "抖音 #记录老年痴呆症患者老人的日常生活", 7161000, "次播放", "平台页面", "抖音话题页", "https://www.douyin.com/hashtag/1780696255376384", "—", "2026-10-22", "A", "—"],
        ["E16", "短视频", "抖音 #桌面书本置物架", 851000, "次播放", "平台页面", "抖音话题页", "https://www.douyin.com/hashtag/1772313117267981", "—", "2026-10-22", "A", "—"],
        ["E17", "社群", "豆瓣“我丢的东西都去哪儿了”", 5917, "人", "平台页面", "豆瓣小组", "https://www.douban.com/group/28617/", "—", "2026-10-22", "A", "成员数"],
        ["E18", "社群", "豆瓣“找东西”", 1564, "人", "平台页面", "豆瓣小组", "https://www.douban.com/group/54824/", "—", "2026-10-22", "A", "成员数"],
        ["E19", "社群", "豆瓣“丢三落四”", 927, "人", "平台页面", "豆瓣小组", "https://www.douban.com/group/68736/", "—", "2026-10-22", "A", "成员数"],
        ["E20", "社群", "豆瓣“每天每天都在找东西”", 905, "人", "平台页面", "豆瓣小组", "https://www.douban.com/group/47941/", "—", "2026-10-22", "A", "成员数"],
        ["E21", "内容编码", "40 条样本：纯痛点吐槽", 14, "条", "作者编码", "调研_找不到东西_公开证据采集.md", "D:\\Findyy\\调研_找不到东西_公开证据采集.md", "2026-10-22", "2026-10-22", "C", "作者归类"],
        ["E22", "内容编码", "40 条样本：解决方案/技巧", 11, "条", "作者编码", "调研_找不到东西_公开证据采集.md", "D:\\Findyy\\调研_找不到东西_公开证据采集.md", "2026-10-22", "2026-10-22", "C", "作者归类"],
        ["E23", "内容编码", "40 条样本：产品种草", 6, "条", "作者编码", "调研_找不到东西_公开证据采集.md", "D:\\Findyy\\调研_找不到东西_公开证据采集.md", "2026-10-22", "2026-10-22", "C", "作者归类"],
        ["E24", "内容编码", "40 条样本：娱乐玄学", 4, "条", "作者编码", "调研_找不到东西_公开证据采集.md", "D:\\Findyy\\调研_找不到东西_公开证据采集.md", "2026-10-22", "2026-10-22", "C", "作者归类"],
        ["E25", "创作者", "主播账号累计开通", 211000000, "个", "行业报告", "中国网络表演行业发展报告 2025-2026", "https://www.cflac.org.cn/new_ys/wlwy/dt/202607/t20260706_1367642.html", "2026-07-06", "2026-10-22", "A", "截至 2026-05"],
        ["E26", "创作者", "月活跃开播账号", 37590000, "个", "行业报告", "中国网络表演行业发展报告 2025-2026", "https://www.cflac.org.cn/new_ys/wlwy/dt/202607/t20260706_1367642.html", "2026-07-06", "2026-10-22", "A", "—"],
        ["E27", "创作者", "短视频用户", 1074000000, "人", "行业报告", "中国网络表演行业发展报告 2025-2026", "https://www.cflac.org.cn/new_ys/wlwy/dt/202607/t20260706_1367642.html", "2026-07-06", "2026-10-22", "A", "—"],
        ["E28", "创作者", "短视频创作者账号规模", 1620000000, "个", "行业白皮书", "2025 网络视听内容创作者白皮书", "https://www.ceweekly.cn/area/shanghai/2025/0922/481150.html", "2025-09-22", "2026-10-22", "B", "账号数，非人数"],
        ["E29", "摄像头市场", "2025 中国消费级摄像头销量", 55070000, "台", "行业数据", "洛图科技 RUNTO", "http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html", "2026-01-28", "2026-10-22", "A", "全渠道，+3.0%"],
        ["E30", "摄像头市场", "2026 中国摄像头预测", 54360000, "台", "行业数据", "洛图科技 RUNTO", "http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html", "2026-01-28", "2026-10-22", "A", "−1.3%"],
        ["E31", "摄像头市场", "线上销量占比", 0.636, "比例", "行业数据", "洛图科技 RUNTO", "http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html", "2026-01-28", "2026-10-22", "A", "—"],
        ["E32", "品牌份额", "小米线上销额份额", 0.168, "比例", "行业数据", "洛图科技 RUNTO", "http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html", "2026-01-28", "2026-10-22", "A", "第一"],
        ["E33", "品牌份额", "萤石线上销额份额", 0.112, "比例", "行业数据", "洛图科技 RUNTO", "http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html", "2026-01-28", "2026-10-22", "A", "—"],
        ["E34", "品牌份额", "海康线上销额份额", 0.084, "比例", "行业数据", "洛图科技 RUNTO", "http://runtotech.com/MarketInsights/info_itemid_6255_lcid_12.html", "2026-01-28", "2026-10-22", "A", "—"],
        ["E35", "摄像头市场", "全球消费级摄像头出货", 143000000, "台", "行业数据", "IDC（虎科技转述）", "https://www.hukeji.com/jiadian/202603/117009.html", "2026-03-18", "2026-10-22", "B", "2025，+2.2%"],
        ["E36", "摄像头市场", "中国消费级摄像头出货", 53100000, "台", "行业数据", "IDC（虎科技转述）", "https://www.hukeji.com/jiadian/202603/117009.html", "2026-03-18", "2026-10-22", "B", "2025，+3.3%"],
        ["E37", "追踪器", "AirTag 占智能 Tag 购买者", 0.69, "比例", "行业研究", "Parks Associates", "https://www.parksassociates.com/index.php/blogs/in-the-news/apple-dominates-smart-tag-market-with-airtags", "2025-03-11", "2026-10-22", "A", "2024 年末；2022 年初 45%"],
        ["E38", "追踪器", "美国互联网家庭 Tag 渗透率", 0.12, "比例", "行业研究", "Parks Associates（ISEMag 转述）", "https://www.isemag.com/industry-trends-and-research/reports/news/55273809/smarttag-adoption-climbs-in-us-internet-households", "—", "2026-10-22", "B", "2022Q3 为 7%"],
        ["E39", "追踪器", "AirTag 年出货", 30000000, "台/年", "产业研究", "物联网世界", "https://www.iotworld.com.cn/html/News/202603/949dd7a7e4c69bfc.shtml", "2026-03-20", "2026-10-22", "B", "产业口径，非官方"],
        ["E40", "追踪器", "Samsung Tag 年出货", 20000000, "台/年", "产业研究", "物联网世界", "https://www.iotworld.com.cn/html/News/202603/949dd7a7e4c69bfc.shtml", "2026-03-20", "2026-10-22", "B", "2025 预计"],
        ["E41", "追踪器", "BLE Tag 规模约为 AirTag 倍数", 2, "倍", "产业研究", "物联网世界", "https://www.iotworld.com.cn/html/News/202603/949dd7a7e4c69bfc.shtml", "2026-03-20", "2026-10-22", "B", "平替规模"],
        ["E42", "AirTag 2", "单件价格", 249, "元", "厂商发布", "IT之家", "https://www.ithome.com/0/916/622.htm", "2026-01-26", "2026-10-22", "A", "四件 ¥849"],
        ["E43", "AirTag 2", "查找范围提升", 0.50, "比例", "厂商发布", "IT之家", "https://www.ithome.com/0/916/622.htm", "2026-01-26", "2026-10-22", "A", "最高 +50%"],
        ["E44", "AirTag 2", "精确查找需 iPhone 15+", 15, "代", "厂商/媒体", "MacRumors", "https://www.macrumors.com/2026/01/26/new-airtag-longer-precision-finding/", "2026-01-26", "2026-10-22", "A", "第二代 UWB"],
        ["E45", "小米 Tag", "BLE 版价格", 69, "元", "厂商发布", "IT之家", "https://www.ithome.com/0/925/181.htm", "2026-03-02", "2026-10-22", "A", "—"],
        ["E46", "小米 Tag", "UWB 版价格", 129, "元", "厂商发布", "IT之家", "https://www.ithome.com/0/925/181.htm", "2026-03-02", "2026-10-22", "A", "仅小米 17 系列"],
        ["E47", "HUAWEI Tag", "上市价", 99, "元起", "电商/媒体", "什么值得买/ZOL", "https://www.smzdm.com/p/183321676/", "2026-10-02", "2026-10-22", "B", "活动价 ¥51.99"],
        ["E48", "SmartTag2", "价格", 29.99, "美元", "厂商页面", "Samsung US", "https://www.samsung.com/us/mobile-accessories/galaxy-smarttag2-black-sku-ei-t5600bbegus/", "2026-10-22", "2026-10-22", "A", "≈¥213"],
        ["E49", "SmartTag2", "评分/评论", 4.1, "分/359 条", "厂商页面", "Samsung US", "https://www.samsung.com/us/mobile-accessories/galaxy-smarttag2-black-sku-ei-t5600bbegus/", "2026-10-22", "2026-10-22", "A", "—"],
        ["E50", "Camtells", "众筹支持者", 24, "人", "众筹数据", "Kicktraq", "https://www.kicktraq.com/projects/948304531/camtells-the-first-ai-camera-that-understands-your-space/", "2026-07-18", "2026-10-22", "A", "—"],
        ["E51", "Camtells", "众筹金额", 113167, "港元", "众筹数据", "Kicktraq", "https://www.kicktraq.com/projects/948304531/camtells-the-first-ai-camera-that-understands-your-space/", "2026-07-18", "2026-10-22", "A", "目标 10 万"],
        ["E52", "Camtells", "客单价", 4715, "港元", "众筹数据", "Kicktraq", "https://www.kicktraq.com/projects/948304531/camtells-the-first-ai-camera-that-understands-your-space/", "2026-07-18", "2026-10-22", "A", "≈¥4,290"],
        ["E53", "Prompt AI", "种子轮融资", 5000000, "美元", "媒体", "环球网/网易", "https://www.163.com/dy/article/KBJCM4VD0514R9OJ.html", "2025-10-11", "2026-10-22", "B", "2023 年"],
        ["E54", "Prompt AI", "团队规模", 11, "人", "媒体", "环球网/网易", "https://www.163.com/dy/article/KBJCM4VD0514R9OJ.html", "2025-10-11", "2026-10-22", "B", "—"],
        ["E55", "Prompt AI", "Seemour App 下架", 1, "是", "媒体", "环球网/网易", "https://www.163.com/dy/article/KBJCM4VD0514R9OJ.html", "2025-10-11", "2026-10-22", "B", "数据删除"],
        ["E56", "MemPal", "研究样本", 15, "人", "论文", "MIT Media Lab / IUI 2025", "https://www.media.mit.edu/publications/mempal/", "2025-02-05", "2026-10-22", "A", "老人，真实家庭"],
        ["E57", "MemPal", "任务负荷显著差异", 0.031, "p 值", "论文", "MIT Media Lab / IUI 2025", "https://www.media.mit.edu/publications/mempal/", "2025-02-05", "2026-10-22", "A", "RTLX"],
        ["E58", "Find My Everything", "价格", 0, "元", "App Store", "App Store", "https://apps.apple.com/cn/app/find-my-everything/id6759879201", "2026-10-22", "2026-10-22", "A", "免费"],
        ["E59", "Vstarcam CS997A", "云台角度", 355, "度", "厂商页面", "威视达康", "https://www.vstarcam.cn/wifi-units/56276.html", "2026-10-22", "2026-10-22", "A", "水平 355°/垂直 90°"],
        ["E60", "Apple HomeView", "摄像头分辨率", 2.5, "K", "厂商/媒体", "搜狐/DoNews", "https://www.sohu.com/a/1087332571_100106801", "2026-10-13", "2026-10-22", "A", "—"],
        ["E61", "Apple HomeView", "自然语言视频搜索", 1, "是", "厂商/媒体", "搜狐/DoNews", "https://www.sohu.com/a/1087332571_100106801", "2026-10-13", "2026-10-22", "A", "Apple Intelligence"],
        ["E62", "Apple HomeView", "开售时间", 2026.12, "年月", "厂商/媒体", "搜狐/DoNews", "https://www.sohu.com/a/1087332571_100106801", "2026-10-13", "2026-10-22", "A", "部分 2027 初"],
        ["E63", "Ugreen HomeAgent", "价格", 899, "美元起", "媒体", "MacRumors", "https://www.macrumors.com/2026/09/04/ugreen-launches-homeagent-hubs-qi2-chargers/", "2026-09-04", "2026-10-22", "A", "最高 $9,999"],
        ["E64", "Violoop", "首发价", 399, "美元", "媒体", "搜狐/明亮公司", "https://m.sohu.com/a/1077272112_122014422/", "2026-09-17", "2026-10-22", "B", "建议零售 $699"],
        ["E65", "Violoop", "众筹 20 小时金额", 1000000, "美元", "媒体", "搜狐/明亮公司", "https://m.sohu.com/a/1077272112_122014422/", "2026-09-17", "2026-10-22", "B", "—"],
        ["E66", "Violoop", "支持者", 1971, "人", "媒体", "搜狐/明亮公司", "https://m.sohu.com/a/1077272112_122014422/", "2026-09-17", "2026-10-22", "B", "截至 9/17"],
        ["E67", "Memories.ai", "种子轮累计", 16000000, "美元", "媒体", "Dealroom", "https://dealroom.co/news/135651-memories-ai-raises-8m-seed-extension-for-visual-memory-ai/", "2026-06-23", "2026-10-22", "A", "LVMM"],
        ["E68", "LG Q9", "状态", 0, "未上市", "媒体", "搜狐/环球网", "https://www.sohu.com/a/832827410_99900743", "2024-12-03", "2026-10-22", "B", "未定价"],
        ["E69", "Samsung Ballie", "六年未发货", 6, "年", "媒体", "Forbes", "https://www.forbes.com/sites/jonmarkman/2026/03/30/why-samsung-still-hasnt-shipped-ballie-after-six-years/", "2026-03-30", "2026-10-22", "B", "—"],
        ["E70", "Ring", "价格", 249.99, "美元", "媒体", "Yahoo Tech", "https://tech.yahoo.com/home/articles/ring-always-home-cam-real-171437022.html", "2025-09", "2026-10-22", "B", "未上市"],
        ["E71", "Astro", "原价", 1600, "美元", "媒体", "Robotomated", "https://robotomated.com/explore/consumer/amazon-astro", "2026-08", "2026-10-22", "B", "停售"],
        ["E72", "小度 X9 Ultra", "上市价", 839, "元", "厂商发布", "IT之家", "https://digi.ithome.com/archiver/0/999/707.htm", "2026-09-08", "2026-10-22", "A", "首销 629"],
        ["E73", "小米摄像机 3", "首销价", 179, "元", "媒体", "凤凰网科技", "https://tech.ifeng.com/c/8x5G22T5IgG", "—", "2026-10-22", "B", "首发 169"],
        ["E74", "小米摄像机 5 Pro", "定价", 499, "元", "厂商发布", "IT之家", "https://m.ithome.com/html/1011605.htm", "2026-10-11", "2026-10-22", "A", "首发 439"],
        ["E75", "萤石 C6c 4K", "挂牌价", 259, "元", "电商", "ZOL", "https://jd.zol.com.cn/1263/12632366.html", "2026-10-21", "2026-10-22", "B", "到手 200.07"],
        ["E76", "Aqara G3", "标价", 119.99, "美元", "电商/媒体", "SmartHomeCompared", "https://smarthomecompared.com/cameras/aqara-camera-hub-g3-vs-eufy-indoor-cam-e220", "2026-10", "2026-10-22", "B", "Prime $98.99"],
        ["E77", "MCI", "中国 60+ MCI 患病率", 0.1454, "比例", "论文", "CHARLS 2018 / PMC13574534", "https://europepmc.org/articles/PMC13574534", "2026-08", "2026-10-22", "A", "单研究"],
        ["E78", "MCI", "专家共识口径", 0.155, "比例", "媒体/共识", "人民日报健康客户端", "https://k.sina.cn/article_1411163204_541ca44402001kolg.html", "2025-09-21", "2026-10-22", "B", "2023 专家共识"],
        ["E79", "ADHD", "全球成人平均患病率", 0.028, "比例", "研究/媒体", "WHO（人民日报转述）", "https://www.srrsh.com/articleInfo/5339", "2023-07-31", "2026-10-22", "B", "—"],
        ["E80", "ADHD", "中国成人患病率口径", 0.034, "比例", "媒体", "中国网·心理中国", "http://psy.china.com.cn/2026-01/13/content_43333609.htm", "2026-01-13", "2026-10-22", "B", "—"],
        ["E81", "ADHD", "中国成人患者规模", 24000000, "人以上", "作者推算", "16–59 岁人口 × 2.8–3.4%", "—", "—", "2026-10-22", "C", "约 2,400–2,900 万"],
        ["E82", "专利", "海康 CN109993045A", 1, "件", "专利", "Google Patents", "https://patents.google.com/patent/CN109993045A/zh", "2019-07-09", "2026-10-22", "A", "申请 2018-04-26"],
        ["E83", "专利", "深圳九洲 WO2020057348A1", 1, "件", "专利", "Google Patents", "https://patents.google.com/patent/WO2020057348A1/en", "—", "2026-10-22", "A", "记忆寻物"],
        ["E84", "专利", "US10298825B2 可穿戴找物", 1, "件", "专利", "Google Patents", "https://patents.google.com/patent/US10298825B2/en", "—", "2026-10-22", "A", "可穿戴"],
        ["E85", "低端 tracker", "摩米士防丢器价格", 42, "元", "媒体", "信网", "http://www.qdxin.com.cn/xin/2026/390771.html", "2026-08-14", "2026-10-22", "B", "依赖苹果设备"],
        ["E86", "AI 硬件失败", "Rabbit R1 4 天销量", 100000, "台", "媒体", "36Kr", "https://eu.36kr.com/en/p/3672645585138436", "2026-02-09", "2026-10-22", "B", "退货率高/资金链断裂"],
        ["E87", "AI 硬件失败", "Humane AI Pin 停售", 1, "是", "媒体", "NYT", "https://www.nytimes.com/2025/02/18/technology/hp-humane-ai-pin.html", "2025-02-18", "2026-10-22", "B", "HP $116M 收购部分资产"],
        ["E88", "AI 硬件失败", "Google Glass 停售", 1, "是", "媒体", "中国新闻网", "https://www.chinanews.com.cn/cj/2023/03-17/9973388.shtml", "2023-03-17", "2026-10-22", "B", "企业版停止销售"],
    ]

    style_sheet(ws, headers, rows, widths, url_col=8)

    # confidence color
    ws.conditional_formatting.add(f"K2:K{len(rows)+1}",
        CellIsRule(operator="equal", formula=['"A"'], fill=PatternFill("solid", fgColor="D9EAD3")))
    ws.conditional_formatting.add(f"K2:K{len(rows)+1}",
        CellIsRule(operator="equal", formula=['"B"'], fill=PatternFill("solid", fgColor="FFF2CC")))
    ws.conditional_formatting.add(f"K2:K{len(rows)+1}",
        CellIsRule(operator="equal", formula=['"C"'], fill=PatternFill("solid", fgColor="FCE5CD")))

    ws2 = wb.create_sheet("说明")
    notes = [
        ["项目", "说明"],
        ["A 级", "页面直接渲染或官方公报（抖音话题播放量、豆瓣成员数、国家统计局、Apple 新闻稿等）。"],
        ["B 级", "搜索摘要/媒体转述（抖音点赞徽标、部分竞品价格、Forbes/NYT 转载等）。"],
        ["C 级", "作者基于 A/B 级材料的归类、评分与推算（内容类型占比、TAM/SAM/SOM 假设、ADHD 患者规模等）。"],
        ["用途", "支撑报告中的关键数字与判断；每条含 URL、发布日期、采集日期与口径。"],
        ["缺口", "未找到可靠公开数据的项标注“未核实/未找到”，不做估算填充。"],
    ]
    for r, row in enumerate(notes, start=1):
        for c, v in enumerate(row, start=1):
            cell = ws2.cell(row=r, column=c, value=v)
            cell.font = HEADER_FONT if r == 1 else BODY_FONT
            cell.fill = HEADER_FILL if r == 1 else PatternFill("solid", fgColor=WHITE)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 110
    ws2.sheet_view.showGridLines = False

    wb.save(EVIDENCE)
    print("saved", EVIDENCE)


if __name__ == "__main__":
    build_matrix()
    build_evidence()
