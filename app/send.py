# -*- coding: utf-8 -*-
"""Отправка готовых документов заказчику: e-mail (SMTP) и мессенджеры."""
from __future__ import annotations

import json
import mimetypes
import smtplib
import ssl
import urllib.parse
import urllib.request
import uuid
from email.message import EmailMessage
from pathlib import Path

from . import core


def smtp_cfg() -> dict:
    return core.get_setting("smtp", {}) or {}


def messenger_cfg() -> dict:
    return core.get_setting("messenger", {}) or {}


def send_email(to: str, subject: str, body: str, files: list[str]) -> dict:
    c = smtp_cfg()
    host = (c.get("host") or "").strip()
    if not host:
        return {"ok": False, "error": "Почта не настроена: Настройки → Почта (SMTP-сервер, логин, пароль)."}
    port = int(c.get("port") or 465)
    user = (c.get("user") or "").strip()
    pwd = c.get("password") or ""
    sender = (c.get("from") or user or "").strip()
    if not sender:
        return {"ok": False, "error": "Не указан адрес отправителя"}
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    for rel in files:
        p = core.BASE / rel
        if not p.exists():
            continue
        data = p.read_bytes()
        ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
        maintype, _, subtype = ctype.partition("/")
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=p.name)
    try:
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as s:
                if user:
                    s.login(user, pwd)
                s.send_message(msg)
        else:
            with smtplib.SMTP(host, port, timeout=30) as s:
                s.ehlo()
                if c.get("tls", True):
                    s.starttls(context=ctx)
                    s.ehlo()
                if user:
                    s.login(user, pwd)
                s.send_message(msg)
    except Exception as e:
        return {"ok": False, "error": "Не удалось отправить: " + str(e)}
    return {"ok": True, "to": to}


def send_telegram(caption: str, files: list[str]) -> dict:
    c = messenger_cfg()
    token = (c.get("telegram_token") or "").strip()
    chat = (c.get("telegram_chat") or "").strip()
    if not token or not chat:
        return {"ok": False, "error": "Telegram не настроен: Настройки → Почта → Telegram (токен бота и chat_id)."}
    for rel in files:
        p = core.BASE / rel
        if not p.exists():
            continue
        boundary = "----smk" + uuid.uuid4().hex
        parts = []
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat}\r\n")
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption[:900]}\r\n")
        body = b"".join(x.encode("utf-8") for x in parts)
        body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{p.name}\"\r\n"
                 f"Content-Type: application/octet-stream\r\n\r\n").encode("utf-8")
        body += p.read_bytes() + b"\r\n"
        body += f"--{boundary}--\r\n".encode("utf-8")
        req = urllib.request.Request(
            f"https://api.telegram.org/bot{token}/sendDocument", data=body,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary})
        try:
            urllib.request.urlopen(req, timeout=60).read()
        except Exception as e:
            return {"ok": False, "error": "Telegram: " + str(e)}
    return {"ok": True}


def messenger_links(phone: str, text: str) -> dict:
    t = urllib.parse.quote(text)
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())
    return {
        "whatsapp": f"https://wa.me/{digits}?text={t}" if digits else "",
        "telegram": f"https://t.me/share/url?url=&text={t}",
        "sms": f"sms:?&body={t}",
    }
