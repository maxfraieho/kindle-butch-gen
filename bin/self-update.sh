#!/usr/bin/env bash
# One-button self-update for kindle-butch-gen (TASK-46).
#
# Spawned DETACHED by kbg_web/app.py's /api/update endpoint (which has
# already verified via `git fetch` that updates exist and that no
# conversion is currently running). Runs independently of Flask because
# it has to kill and restart Flask itself - a process can't survive
# restarting its own parent chain, hence start_new_session on the Flask
# side and the sleep below to let the triggering HTTP response flush
# before its server goes down.
#
# Everything is logged to ~/kbg-update.log so a failed update is
# diagnosable after the fact.
set -uo pipefail

KBG_HOME="$HOME/kindle-butch-gen"
LOG="$HOME/kbg-update.log"

{
    echo ""
    echo "=== self-update started $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    cd "$KBG_HOME" || { echo "FATAL: $KBG_HOME missing"; exit 1; }

    # ff-only: an update must never merge/rebase local history. If this
    # fails (local divergence), we stop BEFORE touching the running
    # service - the old version keeps serving.
    if ! git pull --ff-only; then
        echo "FATAL: git pull --ff-only failed - service left untouched."
        exit 1
    fi
    echo "Now at: $(git log -1 --format='%h %s')"

    # Let the HTTP response that triggered us reach the client before the
    # server disappears out from under it.
    sleep 2

    echo "Restarting Flask web server..."
    pkill -f "python3 kbg_web/app.py" || true
    sleep 1

    # start-all-services.sh restarts Flask; its sshd/llama-server steps
    # are pgrep-guarded no-ops, and its auto-resume step is guarded
    # against an already-running conversion.
    bash "$KBG_HOME/bin/start-all-services.sh"

    echo "=== self-update finished $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
} >> "$LOG" 2>&1
