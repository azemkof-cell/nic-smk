# -*- coding: utf-8 -*-
"""Оцифровка архива протоколов из PDF: номер, дата, объект, текст."""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from . import core


def _text(path: Path, pages: int = 2) -> str:
    try:
        import pypdfium2 as pdfium
    except Exception:
        return ""
    try:
        pdf = pdfium.PdfDocument(str(path))
        parts = []
        for i in range(min(len(pdf), pages)):
            tp = pdf[i].get_textpage()
            parts.append(tp.get_text_bounded())
        pdf.close()
        return "\n".join(parts)
    except Exception:
        return ""


def parse(text: str, filename: str = "", folder: str = "") -> dict:
    """Номер и дата — сначала из имени файла (он у вас информативный), потом из текста."""
    raw = text or ""
    name = filename or ""

    def first_number(src: str):
        m = re.search(r"№\s*([0-9][0-9.,/\-]{1,15})", src)
        return m.group(1).strip(" .,") if m else ""

    def first_date(src: str):
        m = re.search(r"(\d{2}\.\d{2}\.\d{4})", src)
        return m.group(1) if m else ""

    num = first_number(name)
    pdate = first_date(name)
    if not num or not pdate:
        lines = [ln.strip() for ln in raw.splitlines() if ln.strip()]
        head = ""
        for i, ln in enumerate(lines):
            if "ПРОТОКОЛ" in ln.upper():
                head = " ".join(lines[i:i + 4])
                break
        num = num or first_number(head)
        if not num:
            cand = first_number(raw)
            if re.match(r"^(\d{3,}|\d{2,}[.,]\d)", cand or ""):
                num = cand
        pdate = pdate or (re.search(r"от\s+(\d{2}\.\d{2}\.\d{4})", head).group(1)
                          if re.search(r"от\s+(\d{2}\.\d{2}\.\d{4})", head) else "")

    obj = ""
    m = re.search(r"Наименование объекта\s*:?\s*(.{5,180}?)(?:\s+Подрядчик|\s+Наименование материала|$)", raw)
    if m:
        obj = m.group(1).strip()
    if not obj and folder:
        obj = folder
    mat = ""
    m = re.search(r"Наименование материала\s*:?\s*(.{3,90}?)(?:\s+Назначение|\s+Дата отбора|$)", raw)
    if m:
        mat = m.group(1).strip()
    return {"number": num, "pdate": pdate, "object_name": obj, "material": mat}


def reparse() -> int:
    """Перечитывает уже сохранённые тексты — быстро, без обращения к PDF."""
    con = core.connect()
    rows = con.execute("SELECT id,text,path FROM protocol_archive").fetchall()
    n = 0
    for r in rows:
        q = Path(r["path"] or "")
        meta = parse(r["text"] or "", q.name, q.parent.name)
        con.execute("UPDATE protocol_archive SET number=?, pdate=?, object_name=?, material=? WHERE id=?",
                    (meta["number"], meta["pdate"], meta["object_name"], meta["material"], r["id"]))
        n += 1
    con.commit()
    con.close()
    return n


def scan(limit: int = 120) -> dict:
    roots = [core.BASE.parent / "РАБОЧАЯ"]
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS protocol_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, number TEXT, pdate TEXT,
        object_name TEXT, material TEXT, text TEXT, imported_at TEXT)""")
    con.commit()
    known = {r["path"] for r in con.execute("SELECT path FROM protocol_archive")}
    con.close()

    added, scanned = 0, 0
    for root in roots:
        if not root.exists():
            continue
        for f in root.rglob("*.pdf"):
            if scanned >= limit or added >= limit:
                break
            name = f.name.lower()
            if "протокол" not in name:
                continue
            if str(f) in known:
                continue
            scanned += 1
            text = _text(f)
            if not text:
                continue
            meta = parse(text, f.name, f.parent.name)
            con = core.connect()
            con.execute(
                "INSERT OR IGNORE INTO protocol_archive(path,number,pdate,object_name,material,text,imported_at)"
                " VALUES (?,?,?,?,?,?,?)",
                (str(f), meta["number"], meta["pdate"], meta["object_name"], meta["material"],
                 text[:20000], date.today().isoformat()))
            con.commit()
            con.close()
            added += 1
    con = core.connect()
    total = con.execute("SELECT COUNT(*) c FROM protocol_archive").fetchone()["c"]
    con.close()
    return {"added": added, "scanned": scanned, "total": total}


def search(q: str = "", limit: int = 200) -> list[dict]:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS protocol_archive (
        id INTEGER PRIMARY KEY AUTOINCREMENT, path TEXT UNIQUE, number TEXT, pdate TEXT,
        object_name TEXT, material TEXT, text TEXT, imported_at TEXT)""")
    if q:
        like = f"%{q}%"
        rows = con.execute(
            "SELECT id,path,number,pdate,object_name,material,imported_at FROM protocol_archive "
            "WHERE number LIKE ? OR object_name LIKE ? OR material LIKE ? OR text LIKE ? "
            "ORDER BY id DESC LIMIT ?", (like, like, like, like, limit)).fetchall()
    else:
        rows = con.execute(
            "SELECT id,path,number,pdate,object_name,material,imported_at FROM protocol_archive "
            "ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
