# -*- coding: utf-8 -*-
"""Исполнительная схема по точкам съёмки (CSV/TXT) — разбор, чертёж, документ."""
from __future__ import annotations

import math
import re
from datetime import date
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Cm, Mm, Pt

from . import core
from .docs import _cell_text, _margins, _para, _set_run, _widths, ru_date
from .protocol_docs import _flat, _footer, _header, _line, _signatures


def parse_points(path: str) -> list[dict]:
    q = Path(path)
    if not q.exists():
        return []
    text = ""
    for enc in ("utf-8-sig", "utf-8", "cp1251"):
        try:
            text = q.read_text(encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    points = []
    for line in text.splitlines():
        if not line.strip() or line.strip().startswith(("#", "//")):
            continue
        parts = [x.strip() for x in re.split(r"[;\t]", line) if x.strip()]
        vals, name = [], ""
        num_re = re.compile(r"^-?\d+(?:[.,]\d+)?$")
        if sum(1 for x in parts if num_re.match(x)) >= 2:
            for x in parts:
                if num_re.match(x):
                    vals.append(float(x.replace(",", ".")))
                elif not name:
                    name = x
        else:
            mnum = re.search(r"-?\d+(?:[.,]\d+)?", line)
            if not mnum:
                continue
            name = line[:mnum.start()].strip(" ;,\t")
            for n in re.findall(r"-?\d+(?:[.,]\d+)?", line[mnum.start():]):
                try:
                    vals.append(float(n.replace(",", ".")))
                except ValueError:
                    pass
        if len(vals) < 2:
            continue
        points.append({"name": name or f"т.{len(points) + 1}", "x": vals[0], "y": vals[1],
                       "z": vals[2] if len(vals) > 2 else None})
    return points


def draw_schema(points: list[dict], out_png: Path, title: str = "") -> Path:
    from PIL import Image, ImageDraw, ImageFont
    W, H = 1600, 1100
    margin = 110
    img = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 22)
        small = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 18)
    except Exception:
        font = small = ImageFont.load_default()

    xs = [p["x"] for p in points] or [0, 1]
    ys = [p["y"] for p in points] or [0, 1]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    dx = (maxx - minx) or 1
    dy = (maxy - miny) or 1
    scale = min((W - 2 * margin) / dx, (H - 2 * margin) / dy)

    def to_px(x, y):
        px = margin + (x - minx) * scale
        py = H - margin - (y - miny) * scale
        return px, py

    # сетка
    for i in range(11):
        gx = margin + (W - 2 * margin) * i / 10
        gy = margin + (H - 2 * margin) * i / 10
        d.line([(gx, margin), (gx, H - margin)], fill=(225, 230, 238), width=1)
        d.line([(margin, gy), (W - margin, gy)], fill=(225, 230, 238), width=1)

    pts = [to_px(p["x"], p["y"]) for p in points]
    if len(pts) > 1:
        d.line(pts, fill=(47, 95, 208), width=4, joint="curve")
    for i, (px, py) in enumerate(pts):
        r = 7
        d.ellipse([px - r, py - r, px + r, py + r], fill=(180, 35, 35), outline="white", width=2)
        d.text((px + 10, py - 26), str(i + 1), fill=(30, 30, 30), font=small)

    # подписи осей и масштаб
    d.text((margin, H - margin + 12), f"X: {minx:.2f} … {maxx:.2f}", fill=(60, 60, 60), font=small)
    d.text((margin, H - margin + 38), f"Y: {miny:.2f} … {maxy:.2f}", fill=(60, 60, 60), font=small)
    # масштабная линейка 10 м
    bar_m = 10
    bar_px = bar_m * scale
    if 40 < bar_px < 400:
        x0, y0 = W - margin - bar_px, H - margin + 30
        d.line([(x0, y0), (x0 + bar_px, y0)], fill="black", width=3)
        d.text((x0, y0 - 26), f"{bar_m} м", fill="black", font=small)

    if title:
        d.text((margin, 24), title[:90], fill=(20, 30, 50), font=font)
    out_png.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_png)
    return out_png


def build(record: dict, points: list[dict], out_path: Path) -> Path:
    comp = core.company()
    doc = Document()
    s = doc.sections[0]
    s.page_width = Mm(210); s.page_height = Mm(297)
    s.left_margin = Mm(15); s.right_margin = Mm(12)
    s.top_margin = Mm(10); s.bottom_margin = Mm(12)
    st = doc.styles["Normal"]
    st.font.name = "Times New Roman"; st.font.size = Pt(10)
    _footer(doc, False)
    _header(doc, comp)

    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(2)
    r = p.add_run("ИСПОЛНИТЕЛЬНАЯ СХЕМА"); _set_run(r, 13, bold=True)
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_after = Pt(8)
    r = p.add_run(record.get("object_name", "")); _set_run(r, 10.5, bold=True)

    for label, value in (
        ("Заказчик", record.get("customer", "")),
        ("Адрес объекта", record.get("address") or record.get("object_name", "")),
        ("Вид работ", record.get("work", "")),
        ("Дата съёмки", record.get("survey_date", "")),
        ("Исполнитель съёмки", record.get("author", "")),
        ("Система координат", record.get("crs", "МСК")),
    ):
        if not (value or "").strip():
            continue
        p = doc.add_paragraph(); p.paragraph_format.space_after = Pt(1)
        r = p.add_run(label + ": "); _set_run(r, 10, bold=True)
        r = p.add_run(value); _set_run(r, 10)

    p = doc.add_paragraph(); p.paragraph_format.space_before = Pt(8); p.paragraph_format.space_after = Pt(3)
    r = p.add_run("Ведомость точек съёмки"); _set_run(r, 10.5, bold=True)

    t = doc.add_table(rows=1, cols=5)
    t.style = "Table Grid"
    for i, h in enumerate(["№", "Обозначение", "X, м", "Y, м", "Отметка Z, м"]):
        _cell_text(t.rows[0].cells[i], h, 8.5, bold=True, align=WD_ALIGN_PARAGRAPH.CENTER)
    for i, pt in enumerate(points, 1):
        cells = t.add_row().cells
        vals = [str(i), pt["name"], f"{pt['x']:.3f}", f"{pt['y']:.3f}",
                (f"{pt['z']:.3f}" if pt.get("z") is not None else "—")]
        for j, v in enumerate(vals):
            _cell_text(cells[j], v, 8.5,
                       align=WD_ALIGN_PARAGRAPH.LEFT if j == 1 else WD_ALIGN_PARAGRAPH.CENTER)
    _widths(t, [0.9, 5.4, 3.6, 3.6, 3.4])
    _margins(t, 20, 20, 40, 40)

    png = out_path.with_suffix(".png")
    draw_schema(points, png, f"{record.get('object_name','')[:70]}")
    p = doc.add_paragraph(); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(10)
    try:
        p.add_run().add_picture(str(png), width=Cm(17.4))
    except Exception:
        pass

    _signatures(doc, comp, record)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out_path))
    return out_path
