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
- v2: geometry fixes are computed deterministically; the vision model
  only veto-checks them. Text proposals were dropped entirely (approved
  human text edits still feed the translation memory via the approve
  hook in app.py - this script never writes memory itself).
"""
import argparse
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from kbg_web import edit_store

MODEL_DEFAULT = os.path.expanduser("~/models/gemma3-4b/gemma-3-4b-it-Q4_K_M.gguf")
MMPROJ_DEFAULT = os.path.expanduser("~/models/gemma3-4b/mmproj-model-f16.gguf")
MTMD_CLI = os.path.expanduser("~/llama.cpp/build/bin/llama-mtmd-cli")

FLAG_REASONS = ("box_overlap", "overflow", "text_overflow")

# v2 (Q's live feedback on v1): a 4B vision model CANNOT invent good
# coordinates - it played "least invasive" and produced +-10px tweaks and
# outright no-ops. Roles are now flipped: GEOMETRY computes the fix
# deterministically (resolve overlaps to zero intersection, widen
# distorting tall-narrow boxes), and vision only VETOES a computed
# candidate if the target area visibly contains artwork/other text.
VERIFY_PROMPT = """You are a manga typesetting reviewer. Look at the attached translated manga page.

A text box will be MOVED/RESIZED as follows (coordinates in a {width}x{height} pixel space):
{facts}

