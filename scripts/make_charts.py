# -*- coding: utf-8 -*-
"""Generate all charts for the Findyy market research report."""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from matplotlib.patches import Rectangle, Polygon
from matplotlib.lines import Line2D
import numpy as np

OUT = r"D:\Findyy\assets\charts"
os.makedirs(OUT, exist_ok=True)

NAVY = "#1F3A5F"
TEAL = "#2A9D8F"
ORANGE = "#E76F51"
GOLD = "#E9C46A"
GRAY = "#8D99AE"
RED = "#D62828"
BLUE = "#5B7DB1"
PURPLE = "#7B5EA7"
GRID = "#D9E1EA"

plt.rcParams.update({
    "font.sans-serif": ["Microsoft YaHei"],
    "axes.unicode_minus": False,
    "font.size": 10,
    "axes.edgecolor": "#B0B7C3",
    "axes.labelcolor": "#1F2937",
    "text.color": "#1F2937",
    "xtick.color": "#4B5563",
    "ytick.color": "#4B5563",
    "figure.facecolor": "white",
    "axes.facecolor": "white",
    "savefig.facecolor": "white",
})


def save(fig, name):
    path = os.path.join(OUT, name)
    fig.savefig(path, dpi=220, bbox_inches="tight", pad_inches=0.15)
    plt.close(fig)
    print("saved", path)


