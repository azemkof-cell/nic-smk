# -*- coding: utf-8 -*-
"""Еженедельный отчёт по строительному контролю — по образцу «Талаги»."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

from . import core
from .docs import _cell_text, _margins, _para, _set_run, _shade, _widths, ru_date
from .protocol_docs import _footer, _header, _signatures

GOLD = "C9A227"
DARK = "1F2A44"
GREY = "6B7280"


def _gold_line(doc, width_cm=18.0):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "18")
    bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), GOLD)
    pbdr.append(bottom)
    pPr.append(pbdr)


def _top_border(cell, color=GOLD, sz=24):
    tcPr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    top = OxmlElement("w:top")
    top.set(qn("w:val"), "single"); top.set(qn("w:sz"), str(sz))
    top.set(qn("w:space"), "0"); top.set(qn("w:color"), color)
    borders.append(top)
    tcPr.append(borders)


def _no_borders(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblPr.append(borders)


def _crop_cover(path: str) -> str:
    """Обрезает обложечное фото под 16:9, чтобы страница не разъезжалась."""
    try:
        from PIL import Image
        im = Image.open(path).convert("RGB")
        w, h = im.size
        target = 16 / 9
        if w / h > target:
            nw = int(h * target)
            im = im.crop(((w - nw) // 2, 0, (w + nw) // 2, h))
        else:
            nh = int(w / target)
            im = im.crop((0, max(0, (h - nh) // 2), w, max(nh, (h + nh) // 2)))
        im.thumbnail((1800, 1800))
        out = Path(core.DATA) / "cover_tmp.jpg"
        im.save(out, quality=88)
        return str(out)
    except Exception:
        return path


def _photo(doc, path: str, width_cm=17.4, caption: str = ""):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    try:
        if path and Path(path).exists():
            p.add_run().add_picture(str(path), width=Cm(width_cm))
    except Exception:
        pass
    if caption:
        cp = doc.add_paragraph()
        cp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        cp.paragraph_format.space_after = Pt(6)
        r = cp.add_run(caption)
        _set_run(r, 8, italic=True, color=GREY)


def _kpi_table(doc, kpis: list[dict]):
    if not kpis:
        return
    t = doc.add_table(rows=1, cols=len(kpis))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    _no_borders(t)
    for i, k in enumerate(kpis):
        cell = t.rows[0].cells[i]
        _top_border(cell)
        p = cell.paragraphs[0]
        p.paragraph_format.space_before = Pt(4)
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(str(k.get("value", "")))
        _set_run(r, 20, bold=True, color="2E7D32" if k.get("green") else DARK)
        p2 = cell.add_paragraph()
        p2.paragraph_format.space_after = Pt(2)
        r2 = p2.add_run(k.get("label", ""))
        _set_run(r2, 8, color=GREY)
    _widths(t, [18.0 / len(kpis)] * len(kpis))
    _margins(t, 60, 40, 60, 60)


def build(record: dict, data: dict, out_path: Path, signer: dict | None = None) -> Path:
    comp = core.company()
    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(15); s.right_margin = Mm(15)
    s.top_margin = Mm(10); s.bottom_margin = Mm(12)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(10)
    _footer(doc, False, None)

    # ---------- обложка ----------
    _header(doc, comp)
    _gold_line(doc)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(f"г. {data.get('city') or ''} · {data.get('year') or date.today().year} г.")
    _set_run(r, 9, color=GREY)

    # заголовок с золотой полосой слева
    t = doc.add_table(rows=1, cols=2)
    _no_borders(t)
    bar, txt = t.rows[0].cells
    _shade(bar, GOLD)
    titles = [
        ("ЕЖЕНЕДЕЛЬНЫЙ ОТЧЕТ ПО СТРОИТЕЛЬНОМУ КОНТРОЛЮ", 8, True, GOLD),
        (f"Отчет № {record['number']}", 22, True, "111111"),
        (f"за период {data.get('period_text') or ''}", 13, True, "111111"),
        (data.get("object_short") or record.get("object_name", ""), 9, False, GREY),
    ]
    first = True
    for text, size, bold, color in titles:
        p = txt.paragraphs[0] if first else txt.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(2)
        p.paragraph_format.left_indent = Cm(0.28)
        r = p.add_run(text)
        _set_run(r, size, bold=bold, color=color)
    _widths(t, [0.18, 17.2])
    _margins(t, 0, 0, 0, 0)

    cover_photo = (data.get("photos") or [{}])[0].get("path") if data.get("photos") else ""
    if cover_photo:
        _photo(doc, _crop_cover(cover_photo), 17.2, data.get("cover_caption") or "")

    # реквизиты
    rows = [
        ("ЗАКАЗЧИК", data.get("customer") or "—"),
        ("ПОДРЯДЧИК", data.get("contractor") or "—"),
        ("КОНТРАКТ НА СК", data.get("contract") or "—"),
        ("СПЕЦИАЛИСТ СК", data.get("specialist") or "—"),
    ]
    t = doc.add_table(rows=len(rows), cols=2)
    _no_borders(t)
    for i, (k, v) in enumerate(rows):
        c0, c1 = t.rows[i].cells
        _cell_text(c0, k, 8, bold=True, align=WD_ALIGN_PARAGRAPH.LEFT)
        for par in c0.paragraphs:
            for run in par.runs:
                run.font.color.rgb = RGBColor.from_string(GOLD)
        _cell_text(c1, v, 9, align=WD_ALIGN_PARAGRAPH.LEFT)
        for c in (c0, c1):
            tcPr = c._tc.get_or_add_tcPr()
            borders = OxmlElement("w:tcBorders")
            bottom = OxmlElement("w:bottom")
            bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "4")
            bottom.set(qn("w:space"), "0"); bottom.set(qn("w:color"), "DDDDDD")
            borders.append(bottom); tcPr.append(borders)
    _widths(t, [4.2, 13.2])
    _margins(t, 50, 50, 0, 0)
    doc.add_paragraph().paragraph_format.space_after = Pt(4)

    _kpi_table(doc, data.get("kpis") or [])
    doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)

    # ---------- страница 2 ----------
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(8)
    r = p.add_run(f"{comp.get('name','')} · Еженедельный отчет № {record['number']} · "
                  f"{data.get('object_short','')} · {data.get('period_short','')}")
    _set_run(r, 8, color=GREY)

    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(2); p.paragraph_format.space_after = Pt(4)
    r = p.add_run("1. ОБЩИЕ СВЕДЕНИЯ"); _set_run(r, 11, bold=True)

    info = [("Объект", data.get("object_full") or record.get("object_name", "")),
            ("Участки производства работ", data.get("sections") or "—"),
            ("Отчетный период", data.get("period_text") or ""),
            ("Исполнитель СК", data.get("executor") or comp.get("name", ""))]
    t = doc.add_table(rows=len(info), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(info):
        _cell_text(t.rows[i].cells[0], k, 9, bold=True)
        _shade(t.rows[i].cells[0], "F5F1E4")
        _cell_text(t.rows[i].cells[1], v, 9)
    _widths(t, [4.6, 12.8])
    _margins(t, 40, 40, 60, 60)

    if data.get("summary"):
        p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(2)
        r = p.add_run("Краткое резюме. "); _set_run(r, 10, bold=True)
        r = p.add_run(data["summary"]); _set_run(r, 10)

    works = data.get("works") or []
    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(4)
    r = p.add_run("2. ВЫПОЛНЕННЫЕ РАБОТЫ ЗА ПЕРИОД"); _set_run(r, 11, bold=True)
    if works:
        t = doc.add_table(rows=1, cols=7)
        t.style = "Table Grid"
        heads = ["№", "Вид работ", "Ед. изм.", "За период", "Всего", "% от договора", "Статус"]
        for i, h in enumerate(heads):
            _cell_text(t.rows[0].cells[i], h, 8, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for i, w in enumerate(works[:30], 1):
            cells = t.add_row().cells
            vals = [str(i), w.get("name", ""), w.get("unit", "") or "—",
                    w.get("period", "") or "—", w.get("total", "") or "—",
                    w.get("pct") or "—", w.get("status", "") or "—"]
            for j, v in enumerate(vals):
                _cell_text(cells[j], v, 8.5,
                           align=WD_ALIGN_PARAGRAPH.LEFT if j == 1 else WD_ALIGN_PARAGRAPH.CENTER)
        _widths(t, [0.7, 7.8, 1.7, 2.2, 2.0, 2.4, 1.8])
        _margins(t, 25, 25, 40, 40)
    else:
        _para(doc, "За отчетный период работы не зафиксированы.", 10)

    photos = data.get("photos") or []
    if photos:
        doc.add_paragraph().add_run().add_break(WD_BREAK.PAGE)
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(4)
        r = p.add_run("3. ФОТОФИКСАЦИЯ"); _set_run(r, 11, bold=True)
        table = doc.add_table(rows=0, cols=2)
        _no_borders(table)
        for i in range(0, min(len(photos), 8), 2):
            row = table.add_row()
            for j in range(2):
                cell = row.cells[j]
                cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                pp = cell.paragraphs[0]
                pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if i + j < len(photos):
                    ph = photos[i + j]
                    path = Path(ph.get("path", ""))
                    if path.exists():
                        try:
                            pp.add_run().add_picture(str(path), width=Cm(8.4))
                        except Exception:
                            pass
                    cap = cell.add_paragraph()
                    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cap.paragraph_format.space_after = Pt(8)
                    txt = " · ".join(x for x in [ph.get("caption", ""), ph.get("date", "")] if x)
                    rr = cap.add_run(txt)
                    _set_run(rr, 8, italic=True, color=GREY)
        _widths(table, [8.6, 8.6])

    doc.add_paragraph()
    _signatures(doc, comp, record, signer)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
