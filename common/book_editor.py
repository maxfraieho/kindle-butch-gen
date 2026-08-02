#!/usr/bin/env python3
"""
common/book_editor.py — TASK-90: Deterministic QA checks for book editor.

Stateless, atomic JSON write, clear errors, no silent None.
Implements check_artifacts, check_structure, and run_deterministic_checks.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from typing import List, Dict, Optional

import requests

AGENT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "agents", "book_editor")


def _make_flag_id(chapter: str, para_index: int, category: str, issue: str) -> str:
    """Deterministic flag_id (TASK-90 Stage 9 A.7 fix). The old
    secrets.token_hex(6) regenerated a fresh ID on every pipeline re-run,
    so a resolved/discarded flag's ID never matched the newly-detected
    same finding and stage_editor_review's human-gate check
    (unresolved == flag_id not in resolved_ids) could never be satisfied --
    an infinite re-detection deadlock. Hashing the finding's own identity
    (chapter+para_index+category+issue) makes the SAME finding produce the
    SAME id across runs, so a resolved finding stays resolved; a genuinely
    different finding (different issue text) still gets its own id."""
    key = f"{chapter}|{para_index}|{category}|{issue}"
    return "bef_" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]


COMMON_FALSE_POSITIVES = {
    "e.g.", "i.e.", "etc.", "vs.", "mr.", "mrs.", "dr.", "st.", "no.",
    "vol.", "pp.", "p.", "fig.", "eq.", "al."
}


def _extract_artifacts(text: str) -> List[str]:
    """Extract code spans, fenced code blocks, URLs, CLI flags, versions, and file paths."""
    artifacts: List[str] = []

    # 1. Fenced code blocks
    fenced_blocks = re.findall(r"```[\s\S]*?```", text)
    artifacts.extend(fenced_blocks)

    text_no_fenced = re.sub(r"```[\s\S]*?```", "", text)

    # 2. Inline code spans
    inline_spans = re.findall(r"`[^`\n]+`", text_no_fenced)
    artifacts.extend(inline_spans)

    text_clean = re.sub(r"`[^`\n]+`", "", text_no_fenced)

    # 3. URLs
    urls = re.findall(r"https?://\S+", text_clean)
    artifacts.extend(urls)

    # 4. CLI flags
    flags = re.findall(r"--[\w-]+", text_clean)
    artifacts.extend(flags)

    # 5. Version strings
    versions = re.findall(r"\bv?\d+\.\d+(?:\.\d+)?\b", text_clean)
    artifacts.extend(versions)

    # 6. File paths (careful with false positives)
    raw_paths = re.findall(r"[\w./-]+\.\w{1,5}\b", text_clean)
    for p in raw_paths:
        p_lower = p.lower()
        if p_lower in COMMON_FALSE_POSITIVES:
            continue
        if re.match(r"^\d+(?:\.\d+)+$", p):
            continue
        if any(p in u for u in urls):
            continue
        artifacts.append(p)

    # Deduplicate while preserving order
    seen = set()
    unique_artifacts = []
    for art in artifacts:
        if art not in seen:
            seen.add(art)
            unique_artifacts.append(art)

    return unique_artifacts


def check_artifacts(source: str, humanized: str, chapter: str, para_index: int) -> List[Dict]:
    """Check if any technical artifacts present in source are missing in humanized paragraph."""
    source_artifacts = _extract_artifacts(source)
    missing = [art for art in source_artifacts if art not in humanized]

    if missing:
        severity = min(5, max(1, len(missing)))
        issue = f"Source artifact(s) missing in humanized text: {', '.join(missing)}."
        flag = {
            "flag_id": _make_flag_id(chapter, para_index, "artifact_loss", issue),
            "chapter": chapter,
            "para_index": para_index,
            "category": "artifact_loss",
            "severity": severity,
            "source_excerpt": source,
            "humanized_excerpt": humanized,
            "issue": issue,
            "suggested_rewrite": None,
            "detector": "deterministic",
            "editor_model": None,
        }
        return [flag]
    return []


def check_structure(source: str, humanized: str, chapter: str, para_index: int) -> List[Dict]:
    """Check for heading count mismatches or length ratio drift."""
    src_headings = len(re.findall(r"^#{1,6}\s", source, re.MULTILINE))
    hum_headings = len(re.findall(r"^#{1,6}\s", humanized, re.MULTILINE))

    src_len = len(source)
    hum_len = len(humanized)
    ratio = (hum_len / src_len) if src_len > 0 else 1.0

    heading_diff = (src_headings != hum_headings)
    ratio_out_of_bounds = (ratio < 0.6 or ratio > 1.8)

    if heading_diff or ratio_out_of_bounds:
        if heading_diff:
            severity = 4
            issue = f"Heading count changed from {src_headings} in source to {hum_headings} in humanized text."
            if ratio_out_of_bounds:
                issue += f" Length ratio {ratio:.2f} is also outside [0.6, 1.8]."
        else:
            severity = 3
            issue = f"Length ratio {ratio:.2f} (humanized/source) is outside [0.6, 1.8] range."

        flag = {
            "flag_id": _make_flag_id(chapter, para_index, "structural_drift", issue),
            "chapter": chapter,
            "para_index": para_index,
            "category": "structural_drift",
            "severity": severity,
            "source_excerpt": source,
            "humanized_excerpt": humanized,
            "issue": issue,
            "suggested_rewrite": None,
            "detector": "deterministic",
            "editor_model": None,
        }
        return [flag]
    return []


def _append_flags(flags: List[Dict], flags_path: str) -> None:
    """Atomic write (tmp file + os.replace), APPEND to existing flags."""
    if not flags or not flags_path:
        return
    parent_dir = os.path.dirname(flags_path)
    if parent_dir:
        os.makedirs(parent_dir, exist_ok=True)
    existing = []
    if os.path.exists(flags_path):
        try:
            with open(flags_path, "r", encoding="utf-8") as f:
                content = json.load(f)
                if isinstance(content, list):
                    existing = content
        except (json.JSONDecodeError, ValueError):
            existing = []

    # Dedupe by flag_id (TASK-90 Stage 9 A.7 follow-on): _make_flag_id is
    # now deterministic, so re-running the pipeline before a flag is
    # resolved would otherwise re-append the identical finding every time
    # -- same id, same content, but a growing pile of duplicate entries in
    # book_editor_flags.json that would confuse a human reviewer counting
    # "N issues" in the UI.
    existing_ids = {fl.get("flag_id") for fl in existing}
    existing.extend(fl for fl in flags if fl.get("flag_id") not in existing_ids)
    tmp_path = flags_path + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(existing, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, flags_path)


def run_deterministic_checks(
    source: str,
    humanized: str,
    chapter: str,
    para_index: int,
    flags_path: Optional[str] = None,
) -> List[Dict]:
    """Run both check_artifacts and check_structure, atomically write flags if path given."""
    new_flags: List[Dict] = []
    new_flags.extend(check_artifacts(source, humanized, chapter, para_index))
    new_flags.extend(check_structure(source, humanized, chapter, para_index))

    if new_flags and flags_path:
        _append_flags(new_flags, flags_path)

    return new_flags


def split_paragraphs(text: str) -> List[str]:
    """Split markdown text into paragraphs on blank lines. Fence-aware:
    a ``` fenced code block is never split internally even if it contains
    blank lines, since a code block is one semantic unit for artifact-loss
    checking (TASK-90 Stage 9 A.1 fix)."""
    lines = text.split("\n")
    paragraphs: List[str] = []
    current: List[str] = []
    in_fence = False
    for line in lines:
        if re.match(r"^\s*```", line):
            in_fence = not in_fence
            current.append(line)
            continue
        if not in_fence and line.strip() == "":
            if current:
                paragraphs.append("\n".join(current).strip())
                current = []
            continue
        current.append(line)
    if current:
        paragraphs.append("\n".join(current).strip())
    return [p for p in paragraphs if p]