# ---------------------------------------------------------------- 01 positioning
def chart_positioning():
    products = [
        ("AirTag 2", 4.00, 2.55, 5, "tracker"),
        ("小米 Tag", 3.86, 2.42, 5, "tracker"),
        ("Samsung SmartTag2", 3.72, 2.68, 5, "tracker"),
        ("Tile", 3.58, 2.30, 5, "tracker"),
        ("安防摄像头", 3.00, 1.95, 5, "camera"),
        ("小度智能屏 X9", 2.18, 2.18, 5, "camera"),
        ("Vstarcam CS997A", 1.00, 2.18, 4, "camera"),
        ("Camtells", 2.00, 3.18, 2, "memory"),
        ("MemPal", 3.30, 3.42, 1, "memory"),
        ("Find My Everything", 3.72, 2.95, 2, "memory"),
        ("Prompt AI / Seemour", 2.62, 3.18, 1, "memory"),
        ("Apple HomeView", 3.00, 3.62, 4, "memory"),
        ("Ugreen HomeAgent", 2.72, 3.38, 3, "memory"),
        ("Violoop", 1.00, 3.08, 3, "memory"),
        ("LG Q9", 2.55, 3.45, 3, "robot"),
        ("Samsung Ballie", 2.35, 3.30, 2, "robot"),
        ("Ring Always Home Cam", 3.20, 2.40, 2, "robot"),
        ("Findyy 目标", 1.00, 3.92, 1, "findyy"),
    ]
    palette = {"tracker": GRAY, "camera": BLUE, "memory": ORANGE, "robot": PURPLE, "findyy": TEAL}

    fig, ax = plt.subplots(figsize=(8.8, 6.2))
    ax.set_xlim(0.55, 4.45)
    ax.set_ylim(1.55, 4.25)
    ax.set_xticks([1, 2, 3, 4])
    ax.set_xticklabels(["桌面", "房间", "全屋", "随身/任意"], fontsize=9.5)
    ax.set_yticks([1, 2, 3, 4])
    ax.set_yticklabels(["监控", "识别", "记忆/检索", "主动协助"], fontsize=9.5)
    ax.set_xlabel("覆盖范围", fontsize=10.5, labelpad=7)
    ax.set_ylabel("能力层级", fontsize=10.5, labelpad=7)
    ax.grid(color=GRID, linewidth=0.8, linestyle="--", alpha=0.7)
    ax.set_axisbelow(True)

    ax.add_patch(Rectangle((0.62, 2.55), 0.84, 1.55, facecolor=TEAL, alpha=0.10,
                           edgecolor=TEAL, linewidth=1.2, linestyle="--"))
    ax.text(1.04, 4.18, "空位", ha="center", va="bottom", fontsize=9.5, color=TEAL, fontweight="bold")

    for i, (name, x, y, m, cat) in enumerate(products, start=1):
        color = palette[cat]
        if cat == "findyy":
            ax.scatter([x], [y], s=380, marker="*", color=color, edgecolor="white", linewidth=1.5, zorder=10)
        else:
            ax.scatter([x], [y], s=100 + m * 55, color=color, alpha=0.88, edgecolor="white", linewidth=1.2, zorder=5)

    # label only the key products; the rest are in table 6.2
    key_labels = [
        ("Findyy 目标", 1.12, 3.98, "left", TEAL, 9.2, "bold", None),
        ("Vstarcam CS997A", 1.10, 2.08, "left", BLUE, 8.2, "normal", None),
        ("Violoop", 1.10, 3.18, "left", ORANGE, 8.2, "normal", None),
        ("Camtells", 1.55, 3.55, "right", ORANGE, 8.2, "normal", (2.00, 3.18)),
        ("Prompt/Seemour", 2.95, 2.95, "left", ORANGE, 8.2, "normal", (2.62, 3.18)),
        ("Apple HomeView", 3.12, 3.68, "left", ORANGE, 8.2, "normal", None),
        ("MemPal", 3.40, 3.48, "left", ORANGE, 8.2, "normal", None),
        ("AirTag 2", 4.10, 2.55, "left", GRAY, 8.2, "normal", None),
        ("小米 Tag", 3.98, 2.30, "left", GRAY, 8.2, "normal", None),
        ("小度 X9", 2.28, 2.18, "left", BLUE, 8.2, "normal", None),
    ]
    for name, x, y, ha, color, size, weight, arrow in key_labels:
        if arrow is None:
            ax.text(x, y, name, ha=ha, va="center", fontsize=size, color=color, fontweight=weight, zorder=11)
        else:
            ax.annotate(name, xy=arrow, xytext=(x, y), ha=ha, va="center", fontsize=size,
                        color=color, fontweight=weight, zorder=11,
                        arrowprops=dict(arrowstyle="-", color=color, lw=0.8, alpha=0.7))

    from matplotlib.lines import Line2D
    handles = [
        Line2D([0], [0], marker="o", color="w", markerfacecolor=GRAY, markersize=9, label="智能标签"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=BLUE, markersize=9, label="安防/智能屏"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=ORANGE, markersize=9, label="视觉记忆/邻近"),
        Line2D([0], [0], marker="o", color="w", markerfacecolor=PURPLE, markersize=9, label="机器人/巡逻"),
        Line2D([0], [0], marker="*", color="w", markerfacecolor=TEAL, markersize=13, label="Findyy 目标"),
    ]
    ax.legend(handles=handles, loc="upper center", bbox_to_anchor=(0.5, -0.13), ncol=5, frameon=False, fontsize=8.2)
    ax.text(0.01, -0.24, "气泡大小=成熟度（1–5）；未标注点为其他邻近产品，详见 6.2 表。",
            transform=ax.transAxes, fontsize=7.5, color="#6B7280")
    ax.set_title("竞品定位：桌面 × 记忆是空位，但空位很小", fontsize=13.5, fontweight="bold", pad=10, loc="left")
    save(fig, "01_positioning.png")


