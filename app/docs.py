# -*- coding: utf-8 -*-
"""Формирование документов Word (.docx)."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt, RGBColor

from . import core

FONT = "Times New Roman"


# --------------------------------------------------------------------------
#  Вспомогательные функции
# --------------------------------------------------------------------------
def _set_run(run, size=11, bold=False, italic=False, color=None, font=FONT):
    run.font.name = font
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), font)


def _para(doc_or_cell, text="", size=11, bold=False, align=None, space_after=2,
          space_before=0, italic=False, color=None, first_line=None, line=1.0):
    p = doc_or_cell.add_paragraph()
    if align is not None:
        p.alignment = align
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.space_before = Pt(space_before)
    pf.line_spacing = line
    if first_line:
        pf.first_line_indent = Cm(first_line)
    if text:
        r = p.add_run(text)
        _set_run(r, size=size, bold=bold, italic=italic, color=color)
    return p


def _cell_text(cell, text, size=10, bold=False, align=WD_ALIGN_PARAGRAPH.LEFT, valign=WD_ALIGN_VERTICAL.CENTER):
    cell.vertical_alignment = valign
    p = cell.paragraphs[0]
    p.alignment = align
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.space_before = Pt(0)
    r = p.add_run(str(text) if text is not None else "")
    _set_run(r, size=size, bold=bold)


def _shade(cell, hex_color: str):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), hex_color)
    tcPr.append(shd)


def _margins(table, top=30, bottom=30, left=60, right=60):
    tblPr = table._tbl.tblPr
    mar = OxmlElement("w:tblCellMar")
    for side, val in (("top", top), ("bottom", bottom), ("left", left), ("right", right)):
        el = OxmlElement(f"w:{side}")
        el.set(qn("w:w"), str(val))
        el.set(qn("w:type"), "dxa")
        mar.append(el)
    tblPr.append(mar)


def _widths(table, widths_cm):
    table.autofit = False
    tbl = table._tbl
    tblPr = tbl.tblPr
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    tblPr.append(layout)
    for row in table.rows:
        for idx, w in enumerate(widths_cm):
            if idx < len(row.cells):
                row.cells[idx].width = Cm(w)
    for idx, w in enumerate(widths_cm):
        if idx < len(table.columns):
            table.columns[idx].width = Cm(w)


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:tblHeader")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _no_split(row):
    trPr = row._tr.get_or_add_trPr()
    el = OxmlElement("w:cantSplit")
    el.set(qn("w:val"), "true")
    trPr.append(el)


def _field(paragraph, instr: str):
    run = paragraph.add_run()
    f1 = OxmlElement("w:fldChar"); f1.set(qn("w:fldCharType"), "begin")
    it = OxmlElement("w:instrText"); it.set(qn("xml:space"), "preserve"); it.text = instr
    f2 = OxmlElement("w:fldChar"); f2.set(qn("w:fldCharType"), "separate")
    t = OxmlElement("w:t"); t.text = "1"
    f3 = OxmlElement("w:fldChar"); f3.set(qn("w:fldCharType"), "end")
    run._r.append(f1); run._r.append(it); run._r.append(f2); run._r.append(t); run._r.append(f3)
    return run


def _page_setup(doc: Document):
    s = doc.sections[0]
    s.page_width = Mm(210)
    s.page_height = Mm(297)
    s.left_margin = Mm(25)
    s.right_margin = Mm(15)
    s.top_margin = Mm(15)
    s.bottom_margin = Mm(15)
    st = doc.styles["Normal"]
    st.font.name = FONT
    st.font.size = Pt(11)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)


def _footer(doc: Document, prefix=""):
    for section in doc.sections:
        p = section.footer.paragraphs[0]
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_before = Pt(0)
        if prefix:
            r = p.add_run(prefix + "  ")
            _set_run(r, 8, color="808080")
        r = p.add_run("стр. ")
        _set_run(r, 8, color="808080")
        _field(p, "PAGE")
        r = p.add_run(" из ")
        _set_run(r, 8, color="808080")
        _field(p, "NUMPAGES")
        for r in p.runs:
            _set_run(r, 8, color="808080")


def _watermark(doc: Document):
    hdr = doc.sections[0].header
    p = hdr.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run("Ч Е Р Н О В И К")
    _set_run(r, 30, bold=True, color="D0D0D0")
    p2 = hdr.add_paragraph()
    p2.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r2 = p2.add_run("сформирован автоматически · требует проверки специалистом")
    _set_run(r2, 7, color="AAAAAA")


def _company_header(doc: Document, comp: dict, right_lines: list[str] | None = None):
    t = doc.add_table(rows=1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = "Table Grid"
    # убрать границы
    tblPr = t._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblPr.append(borders)
    left, right = t.rows[0].cells
    p = left.paragraphs[0]
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(comp.get("name", ""))
    _set_run(r, 13, bold=True)
    for line in [comp.get("accreditation", ""), comp.get("address", ""),
                 "тел.: " + comp["phone"] if comp.get("phone") else "",
                 "e-mail: " + comp["email"] if comp.get("email") else ""]:
        if not line:
            continue
        pp = left.add_paragraph()
        pp.paragraph_format.space_after = Pt(0)
        rr = pp.add_run(line)
        _set_run(rr, 8.5, color="444444")
    p = right.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p.paragraph_format.space_after = Pt(0)
    for line in (right_lines or []):
        pp = right.add_paragraph()
        pp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        pp.paragraph_format.space_after = Pt(0)
        rr = pp.add_run(line)
        _set_run(rr, 8.5, color="444444")
    _widths(t, [11.5, 5.5])
    _margins(t, 0, 0, 0, 0)
    # линия
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(6)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "1F3864")
    pbdr.append(bottom)
    pPr.append(pbdr)


def _signature_block(doc: Document, left_title: str, left_name: str, right_title: str = "", right_name: str = ""):
    t = doc.add_table(rows=2, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    a, b = t.rows[0].cells
    _cell_text(a, left_title, 10)
    a, b = t.rows[1].cells
    _cell_text(a, "______________________ / " + left_name + " /", 10)
    if right_title or right_name:
        _cell_text(t.rows[0].cells[1], "  " + right_title, 10)
        _cell_text(b, "______________________ / " + right_name + " /", 10)
    _widths(t, [9.0, 8.0])
    _margins(t, 40, 40, 0, 0)


# --------------------------------------------------------------------------
#  Протокол испытаний
# --------------------------------------------------------------------------
SAMPLE_TEXT = {
    "asphalt": "Образцы асфальтобетонной смеси (керны / вырубки), отобранные из покрытия",
    "concrete": "Образцы-кубы бетона",
    "soil": "Проба грунта",
    "rebar": "Контрольные образцы сварных соединений арматуры",
}
ND_PRODUCT = {
    "asphalt": "ГОСТ 58406.2-2020, ГОСТ 9128-2013",
    "concrete": "ГОСТ 26633-2015",
    "soil": "ГОСТ 25100-2020",
    "rebar": "ГОСТ 14098-91, ГОСТ 10922-2012",
}
ND_METHOD = {
    "asphalt": "ГОСТ 12801-98",
    "concrete": "ГОСТ 10180-2012",
    "soil": "ГОСТ 5180-2015, ГОСТ 22733-2016",
    "rebar": "ГОСТ 10922-2012",
}


def protocol_docx(record: dict, calc: dict, out_path: Path) -> Path:
    kind = record["kind"]
    meta = record.get("meta", {}) or {}
    comp = core.company()
    doc = Document()
    _page_setup(doc)
    if record.get("draft"):
        _watermark(doc)
    _footer(doc, comp.get("name", ""))

    _company_header(doc, comp, right_lines=[
        "Аттестат аккредитации",
        comp.get("accreditation", ""),
    ])

    _para(doc, "ПРОТОКОЛ ИСПЫТАНИЙ № " + str(record["number"]), 14, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_before=6, space_after=0)
    _para(doc, "от " + ru_date(record["pdate"]), 10, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)

    # 1. Общие сведения
    _para(doc, "1. ОБЩИЕ СВЕДЕНИЯ", 11, bold=True, space_before=4, space_after=4)
    info = [
        ("Заказчик", record.get("customer") or "—"),
        ("Наименование и адрес объекта", record.get("object_name") or "—"),
        ("Наименование образца (пробы)", meta.get("sample") or SAMPLE_TEXT.get(kind, "—")),
    ]
    if kind == "asphalt":
        info.append(("Тип и марка смеси", f"{meta.get('mix', 'ЩМА-16')}, марка {meta.get('mark', 'I')}"))
    if kind == "concrete":
        info.append(("Размер образцов, возраст", f"{meta.get('size', '100')}×{meta.get('size', '100')}×{meta.get('size', '100')} мм, {meta.get('age', '28')} сут."))
        info.append(("Класс бетона по проекту", str(meta.get("cls", "—"))))
    if kind == "soil":
        info.append(("Тип грунта", str(meta.get("soil", "—"))))
        info.append(("Слой / отметка отбора", str(meta.get("layer", "—"))))
    if kind == "rebar":
        info.append(("Тип соединения", f"{meta.get('joint', 'К1-Км')} (Ø{meta.get('d1', '10')} + Ø{meta.get('d2', '14')} мм)"))
        info.append(("Класс арматуры", str(meta.get("steel", "А500С"))))
    if record.get("lab_no"):
        info.append(("Лабораторный №", str(record["lab_no"])))
    if record.get("act_no"):
        info.append(("Акт отбора проб №", str(record["act_no"])))
    info += [
        ("Дата и время отбора образцов", meta.get("sampled_at") or "—"),
        ("Место отбора", meta.get("place") or "—"),
        ("НД на продукцию", ND_PRODUCT.get(kind, "—")),
        ("НД на методы испытаний", ND_METHOD.get(kind, "—")),
    ]
    t = doc.add_table(rows=len(info), cols=2)
    t.style = "Table Grid"
    for i, (k, v) in enumerate(info):
        _cell_text(t.rows[i].cells[0], k, 9.5, bold=True)
        _shade(t.rows[i].cells[0], "F2F2F2")
        _cell_text(t.rows[i].cells[1], v, 9.5)
    _widths(t, [6.0, 11.0])
    _margins(t, 30, 30, 70, 70)

    # 2. Результаты
    _para(doc, "2. РЕЗУЛЬТАТЫ ИСПЫТАНИЙ", 11, bold=True, space_before=10, space_after=4)
    rows = calc["rows"]
    t = doc.add_table(rows=1, cols=7)
    t.style = "Table Grid"
    headers = ["№", "Показатель", "Ед. изм.", "НД (пункт)", "Требование", "Результат", "Соотв."]
    for i, h in enumerate(headers):
        _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.rows[0].cells[i], "DCE6F1")
    _repeat_header(t.rows[0])
    for idx, row in enumerate(rows, 1):
        cells = t.add_row().cells
        vals = [str(idx), row["name"], row["unit"], row.get("gost", ""), row["req"], row["value"],
                "соотв." if row["ok"] else "не соотв."]
        for i, v in enumerate(vals):
            al = WD_ALIGN_PARAGRAPH.CENTER if i in (0, 2, 5, 6) else WD_ALIGN_PARAGRAPH.LEFT
            _cell_text(cells[i], v, 8.5, align=al)
            if i == 6 and not row["ok"]:
                _shade(cells[i], "FBE5E5")
    _widths(t, [0.8, 5.2, 1.5, 2.8, 2.8, 2.2, 1.7])
    _margins(t, 25, 25, 50, 50)

    _para(doc, "", 6, space_after=2)
    _para(doc, "Примечание: испытания проведены в лаборатории ООО «НИЦ СМК»; "
               "результаты относятся только к образцам, прошедшим испытания.",
          8, italic=True, color="555555")

    # 3. Заключение
    _para(doc, "3. ЗАКЛЮЧЕНИЕ", 11, bold=True, space_before=8, space_after=4)
    p = _para(doc, "", 10.5, space_after=6)
    p.paragraph_format.first_line_indent = Cm(1.0)
    r = p.add_run(calc["conclusion"])
    _set_run(r, 10.5)

    if record.get("draft"):
        p = _para(doc, "Документ сформирован в демонстрационном режиме. Числовые значения показателей "
                       "подлежат замене на фактические результаты измерений до подписания.",
                  9, italic=True, color="B00000", space_before=6)
        p.paragraph_format.first_line_indent = Cm(0)

    # 4. Подписи
    _para(doc, "4. ПОДПИСИ", 11, bold=True, space_before=10, space_after=8)
    _signature_block(doc, "Начальник испытательной лаборатории",
                     record.get("lab_head") or comp.get("lab_head", ""),
                     "Инженер-испытатель", record.get("engineer", ""))
    _para(doc, "М.П.", 9, space_before=8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


# --------------------------------------------------------------------------
#  Отчёт по контракту
# --------------------------------------------------------------------------
def ru_date(value) -> str:
    if not value:
        return "—"
    if isinstance(value, (date, datetime)):
        d = value
    else:
        s = str(value).strip()
        for f in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
            try:
                d = datetime.strptime(s, f)
                break
            except ValueError:
                continue
        else:
            return s
    months = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля",
              "августа", "сентября", "октября", "ноября", "декабря"]
    return f"{d.day:02d} {months[d.month - 1]} {d.year} г."


def period_text(d1, d2) -> str:
    return f"с {ru_date(d1)} по {ru_date(d2)}"


def report_sections(data: dict) -> list[tuple[str, str]]:
    """Текстовые блоки отчёта (без ИИ)."""
    works = data.get("works") or []
    objects = data.get("object_name") or "—"
    cname = core.company().get("name", "ООО «НИЦ СМК»")
    spec = data.get("specialist") or "специалист"
    contract = data.get("contract") or "—"
    issues = (data.get("issues") or "").strip()

    s1 = (f"В период {period_text(data.get('date_from'), data.get('date_to'))} строительный контроль "
          f"на объекте {objects} осуществлял специалист {cname} {spec}.")
    if contract and contract != "—":
        s1 += f" Работы выполнялись в рамках контракта {contract}."
    if data.get("customer"):
        s1 += f" Заказчик: {data['customer']}."

    if works:
        wl = "; ".join(
            f"{w.get('name', '')}" + (f" — {w.get('vol', '')} {w.get('unit', '')}".rstrip() if w.get("vol") else "")
            for w in works
        )
        s2 = ("За отчётный период на объекте выполнены следующие виды работ: " + wl + ".")
    else:
        s2 = "За отчётный период работы на объекте не выполнялись."

    s3 = ("При осуществлении строительного контроля проверялись: соответствие выполняемых работ проектной "
          "документации и требованиям нормативных документов; соблюдение технологии производства работ; "
          "качество применяемых материалов и изделий; соответствие объёмов фактически выполненных работ.")
    if data.get("materials"):
        s3 += " Проверены документы о качестве на применяемые материалы: " + data["materials"] + "."

    s4 = issues if issues else "Замечаний по качеству и объёмам выполненных работ не выявлено."
    s5 = ("Выполненные в отчётном периоде работы соответствуют требованиям проектной документации, "
          "СП 48.13330.2019 и условиям контракта. Строительный контроль проведён в полном объёме.")

    out = [("1. Общие сведения", s1), ("2. Перечень выполненных работ", s2),
           ("3. Результаты контроля", s3), ("4. Замечания", s4), ("5. Выводы", s5)]
    if (data.get("ai_text") or "").strip():
        out.append(("6. Дополнительные сведения", data["ai_text"].strip()))
    return out


def report_docx(record: dict, out_path: Path) -> Path:
    data = record.get("payload", {}) or {}
    comp = core.company()
    doc = Document()
    _page_setup(doc)
    _footer(doc, comp.get("name", ""))

    _company_header(doc, comp, right_lines=["", comp.get("site", "")])
    _para(doc, "", 10, space_after=20)
    _para(doc, "ОТЧЁТ № " + record["number"], 16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    _para(doc, "о результатах строительного контроля", 12, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    _para(doc, period_text(record["date_from"], record["date_to"]), 11,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=16)

    t = doc.add_table(rows=4, cols=2)
    t.style = "Table Grid"
    pairs = [("Объект", record.get("object_name", "—")),
             ("Заказчик", record.get("customer", "—")),
             ("Контракт", record.get("contract", "—")),
             ("Исполнитель", comp.get("name", ""))]
    for i, (k, v) in enumerate(pairs):
        _cell_text(t.rows[i].cells[0], k, 10, bold=True)
        _shade(t.rows[i].cells[0], "F2F2F2")
        _cell_text(t.rows[i].cells[1], v, 10)
    _widths(t, [4.0, 13.0])
    _margins(t, 50, 50, 80, 80)

    for title, body in report_sections(data):
        _para(doc, title, 11, bold=True, space_before=12, space_after=4)
        p = _para(doc, "", 10.5, space_after=4)
        p.paragraph_format.first_line_indent = Cm(1.0)
        r = p.add_run(body)
        _set_run(r, 10.5)
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    photos = data.get("photos") or []
    if photos:
        num = "7" if (data.get("ai_text") or "").strip() else "6"
        _para(doc, num + ". Фотофиксация", 11, bold=True, space_before=12, space_after=4)
        _para(doc, f"В отчётном периоде выполнена фотофиксация работ ({len(photos)} фото).",
              10.5, space_after=6)
        table = doc.add_table(rows=0, cols=2)
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        tblPr = table._tbl.tblPr
        borders = OxmlElement("w:tblBorders")
        for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
            el = OxmlElement(f"w:{edge}"); el.set(qn("w:val"), "nil"); borders.append(el)
        tblPr.append(borders)
        for i in range(0, len(photos), 2):
            row = table.add_row()
            for j in range(2):
                cell = row.cells[j]
                cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
                p0 = cell.paragraphs[0]
                p0.alignment = WD_ALIGN_PARAGRAPH.CENTER
                if i + j < len(photos):
                    ph = photos[i + j]
                    path = Path(ph.get("path", ""))
                    if path.exists():
                        run = p0.add_run()
                        try:
                            run.add_picture(str(path), width=Cm(8.0))
                        except Exception:
                            p0.add_run("[фото недоступно]")
                        cap = cell.add_paragraph()
                        cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
                        cap.paragraph_format.space_after = Pt(8)
                        txt = " · ".join(x for x in [ph.get("caption", ""), ph.get("date", "")] if x)
                        rr = cap.add_run(f"Рис. {i + j + 1}. {txt}")
                        _set_run(rr, 8, italic=True, color="444444")
        _widths(table, [8.5, 8.5])

    _para(doc, "", 8, space_after=10)
    _signature_block(doc, "Главный специалист", data.get("specialist", comp.get("lab_head", "")),
                     "", "")
    _para(doc, "М.П.", 9, space_before=8)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def doc_folder(kind_label: str) -> Path:
    y = date.today().year
    p = core.DOCS / str(y) / kind_label
    p.mkdir(parents=True, exist_ok=True)
    return p
