#!/usr/bin/env python3
"""
bin/run_book_pipeline.py — TASK-90: docs2book pipeline orchestrator.

Detached subprocess launched by kbg_web/book_pipeline.py's
POST /api/book-pipeline/run/<slug>. Same Popen/log/resume pattern as
bin/agent_editor.py and run_conversion_batches.py -- not a Flask route
itself.

Stages: docs_ingest -> humanize -> editor_review -> merge ->
book_compile_en -> translation -> book_compile_uk.

editor_review in THIS pass only runs common.book_editor's deterministic
checks (check_artifacts/check_structure). The model-calling checks
(fact_drift, translation_hostile) are Stage 9 -- not implemented here, the
editor model is not downloaded yet and this script never calls it.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time

repo_dir = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from common.book_paths import resolve_book_paths
from common.book_editor import run_deterministic_checks
from common.notebooklm_client import (
    NotebookLMClient, NotebookLMConnectionError, NotebookLMToolError,
)

DOCS2BOOK_SCRIPT = os.path.join(repo_dir, "tools", "docs2book", "build_book.py")

HUMANIZE_PROMPT_TEMPLATE = (
    'Rewrite the attached source as a chapter of a book, addressed to the '
    'reader as if the project maintainers are speaking directly, '
    'first-person plural ("we built it so that...", "we designed it this '
    'way because..."). Do NOT include any citation markers, footnote '
    'numbers, or bracketed references like [1] or [2] anywhere in the '
    'output -- write it as continuous prose a human would read in a '
    'printed book, with zero visible sourcing apparatus. Preserve every '
    'fact, field name, default value, code sample, and diagram exactly as '
    'given, character-for-character in code blocks -- do not invent or '
    'drop anything technical. Open with 1-2 sentences orienting the reader '
    'on why this chapter matters before diving into specifics. Keep total '
    'length within roughly +/-20% of the source. Output ONLY the finished '
    'chapter in Markdown -- no preamble, no meta-commentary, no citations '
    'of any kind.\n\nChapter title: {title}'
)


def log(msg):
    print(f"[run_book_pipeline] {msg}", flush=True)


def write_progress(book_dir, stage, **extra):
    """Atomic write (tmp + os.replace) -- same pattern as
    common/book_editor.py's _append_flags and common/mqm_review.py."""
    path = os.path.join(book_dir, "book_pipeline_progress.json")
    data = {"stage": stage, "updated_at": time.time(), **extra}
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    os.replace(tmp, path)


def collect_markdown_files(docs_dir):
    """Recursively list *.md/*.mdx under docs_dir, sorted for stable
    chapter ordering. Deliberately simple relative to docs2book's own
    collect_markdown_files (numeric-prefix + README-first sorting) --
    that logic runs again inside build_book.py at compile time anyway;
    this pass only needs a stable, repeatable order to humanize in."""
    files = []
    for root, _dirs, names in os.walk(docs_dir):
        for name in names:
            if name.endswith((".md", ".mdx")):
                files.append(os.path.join(root, name))
    return sorted(files)