# ---------------------------------------------------------------- 02 price ladder
def chart_price_ladder():
    items = [
        ("摩米士防丢器", 42, "tracker"),
        ("小米 Tag（BLE）", 69, "tracker"),
        ("小米 Tag（UWB）", 129, "tracker"),
        ("小米摄像头 3", 179, "camera"),
        ("萤石 C6c 4K", 200, "camera"),
        ("AirTag 2", 249, "tracker"),
        ("Samsung SmartTag2（约）", 250, "tracker"),
        ("天猫精灵 CC6", 294, "camera"),
        ("小米摄像头 5 Pro", 499, "camera"),
        ("小度智能屏 X9 Ultra", 629, "camera"),
        ("Findyy 目标价", 849, "findyy"),
        ("Camtells 众筹客单", 4300, "direct"),
        ("Violoop（$399）", 2850, "direct"),
        ("Ugreen HomeAgent（$899）", 6400, "direct"),
        ("Samsung Ballie（>$2,000）", 14300, "direct"),
    ]
    items = sorted(items, key=lambda x: x[1])
    fig, ax = plt.subplots(figsize=(9.6, 6.2))
    colors = {"tracker": GRAY, "camera": BLUE, "direct": ORANGE, "findyy": TEAL}
    y = np.arange(len(items))
    for i, (name, price, cat) in enumerate(items):
        ax.hlines(i, 35, price, color=colors[cat], linewidth=1.2, alpha=0.55)
        ax.scatter(price, i, s=110 if cat != "findyy" else 190, color=colors[cat], zorder=5,
                   marker="o" if cat != "findyy" else "D", edgecolor="white", linewidth=1.2)
        if name == "Findyy 目标价":
            ax.text(1080, i, "¥699–999", va="center", fontsize=9, color=TEAL, fontweight="bold")
        else:
            label = f"¥{price:,}" if price < 2000 else f"≈¥{price:,}"
            ax.text(price * 1.08, i, label, va="center", fontsize=8.5, color=colors[cat])
    ax.axvspan(699, 999, color=TEAL, alpha=0.10, zorder=0)
    ax.axvline(699, color=TEAL, linestyle="--", linewidth=1, alpha=0.7)
    ax.axvline(999, color=TEAL, linestyle="--", linewidth=1, alpha=0.7)
    ax.set_xscale("log")
    ax.set_xlim(35, 24000)
    ax.set_ylim(-1.15, len(items) - 0.2)
    ax.set_xticks([50, 100, 200, 500, 1000, 2000, 5000, 10000, 20000])
    ax.get_xaxis().set_major_formatter(mtick.FuncFormatter(lambda v, p: f"¥{int(v):,}"))
    ax.set_yticks(y)
    ax.set_yticklabels([x[0] for x in items], fontsize=9)
    ax.set_xlabel("价格（人民币，对数刻度；美元按 1 USD≈7.15 CNY 粗略换算）", fontsize=10, labelpad=8)
    ax.grid(axis="x", color=GRID, linewidth=0.8, linestyle="--", alpha=0.8)
    ax.set_axisbelow(True)
    ax.set_title("价格锚点：Findyy 目标价是 AirTag 的 3–4 倍", fontsize=14, fontweight="bold", pad=12, loc="left")
    ax.text(0.99, 0.01, "注：阴影带为 Findyy 目标价区间；Camtells 为众筹客单价，不是单机售价；SmartTag2 为约数。",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=7.8, color="#6B7280")
    save(fig, "02_price_ladder.png")


# ---------------------------------------------------------------- 03 evidence scorecard
def chart_evidence_scorecard():
    dims = [
        ("痛点频率", 4.5),
        ("情绪强度", 4.5),
        ("社媒热度", 4.0),
        ("付费证据", 2.5),
        ("替代品缺口", 2.5),
        ("隐私接受度", 2.0),
    ]
    fig, ax = plt.subplots(figsize=(9.6, 4.4))
    y = np.arange(len(dims))[::-1]
    colors = [TEAL if s >= 4 else (GOLD if s >= 3 else RED) for _, s in dims]
    for yi, (name, score), c in zip(y, dims, colors):
        ax.hlines(yi, 0, score, color=c, linewidth=3.5, alpha=0.85)
        ax.scatter(score, yi, s=120, color=c, zorder=5, edgecolor="white", linewidth=1.2)
        ax.text(score + 0.10, yi, f"{score:.1f}", va="center", fontsize=10.5, fontweight="bold", color="#1F2937")
    ax.set_yticks(y)
    ax.set_yticklabels([d[0] for d in dims], fontsize=10.5)
    ax.set_xlim(0, 5.4)
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.axvline(3, color="#6B7280", linestyle="--", linewidth=1)
    ax.set_xlabel("证据强度（1=弱，5=强；作者基于公开证据评分）", fontsize=10, labelpad=8)
    ax.grid(axis="x", color=GRID, linewidth=0.8, linestyle="--", alpha=0.8)
    ax.set_axisbelow(True)
    ax.set_title("需求证据评分：痛点很强，付费与隐私两项拖后腿", fontsize=14, fontweight="bold", pad=12, loc="left")
    ax.text(0.99, 0.01, "评分依据见 8.1 节证据表；评分为作者判断，不是平台数据。", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=7.8, color="#6B7280")
    save(fig, "03_evidence_scorecard.png")


