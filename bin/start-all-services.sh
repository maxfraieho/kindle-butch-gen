#!/usr/bin/env bash
# Shared service-startup sequence for kindle-butch-gen. Single source of
# truth called from BOTH:
#   1. ~/.bashrc (fires whenever a new Termux shell session starts - e.g.
#      manually reopening the Termux app after it was killed/crashed)
#   2. ~/.termux/boot/start-services.sh (fires on a genuine Android device
#      boot, via the separate Termux:Boot plugin app - see
#      docs/deployment/termux-boot-setup.md for the manual install step
#      this script alone cannot automate)
# Every step is idempotent (checks for an already-running instance before
# starting one) so it's always safe to re-run, from either trigger, any
# number of times.
set -uo pipefail

KBG_HOME="$HOME/kindle-butch-gen"

# 1. Autostart SSH daemon
if ! pgrep -x "sshd" >/dev/null; then
    sshd
fi

# 2. Autostart Llama Translation Server (Hy-MT2-7B on port 8081)
if ! pgrep -f "llama-server.*8081" >/dev/null; then
    echo "Autostart: Starting llama-server on port 8081..."
    nohup bash "$HOME/start-translation-server.sh" > "$HOME/llama-boot.log" 2>&1 &
fi

# 3. Autostart Flask Web Server (on port 5000)
if ! pgrep -f "python3 kbg_web/app.py" >/dev/null; then
    echo "Autostart: Starting Flask web server on port 5000..."
    termux-wake-lock 2>/dev/null || true
    (cd "$KBG_HOME" && nohup python3 kbg_web/app.py --port 5000 > "$HOME/kbg-flask.log" 2>&1 &)
fi

# 4. Auto-resume a conversion that was still running when the environment
# itself went down (not just this one process) - see kbg_web/app.py's
# _write_active_conversion_state / bin/resume_active_conversion.py for the
# full mechanism. No-ops silently if nothing was interrupted. Confirmed
# working live in production: a genuine Termux crash mid-conversion, on
# restart the interrupted book resumed automatically with no manual steps.
if [ -f "$KBG_HOME/.active_conversion.json" ]; then
    echo "Autostart: Detected an interrupted conversion, resuming..."
    nohup python3 "$KBG_HOME/bin/resume_active_conversion.py" > "$HOME/kbg-autoresume.log" 2>&1 &
fi