def stage_docs_ingest(book_dir, config):
    write_progress(book_dir, "docs_ingest")
    repo_url = config.get("repo_url")
    if not repo_url:
        raise RuntimeError("config.json is missing repo_url")

    clone_dir = os.path.join(book_dir, "repo_clone")
    if not os.path.isdir(os.path.join(clone_dir, ".git")):
        if os.path.isdir(clone_dir):
            shutil.rmtree(clone_dir)
        log(f"Cloning {repo_url} ...")
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, clone_dir],
            check=True, cwd=repo_dir,
        )
    else:
        log("repo_clone/ already present, skipping clone (resume).")

    docs_subdir = config.get("docs_subdir", "docs")
    docs_dir = os.path.join(clone_dir, docs_subdir)
    if not os.path.isdir(docs_dir):
        raise RuntimeError(f"docs_subdir '{docs_subdir}' not found in cloned repo")

    md_files = collect_markdown_files(docs_dir)
    if not md_files:
        raise RuntimeError(f"no .md/.mdx files found under {docs_dir}")

    manifest_dir = os.path.join(book_dir, "source_docs")
    os.makedirs(manifest_dir, exist_ok=True)
    manifest = []
    for i, path in enumerate(md_files):
        rel = os.path.relpath(path, docs_dir)
        dest_name = f"{i:03d}_{rel.replace(os.sep, '_')}"
        shutil.copy2(path, os.path.join(manifest_dir, dest_name))
        manifest.append({"index": i, "source_rel": rel, "manifest_file": dest_name})

    with open(os.path.join(book_dir, "source_docs_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    log(f"docs_ingest: {len(manifest)} chapter file(s) copied to source_docs/")
    return manifest


def stage_humanize(book_dir, config, manifest):
    write_progress(book_dir, "humanize", chapters_total=len(manifest))
    notebook_id = config.get("notebook_id")
    if not notebook_id:
        raise RuntimeError(
            "config.json is missing notebook_id -- there is no automated "
            "notebook-creation step yet (Stage 1's notebooklm_client.py "
            "has no notebooks_create); an existing NotebookLM notebook_id "
            "must be supplied at book-create time."
        )

    humanized_dir = os.path.join(book_dir, "humanized")
    os.makedirs(humanized_dir, exist_ok=True)
    client = NotebookLMClient()

    for entry in manifest:
        out_name = f"{entry['index']:03d}_{os.path.basename(entry['source_rel'])}"
        out_path = os.path.join(humanized_dir, out_name)
        if os.path.exists(out_path):
            log(f"humanize: {out_name} already exists, skipping (resume).")
            continue

        src_path = os.path.join(book_dir, "source_docs", entry["manifest_file"])
        with open(src_path, "r", encoding="utf-8") as f:
            content = f.read()

        title = os.path.splitext(os.path.basename(entry["source_rel"]))[0]
        source_title = f"[run_book_pipeline] {entry['source_rel']}"
        try:
            source = client.sources_add_text(notebook_id, source_title, content)
            source_id = source.get("id") or source.get("source_id")
            answer = client.chat_ask(
                notebook_id,
                HUMANIZE_PROMPT_TEMPLATE.format(title=title),
                source_ids=[source_id] if source_id else None,
            )
        except (NotebookLMConnectionError, NotebookLMToolError) as e:
            raise RuntimeError(f"humanize failed on {entry['source_rel']}: {e}") from e

        with open(out_path, "w", encoding="utf-8") as f:
            f.write(answer)
        log(f"humanize: wrote {out_name} ({len(answer)} chars)")
        write_progress(book_dir, "humanize", chapters_total=len(manifest),
                        chapters_done=entry["index"] + 1)

    return humanized_dir


def stage_editor_review(book_dir, config, manifest, humanized_dir):
    write_progress(book_dir, "editor_review")
    if not config.get("enable_book_editor"):
        log("editor_review: enable_book_editor is not true for this book -- skipping (opt-in).")
        return

    flags_path = os.path.join(book_dir, "book_editor_flags.json")
    for entry in manifest:
        src_path = os.path.join(book_dir, "source_docs", entry["manifest_file"])
        out_name = f"{entry['index']:03d}_{os.path.basename(entry['source_rel'])}"
        hum_path = os.path.join(humanized_dir, out_name)
        if not os.path.exists(hum_path):
            continue
        with open(src_path, "r", encoding="utf-8") as f:
            source = f.read()
        with open(hum_path, "r", encoding="utf-8") as f:
            humanized = f.read()
        flags = run_deterministic_checks(
            source, humanized, chapter=entry["source_rel"],
            para_index=0, flags_path=flags_path,
        )
        if flags:
            log(f"editor_review: {len(flags)} flag(s) on {entry['source_rel']}")

    # Human gate: if any unresolved flags exist, pause here rather than
    # proceeding straight to merge/compile. "Unresolved" == not yet present
    # as an edit_store entry (mode="book") for that flag_id -- the same
    # check kbg_web/book_pipeline.py's status endpoint already does.
    if os.path.exists(flags_path):
        with open(flags_path, "r", encoding="utf-8") as f:
            all_flags = json.load(f)
        from kbg_web import edit_store
        resolved_ids = {e["target_id"] for e in edit_store.list_edits(config.get("_slug", ""), mode="book")}
        pending = [fl for fl in all_flags if fl.get("flag_id") not in resolved_ids]
        if pending:
            write_progress(book_dir, "editor_review", flags_pending=len(pending))
            raise SystemExit(
                f"editor_review: {len(pending)} flag(s) awaiting human review in the UI "
                f"(book_editor_flags.json) -- re-run this pipeline after resolving them."
            )


def stage_merge(book_dir, manifest, humanized_dir):
    write_progress(book_dir, "merge")
    merged_path = os.path.join(book_dir, "merged_en.md")
    chunks = []
    for entry in manifest:
        out_name = f"{entry['index']:03d}_{os.path.basename(entry['source_rel'])}"
        hum_path = os.path.join(humanized_dir, out_name)
        with open(hum_path, "r", encoding="utf-8") as f:
            chunks.append(f.read())
    with open(merged_path, "w", encoding="utf-8") as f:
        f.write("\n\n".join(chunks))
    log(f"merge: wrote {merged_path}")
    return merged_path


def stage_book_compile(book_dir, config, docs_path, out_pdf, stage_name):
    write_progress(book_dir, stage_name)
    output_dir = os.path.join(book_dir, "output")
    os.makedirs(output_dir, exist_ok=True)
    # build_book.py's --docs expects a directory of .md files, not a single
    # file -- merged_en.md/merged_translated_uk.md are single files, so
    # stage into a throwaway one-file dir per compile call.
    stage_dir = os.path.join(book_dir, f"_compile_{stage_name}")
    if os.path.isdir(stage_dir):
        shutil.rmtree(stage_dir)
    os.makedirs(stage_dir)
    shutil.copy2(docs_path, os.path.join(stage_dir, "book.md"))

    cmd = [
        sys.executable, DOCS2BOOK_SCRIPT,
        "--docs", stage_dir,
        "--out", out_pdf,
        "--title", config.get("title", "Untitled"),
        "--author", config.get("authors", "Unknown"),
        "--lang", "uk" if stage_name == "book_compile_uk" else "en",
        "--engine", "typst",
    ]
    log(f"{stage_name}: running docs2book -> {out_pdf}")
    subprocess.run(cmd, check=True, cwd=repo_dir)
    shutil.rmtree(stage_dir, ignore_errors=True)


def stage_translation(book_dir, config, merged_en_path):
    write_progress(book_dir, "translation")
    config_path = os.path.join(book_dir, "config.json")
    target_lang = config.get("target_lang", "uk")
    translated_dir = os.path.join(book_dir, "translated")
    os.makedirs(translated_dir, exist_ok=True)
    out_path = os.path.join(translated_dir, f"merged_translated_{target_lang}.md")
    if os.path.exists(out_path):
        log("translation: output already exists, skipping (resume).")
        return out_path

    cmd = [
        sys.executable, os.path.join(repo_dir, "translate_stage.py"),
        "--input", merged_en_path,
        "--output", out_path,
        "--book", config.get("_slug", ""),
        "--config", config_path,
        "--target-lang", target_lang,
    ]
    log("translation: running translate_stage.py (unchanged, source_lang=en from config.json)")
    subprocess.run(cmd, check=True, cwd=repo_dir)
    return out_path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--book", required=True)
    ap.add_argument("--clean", action="store_true")
    args = ap.parse_args()

    paths = resolve_book_paths(repo_dir, args.book)
    book_dir = paths["book_dir"]
    if not os.path.isdir(book_dir):
        log(f"book directory not found: {book_dir}")
        return 1

    config_path = os.path.join(book_dir, "config.json")
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except Exception as e:
        log(f"failed to load config.json: {e}")
        return 1
    config["_slug"] = args.book

    if config.get("pipeline_kind") != "docsbook":
        log("pipeline_kind is not 'docsbook' for this book -- refusing to run.")
        return 1

    if args.clean:
        for name in ("repo_clone", "source_docs", "humanized", "merged_en.md",
                      "book_editor_flags.json", "book_pipeline_progress.json"):
            p = os.path.join(book_dir, name)
            if os.path.isdir(p):
                shutil.rmtree(p)
            elif os.path.exists(p):
                os.remove(p)

    try:
        manifest = stage_docs_ingest(book_dir, config)
        humanized_dir = stage_humanize(book_dir, config, manifest)
        stage_editor_review(book_dir, config, manifest, humanized_dir)
        merged_en_path = stage_merge(book_dir, manifest, humanized_dir)

        out_en = os.path.join(book_dir, "output", f"{args.book}_en.pdf")
        stage_book_compile(book_dir, config, merged_en_path, out_en, "book_compile_en")

        translated_path = stage_translation(book_dir, config, merged_en_path)

        out_uk = os.path.join(book_dir, "output", f"{args.book}_uk.pdf")
        stage_book_compile(book_dir, config, translated_path, out_uk, "book_compile_uk")

        write_progress(book_dir, "done")
        log("Pipeline complete.")
    except SystemExit as e:
        log(str(e))
        return 0  # human-gate pause, not a failure
    except subprocess.CalledProcessError as e:
        write_progress(book_dir, "error", message=str(e))
        log(f"ABORT: subprocess failed: {e}")
        return 1
    except Exception as e:
        write_progress(book_dir, "error", message=str(e))
        log(f"ABORT: {e}")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
