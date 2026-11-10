# -*- coding: utf-8 -*-
"""ИИ-агенты: проект → записи → отчёт.

Работают в двух режимах:
  * LLM (если в настройках указан ключ API) — анализ записей и фотографий;
  * локальный (без ключа) — разбор записей правилами, чтобы отчёт всё равно собрался.
"""
from __future__ import annotations

import base64
import json
import re
import urllib.request
from datetime import date, datetime
from pathlib import Path

from . import core


class AIError(Exception):
    pass


def normalize_base(base: str) -> str:
    b = (base or "").strip().strip('"').rstrip("/")
    if not b:
        return b
    if not b.startswith("http"):
        b = "https://" + b
    for tail in ("/chat/completions", "/completions", "/models"):
        if b.endswith(tail):
            b = b[: -len(tail)].rstrip("/")
    return b


def cfg(profile: str = "text") -> dict:
    c = core.get_setting("ai", {}) or {}
    p = c.get(profile) or {}
    out = {
        "key": (p.get("key") or "").strip(),
        "base": normalize_base(p.get("base") or ""),
        "model": (p.get("model") or "").strip(),
    }
    # совместимость со старой единственной настройкой
    if not out["key"]:
        out["key"] = (c.get("key") or "").strip()
        out["base"] = out["base"] or normalize_base(c.get("base") or "")
        if profile == "text":
            out["model"] = out["model"] or (c.get("model") or "").strip()
    return out


def available(profile: str = "text") -> bool:
    return bool(cfg(profile).get("key"))


SYSTEM_PROMPT = (
    "Ты — эксперт строительного контроля и испытательной лаборатории в России. "
    "Работаешь с объектами благоустройства, дорогами, монолитом, инженерными сетями. "
    "Знаешь ГОСТ, СП, исполнительную документацию, акты КС-2, протоколы испытаний. "
    "Пиши по-русски, официальным деловым языком, кратко и по существу. "
    "Никогда не выдумывай цифры, адреса, номера и даты: если данных нет — оставь пусто. "
    "Если нужно вернуть JSON — верни только JSON без пояснений."
)


