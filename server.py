# -*- coding: utf-8 -*-
"""Локальный сервер программы «НИЦ СМК · Автоматизация документов».

Запуск:  python server.py   (или файл «Запуск.bat»)
Открывается браузер: http://127.0.0.1:8765
"""
from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import socket
import sys
import threading
import time
import traceback
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, urlparse

from app import acts_doc, ai, archive, asphalt, autoreport, backup, core, defects_doc, docs, extract, final_report, kp, ks2, pdf, protocol_docs, reportgen, send, storage, survey

BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
PORT = int(os.environ.get("SMK_PORT", "8765"))


def safe_name(name: str) -> str:
    name = re.sub(r"[\\/:*?\"<>|]+", "-", name or "")
    name = re.sub(r"\s+", " ", name).strip()
    return name[:120] or "документ"


class LocalServer(ThreadingHTTPServer):
    """Запрещаем два процесса на одном порту (в Windows SO_REUSEADDR это позволяет)."""
    allow_reuse_address = False


class Handler(BaseHTTPRequestHandler):
    server_version = "SMK/1.0"

    # ------------------------------------------------------------------ utils
    def log_message(self, fmt, *args):  # тише в консоли
        pass

    def _json(self, obj, status=200, cookie=None):
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        gzip_ok = "gzip" in (self.headers.get("Accept-Encoding") or "") and len(body) > 1500
        if gzip_ok:
            import gzip as _gzip
            body = _gzip.compress(body, 5)
        self.send_response(status)
        if gzip_ok:
            self.send_header("Content-Encoding", "gzip")
            self.send_header("Vary", "Accept-Encoding")
        self.send_header("Content-Type", "application/json; charset=utf-8")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _err(self, message, status=400):
        self._json({"ok": False, "error": message}, status)

    def _read_json(self):
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            return {}

    def _png(self, data: bytes):
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _file(self, path: Path, download_name: str | None = None):
        if not path.exists() or not path.is_file():
            self._err("Файл не найден", 404)
            return
        data = path.read_bytes()
        ctype = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
        if path.suffix.lower() == ".webmanifest":
            ctype = "application/manifest+json"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        if path.suffix.lower() in (".css", ".js", ".html"):
            self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Content-Length", str(len(data)))
        if download_name:
            fn = quote(download_name)
            fallback = "document" + (path.suffix.lower() or ".bin")
            self.send_header("Content-Disposition",
                             f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{fn}")
        self.end_headers()
        self.wfile.write(data)

    # ------------------------------------------------------------------- HTTP
    def _audit(self, path, payload):
        try:
            keep = {}
            for k in ("name", "number", "object_name", "kind", "id", "to", "channel",
                      "action", "type", "freq", "status"):
                if isinstance(payload, dict) and payload.get(k) not in (None, ""):
                    keep[k] = str(payload.get(k))[:80]
            core.add_audit(getattr(self, "user", None), path.replace("/api/", ""),
                           keep.get("object_name") or keep.get("name") or "",
                           int(keep.get("id") or 0),
                           ", ".join(f"{k}={v}" for k, v in keep.items()))
        except Exception:
            pass

    def _signer(self):
        return _signer(self)

    def _auth_gate(self, path):
        if path in PUBLIC_PATHS or path.startswith("/static") or path in ("/", "/index.html"):
            return False
        if not _users_exist():
            return False
        user = _cookie_user(self)
        if not user:
            self._err("Требуется вход в программу", 401)
            return True
        self.user = user
        return False

    def do_GET(self):
        try:
            url = urlparse(self.path)
            path = url.path
            qs = parse_qs(url.query)
            if self._auth_gate(path):
                return
            if path == "/sw.js":
                return self._file(STATIC / "sw.js")
            if path == "/manifest.webmanifest":
                return self._file(STATIC / "manifest.webmanifest")
            if path in ("/", "/index.html"):
                return self._file(STATIC / "index.html")
            if path.startswith("/static/"):
                return self._file(STATIC / path[len("/static/"):])
            if path == "/api/file":
                rel = (qs.get("f") or [""])[0]
                target = (core.DATA / "files" / rel).resolve()
                if not str(target).startswith(str((core.DATA / "files").resolve())):
                    return self._err("Нет доступа", 403)
                inline = (qs.get("inline") or ["0"])[0] == "1"
                return self._file(target, download_name=None if inline else target.name)
            if path == "/api/object/works":
                oid = int((qs.get("id") or ["0"])[0] or 0)
                return self._json({"ok": True, "items": ks2.list_works(oid)})
            if path == "/api/object":
                oid = int((qs.get("id") or ["0"])[0] or 0)
                con = core.connect()
                row = con.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
                con.close()
                if not row:
                    return self._err("Объект не найден", 404)
                obj = dict(row)
                docs = core.object_docs(oid)
                ents = core.entries(oid)
                data = {
                    "object": obj,
                    "docs": docs[:150],
                    "docs_total": len(docs),
                    "entries": ents[:150],
                    "entries_total": len(ents),
                }
                return self._json({"ok": True, "data": data})
            if path == "/api/numbering":
                return self._json({"ok": True, "data": {
                    "numbering": core.numbering_state(), "kinds": core.NUMBER_KINDS,
                    "log": core.number_log(40),
                    "synced_at": core.get_setting("numbering_synced_at", "")}})
            if path == "/api/archive":
                q = (qs.get("q") or [""])[0]
                return self._json({"ok": True, "items": archive.search(q)})
            if path == "/api/archive/file":
                target = Path((qs.get("path") or [""])[0]).resolve()
                if not str(target).startswith(str(BASE.parent.resolve())):
                    return self._err("Нет доступа", 403)
                return self._file(target, download_name=target.name)
            if path == "/api/audit":
                user = _cookie_user(self)
                if not user or not user_is_admin(user):
                    return self._err("Журнал доступен администратору", 403)
                q = (qs.get("q") or [""])[0]
                return self._json({"ok": True, "items": core.audit_list(200, q),
                                   "enabled": (core.get_setting("audit", {}) or {}).get("enabled", True)})
            if path == "/api/settings/mail":
                smtp = dict(core.get_setting("smtp", {}) or {})
                if smtp.get("password"):
                    smtp["password"] = "***"
                return self._json({"ok": True, "smtp": smtp,
                                   "messenger": core.get_setting("messenger", {}) or {}})
            if path == "/api/object/defects":
                oid = int((qs.get("id") or ["0"])[0] or 0)
                con = core.connect()
                rows = [dict(r) for r in con.execute(
                    "SELECT * FROM entries WHERE object_id=? ORDER BY edate, id", (oid,))]
                con.close()
                items = []
                for r in rows:
                    if "дефект" in (r.get("tags") or "").lower():
                        try:
                            r["photos"] = json.loads(r.get("photos") or "[]")
                        except Exception:
                            r["photos"] = []
                        items.append(r)
                return self._json({"ok": True, "items": items})
            if path == "/api/backup/list":
                return self._json({"ok": True, "items": backup.list_backups(),
                                   "dir": str(backup.BACKUP_DIR)})
            if path == "/api/kp/list":
                return self._kp_list({})
            if path == "/api/fs/list":
                cur = (qs.get("path") or [""])[0] or str(core.BASE.parent / "РАБОЧАЯ" / "СТРОИТЕЛЬНЫЙ КОНТРОЛЬ" / "2026")
                pth = Path(cur)
                allowed_root = core.BASE.parent / "РАБОЧАЯ"
                try:
                    pth.resolve().relative_to(allowed_root.resolve())
                except Exception:
                    return self._err("Путь вне рабочей папки", 403)
                if not pth.exists() or not pth.is_dir():
                    return self._err("Папка не найдена")
                con = core.connect()
                linked = {r["folder"]: r["id"] for r in con.execute(
                    "SELECT id,folder FROM objects WHERE folder<>''").fetchall()}
                con.close()
                dirs = []
                try:
                    for d in sorted(pth.iterdir(), key=lambda x: x.name.lower()):
                        if not d.is_dir() or d.name.startswith("."):
                            continue
                        try:
                            n = sum(1 for _ in d.iterdir())
                        except OSError:
                            n = 0
                        dirs.append({"name": d.name, "path": str(d), "count": n,
                                     "object_id": linked.get(str(d))})
                except OSError:
                    pass
                files = []
                try:
                    for f in sorted(pth.iterdir(), key=lambda x: x.name.lower()):
                        if f.is_file() and not f.name.startswith("."):
                            files.append({"name": f.name, "size": f.stat().st_size})
                except OSError:
                    pass
                return self._json({"ok": True, "path": str(pth), "parent": str(pth.parent),
                                   "dirs": dirs, "files": files[:200],
                                   "object_id": linked.get(str(pth))})
            if path == "/api/report/get":
                rid = int((qs.get("id") or ["0"])[0] or 0)
                con = core.connect()
                row = con.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
                con.close()
                if not row:
                    return self._err("Отчёт не найден", 404)
                return self._json({"ok": True, "data": dict(row)})
            if path == "/api/report/versions":
                rid = int((qs.get("id") or ["0"])[0] or 0)
                con = core.connect()
                con.execute("""CREATE TABLE IF NOT EXISTS report_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER, version INTEGER,
                    file TEXT, payload TEXT, created_at TEXT)""")
                rows = [dict(r) for r in con.execute(
                    "SELECT version,file,created_at FROM report_versions WHERE report_id=? "
                    "ORDER BY version DESC", (rid,))]
                con.close()
                return self._json({"ok": True, "items": rows})
            if path == "/api/protocol/get":
                pid = int((qs.get("id") or ["0"])[0] or 0)
                con = core.connect()
                row = con.execute("SELECT * FROM protocols WHERE id=?", (pid,)).fetchone()
                con.close()
                if not row:
                    return self._err("Протокол не найден", 404)
                return self._json({"ok": True, "data": dict(row)})
            if path == "/api/protocol/versions":
                pid = int((qs.get("id") or ["0"])[0] or 0)
                con = core.connect()
                con.execute("""CREATE TABLE IF NOT EXISTS protocol_versions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, protocol_id INTEGER, version INTEGER,
                    file TEXT, payload TEXT, created_at TEXT)""")
                rows = [dict(r) for r in con.execute(
                    "SELECT version,file,created_at FROM protocol_versions WHERE protocol_id=? "
                    "ORDER BY version DESC", (pid,))]
                con.close()
                return self._json({"ok": True, "items": rows})
            if path == "/api/groups":
                con = core.connect()
                rows = [dict(r) for r in con.execute(
                    "SELECT g.id,g.name,COUNT(o.id) AS cnt FROM object_groups g "
                    "LEFT JOIN objects o ON o.group_id=g.id GROUP BY g.id ORDER BY g.name").fetchall()]
                con.close()
                return self._json({"ok": True, "items": rows})
            if path == "/api/object/files":
                oid = int((qs.get("id") or ["0"])[0] or 0)
                kind = (qs.get("kind") or [""])[0] or None
                return self._json({"ok": True, "items": storage.files(oid, kind)})
            if path == "/api/qr":
                import io as _io
                import qrcode as _qr
                text = (qs.get("text") or [""])[0] or f"http://{local_ip()}:{PORT}"
                img = _qr.make(text)
                buf = _io.BytesIO()
                img.save(buf, format="PNG")
                return self._png(buf.getvalue())
            if path == "/api/state":
                data = core.state()
                user = _cookie_user(self)
                ai_cfg = core.get_setting("ai", {}) or {}
                tx = ai_cfg.get("text") or {}
                vi = ai_cfg.get("vision") or {}
                data["ai"] = {"key": bool((ai_cfg.get("key") or tx.get("key"))),
                              "text": bool(tx.get("key") or ai_cfg.get("key")),
                              "vision": bool(vi.get("key"))}
                data["aiCfg"] = {
                    "text": {"base": tx.get("base") or ai_cfg.get("base") or "",
                             "model": tx.get("model") or ai_cfg.get("model") or "",
                             "key_set": bool(tx.get("key") or ai_cfg.get("key"))},
                    "vision": {"base": vi.get("base") or "", "model": vi.get("model") or "",
                               "key_set": bool(vi.get("key"))}}
                data["phone_url"] = f"http://{local_ip()}:{PORT}"
                data["backupCfg"] = core.get_setting("backup", {}) or {}
                data["auth_required"] = _users_exist()
                data["user"] = ({"id": user["id"], "name": user["name"], "role": user["role"],
                                 "roles": user_roles(user)} if user else None)
                return self._json({"ok": True, "data": data})
            if path == "/api/preview":
                rel = (qs.get("f") or [""])[0]
                target = (BASE / rel).resolve()
                if not str(target).startswith(str(BASE.resolve())) or not target.is_file():
                    return self._err("Файл не найден", 404)
                return self._file(target)
            if path == "/api/download":
                rel = (qs.get("f") or [""])[0]
                target = (BASE / rel).resolve()
                if not str(target).startswith(str(BASE.resolve())):
                    return self._err("Нет доступа", 403)
                return self._file(target, download_name=target.name)
            if path == "/api/asset":
                rel = (qs.get("f") or [""])[0]
                target = (BASE / rel).resolve()
                if not str(target).startswith(str(BASE.resolve())) or not target.is_file():
                    return self._err("Нет доступа", 403)
                return self._file(target)
            if path == "/api/photo":
                rel = (qs.get("f") or [""])[0]
                pth = (qs.get("path") or [""])[0]
                if not rel and pth:
                    target = (BASE / pth).resolve()
                    if str(target).startswith(str(BASE.resolve())) and target.is_file():
                        return self._file(target)
                    return self._err("Фото не найдено", 404)
                rel = (qs.get("f") or [""])[0]
                target = (core.DATA / "photos" / rel).resolve()
                if not str(target).startswith(str(core.PHOTOS.resolve())):
                    return self._err("Нет доступа", 403)
                return self._file(target)
            if path == "/favicon.ico":
                return self._err("", 404)
            return self._err("Не найдено", 404)
        except Exception:
            traceback.print_exc()
            self._err("Внутренняя ошибка сервера", 500)

    def do_POST(self):
        try:
            url = urlparse(self.path)
            path = url.path
            qs = parse_qs(url.query)
            if path in ("/api/register", "/api/telegram/link"):
                body = self._read_json()
                return self._register(body) if path == "/api/register" else self._telegram_link(body)
            if path in ("/api/login", "/api/logout", "/api/users", "/api/users/toggle",
                        "/api/users/activate"):
                return self._auth_routes(path, self._read_json())
            if self._auth_gate(path):
                return
            if _users_exist() and not _can_write(getattr(self, "user", None), path):
                return self._err("Недостаточно прав для этого действия", 403)
            if path == "/api/upload":
                return self._upload(qs)
            if path == "/api/attach":
                return self._attach(qs)
            payload = self._read_json()
            self._audit(path, payload)
            routes = {
                "/api/protocol/ai-fill": self._protocol_ai_fill,
                "/api/protocol/ai-photo": self._protocol_ai_photo,
                "/api/protocol/fill": self._protocol_fill,
                "/api/protocol/preview": self._protocol_preview,
                "/api/protocol/save": self._protocol_save,
                "/api/report/preview": self._report_preview,
                "/api/report/save": self._report_save,
                "/api/settings": self._settings,
                "/api/object": self._object,
                "/api/contract": self._contract,
                "/api/contracts/import": self._contracts_import,
                "/api/ai": self._ai,
                "/api/entry": self._entry_add,
                "/api/entry/delete": self._entry_delete,
                "/api/object/scan": self._object_scan,
                "/api/object/doc": self._object_doc,
                "/api/agent/report": self._agent_report,
                "/api/agent/photo": self._agent_photo,
                "/api/numbering/sync": self._numbering_sync,
                "/api/numbering/set": self._numbering_set,
                "/api/object/status": self._object_status,
                "/api/object/folder": self._object_folder,
                "/api/object/open-folder": self._object_open,
                "/api/object/export": self._object_export,
                "/api/survey/build": self._survey_build,
                "/api/archive/scan": self._archive_scan,
                "/api/pdf": self._make_pdf,
                "/api/object/schedule": self._object_schedule,
                "/api/object/works/scan": self._object_works_scan,
                "/api/object/localize": self._object_localize,
                "/api/object/upload-create": self._object_upload_create,
                "/api/groups": self._groups_list,
                "/api/object/delete": self._object_delete,
                "/api/object/manual": self._object_manual,
                "/api/object/in-folder": self._object_in_folder,
                "/api/object/upload-doc": self._object_upload_doc,
                "/api/object/classify": self._object_classify,
                "/api/object/photos/analyze": self._object_photos_analyze,
                "/api/object/vor": self._object_vor,
                "/api/backup/create": self._backup_create,
                "/api/ai/test": self._ai_test,
                "/api/kp/list": self._kp_list,
                "/api/kp/create": self._kp_create,
                "/api/kp/import": self._kp_import,
                "/api/kp/import-price": self._kp_import_price,
                "/api/objects/import-tree": self._objects_import_tree,
                "/api/object/link": self._object_link,
                "/api/report/collect": self._report_collect,
                "/api/report/letter": self._report_letter,
                "/api/report/send/email": self._report_send_email,
                "/api/report/send/messenger": self._report_send_messenger,
                "/api/users/signature": self._user_signature,
                "/api/object/final-report": self._object_final_report,
                "/api/object/extract": self._object_extract,
                "/api/object/update": self._object_update,
                "/api/act/sampling": self._act_sampling,
                "/api/object/import": self._object_import,
                "/api/object/migrate": self._object_migrate,
                "/api/objects/migrate": self._objects_migrate,
                "/api/object/files": self._object_files,
                "/api/object/defects": self._object_defects,
                "/api/object/defects/doc": self._object_defects_doc,
                "/api/object/report-now": self._object_report_now,
                "/api/schedule/run": self._schedule_run,
                "/api/open-docs": self._open_docs,
            }
            fn = routes.get(path)
            if not fn:
                return self._err("Не найдено", 404)
            return fn(payload)
        except Exception:
            traceback.print_exc()
            self._err("Ошибка: " + traceback.format_exc(limit=1), 500)

    # ------------------------------------------------------------------- API
    @staticmethod
    def _asphalt_preview(meta):
        data = asphalt.calc(meta or {})
        rows = []
        missing_any = False
        for x in data["physical"] + data["operational"]:
            missing = x["fact"] in ("—", "")
            missing_any = missing_any or missing
            rows.append({"key": x["name"], "name": x["name"], "unit": "", "req": x["norm"],
                         "value": x["fact"], "ok": (x["ok"] if not missing else True),
                         "missing": missing})
        conclusion = data["conclusion"] if not missing_any else "Заполните результаты измерений."
        return {"rows": rows, "ok": data["ok"], "complete": not missing_any,
                "conclusion": conclusion, "extra": {}}

    def _protocol_fill(self, p):
        kind = p.get("kind", "asphalt")
        if kind == "asphalt":
            meta = asphalt.random_meta(p.get("meta") or {})
            self._json({"ok": True, "meta": meta, "calc": self._asphalt_preview(meta)})
            return
        meta = core.fill_demo(kind, p.get("meta") or {})
        calc = core.calculate(kind, meta)
        self._json({"ok": True, "meta": meta, "calc": calc})

    def _protocol_preview(self, p):
        kind = p.get("kind", "asphalt")
        meta = p.get("meta") or {}
        if kind == "asphalt":
            self._json({"ok": True, "calc": self._asphalt_preview(meta)})
            return
        calc = core.calculate(kind, meta)
        self._json({"ok": True, "calc": calc})

    def _protocol_ai_photo(self, p):
        kind = p.get("kind", "concrete")
        rel = (p.get("rel") or "").strip()
        if not rel:
            return self._err("Не выбрано фото")
        try:
            res = ai.read_photo(kind, rel)
        except Exception as e:
            return self._err(str(e))
        self._json({"ok": True, **res})

    def _protocol_ai_fill(self, p):
        kind = p.get("kind", "concrete")
        oid = int(p.get("object_id") or 0)
        eid = int(p.get("entry_id") or 0)
        con = core.connect()
        row = None
        if eid:
            row = con.execute("SELECT * FROM entries WHERE id=?", (eid,)).fetchone()
        elif oid:
            row = con.execute("SELECT * FROM entries WHERE object_id=? ORDER BY edate DESC, id DESC LIMIT 1",
                              (oid,)).fetchone()
        con.close()
        if not row:
            return self._err("Нет записей с объекта")
        e = dict(row)
        photos = 0
        try:
            photos = len(json.loads(e.get("photos") or "[]"))
        except Exception:
            pass
        text = (e.get("comment") or "") + "\n" + (e.get("tags") or "")
        res = ai.suggest_meta(kind, text, photos)
        self._json({"ok": True, "entry": {"id": e["id"], "date": e["edate"],
                                          "comment": e.get("comment") or "", "photos": photos},
                    **res})

    def _protocol_save(self, p):
        kind = p.get("kind", "asphalt")
        meta = p.get("meta") or {}
        if kind == "asphalt":
            meta["object_name"] = meta.get("object_name") or (p.get("object_name") or "")
            meta["customer"] = meta.get("customer") or (p.get("customer") or "")
            calc = self._asphalt_preview(meta)
        else:
            calc = core.calculate(kind, meta)
        pdate = p.get("pdate") or date.today().isoformat()

        con = core.connect()
        cols = {r["name"] for r in con.execute("PRAGMA table_info(protocols)")}
        if "version" not in cols:
            con.execute("ALTER TABLE protocols ADD COLUMN version INTEGER DEFAULT 1")
            con.commit()
        con.execute("""CREATE TABLE IF NOT EXISTS protocol_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, protocol_id INTEGER, version INTEGER,
            file TEXT, payload TEXT, created_at TEXT)""")

        edit_id = int(p.get("id") or 0)
        row = con.execute("SELECT * FROM protocols WHERE id=?", (edit_id,)).fetchone() if edit_id else None
        if row:
            number, lab_no, act_no = row["number"], row["lab_no"], row["act_no"]
            version = int(row["version"] or 1) + 1
            con.execute("INSERT INTO protocol_versions(protocol_id,version,file,payload,created_at)"
                        " VALUES (?,?,?,?,?)",
                        (row["id"], int(row["version"] or 1), row["file"], row["payload"],
                         datetime.now().isoformat(timespec="seconds")))
            con.commit()
        else:
            number = (str(p.get("number") or "")).strip()
            if not number:
                number = str(core.take_number("protocol", "protocol", None, (p.get("object_name") or "").strip()))
            lab_no = (str(p.get("lab_no") or "")).strip()
            if not lab_no:
                lab_no = str(core.take_number("lab", "protocol", None, (p.get("object_name") or "").strip()))
            act_no = (str(p.get("act_no") or "")).strip()
            if not act_no and p.get("need_act", True):
                act_no = str(core.take_number("act", "protocol", None, (p.get("object_name") or "").strip()))
            version = 1
        con.close()

        core.ensure_number_after("protocol", number)
        core.ensure_number_after("lab", lab_no)
        core.ensure_number_after("act", act_no)
        record = {
            "number": number, "lab_no": lab_no, "act_no": act_no, "pdate": pdate, "kind": kind,
            "object_name": (p.get("object_name") or "").strip(),
            "customer": (p.get("customer") or "").strip(),
            "meta": meta, "draft": bool(p.get("draft")),
            "internal": bool(p.get("internal")),
            "lab_head": p.get("lab_head") or core.company().get("lab_head", ""),
            "engineer": p.get("engineer") or "",
        }
        label = core.DOC_KINDS.get(kind, {}).get("short", kind)
        suffix = f" (v{version})" if version > 1 else ""
        fname = safe_name(f"Протокол {number} {record['object_name']}{suffix}.docx")
        folder = docs.doc_folder("Протоколы " + label)
        out = folder / fname
        protocol_docs.build(record, calc, out, signer=self._signer())
        pdf.export(out)

        payload = json.dumps({"meta": meta, "calc": calc}, ensure_ascii=False)
        rel = str(out.relative_to(BASE))
        con = core.connect()
        if row:
            con.execute("UPDATE protocols SET pdate=?,kind=?,object_name=?,customer=?,payload=?,"
                        "draft=?,file=?,version=?,lab_no=?,act_no=? WHERE id=?",
                        (pdate, kind, record["object_name"], record["customer"], payload,
                         1 if record["draft"] else 0, rel, version, lab_no, act_no, row["id"]))
            pid = row["id"]
        else:
            cur = con.execute(
                "INSERT INTO protocols(number,lab_no,act_no,pdate,kind,object_name,customer,sample,"
                "payload,draft,created_at,file,version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (number, lab_no, act_no, pdate, kind, record["object_name"], record["customer"],
                 meta.get("sample", ""), payload, 1 if record["draft"] else 0,
                 date.today().isoformat(), rel, 1))
            pid = cur.lastrowid
        con.commit()
        con.close()
        self._json({"ok": True, "id": pid, "number": number, "lab_no": lab_no, "act_no": act_no,
                    "file": rel, "pdf": pdf.pdf_for(rel), "calc": calc,
                    "draft": record["draft"], "version": version})

    def _report_preview(self, p):
        data = p.get("data") or {}
        self._json({"ok": True, "sections": reportgen.sections(data)})

    def _report_save(self, p):
        data = p.get("data") or {}
        edit_id = int(p.get("id") or data.get("id") or 0)
        con = core.connect()
        cols = {r["name"] for r in con.execute("PRAGMA table_info(reports)")}
        if "version" not in cols:
            con.execute("ALTER TABLE reports ADD COLUMN version INTEGER DEFAULT 1")
            con.commit()
        con.execute("""CREATE TABLE IF NOT EXISTS report_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, report_id INTEGER, version INTEGER,
            file TEXT, payload TEXT, created_at TEXT)""")
        con.commit()
        row = con.execute("SELECT * FROM reports WHERE id=?", (edit_id,)).fetchone() if edit_id else None
        if row:
            number = row["number"]
            version = int(row["version"] or 1) + 1
            con.execute("INSERT INTO report_versions(report_id,version,file,payload,created_at)"
                        " VALUES (?,?,?,?,?)",
                        (row["id"], int(row["version"] or 1), row["file"], row["payload"],
                         datetime.now().isoformat(timespec="seconds")))
            con.commit()
        else:
            year = date.today().year
            cnt = con.execute("SELECT value FROM counters WHERE kind='report' AND year=?", (year,)).fetchone()
            n = (cnt["value"] if cnt else 0) + 1
            con.execute("INSERT INTO counters(kind,year,value) VALUES ('report',?,?) "
                        "ON CONFLICT(kind,year) DO UPDATE SET value=excluded.value", (year, n))
            con.commit()
            number = (p.get("number") or "").strip() or f"{n:03d}-СК.{str(year)[2:]}"
            version = 1
        con.close()

        record = {
            "number": number,
            "date_from": data.get("date_from") or date.today().isoformat(),
            "date_to": data.get("date_to") or date.today().isoformat(),
            "object_name": (data.get("object_name") or data.get("address")
                            or data.get("object_title") or "").strip(),
            "customer": (data.get("customer") or "").strip(),
            "contract": (data.get("contract") or "").strip(),
            "payload": data,
        }
        suffix = f" (v{version})" if version > 1 else ""
        fname = safe_name(f"Отчёт {number} {record['object_name']}{suffix}.docx").strip()
        folder = docs.doc_folder("Отчёты")
        out = folder / fname
        reportgen.build(record, out, signer=self._signer())
        pdf.export(out)
        rel = str(out.relative_to(BASE))
        con = core.connect()
        if row:
            con.execute("UPDATE reports SET date_from=?,date_to=?,object_name=?,customer=?,contract=?,"
                        "payload=?,file=?,version=? WHERE id=?",
                        (record["date_from"], record["date_to"], record["object_name"],
                         record["customer"], record["contract"], json.dumps(data, ensure_ascii=False),
                         rel, version, row["id"]))
            rid = row["id"]
        else:
            cur = con.execute(
                "INSERT INTO reports(number,rdate,date_from,date_to,object_name,customer,contract,"
                "payload,created_at,file,version) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (number, date.today().isoformat(), record["date_from"], record["date_to"],
                 record["object_name"], record["customer"], record["contract"],
                 json.dumps(data, ensure_ascii=False), date.today().isoformat(), rel, 1))
            rid = cur.lastrowid
        con.commit()
        con.close()
        self._json({"ok": True, "id": rid, "number": number, "file": rel,
                    "pdf": pdf.pdf_for(rel), "version": version})

    def _settings(self, p):
        if "company" in p:
            comp = core.company()
            comp.update(p["company"] or {})
            core.set_setting("company", comp)
        if "norms" in p:
            core.set_setting("norms", p["norms"])
        if "ai" in p:
            cur = core.get_setting("ai", {}) or {}
            cur.update(p["ai"] or {})
            core.set_setting("ai", cur)
        if "smtp" in p:
            cur = core.get_setting("smtp", {}) or {}
            cur.update(p["smtp"] or {})
            core.set_setting("smtp", cur)
        if "messenger" in p:
            cur = core.get_setting("messenger", {}) or {}
            cur.update(p["messenger"] or {})
            core.set_setting("messenger", cur)
        if "employees" in p:
            con = core.connect()
            con.execute("DELETE FROM employees")
            for e in p["employees"]:
                if (e.get("name") or "").strip():
                    con.execute("INSERT INTO employees(name,position) VALUES (?,?)",
                                (e.get("name", "").strip(), e.get("position", "").strip()))
            con.commit()
            con.close()
        self._json({"ok": True})

    def _object(self, p):
        oid = core.add_object((p.get("name") or "").strip(), (p.get("address") or "").strip(),
                              (p.get("customer") or "").strip())
        self._json({"ok": True, "id": oid})

    def _contract(self, p):
        cid = core.add_contract(p)
        self._json({"ok": True, "id": cid})

    def _contracts_import(self, p):
        added = core.import_contracts_from_excel()
        self._json({"ok": True, "added": added})

    def _upload(self, qs):
        name = (qs.get("name") or ["photo.jpg"])[0]
        length = int(self.headers.get("Content-Length") or 0)
        data = self.rfile.read(length)
        if not data:
            return self._err("Пустой файл")
        sub = core.PHOTOS / date.today().strftime("%Y-%m")
        sub.mkdir(parents=True, exist_ok=True)
        fname = safe_name(f"{date.today().isoformat()}_{name}")
        path = sub / fname
        i = 1
        while path.exists():
            path = sub / safe_name(f"{date.today().isoformat()}_{i}_{name}")
            i += 1
        try:
            import io as _io
            from PIL import Image
            im = Image.open(_io.BytesIO(data)).convert("RGB")
            im.thumbnail((2200, 2200))
            path = path.with_suffix(".jpg")
            im.save(path, "JPEG", quality=88)
        except Exception:
            path.write_bytes(data)
        rel = str(path.relative_to(core.PHOTOS)).replace("\\", "/")
        self._json({"ok": True, "path": str(path), "rel": rel, "name": fname, "size": len(data)})

    def _open_docs(self, p):
        try:
            os.startfile(str(core.DOCS))  # noqa: только Windows, локальное приложение
            self._json({"ok": True})
        except Exception as e:
            self._err("Не удалось открыть папку: " + str(e))

    def _numbering_sync(self, p):
        try:
            res = core.sync_numbering(force=bool(p.get("force")))
        except Exception as e:
            return self._err("Не удалось прочитать реестр: " + str(e))
        self._json({"ok": True, **res, "synced_at": core.get_setting("numbering_synced_at", "")})

    def _numbering_set(self, p):
        kind = p.get("kind")
        if kind not in core.NUMBER_KINDS:
            return self._err("Неизвестный вид нумерации")
        core.set_number(kind, int(p.get("value") or 1))
        self._json({"ok": True, "numbering": core.numbering_state()})

    def _entry_add(self, p):
        eid = core.add_entry(
            int(p.get("object_id") or 0), (p.get("object_name") or "").strip(),
            p.get("edate") or date.today().isoformat(), (p.get("author") or "").strip(),
            (p.get("comment") or "").strip(), p.get("photos") or [],
            (p.get("tags") or "").strip(), p.get("files") or [],
            (p.get("activity") or "").strip())
        try:
            oid = int(p.get("object_id") or 0)
            if oid and (p.get("photos") or []):
                import threading as _th
                _th.Thread(target=_auto_caption,
                           args=(eid, oid, (p.get("comment") or "").strip()), daemon=True).start()
        except Exception:
            pass
        self._json({"ok": True, "id": eid})

    def _entry_delete(self, p):
        core.delete_entry(int(p.get("id") or 0))
        self._json({"ok": True})

    def _register(self, p):
        name = (p.get("name") or "").strip()
        phone = _norm_phone(p.get("phone") or "")
        if not name or len(phone) < 11:
            return self._err("Укажите ФИО и телефон")
        con = core.connect()
        con.execute("""CREATE TABLE IF NOT EXISTS user_extra (
            user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
            tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT)""")
        exists = con.execute("SELECT u.id, u.active FROM users u JOIN user_extra e ON e.user_id=u.id "
                             "WHERE e.phone=?", (phone,)).fetchone()
        con.close()
        if exists and exists["active"]:
            return self._err("Этот телефон уже зарегистрирован — войдите по коду")
        import uuid
        token = uuid.uuid4().hex[:12]
        code = _otp()
        if not exists:
            con = core.connect()
            cur = con.execute("INSERT INTO users(name,login,pin,role,active,created_at) VALUES (?,?,?,'',0,?)",
                              (name, "phone:" + phone, "", date.today().isoformat()))
            con.commit()
            uid = cur.lastrowid
            con.close()
        else:
            uid = exists["id"]
        _extra_set(uid, phone=phone, status="pending", otp=code,
                   otp_exp=(datetime.now() + timedelta(days=7)).isoformat(), link_token=token)
        bot = ((core.get_setting("messenger", {}) or {}).get("telegram_bot") or "").strip()
        link = f"https://t.me/{bot}?start={token}" if bot else ""
        self._json({"ok": True, "pending": True, "user_id": uid, "telegram_link": link,
                    "message": "Заявка создана. Администратор активирует аккаунт и выдаст код."})

    def _login_phone(self, p):
        phone = _norm_phone(p.get("phone") or "")
        code = (p.get("code") or "").strip()
        con = core.connect()
        con.execute("""CREATE TABLE IF NOT EXISTS user_extra (
            user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
            tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT)""")
        row = con.execute(
            "SELECT u.*, e.status st, e.otp, e.otp_exp, e.tg_chat FROM users u "
            "JOIN user_extra e ON e.user_id=u.id WHERE e.phone=?", (phone,)).fetchone()
        con.close()
        if not row:
            return self._err("Телефон не найден — зарегистрируйтесь")
        if row["st"] == "pending" or not row["active"]:
            return self._err("Аккаунт ещё не активирован администратором")
        if not code or code != (row["otp"] or ""):
            return self._err("Неверный код")
        if row["otp_exp"] and row["otp_exp"][:19] < datetime.now().isoformat()[:19]:
            return self._err("Код истёк — запросите новый")
        _extra_set(row["id"], otp="", otp_exp="")
        roles = user_roles(dict(row))
        core.add_audit({"id": row["id"], "name": row["name"], "role": row["role"]},
                       "вход по телефону", "пользователь", row["id"])
        return self._json({"ok": True, "user": {"id": row["id"], "name": row["name"],
                                                "role": row["role"], "roles": roles}},
                          cookie=f"smk_user={row['id']}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")

    def _telegram_link(self, p):
        phone = _norm_phone(p.get("phone") or "")
        con = core.connect()
        row = con.execute("SELECT user_id, link_token FROM user_extra WHERE phone=?", (phone,)).fetchone()
        con.close()
        if not row:
            return self._err("Сначала зарегистрируйтесь")
        bot = ((core.get_setting("messenger", {}) or {}).get("telegram_bot") or "").strip()
        if not bot:
            return self._err("Telegram-бот не настроен администратором")
        return self._json({"ok": True, "link": f"https://t.me/{bot}?start={row['link_token']}"})

    def _user_signature(self, p):
        user = getattr(self, "user", None) or _cookie_user(self)
        if not user:
            return self._err("Требуется вход", 401)
        if not user_is_admin(user):
            return self._err("Подпись сотрудникам задаёт администратор", 403)
        uid = int(p.get("id") or 0)
        path = (p.get("path") or "").strip()
        pos = (p.get("position") or "").strip()
        con = core.connect()
        con.execute("""CREATE TABLE IF NOT EXISTS user_extra (
            user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
            tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT,
            signature TEXT, position TEXT)""")
        cols = {r["name"] for r in con.execute("PRAGMA table_info(user_extra)")}
        for c in ("signature", "position"):
            if c not in cols:
                con.execute(f"ALTER TABLE user_extra ADD COLUMN {c} TEXT DEFAULT ''")
        con.commit(); con.close()
        _extra_set(uid, signature=path, position=pos)
        self._json({"ok": True})

    def _auth_routes(self, path, p):
        if path == "/api/login":
            if p.get("phone"):
                return self._login_phone(p)
            login = (p.get("login") or "").strip()
            pin = (p.get("pin") or "").strip()
            con = core.connect()
            row = con.execute("SELECT * FROM users WHERE login=? AND active=1", (login,)).fetchone()
            con.close()
            if not row or row["pin"] != _hash_pin(pin):
                return self._err("Неверный логин или код")
            roles = user_roles(dict(row))
            core.add_audit({"id": row["id"], "name": row["name"], "role": row["role"]},
                           "вход в программу", "пользователь", row["id"])
            return self._json({"ok": True, "user": {"id": row["id"], "name": row["name"],
                                                    "role": row["role"], "roles": roles}},
                              cookie=f"smk_user={row['id']}; Path=/; HttpOnly; SameSite=Lax; Max-Age=2592000")
        if path == "/api/logout":
            return self._json({"ok": True}, cookie="smk_user=; Path=/; HttpOnly; Max-Age=0")
        user = _cookie_user(self)
        first_run = not _users_exist()
        if not first_run and (not user or not user_is_admin(user)):
            return self._err("Только администратор может управлять сотрудниками", 403)
        if path == "/api/users":
            con = core.connect()
            if p.get("action") == "add":
                login = (p.get("login") or "").strip()
                if not login or not (p.get("pin") or "").strip():
                    con.close()
                    return self._err("Укажите логин и код")
                roles = p.get("roles") or ([p.get("role")] if p.get("role") else ["engineer"])
                if not isinstance(roles, list):
                    roles = [roles]
                roles = [r for r in roles if r] or ["engineer"]
                try:
                    con.execute("INSERT INTO users(name,login,pin,role,active,created_at) VALUES (?,?,?,?,1,?)",
                                ((p.get("name") or login).strip(), login, _hash_pin(p["pin"]),
                                 ("admin" if first_run else ",".join(roles)),
                                 date.today().isoformat()))
                    con.commit()
                except Exception:
                    con.close()
                    return self._err("Такой логин уже есть")
            con.execute("""CREATE TABLE IF NOT EXISTS user_extra (
                user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
                tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT)""")
            rows = [dict(r) for r in con.execute(
                "SELECT u.id,u.name,u.login,u.role,u.active,e.phone,e.status,e.tg_chat,e.otp,"
                "e.link_token,e.signature,e.position "
                "FROM users u LEFT JOIN user_extra e ON e.user_id=u.id ORDER BY u.name").fetchall()]
            for r in rows:
                r["roles"] = user_roles(r)
                r["phone"] = r.get("phone") or ""
                r["status"] = r.get("status") or "active"
            con.close()
            return self._json({"ok": True, "items": rows})
        if path == "/api/users/activate":
            uid = int(p.get("id") or 0)
            roles = p.get("roles") or ["engineer"]
            if not isinstance(roles, list):
                roles = [roles]
            con = core.connect()
            con.execute("UPDATE users SET role=?, active=1 WHERE id=?", (",".join(roles), uid))
            con.commit()
            con.close()
            _extra_set(uid, status="active")
            code = _otp()
            _extra_set(uid, otp=code, otp_exp=(datetime.now() + timedelta(days=1)).isoformat())
            ex = _extra(uid)
            sent = _tg_send(ex.get("tg_chat") or "", f"Аккаунт активирован. Код для входа: {code}")
            return self._json({"ok": True, "code": code, "telegram_sent": sent})
        if path == "/api/users/toggle":
            con = core.connect()
            con.execute("UPDATE users SET active=1-active WHERE id=?", (int(p.get("id") or 0),))
            con.commit()
            con.close()
            return self._json({"ok": True})

    def _report_row(self, rid):
        con = core.connect()
        row = con.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
        obj = None
        if row:
            obj = con.execute("SELECT * FROM objects WHERE name LIKE ? LIMIT 1",
                              (f"%{(row['object_name'] or '')[:40]}%",)).fetchone()
        con.close()
        return (dict(row) if row else None), (dict(obj) if obj else None)

    def _report_collect(self, p):
        oid = int(p.get("object_id") or 0)
        dfrom = p.get("date_from") or ""
        dto = p.get("date_to") or date.today().isoformat()
        con = core.connect()
        obj = con.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
        ents = [dict(r) for r in con.execute(
            "SELECT * FROM entries WHERE object_id=? ORDER BY edate", (oid,))]
        prots = [dict(r) for r in con.execute(
            "SELECT number,pdate,kind FROM protocols WHERE object_name LIKE ? ORDER BY pdate",
            (f"%{(obj['name'] if obj else '')[:40]}%",))]
        con.close()
        if not obj:
            return self._err("Объект не найден")
        o = dict(obj)
        works = ks2.period_works(oid, dfrom, dto)
        defects = [e for e in ents if "дефект" in (e.get("tags") or "").lower()]
        photos = []
        for e in ents:
            try:
                ph = json.loads(e.get("photos") or "[]")
            except Exception:
                ph = []
            for x in ph[:2]:
                photos.append({"path": x.get("path") or "", "rel": x.get("rel") or "",
                               "caption": f"{e.get('edate')} — {(e.get('comment') or '')[:80]}"})
        acts = [f["name"] for f in storage.files(oid, "acts")][:20]
        self._json({"ok": True, "object": {"id": o["id"], "name": o["name"],
                                          "title": o.get("object_title") or o["name"],
                                          "customer": o.get("customer") or "",
                                          "contract": o.get("contract") or "",
                                          "address": o.get("address") or "",
                                          "contractor": o.get("contractor") or ""},
                    "works": [{"section": "", "name": w["name"], "unit": w["unit"],
                               "total": f"{w['total']:.2f}".replace(".", ","),
                               "period": (f"{w['period']:.2f}".replace(".", ",") if w["period"] else "")}
                              for w in works[:40]],
                    "tests": [{"material": core.DOC_KINDS.get(x["kind"], {}).get("label", x["kind"]),
                               "doc": f"Протокол № {x['number']}", "date": x["pdate"],
                               "result": ""} for x in prots[:20]],
                    "issues": [d.get("comment") or "" for d in defects][:20],
                    "photos": photos[:12], "acts": "; ".join(acts),
                    "entries": len(ents)})

    def _report_letter(self, p):
        rep, obj = self._report_row(int(p.get("id") or 0))
        if not rep:
            return self._err("Отчёт не найден")
        period = f"{rep.get('date_from') or ''} – {rep.get('date_to') or ''}"
        letter = ai.build_email_letter(rep.get("object_name") or "", rep.get("number") or "",
                                       period, (obj or {}).get("customer") or "",
                                       core.company().get("name", "ООО «НИЦ СМК»"))
        self._json({"ok": True, **letter,
                    "to": (obj or {}).get("customer_email") or "",
                    "phone": (obj or {}).get("customer_phone") or "",
                    "object_name": rep.get("object_name") or "",
                    "pdf": rep.get("file") and str(Path(rep["file"]).with_suffix(".pdf")) or "",
                    "file": rep.get("file") or ""})

    def _report_send_email(self, p):
        rep, _obj = self._report_row(int(p.get("id") or 0))
        if not rep:
            return self._err("Отчёт не найден")
        to = (p.get("to") or "").strip()
        if "@" not in to:
            return self._err("Укажите e-mail заказчика")
        files = []
        for key in ("file", "pdf"):
            rel = rep.get(key)
            if rel and (BASE / rel).exists():
                files.append(rel)
        res = send.send_email(to, (p.get("subject") or "Отчёт по строительному контролю").strip(),
                              p.get("body") or "", files)
        if not res.get("ok"):
            return self._err(res.get("error") or "Не удалось отправить")
        self._json({"ok": True, "to": to, "files": len(files)})

    def _report_send_messenger(self, p):
        rep, obj = self._report_row(int(p.get("id") or 0))
        if not rep:
            return self._err("Отчёт не найден")
        files = [rep[k] for k in ("file", "pdf") if rep.get(k) and (BASE / rep[k]).exists()]
        text = (p.get("text") or "").strip() or f"Отчёт № {rep.get('number')} — {rep.get('object_name')}"
        channel = (p.get("channel") or "telegram").strip()
        if channel == "telegram":
            res = send.send_telegram(text, files)
            if res.get("ok"):
                return self._json({"ok": True, "sent": "telegram"})
            links = send.messenger_links((obj or {}).get("customer_phone") or "", text)
            return self._json({"ok": True, "sent": False, "error": res.get("error"), "links": links})
        links = send.messenger_links((obj or {}).get("customer_phone") or "", text)
        self._json({"ok": True, "sent": False, "links": links})

    def _object_final_report(self, p):
        oid = int(p.get("id") or 0)
        con = core.connect()
        obj = con.execute("SELECT name FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not obj:
            return self._err("Объект не найден")
        name = "".join(ch for ch in f"Итоговый отчёт {obj['name']} {date.today().isoformat()}.docx"
                       if ch not in '\\/:*?"<>|')
        out = docs.doc_folder("Отчёты") / name
        try:
            final_report.build(oid, out, signer=self._signer())
        except Exception as e:
            return self._err("Не удалось сформировать: " + str(e))
        pdf.export(out)
        try:
            core.copy_docs_to_object(oid)
        except Exception:
            pass
        self._json({"ok": True, "file": str(out.relative_to(BASE)),
                    "pdf": pdf.pdf_for(str(out.relative_to(BASE)))})

    def _object_extract(self, p):
        oid = int(p.get("id") or 0)
        try:
            res = extract.extract(oid)
        except Exception as e:
            return self._err("Не удалось разобрать документы: " + str(e))
        self._json({"ok": True, **res})

    def _object_update(self, p):
        oid = int(p.get("id") or 0)
        fields = {}
        for k in ("customer", "contractor", "contract", "address", "object_title",
                  "obj_type", "city", "customer_email", "customer_phone", "customer_inn"):
            if k in p:
                fields[k] = (p.get(k) or "").strip()
        if "contract_id" in p:
            fields["contract_id"] = int(p.get("contract_id") or 0)
        if not fields:
            return self._json({"ok": True})
        con = core.connect()
        sets = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE objects SET {sets} WHERE id=?", (*fields.values(), oid))
        con.commit()
        con.close()
        self._json({"ok": True})

    def _object_migrate(self, p):
        oid = int(p.get("id") or 0)
        res = storage.migrate_object(oid)
        if not res.get("ok"):
            return self._err(res.get("error") or "Не удалось перенести")
        self._json(res)

    def _objects_migrate(self, p):
        con = core.connect()
        rows = con.execute("SELECT id,folder FROM objects").fetchall()
        con.close()
        done, skipped, failed = [], [], []
        for r in rows:
            folder = r["folder"] or ""
            if not folder or not Path(folder).exists():
                skipped.append(r["id"]); continue
            if str(storage.ROOT) in folder:
                skipped.append(r["id"]); continue
            try:
                res = storage.migrate_object(r["id"])
                (done if res.get("ok") else failed).append(r["id"])
            except Exception:
                failed.append(r["id"])
        self._json({"ok": True, "moved": len(done), "skipped": len(skipped), "failed": len(failed)})

    def _save_sign_data(self, data_url, prefix):
        if not data_url or "base64," not in data_url:
            return ""
        import base64
        try:
            raw = base64.b64decode(data_url.split("base64,", 1)[1])
            folder = core.BASE / "data" / "files" / "acts"
            folder.mkdir(parents=True, exist_ok=True)
            f = folder / f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            f.write_bytes(raw)
            return str(f)
        except Exception:
            return ""

    def _act_sampling(self, p):
        oid = int(p.get("object_id") or 0)
        con = core.connect()
        obj = con.execute("SELECT name FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not obj:
            return self._err("Выберите объект")
        kind = (p.get("kind") or "sampling").strip()
        act_no = (p.get("act_no") or "б/н").strip()
        name = "".join(ch for ch in f"Акт отбора {obj['name']} {date.today().isoformat()}.docx"
                       if ch not in '\\/:*?"<>|')
        out = docs.doc_folder("Документы") / name
        record = {"object_id": oid, "kind": kind, "act_no": act_no,
                  "date": p.get("date") or date.today().isoformat(),
                  "material": p.get("material") or "", "gost": p.get("gost") or "",
                  "place": p.get("place") or "", "batch": p.get("batch") or "",
                  "conditions": p.get("conditions") or "", "purpose": p.get("purpose") or "",
                  "customer": p.get("customer") or "", "contractor": p.get("contractor") or "",
                  "customer_name": p.get("customer_name") or "",
                  "contractor_name": p.get("contractor_name") or "",
                  "customer_sign": self._save_sign_data(p.get("customer_sign_data"), "cust") or (p.get("customer_sign") or ""),
                  "contractor_sign": self._save_sign_data(p.get("contractor_sign_data"), "contr") or (p.get("contractor_sign") or "")}
        try:
            acts_doc.build_sampling(record, out, signer=self._signer())
        except Exception as e:
            return self._err("Не удалось сформировать акт: " + str(e))
        pdf.export(out)
        try:
            core.copy_docs_to_object(oid)
        except Exception:
            pass
        self._json({"ok": True, "file": str(out.relative_to(BASE)),
                    "pdf": pdf.pdf_for(str(out.relative_to(BASE)))})

    def _object_import(self, p):
        src = (p.get("path") or "").strip().strip('"')
        if not src:
            return self._err("Укажите путь к папке")
        name = (p.get("name") or "").strip() or Path(src).name
        oid = core.add_object(name, "", (p.get("customer") or "").strip(),
                              p.get("type") or "contract", int(p.get("contract_id") or 0))
        try:
            stats = storage.import_folder(oid, src)
        except Exception as e:
            return self._err(str(e))
        con = core.connect()
        con.execute("UPDATE objects SET folder=?, object_title=? WHERE id=?",
                    (str(storage.object_dir(oid)), name, oid))
        con.commit()
        con.close()
        try:
            ks2.scan_object(oid)
        except Exception:
            pass
        self._json({"ok": True, "id": oid, "name": name, **stats})

    def _object_files(self, p):
        oid = int((qs.get("id") or ["0"])[0] or 0)
        kind = (qs.get("kind") or [""])[0] or None
        self._json({"ok": True, "items": storage.files(oid, kind)})

    def _object_defects(self, p):
        oid = int((qs.get("id") or ["0"])[0] or 0)
        con = core.connect()
        rows = [dict(r) for r in con.execute(
            "SELECT * FROM entries WHERE object_id=? ORDER BY edate, id", (oid,))]
        con.close()
        items = []
        for r in rows:
            if "дефект" in (r.get("tags") or "").lower():
                r["photos"] = json.loads(r.get("photos") or "[]")
                items.append(r)
        self._json({"ok": True, "items": items})

    def _object_defects_doc(self, p):
        oid = int(p.get("id") or 0)
        con = core.connect()
        obj = con.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not obj:
            return self._err("Объект не найден")
        name = "".join(ch for ch in f"Дефектная ведомость {obj['name']} {date.today().isoformat()}.docx"
                       if ch not in '\\/:*?"<>|')
        out = docs.doc_folder("Документы") / name
        defects_doc.build(oid, out, signer=self._signer())
        pdf.export(out)
        res = {"ok": True, "file": str(out.relative_to(BASE)), "pdf": pdf.pdf_for(str(out.relative_to(BASE)))}
        try:
            core.copy_docs_to_object(oid)
        except Exception:
            pass
        self._json(res)

    def _objects_import_tree(self, p):
        root = (p.get("root") or "").strip().strip('"')
        if not root:
            root = str(core.BASE.parent / "РАБОЧАЯ" / "СТРОИТЕЛЬНЫЙ КОНТРОЛЬ" / "2026")
        base = Path(root)
        if not base.exists():
            return self._err("Папка не найдена: " + root)
        keywords = ("кс-2", "кс2", "протокол", "отчет", "отчёт", "документация подрядчика",
                    "исполнительн", "схем")
        skip_names = ("протокол", "отчет", "отчёт", "ид", "акт", "кс-2", "кс2", "pdf",
                      "архив", "фото", "схем", "документация подрядчика", "от заказчика",
                      "контракт")
        doc_ext = (".pdf", ".docx", ".xlsx", ".xls", ".jpg", ".jpeg", ".png")
        cands = {}
        for dirpath, dirnames, filenames in os.walk(base):
            d = Path(dirpath)
            try:
                depth = len(d.relative_to(base).parts)
            except ValueError:
                continue
            if depth > 6:
                dirnames[:] = []
                continue
            dirnames[:] = [x for x in dirnames if not x.startswith(".") and
                           "неактуальн" not in x.lower() and not x.startswith("2.")]
            if depth == 0:
                continue
            name_low = d.name.lower()
            if any(name_low.startswith(k) for k in skip_names):
                dirnames[:] = []
                continue
            kw_children = [c for c in dirnames if any(k in c.lower() for k in keywords)]
            docs_here = sum(1 for f in filenames if f.lower().endswith(doc_ext))
            if len(kw_children) >= 2:
                cands[d] = len(kw_children) + docs_here / 100.0
            elif len(kw_children) == 1 or docs_here >= 3:
                cands[d] = len(kw_children) + docs_here / 100.0

        strong = [d for d, sc in cands.items() if sc >= 2]
        # из вложенных сильных оставляем самый глубокий
        strong.sort(key=lambda x: len(x.relative_to(base).parts))
        kept = []
        for d in strong:
            kept = [k for k in kept if not str(k).startswith(str(d) + os.sep)]
            if any(str(d).startswith(str(k) + os.sep) for k in kept):
                continue
            kept.append(d)
        # слабые добавляем, только если внутри нет сильного и они не содержат его
        for d, sc in cands.items():
            if sc >= 2:
                continue
            if any(str(k).startswith(str(d) + os.sep) for k in kept):
                continue
            if any(str(d).startswith(str(k) + os.sep) for k in kept):
                continue
            kept.append(d)

        created, skipped = [], 0
        for d in kept[:120]:
            rel = d.relative_to(base)
            name = " / ".join(rel.parts[-2:]) if len(rel.parts) >= 2 else rel.parts[-1]
            con = core.connect()
            exists = con.execute("SELECT id FROM objects WHERE folder=?", (str(d),)).fetchone()
            con.close()
            if exists:
                skipped += 1
                continue
            oid = core.add_object(name, "", "", "contract", 0)
            con = core.connect()
            con.execute("UPDATE objects SET folder=?, object_title=? WHERE id=?", (str(d), name, oid))
            con.commit()
            con.close()
            created.append({"id": oid, "name": name, "folder": str(d)})
        self._json({"ok": True, "created": len(created), "skipped": skipped,
                    "items": created[:20]})

    def _kp_list(self, p):
        con = core.connect()
        con.execute("""CREATE TABLE IF NOT EXISTS kp (
            id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE, kdate TEXT,
            customer TEXT, object TEXT, total REAL DEFAULT 0, file TEXT, items TEXT,
            type TEXT DEFAULT 'commercial', eisc TEXT, request_date TEXT, valid_until TEXT)""")
        cols = {r["name"] for r in con.execute("PRAGMA table_info(kp)")}
        for c in ("type", "eisc", "request_date", "valid_until"):
            if c not in cols:
                con.execute(f"ALTER TABLE kp ADD COLUMN {c} TEXT DEFAULT ''")
        con.commit()
        rows = [dict(r) for r in con.execute(
            "SELECT id,number,kdate,customer,object,total,file,type FROM kp ORDER BY id DESC LIMIT 300").fetchall()]
        have = con.execute("SELECT COUNT(*) c FROM kp_services").fetchone()["c"] if _table_exists(con, "kp_services") else 0
        con.close()
        self._json({"ok": True, "items": rows, "services": kp.services() if have else [],
                    "types": kp.TYPES, "price_loaded": have})

    def _backup_create(self, p):
        try:
            res = backup.create_backup()
        except Exception as e:
            return self._err("Не удалось создать копию: " + str(e))
        self._json({"ok": True, **res})

    def _ai_test(self, p):
        prof = p.get("profile") or "text"
        cfg = core.get_setting("ai", {}) or {}
        pc = cfg.get(prof) or {}
        key = (p.get("key") or pc.get("key") or cfg.get("key") or "").strip()
        base = (p.get("base") or pc.get("base") or cfg.get("base") or "https://api.deepseek.com/v1").strip()
        model = (p.get("model") or pc.get("model") or (cfg.get("model") if prof == "text" else "") or "gpt-4o-mini").strip()
        if not key:
            return self._err("Не указан API-ключ")
        base = ai.normalize_base(base)
        try:
            import urllib.error as _ue
            import urllib.request as _u
            body = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 5}
            req = _u.Request(base.rstrip("/") + "/chat/completions",
                             data=json.dumps(body).encode(),
                             headers={"Content-Type": "application/json",
                                      "Authorization": "Bearer " + key}, method="POST")
            _u.urlopen(req, timeout=40).read()
        except _ue.HTTPError as e:
            if e.code == 401:
                return self._err("Ключ не принят (401). Проверьте ключ и что он от этого сервиса.")
            if e.code == 403:
                return self._err("Доступ запрещён (403). Чаще всего: сервис недоступен из вашей страны "
                                 "или ключ от другого сервиса. Попробуйте ProxyAPI, VseGPT или локальную модель.")
            if e.code == 404:
                return self._err("Адрес не найден (404). Проверьте адрес API — обычно он оканчивается на /v1.")
            if e.code == 429:
                return self._err("Слишком много запросов или закончился баланс (429).")
            return self._err(f"Ошибка сервиса ({e.code}). Проверьте адрес, модель и ключ.")
        except Exception as e:
            return self._err("Не удалось подключиться: " + str(e)[:200])
        self._json({"ok": True, "model": model, "profile": prof})

    def _kp_import_price(self, p):
        try:
            n = kp.import_price()
        except Exception as e:
            return self._err("Не удалось прочитать прайс: " + str(e))
        self._json({"ok": True, "added": n})

    def _kp_create(self, p):
        items = [x for x in (p.get("items") or []) if float(x.get("qty") or 0) > 0]
        if not items:
            return self._err("Добавьте хотя бы одну услугу")
        company = p.get("company") or "nic"
        number = kp.next_number(company)
        con = core.connect()
        total = sum(float(x.get("qty") or 0) * float(x.get("price") or 0) for x in items)
        record = {"number": number, "date": p.get("date") or date.today().isoformat(),
                  "customer": p.get("customer") or "", "object": p.get("object") or "",
                  "company": company,
                  "person": p.get("person") or "", "phone": p.get("phone") or "",
                  "type": p.get("type") or "commercial", "eisc": p.get("eisc") or "",
                  "request_date": p.get("request_date") or "",
                  "valid_until": p.get("valid_until") or "", "items": items}
        name = "".join(ch for ch in f"КП {number} {record['customer']}.docx"
                       if ch not in '\\/:*?"<>|')
        out = docs.doc_folder("КП") / name
        try:
            kp.build(record, out)
        except Exception as e:
            con.close()
            return self._err("Не удалось сформировать КП: " + str(e))
        pdf.export(out)
        con.execute("INSERT INTO kp(number,kdate,customer,object,total,file,items,type,eisc,request_date,valid_until)"
                    " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (number, record["date"], record["customer"], record["object"], total,
                     str(out.relative_to(BASE)), json.dumps(items, ensure_ascii=False),
                     record["type"], record["eisc"], record["request_date"], record["valid_until"]))
        con.commit(); con.close()
        self._json({"ok": True, "number": number, "total": total,
                    "file": str(out.relative_to(BASE)), "pdf": pdf.pdf_for(str(out.relative_to(BASE)))})

    def _kp_import(self, p):
        src = core.BASE.parent / "РАБОЧАЯ" / "КП" / "2026" / "Исходящие №КП.xlsx"
        if not src.exists():
            return self._err("Файл реестра КП не найден")
        import openpyxl
        wb = openpyxl.load_workbook(str(src), data_only=True, read_only=True)
        ws = wb.worksheets[0]
        con = core.connect()
        con.execute("""CREATE TABLE IF NOT EXISTS kp (
            id INTEGER PRIMARY KEY AUTOINCREMENT, number TEXT UNIQUE, kdate TEXT,
            customer TEXT, object TEXT, total REAL DEFAULT 0, file TEXT, items TEXT,
            type TEXT DEFAULT 'commercial', eisc TEXT, request_date TEXT, valid_until TEXT,
            company TEXT DEFAULT 'nic')""")
        cols = {r["name"] for r in con.execute("PRAGMA table_info(kp)")}
        if "company" not in cols:
            con.execute("ALTER TABLE kp ADD COLUMN company TEXT DEFAULT 'nic'")
        con.commit()
        added = 0
        for row in ws.iter_rows(min_row=2, values_only=True):
            vals = list(row) + [None] * 6
            d, cust, work = vals[0], vals[4], vals[5]
            kdate = ""
            try:
                kdate = d.date().isoformat() if hasattr(d, "date") else (str(d)[:10] if d else "")
            except Exception:
                kdate = ""
            nums = {"nic": vals[1], "ing": vals[2], "loft": vals[3]}
            for comp_key, raw in nums.items():
                if raw in (None, ""):
                    continue
                raw = str(raw).strip()
                if comp_key == "nic":
                    num = raw if raw.startswith("КП-") else raw
                elif comp_key == "ing":
                    num = "ИНЖ-" + re.sub(r"\D", "", raw)
                else:
                    num = "ЛОФТ-" + re.sub(r"\D", "", raw)
                try:
                    con.execute("INSERT OR IGNORE INTO kp(number,kdate,customer,object,total,file,items,company)"
                                " VALUES (?,?,?,?,0,'','[]',?)",
                                (num, kdate, str(cust or "").strip(), str(work or "").strip(), comp_key))
                    added += 1
                except Exception:
                    pass
        con.commit(); con.close(); wb.close()
        self._json({"ok": True, "added": added})

    def _object_link(self, p):
        src = (p.get("path") or "").strip()
        name = (p.get("name") or "").strip() or Path(src).name
        if not src or not Path(src).exists():
            return self._err("Папка не найдена")
        con = core.connect()
        row = con.execute("SELECT id FROM objects WHERE folder=?", (src,)).fetchone()
        con.close()
        if row:
            return self._json({"ok": True, "id": row["id"], "existed": True})
        oid = core.add_object(name, "", "", p.get("type") or "contract", 0)
        con = core.connect()
        con.execute("UPDATE objects SET folder=?, object_title=? WHERE id=?", (src, name, oid))
        con.commit()
        con.close()
        self._json({"ok": True, "id": oid, "existed": False})

    def _groups_list(self, p):
        con = core.connect()
        rows = [dict(r) for r in con.execute(
            "SELECT g.id,g.name,COUNT(o.id) AS cnt FROM object_groups g "
            "LEFT JOIN objects o ON o.group_id=g.id GROUP BY g.id ORDER BY g.name").fetchall()]
        con.close()
        return self._json({"ok": True, "items": rows})

    def _object_delete(self, p):
        user = _cookie_user(self)
        if not user or not user_is_admin(user):
            return self._err("Удалять объекты может только администратор", 403)
        oid = int(p.get("id") or 0)
        con = core.connect()
        obj = con.execute("SELECT id,name FROM objects WHERE id=?", (oid,)).fetchone()
        if not obj:
            return self._err("Объект не найден", 404)
        for table in ("entries", "object_works", "object_docs", "object_files", "reports_link"):
            try:
                con.execute(f"DELETE FROM {table} WHERE object_id=?", (oid,))
            except Exception:
                pass
        con.execute("DELETE FROM objects WHERE id=?", (oid,))
        con.commit(); con.close()
        self._json({"ok": True, "name": obj["name"]})

    def _object_localize(self, p):
        oid = int(p.get("id") or 0)
        con = core.connect()
        obj = con.execute("SELECT id,folder FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not obj:
            return self._err("Объект не найден")
        src = (obj["folder"] or "").strip()
        local = core.BASE / "data" / "storage" / "objects" / str(oid)
        if not src:
            con = core.connect()
            con.execute("UPDATE objects SET folder=?", (str(local), oid))
            con.commit(); con.close()
            return self._json({"ok": True, "copied": 0, "folder": str(local)})
        if Path(src).resolve() == local.resolve():
            return self._json({"ok": True, "copied": 0, "already": True, "folder": str(local)})
        if not Path(src).exists():
            return self._err("Папка-источник недоступна: " + src)
        try:
            stats = storage.import_folder(oid, src)
        except Exception as e:
            return self._err("Не удалось скопировать: " + str(e)[:200])
        con = core.connect()
        con.execute("UPDATE objects SET folder=? WHERE id=?", (str(local), oid))
        con.execute("""CREATE TABLE IF NOT EXISTS object_docs (
            id INTEGER PRIMARY KEY AUTOINCREMENT, object_id INTEGER, path TEXT, title TEXT,
            kind TEXT, added_at TEXT)""")
        allowed = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".jpg", ".jpeg", ".png",
                   ".tif", ".tiff", ".txt", ".csv")
        n = 0
        for f in local.rglob("*"):
            if not f.is_file() or f.suffix.lower() not in allowed:
                continue
            con.execute("INSERT OR IGNORE INTO object_docs(object_id,path,title,kind,added_at)"
                        " VALUES (?,?,?,?,?)",
                        (oid, str(f), f.name, f.suffix.lstrip(".").lower(), date.today().isoformat()))
            n += 1
        con.commit(); con.close()
        try:
            ks2.scan_object(oid)
        except Exception:
            pass
        self._json({"ok": True, "copied": stats.get("files", 0), "registered": n,
                    "bytes": stats.get("bytes", 0), "folder": str(local)})

    def _object_upload_create(self, p):
        files = p.get("files") or []
        if not files:
            return self._err("Приложите документы по объекту")
        name = (p.get("name") or "").strip()
        if not name:
            name = Path(str(files[0].get("name") or "Объект")).stem[:80]
        oid = core.add_object(name, "", "", p.get("type") or "contract", 0)
        store = core.BASE / "data" / "storage" / "objects" / str(oid)
        docdir = store / "ДОКУМЕНТАЦИЯ"
        docdir.mkdir(parents=True, exist_ok=True)
        con = core.connect()
        con.execute("UPDATE objects SET folder=? WHERE id=?", (str(store), oid))
        con.commit()
        saved = 0
        allowed = (".pdf", ".docx", ".doc", ".xlsx", ".xls", ".jpg", ".jpeg",
                   ".png", ".tif", ".tiff", ".txt", ".csv")
        for f in files:
            rel = str(f.get("rel") or "").strip()
            src = core.BASE / "data" / "files" / rel
            if not src.exists():
                src = core.BASE / rel
            if not src.exists():
                continue
            if src.suffix.lower() == ".zip":
                import zipfile
                try:
                    with zipfile.ZipFile(src) as z:
                        for m in z.namelist():
                            if m.endswith("/") or Path(m).suffix.lower() not in allowed:
                                continue
                            data = z.read(m)
                            if len(data) > 80 * 1024 * 1024:
                                continue
                            base_name = safe_name(Path(m).name) or "файл"
                            target = docdir / base_name
                            k = 1
                            while target.exists():
                                target = docdir / (Path(base_name).stem + f"_{k}" + Path(base_name).suffix)
                                k += 1
                            target.write_bytes(data)
                            saved += 1
                            c3 = core.connect()
                            c3.execute("INSERT OR IGNORE INTO object_docs(object_id,path,title,kind,added_at)"
                                       " VALUES (?,?,?,?,?)",
                                       (oid, str(target), target.name,
                                        target.suffix.lstrip(".").lower(), date.today().isoformat()))
                            c3.commit()
                            c3.close()
                except Exception:
                    pass
                continue
            fname = safe_name(str(f.get("name") or src.name)) or src.name
            dst = docdir / fname
            if dst.exists():
                dst = docdir / (Path(fname).stem + "_" + str(saved + 1) + Path(fname).suffix)
            try:
                dst.write_bytes(src.read_bytes())
            except OSError:
                continue
            saved += 1
            con2 = core.connect()
            con2.execute("INSERT OR IGNORE INTO object_docs(object_id,path,title,kind,added_at)"
                         " VALUES (?,?,?,?,?)",
                         (oid, str(dst), dst.name, dst.suffix.lstrip(".").lower(), date.today().isoformat()))
            con2.commit()
            con2.close()
        con.close()
        result = {"ok": True, "id": oid, "files": saved}
        try:
            res = ai.classify_project(oid)
            result.update(res)
            city = (res.get("city") or "").strip()
            if not city:
                addr = (res.get("address") or "")
                city = addr.split(",")[0].strip()
            if city:
                city = re.sub(r"^(м\.о\.|московская\s+обл\.?|обл\.?|г\.)\s*", "", city.strip(), flags=re.I).strip(" ,")
                city = city.split(",")[0].strip()
                gid = core.ensure_group(city)
                c2 = core.connect()
                c2.execute("UPDATE objects SET group_id=?, city=? WHERE id=?", (gid, city, oid))
                c2.commit(); c2.close()
                result["group"] = city
            c2 = core.connect()
            fields = {}
            for k in ("object_title", "address", "customer", "contractor", "contract"):
                if res.get(k):
                    fields[k] = res[k][:200]
            if res.get("short_name"):
                fields["name"] = res["short_name"][:80]
            if fields:
                sets = ", ".join(f"{k}=?" for k in fields)
                c2.execute(f"UPDATE objects SET {sets} WHERE id=?", (*fields.values(), oid))
                c2.commit()
            c2.close()
        except Exception as e:
            result["ai_error"] = str(e)[:200]
        self._json(result)

    def _object_manual(self, p):
        name = (p.get("name") or "").strip()
        if not name:
            return self._err("Укажите название объекта")
        oid = core.add_object(name, "", (p.get("customer") or "").strip(),
                              p.get("type") or "contract", int(p.get("contract_id") or 0))
        con = core.connect()
        con.execute("UPDATE objects SET address=?, object_title=?, city=? WHERE id=?",
                    ((p.get("address") or "").strip(), name,
                     (p.get("city") or "").strip(), oid))
        con.commit(); con.close()
        self._json({"ok": True, "id": oid})

    def _object_in_folder(self, p):
        parent = (p.get("parent") or "").strip()
        name = (p.get("name") or "").strip()
        if not parent or not name:
            return self._err("Укажите папку и название объекта")
        base = core.BASE.parent / "РАБОЧАЯ"
        try:
            parent_p = Path(parent).resolve()
            parent_p.relative_to(base.resolve())
        except Exception:
            return self._err("Папка вне рабочей области", 403)
        folder = parent_p / safe_name(name)
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            return self._err("Не удалось создать папку: " + str(e))
        oid = core.add_object(name, "", (p.get("customer") or "").strip(),
                              p.get("type") or "contract", int(p.get("contract_id") or 0))
        con = core.connect()
        con.execute("UPDATE objects SET folder=?, object_title=? WHERE id=?", (str(folder), name, oid))
        con.commit()
        con.close()
        self._json({"ok": True, "id": oid, "folder": str(folder)})

    def _object_upload_doc(self, p):
        oid = int(p.get("id") or 0)
        rel = (p.get("rel") or "").strip()
        src = core.BASE / "data" / "files" / rel
        if not src.exists():
            src = core.BASE / rel
        if not src.exists():
            return self._err("Файл не найден")
        con = core.connect()
        obj = con.execute("SELECT folder FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not obj or not obj["folder"]:
            return self._err("У объекта не задана папка")
        dst_dir = Path(obj["folder"]) / "ДОКУМЕНТАЦИЯ"
        dst_dir.mkdir(parents=True, exist_ok=True)
        name = safe_name((p.get("name") or src.name).strip()) or src.name
        dst = dst_dir / name
        i = 1
        while dst.exists():
            dst = dst_dir / (src.stem + f"_{i}" + src.suffix)
            i += 1
        dst.write_bytes(src.read_bytes())
        con = core.connect()
        con.execute("INSERT OR IGNORE INTO object_docs(object_id,path,title,kind,added_at)"
                    " VALUES (?,?,?,?,?)",
                    (oid, str(dst), dst.name, dst.suffix.lstrip("."), date.today().isoformat()))
        con.commit()
        con.close()
        import threading as _th
        _th.Thread(target=_auto_classify, args=(oid,), daemon=True).start()
        self._json({"ok": True, "name": dst.name})

    def _object_classify(self, p):
        oid = int(p.get("id") or 0)
        try:
            res = ai.classify_project(oid)
        except Exception as e:
            return self._err(str(e))
        con = core.connect()
        sets, vals = [], []
        for k in ("object_title", "address", "customer", "contractor", "contract"):
            v = res.get(k) or ""
            if v:
                sets.append(f"{k}=?")
                vals.append(v[:200])
        if res.get("short_name"):
            sets.append("name=?")
            vals.append(res["short_name"][:80])
        city = (res.get("city") or "").strip()
        if not city:
            city = (res.get("address") or "").split(",")[0].strip()
        if city:
            city = re.sub(r"^(м\.о\.|московская\s+обл\.?|обл\.?|г\.)\s*", "", city, flags=re.I).strip(" ,")
            gid = core.ensure_group(city)
            sets.append("group_id=?")
            vals.append(gid)
            sets.append("city=?")
            vals.append(city)
        if sets:
            con.execute(f"UPDATE objects SET {', '.join(sets)} WHERE id=?", (*vals, oid))
            con.commit()
        con.close()
        self._json({"ok": True, **res})

    def _object_photos_analyze(self, p):
        oid = int(p.get("id") or 0)
        limit = int(p.get("limit") or 12)
        force = bool(p.get("force"))
        con = core.connect()
        rows = [dict(r) for r in con.execute(
            "SELECT id,comment,photos FROM entries WHERE object_id=? ORDER BY edate DESC", (oid,))]
        con.close()
        done, errors = 0, []
        for r in rows:
            try:
                photos = json.loads(r.get("photos") or "[]")
            except Exception:
                continue
            changed = False
            for ph in photos:
                if done >= limit:
                    break
                if not isinstance(ph, dict):
                    continue
                if ph.get("caption") and not force:
                    continue
                rel = ph.get("rel") or ph.get("path") or ""
                if not rel:
                    continue
                try:
                    res = ai.analyze_photo(oid, rel, r.get("comment") or "")
                    if res.get("caption"):
                        ph["caption"] = res["caption"]
                        ph["work"] = res.get("work") or ""
                        changed = True
                        done += 1
                except Exception as e:
                    errors.append(str(e)[:120])
            if changed:
                con = core.connect()
                con.execute("UPDATE entries SET photos=? WHERE id=?",
                            (json.dumps(photos, ensure_ascii=False), r["id"]))
                con.commit()
                con.close()
        self._json({"ok": True, "analyzed": done, "errors": errors[:5]})

    def _object_vor(self, p):
        oid = int(p.get("id") or 0)
        rel = (p.get("rel") or "").strip()
        if not rel:
            return self._err("Файл ВОР не передан")
        q = core.BASE / "data" / "files" / rel
        if not q.exists():
            q = core.BASE / rel
        if not q.exists():
            return self._err("Файл ВОР не найден")
        try:
            act = ks2.parse_act(str(q), "вор")
        except Exception as e:
            return self._err("Не удалось прочитать ВОР: " + str(e))
        works = act.get("works") or []
        if not works:
            return self._err("В файле не найдена таблица «наименование / единица / количество»")
        con = core.connect()
        for w in works:
            con.execute(
                "INSERT OR REPLACE INTO object_works(object_id,name,unit,qty,act_no,act_date,source,imported_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (oid, w["name"], w["unit"], w["qty"], "ДОГОВОР", "",
                 q.name, date.today().isoformat()))
        con.commit()
        con.close()
        self._json({"ok": True, "works": len(works), "file": q.name})

    def _object_works_scan(self, p):
        oid = int(p.get("id") or 0)
        try:
            res = ks2.scan_object(oid)
        except Exception as e:
            return self._err("Не удалось прочитать КС-2: " + str(e))
        self._json({"ok": True, **res, "items": ks2.list_works(oid)})

    def _object_schedule(self, p):
        oid = int(p.get("id") or 0)
        freq = p.get("freq") or "weekly"
        if freq not in ("weekly", "monthly", "none"):
            return self._err("Неизвестная периодичность")
        if freq == "none":
            con = core.connect()
            con.execute("UPDATE objects SET report_freq='', report_auto=0, report_next='' WHERE id=?", (oid,))
            con.commit()
            con.close()
            return self._json({"ok": True, "schedule": {}})
        res = core.set_object_schedule(oid, freq, p.get("start") or "", int(p.get("day") or 1),
                                       bool(p.get("auto", True)))
        self._json({"ok": True, "schedule": res})

    def _object_report_now(self, p):
        oid = int(p.get("id") or 0)
        try:
            res = autoreport.generate(oid, date.today().isoformat())
        except Exception as e:
            return self._err("Не удалось сформировать отчёт: " + str(e))
        if not res:
            return self._err("Объект не найден")
        self._json({"ok": True, **res})

    def _schedule_run(self, p):
        try:
            res = autoreport.run_due()
        except Exception as e:
            return self._err("Ошибка планировщика: " + str(e))
        self._json({"ok": True, "generated": res, "count": len(res)})

    def _make_pdf(self, p):
        rel = (p.get("file") or "").strip()
        target = (BASE / rel).resolve()
        if not str(target).startswith(str(BASE.resolve())) or target.suffix.lower() != ".docx":
            return self._err("Неверный файл")
        if not target.exists():
            return self._err("Файл не найден")
        res = pdf.export(target)
        if not res:
            return self._err("Не удалось сделать PDF. Проверьте, что установлен Microsoft Word.")
        self._json({"ok": True, "pdf": pdf.pdf_for(rel)})

    def _archive_scan(self, p):
        try:
            res = archive.scan(int(p.get("limit") or 80))
        except Exception as e:
            return self._err("Ошибка импорта: " + str(e))
        self._json({"ok": True, **res})

    def _object_status(self, p):
        core.set_object_status(int(p.get("id") or 0), (p.get("status") or "active"))
        self._json({"ok": True})

    def _object_folder(self, p):
        oid = int(p.get("id") or 0)
        con = core.connect()
        row = con.execute("SELECT name FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not row:
            return self._err("Объект не найден", 404)
        path = (p.get("path") or "").strip()
        if not path:
            path = core.find_object_folder(row["name"])
        if path:
            core.set_object_folder(oid, path)
        self._json({"ok": True, "folder": path})

    def _object_open(self, p):
        oid = int(p.get("id") or 0)
        con = core.connect()
        row = con.execute("SELECT folder FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        folder = row["folder"] if row else ""
        if not folder or not Path(folder).exists():
            return self._err("Папка объекта не привязана")
        try:
            os.startfile(folder)
            self._json({"ok": True})
        except Exception as e:
            self._err("Не удалось открыть: " + str(e))

    def _object_export(self, p):
        try:
            copied = core.copy_docs_to_object(int(p.get("id") or 0))
        except Exception as e:
            return self._err("Ошибка выгрузки: " + str(e))
        self._json({"ok": True, "count": len(copied), "files": copied})

    def _survey_build(self, p):
        oid = int(p.get("object_id") or 0)
        eid = int(p.get("entry_id") or 0)
        con = core.connect()
        if not oid and eid:
            ent = con.execute("SELECT object_id FROM entries WHERE id=?", (eid,)).fetchone()
            oid = ent["object_id"] if ent else 0
        obj = con.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not obj:
            return self._err("Объект не найден", 404)
        ents = [e for e in core.entries(oid) if not eid or e["id"] == eid]
        points = []
        for e in ents:
            for f in e.get("files") or []:
                path = f.get("path") if isinstance(f, dict) else f
                if path and Path(path).suffix.lower() in (".csv", ".txt", ".dat"):
                    points += survey.parse_points(path)
        if not points:
            return self._err("В файлах не найдены точки (нужен CSV/TXT с координатами X;Y;Z)")
        author = (p.get("author") or (ents[0].get("author") if ents else "") or "").strip()
        rec = {
            "object_name": obj["name"], "customer": obj["customer"] or "",
            "address": p.get("address") or obj["name"], "work": p.get("work") or "Исполнительная съёмка",
            "survey_date": p.get("survey_date") or date.today().strftime("%d.%m.%Y"),
            "author": author, "crs": p.get("crs") or "МСК",
        }
        fname = safe_name(f"Схема {obj['name']} {date.today().isoformat()}.docx")
        out = docs.doc_folder("Схемы") / fname
        survey.build(rec, points, out)
        pdf.export(out)
        if obj["folder"]:
            try:
                core.copy_docs_to_object(oid)
            except Exception:
                pass
        self._json({"ok": True, "file": str(out.relative_to(BASE)),
                    "pdf": pdf.pdf_for(str(out.relative_to(BASE))),
                    "points": len(points), "author": author})

    def _object_scan(self, p):
        oid = int(p.get("object_id") or 0)
        con = core.connect()
        row = con.execute("SELECT name FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not row:
            return self._err("Объект не найден", 404)
        try:
            total = core.scan_object_docs(oid, row["name"])
        except Exception as e:
            return self._err("Ошибка сканирования: " + str(e))
        self._json({"ok": True, "total": total, "docs": core.object_docs(oid)})

    def _object_doc(self, p):
        oid = int(p.get("object_id") or 0)
        path = (p.get("path") or "").strip()
        if not path:
            return self._err("Не указан путь")
        core.add_object_doc(oid, path, (p.get("title") or "").strip())
        self._json({"ok": True, "docs": core.object_docs(oid)})

    def _save_report_data(self, data: dict) -> dict:
        year = date.today().year
        con = core.connect()
        row = con.execute("SELECT value FROM counters WHERE kind='report' AND year=?", (year,)).fetchone()
        n = (row["value"] if row else 0) + 1
        con.execute("INSERT INTO counters(kind,year,value) VALUES ('report',?,?) "
                    "ON CONFLICT(kind,year) DO UPDATE SET value=excluded.value", (year, n))
        con.commit()
        con.close()
        number = f"{n:03d}-СК.{str(year)[2:]}"
        record = {
            "number": number,
            "date_from": data.get("date_from") or date.today().isoformat(),
            "date_to": data.get("date_to") or date.today().isoformat(),
            "object_name": (data.get("address") or data.get("object_title") or "").strip(),
            "customer": (data.get("customer") or "").strip(),
            "contract": (data.get("contract") or "").strip(),
            "payload": data,
        }
        fname = safe_name(f"Отчёт {number} {record['object_name']}.docx").strip()
        out = docs.doc_folder("Отчёты") / fname
        reportgen.build(record, out)
        con = core.connect()
        cur = con.execute(
            "INSERT INTO reports(number,rdate,date_from,date_to,object_name,customer,contract,payload,created_at,file)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (number, date.today().isoformat(), record["date_from"], record["date_to"],
             record["object_name"], record["customer"], record["contract"],
             json.dumps(data, ensure_ascii=False), date.today().isoformat(),
             str(out.relative_to(BASE))))
        con.commit()
        rid = cur.lastrowid
        con.close()
        return {"id": rid, "number": number, "file": str(out.relative_to(BASE))}

    def _agent_report(self, p):
        oid = int(p.get("object_id") or 0)
        con = core.connect()
        row = con.execute("SELECT * FROM objects WHERE id=?", (oid,)).fetchone()
        con.close()
        if not row:
            return self._err("Объект не найден", 404)
        obj = dict(row)
        try:
            payload, log = ai.build_report_payload(
                oid, obj["name"],
                p.get("date_from") or date.today().isoformat(),
                p.get("date_to") or date.today().isoformat(),
                p.get("specialist") or core.company().get("lab_head", ""),
                customer=obj.get("customer") or "",
                contract=p.get("contract") or "",
                object_title=p.get("object_title") or "")
        except ai.AIError as e:
            return self._err(str(e))
        result = self._save_report_data(payload)
        result.update({"log": log, "payload": payload, "ai": ai.available()})
        self._json({"ok": True, **result})

    def _agent_photo(self, p):
        try:
            text = ai.describe_photos(p.get("paths") or [], p.get("object_name") or "")
        except ai.AIError as e:
            return self._err(str(e))
        self._json({"ok": True, "text": text})

    def _attach(self, qs):
        name = (qs.get("name") or ["file.bin"])[0]
        length = int(self.headers.get("Content-Length") or 0)
        if length <= 0:
            return self._err("Пустой файл")
        if length > 80 * 1024 * 1024:
            return self._err("Файл больше 80 МБ")
        data = self.rfile.read(length)
        sub = core.DATA / "files" / date.today().strftime("%Y-%m")
        sub.mkdir(parents=True, exist_ok=True)
        fname = safe_name(f"{date.today().isoformat()}_{name}")
        path = sub / fname
        i = 1
        while path.exists():
            path = sub / safe_name(f"{date.today().isoformat()}_{i}_{name}")
            i += 1
        path.write_bytes(data)
        rel = str(path.relative_to(core.DATA / "files")).replace("\\", "/")
        self._json({"ok": True, "path": str(path), "rel": rel, "name": path.name, "size": len(data)})

    def _ai(self, p):
        settings = core.get_setting("ai", {}) or {}
        key = settings.get("key") or os.environ.get("SMK_AI_KEY", "")
        if not key:
            return self._err("Не задан ключ ИИ. Откройте «Настройки» → «Искусственный интеллект».")
        base_url = (settings.get("base") or "https://api.deepseek.com/v1").rstrip("/")
        model = settings.get("model") or "deepseek-chat"
        messages = [{"role": "system", "content": p.get("system") or "Ты — помощник инженера строительного контроля. Пиши официальным русским языком."}]
        content = p.get("prompt") or ""
        photos = p.get("photos") or []
        if photos and settings.get("vision"):
            parts = [{"type": "text", "text": content}]
            for ph in photos[:6]:
                try:
                    b = Path(ph).read_bytes()
                    parts.append({"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode()}})
                except Exception:
                    pass
            messages.append({"role": "user", "content": parts})
        else:
            messages.append({"role": "user", "content": content})
        body = json.dumps({"model": model, "messages": messages, "temperature": 0.3}).encode()
        req = urllib.request.Request(base_url + "/chat/completions", data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": "Bearer " + key})
        try:
            with urllib.request.urlopen(req, timeout=90) as resp:
                data = json.loads(resp.read().decode())
            text = data["choices"][0]["message"]["content"]
            self._json({"ok": True, "text": text})
        except Exception as e:
            self._err("Ошибка обращения к ИИ: " + str(e))


def _backup_loop():
    time.sleep(30)
    while True:
        try:
            cfg = core.get_setting("backup", {}) or {}
            if cfg.get("auto", True):
                last = (backup.list_backups() or [{}])[0].get("date", "")
                today = date.today().isoformat()
                if not last.startswith(today):
                    backup.create_backup()
        except Exception:
            traceback.print_exc()
        time.sleep(3600)


def _auto_caption(entry_id: int, oid: int, comment: str):
    try:
        con = core.connect()
        row = con.execute("SELECT photos FROM entries WHERE id=?", (entry_id,)).fetchone()
        con.close()
        if not row:
            return
        photos = json.loads(row["photos"] or "[]")
        changed = False
        for ph in photos[:3]:
            if not isinstance(ph, dict) or ph.get("caption"):
                continue
            rel = ph.get("rel") or ph.get("path") or ""
            if not rel:
                continue
            try:
                res = ai.analyze_photo(oid, rel, comment)
            except Exception:
                continue
            if res.get("caption"):
                ph["caption"] = res["caption"]
                ph["work"] = res.get("work") or ""
                changed = True
        if changed:
            con = core.connect()
            con.execute("UPDATE entries SET photos=? WHERE id=?",
                        (json.dumps(photos, ensure_ascii=False), entry_id))
            con.commit()
            con.close()
    except Exception:
        traceback.print_exc()


def _auto_classify(oid: int):
    try:
        res = ai.classify_project(oid)
    except Exception:
        return
    con = core.connect()
    fields = {}
    for k in ("object_title", "address", "customer", "contractor", "contract"):
        if res.get(k):
            fields[k] = res[k][:200]
    if res.get("short_name"):
        fields["name"] = res["short_name"][:80]
    city = (res.get("city") or "").strip()
    if not city:
        city = (res.get("address") or "").split(",")[0].strip()
    if city:
        city = re.sub(r"^(м\.о\.|московская\s+обл\.?|обл\.?|г\.)\s*", "", city, flags=re.I).strip(" ,")
        gid = core.ensure_group(city)
        fields["group_id"] = gid
        fields["city"] = city
    if fields:
        sets = ", ".join(f"{k}=?" for k in fields)
        con.execute(f"UPDATE objects SET {sets} WHERE id=?", (*fields.values(), oid))
        con.commit()
    con.close()


def _scheduler_loop():
    time.sleep(8)
    while True:
        try:
            autoreport.run_due()
        except Exception:
            traceback.print_exc()
        time.sleep(60)


PUBLIC_PATHS = ("/api/login", "/api/logout", "/api/state", "/api/users", "/api/users/toggle",
                "/api/register", "/api/telegram/link", "/sw.js", "/manifest.webmanifest")


def _hash_pin(pin: str) -> str:
    return hashlib.sha256(("smk:" + str(pin)).encode("utf-8")).hexdigest()


def _cookie_user(handler):
    raw = handler.headers.get("Cookie") or ""
    for part in raw.split(";"):
        k, _, v = part.strip().partition("=")
        if k == "smk_user" and v:
            try:
                con = core.connect()
                row = con.execute("SELECT * FROM users WHERE id=? AND active=1", (int(v),)).fetchone()
                con.close()
                return dict(row) if row else None
            except Exception:
                return None
    return None


def _norm_phone(phone: str) -> str:
    d = "".join(ch for ch in (phone or "") if ch.isdigit())
    if len(d) == 11 and d[0] == "8":
        d = "7" + d[1:]
    if len(d) == 10:
        d = "7" + d
    return d


def _extra(uid: int) -> dict:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS user_extra (
        user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
        tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT,
        signature TEXT, position TEXT)""")
    cols = {r["name"] for r in con.execute("PRAGMA table_info(user_extra)")}
    for c in ("signature", "position"):
        if c not in cols:
            con.execute(f"ALTER TABLE user_extra ADD COLUMN {c} TEXT DEFAULT ''")
    con.commit()
    row = con.execute("SELECT * FROM user_extra WHERE user_id=?", (uid,)).fetchone()
    con.close()
    return dict(row) if row else {}


def _signer(handler) -> dict | None:
    user = getattr(handler, "user", None)
    if not user:
        return None
    ex = _extra(user["id"])
    roles = user_roles(user)
    pos = (ex.get("position") or "").strip()
    if not pos:
        pos = ("Инженер строительного контроля" if "engineer" in roles else
               "Руководитель лаборатории" if "lab_head" in roles else
               "Лаборант" if "lab" in roles else "Специалист")
    return {"pos": pos, "name": user.get("name") or "", "img": ex.get("signature") or ""}


def _extra_set(uid: int, **kw):
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS user_extra (
        user_id INTEGER PRIMARY KEY, phone TEXT, status TEXT DEFAULT 'active',
        tg_chat TEXT, otp TEXT, otp_exp TEXT, link_token TEXT)""")
    cur = _extra(uid)
    if not cur:
        con.execute("INSERT INTO user_extra(user_id,status) VALUES (?, 'active')", (uid,))
    keys = ", ".join(f"{k}=?" for k in kw)
    con.execute(f"UPDATE user_extra SET {keys} WHERE user_id=?", (*kw.values(), uid))
    con.commit()
    con.close()


def _otp() -> str:
    import random
    return f"{random.randint(0, 999999):06d}"


def _tg_send(chat: str, text: str) -> bool:
    import urllib.parse
    token = ((core.get_setting("messenger", {}) or {}).get("telegram_token") or "").strip()
    if not token or not chat:
        return False
    try:
        data = urllib.parse.urlencode({"chat_id": chat, "text": text}).encode()
        urllib.request.urlopen(f"https://api.telegram.org/bot{token}/sendMessage", data=data,
                               timeout=15).read()
        return True
    except Exception:
        return False


def _bot_loop():
    import time as _time
    offset = 0
    while True:
        token = ((core.get_setting("messenger", {}) or {}).get("telegram_token") or "").strip()
        if not token:
            _time.sleep(15)
            continue
        try:
            url = f"https://api.telegram.org/bot{token}/getUpdates?timeout=20&offset={offset}"
            data = json.loads(urllib.request.urlopen(url, timeout=30).read())
            for upd in data.get("result", []):
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                text = (msg.get("text") or "").strip()
                chat = str((msg.get("chat") or {}).get("id") or "")
                if not chat:
                    continue
                if text.startswith("/start"):
                    parts = text.split()
                    if len(parts) > 1:
                        _link_telegram(parts[1].strip(), chat)
                    else:
                        _tg_send(chat, "Откройте ссылку из программы, чтобы привязать аккаунт.")
                elif text.startswith("/code"):
                    row = _user_by_chat(chat)
                    if row:
                        code = _otp()
                        _extra_set(row["id"], otp=code,
                                   otp_exp=(datetime.now() + timedelta(minutes=30)).isoformat())
                        _tg_send(chat, f"Код для входа: {code}")
        except Exception:
            _time.sleep(5)


def _link_telegram(token: str, chat: str):
    con = core.connect()
    row = con.execute("SELECT user_id FROM user_extra WHERE link_token=?", (token,)).fetchone()
    con.close()
    if not row:
        _tg_send(chat, "Ссылка устарела. Запросите новую в программе.")
        return
    _extra_set(row["user_id"], tg_chat=chat)
    _tg_send(chat, "Telegram привязан. Код для входа придёт сюда.")


def _user_by_chat(chat: str):
    con = core.connect()
    row = con.execute(
        "SELECT u.* FROM users u JOIN user_extra e ON e.user_id=u.id WHERE e.tg_chat=?",
        (chat,)).fetchone()
    con.close()
    return dict(row) if row else None


def _table_exists(con, name):
    return con.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _users_exist() -> bool:
    con = core.connect()
    con.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, login TEXT UNIQUE,
        pin TEXT, role TEXT, active INTEGER DEFAULT 1, created_at TEXT)""")
    n = con.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
    con.close()
    return n > 0


ROLE_WRITE = {
    "admin": None,
    "engineer": ("/api/object", "/api/entry", "/api/protocol", "/api/report", "/api/schedule",
                 "/api/agent", "/api/attach", "/api/pdf", "/api/survey", "/api/import", "/api/upload"),
    "lab_head": ("/api/protocol", "/api/pdf", "/api/attach", "/api/upload"),
    "lab": ("/api/protocol", "/api/pdf", "/api/attach", "/api/upload"),
    "viewer": (),
}


def user_roles(user) -> list[str]:
    return [r.strip() for r in ((user or {}).get("role") or "").split(",") if r.strip()]


def user_is_admin(user) -> bool:
    return "admin" in user_roles(user)


def user_can_write(user, path: str) -> bool:
    roles = user_roles(user)
    if not roles:
        return True
    if "admin" in roles:
        return True
    for r in roles:
        if any(path.startswith(a) for a in ROLE_WRITE.get(r, ())):
            return True
    return False


def _can_write(user, path: str) -> bool:
    return user_can_write(user, path)


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def main():
    core.init_db()
    host = "0.0.0.0"

    httpd = None
    port = PORT
    for candidate in range(PORT, PORT + 20):
        try:
            httpd = LocalServer((host, candidate), Handler)
            port = candidate
            break
        except OSError:
            # порт занят: если это наша программа — открываем её и выходим
            try:
                with urllib.request.urlopen(f"http://{host}:{candidate}/api/state", timeout=2) as r:
                    if b'"ok": true' in r.read(200):
                        url = f"http://{host}:{candidate}"
                        print(f"Программа уже запущена: {url}")
                        webbrowser.open(url)
                        return
            except Exception:
                pass
            continue
    if httpd is None:
        print("Не удалось запустить сервер: все порты заняты.")
        input("Нажмите Enter, чтобы выйти...")
        return
    url = f"http://127.0.0.1:{port}"
    lan = local_ip()
    print("=" * 60)
    print("  НИЦ СМК · автоматизация документов")
    print(f"  Открыть: {url}")
    if lan and not lan.startswith("127."):
        print(f"  С телефона (та же Wi-Fi): http://{lan}:{port}")
    print("  Для остановки закройте это окно или нажмите Ctrl+C")
    print("=" * 60)
    if not os.environ.get("SMK_NO_BROWSER"):
        threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    threading.Thread(target=_scheduler_loop, daemon=True).start()
    threading.Thread(target=_backup_loop, daemon=True).start()
    try:
        threading.Thread(target=_bot_loop, daemon=True).start()
    except Exception:
        pass
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nОстановлено.")


if __name__ == "__main__":
    main()
