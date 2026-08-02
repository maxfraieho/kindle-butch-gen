"""
kbg_web/book_pipeline.py — TASK-90: Flask Blueprint for the docs2book pipeline.

Routes under /api/book-pipeline/*. Shared internals that live in kbg_web.app
(active_processes, _find_book_process_pids, _heavy_state, _busy_409,
_write_active_conversion_state, _clear_active_conversion_state,
validate_slug) are imported lazily inside each route function -- the same
pattern kbg_web/protocol_orchestrator.py already uses (`from kbg_web.app
import is_book_process_running` inside get_protocol_status) to avoid a
circular import at module load time, since kbg_web.app imports THIS module
to register the blueprint.
"""
import os
import re
import sys
import json
import subprocess
from flask import Blueprint, jsonify, request

repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from common.book_paths import resolve_book_paths
from kbg_web import edit_store

book_pipeline_bp = Blueprint("book_pipeline", __name__)


def _slugify(text):
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or "book"


def _unique_slug(base):
    slug = base
    n = 2
    while os.path.isdir(os.path.join(repo_dir, "books", slug)):
        slug = f"{base}-{n}"
        n += 1
    return slug


@book_pipeline_bp.route("/api/book-pipeline/create", methods=["POST"])
def book_pipeline_create():
    from kbg_web.app import validate_slug
    data = request.get_json(silent=True) or {}
    repo_url = (data.get("repo_url") or "").strip()
    if not repo_url:
        return jsonify({"status": "error", "message": "repo_url is required"}), 400

    title = (data.get("title") or "").strip()
    default_base = title or re.sub(r"\.git$", "", repo_url.rstrip("/").split("/")[-1])
    slug = _unique_slug(_slugify(default_base))
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Could not derive a valid slug from repo_url/title"}), 400

    book_dir = os.path.join(repo_dir, "books", slug)
    os.makedirs(book_dir, exist_ok=True)
    config = {
        "pipeline_kind": "docsbook",
        "repo_url": repo_url,
        "docs_subdir": data.get("docs_subdir", "docs"),
        # No automated notebook-creation step exists yet (Stage 1's
        # notebooklm_client.py has no notebooks_create) -- the caller must
        # supply an existing NotebookLM notebook_id. docs_ingest fails
        # loudly and early if this is missing, not silently.
        "notebook_id": data.get("notebook_id"),
        "title": title or default_base,
        "authors": data.get("author", "Unknown"),
        "source_lang": data.get("source_lang", "en"),
        "target_lang": data.get("target_lang", "uk"),
        "enable_book_editor": bool(data.get("enable_book_editor", False)),
    }
    config_path = os.path.join(book_dir, "config.json")
    with open(config_path, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

    return jsonify({"status": "success", "slug": slug})


@book_pipeline_bp.route("/api/book-pipeline/run/<slug>", methods=["POST"])
def book_pipeline_run(slug):
    from kbg_web.app import (
        validate_slug, active_processes, _heavy_state, _busy_409,
        _write_active_conversion_state,
    )
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400

    paths = resolve_book_paths(repo_dir, slug)
    if not os.path.exists(paths["book_dir"]):
        return jsonify({"status": "error", "message": "Book not found"}), 404

    if slug in active_processes and active_processes[slug].poll() is None:
        return jsonify({"status": "error", "message": "Already running"}), 409

    heavy = _heavy_state()
    if heavy.get("agent"):
        return _busy_409("🤖 ШІ-агент зараз використовує пам'ять. Зачекайте, поки він завершить.")
    if heavy.get("ner"):
        return _busy_409("🔎 Йде сканування персонажів — та сама модель. Зачекайте кілька хвилин.")

    data = request.get_json(silent=True) or {}
    cmd = [sys.executable, os.path.join(repo_dir, "bin", "run_book_pipeline.py"),
           "--book", slug]
    if data.get("clean"):
        cmd.append("--clean")

    log_path = paths["log_path"]
    log_file = open(log_path, "a", encoding="utf-8")
    try:
        proc = subprocess.Popen(
            cmd, stdout=log_file, stderr=subprocess.STDOUT,
            cwd=repo_dir, start_new_session=True,
        )
    finally:
        # The child holds its own dup of this fd via stdout redirection;
        # closing it in the parent doesn't affect the child, and skipping
        # this leaked one fd per pipeline start in this long-lived process.
        log_file.close()
    active_processes[slug] = proc
    _write_active_conversion_state(slug, cmd, repo_dir, log_path)
    return jsonify({"status": "success", "message": "Book pipeline started"})


@book_pipeline_bp.route("/api/book-pipeline/status/<slug>")
def book_pipeline_status(slug):
    from kbg_web.app import validate_slug, active_processes
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400

    paths = resolve_book_paths(repo_dir, slug)
    if not os.path.exists(paths["book_dir"]):
        return jsonify({"status": "error", "message": "Book not found"}), 404

    running = slug in active_processes and active_processes[slug].poll() is None

    log_lines = []
    if os.path.exists(paths["log_path"]):
        try:
            with open(paths["log_path"], "r", encoding="utf-8", errors="replace") as f:
                log_lines = f.readlines()[-30:]
        except Exception:
            pass

    # Own lightweight progress file, written by bin/run_book_pipeline.py --
    # NOT protocol_orchestrator.py's BOOK_PIPELINE_STAGES (that part of the
    # original TASK-90 Stage 3 design, item 3.4, was deliberately deferred:
    # it needs the get_protocol_status()-based unified StagesView, which is
    # a Stage 5 (frontend) concern. This endpoint is self-contained until
    # that integration happens.
    stage = None
    segments_degraded = None
    progress_path = os.path.join(paths["book_dir"], "book_pipeline_progress.json")
    if os.path.exists(progress_path):
        try:
            with open(progress_path, "r", encoding="utf-8") as f:
                progress_data = json.load(f)
                stage = progress_data.get("stage")
                segments_degraded = progress_data.get("segments_degraded")
        except Exception:
            pass

    flags_path = os.path.join(paths["book_dir"], "book_editor_flags.json")
    flags_pending = 0
    if os.path.exists(flags_path):
        try:
            with open(flags_path, "r", encoding="utf-8") as f:
                flags = json.load(f)
            # Only edits that actually reached a terminal state count as
            # resolved -- a freshly-Applied flag creates a "pending" edit
            # (it still needs approval through the generic edit-approval
            # gate), so counting it here would zero the pending badge
            # before anything was actually approved.
            resolved_ids = {
                e["target_id"] for e in edit_store.list_edits(slug, mode="book")
                if e.get("status") in ("approved", "discarded")
            }
            flags_pending = sum(1 for fl in flags if fl.get("flag_id") not in resolved_ids)
        except Exception:
            pass

    return jsonify({
        "running": running,
        "stage": stage,
        "log": log_lines,
        "flags_pending": flags_pending,
        "segments_degraded": segments_degraded,
    })


@book_pipeline_bp.route("/api/book-pipeline/stop/<slug>", methods=["POST"])
def book_pipeline_stop(slug):
    import signal
    from kbg_web.app import (
        validate_slug, active_processes, _find_book_process_pids,
        _clear_active_conversion_state, _reconcile_active_model,
    )
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400

    pids = _find_book_process_pids(slug)
    if slug not in active_processes and not pids:
        return jsonify({"status": "error", "message": "No active process for this book"}), 400

    # Kill the whole process GROUP, not just the matched pid (TASK-90 A.9
    # fix -- same pattern as the earlier audio_stage.py/tts_helper.py
    # orphan incident: run_book_pipeline.py's own subprocess.run() calls
    # (git clone, docs2book build_book.py, translate_stage.py) are children
    # that don't themselves match _find_book_process_pids' cmdline pattern,
    # so killing only the matched pid left them running. Every launcher of
    # these scripts uses start_new_session=True, which makes the launched
    # pid its own process group leader (pgid == pid), so os.killpg(pid, ...)
    # reaches the whole tree in one signal. Falls back to os.kill on the
    # single pid if killpg fails for any reason (e.g. pid is not a group
    # leader), rather than silently doing nothing.
    for p in pids:
        try:
            os.killpg(p, signal.SIGKILL)
        except ProcessLookupError:
            pass
        except Exception:
            try:
                os.kill(p, signal.SIGKILL)
            except Exception:
                pass
    if slug in active_processes:
        try:
            os.killpg(active_processes[slug].pid, signal.SIGKILL)
        except Exception:
            try:
                active_processes[slug].kill()
            except Exception:
                pass
        del active_processes[slug]

    _clear_active_conversion_state(slug)

    # Q-15: SIGKILL above can catch run_book_pipeline.py mid-editor-swap,
    # leaving global_settings.json's active_model stuck on the editor
    # model. Only safe to reconcile once nothing else is running -- the
    # llama-server slot and its settings are shared across all books.
    if not active_processes:
        _reconcile_active_model()

    return jsonify({"status": "success", "message": f"Book pipeline for '{slug}' stopped"})


@book_pipeline_bp.route("/api/book-pipeline/editor-flags/<slug>")
def book_pipeline_editor_flags(slug):
    from kbg_web.app import validate_slug
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
    paths = resolve_book_paths(repo_dir, slug)
    flags_path = os.path.join(paths["book_dir"], "book_editor_flags.json")
    if not os.path.exists(flags_path):
        return jsonify([])
    try:
        with open(flags_path, "r", encoding="utf-8") as f:
            return jsonify(json.load(f))
    except Exception:
        return jsonify([])


def _get_flag(slug, flag_id):
    paths = resolve_book_paths(repo_dir, slug)
    flags_path = os.path.join(paths["book_dir"], "book_editor_flags.json")
    if not os.path.exists(flags_path):
        return None
    try:
        with open(flags_path, "r", encoding="utf-8") as f:
            flags = json.load(f)
    except Exception:
        return None
    return next((fl for fl in flags if fl.get("flag_id") == flag_id), None)


@book_pipeline_bp.route("/api/book-pipeline/editor-flags/<slug>/<flag_id>/apply", methods=["POST"])
def book_pipeline_editor_flag_apply(slug, flag_id):
    from kbg_web.app import validate_slug
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
    flag = _get_flag(slug, flag_id)
    if not flag:
        return jsonify({"status": "error", "message": "Flag not found"}), 404

    # Never mutates the humanized markdown or book_editor_flags.json --
    # lands as a pending edit through the exact same human-approval gate
    # every other edit source (human, gemma_agent) already goes through.
    edited_value = flag.get("suggested_rewrite") or flag.get("humanized_excerpt", "")
    edit_store.add_edit(
        slug, mode="book", target_id=flag_id, field=flag.get("category"),
        original_value=flag.get("humanized_excerpt", ""),
        edited_value=edited_value,
        source="book_editor", note=flag.get("issue"),
    )
    return jsonify({"status": "success"})


@book_pipeline_bp.route("/api/book-pipeline/editor-flags/<slug>/<flag_id>/discard", methods=["POST"])
def book_pipeline_editor_flag_discard(slug, flag_id):
    from kbg_web.app import validate_slug
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
    flag = _get_flag(slug, flag_id)
    if not flag:
        return jsonify({"status": "error", "message": "Flag not found"}), 404
    # Recorded as a discarded edit-store entry (append-only, mirrors
    # mqm_review.py's decision-log pattern) rather than mutating
    # book_editor_flags.json -- the raw flag stays visible, only its
    # resolution status changes.
    edit = edit_store.add_edit(
        slug, mode="book", target_id=flag_id, field=flag.get("category"),
        original_value=flag.get("humanized_excerpt", ""),
        edited_value=flag.get("humanized_excerpt", ""),
        source="book_editor", note=flag.get("issue"),
    )
    edit_store.mark_status(slug, edit["id"], "discarded")
    return jsonify({"status": "success"})