def chat(messages: list[dict], json_mode: bool = False, temperature: float = 0.2,
         timeout: int = 120, profile: str = "text") -> str:
    c = cfg(profile)
    key = (c.get("key") or "").strip()
    if not key:
        raise AIError("Не задан ключ ИИ для профиля «" + ("фото" if profile == "vision" else "текст") +
                      "» (Настройки → Искусственный интеллект)")
    base = (c.get("base") or "https://api.deepseek.com/v1").rstrip("/")
    msgs = list(messages)
    if not msgs or msgs[0].get("role") != "system":
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + msgs
    body = {"model": c.get("model") or "deepseek-chat", "messages": msgs,
            "temperature": temperature}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    req = urllib.request.Request(
        base + "/chat/completions",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": "Bearer " + key},
        method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return data["choices"][0]["message"]["content"]
    except Exception as e:
        raise AIError(f"Ошибка ИИ: {e}")


def _json_from(text: str) -> dict:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-z]*\s*|\s*```$", "", text, flags=re.S)
    a, b = text.find("{"), text.rfind("}")
    if a >= 0 and b > a:
        text = text[a:b + 1]
    try:
        return json.loads(text)
    except Exception:
        raise AIError("ИИ вернул ответ не в формате JSON")


# --------------------------------------------------------------------------
#  Агент 1. Проект: собирает контекст из документов на Яндекс.Диске
# --------------------------------------------------------------------------
def project_context(object_id: int, object_name: str, limit_docs: int = 6, limit_chars: int = 7000) -> str:
    docs = core.object_docs(object_id)
    if not docs:
        try:
            core.scan_object_docs(object_id, object_name)
            docs = core.object_docs(object_id)
        except Exception:
            docs = []
    parts, used = [], 0
    priority = {"docx": 0, "xlsx": 1, "txt": 2, "md": 2, "pdf": 3, "xls": 4}
    docs = sorted(docs, key=lambda d: priority.get((d.get("kind") or "").lower(), 9))
    for d in docs:
        if used >= limit_docs:
            break
        txt = core.doc_text(d["path"], limit_chars=3000)
        if not txt:
            continue
        parts.append(f"Документ «{d['title']}»:\n{txt}")
        used += 1
        if sum(len(p) for p in parts) > limit_chars:
            break
    return "\n\n".join(parts)[:limit_chars]


# --------------------------------------------------------------------------
#  Агент 2. Записи: нормализация и локальный разбор
# --------------------------------------------------------------------------
_WORK_WORDS = ("устройств", "укладк", "монтаж", "демонтаж", "разборк", "ремонт", "установк",
               "заливк", "бетонир", "асфальтир", "уплотн", "планировк", "выемк", "разработ",
               "прокладк", "сварк", "окраск", "оштукатур", "стяжк", "кровл", "изоляц", "замен")
_ISSUE_WORDS = ("замечан", "не соответств", "нарушен", "трещин", "брак", "дефект",
                "просадк", "отклонен", "не выполн", "загрязнен", "поврежд", "просроч")


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?;])\s+|\n+", text)
    return [p.strip(" .;") for p in parts if len(p.strip()) > 3]


def _is_issue(text: str) -> bool:
    low = text.lower()
    if any(x in low for x in ("замечаний нет", "без замечаний", "не выявлено",
                              "замечаний не", "соответствует", "замечаний по")):
        return False
    return any(w in low for w in _ISSUE_WORDS)


def offline_analysis(object_name: str, entries_list: list[dict], docs_text: str) -> dict:
    comments = [e.get("comment", "") for e in entries_list if (e.get("comment") or "").strip()]
    all_text = " ".join(comments)
    sents = _sentences(all_text)
    works, issues, seen = [], [], set()
    for s in sents:
        key = s.lower().strip(" .;")
        if key in seen:
            continue
        seen.add(key)
        if _is_issue(s):
            issues.append(s)
        elif any(w in s.lower() for w in _WORK_WORDS):
            works.append(s)
    if not works and sents:
        works = sents[:5]
    if not works:
        works = [f"Осмотр и фотофиксация объекта «{object_name}»"]
    summary = (f"В отчётном периоде на объекте {object_name} выполнялись работы, зафиксированные "
               f"специалистом строительного контроля. Выполнено: " + "; ".join(works[:6]) + ".")
    conclusion = (summary + " Замечаний, препятствующих приёмке работ, не выявлено."
                  if not issues else summary + " Выявлены замечания: " + "; ".join(issues[:4]) + ".")
    diary = []
    for e in entries_list:
        diary.append({
            "date": _short(e.get("edate")),
            "weather": "",
            "works": (e.get("comment") or "").strip()[:400] or "Осмотр объекта",
            "control": "Осмотр, фотофиксация, проверка объёмов и качества выполненных работ.",
            "note": "Есть замечания" if _is_issue(e.get("comment") or "") else "Замечаний нет",
        })
    return {
        "summary": summary,
        "works": [{"name": w, "unit": "", "note": ""} for w in works[:12]],
        "issues": issues[:10],
        "diary": diary,
        "conclusion": conclusion,
        "verdict": (f"Работы на объекте {object_name} считать выполненными в соответствии с проектной "
                    f"документацией и требованиями нормативных документов." if not issues
                    else f"Работы на объекте {object_name} требуют устранения замечаний."),
        "photo_notes": [],
    }


def _short(d) -> str:
    if not d:
        return ""
    s = str(d)
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").strftime("%d.%m.%Y")
    except Exception:
        return s


# --------------------------------------------------------------------------
#  Агент 3. Отчёт: LLM-анализ или локальный разбор
# --------------------------------------------------------------------------
SYSTEM = ("Ты — инженер строительного контроля в испытательной лаборатории ООО «НИЦ СМК». "
          "Пиши официальным русским языком, кратко и по делу. Не выдумывай объёмы, даты и марки, "
          "которых нет во входных данных. Если данных не хватает — не домысливай.")


def analyze(object_name: str, entries_list: list[dict], docs_text: str, period: str) -> dict:
    if not available():
        return offline_analysis(object_name, entries_list, docs_text)

    notes = []
    for i, e in enumerate(entries_list, 1):
        photos = e.get("photos") or []
        notes.append(f"{i}. Дата: {_short(e.get('edate'))}; автор: {e.get('author','')}; "
                     f"комментарий: {e.get('comment','')}; фото: {len(photos)} шт.")
    prompt = f"""Объект: {object_name}
Отчётный период: {period}

Записи специалиста с объекта:
{chr(10).join(notes) if notes else 'записей нет'}

Данные проектной документации (фрагменты):
{docs_text[:6000] if docs_text else 'документы не найдены'}

Сформируй данные для отчёта строительного контроля. Верни строго JSON:
{{
  "summary": "3-5 предложений: что сделано на объекте за период",
  "works": [{{"name": "вид работ", "unit": "ед. изм. или пусто", "note": "кратко"}}],
  "issues": ["выявленные замечания, если есть"],
  "diary": [{{"date": "дд.мм.гггг", "weather": "", "works": "что делали", "control": "что проверял инженер", "note": "замечаний нет / есть"}}],
  "conclusion": "2-4 предложения для раздела Заключение",
  "verdict": "1-2 предложения для раздела Вывод",
  "photo_notes": ["что видно на фото (по одному предложению на запись)"]
}}
Записей: {len(entries_list)}. Работы формулируй по комментариям, не придумывай новые."""
    text = chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}],
                json_mode=True, temperature=0.2)
    data = _json_from(text)
    data.setdefault("summary", "")
    data.setdefault("works", [])
    data.setdefault("issues", [])
    data.setdefault("diary", [])
    data.setdefault("conclusion", "")
    data.setdefault("verdict", "")
    data.setdefault("photo_notes", [])
    return data


def describe_photos(paths: list[str], object_name: str) -> str:
    """Анализ фотографий (нужна модель со зрением)."""
    c = cfg()
    if not c.get("vision"):
        raise AIError("В настройках не включена поддержка изображений (vision)")
    content = [{"type": "text", "text": f"Опиши, что видно на фотографиях объекта «{object_name}». "
                                        f"Кратко: виды работ, качество, дефекты."}]
    for p in paths[:6]:
        try:
            b = Path(p).read_bytes()
            content.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," +
                                                                     base64.b64encode(b).decode()}})
        except Exception:
            continue
    return chat([{"role": "system", "content": SYSTEM},
                 {"role": "user", "content": content}], temperature=0.2)


# --------------------------------------------------------------------------
#  Оркестратор: собирает отчёт из записей + проекта
# --------------------------------------------------------------------------
def build_report_payload(object_id: int, object_name: str, date_from: str, date_to: str,
                         specialist: str, customer: str = "", contract: str = "",
                         object_title: str = "", executor: str = "") -> tuple[dict, list[str]]:
    log: list[str] = []
    comp = core.company()

    ents = core.entries(object_id)
    if date_from and date_to:
        ents = [e for e in ents if str(e.get("edate") or "")[:10] >= str(date_from)[:10]
                and str(e.get("edate") or "")[:10] <= str(date_to)[:10]]
    log.append(f"Агент записей: найдено {len(ents)} записей, "
               f"фото {sum(len(e.get('photos') or []) for e in ents)}.")

    docs_text = project_context(object_id, object_name)
    log.append("Агент проекта: " + (f"прочитано документов на {len(docs_text)} символов."
                                   if docs_text else "документы проекта не найдены."))

    period = f"{_short(date_from)} — {_short(date_to)}"
    data = analyze(object_name, ents, docs_text, period)
    log.append("Агент отчёта: " + ("LLM" if available() else "локальный разбор")
               + f", работ {len(data.get('works') or [])}, замечаний {len(data.get('issues') or [])}.")

    photos = []
    for e in ents:
        for ph in e.get("photos") or []:
            path = ph.get("path") if isinstance(ph, dict) else ph
            if not path:
                continue
            photos.append({"path": path, "rel": (ph.get("rel") if isinstance(ph, dict) else ""),
                           "caption": (e.get("comment") or "")[:80],
                           "date": _short(e.get("edate"))})
    if len(photos) < 8:
        con = core.connect()
        row = con.execute("SELECT folder FROM objects WHERE id=?", (object_id,)).fetchone()
        con.close()
        folder = row["folder"] if row else ""
        if folder and Path(folder).exists():
            pics = []
            try:
                for f in Path(folder).rglob("*"):
                    if f.suffix.lower() in (".jpg", ".jpeg", ".png") and f.is_file():
                        pics.append(f)
            except Exception:
                pics = []
            pics.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            for f in pics[:8 - len(photos)]:
                photos.append({"path": str(f), "rel": "", "caption": "Фото из папки объекта", "date": ""})
    log.append(f"Фотофиксация: {len(photos)} фото.")

    works, seen_w = [], set()
    for w in data.get("works") or []:
        name = (w.get("name") or "").strip()
        key = name.lower()
        if name and key not in seen_w:
            seen_w.add(key)
            works.append({"name": name, "unit": (w.get("unit") or "").strip(),
                          "note": (w.get("note") or "").strip()})
    diary = data.get("diary") or []
    if not diary:
        diary = [{"date": _short(e.get("edate")), "weather": "", "works": e.get("comment", "")[:300],
                  "control": "Осмотр и фотофиксация.", "note": "Замечаний нет"} for e in ents]

    payload = {
        "mode": "field",
        "date_from": date_from, "date_to": date_to,
        "customer": customer or "",
        "executor": executor or comp.get("executor") or comp.get("name", ""),
        "object_title": object_title or object_name,
        "contract": contract or "",
        "address": object_name,
        "specialist": specialist,
        "ks": "", "ks_date": date_to,
        "acts": [],
        "works": works,
        "diary": diary,
        "tests": [],
        "passports": [],
        "description": (data.get("summary") or "").strip(),
        "issues_text": "; ".join(data.get("issues") or []),
        "conclusion": (data.get("conclusion") or "").strip(),
        "verdict": (data.get("verdict") or "").strip(),
        "photos": photos,
        "entries_count": len(ents),
        "ai_used": available(),
    }
    return payload, log


def _project_images(files) -> list[str]:
    import base64 as _b64
    import io
    from PIL import Image
    out = []
    for f in files:
        try:
            ext = f.suffix.lower()
            if ext == ".pdf":
                import pypdfium2 as _pdfium
                pdf = _pdfium.PdfDocument(str(f))
                page = pdf[0]
                im = page.render(scale=2.0).to_pil().convert("RGB")
                pdf.close()
            elif ext in (".jpg", ".jpeg", ".png", ".tif", ".tiff"):
                im = Image.open(f).convert("RGB")
            else:
                continue
            im.thumbnail((1400, 1400))
            buf = io.BytesIO()
            im.save(buf, "JPEG", quality=85)
            out.append(_b64.b64encode(buf.getvalue()).decode())
            if len(out) >= 4:
                break
        except Exception:
            continue
    return out


def classify_project(object_id: int) -> dict:
    """Читает документацию объекта и выделяет реквизиты и адреса."""
    if not available("text"):
        raise AIError("Для разбора документации нужен текстовый профиль ИИ")
    from . import extract as _ex
    con = core.connect()
    obj = con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone()
    con.close()
    if not obj:
        raise AIError("Объект не найден")
    folder = obj["folder"] or ""
    texts = []
    files = []
    seen = set()
    con = core.connect()
    try:
        for r in con.execute("SELECT path FROM object_docs WHERE object_id=?", (object_id,)).fetchall():
            fp = Path(r["path"])
            if fp.exists() and fp.suffix.lower() in (".pdf", ".docx", ".txt", ".bin") and fp not in seen:
                files.append(fp); seen.add(fp)
    except Exception:
        pass
    con.close()
    if folder and Path(folder).exists():
        for f in Path(folder).rglob("*"):
            try:
                if (f.is_file() and f.suffix.lower() in (".pdf", ".docx", ".txt")
                        and f.stat().st_size < 30 * 1024 * 1024 and f not in seen):
                    files.append(f); seen.add(f)
            except OSError:
                continue
            if len(files) >= 8:
                break
    for f in files:
        t = _ex._text_of(f)
        if t:
            texts.append(f"Документ «{f.name}»:\n{t[:4000]}")
    if not texts:
        imgs = _project_images(files)
        if not imgs or not available("vision"):
            raise AIError("В документах нет текстового слоя (сканы). Подключите профиль «Фото» — "
                          "тогда ИИ прочитает сканы.")
        vision_prompt = ("Ты специалист строительного контроля. Перед тобой страницы проектной документации. "
                         "Извлеки данные и верни JSON: {\"title\": \"полное наименование объекта\", "
                         "\"short_name\": \"краткое название до 60 символов\", \"address\": \"адрес\", "
                         "\"city\": \"город\", \"customer\": \"заказчик\", \"contractor\": \"подрядчик\", "
                         "\"contract\": \"номер и дата контракта\", \"addresses\": [\"адрес 1\"]}. "
                         "Не выдумывай того, чего не видно.")
        content = [{"type": "text", "text": vision_prompt}]
        for b64 in imgs[:4]:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:image/jpeg;base64," + b64}})
        raw = chat([{"role": "user", "content": content}], json_mode=True,
                   timeout=240, profile="vision")
        parsed = json.loads(raw)
        short = str(parsed.get("short_name") or "").strip()[:80]
        title = str(parsed.get("title") or "").strip()[:200]
        return {"title": title, "short_name": short or title[:80],
                "city": str(parsed.get("city") or "").strip()[:80],
                "address": str(parsed.get("address") or "").strip()[:200],
                "customer": str(parsed.get("customer") or "").strip()[:200],
                "contractor": str(parsed.get("contractor") or "").strip()[:200],
                "contract": str(parsed.get("contract") or "").strip()[:200],
                "addresses": [str(x).strip()[:200] for x in (parsed.get("addresses") or []) if str(x).strip()][:15],
                "docs": len(files), "ocr": True}
    prompt = ("Ты специалист строительного контроля. Прочитай проектную документацию и верни JSON: "
              "{\"title\": \"полное наименование объекта из документов\", "
              "\"short_name\": \"краткое название объекта до 60 символов, например Благоустройство Соборной площади\", "
              "\"address\": \"адрес\", "
              "\"customer\": \"заказчик\", \"contractor\": \"подрядчик\", "
              "\"contract\": \"номер и дата контракта\", \"city\": \"город\", "
              "\"addresses\": [\"адрес 1\", \"адрес 2\"]}. "
              "city — только название города без области и улиц. "
              "addresses — только если в документах перечислены несколько адресов/участков одного объекта. "
              "Не выдумывай, чего нет в тексте.\n\n" + "\n\n".join(texts)[:14000])
    raw = chat([{"role": "user", "content": prompt}], json_mode=True, timeout=180)
    parsed = json.loads(raw)
    short = str(parsed.get("short_name") or "").strip()[:80]
    title = str(parsed.get("title") or "").strip()[:200]
    return {"title": title, "short_name": short or title[:80],
            "city": str(parsed.get("city") or "").strip()[:80],
            "address": str(parsed.get("address") or "").strip()[:200],
            "customer": str(parsed.get("customer") or "").strip()[:200],
            "contractor": str(parsed.get("contractor") or "").strip()[:200],
            "contract": str(parsed.get("contract") or "").strip()[:200],
            "addresses": [str(x).strip()[:200] for x in (parsed.get("addresses") or []) if str(x).strip()][:15],
            "docs": len(files)}


def analyze_photo(object_id: int, rel: str, comment: str = "") -> dict:
    """Определяет, какие работы на фото, и делает подпись для отчёта."""
    if not available("vision"):
        raise AIError("Для анализа фото нужен профиль «Фото» в настройках ИИ")
    q = Path(rel)
    if not q.is_absolute():
        for base in (core.BASE, core.BASE / "data" / "files", core.BASE / "data" / "photos"):
            if (base / q).exists():
                q = base / q
                break
    if not q.exists():
        raise AIError("Файл фото не найден")
    con = core.connect()
    obj = con.execute("SELECT name,address,object_title FROM objects WHERE id=?", (object_id,)).fetchone()
    con.close()
    o = dict(obj) if obj else {}
    project = project_context(object_id, o.get("name") or "", limit_docs=3, limit_chars=2500)
    import io
    from PIL import Image
    im = Image.open(q).convert("RGB")
    im.thumbnail((1400, 1400))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    prompt = (
        "Ты специалист строительного контроля. Посмотри на фотографию с объекта. "
        "Определи, какие работы на ней ведутся (например: устройство песчаного основания, "
        "установка бортового камня, укладка асфальтобетона, армирование, бетонирование). "
        "Сверься с проектной документацией и описанием специалиста. "
        "Верни JSON: {\"work\": \"вид работ, 2-6 слов\", "
        "\"caption\": \"подпись к фото для отчёта, до 120 символов, с местом если известно\", "
        "\"confidence\": 0..1}. Не выдумывай того, чего не видно.\n"
        f"Объект: {o.get('object_title') or o.get('name') or ''}\nАдрес: {o.get('address') or ''}\n"
        f"Описание специалиста: {comment[:600]}\n"
        f"Проект (фрагменты): {project[:2000]}"
    )
    raw = chat([{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
    ]}], json_mode=True, timeout=180, profile="vision")
    parsed = json.loads(raw)
    return {"work": str(parsed.get("work") or "").strip()[:120],
            "caption": str(parsed.get("caption") or "").strip()[:200],
            "confidence": parsed.get("confidence")}


def read_photo(kind: str, rel: str) -> dict:
    """Распознаёт показания прибора/ведомости на фото и возвращает значения полей."""
    if not available("vision"):
        raise AIError("Для распознавания фото нужен ключ ИИ с поддержкой изображений "
                      "(Настройки → Искусственный интеллект → профиль «Фото»).")
    norms = core.NORMS.get(kind) or {}
    fields = norms.get("fields") or norms.get("meta") or []
    q = Path(rel)
    if not q.is_absolute():
        for base in (core.BASE, core.BASE / "data" / "files", core.BASE / "data" / "photos"):
            if (base / q).exists():
                q = base / q
                break
    if not q.exists():
        raise AIError("Файл фото не найден")
    import io
    from PIL import Image
    im = Image.open(q).convert("RGB")
    im.thumbnail((1400, 1400))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    b64 = base64.b64encode(buf.getvalue()).decode()
    keys = [{"key": f.get("key"), "name": f.get("name"), "unit": f.get("unit")} for f in fields]
    prompt = ("На фотографии — прибор или ведомость испытаний. Прочитай показания и верни JSON "
              "{\"values\": {ключ: число}} только для тех показателей, которые видно. "
              "Если не видно — не добавляй.\nПоказатели: " + json.dumps(keys, ensure_ascii=False))
    raw = chat([{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + b64}},
    ]}], json_mode=True, timeout=180, profile="vision")
    parsed = json.loads(raw)
    values = {}
    for k, v in (parsed.get("values") or {}).items():
        if any(k == f.get("key") for f in fields) and v not in (None, ""):
            values[k] = str(v)
    return {"values": values, "source": "ИИ по фото"}


def suggest_meta(kind: str, text: str, photo_count: int = 0) -> dict:
    """Подставляет значения показателей из текста записи специалиста."""
    norms = core.NORMS.get(kind) or {}
    fields = norms.get("fields") or norms.get("meta") or []
    values = {}
    source = "эвристика"
    if available() and text.strip():
        try:
            keys = [{"key": f.get("key"), "name": f.get("name"), "unit": f.get("unit")} for f in fields]
            prompt = ("Из текста записи специалиста извлеки значения показателей. "
                      "Верни JSON: {\"values\": {ключ: число}}. Только то, что явно есть в тексте.\n"
                      f"Показатели: {json.dumps(keys, ensure_ascii=False)}\n"
                      f"Запись: {text[:3000]}")
            parsed = json.loads(chat([{"role": "user", "content": prompt}], json_mode=True))
            for k, v in (parsed.get("values") or {}).items():
                if any(k == f.get("key") for f in fields) and v not in (None, ""):
                    values[k] = str(v)
            if values:
                source = "ИИ"
        except Exception:
            values = {}
    if not values:
        import re
        used = set()
        for f in fields:
            unit = (f.get("unit") or "").strip()
            key = f.get("key")
            if not unit or key in values:
                continue
            pat = re.compile(r"([0-9]+(?:[.,][0-9]+)?)\s*" + re.escape(unit).replace("\\ ", "\\s*"), re.I)
            m = pat.search(text)
            if m:
                val = m.group(1).replace(",", ".")
                values[key] = val
                used.add(unit)
        if not values and kind == "concrete":
            loads = re.findall(r"([0-9]{3}(?:[.,][0-9]+)?)\s*кН", text, re.I)
            if loads:
                values["loads"] = "; ".join(x.replace(",", ".") for x in loads[:3])
    return {"values": values, "source": source, "text": text[:2000], "photos": photo_count}


def build_final_payload(object_id: int) -> dict:
    """Тексты разделов итогового отчёта: из документов объекта и записей специалиста."""
    from . import ks2, storage

    con = core.connect()
    obj = dict(con.execute("SELECT * FROM objects WHERE id=?", (object_id,)).fetchone() or {})
    ents = [dict(r) for r in con.execute(
        "SELECT * FROM entries WHERE object_id=? ORDER BY edate", (object_id,))]
    protocols = [dict(r) for r in con.execute(
        "SELECT number,pdate,kind FROM protocols WHERE object_name LIKE ? ORDER BY pdate",
        (f"%{(obj.get('name') or '')[:40]}%",))]
    con.close()

    for e in ents:
        try:
            e["photos"] = json.loads(e["photos"]) if isinstance(e.get("photos"), str) else (e.get("photos") or [])
        except Exception:
            e["photos"] = []

    works = ks2.period_works(object_id, "", date.today().isoformat())
    docs = storage.files(object_id, "docs")
    passports = [d["name"] for d in docs if any(
        k in d["name"].lower() for k in ("паспорт", "сертификат", "декларац", "свидетельств"))]
    defects = [e for e in ents if "дефект" in (e.get("tags") or "").lower()]
    comments = [str(e.get("comment") or "").strip() for e in ents if str(e.get("comment") or "").strip()]

    context_parts = [f"Объект: {obj.get('object_title') or obj.get('name')}",
                     f"Адрес: {obj.get('address') or ''}",
                     f"Заказчик: {obj.get('customer') or ''}",
                     f"Подрядчик: {obj.get('contractor') or ''}",
                     f"Контракт: {obj.get('contract') or ''}"]
    if comments:
        context_parts.append("Записи специалиста:\n" + "\n".join("- " + c[:400] for c in comments[:40]))
    if works:
        context_parts.append("Работы по КС-2:\n" + "\n".join(
            f"- {w['name']} ({w['unit']}): {w['total']:.2f}" for w in works[:30]))
    if protocols:
        context_parts.append("Протоколы испытаний:\n" + "\n".join(
            f"- №{p['number']} от {p['pdate']} ({core.DOC_KINDS.get(p['kind'], {}).get('label', p['kind'])})"
            for p in protocols[:20]))
    if passports:
        context_parts.append("Паспорта и сертификаты:\n" + "\n".join("- " + p for p in passports[:20]))
    if docs:
        context_parts.append("Документы ИД:\n" + "\n".join("- " + d["name"] for d in docs[:25]))
    project = project_context(object_id, obj.get("name") or "")
    if project:
        context_parts.append("Тексты документов:\n" + project[:6000])
    context = "\n\n".join(context_parts)[:14000]

    result = {}
    if available() and context.strip():
        try:
            prompt = (
                "Ты — специалист строительного контроля. Заполни разделы итогового отчёта "
                "ТОЛЬКО по предоставленным материалам, без выдумок. Верни JSON с ключами: "
                "intro (2-4 предложения: что за объект, кто участники, что делалось), "
                "works (2-5 предложений о выполненных работах и объёмах), "
                "tests (1-3 предложения о результатах испытаний), "
                "defects (1-3 предложения о замечаниях или что их нет), "
                "passports (1-2 предложения о паспортах/сертификатах), "
                "conclusion (2-3 предложения: соответствие/несоответствие, что подтвердить).\n\n"
                "Материалы:\n" + context
            )
            raw = chat([{"role": "user", "content": prompt}], json_mode=True)
            parsed = json.loads(raw)
            for k in ("intro", "works", "tests", "defects", "passports", "conclusion"):
                if parsed.get(k):
                    result[k] = str(parsed[k]).strip()
        except Exception:
            result = {}

    if not result:
        period = f"с {obj.get('report_start')} по {date.today().isoformat()}" if obj.get("report_start") else "на " + date.today().isoformat()
        result["intro"] = (
            f"Объект: {obj.get('object_title') or obj.get('name')}. "
            f"Заказчик — {obj.get('customer') or 'не указан'}, подрядчик — {obj.get('contractor') or 'не указан'}. "
            f"Строительный контроль выполнялся {period}. "
            f"Специалистом СК зафиксировано {len(ents)} записей и {sum(len(e['photos']) for e in ents)} фотоматериалов.")
        if comments:
            result["works"] = ("По записям специалиста выполнялись: " +
                               "; ".join(c[:160] for c in comments[:4]) +
                               f". По актам КС-2 учтено {len(works)} видов работ.")
        else:
            result["works"] = (f"По актам КС-2 учтено {len(works)} видов работ." if works
                               else "Сведения о выполненных работах в материалах отсутствуют.")
        if protocols:
            result["tests"] = "Испытания проводились: " + "; ".join(
                f"№{p['number']} от {p['pdate']}" for p in protocols[:6]) + "."
        else:
            result["tests"] = "Протоколы испытаний по объекту в материалах не обнаружены."
        result["defects"] = ("Выявлены замечания: " + "; ".join(d.get("comment", "")[:160] for d in defects[:4]) + "."
                             if defects else "Замечаний и предписаний не зафиксировано.")
        result["passports"] = ("В материалах есть паспорта и сертификаты: " + "; ".join(passports[:6]) + "."
                               if passports else "Паспорта и сертификаты в материалах не обнаружены.")
        result["conclusion"] = (
            "Выполненные работы соответствуют проектной документации и требованиям нормативных документов; "
            "замечаний не выявлено." if not defects else
            "Выявленные замечания подлежат устранению; после устранения работы считаются соответствующими проекту.")
    result["stats"] = {"entries": len(ents), "photos": sum(len(e["photos"]) for e in ents),
                       "works": len(works), "protocols": len(protocols), "defects": len(defects),
                       "docs": len(docs), "passports": len(passports)}
    result["used_llm"] = bool(available())
    return result


def build_email_letter(object_name: str, report_number: str, period: str,
                       customer: str, sender: str) -> dict:
    """Письмо заказчику по шаблону (ИИ, если подключён)."""
    subject = f"Отчёт по строительному контролю № {report_number} — {object_name}"
    body = (
        f"Уважаемые коллеги!\n\n"
        f"Направляем отчёт по строительному контролю № {report_number} по объекту "
        f"«{object_name}» за период {period}.\n\n"
        f"В отчёте: выполненные работы и объёмы, исполнительная документация, "
        f"результаты испытаний, замечания и фотофиксация.\n\n"
        f"Приложения: отчёт в формате PDF и DOCX.\n\n"
        f"С уважением,\n{sender}\n"
    )
    if available():
        try:
            prompt = ("Напиши официальное сопроводительное письмо заказчику строительного контроля. "
                      "Коротко: что направляем, за какой период, что внутри, просьба рассмотреть. "
                      "Без выдумок. Верни JSON {subject, body}.\n"
                      f"Объект: {object_name}\nЗаказчик: {customer}\nОтчёт №: {report_number}\n"
                      f"Период: {period}\nОтправитель: {sender}")
            parsed = json.loads(chat([{"role": "user", "content": prompt}], json_mode=True))
            if parsed.get("subject"):
                subject = parsed["subject"]
            if parsed.get("body"):
                body = parsed["body"]
        except Exception:
            pass
    return {"subject": subject, "body": body}