Question: would the NEW box position cover important artwork, a character's face,
or OTHER text that is not part of this box's own text? Answer ONLY JSON:
{{"approve": true|false, "reason": "one short sentence"}}"""


def _intersection(a, b):
    ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
    ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
    if ix1 >= ix2 or iy1 >= iy2:
        return None
    return (ix1, iy1, ix2, iy2)


def _overlaps_any(box, partners):
    return any(_intersection(box, p) for p in partners)


def resolve_overlap(box, partners, W, H, min_gap=8):
    """Minimal-displacement shift (or edge cut as fallback) that leaves
    ZERO intersection with every partner box. Returns a new [x1,y1,x2,y2]
    or None if no acceptable geometry exists."""
    x1, y1, x2, y2 = box
    for _ in range(4):  # a shift can create a new collision; few passes
        hit = next((p for p in partners if _intersection((x1, y1, x2, y2), p)), None)
        if hit is None:
            break
        moves = [
            (hit[0] - x2 - min_gap, 0),   # shift left of partner
            (hit[2] - x1 + min_gap, 0),   # shift right of partner
            (0, hit[1] - y2 - min_gap),   # shift above partner
            (0, hit[3] - y1 + min_gap),   # shift below partner
        ]
        placed = False
        for dx, dy in sorted(moves, key=lambda m: abs(m[0]) + abs(m[1])):
            nx1, ny1, nx2, ny2 = x1 + dx, y1 + dy, x2 + dx, y2 + dy
            if nx1 >= 0 and ny1 >= 0 and nx2 <= W and ny2 <= H \
                    and not _overlaps_any((nx1, ny1, nx2, ny2), partners):
                x1, y1, x2, y2 = nx1, ny1, nx2, ny2
                placed = True
                break
        if not placed:
            # No legal shift - cut the overlapping side instead.
            inter = _intersection((x1, y1, x2, y2), hit)
            if (inter[2] - inter[0]) <= (inter[3] - inter[1]):
                if hit[0] > x1:
                    x2 = hit[0] - min_gap
                else:
                    x1 = hit[2] + min_gap
            else:
                if hit[1] > y1:
                    y2 = hit[1] - min_gap
                else:
                    y1 = hit[3] + min_gap
            if (x2 - x1) < 40 or (y2 - y1) < 30:
                return None
    if _overlaps_any((x1, y1, x2, y2), partners):
        return None
    return [int(x1), int(y1), int(x2), int(y2)]


def is_nonsense_text(text):
    """OCR-garbage detector (Q's feedback on the real p173 case: a page-
    tall column reading 'му ікі ?а ащ и 2 от @ << пат) ее іб 2 ей').
    Counts tokens that look like real Ukrainian/Latin words (3+ letters,
    vowel present) vs noise tokens (symbols, digits, 1-2 char shards,
    vowelless clusters). Deterministic - no model call needed."""
    if not text:
        return False
    tokens = re.findall(r"\S+", text)
    if len(tokens) < 3:
        return False
    wordlike = 0
    for t in tokens:
        letters = re.sub(r"[^а-щьюяіїєґa-z]", "", t.lower())
        if len(letters) >= 3 and re.search(r"[аеиіоуюяєїa-z]", letters) \
                and re.search(r"[аеиіоуюяєї]|[aeiouy]", letters):
            wordlike += 1
    return wordlike / len(tokens) < 0.4


def reformat_horizontal(box, partners, W, H, min_gap=8):
    """Convert a page-tall vertical column into a horizontal box a
    left-to-right reader can actually read (target-language ergonomics:
    Ukrainian/European readers need horizontal lines; vertical stacking
    is a Japanese-typography artifact). Keeps the top edge, shrinks
    height hard, widens into whatever horizontal span is free. Returns
    a new box (guaranteed non-overlapping) or None."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w >= 0.6 * h:
        return None  # already horizontal-ish
    new_h = max(90, int(h * 0.22))
    row_partners = [p for p in partners if p[3] > y1 and p[1] < y1 + new_h]
    left_limit = max([0] + [p[2] + min_gap for p in row_partners if p[2] <= x1])
    right_limit = min([W] + [p[0] - min_gap for p in row_partners if p[0] >= x2])
    target_w = min(right_limit - left_limit, max(int(2.2 * new_h), int(w * 3)))
    if target_w < int(w * 1.5):
        return None
    cx = (x1 + x2) // 2
    nx1 = max(left_limit, min(cx - target_w // 2, right_limit - target_w))
    nx2 = nx1 + target_w
    cand = [int(nx1), int(y1), int(nx2), int(y1 + new_h)]
    if _overlaps_any(cand, partners):
        cand = resolve_overlap(cand, partners, W, H, min_gap)
    return cand


def widen_if_distorting(box, text, partners, W, H, min_gap=8):
    """A box much taller than wide squeezes text into a distorted
    one-character-per-line column. Widen it horizontally into free space
    (never into a partner box or off-page). Returns new box or None."""
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w >= 0.5 * h or len(text or "") < 8:
        return None
    target_w = min(int(1.3 * h), int(2.5 * w) + 60)
    grow = (target_w - w) / 2
    left_limit = max([0] + [p[2] + min_gap for p in partners if p[3] > y1 and p[1] < y2 and p[2] <= x1])
    right_limit = min([W] + [p[0] - min_gap for p in partners if p[3] > y1 and p[1] < y2 and p[0] >= x2])
    nx1 = max(left_limit, int(x1 - grow))
    nx2 = min(right_limit, int(x2 + grow))
    if (nx2 - nx1) < w * 1.3:
        return None  # not enough free space to make a real difference
    return [nx1, y1, nx2, y2]


def log(msg):
    print(f"[agent_editor] {msg}", flush=True)


def api_call(api_base, auth, method, path, payload):
    import requests
    url = api_base.rstrip("/") + path
    r = requests.request(method, url, json=payload, auth=auth, timeout=30)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else {})


def run_vision(model, mmproj, image_path, prompt, timeout=1200):
    # -t 4: deliberately NOT all cores. Full-load llama-mtmd-cli got the
    # entire Termux session killed by Android's background process killer
    # on the OnePlus 13 (known device behavior, independent of thermals -
    # happened WITH active cooling and 8GB free RAM). Slower per page but
    # survives.
    cmd = [MTMD_CLI, "-m", model, "--mmproj", mmproj, "--image", image_path,
           "-c", "8192", "-n", "512", "--temp", "0.2", "-t", "4", "-p", prompt]
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
        cur_box = case.get("box") or bubble.get("bbox")
        partner_ids = case.get("overlapping_with") or []
        partners = [b["bbox"] for b in bubbles
                    if b["id"] in partner_ids and b.get("bbox")]

        # 1. GEOMETRY computes the actual fix (deterministic - the thing
        # a human would do: розвести рамки, розширити спотворену).
        other_boxes = [b["bbox"] for b in bubbles
                       if b["id"] != bubble_id and b.get("bbox")]
        new_box = None
        fix_kind = None
        note = None

        # Nonsense-text branch first (Q's feedback): a page-tall column
        # of OCR garbage isn't a "shift it sideways" problem - the human
        # needs to know the TEXT itself is meaningless (likely decorative
        # kanji / chapter title), and the box should become horizontal
        # for a left-to-right reader.
        if is_nonsense_text(bubble.get("translated_text")):
            note = ("⚠️ Текст виглядає як OCR-шум без змісту (ймовірно "
                    "декоративний напис/назва розділу в оригіналі). Рамку "
                    "запропоновано переформатувати горизонтально - впишіть "
                    "правильний текст вручну, звірившись з оригіналом.")
            horiz = reformat_horizontal(cur_box, other_boxes, width, height)
            if horiz:
                new_box, fix_kind = horiz, "horizontal-reformat"
            else:
                # No room to reformat - still surface the finding: the
                # note IS the value; box stays as-is so approve is a
                # no-op geometrically but the flag reaches the human.
                new_box, fix_kind = [int(v) for v in cur_box], "nonsense-flag-only"
        else:
            widened = widen_if_distorting(cur_box, bubble.get("translated_text"),
                                          other_boxes, width, height)
            if widened and not _overlaps_any(widened, partners):
                new_box, fix_kind = widened, "widen-distorted-box"
            elif partners:
                resolved = resolve_overlap(cur_box, partners, width, height)
                if resolved and resolved != [int(v) for v in cur_box]:
                    new_box, fix_kind = resolved, "resolve-overlap"

        # Hard honesty gate: no computable real improvement -> NO proposal.
        # (v1 shipped +-10px tweaks and no-ops; better silence than noise.)
        # A nonsense-flag proposal is exempt: its value is the note itself.
        if new_box is None:
            log(f"skip {bubble_id}: no real geometric improvement computable "
                f"(box={cur_box}, partners={len(partners)})")
            skipped += 1
            continue
        if partners and _overlaps_any(new_box, partners) and fix_kind != "nonsense-flag-only":
            log(f"skip {bubble_id}: computed box still overlaps - refusing to propose")
            skipped += 1
            continue

        # 2. VISION only veto-checks the computed candidate (binary
        # judgment - within a 4B model's actual competence, unlike
        # coordinate generation).
        facts = {
            "fix_kind": fix_kind,
            "bubble_own_text": bubble.get("translated_text"),
            "current_box": [int(v) for v in cur_box],
            "proposed_new_box": new_box,
        }
        prompt = VERIFY_PROMPT.format(
            facts=json.dumps(facts, ensure_ascii=False, indent=1),
            width=width, height=height)
        log(f"geometry fix ready for {bubble_id} ({fix_kind}: {cur_box} -> {new_box}); vision veto-check...")
        vetoed = False
        veto_reason = ""
        try:
            raw = run_vision(args.model, args.mmproj, image_path, prompt)
            verdict = parse_proposal(raw)
            if isinstance(verdict, dict) and verdict.get("approve") is False:
                vetoed = True
                veto_reason = str(verdict.get("reason", ""))
                log(f"vision VETO for {bubble_id}: {veto_reason!r}")
        except subprocess.TimeoutExpired:
            log(f"{bubble_id}: vision check timed out - submitting geometry fix anyway "
                f"(human gate is the final QA)")
        if vetoed:
            if note:
                # Nonsense case: the FINDING must reach the human even
                # when no safe geometry exists (first live run: both
                # p173 reformats vetoed for covering the character's
                # face - correct veto, but the flag itself vanished).
                new_box = [int(v) for v in cur_box]
                fix_kind = "nonsense-flag-only"
                note += (" Горизонтальне переформатування відхилено vision-перевіркою"
                         + (f" ({veto_reason})" if veto_reason else "")
                         + " - розташуйте рамку вручну.")
                log(f"{bubble_id}: falling back to flag-only proposal with the note")
            else:
                log(f"skip {bubble_id}: vetoed, no note to surface")
                skipped += 1
                continue

        body = {"bubble_id": bubble_id, "source": "gemma_agent",
                "bbox": new_box, "ref_size": [width, height]}
        if note:
            body["note"] = note
        endpoint = f"/api/edit/manga-bbox/{args.book}/{page}"
        status, resp = api_call(args.api, auth, "PUT", endpoint, body)
        if status == 200:
            proposed += 1
            existing.add(target_id)
            log(f"PROPOSED {fix_kind} for {bubble_id}: {cur_box} -> {new_box}")
        else:
            skipped += 1
            log(f"skip {bubble_id}: API {status}: {resp.get('message')}")

    log(f"done: {proposed} proposal(s) submitted as pending (source=gemma_agent), {skipped} skipped.")
    log("Nothing was applied - review in Pending Edits (Approve/Discard).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