# ---------------------------------------------------------------- 04 market funnel
def chart_market_funnel():
    stages = [
        ("城镇家庭", 34860, "2025 年全国 51,465 万户 × 67.74% 城镇化（粗略推导）"),
        ("有书桌/工作台", 12201, "假设 35% 家庭有独立书桌/工作台"),
        ("经常忘事", 4295, "× 35.2% 经常忘事（中国青年报 2020，N=2002）"),
        ("高痛/早期采用", 430, "× 10% 高痛且愿尝试新硬件（假设）"),
        ("愿付 ¥699+", 43, "× 10% 价格接受度（假设，待验证）"),
    ]
    fig, ax = plt.subplots(figsize=(9.0, 5.9))
    ax.set_xlim(0, 10)
    ax.set_ylim(-1.45, len(stages) + 1.0)
    ax.axis("off")
    max_w = 8.2
    colors = ["#1F3A5F", "#2A5A7A", TEAL, GOLD, ORANGE]
    for i, (name, value, note) in enumerate(stages):
        w_top = max_w * (1 - i * 0.155)
        w_bot = max_w * (1 - (i + 1) * 0.155)
        y_top = len(stages) - i
        y_bot = y_top - 0.72
        cx = 4.9
        poly = Polygon([[cx - w_top / 2, y_top], [cx + w_top / 2, y_top],
                        [cx + w_bot / 2, y_bot], [cx - w_bot / 2, y_bot]],
                       closed=True, facecolor=colors[i], edgecolor="white", linewidth=1.5, alpha=0.92)
        ax.add_patch(poly)
        ax.text(cx, (y_top + y_bot) / 2, f"{name}  {value:,} 万户", ha="center", va="center",
                fontsize=10.2, color="white", fontweight="bold")
        ax.text(cx + max_w / 2 + 0.2, (y_top + y_bot) / 2, note, ha="left", va="center", fontsize=7.5, color="#4B5563")
    ax.text(4.9, -0.45, "SAM ≈ 43 万户 × ¥699 ≈ ¥3.0 亿元/年（基准情景，方向性测算）", ha="center", va="center",
            fontsize=10.5, color=TEAL, fontweight="bold")
    ax.text(0.02, -1.25, "注：假设均可调整；本图不是预测，而是把“哪些假设最敏感”显性化。", fontsize=7.5, color="#6B7280")
    ax.set_title("方向性测算：从 3.49 亿城镇家庭到 3 亿元 SAM", fontsize=14, fontweight="bold", pad=10, loc="left")
    save(fig, "04_market_funnel.png")


