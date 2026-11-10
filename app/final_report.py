# -*- coding: utf-8 -*-
"""Итоговый отчёт по строительному контролю (по образцу «Талаги»)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Mm, Pt

from . import ai, core, ks2, storage
from .docs import _cell_text, _margins, _para, _set_run, _shade, _widths, ru_date
from .protocol_docs import _footer, _header, _signatures
from .weekly_report import _crop_cover, _gold_line, _kpi_table, _photo
from . import weekly_report


def _num(x: float) -> str:
    s = f"{x:.2f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def _h(doc, text: str, size=11):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run(text)
    _set_run(r, size, bold=True)


def build(object_id: int, out_path: Path, signer: dict | None = None) -> Path:
    comp = core.company()
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    protocols = [dict(r) for r in con.execute(
        "SELECT number,pdate,kind FROM protocols WHERE object_name LIKE ? ORDER BY pdate",
        (f"%{(obj['name'] if obj else '')[:40]}%",))]
    con.close()
    if not obj:
        raise ValueError("Объект не найден")
    o = dict(obj)
    works = ks2.period_works(object_id, "", date.today().isoformat())
    all_docs = storage.files(object_id, "docs")
    passports = [d for d in all_docs if any(
        k in d["name"].lower() for k in ("паспорт", "сертификат", "декларац", "свидетельств"))]
    docs = all_docs[:24]
    acts = [f for f in storage.files(object_id, "acts")]
    photos = [f for f in storage.files(object_id, "photos")][:10]
    con = core.connect()
    entries = [dict(r) for r in con.execute(
        "SELECT * FROM entries WHERE object_id=? ORDER BY edate DESC LIMIT 60", (object_id,))]
    con.close()
    defects = [e for e in entries if "дефект" in (e.get("tags") or "").lower()]
    for e in entries:
        try:
            e["photos"] = json.loads(e.get("photos") or "[]") if isinstance(e.get("photos"), str) else (e.get("photos") or [])
        except Exception:
            e["photos"] = []

    payload = ai.build_final_payload(object_id)

    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(15); s.right_margin = Mm(15)
    s.top_margin = Mm(10); s.bottom_margin = Mm(12)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(10)
    _footer(doc, False, None)

    # ---------------- обложка ----------------
    _header(doc, comp)
    _gold_line(doc)
    city = (o.get("city") or "").strip()
    if not city:
        import re as _re
        m = _re.search(r"г\.\s*([А-ЯЁ][а-яё-]+)", o.get("address") or "")
        city = m.group(1) if m else ""
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    r = p.add_run(f"г. {city} · {date.today().year} г." if city else f"{date.today().year} г.")
    _set_run(r, 9, color=weekly_report.GREY)

    t = doc.add_table(rows=1, cols=2)
    weekly_report._no_borders(t)
    bar, txt = t.rows[0].cells
    _shade(bar, weekly_report.GOLD)
    titles = [
        ("ИТОГОВЫЙ ОТЧЕТ ПО СТРОИТЕЛЬНОМУ КОНТРОЛЮ", 8, True, weekly_report.GOLD),
        (f"Сезон {date.today().year} года", 20, True, "111111"),
        (f"за период {ru_date(o.get('report_start') or '')} – {ru_date(date.today().isoformat())}"
         if o.get("report_start") else f"на {ru_date(date.today().isoformat())}", 12, True, "111111"),
        (o.get("object_title") or o["name"], 9, False, weekly_report.GREY),
    ]
    first = True
    for text, size, bold, color in titles:
        pp = txt.paragraphs[0] if first else txt.add_paragraph()
        first = False
        pp.paragraph_format.space_after = Pt(2)
        pp.paragraph_format.left_indent = Cm(0.28)
        rr = pp.add_run(text)
        _set_run(rr, size, bold=bold, color=color)
    _widths(t, [0.18, 17.2])
    _margins(t, 0, 0, 0, 0)

    cover = ""
    if photos:
        cover = str(core.BASE / photos[0]["rel"])
    elif entries and entries[0]["photos"]:
        cover = entries[0]["photos"][0].get("path") or ""
    if cover and Path(cover).exists():
        _photo(doc, _crop_cover(cover), 17.2, "")

    rows = [("ЗАКАЗЧИК", o.get("customer") or "—"),
            ("ПОДРЯДЧИК", o.get("contractor") or "—"),
            ("КОНТРАКТ НА СК", o.get("contract") or "—"),
            ("ИСПОЛНИТЕЛЬ СК", comp.get("executor") or comp.get("name", ""))]
    t = doc.add_table(rows=len(rows), cols=2)
    weekly_report._no_borders(t)
    for i, (k, v) in enumerate(rows):
        c0, c1 = t.rows[i].cells
        _cell_text(c0, k, 8, bold=True)
        for par in c0.paragraphs:
            for run in par.runs:
                run.font.color.rgb = weekly_report.RGBColor.from_string(weekly_report.GOLD)
        _cell_text(c1, v, 9)
    _widths(t, [4.2, 13.2])
    _margins(t, 50, 50, 0, 0)

    _kpi_table(doc, [
        {"value": str(len(works)), "label": "видов работ"},
        {"value": str(len(protocols)), "label": "протоколов испытаний"},
        {"value": str(len(docs)), "label": "документов ИД"},
        {"value": str(len(defects)), "label": "замечаний", "green": not defects},
    ])
    doc.add_paragraph().add_run().add_break(weekly_report.WD_BREAK.PAGE)

    # ---------------- 1. общие сведения ----------------
    p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(6)
    rr = p.add_run(f"{comp.get('name','')} · Итоговый отчет по СК · {o['name']}")
    _set_run(rr, 8, color=weekly_report.GREY)
    _h(doc, "1. ОБЩИЕ СВЕДЕНИЯ")
    info = [("Объект", o.get("object_title") or o["name"]),
            ("Адрес", o.get("address") or "—"),
            ("Заказчик", o.get("customer") or "—"),
            ("Подрядчик", o.get("contractor") or "—"),
            ("Контракт на СК", o.get("contract") or "—"),
            ("Исполнитель СК", comp.get("executor") or comp.get("name", "")),
            ("Период отчета", f"{ru_date(o.get('report_start'))} – {ru_date(date.today().isoformat())}"
             if o.get("report_start") else "на " + ru_date(date.today().isoformat()))]
    t = doc.add_table(rows=len(info), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(info):
        _cell_text(t.rows[i].cells[0], k, 9, bold=True)
        _shade(t.rows[i].cells[0], "F5F1E4")
        _cell_text(t.rows[i].cells[1], v, 9)
    _widths(t, [4.6, 12.8])
    _margins(t, 40, 40, 60, 60)
    if payload.get("intro"):
        doc.add_paragraph()
        _para(doc, payload["intro"], 10)

    # ---------------- 2. нормативная база ----------------
    _h(doc, "2. НОРМАТИВНАЯ БАЗА")
    norms = ["СП 48.13330.2019 — организация строительства",
             "СП 78.13330.2012 — автомобильные дороги",
             "СП 45.13330.2017 — земляные сооружения, основания и фундаменты",
             "СП 63.13330.2018 — бетонные и железобетонные конструкции",
             "СП 71.13330.2017 — изоляционные и отделочные покрытия",
             "ГОСТ 9128-2013 — смеси асфальтобетонные",
             "ГОСТ 12801-98 — материалы на основе органических вяжущих",
             "ГОСТ 10180-2012 — бетоны, методы определения прочности",
             "ГОСТ 28570-2019 — прочность бетона по кернам",
             "ГОСТ 22690-2015 — неразрушающий контроль прочности бетона"]
    for n in norms:
        _para(doc, "• " + n, 9.5)

    # ---------------- 3. объёмы ----------------
    _h(doc, "3. ОБЪЁМЫ ВЫПОЛНЕННЫХ РАБОТ")
    if works:
        t = doc.add_table(rows=1, cols=5)
        t.style = "Table Grid"
        for i, h in enumerate(("№", "Вид работ", "Ед. изм.", "По актам", "% от договора")):
            _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for i, w in enumerate(works[:40], 1):
            cells = t.add_row().cells
            _cell_text(cells[0], str(i), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[1], w["name"], 8.5)
            _cell_text(cells[2], w["unit"], 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[3], _num(w["total"]), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[4], (f"{w['pct']:.0f} %" if w.get("pct") else "—"), 8.5,
                       align=WD_ALIGN_PARAGRAPH.CENTER)
        _widths(t, [0.8, 9.0, 2.2, 2.8, 2.8])
        _margins(t, 25, 25, 40, 40)
    else:
        _para(doc, "Объёмы не загружены: нет актов КС-2 в папке объекта.", 9.5)
    if payload.get("works"):
        doc.add_paragraph()
        _para(doc, payload["works"], 10)

    # ---------------- 3А. график ----------------
    con = core.connect()
    months = [dict(r) for r in con.execute(
        "SELECT substr(act_date,1,7) m, COUNT(DISTINCT name) c, SUM(qty) q "
        "FROM object_works WHERE object_id=? AND act_no<>'ДОГОВОР' AND act_date<>'' "
        "GROUP BY substr(act_date,1,7) ORDER BY m", (object_id,))]
    con.close()
    if months:
        _h(doc, "3А. ГРАФИК ВЫПОЛНЕНИЯ РАБОТ")
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        for i, h in enumerate(("Месяц", "Видов работ", "Объём по актам")):
            _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for m in months:
            cells = t.add_row().cells
            _cell_text(cells[0], m["m"], 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[1], str(m["c"]), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[2], _num(m["q"] or 0), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        _widths(t, [5.0, 5.0, 6.0])
        _margins(t, 25, 25, 40, 40)

    # ---------------- 4. ИД ----------------
    _h(doc, "4. ИСПОЛНИТЕЛЬНАЯ ДОКУМЕНТАЦИЯ")
    if docs:
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        for i, h in enumerate(("№", "Документ", "Дата")):
            _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for i, d in enumerate(docs[:20], 1):
            cells = t.add_row().cells
            _cell_text(cells[0], str(i), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[1], d["name"], 8.5)
            _cell_text(cells[2], ru_date(d.get("added_at") or ""), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        _widths(t, [0.8, 12.6, 3.2])
        _margins(t, 25, 25, 40, 40)
    else:
        _para(doc, "Исполнительная документация в папке объекта не обнаружена.", 9.5)

    # ---------------- 5. испытания ----------------
    _h(doc, "5. РЕЗУЛЬТАТЫ ИСПЫТАНИЙ")
    if protocols:
        t = doc.add_table(rows=1, cols=3)
        t.style = "Table Grid"
        for i, h in enumerate(("№ протокола", "Дата", "Вид испытания")):
            _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for pr in protocols[:20]:
            cells = t.add_row().cells
            _cell_text(cells[0], str(pr["number"]), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[1], ru_date(pr.get("pdate") or ""), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[2], core.DOC_KINDS.get(pr.get("kind"), {}).get("label", pr.get("kind") or ""), 8.5)
        _widths(t, [3.2, 3.2, 10.2])
        _margins(t, 25, 25, 40, 40)
    else:
        _para(doc, "Протоколы испытаний по объекту не найдены.", 9.5)
    if payload.get("tests"):
        doc.add_paragraph()
        _para(doc, payload["tests"], 10)

    # ---------------- 5а. паспорта ----------------
    _h(doc, "5А. ПАСПОРТА И СЕРТИФИКАТЫ МАТЕРИАЛОВ")
    if payload.get("passports"):
        _para(doc, payload["passports"], 10)
    if passports:
        tt = doc.add_table(rows=1, cols=3)
        tt.style = "Table Grid"
        for i, h in enumerate(("№", "Документ", "Дата")):
            _cell_text(tt.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        for i, d in enumerate(passports[:15], 1):
            cells = tt.add_row().cells
            _cell_text(cells[0], str(i), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
            _cell_text(cells[1], d["name"], 8.5)
            _cell_text(cells[2], ru_date(d.get("added_at") or ""), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        _widths(tt, [0.8, 12.6, 3.2])
        _margins(tt, 25, 25, 40, 40)

    # ---------------- 6. замечания ----------------
    _h(doc, "6. ЗАМЕЧАНИЯ И ПРЕДПИСАНИЯ")
    if payload.get("defects"):
        _para(doc, payload["defects"], 10)
    if defects:
        for i, d in enumerate(defects[:10], 1):
            _para(doc, f"{i}. {ru_date(d['edate'])} — {d.get('comment') or ''}", 9.5)
    else:
        _para(doc, "Замечаний и предписаний не зафиксировано.", 9.5)

    # ---------------- 7. фото ----------------
    if photos or any(e["photos"] for e in entries):
        doc.add_paragraph().add_run().add_break(weekly_report.WD_BREAK.PAGE)
        _h(doc, "7. ФОТОФИКСАЦИЯ")
        t = doc.add_table(rows=0, cols=2)
        weekly_report._no_borders(t)
        pics = []
        for p in photos:
            pics.append({"path": str(core.BASE / p["rel"]), "caption": ""})
        for e in entries:
            for ph in e["photos"][:2]:
                pics.append({"path": ph.get("path") or "", "caption": ph.get("caption") or ""})
        pics = [p for p in pics if p["path"] and Path(p["path"]).exists()][:8]
        for i in range(0, len(pics), 2):
            row = t.add_row()
            for j in range(2):
                cell = row.cells[j]
                pp = cell.paragraphs[0]
                pp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if i + j < len(pics):
                    item = pics[i + j]
                    try:
                        pp.add_run().add_picture(item["path"], width=Cm(8.2))
                    except Exception:
                        pass
                    if item.get("caption"):
                        cap = cell.add_paragraph()
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap.paragraph_format.space_after = Pt(4)
                        r = cap.add_run(item["caption"])
                        _set_run(r, 8, italic=True)
        _widths(t, [8.5, 8.5])

    # ---------------- 8. заключение ----------------
    _h(doc, "8. ЗАКЛЮЧЕНИЕ")
    if payload.get("conclusion"):
        _para(doc, payload["conclusion"], 10)
    concl = ("Строительный контроль на объекте выполнялся в соответствии с договором. "
             "Выполненные работы соответствуют проектной документации и требованиям нормативных документов. "
             if not defects else
             "В ходе строительного контроля выявлены замечания, указанные в разделе 6; "
             "их устранение подлежит подтверждению. ")
    _para(doc, concl, 10)
    _h(doc, "9. ПРИЛОЖЕНИЯ")
    apps = [f"1. Протоколы испытаний — {len(protocols)} шт.",
            f"2. Исполнительная документация — {len(docs)} док.",
            f"3. Акты КС-2 — {len(acts)} шт.",
            f"4. Фотоматериалы — {len(photos)} шт.",
            f"5. Дефектная ведомость — {len(defects)} записей."]
    for a in apps:
        _para(doc, a, 9.5)
    doc.add_paragraph()
    _signatures(doc, comp, {"number": f"ИТ-{object_id}", "pdate": date.today().isoformat()}, signer)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