def run_deterministic_checks_for_chapter(
    source: str,
    humanized: str,
    chapter: str,
    flags_path: Optional[str] = None,
) -> List[Dict]:
    """Chapter-level entry point for the deterministic pre-filter (TASK-90
    Stage 9 A.1/A.2 fix -- the two were one problem: whole-chapter text
    was both the wrong granularity to flag against a human reviewer AND,
    unfixed, would have been what Part 2 hands the editor model, risking
    context_size truncation on anything but the shortest chapters).

    check_structure runs once at whole-chapter scope (heading count /
    length ratio are chapter-scoped concerns; para_index=-1 marks this as
    distinct from a real paragraph index). source and humanized are then
    split into paragraphs (see split_paragraphs) and check_artifacts runs
    per paired paragraph (para_index 0..N-1) -- these paragraph-sized
    source_excerpt/humanized_excerpt values are what Part 2 will read
    directly from book_editor_flags.json rather than re-slicing chapters.

    A source/humanized paragraph-count mismatch means index-pairing past
    the shorter length is unreliable (humanization can merge/split
    paragraphs) -- this itself is surfaced as one structural_drift flag,
    and only the first min(len, len) paragraphs are paired and checked.

    SENTINEL WARNING for future readers (Stage 5 frontend, Part 2, or any
    other consumer of book_editor_flags.json): para_index=-1 is an
    intentional "this flag is chapter-scoped, not paragraph-scoped" marker,
    not an error and not a real index. Verified 2026-08-01: nothing in this
    repo currently reads flag['para_index'] back as a list index (grep for
    "para_index" outside this file and tests/test_book_editor.py returns
    nothing), so there is no existing paragraphs[-1]-style misuse today --
    but any future code that DOES index into a paragraph list with this
    value must special-case -1 first, the same way it must already handle
    "flag has no paragraph, it's about the whole chapter" in its UI/logic."""
    new_flags: List[Dict] = []
    new_flags.extend(check_structure(source, humanized, chapter, para_index=-1))

    source_paras = split_paragraphs(source)
    humanized_paras = split_paragraphs(humanized)
    paired = min(len(source_paras), len(humanized_paras))

    if len(source_paras) != len(humanized_paras):
        issue = (
            f"Paragraph count changed from {len(source_paras)} in source to "
            f"{len(humanized_paras)} in humanized text -- pairing is unreliable "
            f"past this point; only the first {paired} paragraph(s) were "
            f"checked for artifact loss."
        )
        new_flags.append({
            "flag_id": _make_flag_id(chapter, -1, "structural_drift", issue),
            "chapter": chapter,
            "para_index": -1,
            "category": "structural_drift",
            "severity": 3,
            "source_excerpt": source,
            "humanized_excerpt": humanized,
            "issue": issue,
            "suggested_rewrite": None,
            "detector": "deterministic",
            "editor_model": None,
        })

    for i in range(paired):
        new_flags.extend(check_artifacts(source_paras[i], humanized_paras[i], chapter, para_index=i))

    if new_flags and flags_path:
        _append_flags(new_flags, flags_path)

    return new_flags