# ---------------------------------------------------------------- 05 segment matrix
def chart_segment_matrix():
    segs = [
        ("大众消费者", 2.0, 4.0, 100, "低付费、最大人群", (0.12, 0.12), "left"),
        ("创作者/小型工作室", 4.2, 4.5, 5, "高价值器材、桌面集中", (-0.12, 0.16), "right"),
        ("ADHD 成人", 3.5, 4.8, 25, "高痛、外部大脑", (0.12, 0.10), "left"),
        ("老人/MCI 照护者", 4.5, 4.2, 50, "子女付费、照护叙事", (-0.12, -0.12), "right"),
        ("收纳爱好者", 2.5, 3.5, 20, "审美/整齐，非记忆", (0.12, -0.12), "left"),
    ]
    fig, ax = plt.subplots(figsize=(9.2, 6.2))
    ax.set_xlim(1.4, 5.9)
    ax.set_ylim(3.0, 5.25)
    ax.axvline(3.4, color="#9CA3AF", linestyle="--", linewidth=1)
    ax.axhline(4.0, color="#9CA3AF", linestyle="--", linewidth=1)
    ax.text(5.85, 5.20, "优先切入", ha="right", va="top", fontsize=11, color=TEAL, fontweight="bold")
    ax.text(1.45, 5.20, "观望/教育", ha="left", va="top", fontsize=11, color=GOLD, fontweight="bold")
    ax.text(5.85, 3.04, "不优先", ha="right", va="bottom", fontsize=11, color=RED, fontweight="bold")
    colors = [GRAY, TEAL, ORANGE, PURPLE, BLUE]
    for (name, x, y, pop, note, off, ha), c in zip(segs, colors):
        ax.scatter(x, y, s=pop * 6 + 160, color=c, alpha=0.85, edgecolor="white", linewidth=1.5, zorder=5)
        ax.annotate(f"{name}\n{note}", (x, y), xytext=(x + off[0], y + off[1]), fontsize=8.4,
                    color="#1F2937", ha=ha, va="center")
    ax.set_xlabel("付费意愿（1–5）", fontsize=10.5)
    ax.set_ylabel("痛点/产品匹配（1–5）", fontsize=10.5)
    ax.grid(color=GRID, linewidth=0.8, linestyle="--", alpha=0.7)
    ax.set_axisbelow(True)
    ax.set_title("人群优先级：先打创作者/工作室，老人照护第二", fontsize=14, fontweight="bold", pad=12, loc="left")
    ax.text(0.02, 0.02, "气泡大小=可触达人群规模（示意）", transform=ax.transAxes, fontsize=7.8, color="#6B7280")
    save(fig, "05_segment_matrix.png")


# ---------------------------------------------------------------- 06 go/no-go
def chart_go_no_go():
    rows = [
        ("需求频率/强度（25%）", 0.25, 4.5),
        ("替代品威胁（反向，20%）", 0.20, 2.0),
        ("付费意愿（20%）", 0.20, 2.5),
        ("竞争空位（15%）", 0.15, 3.0),
        ("技术/成本可行性（10%）", 0.10, 3.5),
        ("隐私/合规/IP（10%）", 0.10, 2.5),
    ]
    fig, ax = plt.subplots(figsize=(9.4, 4.6))
    y = np.arange(len(rows))[::-1]
    colors = [TEAL if s >= 3.5 else (GOLD if s >= 2.5 else RED) for _, _, s in rows]
    ax.barh(y, [r[2] for r in rows], color=colors, height=0.55, alpha=0.9)
    ax.set_yticks(y)
    ax.set_yticklabels([r[0] for r in rows], fontsize=10.2)
    ax.set_xlim(0, 5.4)
    ax.set_xticks([0, 1, 2, 3, 4, 5])
    ax.axvline(3, color="#6B7280", linestyle="--", linewidth=1)
    for yi, (name, w, s) in zip(y, rows):
        ax.text(s + 0.08, yi, f"{s:.1f}", va="center", fontsize=10, fontweight="bold")
    ax.set_xlabel("得分（1=差，5=好；替代品威胁为反向计分）", fontsize=10)
    ax.grid(axis="x", color=GRID, linewidth=0.8, linestyle="--", alpha=0.8)
    ax.set_axisbelow(True)
    ax.set_title("Go/No-Go 加权评分：3.1/5，结论为“条件性 Go”", fontsize=14, fontweight="bold", pad=12, loc="left")
    ax.text(0.99, 0.01, "加权总分 = Σ(权重×得分) = 3.1；门槛 3.0。", transform=ax.transAxes, ha="right", va="bottom",
            fontsize=8, color="#6B7280")
    save(fig, "06_go_no_go.png")


