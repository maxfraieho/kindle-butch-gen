"""Read-only Appwrite profile lookup for the support system (TASK-49).

Architectural split (Q): Appwrite = registration/referrals only; ALL AI
generation stays on the phone. The phone therefore only ever READS here,
with a hard timeout, and every failure path answers with the safe
defaults - the banner counts as ENABLED and book generation is NEVER
blocked by the external service being down.

Credentials deliberately live OUTSIDE git:
  - key:  env KBG_APPWRITE_KEY, or first line of ~/.kbg_appwrite_key
  - who:  `appwrite` section of support_config.json (endpoint, project,
          telegram_id of this installation's owner)
"""
import json
import os

import requests

from common.support_banner import CONFIG_PATH

_TIMEOUT_S = 3
_SAFE_DEFAULTS = {"banner_disabled": False, "priority_tier": 0}


def _read_key():
    key = os.environ.get("KBG_APPWRITE_KEY", "").strip()
    if key:
        return key
    try:
        with open(os.path.expanduser("~/.kbg_appwrite_key"), "r",
                  encoding="utf-8") as f:
            return f.read().strip()
    except OSError:
        return ""


def fetch_profile():
    """Return {'banner_disabled': bool, 'priority_tier': int}.

    ANY problem - missing config/key, network error, timeout, HTTP error,
    unexpected payload, user not registered - returns the safe defaults.
    A wrong answer here may show one extra banner; it must never break or
    delay a build.
    """
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            aw = (json.load(f) or {}).get("appwrite") or {}
        endpoint = aw.get("endpoint", "").rstrip("/")
        project = aw.get("project", "")
        tg_id = str(aw.get("telegram_id", "")).strip()
        key = _read_key()
        if not (endpoint and project and tg_id and key):
            return dict(_SAFE_DEFAULTS)

        r = requests.get(
            f"{endpoint}/databases/{aw.get('database', 'kbg-support')}"
            f"/collections/{aw.get('collection', 'users')}/documents",
            headers={"X-Appwrite-Project": project, "X-Appwrite-Key": key},
            params={"queries[]": json.dumps(
                {"method": "equal", "attribute": "telegram_id",
                 "values": [tg_id]})},
            timeout=_TIMEOUT_S,
        )
        r.raise_for_status()
        docs = r.json().get("documents", [])
        if not docs:
            return dict(_SAFE_DEFAULTS)
        doc = docs[0]
        return {
            "banner_disabled": bool(doc.get("banner_disabled")),
            "priority_tier": int(doc.get("priority_tier") or 0),
        }
    except Exception:
        return dict(_SAFE_DEFAULTS)


def remote_banner_disabled():
    return fetch_profile()["banner_disabled"]


def get_priority_tier():
    return fetch_profile()["priority_tier"]
