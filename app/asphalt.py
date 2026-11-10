# -*- coding: utf-8 -*-
"""Асфальтобетон: модель протокола как в реальных документах НИЦ СМК.

Зерновой состав + физические + эксплуатационные показатели.
Нормативы — по ГОСТ 58406.2-2020 для смеси типа А (как в протоколе №2855.11/26).
"""
from __future__ import annotations

import random

SIEVES = ["22,4", "16,0", "11,2", "8,0", "5,6", "4,0", "2,0", "1,0", "0,5", "0,25", "0,125", "0,063", "<0,063"]

GOST_MIN = [100, 100, 100, 90, 70, 52, 35, None, None, None, 8, 6, None]
GOST_MAX = [100, 100, 100, 100, 90, 75, 60, None, None, None, 22, 12, None]
RECIPE = [100, 100, 100, 99.8, 88.0, 70.8, 45.9, None, None, None, 14.0, 11.0, None]
PDO = [None, None, None, None, 6, 6, 6, None, None, None, 4, 4, None]

PHYSICAL = [
    # key, наименование, норма (текст/диапазон), рецепт, ПДО, единица
    ("binder_over", "Содержание вяжущего, % сверх 100%", None, 6.0, None, "%"),
    ("pb", "Содержание вяжущего Pb, % от массы смеси", None, 5.7, 0.5, "%"),
    ("gmm", "Максимальная плотность смеси Gmm, г/см3", None, 2.723, None, "г/см3"),
    ("gmb", "Объемная плотность Gmb, г/см3", None, 2.654, None, "г/см3"),
    ("pa", "Содержание воздушных пустот Pa, % от объема", (1.5, 4.5), 2.53, 1.4, "%"),
    ("pmz", "Пустоты в минеральном заполнителе (ПМЗ), %", (14.0, None), 17.091, None, "%"),
    ("pnb", "Пустоты, наполненные битумным вяжущим (ПНБ), %", (75.0, 90.0), 85.17, None, "%"),
]

OPERATIONAL = [
    ("rut", "Средняя глубина колеи при температуре испытания 60 °C, мм", (None, 7.0), 4.7, "мм"),
    ("water", "Коэффициент водостойкости при содержании воздушных пустот (6,0±0,5), %", (0.85, None), 0.88, ""),
]

ND = "ГОСТ 58406.2-2020"

EQUIPMENT = ("весы OHAUS Adventurer ARC120; шкаф сушильный ШС-80-01; вакуумный пикнометр ВП-10; "
             "уплотнитель Маршалла автоматический AYM; набор сит")
CONDITIONS = "Т- 21 °C, W- 45%"


def _rng(lo, hi):
    return random.uniform(lo, hi)


def default_meta() -> dict:
    return {
        "customer": "",
        "customer_address": "",
        "object_name": "",
        "contractor": "",
        "material": "а/б смесь А8Вл",
        "purpose": "Верхний слой",
        "sampled_at": "",
        "manufacturer": "",
        "recipe": "",
        "nd": ND,
        "grain": ["" for _ in SIEVES],
        "physical": {k: "" for k, *_ in PHYSICAL},
        "operational": {k: "" for k, *_ in OPERATIONAL},
    }


def random_meta(meta: dict | None = None) -> dict:
    """Правдоподобные значения в допусках — для внутренних экземпляров."""
    m = dict(meta or {})
    m.setdefault("material", "а/б смесь А8Вл")
    m.setdefault("purpose", "Верхний слой")
    m.setdefault("nd", ND)
    m.setdefault("equipment", EQUIPMENT)
    m.setdefault("conditions", CONDITIONS)

    grain = []
    for i, sieve in enumerate(SIEVES):
        base = RECIPE[i]
        if base is None:
            grain.append("")
            continue
        dev = PDO[i] or 2.0
        val = base + _rng(-dev * 0.75, dev * 0.75)
        if sieve in ("22,4", "16,0", "11,2"):
            val = 100.0
        lo, hi = GOST_MIN[i], GOST_MAX[i]
        if lo is not None and val < lo:
            val = lo + abs(_rng(0, 0.5))
        if hi is not None and val > hi:
            val = hi - abs(_rng(0, 0.5))
        grain.append(round(max(0.0, min(100.0, val)), 1))
    m["grain"] = grain

    phys = {}
    for key, name, norm, recipe, pdo, unit in PHYSICAL:
        if norm and pdo:
            lo, hi = norm[0], norm[1]
            if lo is not None and hi is not None:
                phys[key] = round(_rng(lo + (hi - lo) * 0.2, hi - (hi - lo) * 0.2), 2)
            elif lo is not None:
                phys[key] = round(lo + _rng(1.0, 3.0), 3)
            else:
                phys[key] = round(hi - _rng(0.5, 2.0), 3)
        elif key == "pb":
            phys[key] = round(recipe + _rng(-0.35, 0.35), 1)
        elif key in ("gmm", "gmb"):
            phys[key] = round(recipe + _rng(-0.03, 0.02), 3)
        elif key == "binder_over":
            phys[key] = round(recipe + _rng(0.5, 1.2), 1)
        else:
            phys[key] = round(recipe, 3)
    m["physical"] = phys

    ops = {}
    for key, name, norm, recipe, unit in OPERATIONAL:
        lo, hi = norm
        if lo is not None:
            ops[key] = round(lo + _rng(0.02, 0.12), 2)
        else:
            ops[key] = round(hi - _rng(1.5, 2.5), 1)
    m["operational"] = ops
    return m


