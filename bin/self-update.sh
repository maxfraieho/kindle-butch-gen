#!/usr/bin/env bash
# One-button self-update for kindle-butch-gen (TASK-46).
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
KBG_HOME="${KBG_HOME:-$SCRIPT_DIR}"
LOG="$HOME/kbg-update.log"

{
    echo ""
    echo "=== self-update started $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    cd "$KBG_HOME" || { echo "FATAL: $KBG_HOME missing"; exit 1; }

    echo "Fetching latest changes from origin/master..."
    git fetch origin master || true
    if git reset --hard origin/master; then
        echo "Successfully updated repo to latest origin/master."
    else
        echo "Fallback: attempting git pull origin master..."
        git pull origin master || true
    fi
    echo "Now at: $(git log -1 --format='%h %s')"

    sleep 2

    echo "Restarting Flask web server..."
    pkill -f "python3 kbg_web/app.py" || true
    sleep 1

    bash "$KBG_HOME/bin/start-all-services.sh"

    echo "=== self-update finished $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
} >> "$LOG" 2>&1
