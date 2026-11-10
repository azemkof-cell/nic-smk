# -*- coding: utf-8 -*-
"""Отчёт строительного контроля по образцу «ОТЧЕТ №012-СК.26 БОГОЛЮБОВА 45»."""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Mm, Pt

from . import core
from .docs import (_cell_text, _margins, _para, _repeat_header, _set_run, _shade,
                   _widths, period_text, ru_date)

BODY = 10.5
SMALL = 9.0

LEGAL = [
    "ООО «НИЦ СМК» является членом Ассоциации СРО «АЛЬЯНС СТРОИТЕЛЕЙ» регистрационный номер записи "
    "в реестре саморегулируемых организаций СРО-С-018-16072009 от 05.08.2024 г. на основании протокола Президиума №1003.",
    "ООО «НИЦ СМК» является членом Ассоциации СРО «ЛИГА ИЗЫСКАТЕЛЕЙ», регистрационный номер члена "
    "саморегулируемой организации И-013-009715387698-1360 от 26.03.2024 г. на основании протокола Президиума № 1064.",
    "ООО «НИЦ СМК» является членом Ассоциации СРО «ЦЕНТРСТРОЙПРОЕКТ», регистрационный номер записи "
    "в реестре саморегулируемых организаций СРО-П-029-25092009 от 29.10.2024 г. на основании протокола "
    "Правления № 02-2910-Ц-24 от 29.10.2024 г.",
    "ООО «НИЦ СМК» аккредитовано в качестве испытательной лаборатории. Аттестат аккредитации "
    "№RU.АСК.ИЛ.1132 от 29.12.2022.",
    "Настоящие материалы являются результатом интеллектуальной деятельности ООО «НИЦ СМК», в связи с чем "
    "они не могут быть полностью или частично воспроизведены, тиражированы, распространены или переданы "
    "для использования третьим лицам без согласия ООО «НИЦ СМК».",
]

NORM_BASE = [
    "Постановление Правительства РФ от 21 июня 2010 г. N 468 «О порядке проведения строительного контроля "
    "при осуществлении строительства, реконструкции и капитального ремонта объектов капитального строительства»;",
    "СП 48.13330.2019. «Свод правил. Организация строительства. СНиП 12-01-2004» "
    "(утв. и введен в действие Приказом Минстроя России от 24.12.2019 N 861/пр);",
    "«Градостроительный кодекс Российской Федерации» от 29.12.2004 N 190-ФЗ;",
    "СП 126.13330.2017 «Геодезические работы в строительстве»;",
    "СП 45.13330.2017 «Земляные сооружения, основания и фундаменты»;",
    "ГОСТ 8736-2014 «Песок для строительных работ. Технические условия»;",
    "ГОСТ 8267-93 «Щебень и гравий из плотных горных пород для строительных работ. Технические условия»;",
    "ГОСТ Р 55030-2012 «Геосинтетические материалы. Общие технические требования»;",
    "ГОСТ 9128-2013 «Смеси асфальтобетонные дорожные и асфальтобетон. Технические условия»;",
    "СП 82.13330.2016 «Благоустройство территорий»;",
    "ГОСТ 6665-91 «Камни бортовые бетонные и железобетонные. Технические условия»;",
    "СП 49.13330.2010 «Безопасность труда в строительстве»;",
    "Проектно-сметная и рабочая документация.",
]

DESCRIPTION = [
    "Отгруженные и примененные на объекте строительные материалы и изделия по объему, виду, типу, модели "
    "соответствуют требованиям проектно-сметной документации.",
    "Отклонений показателей качества готовых конструкций от требований проектной, нормативно-правовой "
    "документации не выявлено.",
    "Предоставленный комплект рабочей документации содержит исчерпывающую, достоверную информацию о видах, "
    "характере и содержании производимых работ.",
    "Полнота, содержание и оформление исполнительной документации соответствует требованиям НТД.",
]


