#!/usr/bin/env python3
"""Agentic vision editor (TASK-65; spec doc titled "TASK-53").

Extension of the Cast Registry premium line: Gemma 3 4B (vision, via
llama-mtmd-cli) LOOKS at already-flagged problem pages (box_overlap /
overflow from the algorithmic QA pass) and PROPOSES fixes using the exact
same edit API a human uses - PUT /api/edit/manga-bbox (TASK-36 geometry/
font-size) and PUT /api/edit/manga-text. Every proposal lands in
edit_store as status=pending with source="gemma_agent" and goes through
the same human Approve/Discard gate as any manual edit.

Hard rules (direct lessons from the removed TASK-17 editor_model):
- NOTHING is ever applied without human approval. agent_auto_approve is
  read but deliberately NOT honored in v1 - no exceptions.
- Only algorithmically flagged cases are examined (never the whole book).
- MemPalace is queried (best-effort) for precedent before proposing a
  text change; approved decisions are recorded elsewhere (approve hook in
  app.py) - this script never writes to any translation memory itself.
"""
import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kbg_web import edit_store

MODEL_DEFAULT = os.path.expanduser("~/models/gemma3-4b/gemma-3-4b-it-Q4_K_M.gguf")
MMPROJ_DEFAULT = os.path.expanduser("~/models/gemma3-4b/mmproj-model-f16.gguf")
MTMD_CLI = os.path.expanduser("~/llama.cpp/build/bin/llama-mtmd-cli")

FLAG_REASONS = ("box_overlap", "overflow", "text_overflow")

PROMPT_TEMPLATE = """You are a manga typesetting QA agent. Look at the attached translated manga page.

A quality check flagged this problem:
{facts}

Decide the SINGLE best fix and answer with ONLY a JSON object, no other text:
{{"action": "bbox" | "font_size" | "text" | "none",
  "bbox": [x1, y1, x2, y2],          // only for action=bbox, absolute pixels on this image ({width}x{height})
  "font_size": <int 8-200>,           // only for action=font_size
  "translated_text": "...",           // only for action=text (Ukrainian)
  "rationale": "one short sentence why"}}

Rules: prefer the least invasive fix (usually shrinking/moving the box or
reducing font size); only propose "text" if the translation itself is
clearly wrong or too long for any reasonable box; "none" if the render
actually looks fine."""


def log(msg):
    print(f"[agent_editor] {msg}", flush=True)


def api_call(api_base, auth, method, path, payload):
    import requests
    url = api_base.rstrip("/") + path
    r = requests.request(method, url, json=payload, auth=auth, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})


def query_mempalace(text):
    """Best-effort precedent lookup; absent URL or any failure -> None."""
    url = os.environ.get("KBG_MEMPALACE_URL")
    if not url or not text:
        return None
    try:
        import requests
        r = requests.get(url.rstrip("/") + "/api/tm/search",
                         params={"q": text[:200]}, timeout=5)
        if r.ok:
            hits = r.json()
            if isinstance(hits, list) and hits:
                return json.dumps(hits[:3], ensure_ascii=False)
    except Exception:
        pass
    return None


def run_vision(model, mmproj, image_path, prompt, timeout=1200):
    cmd = [MTMD_CLI, "-m", model, "--mmproj", mmproj, "--image", image_path,
           "-c", "8192", "-n", "512", "--temp", "0.2", "-p", prompt]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    return res.stdout


