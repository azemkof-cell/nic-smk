# -*- coding: utf-8 -*-
"""Локальное хранилище документов объекта (без Яндекс.Диска)."""
from __future__ import annotations

import shutil
from datetime import date
from pathlib import Path

from . import core

ROOT = core.BASE / "data" / "storage"
MAX_FILES = 400
MAX_SIZE = 60 * 1024 * 1024
SKIP_EXT = {".mp4", ".mov", ".avi", ".mkv", ".iso", ".rar", ".7z", ".exe", ".dwg"}


def object_dir(object_id: int) -> Path:
    p = ROOT / "objects" / str(object_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def categorize(name: str) -> str:
    low = name.lower()
    ext = Path(name).suffix.lower()
    if "кс-2" in low or "кс2" in low or "кс-3" in low:
        return "acts"
    if ext in (".jpg", ".jpeg", ".png", ".webp", ".bmp"):
        return "photos"
    if ext in (".xlsx", ".xls", ".csv"):
        return "tables"
    if ext in (".pdf", ".docx", ".doc", ".txt", ".rtf"):
        return "docs"
    return "other"


def import_folder(object_id: int, src: str) -> dict:
    """Копирует папку в локальное хранилище объекта и регистрирует файлы."""
    source = Path(src)
    if not source.exists() or not source.is_dir():
        raise ValueError("Папка не найдена: " + src)
    dst_root = object_dir(object_id)
    stats = {"files": 0, "skipped": 0, "bytes": 0, "acts": 0, "photos": 0}
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS object_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, rel TEXT, name TEXT,
        kind TEXT, size INTEGER, added_at TEXT, UNIQUE(object_id, rel))""")
    con.commit()
    for f in sorted(source.rglob("*")):
        if stats["files"] >= MAX_FILES:
            break
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext in SKIP_EXT:
            stats["skipped"] += 1
            continue
        try:
            size = f.stat().st_size
        except OSError:
            continue
        if size > MAX_SIZE:
            stats["skipped"] += 1
            continue
        try:
            rel_src = f.relative_to(source)
        except ValueError:
            continue
        dst = dst_root / rel_src
        dst.parent.mkdir(parents=True, exist_ok=True)
        if not dst.exists():
            try:
                shutil.copy2(f, dst)
            except OSError:
                stats["skipped"] += 1
                continue
        kind = categorize(f.name)
        rel = str(dst.relative_to(core.BASE))
        con.execute("INSERT OR IGNORE INTO object_files(object_id,rel,name,kind,size,added_at)"
                    " VALUES (?,?,?,?,?,?)",
                    (object_id, rel, f.name, kind, size, date.today().isoformat()))
        stats["files"] += 1
        stats["bytes"] += size
        if kind == "acts":
            stats["acts"] += 1
        elif kind == "photos":
            stats["photos"] += 1
    con.commit()
    con.close()
    return stats


def is_local(object_id: int) -> bool:
    con = core.connect()
    row = con.execute("SELECT folder FROM objects WHERE id=?", (object_id,)).fetchone()
    con.close()
    folder = (row["folder"] if row else "") or ""
    return str(ROOT) in folder


def migrate_object(object_id: int) -> dict:
    """Копирует папку объекта (в т.ч. Яндекс.Диск) в локальное хранилище."""
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    con.close()
    if not obj:
        return {"ok": False, "error": "Объект не найден"}
    src = obj["folder"] or ""
    if not src or not Path(src).exists():
        return {"ok": False, "error": "Папка объекта не найдена"}
    if str(ROOT) in str(src):
        return {"ok": True, "already": True, "files": len(files(object_id))}
    stats = import_folder(object_id, src)
    con = core.connect()
    con.execute("UPDATE objects SET folder=? WHERE id=?", (str(object_dir(object_id)), object_id))
    con.commit()
    con.close()
    return {"ok": True, "already": False, **stats}


def files(object_id: int, kind: str | None = None) -> list[dict]:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS object_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, rel TEXT, name TEXT,
        kind TEXT, size INTEGER, added_at TEXT, UNIQUE(object_id, rel))""")
    if kind:
        rows = con.execute("SELECT * FROM object_files WHERE object_id=? AND kind=? ORDER BY name",
                           (object_id, kind)).fetchall()
    else:
        rows = con.execute("SELECT * FROM object_files WHERE object_id=? ORDER BY kind, name",
                           (object_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]
