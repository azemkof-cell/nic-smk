# -*- coding: utf-8 -*-
"""Автоматические отчёты по расписанию (неделя / месяц)."""
from __future__ import annotations

import json
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

from . import ai, core, docs, pdf, reportgen, weekly_report


def _report_number() -> str:
    year = date.today().year
    con = core.connect()
    row = con.execute("SELECT value FROM counters WHERE kind='report' AND year=?", (year,)).fetchone()
    n = (row["value"] if row else 0) + 1
    con.execute("INSERT INTO counters(kind,year,value) VALUES ('report',?,?) "
                "ON CONFLICT(kind,year) DO UPDATE SET value=excluded.value", (year, n))
    con.commit()
    con.close()
    return f"{n:03d}-СК.{str(year)[2:]}"


def _period(obj: dict, date_to: str) -> tuple[str, str]:
    con = core.connect()
    row = con.execute(
        "SELECT MAX(date_to) d FROM reports WHERE object_name LIKE ?",
        (f"%{obj['name'][:40]}%",)).fetchone()
    con.close()
    if row and row["d"]:
        start = datetime.strptime(row["d"][:10], "%Y-%m-%d").date() + timedelta(days=1)
    elif obj.get("report_start"):
        start = datetime.strptime(obj["report_start"][:10], "%Y-%m-%d").date()
    else:
        start = datetime.strptime(date_to[:10], "%Y-%m-%d").date() - timedelta(days=6)
    return start.isoformat(), date_to[:10]


def generate(object_id: int, date_to: str | None = None, force: bool = False) -> dict | None:
    """Собирает отчёт по объекту за период и сохраняет DOCX+PDF."""
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    con.close()
    if not obj:
        return None
    obj = dict(obj)
    date_to = (date_to or obj.get("report_next") or date.today().isoformat())[:10]
    date_from, date_to = _period(obj, date_to)

    payload, log = ai.build_report_payload(
        object_id, obj["name"], date_from, date_to,
        core.company().get("lab_head", ""), customer=obj.get("customer") or "",
        contract=obj.get("contract") or "", object_title=obj["name"],
        executor=core.company().get("executor") or core.company().get("name", ""))
    payload["auto"] = True
    number = _report_number()
    record = {"number": number, "date_from": date_from, "date_to": date_to,
              "object_name": obj["name"], "customer": obj.get("customer") or "",
              "contract": obj.get("contract") or "", "payload": payload}
    fname = f"Отчёт {number} {obj['name']}.docx"
    fname = "".join(ch for ch in fname if ch not in '\\/:*?"<>|')
    out = docs.doc_folder("Отчёты") / fname

    freq = obj.get("report_freq") or "weekly"
    weekly = freq in ("weekly", "monthly")
    if weekly:
        works = []
        try:
            from . import ks2
            rows = ks2.period_works(object_id, date_from, date_to)
        except Exception:
            rows = []
        if rows:
            def _f(x):
                s = f"{x:.2f}".rstrip("0").rstrip(".")
                return s.replace(".", ",")
            for w in rows[:60]:
                works.append({"name": w["name"], "unit": w["unit"],
                              "period": _f(w["period"]) if w["period"] else "—",
                              "total": _f(w["total"]),
                              "pct": (f"{w['pct']:.0f} %".replace(".", ",") if w.get("pct") else "—"),
                              "status": "по КС-2"})
        else:
            for w in payload.get("works") or []:
                works.append({"name": w.get("name", ""), "unit": w.get("unit", ""),
                              "period": "", "total": "", "status": w.get("note", "") or "—"})
        photos = payload.get("photos") or []
        data = {
            "city": obj.get("city") or obj["name"].split(",")[0].title(),
            "year": date.today().year,
            "period_text": f"{date_from[8:10]}.{date_from[5:7]}.{date_from[:4]} – "
                           f"{date_to[8:10]}.{date_to[5:7]}.{date_to[:4]}",
            "period_short": f"{date_from[8:10]}.{date_from[5:7]}–{date_to[8:10]}.{date_to[5:7]}",
            "object_short": obj.get("object_title") or obj["name"],
            "object_full": obj.get("object_title") or obj["name"],
            "sections": obj.get("address") or obj["name"],
            "customer": obj.get("customer") or "",
            "contractor": obj.get("contractor") or "",
            "contract": obj.get("contract") or "",
            "specialist": core.company().get("lab_head", ""),
            "executor": core.company().get("executor") or core.company().get("name", ""),
            "summary": payload.get("description") or "",
            "works": works, "photos": photos,
            "cover_caption": (photos[0].get("caption") if photos else "") or "",
            "kpis": [
                {"value": str(payload.get("entries_count") or 0), "label": "записей с объекта"},
                {"value": str(len(photos)), "label": "фотоматериалов"},
                {"value": str(len(works)), "label": "видов работ"},
                {"value": "0", "label": "новых предписаний", "green": True},
            ],
        }
        weekly_report.build(record, data, out)
    else:
        reportgen.build(record, out)
    pdf.export(out)
    con = core.connect()
    cur = con.execute(
        "INSERT INTO reports(number,rdate,date_from,date_to,object_name,customer,contract,payload,created_at,file,kind)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (number, date.today().isoformat(), date_from, date_to, obj["name"],
         obj.get("customer") or "", obj.get("contract") or "",
         json.dumps(payload, ensure_ascii=False), date.today().isoformat(),
         str(out.relative_to(core.BASE)), "weekly" if weekly else "final"))
    con.commit()
    rid = cur.lastrowid
    con.close()

    nxt = core.next_report_date(date_to, obj.get("report_freq") or "weekly").isoformat()
    con = core.connect()
    con.execute("UPDATE objects SET report_next=? WHERE id=?", (nxt, object_id))
    con.commit()
    con.close()
    if obj.get("folder"):
        try:
            core.copy_docs_to_object(object_id)
        except Exception:
            pass
    return {"id": rid, "number": number, "file": str(out.relative_to(core.BASE)),
            "pdf": pdf.pdf_for(str(out.relative_to(core.BASE))), "date_from": date_from,
            "date_to": date_to, "log": log, "next": nxt}


def run_due() -> list[dict]:
    results = []
    for obj in core.due_objects():
        try:
            res = generate(obj["id"], obj.get("report_next"))
            if res:
                results.append(res)
        except Exception:
            traceback.print_exc()
    return results