# ---------------------------------------------------------------- 07 social mix
def chart_social_mix():
    fig, axes = plt.subplots(1, 2, figsize=(11.0, 4.5), gridspec_kw={"width_ratios": [1.0, 1.15]})
    types = ["纯痛点吐槽", "解决方案/技巧", "产品种草", "娱乐玄学", "科普/新闻", "娱乐（非玄学）"]
    counts = [14, 11, 6, 4, 3, 1]
    colors = [ORANGE, TEAL, GRAY, GOLD, BLUE, PURPLE]
    y = np.arange(len(types))[::-1]
    axes[0].barh(y, counts, color=colors, height=0.6, alpha=0.9)
    axes[0].set_yticks(y)
    axes[0].set_yticklabels(types, fontsize=9.5)
    axes[0].set_xlim(0, 16)
    for yi, c in zip(y, counts):
        axes[0].text(c + 0.2, yi, str(c), va="center", fontsize=9.5, fontweight="bold")
    axes[0].set_title("40 条内容样本的类型分布", fontsize=11.5, fontweight="bold", loc="left")
    axes[0].set_xlabel("条数", fontsize=9.5)
    axes[0].grid(axis="x", color=GRID, linestyle="--", linewidth=0.8, alpha=0.7)
    axes[0].set_axisbelow(True)

    tags = ["#看我怎么收拾你\n（收纳/品牌活动）", "#超市找东西挑战", "#记录老年痴呆症\n患者老人日常", "#桌面书本置物架", "#衣橱换季整理中"]
    plays = [710_000_000, 77_199_000, 7_161_000, 851_000, 57_000]
    y2 = np.arange(len(tags))[::-1]
    axes[1].barh(y2, plays, color=[GOLD, TEAL, PURPLE, BLUE, GRAY], height=0.6, alpha=0.9)
    axes[1].set_yticks(y2)
    axes[1].set_yticklabels(tags, fontsize=8.2)
    axes[1].set_xscale("log")
    axes[1].set_xlim(30_000, 2_000_000_000)
    axes[1].xaxis.set_major_formatter(mtick.FuncFormatter(lambda v, p: f"{v/1e8:.0f}亿" if v >= 1e8 else f"{v/1e4:.0f}万"))
    for yi, v in zip(y2, plays):
        axes[1].text(v * 1.15, yi, f"{v/1e8:.1f}亿" if v >= 1e8 else f"{v/1e4:.0f}万", va="center", fontsize=8.2)
    axes[1].set_title("抖音话题播放量（A 级，页面公开）", fontsize=11.5, fontweight="bold", loc="left")
    axes[1].set_xlabel("播放量（对数刻度）", fontsize=9.5)
    axes[1].grid(axis="x", color=GRID, linestyle="--", linewidth=0.8, alpha=0.7)
    axes[1].set_axisbelow(True)

    fig.text(0.01, 0.01, "注：内容类型为作者对 40 条样本的逐条归类（C 级）；抖音话题播放量为页面直接渲染（A 级），仅代表该话题，不代表全部“找东西”内容。",
             fontsize=7.4, color="#6B7280")
    fig.suptitle("短视频证据：痛点内容很多，但产品种草很薄", fontsize=14, fontweight="bold", x=0.01, ha="left")
    fig.tight_layout(rect=[0, 0.03, 1, 0.93])
    save(fig, "07_social_mix.png")


