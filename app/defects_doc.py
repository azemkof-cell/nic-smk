# -*- coding: utf-8 -*-
"""Дефектная ведомость по записям объекта."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Mm, Pt

from . import core
from .docs import _cell_text, _margins, _para, _set_run, _shade, _widths, ru_date
from .protocol_docs import _footer, _header, _signatures


def build(object_id: int, out_path: Path, signer: dict | None = None) -> Path:
    comp = core.company()
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    rows = con.execute("SELECT * FROM entries WHERE object_id=? ORDER BY edate, id", (object_id,)).fetchall()
    con.close()
    defects = []
    for r in rows:
        if "дефект" in (r["tags"] or "").lower():
            try:
                photos = json.loads(r["photos"] or "[]")
            except Exception:
                photos = []
            defects.append({"date": r["edate"], "author": r["author"], "comment": r["comment"],
                            "photos": photos})

    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(18); s.right_margin = Mm(15)
    s.top_margin = Mm(12); s.bottom_margin = Mm(15)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(10)
    _footer(doc, False, None)
    _header(doc, comp)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(2)
    r = p.add_run("ДЕФЕКТНАЯ ВЕДОМОСТЬ")
    _set_run(r, 14, bold=True)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(f"№ {object_id}-ДВ от {ru_date(date.today().isoformat())}")
    _set_run(r, 10.5, bold=True)

    info = [("Объект", (obj["name"] if obj else "") or "—"),
            ("Заказчик", (obj["customer"] if obj else "") or "—"),
            ("Подрядчик", (obj["contractor"] if obj else "") or "—")]
    t = doc.add_table(rows=len(info), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(info):
        _cell_text(t.rows[i].cells[0], k, 9, bold=True)
        _shade(t.rows[i].cells[0], "F2F2F2")
        _cell_text(t.rows[i].cells[1], v, 9)
    _widths(t, [4.2, 13.0])
    _margins(t, 40, 40, 60, 60)

    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(10); p.paragraph_format.space_after = Pt(4)
    r = p.add_run("Выявленные дефекты и замечания"); _set_run(r, 11, bold=True)

    if defects:
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        for i, h in enumerate(("№", "Дата / описание", "Фотофиксация")):
            _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for i, d in enumerate(defects, 1):
            cells = t.add_row().cells
            _cell_text(cells[0], str(i), 9, align=WD_ALIGN_PARAGRAPH.CENTER)
            txt = f"{ru_date(d['date'])}\n{d['comment']}"
            if d["author"]:
                txt += f"\n({d['author']})"
            _cell_text(cells[1], txt, 9)
            c = cells[2]
            p0 = c.paragraphs[0]
            p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
            added = False
            for ph in d["photos"][:2]:
                path = Path(ph.get("path") or "")
                if not path.exists() and ph.get("rel"):
                    path = core.BASE / str(ph["rel"])
                if path.exists():
                    try:
                        p0.add_run().add_picture(str(path), width=Cm(5.2))
                        added = True
                    except Exception:
                        pass
            if not added:
                _cell_text(c, "—", 9, align=WD_ALIGN_PARAGRAPH.CENTER)
        _widths(t, [1.0, 9.4, 6.8])
        _margins(t, 30, 30, 40, 40)
    else:
        _para(doc, "Дефекты не зафиксированы.", 10)

    doc.add_paragraph()
    _signatures(doc, comp, {"number": f"{object_id}-ДВ", "pdate": date.today().isoformat()}, signer)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