def parse_proposal(raw):
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def validate_proposal(prop, width, height):
    """Return (kind, payload_fragment) or (None, reason)."""
    action = (prop or {}).get("action")
    if action == "none":
        return "none", None
    if action == "bbox":
        bbox = prop.get("bbox")
        if not (isinstance(bbox, list) and len(bbox) == 4
                and all(isinstance(v, (int, float)) for v in bbox)):
            return None, "malformed bbox"
        x1, y1, x2, y2 = [int(v) for v in bbox]
        if not (0 <= x1 < x2 <= width and 0 <= y1 < y2 <= height):
            return None, f"bbox out of bounds for {width}x{height}"
        return "bbox", {"bbox": [x1, y1, x2, y2], "ref_size": [width, height]}
    if action == "font_size":
        try:
            fs = int(prop.get("font_size"))
        except (TypeError, ValueError):
            return None, "malformed font_size"
        if not (8 <= fs <= 200):
            return None, "font_size out of range"
        return "bbox", {"font_size": fs}
    if action == "text":
        text = (prop.get("translated_text") or "").strip()
        if not text:
            return None, "empty text"
        return "text", {"translated_text": text}
    return None, f"unknown action {action!r}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--limit", type=int, default=5)
    ap.add_argument("--model", default=MODEL_DEFAULT)
    ap.add_argument("--mmproj", default=MMPROJ_DEFAULT)
    ap.add_argument("--api", default="http://127.0.0.1:5000")
    args = ap.parse_args()

    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    book_dir = os.path.join(repo, "books", args.book)

    cfg = {}
    try:
        cfg = json.load(open(os.path.join(book_dir, "config.json"), encoding="utf-8"))
    except Exception:
        pass
    if not cfg.get("enable_agent_editor"):
        log("enable_agent_editor is not true for this book - refusing to run (opt-in).")
        return 1
    if cfg.get("agent_auto_approve"):
        log("agent_auto_approve=true is IGNORED in v1 - every proposal still requires human approval.")

    for p in (args.model, args.mmproj, MTMD_CLI):
        if not os.path.exists(p):
            log(f"missing required file: {p}")
            return 1

    # RAM guard: the first live run OOM-killed the ENTIRE Termux session
    # (Android low-memory killer) because Gemma vision (~3.3GB) was loaded
    # on top of the resident llama-server translation model (~4.4GB).
    # Refuse to start rather than take the whole phone environment down -
    # and never silently kill the user's llama-server ourselves (it may be
    # mid-translation on another book).
    try:
        meminfo = {l.split(":")[0]: int(l.split()[1])
                   for l in open("/proc/meminfo") if ":" in l}
        avail_gb = meminfo.get("MemAvailable", 0) / 1024 / 1024
    except Exception:
        avail_gb = None
    if avail_gb is not None and avail_gb < 5.0:
        llama_up = subprocess.run(["pgrep", "-f", "llama-server"],
                                  capture_output=True).returncode == 0
        log(f"ABORT: only {avail_gb:.1f}GB RAM available; the vision model needs ~5GB headroom "
            f"or Android will OOM-kill all of Termux (happened on the first live run).")
        if llama_up:
            log("llama-server is holding the translation model - stop it first "
                "(Models Manager -> Stop Server), then re-run the agent scan.")
        return 1

    user = os.environ.get("KBG_WEB_USER", "admin")
    password = os.environ.get("KBG_WEB_PASSWORD", "")
    auth = (user, password)

    flags_path = os.path.join(book_dir, "quality_flags.json")
    try:
        flags = json.load(open(flags_path, encoding="utf-8"))
    except Exception as e:
        log(f"cannot read quality_flags.json: {e}")
        return 1
    cases = [f for f in flags if f.get("reason") in FLAG_REASONS]
    log(f"{len(cases)} flagged case(s); limit {args.limit}")

    existing = {e["target_id"] for e in edit_store.list_edits(args.book)
                if e["status"] in ("pending", "approved")}

    proposed = skipped = 0
    for case in cases:
        if proposed >= args.limit:
            break
        page = case.get("page", "")
        bubble_id = case.get("bubble_id", "")
        target_id = f"{page}#{bubble_id}"
        if target_id in existing:
            log(f"skip {bubble_id}: edit already pending/approved")
            skipped += 1
            continue

        image_path = os.path.join(book_dir, "preview_cache", "translated", page)
        if not os.path.exists(image_path):
            log(f"skip {bubble_id}: rendered page not found ({page})")
            skipped += 1
            continue

        stem = os.path.splitext(page)[0]
        try:
            bubbles = json.load(open(os.path.join(book_dir, "bubbles_meta", f"{stem}.json"), encoding="utf-8"))
        except Exception:
            log(f"skip {bubble_id}: no bubbles_meta")
            skipped += 1
            continue
        bubble = next((b for b in bubbles if b["id"] == bubble_id), None)
        if not bubble:
            log(f"skip {bubble_id}: bubble not in meta")
            skipped += 1
            continue

        # Canonical bubble coordinate space (no PIL on the Termux host -
        # TASK-57 lesson; bubbles_meta already carries the reference size,
        # and using it keeps every number in the prompt consistent with
        # the bubble bboxes, which are stored in that same space).
        ref = bubble.get("bbox_ref_size")
        if not (isinstance(ref, list) and len(ref) == 2):
            log(f"skip {bubble_id}: no bbox_ref_size in meta")
            skipped += 1
            continue
        width, height = int(ref[0]), int(ref[1])
        facts = {
            "reason": case.get("reason"),
            "bubble_id": bubble_id,
            "bubble_bbox": case.get("box") or bubble.get("bbox"),
            "overlapping_with": case.get("overlapping_with"),
            "iou": case.get("iou"),
            "current_translated_text": bubble.get("translated_text"),
            "original_text": bubble.get("original_text"),
        }
        precedent = query_mempalace(bubble.get("original_text") or "")
        if precedent:
            facts["translation_precedents"] = precedent

        prompt = PROMPT_TEMPLATE.format(
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
            width=width, height=height)

        log(f"vision pass: {bubble_id} ({case.get('reason')})...")
        try:
            raw = run_vision(args.model, args.mmproj, image_path, prompt)
        except subprocess.TimeoutExpired:
            log(f"skip {bubble_id}: vision call timed out")
            skipped += 1
            continue

        prop = parse_proposal(raw)
        kind, payload = validate_proposal(prop, width, height)
        if kind is None:
            log(f"skip {bubble_id}: invalid proposal ({payload}); raw tail: {raw[-200:]!r}")
            skipped += 1
            continue
        if kind == "none":
            log(f"{bubble_id}: agent says render is fine - no proposal")
            skipped += 1
            continue

        body = dict(payload)
        body["bubble_id"] = bubble_id
        body["source"] = "gemma_agent"
        endpoint = f"/api/edit/manga-{'bbox' if kind == 'bbox' else 'text'}/{args.book}/{page}"
        status, resp = api_call(args.api, auth, "PUT", endpoint, body)
        if status == 200:
            proposed += 1
            existing.add(target_id)
            log(f"PROPOSED {kind} for {bubble_id}: {json.dumps(payload, ensure_ascii=False)}"
                f" | rationale: {prop.get('rationale', '')!r}")
        else:
            skipped += 1
            log(f"skip {bubble_id}: API {status}: {resp.get('message')}")

    log(f"done: {proposed} proposal(s) submitted as pending (source=gemma_agent), {skipped} skipped.")
    log("Nothing was applied - review in Pending Edits (Approve/Discard).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
