# -*- coding: utf-8 -*-
"""Разбор актов КС-2 из папки объекта: виды работ, единицы, объёмы."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from . import core


def _num(v):
    try:
        return float(str(v).replace(",", ".").replace(" ", ""))
    except (TypeError, ValueError):
        return None


def parse_act(path: str, sheet_key: str = "кс-2") -> dict:
    import openpyxl
    q = Path(path)
    out = {"file": str(q), "act_no": "", "act_date": "", "works": []}
    try:
        wb = openpyxl.load_workbook(str(q), data_only=True, read_only=True)
    except Exception:
        return out
    try:
        ws = None
        for name in wb.sheetnames:
            low = name.lower()
            if sheet_key == "смета":
                if "смет" in low:
                    ws = wb[name]; break
            elif sheet_key == "вор":
                if "вор" in low or "ведомост" in low:
                    ws = wb[name]; break
            elif low.strip() in ("кс-2", "кс2", "кс 2"):
                ws = wb[name]; break
        if ws is None:
            for name in wb.sheetnames:
                low = name.lower()
                if (sheet_key == "смета" and "смет" in low) or (sheet_key == "вор" and ("вор" in low or "ведомост" in low)) or (sheet_key == "кс-2" and "кс-2" in low):
                    ws = wb[name]; break
        if ws is None and sheet_key == "вор":
            ws = wb.worksheets[0]
        if ws is None:
            return out
        rows = list(ws.iter_rows(values_only=True))

        # шапка таблицы: ищем индексы колонок по названиям
        header = None
        cols = {}
        for i, row in enumerate(rows[:80]):
            low = [str(v).lower() if v is not None else "" for v in row]
            name_i = next((j for j, v in enumerate(low) if "наименование работ" in v), None)
            unit_i = next((j for j, v in enumerate(low)
                           if "единица измерения" in v or v.strip() in ("ед. изм.", "ед.изм.", "ед. изм", "ед")), None)
            qty_i = next((j for j, v in enumerate(low)
                          if v.startswith("количество") or v.startswith("кол-во") or v.startswith("кол.")), None)
            if name_i is not None and unit_i is not None and qty_i is not None:
                header = i
                cols = {"name": name_i, "unit": unit_i, "qty": qty_i,
                        "num": next((j for j, v in enumerate(low) if v.startswith("№")), 0)}
                break
        if header is None:
            return out

        # дата акта: последняя дата перед таблицей (период «по»)
        all_dates = [v for row in rows[:header] for v in row if isinstance(v, datetime)]
        if all_dates:
            out["act_date"] = all_dates[-1].date().isoformat()
        for row in rows[:header]:
            nums = [v for v in row if isinstance(v, (int, float)) and not isinstance(v, bool) and 0 < v < 100000]
            if nums and any(isinstance(v, datetime) for v in row):
                out["act_no"] = str(int(nums[0]))
                break

        if sheet_key in ("смета", "вор"):
            out["act_no"] = "ДОГОВОР"
            out["act_date"] = ""
        for row in rows[header + 1:]:
            if not row or len(row) <= max(cols.values()):
                continue
            a = _num(row[cols["num"]])
            name = row[cols["name"]]
            unit = row[cols["unit"]]
            qty = row[cols["qty"]]
            if a is None or int(a) != a or not name or not unit:
                continue
            text = str(name).strip()
            low = text.lower()
            if len(text) < 5 or low.startswith(("итого", "всего", "раздел", "подраздел", "справочно")):
                continue
            unit_s = str(unit).strip()
            if not unit_s or unit_s.replace(".", "").isdigit():
                continue
            qv = _num(qty)
            if qv is None or qv < 0 or qv > 1e7:
                continue
            if "поправки к" in low:
                continue
            clean = re.split(r"\s+V=|\s+Поправки", text)[0]
            clean = re.sub(r"\s+", " ", clean).strip()[:200]
            out["works"].append({"name": clean, "unit": unit_s[:20], "qty": qv})
    finally:
        wb.close()
    return out


def scan_object(object_id: int) -> dict:
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    con.execute("""CREATE TABLE IF NOT EXISTS object_works (
        id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, name TEXT, unit TEXT,
        qty REAL, act_no TEXT, act_date TEXT, source TEXT, imported_at TEXT,
        UNIQUE(object_id, name, unit, act_no))""")
    con.commit()
    con.close()
    if not obj:
        return {"acts": 0, "works": 0}
    folder = obj["folder"] or ""
    files = []
    if folder and Path(folder).exists():
        for f in Path(folder).rglob("*.xlsx"):
            low = f.name.lower()
            if ("кс-2" in low or "кс2" in low) and not ("кс-3" in low and "кс-2" not in low) and not any(
                    x in low for x in ("сверка", "ведомост", "реестр")):
                files.append(f)
    if not files:
        # папка объекта может быть привязана неверно — ищем КС-2 по названию объекта
        import re as _re
        tokens = [w.lower() for w in _re.split(r"[^\wа-яА-ЯёЁ]+", obj["name"]) if len(w) > 2]
        root = core.BASE.parent / "РАБОЧАЯ"
        if root.exists() and tokens:
            for f in root.rglob("*.xlsx"):
                low = str(f).lower()
                if ("кс-2" in f.name.lower() or "кс2" in f.name.lower()) and not ("кс-3" in f.name.lower() and "кс-2" not in f.name.lower()) \
                        and not any(x in f.name.lower() for x in ("сверка", "ведомост", "реестр")) and \
                        sum(1 for tok in tokens if tok in low) >= max(1, len(tokens) - 1):
                    files.append(f)
                    if len(files) >= 20:
                        break
    acts = 0
    parsed = []
    for f in files[:30]:
        act = parse_act(str(f))
        if not act["works"]:
            continue
        import re as _re
        m = _re.search(r"(\d{2})[._-](\d{2})", f.name)
        if m:
            try:
                act["act_date"] = date(date.today().year, int(m.group(2)), int(m.group(1))).isoformat()
            except ValueError:
                pass
        m2 = _re.search(r"КС-?2\s*№\s*(\d+)", f.name, _re.I)
        if m2:
            act["act_no"] = m2.group(1)
        parsed.append((f, act))

    # один акт может лежать в двух файлах (оригинал/испр) — берём свежий
    best = {}
    for f, act in parsed:
        key = (act["act_no"], act["act_date"], len(act["works"]))
        try:
            mt = f.stat().st_mtime
        except OSError:
            mt = 0
        if key not in best or mt > best[key][0]:
            best[key] = (mt, f, act)
    # договорные объёмы: ВОР, если есть, иначе смета
    vor_files = []
    if folder and Path(folder).exists():
        for f in Path(folder).rglob("*.xlsx"):
            low = f.name.lower()
            if "вор" in low or ("ведомост" in low and "объем" in low) or "объём" in low:
                vor_files.append(f)
    if vor_files:
        for f in vor_files[:5]:
            try:
                vor = parse_act(str(f), "вор")
            except Exception:
                continue
            for w in vor.get("works") or []:
                con = core.connect()
                con.execute(
                    "INSERT OR REPLACE INTO object_works(object_id,name,unit,qty,act_no,act_date,source,imported_at)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (object_id, w["name"], w["unit"], w["qty"], "ДОГОВОР", "",
                     f.name, date.today().isoformat()))
                con.commit()
                con.close()
        files = files  # no-op
    # договорные объёмы из сметы (для процентов)
    contracts_best = {}
    for f in files[:30]:
        try:
            sm = parse_act(str(f), "смета")
        except Exception:
            continue
        for w in sm.get("works") or []:
            key = (w["name"], w["unit"])
            if key not in contracts_best or w["qty"] > contracts_best[key]["qty"]:
                contracts_best[key] = w
    if contracts_best:
        con = core.connect()
        for w in contracts_best.values():
            con.execute(
                "INSERT OR REPLACE INTO object_works(object_id,name,unit,qty,act_no,act_date,source,imported_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (object_id, w["name"], w["unit"], w["qty"], "ДОГОВОР", "",
                 "смета", date.today().isoformat()))
        con.commit()
        con.close()

    for _mt, f, act in best.values():
        acts += 1
        con = core.connect()
        for w in act["works"]:
            con.execute(
                "INSERT OR IGNORE INTO object_works(object_id,name,unit,qty,act_no,act_date,source,imported_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (object_id, w["name"], w["unit"], w["qty"], act["act_no"], act["act_date"],
                 f.name, date.today().isoformat()))
        con.commit()
        con.close()
    return {"acts": acts, "files": len(files)}


def list_works(object_id: int) -> list[dict]:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS object_works (
        id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, name TEXT, unit TEXT,
        qty REAL, act_no TEXT, act_date TEXT, source TEXT, imported_at TEXT,
        UNIQUE(object_id, name, unit, act_no))""")
    rows = con.execute(
        "SELECT name, unit, SUM(qty) qty, MAX(act_date) last_date, COUNT(*) acts "
        "FROM object_works WHERE object_id=? GROUP BY name, unit ORDER BY name", (object_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def period_works(object_id: int, date_from: str, date_to: str) -> list[dict]:
    """Объёмы за период и нарастающим итогом по актам КС-2."""
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS object_works (
        id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, name TEXT, unit TEXT,
        qty REAL, act_no TEXT, act_date TEXT, source TEXT, imported_at TEXT,
        UNIQUE(object_id, name, unit, act_no))""")
    rows = con.execute("SELECT name, unit, qty, act_date, act_no FROM object_works WHERE object_id=?",
                       (object_id,)).fetchall()
    con.close()
    agg = {}
    for r in rows:
        key = (r["name"], r["unit"])
        a = agg.setdefault(key, {"name": r["name"], "unit": r["unit"], "period": 0.0,
                                 "total": 0.0, "contract": 0.0})
        if (r["act_no"] or "") == "ДОГОВОР":
            a["contract"] = max(a["contract"], r["qty"] or 0)
            continue
        a["total"] += r["qty"] or 0
        d = (r["act_date"] or "")[:10]
        if (not date_from or d >= date_from) and (not date_to or d <= date_to):
            a["period"] += r["qty"] or 0
    out = []
    for a in agg.values():
        a["pct"] = (100.0 * a["total"] / a["contract"]) if a["contract"] else None
        out.append(a)
    return out
