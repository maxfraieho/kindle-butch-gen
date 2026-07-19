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
NOTIFY_FUNCTION_ID = "kbg-tg-support-bot"

# 5 min (Q's explicit call, 2026-07-19 - 15min felt too slow): still well
# above the phone's own per-page heartbeat cadence (roughly one heartbeat
# every 20-40s during active translation) and above the 5-minute schedule
# interval itself, so a real stall is caught on close to the first check
# after it happens without false-firing on ordinary per-page variance.
STALE_SECONDS = 5 * 60

# Q's explicit call, 2026-07-19: 30min felt too long, matches STALE_SECONDS
# now - re-nudge on essentially every schedule tick while still down,
# rather than going quiet for half an hour.
REALERT_SECONDS = 5 * 60


def _tg_send(endpoint, project, api_key, watchdog_secret, chat_id, text):
    """Routed through tg-support-bot's own _send_notification handler
    instead of holding a TELEGRAM_BOT_TOKEN here directly - one less
    place that sensitive value lives. Uses the Functions execution API,
    the same mechanism (and the SAME account API key this function's own
    x-appwrite-key already grants) used to test this path manually."""
    try:
        requests.post(
            f"{endpoint}/functions/{NOTIFY_FUNCTION_ID}/executions",
            headers={"X-Appwrite-Project": project, "X-Appwrite-Key": api_key,
                     "Content-Type": "application/json"},
            json={
                "async": True,
                "headers": {"x-vydra-watchdog-secret": watchdog_secret},
                "body": __import__("json").dumps({"chat_id": chat_id, "text": text}),
            },
            timeout=10,
        )
    except requests.RequestException:
        pass  # best-effort; a missed nudge isn't worth failing the run over


def main(context):
    res = context.res
    watchdog_secret = os.environ.get("WATCHDOG_SECRET", "")
    if not watchdog_secret:
        context.log("WATCHDOG_SECRET not configured - nothing to do.")
        return res.json({"ok": False, "error": "watchdog secret not configured"})
    endpoint = os.environ.get("APPWRITE_FUNCTION_API_ENDPOINT", "https://fra.cloud.appwrite.io/v1")
    project = os.environ["APPWRITE_FUNCTION_PROJECT_ID"]
    api_key = context.req.headers.get("x-appwrite-key", "")

    client = Client().set_endpoint(endpoint).set_project(project).set_key(api_key)
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
        # Every registered process type auto-resumes on Termux restart
        # (bin/resume_active_conversion.py), but what that means for the
        # USER differs: some genuinely finish unattended, others still
        # need a human step afterward. Keep this in sync with every
        # send_heartbeat(..., stage=...) call across the codebase.
        stage_l = stage.lower()
        if "агент" in stage_l:
            # source="gemma_agent" edits always land pending, never
            # auto-applied - resuming the scan doesn't apply anything by
            # itself.
            resume_note = "відкрийте вкладку «Агент» і натисніть запуск ще раз"
        elif "сканування персонажів" in stage_l:
            resume_note = ("сканування продовжиться автоматично; перевірте нових "
                           "персонажів у вкладці «Cast & Context» після завершення")
        else:
            # переклад / переклад книги / озвучення - all fully unattended resumes.
            resume_note = "продовжиться з того ж місця автоматично"
        _tg_send(endpoint, project, api_key, watchdog_secret, int(user["telegram_id"]),
                 f"⏸️ Схоже, {stage} книги «{book}»{progress_txt} зупинився(-лася) — "
                 f"Termux на телефоні міг закритися сам. Відкрийте застосунок "
                 f"Termux ще раз, {resume_note}.")
        db.update_document(DB_ID, COLL_ID, user["$id"],
                           data={"last_stall_alert_ts": now})
        nudged += 1

    context.log(f"Checked {len(users.get('documents', []))} active users, nudged {nudged}.")
    return res.json({"ok": True, "checked": len(users.get("documents", [])), "nudged": nudged})