def _h1(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(4)
    p.paragraph_format.keep_with_next = True
    r = p.add_run(text.upper())
    _set_run(r, 11, bold=True)


def _body(doc, text: str, size=BODY, bold=False, justify=True, indent=1.15, space_after=4):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.space_after = Pt(space_after)
    pf.line_spacing = 1.15
    if indent:
        pf.first_line_indent = Cm(indent)
    if justify:
        p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run(text)
    _set_run(r, size, bold=bold)
    return p


def _bullet(doc, text: str, size=BODY):
    p = doc.add_paragraph()
    pf = p.paragraph_format
    pf.left_indent = Cm(1.0)
    pf.first_line_indent = Cm(-0.5)
    pf.space_after = Pt(2)
    pf.line_spacing = 1.1
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    r = p.add_run("– " + text)
    _set_run(r, size)
    return p


def _img(doc, path: str, width_cm: float, align=WD_ALIGN_PARAGRAPH.CENTER):
    p = doc.add_paragraph()
    p.alignment = align
    p.paragraph_format.space_after = Pt(2)
    try:
        if path and Path(path).exists():
            p.add_run().add_picture(str(path), width=Cm(width_cm))
    except Exception:
        pass
    return p


def _flat(table):
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "nil")
        borders.append(el)
    tblPr.append(borders)


def _short(d) -> str:
    if not d:
        return ""
    if isinstance(d, (date, datetime)):
        return d.strftime("%d.%m.%Y")
    s = str(d).strip()
    for f in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s, f).strftime("%d.%m.%Y")
        except ValueError:
            continue
    return s


def period_short(d1, d2) -> str:
    return f"{_short(d1)} – {_short(d2)}"


def _fmt(v, nd=3):
    if v in (None, ""):
        return ""
    try:
        f = float(str(v).replace(",", "."))
    except Exception:
        return str(v)
    s = f"{f:.{nd}f}".rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


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


def _header_block(doc, comp: dict):
    t = doc.add_table(rows=1, cols=2)
    t.autofit = False
    _flat(t)
    left, right = t.rows[0].cells
    left.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    logo = _asset(comp.get("logo") or "")
    lp = left.paragraphs[0]
    lp.alignment = WD_ALIGN_PARAGRAPH.LEFT
    if logo:
        try:
            lp.add_run().add_picture(str(logo), width=Cm(5.2))
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
        _set_run(r, SMALL, bold=bold)
    _widths(t, [5.6, 12.8])
    _margins(t, 0, 0, 0, 40)
    # линия под шапкой
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    pPr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single"); bottom.set(qn("w:sz"), "12")
    bottom.set(qn("w:space"), "1"); bottom.set(qn("w:color"), "1F3864")
    pbdr.append(bottom)
    pPr.append(pbdr)


