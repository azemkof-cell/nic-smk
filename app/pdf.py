# -*- coding: utf-8 -*-
"""Экспорт DOCX → PDF через установленный Microsoft Word."""
from __future__ import annotations

import subprocess
import threading
from pathlib import Path

from . import core

LOCK = threading.Lock()
PS1 = core.BASE / "tools" / "docx2pdf.ps1"


def _soffice() -> str:
    import shutil
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for path in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                 r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
                 "/usr/bin/libreoffice", "/usr/bin/soffice"):
        if Path(path).exists():
            return path
    return ""


def export(docx_path) -> Path | None:
    q = Path(docx_path)
    if not q.exists():
        return None
    pdf = q.with_suffix(".pdf")
    try:
        if pdf.exists() and pdf.stat().st_mtime >= q.stat().st_mtime and pdf.stat().st_size > 1000:
            return pdf
    except OSError:
        pass
    if not PS1.exists():
        return None
    before = pdf.stat().st_mtime if pdf.exists() else 0
    soffice = _soffice()
    with LOCK:
        if soffice:
            try:
                subprocess.run([soffice, "--headless", "--norestore", "--convert-to", "pdf",
                                "--outdir", str(q.parent), str(q)],
                               capture_output=True, timeout=240)
            except Exception:
                pass
        if not pdf.exists() or pdf.stat().st_mtime <= before:
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                     "-File", str(PS1), "-Docx", str(q), "-Pdf", str(pdf)],
                    capture_output=True, timeout=240)
            except Exception:
                return None
    if pdf.exists() and pdf.stat().st_size > 1000 and pdf.stat().st_mtime > before:
        return pdf
    return None


def pdf_for(file_rel: str) -> str:
    """Путь к PDF рядом с docx (если он существует)."""
    if not file_rel:
        return ""
    q = Path(core.BASE / file_rel).with_suffix(".pdf")
    if q.exists():
        try:
            return str(q.relative_to(core.BASE))
        except ValueError:
            return ""
    return ""
