"""Vydra (🦦) conversion heartbeat watchdog — Appwrite Function.

**Deploy this function as SCHEDULE-TRIGGER ONLY, with no HTTP execute
permission granted to anyone (including "any").** Unlike tg-support-bot,
this function does not authenticate its invocation - it relies entirely
on Appwrite's own trigger-permission model to ensure it only ever runs
on the configured cron schedule, never from an arbitrary HTTP caller.
Do not add an HTTP-callable path to this function without adding real
request authentication first.

Purpose: phones periodically heartbeat their active conversion via
tg-support-bot's /heartbeat path (see that function's `_heartbeat()`),
writing `last_heartbeat_ts` + `active_book_slug` on their user document.
Termux/Android can silently kill the whole phone-side process tree
(confirmed live 2026-07-19 - twice in one session) with zero signal
reaching the user; auto-resume-on-restart handles recovery once the user
reopens Termux, but nothing told them to. This function scans for users
whose heartbeat has gone stale while a book was still marked active, and
sends them a Telegram nudge to reopen Termux.

Recommended schedule: every 5 minutes (`*/5 * * * *`).
"""
import os
from datetime import datetime, timezone

import requests
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.query import Query

DB_ID = "kbg-support"
COLL_ID = "users"

# 15 min: comfortably above the phone's own per-page heartbeat cadence
# (roughly one heartbeat every 20-40s during active translation), so a
# real stall reliably crosses this well before the timer wrongly fires
# during ordinary variance (a single slow page, a brief network drop).
STALE_SECONDS = 15 * 60

# Don't re-alert every 5-minute tick for a phone that's been dead for
# hours - only nudge again after this much time since the last alert.
REALERT_SECONDS = 30 * 60


def _tg_send(token, chat_id, text):
    try:
        requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
    except requests.RequestException:
        pass  # best-effort; a missed nudge isn't worth failing the run over


def main(context):
    res = context.res
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        context.log("TELEGRAM_BOT_TOKEN not configured - nothing to do.")
        return res.json({"ok": False, "error": "bot token not configured"})

    client = (Client()
              .set_endpoint(os.environ.get("APPWRITE_FUNCTION_API_ENDPOINT",
                                           "https://fra.cloud.appwrite.io/v1"))
              .set_project(os.environ["APPWRITE_FUNCTION_PROJECT_ID"])
              .set_key(context.req.headers.get("x-appwrite-key", "")))
    db = Databases(client)

    now = int(datetime.now(timezone.utc).timestamp())
    users = db.list_documents(DB_ID, COLL_ID, queries=[
        Query.is_not_null("active_book_slug"),
        Query.limit(100),
    ])

    nudged = 0
    for user in users.get("documents", []):
        last_hb = int(user.get("last_heartbeat_ts") or 0)
        if last_hb == 0:
            continue
        age = now - last_hb
        if age < STALE_SECONDS:
            continue
        last_alert = int(user.get("last_stall_alert_ts") or 0)
        if now - last_alert < REALERT_SECONDS:
            continue

        book = user.get("active_book_slug", "книгу")
        progress = user.get("active_book_progress", "")
        stage = user.get("active_book_stage", "") or "переклад"
        progress_txt = f" ({progress})" if progress else ""
        # Agent-editor proposals require explicit human review even after
        # resume (source="gemma_agent" edits always land pending, never
        # auto-applied) - the resume note differs so the user isn't told
        # "продовжиться автоматично" for a step that still needs them.
        resume_note = ("відкрийте вкладку «Агент» і натисніть запуск ще раз"
                        if "агент" in stage.lower()
                        else "переклад продовжиться з того ж місця автоматично")
        _tg_send(token, int(user["telegram_id"]),
                 f"⏸️ Схоже, {stage} книги «{book}»{progress_txt} зупинився(-лася) — "
                 f"Termux на телефоні міг закритися сам. Відкрийте застосунок "
                 f"Termux ще раз, {resume_note}.")
        db.update_document(DB_ID, COLL_ID, user["$id"],
                           data={"last_stall_alert_ts": now})
        nudged += 1

    context.log(f"Checked {len(users.get('documents', []))} active users, nudged {nudged}.")
    return res.json({"ok": True, "checked": len(users.get("documents", [])), "nudged": nudged})
