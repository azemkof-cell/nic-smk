# -*- coding: utf-8 -*-
"""Акты на объекте: отбор проб, освидетельствование, прочие."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Mm, Pt

from . import core
from .docs import _cell_text, _margins, _para, _set_run, _shade, _widths, ru_date
from .protocol_docs import _footer, _header

TITLES = {
    "sampling": "АКТ ОТБОРА ПРОБ (ОБРАЗЦОВ)",
    "inspection": "АКТ ОСВИДЕТЕЛЬСТВОВАНИЯ",
    "defect": "АКТ О ВЫЯВЛЕННЫХ ДЕФЕКТАХ",
}


def _gold_line(doc):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    pPr = p._p.get_or_add_pPr()
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "18")
    bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "C9A227")
    pbdr.append(bottom); pPr.append(pbdr)


def _section(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(4)
    r = p.add_run(text)
    _set_run(r, 10.5, bold=True)


def _sign_row(doc, label: str, name: str, img: str | None):
    t = doc.add_table(rows=1, cols=3)
    t.style = "Table Grid"
    for c in t.rows[0].cells:
        c.vertical_alignment = 1
    _cell_text(t.cell(0, 0), label, 9)
    p = t.cell(0, 1).paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(4)
    if img:
        from .protocol_docs import _asset
        q = _asset(img)
        if q:
            try:
                p.add_run().add_picture(str(q), width=Cm(3.0))
            except Exception:
                pass
    _cell_text(t.cell(0, 2), name or "", 9, align=WD_ALIGN_PARAGRAPH.CENTER)
    _widths(t, [6.0, 5.4, 5.4])
    _margins(t, 60, 60, 60, 60)


def build_sampling(record: dict, out_path: Path, signer: dict | None = None) -> Path:
    comp = core.company()
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (record.get("object_id") or 0,)).fetchone()
    con.close()
    o = dict(obj) if obj else {}

    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(16); s.right_margin = Mm(14)
    s.top_margin = Mm(12); s.bottom_margin = Mm(14)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(10)
    _footer(doc, False, None)
    _header(doc, comp)
    _gold_line(doc)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(TITLES.get(record.get("kind") or "sampling", TITLES["sampling"]))
    _set_run(r, 14, bold=True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(10)
    r = p.add_run(f"№ {record.get('act_no') or 'б/н'} от {ru_date(record.get('date') or date.today().isoformat())}")
    _set_run(r, 10.5, bold=True)

    _section(doc, "1. СВЕДЕНИЯ ОБ ОБЪЕКТЕ")
    obj_rows = [("Объект", o.get("object_title") or o.get("name") or "—"),
                ("Адрес", o.get("address") or "—"),
                ("Заказчик", record.get("customer") or o.get("customer") or "—"),
                ("Подрядчик", record.get("contractor") or o.get("contractor") or "—")]
    t = doc.add_table(rows=len(obj_rows), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(obj_rows):
        _cell_text(t.rows[i].cells[0], k, 9, bold=True)
        _shade(t.rows[i].cells[0], "F7F3E6")
        _cell_text(t.rows[i].cells[1], str(v), 9)
    _widths(t, [4.8, 12.4])
    _margins(t, 40, 40, 60, 60)

    _section(doc, "2. ОТБОР ПРОБ")
    rows = [("Материал / конструкция", record.get("material") or "—"),
            ("Нормативный документ", record.get("gost") or "—"),
            ("Место отбора", record.get("place") or "—"),
            ("Партия / объём", record.get("batch") or "—"),
            ("Условия отбора", record.get("conditions") or "температура воздуха, °C; влажность, %"),
            ("Цель отбора", record.get("purpose") or "испытание образцов")]
    t = doc.add_table(rows=len(rows), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(rows):
        _cell_text(t.rows[i].cells[0], k, 9, bold=True)
        _shade(t.rows[i].cells[0], "F7F3E6")
        _cell_text(t.rows[i].cells[1], str(v), 9)
    _widths(t, [4.8, 12.4])
    _margins(t, 40, 40, 60, 60)

    doc.add_paragraph()
    _para(doc, "Отбор произведён в соответствии с требованиями нормативных документов. "
               "Образцы упакованы, маркированы и переданы в испытательную лабораторию.", 9.5)

    _section(doc, "3. ПОДПИСИ СТОРОН")
    _sign_row(doc, "Представитель заказчика", record.get("customer_name") or "",
              record.get("customer_sign") or "")
    _sign_row(doc, "Представитель подрядчика", record.get("contractor_name") or "",
              record.get("contractor_sign") or "")
    _sign_row(doc, "Специалист СК", (signer or {}).get("name") or comp.get("lab_head", ""),
              (signer or {}).get("img") or comp.get("signature") or "")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
