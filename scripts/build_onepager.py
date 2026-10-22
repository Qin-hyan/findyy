# -*- coding: utf-8 -*-
"""Build a one-page conclusion DOCX (and later PDF)."""
import os
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

OUT = r"D:\Findyy\Findyy_一页纸结论_2026-10.docx"
NAVY = RGBColor(0x1F, 0x3A, 0x5F)
TEAL = RGBColor(0x2A, 0x9D, 0x8F)
GRAY = RGBColor(0x6B, 0x72, 0x80)
DARK = RGBColor(0x1F, 0x29, 0x37)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
CN = "微软雅黑"


def font(run, size=9, bold=False, color=DARK):
    run.font.name = CN
    rPr = run._element.get_or_add_rPr()
    rFonts = rPr.find(qn("w:rFonts"))
    if rFonts is None:
        rFonts = OxmlElement("w:rFonts")
        rPr.append(rFonts)
    rFonts.set(qn("w:eastAsia"), CN)
    rFonts.set(qn("w:ascii"), CN)
    rFonts.set(qn("w:hAnsi"), CN)
    run.font.size = Pt(size)
    run.bold = bold
    run.font.color.rgb = color


def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def cell_margins(cell, top=50, bottom=50, left=80, right=80):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = OxmlElement("w:tcMar")
    for k, v in (("top", top), ("bottom", bottom), ("start", left), ("end", right)):
        node = OxmlElement(f"w:{k}")
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")
        tcMar.append(node)
    tcPr.append(tcMar)


def para(doc, text, size=9, bold=False, color=DARK, space_after=2, align=WD_ALIGN_PARAGRAPH.LEFT):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(space_after)
    p.paragraph_format.line_spacing = 1.1
    r = p.add_run(text)
    font(r, size, bold, color)
    return p