def _works_table(doc, works: list[dict], address: str):
    rows = max(len(works), 1) + 2
    t = doc.add_table(rows=2, cols=7)
    t.style = "Table Grid"
    # шапка
    for i in range(3):
        t.cell(0, i).merge(t.cell(1, i))
    t.cell(0, 3).merge(t.cell(0, 6))
    hdr = {0: "№\nп/п", 1: "Перечень выполненных работ", 2: "Ед. изм."}
    for i, txt in hdr.items():
        _cell_text(t.cell(0, i), txt, SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.cell(0, i), "EDEDED")
    _cell_text(t.cell(0, 3), "Объемы работ", SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _shade(t.cell(0, 3), "EDEDED")
    for i, txt in enumerate(["Всего по контракту", "За отчетный период", "Нарастающим итогом", "Остаток"], 3):
        _cell_text(t.cell(1, i), txt, SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.cell(1, i), "EDEDED")
    _repeat_header(t.rows[0]); _repeat_header(t.rows[1])

    # строка адреса
    r = t.add_row()
    merged = r.cells[0].merge(r.cells[6])
    _cell_text(merged, f"Адрес: {address}", SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    _shade(merged, "F7F7F7")

    n = 0
    last_section = None
    for w in works:
        sec = (w.get("section") or "").strip()
        if sec and sec != last_section:
            rr = t.add_row()
            mm = rr.cells[0].merge(rr.cells[6])
            _cell_text(mm, sec, SMALL, bold=True)
            _shade(mm, "F2F2F2")
            last_section = sec
            n = 0
        n += 1
        rr = t.add_row()
        total = w.get("total")
        per = w.get("period")
        cum = w.get("cum")
        try:
            cum_v = float(str(cum).replace(",", ".")) if cum not in (None, "") else float(str(per).replace(",", "."))
        except Exception:
            cum_v = None
        try:
            rest = float(str(total).replace(",", ".")) - (cum_v or 0)
        except Exception:
            rest = None
        vals = [str(n), w.get("name", ""), w.get("unit", ""),
                _fmt(total), _fmt(per), _fmt(cum_v), _fmt(rest)]
        for i, v in enumerate(vals):
            al = WD_ALIGN_PARAGRAPH.LEFT if i == 1 else WD_ALIGN_PARAGRAPH.CENTER
            _cell_text(rr.cells[i], v, SMALL, align=al)
    _widths(t, [1.0, 5.6, 1.7, 2.4, 2.4, 2.4, 2.3])
    _margins(t, 20, 20, 40, 40)
    return t


def _works_simple(doc, works: list[dict]):
    t = doc.add_table(rows=1, cols=4)
    t.style = "Table Grid"
    for i, h in enumerate(["№ п/п", "Наименование работ", "Ед. изм.", "Примечание"]):
        _cell_text(t.rows[0].cells[i], h, SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.rows[0].cells[i], "EDEDED")
    _repeat_header(t.rows[0])
    for i, w in enumerate(works, 1):
        cells = t.add_row().cells
        _cell_text(cells[0], str(i), SMALL, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(cells[1], w.get("name", ""), SMALL)
        _cell_text(cells[2], w.get("unit", ""), SMALL, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(cells[3], w.get("note", ""), SMALL)
    _widths(t, [1.2, 10.6, 2.2, 4.4])
    _margins(t, 20, 20, 40, 40)
    return t


def _diary_table(doc, rows: list[dict]):
    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    for i, h in enumerate(["Дата", "Погода, температура, осадки", "Описание работ исполнителя",
                           "Описание работ инженера-резидента", "Примечание"]):
        _cell_text(t.rows[0].cells[i], h, SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.rows[0].cells[i], "EDEDED")
    _repeat_header(t.rows[0])
    for row in rows:
        cells = t.add_row().cells
        vals = [row.get("date", ""), row.get("weather", ""), row.get("works", ""),
                row.get("control", ""), row.get("note", "")]
        for i, v in enumerate(vals):
            _cell_text(cells[i], v, SMALL)
    _widths(t, [2.6, 2.4, 5.2, 5.8, 2.4])
    _margins(t, 20, 20, 40, 40)


def _tests_table(doc, tests: list[dict]):
    t = doc.add_table(rows=1, cols=7)
    t.style = "Table Grid"
    heads = ["№\nп/п", "Дата проведения испытаний (отбора проб)", "Наименование испытываемого материала",
             "Наименование участка дороги и элемента сооружения", "Требования проекта",
             "Результат испытаний", "Оценка"]
    for i, h in enumerate(heads):
        _cell_text(t.rows[0].cells[i], h, 8, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.rows[0].cells[i], "EDEDED")
    _repeat_header(t.rows[0])
    for i, row in enumerate(tests, 1):
        cells = t.add_row().cells
        vals = [str(i), row.get("date", ""), row.get("material", ""), row.get("place", ""),
                row.get("requirement", ""), row.get("result", ""), row.get("mark", "+")]
        for j, v in enumerate(vals):
            _cell_text(cells[j], v, 8, align=WD_ALIGN_PARAGRAPH.CENTER if j in (0, 6) else WD_ALIGN_PARAGRAPH.LEFT)
    _widths(t, [0.8, 3.0, 3.4, 3.2, 2.8, 2.8, 2.0])
    _margins(t, 20, 20, 30, 30)


def _passports_table(doc, rows: list[dict]):
    t = doc.add_table(rows=1, cols=4)
    t.style = "Table Grid"
    for i, h in enumerate(["№ п/п", "Наименование материала", "Наименование и № документа", "Дата документа"]):
        _cell_text(t.rows[0].cells[i], h, SMALL, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
        _shade(t.rows[0].cells[i], "EDEDED")
    _repeat_header(t.rows[0])
    for i, row in enumerate(rows, 1):
        cells = t.add_row().cells
        _cell_text(cells[0], str(i), SMALL, align=WD_ALIGN_PARAGRAPH.CENTER)
        _cell_text(cells[1], row.get("material", ""), SMALL)
        _cell_text(cells[2], row.get("doc", ""), SMALL)
        _cell_text(cells[3], row.get("date", ""), SMALL, align=WD_ALIGN_PARAGRAPH.CENTER)
    _widths(t, [1.2, 6.8, 7.4, 3.2])
    _margins(t, 20, 20, 40, 40)


def _signature(doc, comp: dict, specialist: str, signer: dict | None = None):
    pos_text = (signer or {}).get("pos") or "Специалист по строительному контролю"
    person = (signer or {}).get("name") or specialist
    sig = _asset((signer or {}).get("img") or comp.get("signature") or "")
    doc.add_paragraph().paragraph_format.space_after = Pt(10)
    t = doc.add_table(rows=2, cols=3)
    _flat(t)
    for row in t.rows:
        for cell in row.cells:
            cell.vertical_alignment = WD_ALIGN_VERTICAL.BOTTOM
    _cell_text(t.cell(0, 0), pos_text, SMALL)
    cell = t.cell(0, 1)
    p = cell.paragraphs[0]
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(0)
    if sig:
        try:
            p.add_run().add_picture(str(sig), width=Cm(3.6))
        except Exception:
            pass
    _cell_text(t.cell(0, 2), person, SMALL, align=WD_ALIGN_PARAGRAPH.CENTER)
    _cell_text(t.cell(1, 0), comp.get("name", ""), SMALL)
    _cell_text(t.cell(1, 1), "(подпись)", 8, align=WD_ALIGN_PARAGRAPH.CENTER)
    _cell_text(t.cell(1, 2), "", SMALL)
    _widths(t, [8.0, 5.0, 5.4])
    _margins(t, 0, 0, 0, 0)

    stamp = _asset(comp.get("stamp") or "")
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run("М.П.")
    _set_run(r, SMALL)
    if stamp:
        pp = doc.add_paragraph()
        pp.alignment = WD_ALIGN_PARAGRAPH.LEFT
        pp.paragraph_format.space_after = Pt(0)
        try:
            pp.add_run().add_picture(str(stamp), width=Cm(3.4))
        except Exception:
            pass


def _photos(doc, photos: list[dict]):
    table = doc.add_table(rows=0, cols=2)
    _flat(table)
    for i in range(0, len(photos), 2):
        row = table.add_row()
        for j in range(2):
            cell = row.cells[j]
            cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
            p = cell.paragraphs[0]
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            p.paragraph_format.space_after = Pt(4)
            if i + j < len(photos):
                ph = photos[i + j]
                path = Path(ph.get("path", ""))
                if path.exists():
                    try:
                        p.add_run().add_picture(str(path), width=Cm(8.6))
                    except Exception:
                        p.add_run("[фото недоступно]")
                cap = " · ".join(x for x in [ph.get("caption", ""), ph.get("date", "")] if x)
                if cap:
                    cp = cell.add_paragraph()
                    cp.alignment = WD_ALIGN_PARAGRAPH.CENTER
                    cp.paragraph_format.space_after = Pt(8)
                    rr = cp.add_run(cap)
                    _set_run(rr, 8, italic=True, color="444444")
    _widths(table, [8.9, 8.9])


def _default_conclusion(data: dict) -> str:
    addr = data.get("address") or data.get("object_title") or ""
    return (f"Работы по {addr} выполнены без нарушений СНиП, СП, ГОСТ. Исполнительная документация "
            f"предоставлена в полном объеме. В акте выполненных работ от {ru_date(data.get('ks_date'))} "
            f"№{data.get('ks', '')} (КС-2) представлены фактически выполненные объемы работ за отчетный "
            f"период {period_text(data.get('date_from'), data.get('date_to'))}.")


def _default_verdict(data: dict) -> str:
    addr = data.get("address") or ""
    return (f"Принять результат выполненных работ по {addr} по муниципальному контракту "
            f"{data.get('contract', '')}.")


def auto_diary(data: dict) -> list[dict]:
    works = data.get("works") or []
    period = period_short(data.get("date_from"), data.get("date_to"))
    control = ("Контроль за ходом выполнения работ. Проверка соответствия проектной документации, "
               "технологии производства работ и объёмов выполненных работ.")
    rows, seen = [], set()
    for w in works:
        name = (w.get("name") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        rows.append({"date": period, "weather": "ясно", "works": name,
                     "control": control, "note": "Замечаний нет"})
    return rows


def build(record: dict, out_path: Path, signer: dict | None = None) -> Path:
    data = record.get("payload", {}) or {}
    comp = core.company()
    doc = Document()

    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(13); s.right_margin = Mm(13)
    s.top_margin = Mm(13); s.bottom_margin = Mm(13)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"
    st.font.size = Pt(BODY)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), "Times New Roman")

    _header_block(doc, comp)

    p = _para(doc, "ОТЧЕТ №" + record["number"], 16, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER, space_after=2)
    _para(doc, "по результатам строительного контроля", 11, bold=True,
          align=WD_ALIGN_PARAGRAPH.CENTER, space_after=10)

    addr_label = "Адрес объекта" if data.get("mode") == "field" else "Адрес пешеходной коммуникации"
    req = [
        ("Заказчик", data.get("customer", "")),
        ("Исполнитель", data.get("executor", "")),
        ("Объект", data.get("object_title", "")),
        ("Муниципальный контракт", data.get("contract", "")),
        (addr_label, data.get("address", "")),
        ("Отчетный период", period_text(data.get("date_from"), data.get("date_to"))),
    ]
    if (data.get("address") or "").strip() == (data.get("object_title") or "").strip():
        req = [x for x in req if x[0] != addr_label]
    for k, v in req:
        if not (v or "").strip():
            continue
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(3)
        p.paragraph_format.line_spacing = 1.05
        r = p.add_run(f"{k}: ")
        _set_run(r, BODY, bold=True)
        r = p.add_run(v)
        _set_run(r, BODY, bold=True)

    # 1
    _h1(doc, "Правовые и нормативные основания, требования и обязательства")
    for t in LEGAL:
        _body(doc, t)

    # 2
    _h1(doc, "Нормативно-правовая база")
    _body(doc, "Строительный контроль выполнен в соответствии с Градостроительным кодексом "
               "Российской Федерации и требованиями нормативной документации:", indent=1.15)
    for t in NORM_BASE:
        _bullet(doc, t)

    field_mode = data.get("mode") == "field"

    # 3
    obj = data.get("object_title") or data.get("address") or ""
    _h1(doc, "Краткое описание выполненных работ")
    if field_mode and (data.get("description") or "").strip():
        for block in data["description"].split("\n"):
            if block.strip():
                _body(doc, block.strip())
        _body(doc, f"Работы по {data.get('address') or obj} выполнялись в соответствии с проектной "
                   f"документацией, требованиями СНиП, СП и ГОСТ.")
    else:
        _body(doc, f"Работы по {data.get('address') or obj} выполнены без нарушений СНиП, СП, ГОСТ.")
    for t in DESCRIPTION[:3]:
        _body(doc, t)

    # 4
    if field_mode:
        _h1(doc, "Виды работ, зафиксированные за отчетный период")
        _body(doc, f"Перечень составлен по {data.get('entries_count', 0)} полевым записям специалиста "
                   f"строительного контроля с фотофиксацией.")
        _works_simple(doc, data.get("works") or [])
    else:
        _h1(doc, "Объемы работ, выполненные за отчетный период")
        executor = data.get("executor") or comp.get("name", "")
        intro = (f"Объемы работ, указанные в ведомости, подтверждены предоставленными {executor} "
                 f"формой КС-2 {data.get('ks', '')} и следующими актами освидетельствования скрытых работ:")
        _body(doc, intro)
        acts = data.get("acts") or []
        for a in acts:
            txt = a.strip()
            if not txt:
                continue
            p = doc.add_paragraph()
            p.paragraph_format.space_after = Pt(1)
            p.paragraph_format.left_indent = Cm(0.6)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            r = p.add_run(txt)
            _set_run(r, BODY, bold=True)
        _body(doc, "Указанные акты проверены специалистом по строительному контролю. Замечаний по "
                   "результатам проверки не выявлено.")
        _works_table(doc, data.get("works") or [], data.get("address", ""))

    # 5
    _h1(doc, "Дневник инженера-резидента")
    diary = data.get("diary") or auto_diary(data)
    _diary_table(doc, diary)

    # 6
    tests = data.get("tests") or []
    if tests:
        _h1(doc, "Результаты входного, операционного и приемо-сдаточного контроля при выполнении контрольных "
                 "испытаний всех видов строительных материалов и технологических процессов, выполненных "
                 "строительной лабораторией технадзора (Форма Ф-7)")
        _tests_table(doc, tests)

    # 7
    passports = data.get("passports") or []
    if passports:
        _h1(doc, "Реестр паспортов и сертификатов")
        _passports_table(doc, passports)

    # 8
    _h1(doc, "Заключение")
    conclusion = (data.get("conclusion") or "").strip() or _default_conclusion(data)
    for block in conclusion.split("\n"):
        if block.strip():
            _body(doc, block.strip())

    # 9
    _h1(doc, "Вывод")
    verdict = (data.get("verdict") or "").strip() or _default_verdict(data)
    _body(doc, verdict)

    doc.add_paragraph()
    _signature(doc, comp, data.get("specialist") or comp.get("lab_head", ""), signer)

    # фото
    photos = data.get("photos") or []
    if photos:
        p = doc.add_paragraph()
        p.add_run().add_break(WD_BREAK.PAGE)
        _h1(doc, "Материалы фотофиксации")
        _photos(doc, photos)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path


def sections(data: dict) -> list[tuple[str, str]]:
    """Короткий предпросмотр текстовой части для интерфейса."""
    return [
        ("1. Правовые и нормативные основания", " ".join(LEGAL[:4])),
        ("2. Нормативно-правовая база", f"Перечень из {len(NORM_BASE)} документов: от Градостроительного "
                                        f"кодекса РФ и СП 48.13330.2019 до ГОСТ 9128-2013 и проектной документации."),
        ("3. Краткое описание работ", f"Работы по {data.get('address','—')} выполнены без нарушений СНиП, СП, ГОСТ. "
                                     + " ".join(DESCRIPTION[:2])),
        ("4. Объёмы работ", f"В таблице {len(data.get('works') or [])} позиций; подтверждаются формой КС-2 "
                            f"{data.get('ks','')} и актами освидетельствования скрытых работ."),
        ("5. Дневник инженера-резидента", f"Записей: {len(data.get('diary') or auto_diary(data))}."),
        ("8. Заключение", (data.get("conclusion") or "").strip() or _default_conclusion(data)),
        ("9. Вывод", (data.get("verdict") or "").strip() or _default_verdict(data)),
    ]