# ---------------------------------------------------------------- 08 timeline
def chart_timeline():
    events = [
        (2021.3, "AirTag 发布", "苹果进入物品追踪", TEAL),
        (2023.5, "Prompt AI 成立", "Seemour：家庭视觉理解", ORANGE),
        (2024.9, "Astro for Business 停产", "上市约 7 个月", RED),
        (2025.7, "Samsung Ballie 延期", "定价或超 $2,000", PURPLE),
        (2025.10, "苹果洽谈收购 Prompt AI", "Seemour App 下架", ORANGE),
        (2026.1, "AirTag 2 发布", "¥249；精确查找 +50%", TEAL),
        (2026.3, "小米 Tag 国行上架", "BLE ¥69 / UWB ¥129", GRAY),
        (2026.9, "Ugreen HomeAgent", "本地 AI + 视频检索", BLUE),
        (2026.10, "Apple HomeView 发布", "Home Collection：2.5K + 自然语言搜索", ORANGE),
        (2026.12, "Apple 摄像头开售", "HomeKit 生态入场", ORANGE),
    ]
    fig, ax = plt.subplots(figsize=(10.8, 4.8))
    ax.set_xlim(2020.8, 2028.2)
    ax.set_ylim(-0.8, len(events) - 0.2)
    ax.set_yticks([])
    ax.set_xticks([2021, 2022, 2023, 2024, 2025, 2026, 2027])
    ax.set_xticklabels(["2021", "2022", "2023", "2024", "2025", "2026", "2027"])
    ax.grid(axis="x", color=GRID, linestyle="--", linewidth=0.7, alpha=0.6)
    for i, (x, title, sub, color) in enumerate(events):
        yy = len(events) - 1 - i
        ax.plot([2020.8, x], [yy, yy], color=color, linewidth=0.9, alpha=0.35)
        ax.scatter([x], [yy], s=70, color=color, zorder=5, edgecolor="white", linewidth=1.2)
        ax.text(x + 0.08, yy + 0.06, title, ha="left", va="bottom", fontsize=8.6, color=color, fontweight="bold")
        ax.text(x + 0.08, yy - 0.08, sub, ha="left", va="top", fontsize=7.6, color="#4B5563")
    ax.axvline(2026, color="#9CA3AF", linestyle=":", linewidth=1)
    ax.text(2026.03, len(events) - 0.55, "2026：大厂集中入场", fontsize=8.5, color="#6B7280")
    ax.set_title("竞争时间线：2026 年是大厂集中入场的一年", fontsize=14, fontweight="bold", pad=12, loc="left")
    ax.text(0.01, 0.01, "来源：公开报道，详见附录 A；时间按发布/报道月份近似。", transform=ax.transAxes,
            fontsize=7.4, color="#6B7280")
    save(fig, "08_timeline.png")


# ---------------------------------------------------------------- 09 risk heatmap
def chart_risk_heatmap():
    risks = ["隐私/信任", "准确性/遮挡", "覆盖范围（桌面外）", "价格/替代品", "IP/FTO", "供应链/成本"]
    cols = ["发生概率", "影响", "可缓解性"]
    data = np.array([
        [4.5, 5.0, 3.0],
        [4.5, 4.5, 3.5],
        [4.8, 4.0, 2.5],
        [5.0, 4.5, 2.0],
        [3.5, 5.0, 2.0],
        [3.0, 3.5, 3.5],
    ])
    fig, ax = plt.subplots(figsize=(8.4, 4.6))
    ax.imshow(data, cmap="RdYlGn_r", vmin=1, vmax=5, aspect="auto")
    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, fontsize=10)
    ax.set_yticks(range(len(risks)))
    ax.set_yticklabels(risks, fontsize=10)
    for i in range(len(risks)):
        for j in range(len(cols)):
            ax.text(j, i, f"{data[i, j]:.1f}", ha="center", va="center", fontsize=10.5,
                    color="white" if data[i, j] >= 4.0 else "#1F2937", fontweight="bold")
    ax.set_title("主要风险热力图（5=高概率/高影响/易缓解）", fontsize=14, fontweight="bold", pad=12, loc="left")
    ax.text(0.01, -0.18, "注：评分为作者基于公开证据的判断；“可缓解性”越高越容易通过设计/合规/供应链解决。",
            transform=ax.transAxes, fontsize=7.6, color="#6B7280")
    save(fig, "09_risk_heatmap.png")


if __name__ == "__main__":
    chart_positioning()
    chart_price_ladder()
    chart_evidence_scorecard()
    chart_market_funnel()
    chart_segment_matrix()
    chart_go_no_go()
    chart_social_mix()
    chart_timeline()
    chart_risk_heatmap()