def build():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width = Cm(21.0)
    sec.page_height = Cm(29.7)
    sec.top_margin = Cm(1.2)
    sec.bottom_margin = Cm(1.2)
    sec.left_margin = Cm(1.4)
    sec.right_margin = Cm(1.4)

    # top band
    t = doc.add_table(rows=1, cols=1)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0)
    c.width = Cm(18.2)
    shade(c, "1F3A5F")
    cell_margins(c, 140, 140, 180, 180)
    p = c.paragraphs[0]
    r = p.add_run("Findyy  ")
    font(r, 22, True, WHITE)
    r = p.add_run("一页纸结论")
    font(r, 22, True, RGBColor(0xE9, 0xC4, 0x6A))
    p2 = c.add_paragraph()
    r = p2.add_run("桌面物品记忆相机 · 市场调研与需求验证 · 2026-10-22")
    font(r, 8.5, False, RGBColor(0xD1, 0xD5, 0xDB))

    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # conclusion
    t = doc.add_table(rows=1, cols=1)
    c = t.cell(0, 0)
    c.width = Cm(18.2)
    shade(c, "E8F4F1")
    cell_margins(c, 100, 100, 160, 160)
    p = c.paragraphs[0]
    r = p.add_run("结论：条件性 Go")
    font(r, 15, True, TEAL)
    p2 = c.add_paragraph()
    r = p2.add_run("需求真实，但“桌面物品记忆相机”目前既没有成熟同款，也没有被验证的付费市场。先打创作者/小型工作室，¥699–999 切入，用 4 周验证定金、访谈与 FTO，再决定是否开模。")
    font(r, 8.8, False, DARK)

    doc.add_paragraph().paragraph_format.space_after = Pt(2)

    # three findings in a 3-column table
    t = doc.add_table(rows=2, cols=3)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    heads = ["市场：空位存在，但很小", "需求：痛点强，付费弱", "竞争：大厂正在入场"]
    bodies = [
        "25 个产品中，没有一款专用硬件同时具备“摄像头+物品识别+长期记忆+自然语言检索”。Camtells 只有 24 名众筹支持者、未发货；Prompt AI 技术可行但商业模式失败。",
        "35.2% 经常忘事；中国用户月均 154 分钟找东西；抖音“找东西”话题 7,719.9 万次。但主流支付价是 ¥69–249，产品种草仅 6/40，零成本技巧/玄学/问家人是强替代。",
        "Apple HomeView（2026-12）把 2.5K 摄像头、物体识别、自然语言视频搜索、端到端加密打包进 HomeKit；Ugreen、LG、Samsung、Memories.ai 同向。2026 年中国摄像头市场预计 −1.3%。",
    ]
    for i in range(3):
        c = t.cell(0, i)
        c.width = Cm(6.0)
        shade(c, "1F3A5F")
        cell_margins(c, 60, 60, 80, 80)
        p = c.paragraphs[0]
        r = p.add_run(heads[i])
        font(r, 9.2, True, WHITE)
        c2 = t.cell(1, i)
        c2.width = Cm(6.0)
        cell_margins(c2, 80, 80, 80, 80)
        p = c2.paragraphs[0]
        p.paragraph_format.line_spacing = 1.05
        r = p.add_run(bodies[i])
        font(r, 7.6, False, DARK)

    doc.add_paragraph().paragraph_format.space_after = Pt(1)

    # decision table
    rows = [
        ("滩头人群", "创作者/小型工作室（高价值器材、桌面集中、可报销）；第二是老人/MCI 照护者"),
        ("产品定位", "“桌面记忆助手”，卖“我上次放哪了”，不卖“防丢”；避免与 AirTag/安防摄像头比价"),
        ("价格", "¥699–999（创作者版 ¥999–1,299）；不强制订阅；核心功能本地"),
        ("核心功能", "一键扫描、物品库、自然语言查询、最后出现帧+时间+区域、手动纠错、物理遮蔽"),
        ("渠道", "众筹 + 内容电商 + 创作者社区；老人线走子女/养老机构"),
    ]
    t = doc.add_table(rows=len(rows) + 1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    c = t.cell(0, 0); c.width = Cm(3.2); shade(c, "1F3A5F"); cell_margins(c, 50, 50, 60, 60)
    p = c.paragraphs[0]; r = p.add_run("决策"); font(r, 8.2, True, WHITE)
    c = t.cell(0, 1); c.width = Cm(15.0); shade(c, "1F3A5F"); cell_margins(c, 50, 50, 60, 60)
    p = c.paragraphs[0]; r = p.add_run("建议"); font(r, 8.2, True, WHITE)
    for i, (k, v) in enumerate(rows, start=1):
        c = t.cell(i, 0); c.width = Cm(3.2); cell_margins(c, 45, 45, 60, 60)
        if i % 2 == 0: shade(c, "F4F7FA")
        p = c.paragraphs[0]; r = p.add_run(k); font(r, 7.8, True, NAVY)
        c = t.cell(i, 1); c.width = Cm(15.0); cell_margins(c, 45, 45, 60, 60)
        if i % 2 == 0: shade(c, "F4F7FA")
        p = c.paragraphs[0]; p.paragraph_format.line_spacing = 1.0
        r = p.add_run(v); font(r, 7.8, False, DARK)

    doc.add_paragraph().paragraph_format.space_after = Pt(1)

    # Go conditions
    p = doc.add_paragraph()
    r = p.add_run("Go 的五个条件（缺一不可）")
    font(r, 10, True, NAVY)
    p.paragraph_format.space_after = Pt(1)
    conds = [
        "定金转化 ≥2%（50/500 线索），退款率 <30%；",
        "30 位目标用户中 ≥30% 愿用 Findyy 替代/补充 AirTag，可接受价 ≥¥699；",
        "FTO 结论为“可设计绕开”或“可获许可”；",
        "10k 台 BOM ≤¥350，零售 ¥699 时毛利率 ≥45%；",
        "10 户日记研究中，设备覆盖 ≥60% 的“找不到”事件。",
    ]
    for c in conds:
        p = doc.add_paragraph()
        p.paragraph_format.left_indent = Cm(0.4)
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run("• ")
        font(r, 8.5, True, TEAL)
        r = p.add_run(c)
        font(r, 8.5, False, DARK)

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(1)
    r = p.add_run("4 周验证：落地页 + ¥99 定金（500 线索/50 定金） → 30 访谈（10 创作者/10 ADHD/10 照护者） → 10 户日记研究 + BOM 询价 → FTO + Go/No-Go。")
    font(r, 8.2, False, GRAY)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    r = p.add_run("不要用“AI 相机”的叙事去开模，先用“记忆”的价值去换定金。")
    font(r, 10, True, NAVY)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("数据截止 2026-10-22 · 公开资料与作者判断 · 不构成投资/法律意见")
    font(r, 7, False, GRAY)

    doc.save(OUT)
    print("saved", OUT)


if __name__ == "__main__":
    build()
