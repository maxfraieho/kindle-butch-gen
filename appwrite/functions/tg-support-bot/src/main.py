"""Vydra (🦦) support-system Telegram bot — Appwrite Function (TASK-49).

HTTP-triggered by a Telegram webhook. Commands:
  /start [ref_code]  — register, generate personal referral code; with a
                       valid deep-link code, records referred_by and
                       bumps the referrer's priority_tier by 1.
  /referral          — personal code + how many people joined with it.
  /no_support_banner — one-step opt-out, instant confirmation.

Security: every request must carry Telegram's
X-Telegram-Bot-Api-Secret-Token matching TG_WEBHOOK_SECRET (set when the
webhook is registered) — anything else gets 401 and no processing.

Architectural split (Q, 2026-07-17): Appwrite = registration/referrals/
site only. All AI generation stays self-hosted on the phone; the phone
reads this database read-only and NEVER blocks on it.
"""
import json
import os
import secrets

import requests
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query
from appwrite.id import ID

DB_ID = "kbg-support"
COLL_ID = "users"


def _tg_send(token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                  "disable_web_page_preview": True},
            timeout=10,
        )
    except requests.RequestException:
        pass  # Telegram hiccup must not fail the webhook (it would retry forever)


def _get_user(db, tg_id):
    res = db.list_documents(DB_ID, COLL_ID,
                            queries=[Query.equal("telegram_id", str(tg_id))])
    docs = res.get("documents", [])
    return docs[0] if docs else None


def main(context):
    req, res = context.req, context.res

    secret = os.environ.get("TG_WEBHOOK_SECRET", "")
    header = req.headers.get("x-telegram-bot-api-secret-token", "")
    if not secret or header != secret:
        return res.json({"ok": False, "error": "unauthorized"}, 401)

    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return res.json({"ok": False, "error": "bot token not configured"}, 500)

    try:
        update = req.body if isinstance(req.body, dict) else json.loads(req.body_raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return res.json({"ok": True})  # not for us; ack so Telegram stops retrying

    msg = update.get("message") or update.get("edited_message") or {}
    chat_id = (msg.get("chat") or {}).get("id")
    tg_id = (msg.get("from") or {}).get("id")
    text = (msg.get("text") or "").strip()
    if not chat_id or not tg_id or not text.startswith("/"):
        return res.json({"ok": True})

    client = (Client()
              .set_endpoint(os.environ.get("APPWRITE_FUNCTION_API_ENDPOINT",
                                           "https://fra.cloud.appwrite.io/v1"))
              .set_project(os.environ["APPWRITE_FUNCTION_PROJECT_ID"])
              .set_key(req.headers.get("x-appwrite-key", "")))
    db = Databases(client)

    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    arg = arg.strip()

    if cmd == "/start":
        user = _get_user(db, tg_id)
        if user:
            _tg_send(token, chat_id,
                     "Ви вже зареєстровані ✅\n"
                     f"Ваш реферальний код: <code>{user['referral_code']}</code>\n"
                     "Команди: /referral — ваш код і запрошені; "
                     "/no_support_banner — вимкнути примітки підтримки в книгах.")
            return res.json({"ok": True})

        code = secrets.token_hex(4)
        referred_by = None
        if arg:
            ref = db.list_documents(DB_ID, COLL_ID,
                                    queries=[Query.equal("referral_code", arg)])
            ref_docs = ref.get("documents", [])
            if ref_docs and str(ref_docs[0]["telegram_id"]) != str(tg_id):
                referred_by = arg
                referrer = ref_docs[0]
                db.update_document(DB_ID, COLL_ID, referrer["$id"], data={
                    "priority_tier": int(referrer.get("priority_tier") or 0) + 1,
                })

        from datetime import datetime, timezone
        db.create_document(DB_ID, COLL_ID, ID.unique(), data={
            "telegram_id": str(tg_id),
            "referral_code": code,
            "referred_by": referred_by,
            "banner_disabled": False,
            "priority_tier": 1 if referred_by else 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        bonus = ("\n🎁 Ви прийшли за запрошенням — вам і другу нараховано "
                 "пріоритет у черзі генерації.") if referred_by else ""
        _tg_send(token, chat_id,
                 "🦦 Вітаємо у Vydra — книги, аудіокниги та манґа українською,\n"
                 "все локально, на вашому пристрої. Без хмари і збору даних.\n"
                 f"Ваш реферальний код: <code>{code}</code>{bonus}\n\n"
                 "Команди:\n"
                 "/referral — ваш код і скільки людей приєдналось\n"
                 "/no_support_banner — вимкнути примітки підтримки в книгах")
        return res.json({"ok": True})

    if cmd == "/referral":
        user = _get_user(db, tg_id)
        if not user:
            _tg_send(token, chat_id, "Спершу зареєструйтесь: /start")
            return res.json({"ok": True})
        invited = db.list_documents(DB_ID, COLL_ID,
                                    queries=[Query.equal("referred_by",
                                                         user["referral_code"])])
        bot_name = os.environ.get("TELEGRAM_BOT_USERNAME", "")
        link = (f"\nПосилання: https://t.me/{bot_name}?start={user['referral_code']}"
                if bot_name else "")
        _tg_send(token, chat_id,
                 f"Ваш код: <code>{user['referral_code']}</code>{link}\n"
                 f"Запрошено: {invited.get('total', 0)}\n"
                 f"Ваш пріоритет у черзі: {user.get('priority_tier') or 0}")
        return res.json({"ok": True})

    if cmd == "/no_support_banner":
        user = _get_user(db, tg_id)
        if not user:
            _tg_send(token, chat_id, "Спершу зареєструйтесь: /start")
            return res.json({"ok": True})
        db.update_document(DB_ID, COLL_ID, user["$id"],
                           data={"banner_disabled": True})
        _tg_send(token, chat_id, "Готово, більше не показуватимемо ✅")
        return res.json({"ok": True})

    _tg_send(token, chat_id,
             "Команди: /start, /referral, /no_support_banner")
    return res.json({"ok": True})
