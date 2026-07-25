"""Web perемикач трьох ексклюзивних GPU-режимів на телефоні:
Vydra (переклад, порт 8081), кодинг-модель (Bonsai-27B, порт 8082) і
Швейцарські опитування (survey_agent.py, mode 3).

Registered on the same Flask `app` as everything else in app.py, so the
existing global auth gate (@app.before_request::require_login) already
protects every route here — no separate auth wiring needed. Also means
this page is reachable the moment kbg_web/app.py is up, which already
autostarts with Vydra via bin/start-all-services.sh — no new autostart
plumbing required.

Deliberately calls the SAME scripts app.py's own /api/models/start and
~/llm-switch.sh already use, rather than re-implementing model lifecycle
here — this module is just a thin "one button = one llm-switch.sh call"
front end.
"""
from __future__ import annotations

import os
import socket
import subprocess
import time

from flask import Blueprint, jsonify, render_template, request

mode_bp = Blueprint("mode_switcher", __name__)

LLM_SWITCH = os.path.expanduser("~/llm-switch.sh")
START_TRANSLATION = os.path.expanduser("~/start-translation-server.sh")
BONSAI_PORT = 8082
TRANSLATION_PORT = 8081

MODE_SWITCH_LOCK_FILE = os.path.expanduser("~/mode-switch.lock")
MODE_SWITCH_LOCK_STALE_SECONDS = 30


def _port_open(port: int, timeout: float = 0.4) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=timeout):
            return True
    except OSError:
        return False


def _pgrep(pattern: str) -> bool:
    return subprocess.run(["pgrep", "-f", pattern], capture_output=True).returncode == 0


def current_mode() -> str:
    # Checked in this order deliberately: survey_agent.py doesn't hold a
    # fixed port the way the two llama-server modes do, so it has to be
    # checked by process name first, before either port check could give
    # a false "idle" reading while a survey run is between CDP calls.
    if _pgrep("survey_agent.py"):
        return "survey"
    if _port_open(BONSAI_PORT):
        return "coding"
    if _port_open(TRANSLATION_PORT):
        return "vydra"
    return "idle"


@mode_bp.route("/modes")
def modes_page():
    return render_template("mode_switcher.html")


@mode_bp.route("/api/mode")
def api_mode():
    return jsonify({"mode": current_mode()})


@mode_bp.route("/api/mode/switch", methods=["POST"])
def api_mode_switch():
    data = request.get_json(silent=True) or {}
    target = data.get("target")
    if target not in ("vydra", "coding", "survey", "idle"):
        return jsonify({"status": "error", "message": "Invalid target"}), 400

    profile = data.get("profile")
    url = data.get("url")
    if target == "survey" and (not profile or not url):
        return jsonify({"status": "error", "message": "survey потребує profile і url"}), 400

    # Same PID/start-lock-file pattern app.py's /api/models/start already
    # uses, to stop two concurrent switch clicks from racing each other.
    if os.path.exists(MODE_SWITCH_LOCK_FILE):
        try:
            age = time.time() - os.path.getmtime(MODE_SWITCH_LOCK_FILE)
        except OSError:
            age = MODE_SWITCH_LOCK_STALE_SECONDS + 1
        if age > MODE_SWITCH_LOCK_STALE_SECONDS:
            try:
                os.remove(MODE_SWITCH_LOCK_FILE)
            except OSError:
                pass
    try:
        lock_fd = os.open(MODE_SWITCH_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.close(lock_fd)
    except FileExistsError:
        return jsonify({"status": "error", "message": "Перемикання вже виконується"}), 409

    try:
        # A human clicking a button in this UI IS the confirmation
        # check_conflict_and_prompt asks for — always force-stop whatever
        # is currently active before starting the target.
        subprocess.run(["bash", LLM_SWITCH, "stop"], capture_output=True, timeout=15)

        if target == "idle":
            return jsonify({"status": "success", "message": "Усі режими зупинено"})

        if target == "vydra":
            subprocess.Popen(["bash", START_TRANSLATION],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        elif target == "coding":
            subprocess.Popen(["bash", LLM_SWITCH, "bonsai", "-f"],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        elif target == "survey":
            cmd = ["bash", LLM_SWITCH, "survey", profile, url, "-f"]
            if data.get("dry_run", True):
                cmd.append("--dry-run")
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)

        return jsonify({"status": "success", "message": f"Перемикання на '{target}' запущено"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            os.remove(MODE_SWITCH_LOCK_FILE)
        except OSError:
            pass
