# -*- coding: utf-8 -*-
"""Извлечение реквизитов объекта из документов его папки."""
from __future__ import annotations

import re
from pathlib import Path

from . import core, storage

MAX_DOCS = 12
MAX_CHARS = 30000

ORG = r"(?:АДМИНИСТРАЦИЯ|ООО|ОАО|ПАО|АО|ИП|ФКУ|ГКУ|ГБУ|МУП|ГУП|ДЕПАРТАМЕНТ|МИНИСТЕРСТВО|ПРАВИТЕЛЬСТВО)"
RE_CUSTOMER = re.compile(r"Заказчик[:\s|]*(" + ORG + r"[^\n]{2,140})", re.I)
RE_CUSTOMER_ANY = re.compile(r"Заказчик[:\s|]*([^\n]{3,140})", re.I)
RE_CONTRACTOR = re.compile(r"Подрядчик[^\n:]*[:\s|]*(" + ORG + r"[^\n]{2,140})", re.I)
RE_CONTRACTOR_ANY = re.compile(r"Подрядчик[^\n:]*[:\s|]*([^\n]{3,140})", re.I)
RE_CONTRACT = re.compile(r"(?:Контракт|Договор)[^\n]{0,80}?(?:№|номер)\s*([0-9A-Za-zА-Яа-яЁё/._-]{3,40})", re.I)
RE_OBJECT = re.compile(r"Объект[:\s|]+([^\n]{5,200})", re.I)
RE_ADDRESS = re.compile(r"((?:г\.|город|пгт\.|пос\.)[ \t]*[А-ЯЁ][а-яё-]{2,25}(?:[ \t]*,[^\n;]{3,80})?)")


def _pdf_text(path: Path) -> str:
    try:
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(str(path))
        out = []
        for i in range(min(len(pdf), 6)):
            out.append(pdf[i].get_textpage().get_text_bounded())
        pdf.close()
        return "\n".join(out)
    except Exception:
        return ""


def _docx_text(path: Path) -> str:
    try:
        import docx
        d = docx.Document(str(path))
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        return "\n".join(parts)
    except Exception:
        return ""


def _xlsx_text(path: Path) -> str:
    try:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        parts = []
        for ws in wb.worksheets[:2]:
            for ri, row in enumerate(ws.iter_rows(values_only=True)):
                if ri > 30:
                    break
                vals = [str(v) for v in row if v is not None]
                if vals:
                    parts.append(" | ".join(vals))
                if len(parts) > 400:
                    break
        wb.close()
        return "\n".join(parts)
    except Exception:
        return ""


def _text_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        return _pdf_text(path)
    if ext == ".docx":
        return _docx_text(path)
    if ext in (".xlsx", ".xls"):
        return _xlsx_text(path)
    if ext in (".txt", ".csv"):
        try:
            return path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return ""
    return ""


def _clean(value: str) -> str:
    v = re.split(r"\s{2,}|,\s*ИНН|\s+ИНН|\s+ОГРН|\s*\|\s*по\s|\s*\|", value.strip())[0]
    return v.strip(" .,:;|")[:200]


def extract(object_id: int) -> dict:
    rows = storage.files(object_id)
    cand = [r for r in rows if r["kind"] in ("docs", "tables", "acts")]
    def _prio(r):
        ext = Path(r["name"]).suffix.lower()
        return (0 if ext in (".xlsx", ".xls") else 1 if ext == ".docx" else 2)
    docs = sorted(cand, key=_prio)[:MAX_DOCS]
    text = ""
    used = 0
    for r in docs:
        p = core.BASE / r["rel"]
        if not p.exists() or p.stat().st_size > 25 * 1024 * 1024:
            continue
        t = _text_of(p)
        if t:
            text += "\n" + t[:8000]
            used += 1
        if len(text) > MAX_CHARS:
            break
    text = text[:MAX_CHARS]

    found = {}
    orgs = [c for c in RE_CUSTOMER.findall(text)]
    if orgs:
        found["customer"] = _clean(orgs[0])
    else:
        m = RE_CUSTOMER_ANY.search(text)
        if m and not any(x in m.group(1).lower() for x in ("лицо, ответственное", "эксплуатацию")):
            found["customer"] = _clean(m.group(1))
    orgs = [c for c in RE_CONTRACTOR.findall(text)]
    if orgs:
        found["contractor"] = _clean(orgs[0])
    else:
        m = RE_CONTRACTOR_ANY.search(text)
        if m and not any(x in m.group(1).lower() for x in ("лицо, ответственное", "эксплуатацию")):
            found["contractor"] = _clean(m.group(1))
    m = RE_CONTRACT.search(text)
    if m:
        found["contract"] = "№" + m.group(1)
    for cand in RE_OBJECT.findall(text):
        val = _clean(cand)
        if len(val) < 8:
            continue
        low = val.lower()
        if low.startswith(("капитального", "наименование", "ремонт", "строительств")):
            continue
        if not any(x in val for x in ("г.", "ул.", "д.", "проспект", "обл.", "р-н")):
            continue
        found["object_title"] = val[:200]
        break
    if "address" not in found:
        m = RE_ADDRESS.search(text)
        if m:
            found["address"] = _clean(m.group(1))

    if found.get("contract"):
        digits = re.sub(r"\D", "", found["contract"])
        if digits:
            con0 = core.connect()
            for c in con0.execute("SELECT id,number FROM contracts").fetchall():
                cd = re.sub(r"\D", "", c["number"] or "")
                if cd and (cd == digits or cd in digits or digits in cd):
                    found["contract_id"] = c["id"]
                    break
            con0.close()
    if found:
        con = core.connect()
        sets = ", ".join(f"{k}=?" for k in found)
        con.execute(f"UPDATE objects SET {sets} WHERE id=?", (*found.values(), object_id))
        con.commit()
        con.close()
    return {"found": found, "docs_used": used, "chars": len(text)}