# ---------------------------------------------------------------------------
# TASK-90 Stage 9 — model-calling half. Only invoked by the caller
# (bin/run_book_pipeline.py's stage_editor_review) on paragraphs the
# deterministic checks above already flagged -- gating decision made
# 2026-08-01, see TASK-90_plan.md: cheaper, matches the original pre-filter
# design; revisit only if real data later shows the regex pre-filter is
# systematically missing drift the model would catch.
# ---------------------------------------------------------------------------


class EditorModelError(Exception):
    """Raised on any failure to get a usable verdict from the editor model
    (connection/timeout, non-200, malformed response). Callers must NOT
    swallow this silently -- a paragraph the model failed to check is not
    the same as a paragraph the model checked and found clean; see
    bin/run_book_pipeline.py's stage_editor_review for how this is
    surfaced to the human reviewer."""


def load_agent_config() -> Dict:
    """Public (TASK-90 Stage 9 Part 2): bin/run_book_pipeline.py's
    stage_editor_review calls this directly to get the dict it passes into
    run_model_checks -- not an internal-only helper anymore."""
    with open(os.path.join(AGENT_DIR, "agent.json"), "r", encoding="utf-8") as f:
        return json.load(f)


def _load_prompt_template(name: str) -> tuple[str, str]:
    """Load agents/book_editor/prompts/{name}.md and split on the '## User'
    heading into (system_message, user_template). Verified 2026-08-01
    bake-off: Qwen2.5-3B-Instruct is chat-template-tuned and needs real
    system/user roles via /v1/chat/completions, not a single blob of text
    through raw /completion -- see agent.json's _endpoint_note."""
    path = os.path.join(AGENT_DIR, "prompts", f"{name}.md")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    system_part, user_part = text.split("## User")
    return system_part.replace("## System", "").strip(), user_part.strip()


