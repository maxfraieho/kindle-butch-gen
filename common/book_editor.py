#!/usr/bin/env python3
"""
common/book_editor.py — TASK-90: Deterministic QA checks for book editor.

Stateless, atomic JSON write, clear errors, no silent None.
Implements check_artifacts, check_structure, and run_deterministic_checks.
"""

from __future__ import annotations

import json
import os
import re
import secrets
from typing import List, Dict, Optional


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
        flag = {
            "flag_id": f"bef_{secrets.token_hex(6)}",
            "chapter": chapter,
            "para_index": para_index,
            "category": "artifact_loss",
            "severity": severity,
            "source_excerpt": source,
            "humanized_excerpt": humanized,
            "issue": f"Source artifact(s) missing in humanized text: {', '.join(missing)}.",
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
            "flag_id": f"bef_{secrets.token_hex(6)}",
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

    existing.extend(flags)
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
