#!/usr/bin/env python3
"""
common/agent_rules.py — v0 rules interpreter (extracted from bin/agent_editor.py for TASK-94).
"""

from __future__ import annotations

import os
import re


def _eval_cond(cond: str, facts: dict) -> bool:
    m = re.match(r"^(\w+)\s*(==|!=|<=|>=|<|>)\s*(.+)$", cond)
    if not m or m.group(1) not in facts:
        return False
    left, op, raw = facts[m.group(1)], m.group(2), m.group(3).strip()
    if raw in ("true", "false"):
        right = raw == "true"
    else:
        try:
            right = float(raw)
        except ValueError:
            right = raw
    try:
        if isinstance(right, float):
            left = float(left)
        return {"==": left == right, "!=": left != right, "<": left < right,
                "<=": left <= right, ">": left > right, ">=": left >= right}[op]
    except (TypeError, ValueError):
        return False


def _log(msg: str) -> None:
    print(f"[agent_rules] {msg}", flush=True)


def load_rules(book_dir: str, repo: str):
    """v0 rules interpreter (TASK-66): reads agent_rules.yaml written by
    the studio's drakon2rules converter (strict subset - parsed with a
    tiny indent parser, no yaml dependency on the Termux host). Honored
    verbs: skip, require_note, advise lines (vision prompt), and the
    directional set - prefer_move / forbid_move / max_shift_px - which
    steer resolve_overlap's candidate ordering directly."""
    path = os.path.join(book_dir, "agent_rules.yaml")
    if not os.path.exists(path):
        path = os.path.join(repo, "agent_rules.yaml")
    if not os.path.exists(path):
        return [], []
    rules, advise, cur, section = [], [], None, None
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        s = line.strip()
        if s.startswith("#") or not s:
            continue
        if s == "rules:":
            section = "rules"
        elif s == "advise:":
            section = "advise"
        elif section == "advise" and s.startswith("- "):
            advise.append(s[2:].strip().strip('"'))
        elif section == "rules":
            if s.startswith("- id:"):
                cur = {"id": s.split(":", 1)[1].strip(), "when": [], "then": []}
                rules.append(cur)
            elif cur is not None and s.startswith("- ") and ":" not in s:
                cur["when"].append(s[2:].strip())
            elif cur is not None and s.startswith("- "):
                body = s[2:]
                if any(body.startswith(op) for op in ()) or " == " in body or " != " in body \
                        or " < " in body or " > " in body or " <= " in body or " >= " in body:
                    cur["when"].append(body.strip())
                else:
                    verb, _, arg = body.partition(":")
                    cur["then"].append((verb.strip(), arg.strip().strip('"')))
    return rules, advise


def apply_rules(rules: list, facts: dict):
    """Returns (skip_reason|None, extra_notes, matched_ids, constraints).
    First-in-file precedence; skip is strongest and stops evaluation.
    constraints: prefer/forbid move directions, max_shift_px - consumed
    by resolve_overlap so Q's diagrams literally steer the geometry."""
    notes, matched = [], []
    cons = {"prefer": [], "forbid": [], "max_shift": None}
    for r in rules:
        if not all(_eval_cond(c, facts) for c in r["when"]):
            continue
        matched.append(r["id"])
        for verb, arg in r["then"]:
            if verb == "skip":
                return arg or r["id"], notes, matched, cons
            if verb == "require_note":
                notes.append(arg)
            elif verb == "veto_note":
                pass  # advise lines cover the vision prompt globally
            elif verb == "prefer_move" and arg in ("left", "right", "up", "down"):
                if arg not in cons["prefer"]:
                    cons["prefer"].append(arg)
            elif verb == "forbid_move" and arg in ("left", "right", "up", "down"):
                if arg not in cons["forbid"]:
                    cons["forbid"].append(arg)
            elif verb == "max_shift_px":
                try:
                    v = int(arg)
                    # first-in-file wins: keep the earliest (strictest-by-order)
                    if cons["max_shift"] is None:
                        cons["max_shift"] = v
                except ValueError:
                    _log(f"[rules] {r['id']}: bad max_shift_px value {arg!r}")
            else:
                _log(f"[rules] {r['id']}: verb {verb!r} not honored (font verbs apply once font proposals exist)")
    return None, notes, matched, cons
