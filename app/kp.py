# -*- coding: utf-8 -*-
"""Коммерческие предложения: прайс НИЦ СМК, гос-формы и документ."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Mm, Pt

from . import core
from .docs import _cell_text, _margins, _para, _set_run, _shade, _widths, ru_date
from .protocol_docs import _asset, _footer, _header
from .weekly_report import _gold_line

PRICE_FILE = core.BASE.parent / "РАБОЧАЯ" / "КП" / "РАЗНЫЕ" / "КП НИЦ СМК 2026 (актуальное).xls"

COMPANIES = {
    "nic": {"name": "ООО «НИЦ СМК»", "full_name": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "
            "«НАУЧНО-ИСПЫТАТЕЛЬНЫЙ ЦЕНТР СТРОИТЕЛЬНЫХ МАТЕРИАЛОВ И КОНСТРУКЦИЙ»",
            "number_mask": "КП-{year}-{n:03d}"},
    "ing": {"name": "ООО «Инжиниринг Лаб»", "full_name": "ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "
            "«Инжиниринг Лаб»",
            "address": "РФ, 107143, г. Москва, ул. Вербная, д. 6, стр. 6, пом. 6/105",
            "phone": "+7 (499) 390-24-43", "email": "info@lab-eng.ru",
            "ogrn": "5177746091056", "inn": "9729156411", "kpp": "771801001",
            "accreditation": "Свидетельство об аккредитации № ИЛ-ЛРИ-01292",
            "number_mask": "{n}"},
    "loft": {"name": "ООО «ЛОФТ»", "full_name": "ООО «ЛОФТ»",
             "number_mask": "КП.{n}"},
}

TYPES = {
    "commercial": "Коммерческое (по прайсу)",
    "ab": "Госзакупка — АБ",
    "euro": "Госзакупка — АБ ЕВРО",
    "sk": "Госзакупка — СК",
}


def _num(v: str) -> float:
    s = str(v or "").replace(" ", "").replace(",", ".")
    m = re.search(r"\d+(?:\.\d+)?", s)
    return float(m.group(0)) if m else 0.0


def import_price() -> int:
    import xlrd
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS kp_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, gost TEXT,
        unit TEXT, price REAL, note TEXT, section TEXT)""")
    con.execute("DELETE FROM kp_services")
    wb = xlrd.open_workbook(str(PRICE_FILE))
    sh = wb.sheet_by_name("текст")
    section = ""
    added = 0
    for r in range(1, sh.nrows):
        row = [str(sh.cell_value(r, c)).strip() for c in range(min(sh.ncols, 5))]
        code, name, gost, unit, price = (row + [""] * 5)[:5]
        if not name:
            continue
        if re.match(r"^[IVX]+\.", name) or (not code and name.isupper()):
            section = name
            continue
        if not re.match(r"^\d+(\.\d+)*$", code):
            continue
        note = "от" if price.lower().startswith("от") else ""
        con.execute("INSERT INTO kp_services(code,name,gost,unit,price,note,section)"
                    " VALUES (?,?,?,?,?,?,?)",
                    (code, name, gost, unit, _num(price), note, section))
        added += 1
    con.commit()
    con.close()
    return added


def services() -> list[dict]:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS kp_services (
        id INTEGER PRIMARY KEY AUTOINCREMENT, code TEXT, name TEXT, gost TEXT,
        unit TEXT, price REAL, note TEXT, section TEXT)""")
    rows = [dict(r) for r in con.execute(
        "SELECT id,code,name,gost,unit,price,note,section FROM kp_services ORDER BY id").fetchall()]
    con.close()
    return rows


def _money(v: float) -> str:
    return f"{v:,.2f}".replace(",", " ").replace(".", ",")


def company_for(key: str) -> dict:
    base = dict(core.company())
    c = dict(COMPANIES.get(key or "nic", COMPANIES["nic"]))
    if key in (None, "", "nic"):
        return base
    out = {"logo": "", "signature": "", "stamp": ""}
    out.update(c)
    out.setdefault("lab_head", base.get("lab_head") or "")
    return out


def next_number(company: str) -> str:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS kp (
        id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE, kdate TEXT,
        customer TEXT, object TEXT, total REAL DEFAULT 0, file TEXT, items TEXT,
        type TEXT DEFAULT 'commercial', eisc TEXT, request_date TEXT, valid_until TEXT,
        company TEXT DEFAULT 'nic')""")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(kp)")}
    if "company" not in cols:
        con.execute("ALTER TABLE kp ADD COLUMN company TEXT DEFAULT 'nic'")
    con.commit()
    mx = 0
    for r in con.execute("SELECT number FROM kp WHERE company=?", (company,)).fetchall():
        nums = re.findall(r"(\d+)\s*$", str(r["number"]))
        if nums:
            mx = max(mx, int(nums[-1]))
    con.close()
    mask = COMPANIES.get(company, COMPANIES["nic"]).get("number_mask", "КП-{year}-{n:03d}")
    return mask.format(year=date.today().year, n=mx + 1)


