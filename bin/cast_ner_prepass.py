#!/usr/bin/env python3
"""Cast Registry NER pre-pass (TASK-54): auto-draft characters from the
book's opening slice using local Gemma 3 4B via llama-cli.

Reads: manga -> original_text from bubbles_meta of the first N pages;
text book -> first chunk of merged markdown. Writes auto_drafted entries
into books/<slug>/edits/characters.json, never touching existing entries
(esp. verified ones). Gender guesses come from the TEXT only and always
require human verification before any rule is injected (QA-gate).
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from common.cast_registry import load_characters, save_characters, VALID_GENDERS
from common.heartbeat import send_heartbeat

MODEL_DEFAULT = os.path.expanduser("~/models/gemma3-4b/gemma-3-4b-it-Q4_K_M.gguf")
LLAMA_CLI = os.path.expanduser("~/llama.cpp/build/bin/llama-cli")

PROMPT = """Extract the recurring CHARACTERS from this book excerpt.
Return ONLY a JSON array, no other text. For each character:
{"name_source": ["primary name", "variants seen in text"],
 "name_target": "", "gender": "feminine|masculine|neutral",
 "confidence": 0.0-1.0, "mentions": <count>}
Rules: only actual characters (not places/objects); gender only when the
text makes it clear (pronouns/titles), otherwise "neutral"; include
ALL-CAPS variants seen in the text as separate entries in name_source.

EXCERPT:
"""


def collect_text(book_dir, pages):
    meta = sorted(glob.glob(os.path.join(book_dir, "bubbles_meta", "*.json")))
    if meta:
        chunks = []
        for p in meta[:pages]:
            try:
                for b in json.load(open(p, encoding="utf-8")):
                    t = (b.get("original_text") or "").strip()
                    if t:
                        chunks.append(t)
            except Exception:
                continue
        return "\n".join(chunks)
    for cand in glob.glob(os.path.join(book_dir, "translated", "merged*_*.md")) + \
                glob.glob(os.path.join(book_dir, "translated", "*.md")):
        try:
            return open(cand, encoding="utf-8").read()[:15000]
        except Exception:
            continue
    return ""


def run_llm(text, model):
    cmd = [LLAMA_CLI, "-m", model, "-c", "8192", "-n", "1024",
           "--temp", "1.0", "--top-k", "64", "--top-p", "0.95",
           "--min-p", "0.01", "--repeat-penalty", "1.0",
           "-no-cnv", "-p", PROMPT + text[:12000]]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=1800)
    return res.stdout


def parse_characters(raw):
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return []
    out = []
    for i, ch in enumerate(data if isinstance(data, list) else []):
        names = [n for n in (ch.get("name_source") or []) if isinstance(n, str) and n.strip()]
        if not names:
            continue
        gender = ch.get("gender") if ch.get("gender") in VALID_GENDERS else "neutral"
        out.append({
            "id": f"char_auto_{i:02d}_{re.sub(r'[^a-z0-9]', '', names[0].lower())[:12]}",
            "name_source": names,
            "name_target": ch.get("name_target") or "",
            "gender": gender,
            "grammar_rules": "",
            "speech_style": "",
            "is_pov_narrator": False,
            "status": "auto_drafted",
            "ner_confidence": ch.get("confidence"),
            "ner_mentions": ch.get("mentions"),
        })
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book-dir", required=True)
    ap.add_argument("--pages", type=int, default=50)
    ap.add_argument("--model", default=MODEL_DEFAULT)
    args = ap.parse_args()

    if not os.path.exists(args.model):
        print(f"NER model missing: {args.model} - download it first "
              f"(premium flow warns about this).", file=sys.stderr)
        sys.exit(2)
    text = collect_text(args.book_dir, args.pages)
    if not text.strip():
        print("No source text found to scan.", file=sys.stderr)
        sys.exit(1)

    slug = os.path.basename(args.book_dir.rstrip("/"))
    send_heartbeat(slug, "аналізує текст", stage="сканування персонажів")
    drafted = parse_characters(run_llm(text, args.model))
    existing = load_characters(args.book_dir)
    known = {n for ch in existing for n in (ch.get("name_source") or [])}
    added = [ch for ch in drafted
             if not any(n in known for n in ch["name_source"])]
    save_characters(args.book_dir, existing + added)

    # Clear auto-resume state on normal completion - same pattern as
    # agent_editor.py's own main().
    try:
        repo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        state_path = os.path.join(repo_dir, ".active_conversion.json")
        if os.path.exists(state_path):
            with open(state_path, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("slug") == slug:
                os.remove(state_path)
    except Exception:
        pass
    print(f"NER pre-pass: {len(drafted)} candidates, {len(added)} new "
          f"drafted (existing entries untouched).")


if __name__ == "__main__":
    main()
