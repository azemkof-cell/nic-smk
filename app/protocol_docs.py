# -*- coding: utf-8 -*-
"""Протоколы испытаний в стиле реальных документов НИЦ СМК (по PDF №2855.11/26)."""
from __future__ import annotations

from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt

from . import asphalt, core
from .docs import (_cell_text, _margins, _para, _set_run, _shade, _widths, ru_date)

FONT = "Times New Roman"
BODY = 10


def _asset(path: str) -> Path | None:
    if not path:
        return None
    q = Path(path)
    if not q.is_absolute():
        for base in (core.BASE, core.BASE / "data" / "files", core.BASE / "data" / "branding"):
            cand = base / q
            if cand.exists():
                return cand
        return None
    return q if q.exists() else None


def _line(doc, width_cm=18.0):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "10")
    bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "000000")
    pbdr.append(bottom)
    pPr.append(pbdr)


def _header(doc, comp: dict):
    t = doc.add_table(rows=1, cols=2)
    t.autofit = False
    _flat(t)
    left, right = t.rows[0].cells
    left.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    logo = _asset(comp.get("logo") or "")
    lp = left.paragraphs[0]
    lp.paragraph_format.space_after = Pt(0)
    if logo:
        try:
            lp.add_run().add_picture(str(logo), width=Cm(6.4))
        except Exception:
            pass
    right.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    lines = [
        (comp.get("full_name", ""), True),
        (comp.get("address", ""), False),
        (f"ОГРН {comp.get('ogrn','')} ИНН {comp.get('inn','')} КПП {comp.get('kpp','')}".strip(), False),
        (f"тел. {comp.get('phone','')}, email: {comp.get('email','')}", False),
        (f"Аттестат аккредитации {comp.get('accreditation','')}", False),
    ]
    first = True
    for text, bold in lines:
        if not text.strip():
            continue
        p = right.paragraphs[0] if first else right.add_paragraph()
        first = False
        p.paragraph_format.space_after = Pt(0)
        p.paragraph_format.line_spacing = 1.0
        r = p.add_run(text)
        _set_run(r, 8.5 if bold else 9, bold=bold)
    _widths(t, [6.8, 11.0])
    _margins(t, 0, 0, 0, 40)
    _line(doc)


