#!/usr/bin/env python3
"""Auto-resume-on-restart helper, run from Termux's ~/.bashrc autostart.

If a conversion was still marked "active" in .active_conversion.json when
Termux/Flask itself went down (not just the one subprocess - the whole
environment), this file is left behind (see kbg_web/app.py's
_write_active_conversion_state / _clear_active_conversion_state - the
state is only cleared on an observed completion or an explicit user
stop, so its mere presence on boot means neither of those happened).

Re-launches the exact same command that was running. No page-level state
tracking is needed here: the underlying pipeline (translate_manga.py /
run_conversion_batches.py) already has its own per-page skip-if-already-
done resumability, established and tested throughout this project - simply
re-running the identical invocation picks up correctly from wherever it
left off.

Deliberately a small Python script, not inline shell in .bashrc - the
saved cmd is a real argv list (may contain filenames with spaces/quotes/
apostrophes, the exact class of bug TASK-34 fixed elsewhere in this
project for a different reason), and Python's subprocess module handles
that correctly without needing to shell-escape a reconstructed string.
"""
import json
import os
import subprocess
import sys

STATE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    ".active_conversion.json"
)


def main():
    if not os.path.exists(STATE_PATH):
        return  # nothing was interrupted - normal boot, do nothing

    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            state = json.load(f)
    except Exception as e:
        print(f"[AutoResume] Could not read {STATE_PATH}: {e}", file=sys.stderr)
        return

    cmd = state.get("cmd")
    cwd = state.get("cwd")
    log_path = state.get("log_path")
    slug = state.get("slug", "?")
    if not cmd or not cwd:
        print(f"[AutoResume] Incomplete state in {STATE_PATH}, skipping.", file=sys.stderr)
        return

    print(f"[AutoResume] Resuming interrupted conversion for '{slug}': {' '.join(cmd)}")

    log_file = open(log_path, "a", encoding="utf-8") if log_path else subprocess.DEVNULL
    if log_path:
        log_file.write(f"\n\n--- Auto-resumed after Termux restart (interrupted run detected) ---\n")
        log_file.flush()

    # start_new_session=True: same reasoning as TASK-40's regen-timeout fix -
    # this process should survive independently of whatever shell/session
    # .bashrc itself is running under.
    subprocess.Popen(
        cmd,
        stdout=log_file,
        stderr=subprocess.STDOUT if log_path else subprocess.DEVNULL,
        cwd=cwd,
        start_new_session=True,
    )
    # Deliberately do NOT delete STATE_PATH here - if THIS resumed process
    # also gets interrupted before Flask restarts and observes it complete,
    # the state file must still be there to resume it again on the next boot.


if __name__ == "__main__":
    main()