def _fmt(v, nd=1) -> str:
    if v in (None, ""):
        return "—"
    try:
        f = float(str(v).replace(",", "."))
    except ValueError:
        return str(v)
    s = f"{f:.{nd}f}".rstrip("0").rstrip(".")
    return (s or "0").replace(".", ",")


def _norm_text(norm, unit="") -> str:
    if not norm:
        return "не нормируется"
    lo, hi = norm
    if lo is not None and hi is not None:
        if abs(float(lo) - float(hi)) < 1e-9:
            return _fmt(lo)
        return f"от {_fmt(lo)} до {_fmt(hi)}"
    if lo is not None:
        return f"не менее {_fmt(lo)}"
    return f"не более {_fmt(hi)}"


def calc(meta: dict) -> dict:
    """Возвращает данные таблиц, соответствие и заключение."""
    meta = dict(meta or {})
    grain_vals = list(meta.get("grain") or [])
    grain_vals += [""] * (len(SIEVES) - len(grain_vals))

    grain_rows = []
    ok = True
    for i, sieve in enumerate(SIEVES):
        raw = grain_vals[i]
        try:
            fact = float(str(raw).replace(",", ".")) if str(raw).strip() else None
        except ValueError:
            fact = None
        rec = RECIPE[i]
        pdo = PDO[i]
        dev = None
        if fact is not None and rec is not None:
            dev = round(fact - rec, 1)
        gmin, gmax = GOST_MIN[i], GOST_MAX[i]
        if fact is not None:
            if gmin is not None and fact < gmin - 0.01:
                ok = False
            if gmax is not None and fact > gmax + 0.01:
                ok = False
        grain_rows.append({
            "sieve": sieve,
            "gost": (_norm_text((gmin, gmax)) if (gmin is not None or gmax is not None) else "—"),
            "recipe": _fmt(rec),
            "pdo": (f"±{_fmt(pdo)}" if pdo else "—"),
            "fact": _fmt(fact),
            "dev": (f"{dev:+.1f}".replace(".", ",") if dev is not None else "—"),
        })

    phys_rows = []
    for key, name, norm, recipe, pdo, unit in PHYSICAL:
        val = (meta.get("physical") or {}).get(key)
        try:
            f = float(str(val).replace(",", ".")) if str(val).strip() else None
        except ValueError:
            f = None
        good = True
        if f is not None and norm:
            lo, hi = norm
            if lo is not None and f < lo - 1e-9:
                good = False
            if hi is not None and f > hi + 1e-9:
                good = False
        ok = ok and good
        phys_rows.append({
            "name": name, "norm": _norm_text(norm), "recipe": _fmt(recipe, 3),
            "pdo": (f"±{_fmt(pdo)}" if pdo else "—"), "fact": _fmt(f, 3 if unit == "г/см3" else 2),
            "ok": good,
        })

    op_rows = []
    for key, name, norm, recipe, unit in OPERATIONAL:
        val = (meta.get("operational") or {}).get(key)
        try:
            f = float(str(val).replace(",", ".")) if str(val).strip() else None
        except ValueError:
            f = None
        good = True
        if f is not None:
            lo, hi = norm
            if lo is not None and f < lo - 1e-9:
                good = False
            if hi is not None and f > hi + 1e-9:
                good = False
        ok = ok and good
        op_rows.append({"name": name, "norm": _norm_text(norm), "fact": _fmt(f, 2), "ok": good})

    material = (meta.get("material") or "асфальтобетонная смесь").strip()
    conclusion = (f"{material} {'соответствует' if ok else 'не соответствует'} "
                  f"требованиям {meta.get('nd') or ND}")
    return {"grain": grain_rows, "physical": phys_rows, "operational": op_rows,
            "ok": ok, "conclusion": conclusion}