def _flat(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblPr.append(borders)


def _req(doc, label: str, value: str, size=BODY):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(1)
    p.paragraph_format.line_spacing = 1.05
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(label + ": ")
    _set_run(r, size, bold=True)
    r = p.add_run(value or "—")
    _set_run(r, size)
    return p


def _section(doc, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(text)
    _set_run(r, BODY + 0.5, bold=True)


def _table(doc, headers: list[str], rows: list[list[str]], widths: list[float],
           header_size=8.5, size=8.5, aligns: list[str] | None = None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for i, h in enumerate(headers):
        _cell_text(t.rows[0].cells[i], h, header_size, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    for row in rows:
        cells = t.add_row().cells
        for i, v in enumerate(row):
            al = WD_ALIGN_PARAGRAPH.CENTER
            if aligns and i < len(aligns) and aligns[i] == "left":
                al = WD_ALIGN_PARAGRAPH.LEFT
            _cell_text(cells[i], v, size, align=al)
    _widths(t, widths)
    _margins(t, 15, 15, 30, 30)
    return t


def fmt_number(number, kind: str, pdate) -> str:
    """2855 -> 2855.11/26 (код вида испытания и год), если код задан в настройках."""
    comp = core.company()
    code = str(comp.get("code_" + kind, "") or "").strip()
    if not code:
        return str(number)
    year = ""
    try:
        y = str(pdate or "")[:4]
        year = y[2:] if len(y) == 4 else ""
    except Exception:
        year = ""
    return f"{number}.{code}/{year}" if year else f"{number}.{code}"


def _signatures(doc, comp: dict, data: dict, signer: dict | None = None):
    people = [
        (comp.get("signer1_pos", "Главный специалист"), comp.get("signer1", "Стрючкова К.И."),
         comp.get("signer1_img", "data/branding/sign_stryuchkova.png")),
        (comp.get("signer2_pos", "Руководитель лаборатории"), comp.get("signer2", "Бунин Н.И."),
         comp.get("signer2_img", "data/branding/sign_bunin.png")),
    ]
    if signer and signer.get("name"):
        people[0] = (signer.get("pos") or "Инженер строительного контроля",
                     signer.get("name"), signer.get("img") or people[0][2])
    t = doc.add_table(rows=4, cols=4)
    _flat(t)
    stamp = _asset(comp.get("stamp") or "data/branding/stamp.png")

    for i, (pos, name, img) in enumerate(people):
        r0, r1 = i * 2, i * 2 + 1
        c_pos, c_sign, c_name = t.cell(r0, 0), t.cell(r0, 1), t.cell(r0, 2)
        c_cap = t.cell(r1, 1)
        for c in (c_pos, c_sign, c_name, c_cap):
            c.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
        _cell_text(c_pos, pos, BODY)
        sp = c_sign.paragraphs[0]
        sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
        sp.paragraph_format.space_after = Pt(0)
        sign = _asset(img)
        if sign:
            try:
                sp.add_run().add_picture(str(sign), width=Cm(3.0))
            except Exception:
                pass
        _cell_text(c_name, name, BODY, align=WD_ALIGN_PARAGRAPH.LEFT)
        _cell_text(c_cap, "(подпись)", 8, align=WD_ALIGN_PARAGRAPH.CENTER)

    stamp_cell = t.cell(0, 3).merge(t.cell(3, 3))
    stamp_cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    sp = stamp_cell.paragraphs[0]
    sp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    sp.paragraph_format.space_after = Pt(0)
    if stamp:
        try:
            sp.add_run().add_picture(str(stamp), width=Cm(4.4))
        except Exception:
            pass
    mp = stamp_cell.add_paragraph()
    mp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    mp.paragraph_format.space_before = Pt(0)
    r = mp.add_run("М.П.")
    _set_run(r, 9)

    _widths(t, [5.6, 3.6, 4.2, 4.4])
    _margins(t, 0, 0, 0, 0)


def _footer(doc, internal: bool, record: dict | None = None):
    sec = doc.sections[0]
    p = sec.footer.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if record:
        try:
            num = fmt_number(record.get("number"), record.get("kind", ""), record.get("pdate"))
        except Exception:
            num = record.get("number", "")
        r = p.add_run(f"ЭКСПЕРТНОЕ ЗАКЛЮЧЕНИЕ №{num}   ·   ")
        _set_run(r, 8, color="555555")
    if internal:
        r = p.add_run("Внутренний экземпляр · ")
        _set_run(r, 8, color="808080")
    r = p.add_run("Страница ")
    _set_run(r, 8, color="555555")
    _field(p, "PAGE")
    r = p.add_run(" из ")
    _set_run(r, 8, color="555555")
    _field(p, "NUMPAGES")


def _field(p, instr):
    run = p.add_run()
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = "1"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    run._r.append(f1); run._r.append(it); run._r.append(f2); run._r.append(t); run._r.append(f3)
    _set_run(run, 8, color="555555")


def _watermark(doc):
    hdr = doc.sections[0].header
    p = hdr.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Ч Е Р Н О В И К")
    _set_run(r, 30, bold=True, color="D0D0D0")
    p2 = hdr.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run("сформирован автоматически · требует проверки специалистом")
    _set_run(r2, 7, color="AAAAAA")


TITLE = {
    "asphalt": "ПРОТОКОЛ ИСПЫТАНИЙ АСФАЛЬТОБЕТОННОЙ СМЕСИ",
    "concrete": "ПРОТОКОЛ ИСПЫТАНИЙ БЕТОНА",
    "soil": "ПРОТОКОЛ ИСПЫТАНИЙ ГРУНТА",
    "rebar": "ПРОТОКОЛ ИСПЫТАНИЙ СВАРНЫХ СОЕДИНЕНИЙ",
    "asphalt_euro": "ПРОТОКОЛ ИСПЫТАНИЙ АСФАЛЬТОБЕТОННОЙ СМЕСИ (ЕВРО)",
    "concrete_ndt": "ПРОТОКОЛ ИСПЫТАНИЙ БЕТОНА (НЕРАЗРУШАЮЩИЙ КОНТРОЛЬ)",
    "soil_proctor": "ПРОТОКОЛ ИСПЫТАНИЙ ГРУНТА (МАКСИМАЛЬНАЯ ПЛОТНОСТЬ)",
}

ND_PRODUCT = {
    "asphalt": "ГОСТ 58406.2-2020",
    "concrete": "ГОСТ 26633-2015",
    "soil": "ГОСТ 25100-2020",
    "rebar": "ГОСТ 14098-91, ГОСТ 10922-2012",
    "asphalt_euro": "EN 13108-1",
    "concrete_ndt": "ГОСТ 22690-2015",
    "soil_proctor": "ГОСТ 22733-2016",
}
ND_METHOD = {
    "asphalt": "ГОСТ 12801-98",
    "concrete": "ГОСТ 10180-2012",
    "soil": "ГОСТ 5180-2015, ГОСТ 22733-2016",
    "rebar": "ГОСТ 10922-2012",
    "asphalt_euro": "EN 12697",
    "concrete_ndt": "ГОСТ 22690-2015",
    "soil_proctor": "ГОСТ 5180-2015, ГОСТ 22733-2016",
}

SAMPLE = {
    "concrete": "Образцы-кубы бетона",
    "soil": "Проба грунта",
    "rebar": "Контрольные образцы сварных соединений",
    "asphalt_euro": "Образцы асфальтобетонной смеси (евро)",
    "concrete_ndt": "Конструкция бетонная (неразрушающий контроль)",
    "soil_proctor": "Проба грунта (прибор СоюздорНИИ)",
}


def build(record: dict, calc: dict | None, out_path: Path, signer: dict | None = None) -> Path:
    comp = core.company()
    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(15); s.right_margin = Mm(12)
    s.top_margin = Mm(10); s.bottom_margin = Mm(12)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    if record.get("draft"):
        _watermark(doc)
    _footer(doc, bool(record.get("internal")), record)

    _header(doc, comp)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(TITLE.get(record["kind"], "ПРОТОКОЛ ИСПЫТАНИЙ"))
    _set_run(r, 12, bold=True)

    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(6)
    r = p.add_run(f"№{fmt_number(record['number'], record['kind'], record.get('pdate'))} "
                  f"от {ru_date(record.get('pdate'))}")
    _set_run(r, 11, bold=True)

    kind = record["kind"]
    meta = record.get("meta") or {}
    if kind == "asphalt":
        _asphalt_body(doc, record, meta)
    else:
        _generic_body(doc, record, meta, calc or {})

    _signatures(doc, comp, record, signer)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def _asphalt_body(doc, record, meta):
    data = asphalt.calc(meta)
    _req(doc, "Заказчик", meta.get("customer", ""))
    if meta.get("customer_address"):
        _req(doc, "Юридический адрес", meta["customer_address"])
    _req(doc, "Наименование объекта", meta.get("object_name", ""))
    _req(doc, "Подрядчик", meta.get("contractor", ""))
    _req(doc, "Наименование материала", meta.get("material", ""))
    _req(doc, "Назначение", meta.get("purpose", ""))
    _req(doc, "Дата отбора пробы", meta.get("sampled_at") or ru_date(record.get("pdate")))
    _req(doc, "Акт отбора проб", f"№{fmt_number(record.get('act_no'), record['kind'], record.get('pdate'))}" if record.get("act_no") else "—")
    _req(doc, "Лабораторный № пробы", f"№{fmt_number(record.get('lab_no'), record['kind'], record.get('pdate'))}" if record.get("lab_no") else "—")
    _req(doc, "Производитель материала", meta.get("manufacturer", ""))
    _req(doc, "Утвержденный рецепт на а/б смесь", meta.get("recipe", ""))
    _req(doc, "НД на продукцию", meta.get("nd") or asphalt.ND)
    _req(doc, "НД, регламентирующие объем лабораторных исследований и их оценку",
         (meta.get("nd") or asphalt.ND) + ", ГОСТ 12801-98")
    _req(doc, "Испытательное оборудование", meta.get("equipment") or asphalt.EQUIPMENT)
    _req(doc, "Условия в помещении при проведении испытаний", meta.get("conditions") or asphalt.CONDITIONS)

    _section(doc, "Результаты испытания")
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("1. Зерновой состав")
    _set_run(r, BODY, bold=True)

    rows = []
    for g in data["grain"]:
        rows.append([g["sieve"], g["gost"], g["recipe"], g["pdo"], g["fact"], g["dev"]])
    _table(doc,
           ["Размер сит, мм", "Требования ГОСТ 58406.2-2020, %", "Рецепт, %",
            "ПДО, %", "Факт, %", "Отклонение, %"],
           rows, [2.0, 5.0, 2.6, 2.4, 2.6, 3.0])

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("2. Физические показатели")
    _set_run(r, BODY, bold=True)
    rows = [[x["name"], x["norm"], x["recipe"], x["pdo"], x["fact"]] for x in data["physical"]]
    _table(doc,
           ["Наименование показателей", "Нормативные требования", "Рецепт",
            "ПДО", "Фактическое значение"],
           rows, [6.4, 3.2, 2.8, 2.2, 3.0], aligns=["left", "center", "center", "center", "center"])

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("3. Эксплуатационные показатели")
    _set_run(r, BODY, bold=True)
    rows = [[x["name"], x["norm"], x["fact"]] for x in data["operational"]]
    _table(doc, ["Наименование показателей", "Нормативные требования", "Фактические показатели"],
           rows, [9.4, 4.4, 3.8], aligns=["left", "center", "center"])

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("4. Заключение:  ")
    _set_run(r, BODY, bold=True)
    r = p.add_run(data["conclusion"] + ".")
    _set_run(r, BODY)


DEFAULT_EQUIP = {
    "concrete": "пресс испытательный ТП-1-500 «Универсал»; штангенциркуль; весы лабораторные",
    "concrete_ndt": "ультразвуковой прибор ПУЛЬСАР-2,5; склерометр ОМШ-1",
    "soil": "прибор СоюздорНИИ; весы; сушильный шкаф",
    "soil_proctor": "прибор СоюздорНИИ; весы; сушильный шкаф",
    "rebar": "пресс испытательный; штангенциркуль",
}


def _loads(meta, key="loads"):
    raw = str(meta.get(key) or "").replace(",", ".")
    out = []
    for x in raw.replace(";", " ").split():
        try:
            out.append(float(x))
        except ValueError:
            pass
    return out


def _concrete_table(doc, record, meta):
    """Таблица как в форме «Испытание кубов бетона»: по строке на образец."""
    size = float(str(meta.get("size") or 100).replace(",", "."))
    loads = _loads(meta)
    if not loads:
        return False
    area = size * size
    k = {100: 0.95, 150: 1.0, 200: 1.05}.get(int(size), 1.0)
    norm = float(str(meta.get("norm") or 32.7).replace(",", "."))
    rows = []
    for i, f in enumerate(loads, 1):
        r = f * 1000 / area * k
        rows.append([str(i), ru_date(record.get("pdate")), str(meta.get("age") or "28"),
                     f"{size:g}×{size:g}×{size:g}", "—", "—", f"{f:.1f}".replace(".", ","),
                     f"{r:.2f}".replace(".", ","), f"{100 * r / norm:.1f}%".replace(".", ",")])
    _table(doc,
           ["№", "Дата испытаний", "Возраст, сут.", "Размер, мм", "Масса, г",
            "Плотность, г/см³", "Нагрузка, кН", "Прочность, МПа", "% от требуемой"],
           rows, [0.8, 2.6, 1.8, 3.0, 1.8, 2.2, 2.2, 2.2, 2.2],
           header_size=8, size=8.5)
    return True


def _summary(doc, calc):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("Заключение:  ")
    _set_run(r, BODY, bold=True)
    r = p.add_run(calc.get("conclusion", ""))
    _set_run(r, BODY)


def _generic_body(doc, record, meta, calc):
    _req(doc, "Заказчик", record.get("customer", ""))
    if meta.get("customer_address"):
        _req(doc, "Юридический адрес", meta["customer_address"])
    _req(doc, "Адрес участка", meta.get("place") or record.get("object_name", ""))
    if meta.get("contractor"):
        _req(doc, "Подрядчик", meta["contractor"])
    _req(doc, "Наименование объекта", record.get("object_name", ""))
    _req(doc, "Наименование образца (пробы)", meta.get("sample") or SAMPLE.get(record["kind"], ""))
    _req(doc, "Дата отбора пробы", meta.get("sampled_at", ""))
    _req(doc, "Место отбора", meta.get("place", ""))
    _req(doc, "Акт отбора проб", f"№{fmt_number(record.get('act_no'), record['kind'], record.get('pdate'))}" if record.get("act_no") else "—")
    _req(doc, "Лабораторный № пробы", f"№{fmt_number(record.get('lab_no'), record['kind'], record.get('pdate'))}" if record.get("lab_no") else "—")
    _req(doc, "НД на продукцию", meta.get("nd") or ND_PRODUCT.get(record["kind"], ""))
    _req(doc, "Методика испытаний", meta.get("nd_method") or ND_METHOD.get(record["kind"], ""))
    _req(doc, "Испытательное оборудование",
         meta.get("equipment") or DEFAULT_EQUIP.get(record["kind"], "—"))

    _section(doc, "Результаты испытаний")
    if record["kind"] == "concrete" and _concrete_table(doc, record, meta):
        _summary(doc, calc)
        return
    rows = []
    for i, r in enumerate(calc.get("rows") or [], 1):
        rows.append([str(i), r.get("name", ""), r.get("unit", ""), r.get("req", ""),
                     r.get("value", ""), "соотв." if r.get("ok") else "не соотв."])
    _table(doc, ["№", "Показатель", "Ед. изм.", "Норматив", "Факт", "Соответствие"],
           rows, [0.8, 7.6, 1.8, 3.6, 2.4, 2.6], aligns=["center", "left", "center", "center", "center", "center"])

    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("Заключение:  ")
    _set_run(r, BODY, bold=True)
    r = p.add_run(calc.get("conclusion", ""))
    _set_run(r, BODY)


TITLE.update({
    "concrete_core": "ПРОТОКОЛ ИСПЫТАНИЙ БЕТОНА (КЕРНЫ)",
    "mortar_cube": "ПРОТОКОЛ ИСПЫТАНИЙ РАСТВОРА",
    "protective_layer": "ПРОТОКОЛ КОНТРОЛЯ ЗАЩИТНОГО СЛОЯ БЕТОНА",
    "waterproofing": "ПРОТОКОЛ ИСПЫТАНИЙ ГИДРОИЗОЛЯЦИИ",
    "soil_fms_sand": "ПРОТОКОЛ ИСПЫТАНИЙ ПЕСКА (ФМС)",
    "soil_fms_soil": "ПРОТОКОЛ ИСПЫТАНИЙ ГРУНТА (ФМС)",
    "crushed_stone": "ПРОТОКОЛ ИСПЫТАНИЙ ЩЕБНЯ",
    "pdu": "ПРОТОКОЛ ИСПЫТАНИЙ ОСНОВАНИЯ (ПДУ)",
    "asphalt_core": "ПРОТОКОЛ ИСПЫТАНИЙ КЕРНОВ АСФАЛЬТОБЕТОНА",
    "asphalt_euro_core": "ПРОТОКОЛ ИСПЫТАНИЙ КЕРНОВ АСФАЛЬТОБЕТОНА (ЕВРО)",
})
ND_PRODUCT.update({
    "concrete_core": "ГОСТ 28570-2019",
    "mortar_cube": "ГОСТ 5802-86",
    "protective_layer": "СП 63.13330.2018",
    "waterproofing": "СП 71.13330.2017",
    "soil_fms_sand": "ГОСТ 8736-2014",
    "soil_fms_soil": "ГОСТ 25100-2020",
    "crushed_stone": "ГОСТ 8267-93",
    "pdu": "СП 45.13330.2017",
    "asphalt_core": "ГОСТ 9128-2013",
    "asphalt_euro_core": "EN 13108-1",
})
ND_METHOD.update({
    "concrete_core": "ГОСТ 28570-2019",
    "mortar_cube": "ГОСТ 5802-86",
    "protective_layer": "СП 63.13330.2018",
    "waterproofing": "СП 71.13330.2017",
    "soil_fms_sand": "ГОСТ 5180-2015, ГОСТ 8736-2014",
    "soil_fms_soil": "ГОСТ 5180-2015",
    "crushed_stone": "ГОСТ 8267-93, ГОСТ 8269.0-97",
    "pdu": "СП 45.13330.2017",
    "asphalt_core": "ГОСТ 12801-98",
    "asphalt_euro_core": "EN 12697-6, EN 12697-8",
})