def build(record: dict, out_path: Path) -> Path:
    comp = company_for(record.get("company") or "nic")
    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(18); s.right_margin = Mm(15)
    s.top_margin = Mm(12); s.bottom_margin = Mm(14)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(10)
    _footer(doc, False, None)
    _header(doc, comp)
    _gold_line(doc)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run("КОММЕРЧЕСКОЕ ПРЕДЛОЖЕНИЕ")
    _set_run(r, 14, bold=True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(f"№ {record.get('number')} от {ru_date(record.get('date') or date.today().isoformat())}")
    _set_run(r, 10.5, bold=True)

    kind = record.get("type") or "commercial"
    info = [("Получатель", record.get("customer") or "—"),
            ("Объект / адрес", record.get("object") or "—")]
    if record.get("person"):
        info.append(("Контактное лицо", record["person"]))
    if record.get("phone"):
        info.append(("Телефон", record["phone"]))
    if kind != "commercial":
        if record.get("eisc"):
            info.append(("Запрос ЕИС", record["eisc"]))
        if record.get("request_date"):
            info.append(("Дата запроса", ru_date(record["request_date"])))
        if record.get("valid_until"):
            info.append(("Срок действия КП", "до " + ru_date(record["valid_until"])))
    t = doc.add_table(rows=len(info), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(info):
        _cell_text(t.rows[i].cells[0], k, 9, bold=True)
        _shade(t.rows[i].cells[0], "F7F3E6")
        _cell_text(t.rows[i].cells[1], str(v), 9)
    _widths(t, [4.8, 12.4])
    _margins(t, 40, 40, 60, 60)

    text = ("В ответ на Ваш запрос направляем стоимость работ по испытаниям и обследованию:"
            if kind == "commercial" else
            "В ответ на запрос ценовой информации направляем стоимость работ:")
    _para(doc, text, 9.5)

    items = record.get("items") or []
    cols = 6
    t = doc.add_table(rows=1, cols=cols)
    t.style = "Table Grid"
    heads = ("№", "Наименование услуги", "Ед.", "Кол-во", "Цена, руб.", "Сумма, руб.")
    for i, h in enumerate(heads):
        _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    total = 0.0
    for i, it in enumerate(items, 1):
        qty = float(it.get("qty") or 0)
        price = float(it.get("price") or 0)
        summ = qty * price
        total += summ
        cells = t.add_row().cells
        _cell_text(cells[0], str(i), 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(cells[1], it.get("name") or "", 8.5)
        _cell_text(cells[2], it.get("unit") or "", 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(cells[3], f"{qty:g}", 8.5, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(cells[4], _money(price), 8.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
        _cell_text(cells[5], _money(summ), 8.5, align=WD_ALIGN_PARAGRAPH.RIGHT)
    _widths(t, [0.8, 8.4, 1.6, 1.6, 2.4, 2.6])
    _margins(t, 25, 25, 40, 40)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_before = Pt(8)
    label = "Общая цена контракта:" if kind == "sk" else "Итого:"
    r = p.add_run(f"{label} {_money(total)} руб.")
    _set_run(r, 11, bold=True)

    tail = ("Цена предложения включает все налоги и сборы. Срок действия предложения — 30 календарных дней."
            if kind == "commercial" else
            "Цена предложения включает все налоги и сборы. Предложение действительно в течение срока, "
            "указанного в запросе.")
    _para(doc, tail, 9.5)

    doc.add_paragraph()
    t = doc.add_table(rows=2, cols=3)
    for row in t.rows:
        for c in row.cells:
            c.vertical_alignment = 1
    _cell_text(t.cell(0, 0), "Руководитель", 9)
    p = t.cell(0, 1).paragraphs[0]; p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sig = _asset(comp.get("signature") or "")
    if sig:
        try:
            p.add_run().add_picture(str(sig), width=Cm(3.0))
        except Exception:
            pass
    _cell_text(t.cell(0, 2), comp.get("lab_head") or "", 9, align=WD_ALIGN_PARAGRAPH.CENTER)
    _cell_text(t.cell(1, 1), "(подпись)", 8, align=WD_ALIGN_PARAGRAPH.CENTER)
    _widths(t, [5.5, 6.5, 5.2])

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