def _call_editor_model(
    source: str,
    humanized: str,
    detector_type: str,
    agent_config: Dict,
    base_url: str = "http://127.0.0.1:8081",
) -> Dict:
    """POST to /v1/chat/completions with the validated response_format
    (grammar-constrained decoding). Verified 2026-08-01 bake-off (N=28
    trials): no prefill, no truncation parser -- content is parsed as
    complete JSON directly, per agent.json's _prefill_note.

    Raises EditorModelError on any failure. Never returns a default/empty
    verdict on error -- a failed check must be visibly distinct from a
    clean one to whoever reviews book_editor_flags.json."""
    system_msg, user_template = _load_prompt_template(detector_type)
    user_msg = user_template.format(source=source, humanized=humanized)

    payload = {
        "model": "editor",
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        "temperature": agent_config["temperature"],
        "max_tokens": agent_config["max_tokens"],
        "response_format": agent_config["response_format"],
    }
    try:
        resp = requests.post(f"{base_url}/v1/chat/completions", json=payload, timeout=90)
    except requests.RequestException as e:
        raise EditorModelError(f"{detector_type}: request failed: {e}") from e

    if resp.status_code != 200:
        raise EditorModelError(f"{detector_type}: HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
        verdict = json.loads(content)
    except (KeyError, IndexError, json.JSONDecodeError) as e:
        raise EditorModelError(f"{detector_type}: malformed response: {e}") from e

    if "issue" not in verdict or "severity" not in verdict:
        raise EditorModelError(f"{detector_type}: response missing required keys: {verdict!r}")

    return verdict


def run_model_checks(
    source: str,
    humanized: str,
    chapter: str,
    para_index: int,
    agent_config: Dict,
    flags_path: Optional[str] = None,
) -> List[Dict]:
    """Run both fact_drift and translation_hostile checks via the editor
    model. Raises EditorModelError on the FIRST failing detector call --
    does not silently skip a failed detector, since a partial result
    (e.g. fact_drift checked but translation_hostile silently didn't) is
    exactly the kind of ambiguity that undermines the human review gate.
    Caller (stage_editor_review) is responsible for catching this per
    paragraph and recording it visibly, not treating it as \"clean\"."""
    threshold = agent_config.get("severity_threshold", 3)
    editor_model_name = os.path.basename(agent_config["model_path"])
    new_flags: List[Dict] = []

    for detector_type in ("fact_drift", "translation_hostile"):
        verdict = _call_editor_model(source, humanized, detector_type, agent_config)
        if verdict["severity"] < threshold:
            continue
        new_flags.append({
            "flag_id": _make_flag_id(chapter, para_index, detector_type, verdict["issue"]),
            "chapter": chapter,
            "para_index": para_index,
            "category": detector_type,
            "severity": verdict["severity"],
            "source_excerpt": source,
            "humanized_excerpt": humanized,
            "issue": verdict["issue"],
            "suggested_rewrite": None,
            "detector": "model",
            "editor_model": editor_model_name,
        })

    if new_flags and flags_path:
        _append_flags(new_flags, flags_path)

    return new_flags
