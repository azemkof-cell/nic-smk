# -*- coding: utf-8 -*-
"""Резервные копии данных программы."""
from __future__ import annotations

import shutil
import zipfile
from datetime import datetime
from pathlib import Path

from . import core

BACKUP_DIR = core.BASE / "backups"


def create_backup() -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    out = BACKUP_DIR / f"nic-smk-{stamp}.zip"
    include = [
        core.BASE / "data" / "app.db",
        core.BASE / "data" / "files",
        core.BASE / "data" / "photos",
        core.BASE / "data" / "storage",
        core.BASE / "data" / "branding",
        core.BASE / "Документы",
    ]
    tmp = BACKUP_DIR / f".tmp-{stamp}"
    if tmp.exists():
        shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    for src in include:
        if not src.exists():
            continue
        dst = tmp / src.relative_to(core.BASE)
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.is_dir():
            shutil.copytree(src, dst, dirs_exist_ok=True,
                            ignore=shutil.ignore_patterns("*.lock", "*.tmp", "ep*"))
        else:
            shutil.copy2(src, dst)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in tmp.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(tmp))
    shutil.rmtree(tmp, ignore_errors=True)
    keep = int((core.get_setting("backup", {}) or {}).get("keep") or 14)
    files = sorted(BACKUP_DIR.glob("nic-smk-*.zip"))
    for old in files[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    return {"file": str(out), "name": out.name, "size": out.stat().st_size}


def list_backups() -> list[dict]:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for f in sorted(BACKUP_DIR.glob("nic-smk-*.zip"), reverse=True):
        rows.append({"name": f.name, "size": f.stat().st_size,
                     "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat(timespec="minutes")})
    return rows
