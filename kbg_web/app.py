import os
import sys
import re
import json
import subprocess
import shutil
import signal
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, render_template, send_file

# Resolve repository root
repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from common.book_paths import resolve_book_paths
from common.edit_patch import patch_batch_translation
from common.file_lock import file_lock
from kbg_web.status_helper import calculate_progress, get_pdf_page_count
from kbg_web import edit_store

TTS_ENGINES = {
    "supertonic3": {
        "languages": ["ar", "bg", "hr", "cs", "da", "nl", "en", "et", "fi", "fr", "de", "el", "hi", "hu", "id", "it", "ja", "ko", "lv", "lt", "pl", "pt", "ro", "ru", "sk", "sl", "es", "sv", "tr", "uk", "vi", "na"],
        "label": "Supertonic 3 (Flow Matching, 31 мова)"
    },
    "styletts2": {
        "languages": ["uk"],
        "label": "StyleTTS2 (спеціалізована для української)"
    },
}

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 200 * 1024 * 1024  # 200 MB

# Translation server (llama-server on :8081) lifecycle tracking.
# PID-file based instead of pkill-by-pattern to avoid matching an unrelated
# process, and a start lock to prevent two concurrent /api/models/start
# calls from each spawning their own llama-server (see TASK-18).
LLAMA_PID_FILE = os.path.expanduser("~/llama-server-8081.pid")
LLAMA_START_LOCK_FILE = os.path.expanduser("~/llama-server-8081.lock")
LLAMA_START_LOCK_STALE_SECONDS = 15

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

auth = HTTPBasicAuth()

import secrets

credentials_file = os.path.join(repo_dir, "web_credentials.json")
users_data = {}

env_password = os.environ.get("KBG_WEB_PASSWORD")

if env_password:
    users_data = {"vokov": generate_password_hash(env_password)}
elif os.path.exists(credentials_file):
    try:
        with open(credentials_file, "r") as f:
            users_data = json.load(f)
    except Exception:
        pass

if not users_data:
    generated_password = secrets.token_urlsafe(16)
    print(f"\n==================================================")
    print(f"WARNING: No credentials found and KBG_WEB_PASSWORD not set.")
    print(f"Generated temporary password for user 'vokov':")
    print(f"Password: {generated_password}")
    print(f"==================================================\n")
    users_data = {"vokov": generate_password_hash(generated_password)}
    try:
        with open(credentials_file, "w") as f:
            json.dump(users_data, f)
    except Exception as e:
        print(f"Failed to save generated credentials to {credentials_file}: {e}")


@auth.verify_password
def verify_password(username, password):
    if username in users_data:
        return check_password_hash(users_data.get(username), password)
    return False

@app.before_request
@auth.login_required
def require_login():
    pass

@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"status": "error", "message": "File is too large (maximum allowed size is 200MB)"}), 413

# Registry of active background processes: {slug: subprocess.Popen}
active_processes = {}
completed_copied = set()

# Auto-resume-on-restart: persists the CURRENTLY running conversion's exact
# invocation to disk, so if Termux/Flask itself dies mid-run (not just this
# one process - the whole environment going down, which active_processes
# alone can't survive since it's purely in-memory), the autostart script
# can detect an interrupted run and re-launch the identical command on the
# next boot. The pipeline's own per-page skip-if-already-done logic (used
# throughout this project already) means simply re-running the same
# command resumes correctly with no extra state tracking needed here.
ACTIVE_CONVERSION_STATE_PATH = os.path.join(repo_dir, ".active_conversion.json")


def _write_active_conversion_state(slug, cmd, cwd, log_path):
    try:
        with open(ACTIVE_CONVERSION_STATE_PATH, "w", encoding="utf-8") as f:
            json.dump({"slug": slug, "cmd": cmd, "cwd": cwd, "log_path": log_path}, f, ensure_ascii=False)
    except Exception as e:
        print(f"[AutoResume] Warning: failed to write active-conversion state: {e}")


def _clear_active_conversion_state(slug=None):
    # Only clear if the on-disk state still refers to THIS slug - avoids a
    # race where book A's completion handler clears book B's still-running
    # state if a later conversion started before A's completion was noticed
    # (completion detection is lazy/poll-based here, see handle_process_completion).
    try:
        if not os.path.exists(ACTIVE_CONVERSION_STATE_PATH):
            return
        if slug is not None:
            with open(ACTIVE_CONVERSION_STATE_PATH, "r", encoding="utf-8") as f:
                state = json.load(f)
            if state.get("slug") != slug:
                return
        os.remove(ACTIVE_CONVERSION_STATE_PATH)
    except Exception as e:
        print(f"[AutoResume] Warning: failed to clear active-conversion state: {e}")

def is_book_process_running(slug):
    # Scan /proc for running python processes that match this book slug
    import os
    try:
        for pid_str in os.listdir("/proc"):
            if pid_str.isdigit():
                try:
                    with open(f"/proc/{pid_str}/cmdline", "r") as f:
                        cmdline = f.read()
                    if slug in cmdline and ("translate_epub.py" in cmdline or "translate_manga.py" in cmdline or "run_conversion_batches.py" in cmdline):
                        return True
                except Exception:
                    pass
    except Exception:
        pass
    return False

def handle_process_completion(slug, proc):
    # Flask observed this process end (success OR failure) while it was
    # still alive to see it - clear the auto-resume state regardless of
    # exit code, so a genuinely-failed run isn't retried forever on every
    # Termux restart. Only a crash that killed Flask/Termux itself BEFORE
    # this function ever got to run leaves the state file behind, which is
    # exactly the correct signal for the autostart script to resume it.
    _clear_active_conversion_state(slug)
    if proc.poll() == 0:
        try:
            settings = load_global_settings()
            out_root = settings.get("output_root")
            if out_root:
                os.makedirs(out_root, exist_ok=True)
                paths = resolve_book_paths(repo_dir, slug)
                local_out_dir = paths["output_dir"]
                if os.path.exists(local_out_dir):
                    import shutil
                    for filename in os.listdir(local_out_dir):
                        src_path = os.path.join(local_out_dir, filename)
                        if os.path.isfile(src_path):
                            dest_path = os.path.join(out_root, filename)
                            shutil.copy2(src_path, dest_path)
                            print(f"[CompletionHelper] Copied {filename} to {dest_path}")
        except Exception as e:
            print(f"[CompletionHelper] Error copying completion files: {e}")

def validate_slug(slug):
    return bool(re.match(r"^[a-z0-9_-]+$", slug))

def detect_epub_lang(epub_path):
    try:
        import zipfile
        import xml.etree.ElementTree as ET
        with zipfile.ZipFile(epub_path, 'r') as z:
            container_content = z.read("META-INF/container.xml")
            container_root = ET.fromstring(container_content)
            root_file_el = container_root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            if root_file_el is None:
                root_file_el = container_root.find(".//rootfile")
            opf_rel_path = root_file_el.attrib["full-path"]
            opf_content = z.read(opf_rel_path)
            opf_root = ET.fromstring(opf_content)
            lang_el = opf_root.find('.//{http://purl.org/dc/elements/1.1/}language')
            if lang_el is None:
                lang_el = opf_root.find('.//language')
            if lang_el is not None and lang_el.text:
                return lang_el.text.split('-')[0].lower()
    except Exception:
        pass
    return None

@app.route("/")
def dashboard():
    return render_template("dashboard.html")

@app.route("/api/books")
def list_books():
    books_dir = os.path.join(repo_dir, "books")
    if not os.path.exists(books_dir):
        return jsonify([])
        
    books = []
    for entry in os.listdir(books_dir):
        entry_path = os.path.join(books_dir, entry)
        if os.path.isdir(entry_path) and validate_slug(entry):
            config_path = os.path.join(entry_path, "config.json")
            if os.path.exists(config_path):
                try:
                    with open(config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)
                except Exception:
                    cfg = {}
            else:
                cfg = {}
                
            title = cfg.get("title", entry)
            authors = cfg.get("authors", "Unknown")
            target_lang = cfg.get("target_lang", "uk")
            
            # Determine if running
            is_running = False
            if entry in active_processes:
                proc = active_processes[entry]
                if proc.poll() is None:
                    is_running = True
                elif entry not in completed_copied:
                    handle_process_completion(entry, proc)
                    completed_copied.add(entry)
            if not is_running:
                is_running = is_book_process_running(entry)
                    
            # Calculate progress
            prog = calculate_progress(entry)
            if "error" in prog:
                prog = {"marker_percent": 0.0, "translation_percent": 0.0, "stress_percent": 0.0, "tts_percent": 0.0}
                
            # Scan output files
            output_dir = os.path.join(entry_path, "output")
            output_files = []
            if os.path.exists(output_dir):
                for f in os.listdir(output_dir):
                    if f.endswith((".epub", ".azw3", ".mp3", ".md", ".cbz", ".cbr", ".cb7", ".zip")):
                        output_files.append(f)
                        
            books.append({
                "slug": entry,
                "title": title,
                "authors": authors,
                "target_lang": target_lang,
                "is_running": is_running,
                "progress": prog,
                "output_files": sorted(output_files),
                "is_manga": cfg.get("is_manga", False),
                "tts_voice": cfg.get("tts_voice", "ukrainian_tts"),
                "tts_voice_quality": cfg.get("tts_voice_quality", "medium"),
                "tts_speaker_id": int(cfg.get("tts_speaker_id", 2)),
                "tts_speed": float(cfg.get("tts_speed", 1.0)),
                "tts_noise_scale": float(cfg.get("tts_noise_scale", 0.667)),
                "tts_noise_w": float(cfg.get("tts_noise_w", 0.8)),
                "tts_engine": cfg.get("tts_engine", "supertonic3")
            })
            
    return jsonify(books)

@app.route("/api/add", methods=["POST"])
def add_book_api():
    data = request.get_json() or {}
    slug = data.get("slug", "").strip()
    pdf_path = data.get("pdf_path", "").strip()
    title = data.get("title", "").strip()
    authors = data.get("authors", "").strip()
    lang = data.get("lang", "").strip()
    source_lang = data.get("source_lang", "").strip() or "ru"
    is_manga = bool(data.get("is_manga", False))
    
    if not slug or not pdf_path or not title or not authors or not lang:
        return jsonify({"status": "error", "message": "All fields are required"}), 400
        
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    if source_lang == "auto":
        return jsonify({"status": "error", "message": "Auto-detect source language is not supported for local PDF paths. Please select the correct language."}), 400
        
    if not os.path.exists(pdf_path):
        return jsonify({"status": "error", "message": "Source PDF file not found"}), 400
        
    try:
        # Create folder structure
        paths = resolve_book_paths(repo_dir, slug)
        if os.path.exists(paths["config_path"]):
            return jsonify({"status": "error", "message": "Book with this slug already exists. Use a different slug or delete the existing book first"}), 409
        book_dir = paths["book_dir"]
        
        os.makedirs(book_dir, exist_ok=True)
        os.makedirs(paths["cache_dir"], exist_ok=True)
        os.makedirs(paths["batches_dir"], exist_ok=True)
        os.makedirs(paths["translated_dir"], exist_ok=True)
        os.makedirs(paths["output_dir"], exist_ok=True)
        os.makedirs(paths["audio_dir"], exist_ok=True)
        
        # Copy source file
        ext = ""
        if os.path.isdir(pdf_path):
            if not is_manga:
                return jsonify({"status": "error", "message": "Source path is a directory. Directory sources are only supported for Manga."}), 400
            dest_dir = os.path.join(book_dir, "source")
            shutil.copytree(pdf_path, dest_dir, dirs_exist_ok=True)
            pages = len([f for f in os.listdir(dest_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
            page_ranges = []
        else:
            ext = os.path.splitext(pdf_path)[1].lower()
            dest_file = os.path.join(book_dir, f"{slug}{ext}")
            shutil.copy2(pdf_path, dest_file)
            
            if ext == ".pdf":
                pages = get_pdf_page_count(dest_file)
                page_ranges = [[1, pages]]
            else:
                pages = 0
                page_ranges = []
        
        # Write config.json
        config_data = {
            "slug": slug,
            "title": title,
            "authors": authors,
            "source_lang": source_lang,
            "target_lang": lang,
            "pdf_path": f"books/{slug}/{slug}.pdf" if ext == ".pdf" else "",
            "is_manga": is_manga,
            "generate_audiobook": not is_manga,
            "tts_voice": "ukrainian_tts" if lang == "uk" else "irina",
            "tts_voice_quality": "medium",
            "tts_speaker_id": 2 if lang == "uk" else 0,
            "tts_speed": 1.0,
            "tts_noise_scale": 0.667,
            "tts_noise_w": 0.8,
            "page_ranges": page_ranges
        }
        
        with open(paths["config_path"], "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": f"Book '{slug}' added successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/parse-metadata", methods=["POST"])
def parse_metadata_api():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
    file = request.files["file"]
    filename = file.filename
    ext = os.path.splitext(filename)[1].lower()
    
    title = ""
    authors = ""
    slug = ""
    detected_lang = "auto"
    
    if ext == ".epub":
        try:
            import zipfile
            import xml.etree.ElementTree as ET
            import tempfile
            import shutil
            
            temp_dir = tempfile.mkdtemp()
            temp_path = os.path.join(temp_dir, "temp.epub")
            file.save(temp_path)
            
            with zipfile.ZipFile(temp_path, 'r') as z:
                container_content = z.read("META-INF/container.xml")
                container_root = ET.fromstring(container_content)
                root_file_el = container_root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
                if root_file_el is None:
                    root_file_el = container_root.find(".//rootfile")
                opf_rel_path = root_file_el.attrib["full-path"]
                
                opf_content = z.read(opf_rel_path)
                opf_root = ET.fromstring(opf_content)
                
                title_el = opf_root.find('.//{http://purl.org/dc/elements/1.1/}title')
                if title_el is None:
                    title_el = opf_root.find('.//title')
                if title_el is not None:
                    title = title_el.text or ""
                    
                creator_el = opf_root.find('.//{http://purl.org/dc/elements/1.1/}creator')
                if creator_el is None:
                    creator_el = opf_root.find('.//creator')
                if creator_el is not None:
                    authors = creator_el.text or ""
                    
                lang_el = opf_root.find('.//{http://purl.org/dc/elements/1.1/}language')
                if lang_el is None:
                    lang_el = opf_root.find('.//language')
                if lang_el is not None and lang_el.text:
                    detected_lang = lang_el.text.split('-')[0].lower()
                    
            shutil.rmtree(temp_dir)
            title = title.strip()
            authors = authors.strip()
            
            if title:
                slug_base = title.lower()
            else:
                slug_base = os.path.splitext(filename)[0].lower()
            slug = re.sub(r'[^a-z0-9_-]', '-', slug_base)
            slug = re.sub(r'-+', '-', slug).strip('-')
            
            if not slug:
                slug_base = os.path.splitext(filename)[0].lower()
                slug = re.sub(r'[^a-z0-9_-]', '-', slug_base)
                slug = re.sub(r'-+', '-', slug).strip('-')
            if not slug:
                slug = "uploaded-book"
        except Exception:
            pass
            
    elif ext in [".pdf", ".txt", ".md"]:
        slug_base = os.path.splitext(filename)[0].lower()
        slug = re.sub(r'[^a-z0-9_-]', '-', slug_base)
        slug = re.sub(r'-+', '-', slug).strip('-')
        if not slug:
            slug = "uploaded-book"
        title = os.path.splitext(filename)[0]
        
    return jsonify({
        "status": "success",
        "detected_title": title,
        "detected_authors": authors,
        "detected_slug": slug,
        "detected_lang": detected_lang
    })

@app.route("/api/upload", methods=["POST"])
def upload_file_api():
    if "file" not in request.files:
        return jsonify({"status": "error", "message": "No file uploaded"}), 400
        
    uploaded_file = request.files["file"]
    slug = request.form.get("slug", "").strip()
    title = request.form.get("title", "").strip()
    authors = request.form.get("authors", "").strip()
    lang = request.form.get("lang", "").strip()
    source_lang = request.form.get("source_lang", "").strip() or lang
    
    if not slug or not title or not authors or not lang:
        return jsonify({"status": "error", "message": "All fields (slug, title, authors, lang) are required"}), 400
        
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    if os.path.exists(paths["config_path"]):
        return jsonify({"status": "error", "message": "Book with this slug already exists. Use a different slug or delete the existing book first"}), 409
        
    filename = uploaded_file.filename
    ext = os.path.splitext(filename)[1].lower()
    if ext != ".epub" and source_lang == "auto":
        return jsonify({"status": "error", "message": "Auto-detect source language is only supported for EPUB files. Please select the correct language."}), 400
        
    manga_extensions = [".cbz", ".cbr", ".cb7", ".zip", ".rar"]
    if ext not in [".pdf", ".epub", ".txt", ".md"] + manga_extensions:
        return jsonify({"status": "error", "message": f"Unsupported file extension '{ext}'"}), 400
        
    try:
        is_manga = ext in manga_extensions or request.form.get("is_manga", "false").lower() == "true"
        
        book_dir = paths["book_dir"]
        os.makedirs(book_dir, exist_ok=True)
        os.makedirs(paths["cache_dir"], exist_ok=True)
        os.makedirs(paths["batches_dir"], exist_ok=True)
        os.makedirs(paths["translated_dir"], exist_ok=True)
        os.makedirs(paths["output_dir"], exist_ok=True)
        os.makedirs(paths["audio_dir"], exist_ok=True)
        
        pdf_path = ""
        page_ranges = []
        
        if is_manga:
            dest_manga = os.path.join(book_dir, f"{slug}{ext}")
            uploaded_file.save(dest_manga)
            if ext == ".pdf":
                pdf_path = f"books/{slug}/{slug}.pdf"
                pages = get_pdf_page_count(dest_manga)
                page_ranges = [[1, pages]]
        else:
            if ext == ".pdf":
                pdf_path = f"books/{slug}/{slug}.pdf"
                dest_pdf = os.path.join(book_dir, f"{slug}.pdf")
                uploaded_file.save(dest_pdf)
                pages = get_pdf_page_count(dest_pdf)
                page_ranges = [[1, pages]]
                
            elif ext == ".epub":
                temp_epub_path = os.path.join(book_dir, f"uploaded_temp.epub")
                uploaded_file.save(temp_epub_path)
                
                if source_lang == "auto":
                    source_lang = detect_epub_lang(temp_epub_path) or lang
                    
                if source_lang == lang:
                    target_md_name = f"merged_translated_{lang}.md"
                else:
                    target_md_name = f"merged_source_{source_lang}.md"
                    
                merged_md_path = os.path.join(paths["translated_dir"], target_md_name)
                cmd = [
                    sys.executable,
                    os.path.join(repo_dir, "bin", "extract_epub_text.py"),
                    "-i", temp_epub_path,
                    "-o", merged_md_path
                ]
                res = subprocess.run(cmd, capture_output=True, text=True)
                if os.path.exists(temp_epub_path):
                    os.remove(temp_epub_path)
                    
                if res.returncode != 0:
                    raise Exception(f"Failed to extract text from EPUB: {res.stderr}")
                    
            elif ext in [".txt", ".md"]:
                if source_lang == "auto":
                    source_lang = lang
                    
                if source_lang == lang:
                    target_md_name = f"merged_translated_{lang}.md"
                else:
                    target_md_name = f"merged_source_{source_lang}.md"
                    
                merged_md_path = os.path.join(paths["translated_dir"], target_md_name)
                uploaded_file.save(merged_md_path)
            
        config_data = {
            "slug": slug,
            "title": title,
            "authors": authors,
            "source_lang": source_lang,
            "target_lang": lang,
            "pdf_path": pdf_path,
            "is_manga": is_manga,
            "generate_audiobook": not is_manga,
            "tts_voice": "ukrainian_tts" if lang == "uk" else "irina",
            "tts_voice_quality": "medium",
            "tts_speaker_id": 2 if lang == "uk" else 0,
            "tts_speed": 1.0,
            "tts_noise_scale": 0.667,
            "tts_noise_w": 0.8,
            "page_ranges": page_ranges
        }
        
        with open(paths["config_path"], "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": f"Book '{slug}' uploaded and initialized successfully."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/run/<slug>", methods=["POST"])
def run_conversion_api(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    if not os.path.exists(paths["book_dir"]):
        return jsonify({"status": "error", "message": "Book directory not found"}), 404
        
    data = request.get_json() or {}
    force = data.get("force", False)

    # Check if already running
    is_running = False
    if slug in active_processes:
        proc = active_processes[slug]
        if proc.poll() is None:
            is_running = True
    if not is_running and is_book_process_running(slug):
        is_running = True

    if is_running:
        if not force:
            return jsonify({"status": "error", "message": "Conversion is already running"}), 400
        # force=true: kill existing process and continue
        try:
            if slug in active_processes:
                active_processes[slug].kill()
                del active_processes[slug]
            import signal
            for pid_str in os.listdir("/proc"):
                if pid_str.isdigit():
                    try:
                        with open(f"/proc/{pid_str}/cmdline", "r") as _f:
                            cmdline = _f.read()
                        if slug in cmdline and ("translate_epub.py" in cmdline or "translate_manga.py" in cmdline or "run_conversion_batches.py" in cmdline):
                            os.kill(int(pid_str), signal.SIGKILL)
                    except Exception:
                        pass
        except Exception:
            pass
        import time as _time
        _time.sleep(1)
        
    # Clear stale progress files
    epub_prog_path = os.path.join(paths["cache_dir"], "epub_progress.json")
    if os.path.exists(epub_prog_path):
        try:
            os.remove(epub_prog_path)
        except Exception:
            pass
    manga_prog_path = os.path.join(paths["book_dir"], "manga_progress.json")
    if os.path.exists(manga_prog_path):
        try:
            os.remove(manga_prog_path)
        except Exception:
            pass
            
    # data already parsed above (force handling)
    
    config_path = paths["config_path"]
    is_manga = False
    cfg = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                is_manga = cfg.get("is_manga", False)
        except Exception:
            pass
            
    if is_manga:
        # Determine source file or directory
        manga_input = ""
        if os.path.isdir(os.path.join(paths["book_dir"], "source")):
            manga_input = os.path.join(paths["book_dir"], "source")
        else:
            source_ext = ""
            for possible_ext in [".cbz", ".cbr", ".cb7", ".zip", ".rar", ".pdf", ".epub"]:
                if os.path.exists(os.path.join(paths["book_dir"], f"{slug}{possible_ext}")):
                    source_ext = possible_ext
                    break
            if source_ext:
                manga_input = os.path.join(paths["book_dir"], f"{slug}{source_ext}")
                
        if not manga_input:
            return jsonify({"status": "error", "message": "Manga source file or directory not found"}), 400
        manga_output_dir = os.path.join(paths["book_dir"], "output")
        os.makedirs(manga_output_dir, exist_ok=True)
        manga_output = os.path.join(manga_output_dir, f"{slug}_translated_{cfg.get('target_lang', 'uk')}.cbz")
        
        # Reset progress file
        progress_file = os.path.join(paths["book_dir"], "manga_progress.json")
        try:
            with open(progress_file, "w", encoding="utf-8") as pf:
                json.dump({"current_page": 0, "total_pages": 1}, pf)
        except Exception:
            pass
            
        # Run translate_manga.py inside PRoot Ubuntu container
        cmd = [
            "proot-distro", "login", "ubuntu", "--", 
            "python3", "-u", "/data/data/com.termux/files/home/kindle-butch-gen/translate_manga.py",
            "--input", manga_input,
            "--output", manga_output,
            "--lang", cfg.get("source_lang", "en"),
            "--progress-file", progress_file
        ]
        # Include glossary if it exists
        glossary_path = os.path.join(paths["book_dir"], "glossary.json")
        if os.path.exists(glossary_path):
            cmd.extend(["--glossary", glossary_path])
        if data.get("no_translate"):
            cmd.append("--no-translate")
        if data.get("no_ebook"):
            cmd.append("--no-ebook")
            
        manga_resolution = data.get("manga_resolution", "1280x1920")
        max_width, max_height = 1280, 1920
        if manga_resolution == "original":
            max_width, max_height = 0, 0
        elif "x" in manga_resolution:
            try:
                w_str, h_str = manga_resolution.split("x")
                max_width, max_height = int(w_str), int(h_str)
            except ValueError:
                pass
        
        cmd.extend(["--max-width", str(max_width), "--max-height", str(max_height)])
    else:
        # Check if it is an EPUB book (so we use direct EPUB translation)
        epub_source_file = os.path.join(paths["book_dir"], f"{slug}.epub")
        if os.path.exists(epub_source_file):
            cmd = [
                sys.executable, "translate_epub.py",
                "--input", epub_source_file,
                "--output", os.path.join(paths["output_dir"], f"{slug}_translated_{cfg.get('target_lang', 'uk')}.epub"),
                "--target-lang", cfg.get("target_lang", "uk"),
                "--book", slug
            ]
        else:
            cmd = [sys.executable, "run_conversion_batches.py", "--book", slug]
            if data.get("clean"):
                cmd.append("--clean")
            if data.get("no_translate"):
                cmd.append("--no-translate")
            if data.get("no_ebook"):
                cmd.append("--no-ebook")
            if data.get("no_audio"):
                cmd.append("--no-audio")
        
    log_path = paths["log_path"]
    
    try:
        # Prepare progress log with execution header
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n\n--- Starting Conversion Pipeline via Web GUI at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ---\n")
            f.write(f"Command: {' '.join(cmd)}\n\n")
            
        log_file = open(log_path, "a", encoding="utf-8")
        
        # Start background subprocess
        proc = subprocess.Popen(
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            cwd=repo_dir,
            text=True
        )
        
        active_processes[slug] = proc
        _write_active_conversion_state(slug, cmd, repo_dir, log_path)
        return jsonify({"status": "success", "message": "Pipeline started in background"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/stop/<slug>", methods=["POST"])
def stop_conversion_api(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    if slug not in active_processes:
        return jsonify({"status": "error", "message": "No process running for this book"}), 400
        
    proc = active_processes[slug]
    if proc.poll() is not None:
        return jsonify({"status": "error", "message": "Process has already terminated"}), 400
        
    try:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()

        # Explicit user stop should not trigger auto-resume on next restart.
        _clear_active_conversion_state(slug)

        paths = resolve_book_paths(repo_dir, slug)
        with open(paths["log_path"], "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Conversion process terminated by user ---\n")

        return jsonify({"status": "success", "message": "Process terminated successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/delete/<slug>", methods=["POST"])
def delete_book_api(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400

    paths = resolve_book_paths(repo_dir, slug)
    if not os.path.exists(paths["book_dir"]):
        return jsonify({"status": "error", "message": "Book directory not found"}), 404

    is_running = False
    if slug in active_processes:
        proc = active_processes[slug]
        if proc.poll() is None:
            is_running = True
    if not is_running and is_book_process_running(slug):
        is_running = True

    if is_running:
        return jsonify({"status": "error", "message": "Stop the conversion before deleting this book"}), 400

    try:
        shutil.rmtree(paths["book_dir"])
        active_processes.pop(slug, None)
        completed_copied.discard(slug)
        return jsonify({"status": "success", "message": f"Book '{slug}' deleted"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/status/<slug>")
def status_api(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    if not os.path.exists(paths["book_dir"]):
        return jsonify({"status": "error", "message": "Book directory not found"}), 404
        
    # Check running status
    is_running = False
    if slug in active_processes:
        proc = active_processes[slug]
        if proc.poll() is None:
            is_running = True
        elif slug not in completed_copied:
            handle_process_completion(slug, proc)
            completed_copied.add(slug)
    if not is_running:
        is_running = is_book_process_running(slug)
            
    # Calculate progress percentages
    prog = calculate_progress(slug)
    if "error" in prog:
        return jsonify({"status": "error", "message": prog["error"]}), 400
        
    # Read the last 30 lines of the progress log
    log_lines = []
    log_path = paths["log_path"]
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                log_lines = lines[-30:]
        except Exception as e:
            log_lines = [f"Error reading log file: {e}"]
            
    return jsonify({
        "slug": slug,
        "is_running": is_running,
        "marker_percent": prog["marker_percent"],
        "translation_percent": prog["translation_percent"],
        "stress_percent": prog["stress_percent"],
        "tts_percent": prog["tts_percent"],
        "logs": log_lines
    })

@app.route("/api/download/<slug>/<filename>")
def download_output_file(slug, filename):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    filename = os.path.basename(filename)
    paths = resolve_book_paths(repo_dir, slug)
    output_dir = os.path.abspath(paths["output_dir"])
    file_path = os.path.abspath(os.path.join(output_dir, filename))
    
    # Path traversal validation: ensure resolved path is strictly inside books/<slug>/output/
    if not file_path.startswith(output_dir + os.sep):
        return jsonify({"status": "error", "message": "Access denied (path traversal detected)"}), 403
        
    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    return send_file(file_path, as_attachment=True)

@app.route("/api/delete-file/<slug>/<filename>", methods=["POST"])
def delete_output_file(slug, filename):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400

    filename = os.path.basename(filename)
    paths = resolve_book_paths(repo_dir, slug)
    output_dir = os.path.abspath(paths["output_dir"])
    file_path = os.path.abspath(os.path.join(output_dir, filename))

    # Path traversal validation: ensure resolved path is strictly inside books/<slug>/output/
    if not file_path.startswith(output_dir + os.sep):
        return jsonify({"status": "error", "message": "Access denied (path traversal detected)"}), 403

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return jsonify({"status": "error", "message": "File not found"}), 404

    try:
        os.remove(file_path)
        return jsonify({"status": "success", "message": f"'{filename}' deleted"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/tts-settings/<slug>", methods=["POST"])
def update_tts_settings(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    config_path = paths["config_path"]
    if not os.path.exists(config_path):
        return jsonify({"status": "error", "message": "Book configuration not found"}), 404
        
    data = request.get_json() or {}
    try:
        # Load existing config
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        # Parse inputs
        tts_engine = str(data.get("tts_engine", config.get("tts_engine", "supertonic3"))).strip()
        tts_voice = str(data.get("tts_voice", config.get("tts_voice", "supertonic3"))).strip()
        tts_voice_quality = str(data.get("tts_voice_quality", config.get("tts_voice_quality", "medium"))).strip()
        
        # Validations
        if tts_engine not in TTS_ENGINES:
            return jsonify({"status": "error", "message": "Invalid tts_engine"}), 400
            
        target_lang = config.get("target_lang", "uk")
        if target_lang not in TTS_ENGINES[tts_engine]["languages"]:
            return jsonify({"status": "error", "message": f"TTS engine '{tts_engine}' does not support book language '{target_lang}'"}), 400
            
        tts_speaker_id = int(data.get("tts_speaker_id", config.get("tts_speaker_id", 2)))
        tts_speed = float(data.get("tts_speed", config.get("tts_speed", 1.0)))
        tts_noise_scale = float(data.get("tts_noise_scale", config.get("tts_noise_scale", 0.667)))
        tts_noise_w = float(data.get("tts_noise_w", config.get("tts_noise_w", 0.8)))
        
        if tts_engine == "supertonic3":
            if not (0 <= tts_speaker_id <= 9):
                return jsonify({"status": "error", "message": "tts_speaker_id must be between 0 and 9 for Supertonic 3"}), 400
                
        if not (0.5 <= tts_speed <= 2.0):
            return jsonify({"status": "error", "message": "tts_speed must be between 0.5 and 2.0"}), 400
        if not (0.1 <= tts_noise_scale <= 1.5):
            return jsonify({"status": "error", "message": "tts_noise_scale must be between 0.1 and 1.5"}), 400
        if not (0.1 <= tts_noise_w <= 1.5):
            return jsonify({"status": "error", "message": "tts_noise_w must be between 0.1 and 1.5"}), 400
            
        # Update config
        config["tts_engine"] = tts_engine
        config["tts_voice"] = tts_voice
        config["tts_voice_quality"] = tts_voice_quality
        config["tts_speaker_id"] = tts_speaker_id
        config["tts_speed"] = tts_speed
        config["tts_noise_scale"] = tts_noise_scale
        config["tts_noise_w"] = tts_noise_w
        
        # Write back
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": "TTS settings saved successfully"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/api/tts-preview/<slug>", methods=["POST"])
def tts_preview(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
    data = request.get_json() or {}
    text = data.get("text", "").strip()
    if not text:
        return jsonify({"status": "error", "message": "Text is required for preview"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    config_path = paths["config_path"]
    if not os.path.exists(config_path):
        return jsonify({"status": "error", "message": "Book configuration not found"}), 404
        
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
            
        target_lang = config.get("target_lang", "uk")
        tts_engine = str(data.get("tts_engine", config.get("tts_engine", "supertonic3"))).strip()
        
        if tts_engine not in TTS_ENGINES:
            return jsonify({"status": "error", "message": f"Unsupported tts_engine '{tts_engine}'"}), 400
        if target_lang not in TTS_ENGINES[tts_engine]["languages"]:
            return jsonify({"status": "error", "message": f"TTS engine '{tts_engine}' does not support language '{target_lang}'"}), 400
            
        # Read parameters from request JSON data or config
        speaker_id = int(data.get("tts_speaker_id", config.get("tts_speaker_id", 2) if target_lang == "uk" else 0))
        speed = float(data.get("tts_speed", config.get("tts_speed", 1.0)))
        noise_scale = float(data.get("tts_noise_scale", config.get("tts_noise_scale", 0.667)))
        noise_w = float(data.get("tts_noise_w", config.get("tts_noise_w", 0.8)))
        
        # Prepare target path
        preview_wav_path = os.path.join(paths["cache_dir"], "preview.wav")
        if os.path.exists(preview_wav_path):
            try:
                os.remove(preview_wav_path)
            except Exception:
                pass
        os.makedirs(os.path.dirname(preview_wav_path), exist_ok=True)
        if target_lang == "uk":
            try:
                cmd_stress = [
                    "proot-distro", "login", "ubuntu", "--",
                    "python3", "/data/data/com.termux/files/home/kindle-butch-gen/bin/stressify_batch.py",
                    "--inline", text
                ]
                res_stress = subprocess.run(cmd_stress, capture_output=True, text=True, timeout=15)
                if res_stress.returncode == 0:
                    stressed_text = res_stress.stdout.strip()
                    if stressed_text:
                        text = stressed_text
                else:
                    print(f"Warning: inline stressifier returned code {res_stress.returncode}, stderr: {res_stress.stderr}", file=sys.stderr)
            except Exception as e:
                print(f"Warning: inline stressifier failed: {e}", file=sys.stderr)

        if tts_engine in ["supertonic3", "styletts2"]:
            # Prepare payload for tts_helper.py
            payload = {
                "tts_engine": tts_engine,
                "output_dir": paths["cache_dir"],
                "chunks": [{"hash": "preview", "text": text}],
                "speaker_id": speaker_id,
                "speed": speed,
                "lang": target_lang
            }
            helper_path = "/data/data/com.termux/files/home/kindle-butch-gen/bin/tts_helper.py"
            cmd = [
                sys.executable, helper_path
            ]
            res = subprocess.run(cmd, input=json.dumps(payload, ensure_ascii=False), capture_output=True, text=True)
            if res.returncode != 0:
                return jsonify({"status": "error", "message": f"{tts_engine} preview failed: {res.stderr}"}), 500
        else:
            return jsonify({"status": "error", "message": f"TTS preview is not supported for engine: {tts_engine}"}), 400
                
        if not os.path.exists(preview_wav_path):
            return jsonify({"status": "error", "message": "Failed to generate preview WAV file"}), 500
            
        return send_file(preview_wav_path, mimetype="audio/wav")
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

def load_global_settings():
    path = os.path.join(repo_dir, "global_settings.json")
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"output_root": "/storage/emulated/0/Documents/kindle-butch-gen/library"}

def save_global_settings(settings):
    path = os.path.join(repo_dir, "global_settings.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"Failed to save global settings: {e}")

@app.route("/api/browse-fs")
def browse_fs():
    path = request.args.get("path", "/storage/emulated/0")
    path = os.path.abspath(path)
    # Allowed root zones
    ALLOWED_ROOTS = ["/storage/emulated/0", "/data/data/com.termux/files/home"]
    if not any(path.startswith(root) for root in ALLOWED_ROOTS):
        return jsonify({"error": "Path outside allowed roots"}), 403
    if not os.path.isdir(path):
        return jsonify({"error": "Not a directory"}), 400
    try:
        entries = []
        for item in sorted(os.listdir(path)):
            full = os.path.join(path, item)
            if os.path.isdir(full) and not item.startswith('.'):
                entries.append({"name": item, "path": full})
        parent = os.path.dirname(path) if path not in ALLOWED_ROOTS else None
        return jsonify({"current": path, "parent": parent, "dirs": entries})
    except PermissionError:
        return jsonify({"error": "Permission denied"}), 403

@app.route("/api/settings/output-root", methods=["POST"])
def set_output_root():
    data = request.get_json() or {}
    new_root = data.get("path", "").strip()
    if not new_root or not os.path.isabs(new_root):
        return jsonify({"status": "error", "message": "Invalid path"}), 400
    try:
        os.makedirs(new_root, exist_ok=True)  # verification that we can write
    except Exception as e:
        return jsonify({"status": "error", "message": f"Cannot write to directory: {e}"}), 403
    settings = load_global_settings()
    settings["output_root"] = new_root
    save_global_settings(settings)
    return jsonify({"status": "success", "output_root": new_root})

@app.route("/api/settings")
def get_settings():
    return jsonify(load_global_settings())

@app.route("/api/models")
@auth.login_required
def get_models_info():
    import socket
    import glob
    settings = load_global_settings()
    translation_model = settings.get("translation_model", "/data/data/com.termux/files/home/models/hy-mt2/Hy-MT2-7B-Q4_K_M.gguf")

    models_dir = os.path.expanduser("~/models")
    available = []
    if os.path.exists(models_dir):
        for path in glob.glob(os.path.join(models_dir, "**/*.gguf"), recursive=True):
            available.append(path)
            
    is_open = False
    try:
        with socket.create_connection(("127.0.0.1", 8081), timeout=0.5) as s:
            is_open = True
    except Exception:
        pass
        
    loaded_model = None
    if is_open:
        try:
            import requests
            resp = requests.get("http://127.0.0.1:8081/props", timeout=0.5)
            if resp.status_code == 200:
                data = resp.json()
                loaded_model = data.get("model_alias", "") or data.get("model", "")
        except Exception:
            pass
            
    return jsonify({
        "translation_model": translation_model,
        "available_models": available,
        "server_status": {
            "running": is_open,
            "loaded_model": loaded_model
        }
    })

@app.route("/api/models/configure", methods=["POST"])
@auth.login_required
def configure_models():
    data = request.get_json() or {}
    translation_model = data.get("translation_model")

    settings = load_global_settings()
    if translation_model:
        settings["translation_model"] = translation_model

    save_global_settings(settings)
    return jsonify({"status": "success"})

def _read_llama_pid():
    """Return the tracked llama-server PID if the PID file exists and that
    process is still alive, else None (also true for a stale/dead PID)."""
    if not os.path.exists(LLAMA_PID_FILE):
        return None
    try:
        with open(LLAMA_PID_FILE, "r") as f:
            pid = int(f.read().strip())
    except Exception:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid

def _stop_llama_server():
    """Stop the tracked llama-server (if any) and always clear the PID
    file afterward, so a stale/dead entry never lingers and blocks a
    future start."""
    import signal
    import time
    pid = _read_llama_pid()
    if pid:
        try:
            os.kill(pid, signal.SIGTERM)
            for _ in range(10):
                time.sleep(0.3)
                try:
                    os.kill(pid, 0)
                except OSError:
                    break
            else:
                try:
                    os.kill(pid, signal.SIGKILL)
                except OSError:
                    pass
        except OSError:
            pass
    if os.path.exists(LLAMA_PID_FILE):
        try:
            os.remove(LLAMA_PID_FILE)
        except Exception:
            pass

@app.route("/api/models/start", methods=["POST"])
@auth.login_required
def start_translation_server_api():
    import time

    # Clear a stale lock (e.g. left behind by a crashed request) before
    # trying to acquire — a lock older than this is never legitimate,
    # since the critical section below only takes ~1s.
    if os.path.exists(LLAMA_START_LOCK_FILE):
        try:
            age = time.time() - os.path.getmtime(LLAMA_START_LOCK_FILE)
        except OSError:
            age = LLAMA_START_LOCK_STALE_SECONDS + 1
        if age > LLAMA_START_LOCK_STALE_SECONDS:
            try:
                os.remove(LLAMA_START_LOCK_FILE)
            except Exception:
                pass

    try:
        lock_fd = os.open(LLAMA_START_LOCK_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        return jsonify({"status": "error", "message": "A start is already in progress"}), 409

    try:
        os.write(lock_fd, str(os.getpid()).encode())
        os.close(lock_fd)

        # Single point of truth for stopping the old instance: the API
        # layer, via the PID file. start-translation-server.sh no longer
        # does its own pkill.
        _stop_llama_server()

        sh_script = os.path.expanduser("~/start-translation-server.sh")
        if not os.path.exists(sh_script):
            return jsonify({"status": "error", "message": "Translation server script not found"}), 404

        subprocess.Popen(["bash", sh_script, LLAMA_PID_FILE], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True)
        return jsonify({"status": "success", "message": "Translation server start triggered"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        try:
            os.remove(LLAMA_START_LOCK_FILE)
        except Exception:
            pass

@app.route("/api/models/stop", methods=["POST"])
@auth.login_required
def stop_translation_server_api():
    _stop_llama_server()
    return jsonify({"status": "success", "message": "Translation server stopped"})

# -------------------------------------------------------------
# VISUAL STAGE VIEWER / QUALITY ASSURANCE ROUTES
# -------------------------------------------------------------

@app.route("/view/<slug>")
@auth.login_required
def view_book_stages(slug):
    if not validate_slug(slug):
        return "Invalid slug format", 400
    # Serve visualizer page
    return render_template("stages.html", slug=slug)

@app.route("/api/preview/audio/<slug>/<chunk_hash>")
@auth.login_required
def preview_audio(slug, chunk_hash):
    if not validate_slug(slug) or not re.match(r"^[a-f0-9]{64}$", chunk_hash):
        return "Invalid parameters", 400
    paths = resolve_book_paths(repo_dir, slug)
    for voice_slug in ["styletts2", "supertonic-3-tts-int8"]:
        wav_path = os.path.join(paths["audio_dir"], f"chunks_{voice_slug}", f"{chunk_hash}.wav")
        if os.path.exists(wav_path):
            return send_file(wav_path, mimetype="audio/wav")
    return "Audio not found", 404

@app.route("/api/preview/manga/<slug>")
@auth.login_required
def preview_manga(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    config_path = paths["config_path"]
    if not os.path.exists(config_path):
        return jsonify({"status": "error", "message": "Book not found"}), 404
        
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
        
    if not cfg.get("is_manga", False):
        return jsonify({"status": "error", "message": "Not a manga"}), 400
        
    source_ext = ""
    is_dir_source = os.path.isdir(os.path.join(paths["book_dir"], "source"))
    if not is_dir_source:
        for possible_ext in [".cbz", ".cbr", ".cb7", ".zip", ".rar", ".pdf"]:
            if os.path.exists(os.path.join(paths["book_dir"], f"{slug}{possible_ext}")):
                source_ext = possible_ext
                break
        if not source_ext:
            return jsonify({"status": "error", "message": "Manga source file or directory not found"}), 400
            
    translated_file = os.path.join(paths["book_dir"], "output", f"{slug}_translated_{cfg.get('target_lang', 'uk')}.cbz")
    
    preview_cache = os.path.join(paths["book_dir"], "preview_cache")
    os.makedirs(preview_cache, exist_ok=True)
    
    # 1. Source pages extraction
    src_preview_dir = os.path.join(preview_cache, "source")
    os.makedirs(src_preview_dir, exist_ok=True)
    if not os.listdir(src_preview_dir):
        try:
            if is_dir_source:
                pass  # Read directly from actual source directory
            elif source_ext in [".zip", ".cbz"]:
                source_file = os.path.join(paths["book_dir"], f"{slug}{source_ext}")
                subprocess.run(["unzip", "-j", source_file, "*.png", "*.jpg", "*.jpeg", "-d", src_preview_dir], capture_output=True)
            elif source_ext in [".rar", ".cbr"]:
                source_file = os.path.join(paths["book_dir"], f"{slug}{source_ext}")
                subprocess.run(["unrar", "e", source_file, "-d", src_preview_dir], capture_output=True)
            elif source_ext == ".pdf":
                source_file = os.path.join(paths["book_dir"], f"{slug}{source_ext}")
                subprocess.run(["pdftoppm", "-png", "-f", "1", "-l", "5", "-r", "100", source_file, os.path.join(src_preview_dir, "page")], capture_output=True)
        except Exception:
            pass
            
    # 2. Cleaned pages extraction (not needed anymore, we serve directly from the actual cleaned folder)
    cleaned_preview_dir = os.path.join(preview_cache, "cleaned")
    os.makedirs(cleaned_preview_dir, exist_ok=True)
            
    # 3. Translated pages extraction (only extract if archive exists and target_preview is empty)
    tgt_preview_dir = os.path.join(preview_cache, "translated")
    os.makedirs(tgt_preview_dir, exist_ok=True)
    if os.path.exists(translated_file) and not os.listdir(tgt_preview_dir):
        try:
            subprocess.run(["unzip", "-j", translated_file, "*.png", "*.jpg", "*.jpeg", "-d", tgt_preview_dir], capture_output=True)
        except Exception:
            pass
            
    from natsort import natsorted
    actual_source_dir = os.path.join(paths["book_dir"], "source")
    actual_cleaned_dir = os.path.join(paths["book_dir"], "cleaned")
    actual_translated_dir = os.path.join(paths["book_dir"], "translated")

    if is_dir_source and os.path.exists(actual_source_dir):
        src_files = natsorted([f for f in os.listdir(actual_source_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    else:
        src_files = natsorted([f for f in os.listdir(src_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])

    if os.path.exists(actual_cleaned_dir):
        clean_files = natsorted([f for f in os.listdir(actual_cleaned_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    else:
        clean_files = natsorted([f for f in os.listdir(cleaned_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])

    if os.path.exists(actual_translated_dir):
        tgt_files = natsorted([f for f in os.listdir(actual_translated_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    else:
        tgt_files = natsorted([f for f in os.listdir(tgt_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    
    return jsonify({
        "status": "success",
        "source_pages": src_files,
        "cleaned_pages": clean_files,
        "translated_pages": tgt_files
    })

@app.route("/api/preview/manga-file/<slug>/<folder>/<filename>")
@auth.login_required
def serve_manga_preview_file(slug, folder, filename):
    if not validate_slug(slug) or folder not in ["source", "translated", "cleaned"]:
        return "Invalid parameters", 400
    paths = resolve_book_paths(repo_dir, slug)
    
    # Try actual directory first
    actual_path = os.path.join(paths["book_dir"], folder, filename)
    if os.path.exists(actual_path):
        return send_file(actual_path)
        
    # Fallback to preview_cache
    file_path = os.path.join(paths["book_dir"], "preview_cache", folder, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    return "Not found", 404

@app.route("/api/preview/manga-bubbles/<slug>/<page_filename>")
@auth.login_required
def preview_manga_bubbles(slug, page_filename):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
    paths = resolve_book_paths(repo_dir, slug)
    page_filename = os.path.basename(page_filename)
    page_stem = os.path.splitext(page_filename)[0]
    meta_path = os.path.join(paths["book_dir"], "bubbles_meta", f"{page_stem}.json")
    if not os.path.exists(meta_path):
        return jsonify({"status": "error", "message": "Page not processed yet - no bubble metadata found"}), 404
    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            bubbles = json.load(f)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to read bubble metadata: {e}"}), 500
    return jsonify({"status": "success", "page": page_filename, "bubbles": bubbles})

@app.route("/api/preview/manga-quality-flags/<slug>")
@auth.login_required
def preview_manga_quality_flags(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
    paths = resolve_book_paths(repo_dir, slug)
    quality_flags_path = os.path.join(paths["book_dir"], "quality_flags.json")
    if not os.path.exists(quality_flags_path):
        return jsonify({"status": "success", "flags": []})
    try:
        with open(quality_flags_path, "r", encoding="utf-8") as f:
            flags = json.load(f)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to read quality flags: {e}"}), 500
    return jsonify({"status": "success", "flags": flags})

@app.route("/api/preview/book/<slug>")
@auth.login_required
def preview_book_stages(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
        
    paths = resolve_book_paths(repo_dir, slug)
    config_path = paths["config_path"]
    if not os.path.exists(config_path):
        return jsonify({"status": "error", "message": "Book not found"}), 404
        
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
        
    target_lang = cfg.get("target_lang", "uk")
    source_lang = cfg.get("source_lang", "ru")
    
    trans_cache = {}
    if os.path.exists(paths["translate_cache"]):
        try:
            with open(paths["translate_cache"], "r", encoding="utf-8") as f:
                trans_cache = json.load(f)
        except Exception:
            pass
            
    stress_cache = {}
    stress_cache_path = os.path.join(paths["book_dir"], "translated", f"stress_cache_{target_lang}.json")
    if os.path.exists(stress_cache_path):
        try:
            with open(stress_cache_path, "r", encoding="utf-8") as f:
                stress_cache = json.load(f)
        except Exception:
            pass
            
    import hashlib
    def get_hash(text):
        return hashlib.sha256(text.encode('utf-8')).hexdigest()
        
    from kbg_web.status_helper import split_paragraph_to_chunks
    
    tts_engine = cfg.get("tts_engine", "supertonic3")
    voice_slug = "styletts2" if tts_engine == "styletts2" else "supertonic-3-tts-int8"
    chunks_dir = os.path.join(paths["audio_dir"], f"chunks_{voice_slug}")
    
    suffix = f"_translated_{target_lang}" if (target_lang != source_lang) else ""
    if suffix:
        target_md_file = os.path.join(paths["translated_dir"], f"merged_translated_{target_lang}.md")
    else:
        target_md_file = os.path.join(paths["translated_dir"], f"merged_source_{source_lang}.md")
        
    from flask import request
    page = request.args.get("page", 1, type=int)
    limit = request.args.get("limit", 30, type=int)
    
    raw_chunks = []
    if os.path.exists(target_md_file):
        try:
            with open(target_md_file, "r", encoding="utf-8") as f:
                content = f.read()
            raw_paragraphs = re.split(r'\n\s*\n', content)
            
            max_chunk_chars = 150 if tts_engine == "styletts2" else 1000
            
            for p in raw_paragraphs:
                p = p.strip()
                if not p or p.startswith("#"):
                    continue
                chunks = split_paragraph_to_chunks(p, max_chars=max_chunk_chars)
                for chunk in chunks:
                    chunk = chunk.strip()
                    if chunk:
                        raw_chunks.append(chunk)
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error parsing book: {e}"}), 500
            
    total_chunks = len(raw_chunks)
    total_pages = (total_chunks + limit - 1) // limit if total_chunks > 0 else 1
    
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    sliced_chunks = raw_chunks[start_idx:end_idx]
    
    paragraphs = []
    if sliced_chunks:
        try:
            # Speed up the translation original text lookup using a reverse index dict
            reverse_trans_cache = {v.strip(): k for k, v in trans_cache.items()}
            for chunk in sliced_chunks:
                h = get_hash(chunk)
                original = reverse_trans_cache.get(chunk, chunk)
                stressed = stress_cache.get(h, chunk)
                has_audio = os.path.exists(os.path.join(chunks_dir, f"{h}.wav"))
                
                paragraphs.append({
                    "hash": h,
                    "original": original,
                    "translated": chunk,
                    "stressed": stressed,
                    "has_audio": has_audio
                })
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error resolving chunks: {e}"}), 500
            
    # Detect EPUB availability and cache stats
    epub_path = find_book_epub(paths["book_dir"], slug)
    epub_available = epub_path is not None and os.path.exists(epub_path)

    # Count translated blocks from cache
    cache_size = len(trans_cache)
    is_epub_book = cfg.get("pdf_path", "") == "" and epub_available

    # Check epub_progress for live stats
    epub_progress = {}
    epub_progress_path = os.path.join(paths["cache_dir"], "epub_progress.json")
    if os.path.exists(epub_progress_path):
        try:
            with open(epub_progress_path, "r", encoding="utf-8") as f:
                epub_progress = json.load(f)
        except Exception:
            pass

    return jsonify({
        "status": "success",
        "tts_engine": tts_engine,
        "paragraphs": paragraphs,
        "total_chunks": total_chunks,
        "total_pages": total_pages,
        "page": page,
        "limit": limit,
        "epub_available": epub_available,
        "is_epub_book": is_epub_book,
        "cache_stats": {
            "translated_blocks": cache_size,
            "current_file": epub_progress.get("current_file", 0),
            "total_files": epub_progress.get("total_files", 0),
            "percent": epub_progress.get("percent", 0),
            "completed_blocks": epub_progress.get("completed_blocks", 0),
            "total_blocks": epub_progress.get("total_blocks", 0)
        }
    })

def _tts_voice_slug_and_model(paths, repo_dir):
    tts_engine = paths.get("tts_engine", "supertonic3")
    if tts_engine == "styletts2":
        return "styletts2", os.path.join(repo_dir, "models", "styletts2", "model.onnx")
    return "supertonic-3-tts-int8", ""

# -------------------------------------------------------------
# POINT-EDIT ROUTES (text/audio) — see EDIT_METHODOLOGY_kindle-butch-gen.md
# Non-destructive overlay via edit_store.py. Approve is the only step that
# touches generated artifacts (translate_cache/merged markdown/batch files).
# No automatic full-book re-pass — see TASK-17 for why that was removed.
# -------------------------------------------------------------

@app.route("/api/edit/text/<slug>/<chunk_hash>", methods=["PUT"])
@auth.login_required
def edit_text(slug, chunk_hash):
    if not validate_slug(slug) or not re.match(r"^[a-f0-9]{64}$", chunk_hash):
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    data = request.get_json() or {}
    original_text = data.get("original_text", "")
    new_text = data.get("new_text", "").strip()
    if not original_text or not new_text:
        return jsonify({"status": "error", "message": "original_text and new_text are required"}), 400

    import hashlib
    if hashlib.sha256(original_text.encode("utf-8")).hexdigest() != chunk_hash:
        return jsonify({"status": "error", "message": "original_text does not match chunk_hash — data is stale, refresh and retry"}), 409

    edit = edit_store.add_edit(slug, mode="text", target_id=chunk_hash, field="translated_text",
                                original_value=original_text, edited_value=new_text)
    return jsonify({"status": "success", "edit": edit})

@app.route("/api/edit/stress/<slug>/<chunk_hash>", methods=["PUT"])
@auth.login_required
def edit_stress(slug, chunk_hash):
    if not validate_slug(slug) or not re.match(r"^[a-f0-9]{64}$", chunk_hash):
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    data = request.get_json() or {}
    original_stress = data.get("original_stress", "")
    new_stress = data.get("new_stress", "").strip()
    if not new_stress:
        return jsonify({"status": "error", "message": "new_stress is required"}), 400

    edit = edit_store.add_edit(slug, mode="stress", target_id=chunk_hash, field="stress",
                                original_value=original_stress, edited_value=new_stress)
    return jsonify({"status": "success", "edit": edit})

@app.route("/api/edit/queue/<slug>")
@auth.login_required
def edit_queue(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
    mode = request.args.get("mode")
    status = request.args.get("status")
    return jsonify(edit_store.list_edits(slug, mode=mode, status=status))

@app.route("/api/edit/regenerate-audio/<slug>/<chunk_hash>", methods=["POST"])
@auth.login_required
def edit_regenerate_audio(slug, chunk_hash):
    if not validate_slug(slug) or not re.match(r"^[a-f0-9]{64}$", chunk_hash):
        return jsonify({"status": "error", "message": "Invalid parameters"}), 400

    paths = resolve_book_paths(repo_dir, slug)
    if not os.path.exists(paths["config_path"]):
        return jsonify({"status": "error", "message": "Book not found"}), 404

    pending = edit_store.list_edits(slug, status="pending")
    stress_edit = next((e for e in pending if e["target_id"] == chunk_hash and e["mode"] == "stress"), None)
    text_edit = next((e for e in pending if e["target_id"] == chunk_hash and e["mode"] == "text"), None)

    if stress_edit:
        # Already manually stress-marked by the user — synthesize as-is.
        tts_text = stress_edit["edited_value"]
        source_edit = stress_edit
    elif text_edit:
        tts_text = text_edit["edited_value"]
        source_edit = text_edit
        target_lang = paths.get("target_lang", "uk")
        if target_lang == "uk":
            try:
                cmd_stress = [
                    "proot-distro", "login", "ubuntu", "--",
                    "python3", "/data/data/com.termux/files/home/kindle-butch-gen/bin/stressify_batch.py",
                    "--inline", tts_text
                ]
                res_stress = subprocess.run(cmd_stress, capture_output=True, text=True, timeout=15)
                if res_stress.returncode == 0 and res_stress.stdout.strip():
                    tts_text = res_stress.stdout.strip()
            except Exception as e:
                print(f"Warning: inline stressifier failed during regenerate-audio: {e}", file=sys.stderr)
    else:
        return jsonify({"status": "error", "message": "No pending edit found for this chunk — save an edit first"}), 400

    import hashlib
    new_hash = hashlib.sha256(tts_text.encode("utf-8")).hexdigest()

    voice_slug, model_path = _tts_voice_slug_and_model(paths, repo_dir)
    chunks_dir = os.path.join(paths["audio_dir"], f"chunks_{voice_slug}")
    cache_path = os.path.join(paths["cache_dir"], f"tts_cache_{voice_slug}.json")
    os.makedirs(chunks_dir, exist_ok=True)
    os.makedirs(paths["cache_dir"], exist_ok=True)

    # TASK-23: don't fire a second tts_helper.py (a second loaded TTS model)
    # if audio_stage.py is already running for this book — its own
    # tts_helper.py loop checks this file between chunks and picks new
    # entries up using the already-loaded model instead.
    if is_book_process_running(slug):
        audio_priority_path = os.path.join(paths["audio_dir"], f"audio_priority_{voice_slug}.json")
        os.makedirs(paths["audio_dir"], exist_ok=True)
        with file_lock(audio_priority_path, timeout=2.0):
            queued = []
            if os.path.exists(audio_priority_path):
                try:
                    with open(audio_priority_path, "r", encoding="utf-8") as f:
                        queued = json.load(f)
                except Exception:
                    queued = []
            if not any(q.get("hash") == new_hash for q in queued):
                queued.append({"hash": new_hash, "text": tts_text, "edit_id": source_edit["id"]})
            with open(audio_priority_path, "w", encoding="utf-8") as f:
                json.dump(queued, f, ensure_ascii=False, indent=2)
        return jsonify({
            "status": "queued",
            "message": "Generation is currently in progress for this book - your edit is saved and will be synthesized automatically."
        })

    payload = {
        "tts_engine": paths.get("tts_engine", "supertonic3"),
        "model_path": model_path,
        "output_dir": os.path.abspath(chunks_dir),
        "cache_path": os.path.abspath(cache_path),
        "chunks": [{"hash": new_hash, "text": tts_text}],
        "speaker_id": paths.get("tts_speaker_id", 2),
        "speed": paths.get("tts_speed", 1.0),
        "noise_scale": paths.get("tts_noise_scale", 0.667),
        "noise_w": paths.get("tts_noise_w", 0.8),
        "lang": paths.get("target_lang", "uk")
    }
    helper_path = "/data/data/com.termux/files/home/kindle-butch-gen/bin/tts_helper.py"
    res = subprocess.run([sys.executable, helper_path], input=json.dumps(payload, ensure_ascii=False),
                          capture_output=True, text=True)
    if res.returncode != 0:
        return jsonify({"status": "error", "message": f"Synthesis failed: {res.stderr}"}), 500

    new_wav_path = os.path.join(chunks_dir, f"{new_hash}.wav")
    if not os.path.exists(new_wav_path):
        return jsonify({"status": "error", "message": "Synthesis reported success but no wav file was produced"}), 500

    edit_store.mark_status(slug, source_edit["id"], "regenerated")
    return jsonify({"status": "success", "new_hash": new_hash})

@app.route("/api/edit/approve/<slug>/<edit_id>", methods=["POST"])
@auth.login_required
def edit_approve(slug, edit_id):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400

    paths = resolve_book_paths(repo_dir, slug)
    edit = edit_store.get_edit(slug, edit_id)
    if not edit:
        return jsonify({"status": "error", "message": "Edit not found"}), 404
    if edit["status"] == "approved":
        return jsonify({"status": "error", "message": "Edit already approved"}), 400

    if edit["mode"] == "stress":
        target_lang = paths.get("target_lang", "uk")
        stress_cache_path = os.path.join(paths["book_dir"], "translated", f"stress_cache_{target_lang}.json")
        stress_cache = {}
        if os.path.exists(stress_cache_path):
            try:
                with open(stress_cache_path, "r", encoding="utf-8") as f:
                    stress_cache = json.load(f)
            except Exception:
                pass
        stress_cache[edit["target_id"]] = edit["edited_value"]
        os.makedirs(os.path.dirname(stress_cache_path), exist_ok=True)
        with open(stress_cache_path, "w", encoding="utf-8") as f:
            json.dump(stress_cache, f, ensure_ascii=False, indent=2)

    elif edit["mode"] == "text":
        old_text = edit["original_value"]
        new_text = edit["edited_value"]

        # 1. translate_cache.json — keyed by hash of the ORIGINAL SOURCE
        # (RU/EN) segment, not the translated chunk, so we can't look it up
        # by re-hashing old_text. Segments (translate_stage.py, ~1200 chars)
        # and TTS chunks (~150-1000 chars) are also different granularities,
        # so a chunk isn't guaranteed to equal a full cached segment value.
        # Best-effort: patch by exact value match if found; if not, skip —
        # this only affects a full re-translate (rare, opt-in), not what's
        # actually served (steps 2/3 below cover that).
        if os.path.exists(paths["translate_cache"]):
            try:
                with open(paths["translate_cache"], "r", encoding="utf-8") as f:
                    trans_cache = json.load(f)
            except Exception:
                trans_cache = {}
        else:
            trans_cache = {}
        cache_patched = False
        for seg_hash, seg_translation in trans_cache.items():
            if seg_translation == old_text:
                trans_cache[seg_hash] = new_text
                cache_patched = True
                break
        if cache_patched:
            os.makedirs(paths["cache_dir"], exist_ok=True)
            with open(paths["translate_cache"], "w", encoding="utf-8") as f:
                json.dump(trans_cache, f, ensure_ascii=False, indent=2)

        # 2. merged_translated_<lang>.md — the canonical file everything
        # (preview, audio_stage.py, ebook-convert on the no-PDF resume path)
        # reads from. Reconstruct via the exact same chunking the preview
        # endpoint uses rather than a blind substring replace on raw markdown.
        target_lang = paths.get("target_lang", "uk")
        source_lang = paths.get("source_lang", "ru")
        suffix = f"_translated_{target_lang}" if (target_lang != source_lang) else ""
        if suffix:
            target_md_file = os.path.join(paths["translated_dir"], f"merged_translated_{target_lang}.md")
        else:
            target_md_file = os.path.join(paths["translated_dir"], f"merged_source_{source_lang}.md")
        merged_patched = False
        if os.path.exists(target_md_file):
            with open(target_md_file, "r", encoding="utf-8") as f:
                content = f.read()
            if old_text in content:
                content = content.replace(old_text, new_text, 1)
                with open(target_md_file, "w", encoding="utf-8") as f:
                    f.write(content)
                merged_patched = True

        # 3. Per-batch translated markdown files — books that still have
        # their source PDF get merged_translated_<lang>.md unconditionally
        # rebuilt from these on the next conversion run, which would
        # silently discard step 2's patch otherwise. Locked (TASK-23):
        # the main pipeline may still be writing other batch files
        # concurrently if this book is still status=running.
        batch_patched = patch_batch_translation(paths["batches_dir"], suffix, old_text, new_text)

        if not merged_patched and not batch_patched:
            return jsonify({"status": "error", "message": "Could not locate the original text in merged markdown or any batch file — approve aborted, nothing was changed"}), 500

    # mode == "manga" intentionally falls through with no file mutation
    # here: regenerate-manga-page already bakes the edit into the actual
    # page image (a manga edit only affects pixels, unlike text/stress
    # which patch a shared cache/markdown file), so approving one is just
    # a reviewer confirming the regenerated result, not a data write.

    edit_store.mark_status(slug, edit_id, "approved", applied_at=datetime.now().isoformat())
    return jsonify({"status": "success"})

@app.route("/api/edit/discard/<slug>/<edit_id>", methods=["POST"])
@auth.login_required
def edit_discard(slug, edit_id):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
    edit = edit_store.get_edit(slug, edit_id)
    if not edit:
        return jsonify({"status": "error", "message": "Edit not found"}), 404
    edit_store.mark_status(slug, edit_id, "discarded")
    return jsonify({"status": "success"})

@app.route("/api/edit/manga-text/<slug>/<page_filename>", methods=["PUT"])
@auth.login_required
def edit_manga_text(slug, page_filename):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400

    data = request.get_json() or {}
    bubble_id = data.get("bubble_id", "").strip()
    new_text = data.get("translated_text", "").strip()
    if not bubble_id or not new_text:
        return jsonify({"status": "error", "message": "bubble_id and translated_text are required"}), 400

    page_filename = os.path.basename(page_filename)
    page_stem = os.path.splitext(page_filename)[0]
    paths = resolve_book_paths(repo_dir, slug)
    meta_path = os.path.join(paths["book_dir"], "bubbles_meta", f"{page_stem}.json")
    if not os.path.exists(meta_path):
        return jsonify({"status": "error", "message": "Page not processed yet - no bubble metadata found"}), 404

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            bubbles = json.load(f)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to read bubble metadata: {e}"}), 500

    bubble = next((b for b in bubbles if b["id"] == bubble_id), None)
    if not bubble:
        return jsonify({"status": "error", "message": f"Bubble '{bubble_id}' not found on this page"}), 404

    edit = edit_store.add_edit(slug, mode="manga", target_id=f"{page_filename}#{bubble_id}",
                                field="translated_text", original_value=bubble["translated_text"],
                                edited_value=new_text)
    return jsonify({"status": "success", "edit": edit})

@app.route("/api/edit/manga-bbox/<slug>/<page_filename>", methods=["PUT"])
@auth.login_required
def edit_manga_bbox(slug, page_filename):
    # TASK-36: manual geometry/font-size override, independent of and
    # separate-Save-button from edit_manga_text above - a human can fix
    # only the box, only the font size, or both, without touching the
    # translated text itself.
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400

    data = request.get_json() or {}
    bubble_id = data.get("bubble_id", "").strip()
    bbox = data.get("bbox")
    ref_size = data.get("ref_size")
    font_size = data.get("font_size")

    if not bubble_id:
        return jsonify({"status": "error", "message": "bubble_id is required"}), 400
    if bbox is None and font_size is None:
        return jsonify({"status": "error", "message": "at least one of bbox or font_size is required"}), 400

    if bbox is not None:
        if not (isinstance(bbox, list) and len(bbox) == 4 and all(isinstance(v, (int, float)) for v in bbox)):
            return jsonify({"status": "error", "message": "bbox must be [x1, y1, x2, y2]"}), 400
        if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            return jsonify({"status": "error", "message": "bbox must have positive width and height"}), 400
        if not (isinstance(ref_size, list) and len(ref_size) == 2 and all(isinstance(v, (int, float)) for v in ref_size)):
            return jsonify({"status": "error", "message": "ref_size ([w, h]) is required when bbox is set"}), 400

    if font_size is not None:
        try:
            font_size = int(font_size)
        except (TypeError, ValueError):
            return jsonify({"status": "error", "message": "font_size must be an integer"}), 400
        if font_size < 8 or font_size > 200:
            return jsonify({"status": "error", "message": "font_size out of range (8-200)"}), 400

    page_filename = os.path.basename(page_filename)
    page_stem = os.path.splitext(page_filename)[0]
    paths = resolve_book_paths(repo_dir, slug)
    meta_path = os.path.join(paths["book_dir"], "bubbles_meta", f"{page_stem}.json")
    if not os.path.exists(meta_path):
        return jsonify({"status": "error", "message": "Page not processed yet - no bubble metadata found"}), 404

    try:
        with open(meta_path, "r", encoding="utf-8") as f:
            bubbles = json.load(f)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to read bubble metadata: {e}"}), 500

    bubble = next((b for b in bubbles if b["id"] == bubble_id), None)
    if not bubble:
        return jsonify({"status": "error", "message": f"Bubble '{bubble_id}' not found on this page"}), 404

    original_value = {"bbox": bubble.get("bbox"), "ref_size": bubble.get("bbox_ref_size")}
    edited_value = {}
    if bbox is not None:
        edited_value["bbox"] = [int(v) for v in bbox]
        edited_value["ref_size"] = [int(v) for v in ref_size]
    if font_size is not None:
        edited_value["font_size"] = font_size

    edit = edit_store.add_edit(slug, mode="manga", target_id=f"{page_filename}#{bubble_id}",
                                field="manual_bbox_override", original_value=original_value,
                                edited_value=edited_value)
    return jsonify({"status": "success", "edit": edit})

@app.route("/api/edit/regenerate-manga-page/<slug>/<page_filename>", methods=["POST"])
@auth.login_required
def edit_regenerate_manga_page(slug, page_filename):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400

    page_filename = os.path.basename(page_filename)
    paths = resolve_book_paths(repo_dir, slug)
    config_path = paths["config_path"]
    if not os.path.exists(config_path):
        return jsonify({"status": "error", "message": "Book not found"}), 404
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    if not cfg.get("is_manga", False):
        return jsonify({"status": "error", "message": "Not a manga"}), 400

    # TASK-23: don't fire a second translate_manga.py process (same GPU/OCR/
    # LLM resources) if the main pipeline is still running for this book -
    # main()'s own per-page loop now checks pending edits at each page
    # boundary and will pick this one up automatically.
    if is_book_process_running(slug):
        return jsonify({
            "status": "queued",
            "message": "Generation is currently in progress for this book - your edit is saved and will be applied automatically as the pipeline reaches this page."
        })

    # Same source resolution run_conversion_api already uses for the full
    # manga run - --regenerate-page re-extracts from this same source, so
    # directory/CBZ/PDF sources all work uniformly with no special-casing.
    manga_input = ""
    if os.path.isdir(os.path.join(paths["book_dir"], "source")):
        manga_input = os.path.join(paths["book_dir"], "source")
    else:
        for possible_ext in [".cbz", ".cbr", ".cb7", ".zip", ".rar", ".pdf", ".epub"]:
            if os.path.exists(os.path.join(paths["book_dir"], f"{slug}{possible_ext}")):
                manga_input = os.path.join(paths["book_dir"], f"{slug}{possible_ext}")
                break
    if not manga_input:
        return jsonify({"status": "error", "message": "Manga source file or directory not found"}), 400

    target_lang = cfg.get("target_lang", "uk")
    manga_output = os.path.join(paths["book_dir"], "output", f"{slug}_translated_{target_lang}.cbz")

    prefix = f"{page_filename}#"
    page_edits = [e for e in edit_store.list_edits(slug, mode="manga") if e["target_id"].startswith(prefix)]
    pending = [e for e in page_edits if e.get("status") == "pending"]
    if not pending:
        return jsonify({"status": "error", "message": "No pending edits for this page - nothing to regenerate"}), 400

    # Bug found live during TASK-36 testing: process_page() re-runs the
    # WHOLE page from scratch on every regen (fresh OCR + fresh LLM
    # translation), so an edit that's already "regenerated" from a PAST
    # run is invisible to a LATER regen triggered for an unrelated reason
    # (e.g. a geometry-only fix on a different bubble) unless it's
    # included again here too - otherwise it silently reverts to a fresh
    # (and possibly different) auto-translation. "regenerated" edits are
    # therefore included in the override set on every future regen of
    # this page, not just the run they were first created in - the
    # pending-only check above still gates WHETHER a regen even happens
    # (so clicking Regenerate on a page with zero new edits does nothing),
    # but once triggered, every previously-confirmed fix for this page
    # rides along. "orphaned"/"discarded" edits are excluded - they no
    # longer correspond to anything meaningful to reapply.
    to_apply = [e for e in page_edits if e.get("status") in ("pending", "regenerated")]

    page_stem = os.path.splitext(page_filename)[0]
    meta_path = os.path.join(paths["book_dir"], "bubbles_meta", f"{page_stem}.json")
    bubbles_by_id = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                bubbles_by_id = {b["id"]: b for b in json.load(f)}
        except Exception:
            bubbles_by_id = {}

    overrides = {}
    bbox_overrides = {}
    for e in to_apply:
        bubble_id = e["target_id"].split("#", 1)[1]
        bubble = bubbles_by_id.get(bubble_id)
        if not bubble:
            continue
        orig_text = bubble["original_text"]
        if e.get("field") == "translated_text":
            overrides[orig_text] = e["edited_value"]
        elif e.get("field") == "manual_bbox_override":
            # TASK-36: bbox/font_size overrides are captured by the client
            # against whatever image dimensions were on screen at edit
            # time (ref_size) - kept UNSCALED here and scaled later inside
            # translate_manga.py once the actual regen's working image
            # dimensions are known (same reference-scaling approach TASK-27
            # established), not here where that size isn't available yet.
            ev = e.get("edited_value") or {}
            entry = bbox_overrides.setdefault(orig_text, {})
            if "bbox" in ev and "ref_size" in ev:
                entry["bbox"] = ev["bbox"]
                entry["ref_size"] = ev["ref_size"]
            if "font_size" in ev:
                entry["font_size"] = ev["font_size"]
                entry.setdefault("ref_size", ev.get("ref_size"))

    overrides_path = os.path.join(paths["cache_dir"], f"manga_regen_overrides_{page_stem}.json")
    bbox_overrides_path = os.path.join(paths["cache_dir"], f"manga_regen_bbox_overrides_{page_stem}.json")
    os.makedirs(paths["cache_dir"], exist_ok=True)
    with open(overrides_path, "w", encoding="utf-8") as f:
        json.dump(overrides, f, ensure_ascii=False)
    with open(bbox_overrides_path, "w", encoding="utf-8") as f:
        json.dump(bbox_overrides, f, ensure_ascii=False)

    cmd = [
        "proot-distro", "login", "ubuntu", "--",
        "python3", "-u", "/data/data/com.termux/files/home/kindle-butch-gen/translate_manga.py",
        "--input", manga_input,
        "--output", manga_output,
        "--lang", cfg.get("source_lang", "en"),
        "--regenerate-page", page_filename,
        "--overrides-json", overrides_path,
        "--bbox-overrides-json", bbox_overrides_path
    ]
    glossary_path = os.path.join(paths["book_dir"], "glossary.json")
    if os.path.exists(glossary_path):
        cmd.extend(["--glossary", glossary_path])

    try:
        # Single-page regen (detector init + a few OCR/LLM calls) is fast
        # enough to run synchronously - the UI shows a spinner rather than
        # needing a background-job+poll flow, per the doc's own framing.
        #
        # start_new_session=True (setsid) puts the whole proot -> bash ->
        # python3 chain in its own process group, so a timeout can kill the
        # ENTIRE tree via os.killpg. Plain subprocess.run(..., timeout=...)'s
        # default TimeoutExpired handling only kills the direct child (the
        # proot wrapper itself) - confirmed live during TASK-36 testing that
        # this left the python3 translate_manga.py process it exec'd running
        # ORPHANED inside proot-distro for several more minutes after Flask
        # (and the client) had already given up, wasting phone battery/CPU
        # with nothing watching it. It happened to complete correctly on its
        # own both times this was observed, but that was luck, not a
        # guarantee - a truly hung regen would run forever unmonitored.
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
        try:
            stdout, stderr = proc.communicate(timeout=180)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.communicate()  # reap the now-killed process, avoid a zombie
            raise
        res = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Regeneration timed out after 180s"}), 500
    finally:
        try:
            os.remove(overrides_path)
        except Exception:
            pass
        try:
            os.remove(bbox_overrides_path)
        except Exception:
            pass

    if res.returncode != 0:
        return jsonify({"status": "error", "message": f"Regeneration failed: {res.stderr[-2000:]}"}), 500

    # translate_manga.py prints exactly one JSON line to stdout on success.
    result_line = None
    for line in res.stdout.strip().splitlines():
        line = line.strip()
        if line.startswith("{"):
            result_line = line
    if not result_line:
        return jsonify({"status": "error", "message": f"Regeneration completed but produced no result JSON: {res.stdout[-1000:]}"}), 500

    try:
        result = json.loads(result_line)
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to parse regeneration result: {e}"}), 500

    if result.get("status") != "success":
        return jsonify({"status": "error", "message": result.get("message", "Regeneration failed")}), 500

    id_mapping = result.get("bubble_id_mapping", {})
    now = datetime.now().isoformat()
    for e in to_apply:
        old_bubble_id = e["target_id"].split("#", 1)[1]
        new_bubble_id = id_mapping.get(old_bubble_id)
        if new_bubble_id is not None:
            # Re-marking an already-"regenerated" edit here too (fresh
            # applied_at) - it just rode along in this regen, still
            # correctly applied, timestamp reflects the latest confirmation.
            edit_store.mark_status(slug, e["id"], "regenerated", applied_at=now)
        else:
            # The bubble this edit targeted has no confident IoU match in
            # the fresh detection - don't silently drop the edit, surface
            # it for a human to resolve.
            edit_store.mark_status(slug, e["id"], "orphaned")

    return jsonify({"status": "success", "bubbles": result.get("bubbles", []), "bubble_id_mapping": id_mapping})

def find_book_epub(book_dir, slug):
    import os
    import glob
    candidate = os.path.join(book_dir, f"{slug}.epub")
    if os.path.exists(candidate):
        return candidate
    epubs = glob.glob(os.path.join(book_dir, "*.epub"))
    if epubs:
        return epubs[0]
    epubs_input = glob.glob(os.path.join(book_dir, "input", "*.epub"))
    if epubs_input:
        return epubs_input[0]
    epubs_output = glob.glob(os.path.join(book_dir, "output", "*.epub"))
    if epubs_output:
        return epubs_output[0]
    return None

@app.route("/api/preview/book-chapters/<slug>")
@auth.login_required
def preview_book_chapters(slug):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
        
    import zipfile
    import xml.etree.ElementTree as ET
    
    paths = resolve_book_paths(repo_dir, slug)
    epub_path = find_book_epub(paths["book_dir"], slug)
    if not epub_path or not os.path.exists(epub_path):
        return jsonify({"status": "error", "message": f"EPUB file not found for book '{slug}'"}), 404
        
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            container_data = z.read("META-INF/container.xml")
            root = ET.fromstring(container_data)
            root_file_el = root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            if root_file_el is None:
                root_file_el = root.find(".//rootfile")
            if root_file_el is None:
                return jsonify({"status": "error", "message": "rootfile not found in container.xml"}), 400
            opf_rel_path = root_file_el.attrib["full-path"]
            opf_dir = os.path.dirname(opf_rel_path)
            
            opf_data = z.read(opf_rel_path)
            opf_root = ET.fromstring(opf_data)
            
            manifest_el = opf_root.find(".//{http://www.idpf.org/2007/opf}manifest")
            if manifest_el is None:
                manifest_el = opf_root.find(".//manifest")
            if manifest_el is None:
                return jsonify({"status": "error", "message": "manifest not found in OPF"}), 400
                
            chapters = []
            for item in manifest_el.findall(".//{http://www.idpf.org/2007/opf}item"):
                href = item.attrib.get("href")
                media_type = item.attrib.get("media-type", "")
                if href and media_type in ["application/xhtml+xml", "text/html"]:
                    chapters.append({
                        "href": href,
                        "id": item.attrib.get("id", "")
                    })
            return jsonify({
                "status": "success",
                "chapters": chapters,
                "opf_dir": opf_dir
            })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Failed to read EPUB chapters: {e}"}), 500

@app.route("/api/preview/book-page/<slug>/<path:href>")
@auth.login_required
def preview_book_page(slug, href):
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug"}), 400
        
    import os
    import json
    import zipfile
    import hashlib
    import re
    import xml.etree.ElementTree as ET
    from common.epub_validate import sanitize_xhtml_for_xml_parser
    
    paths = resolve_book_paths(repo_dir, slug)
    epub_path = find_book_epub(paths["book_dir"], slug)
    if not epub_path or not os.path.exists(epub_path):
        return jsonify({"status": "error", "message": "EPUB file not found"}), 404
        
    # Serve binary assets (images, css) directly from EPUB
    lower_href = href.lower()
    if lower_href.endswith(('.jpg', '.jpeg', '.png', '.gif', '.svg', '.css')):
        try:
            with zipfile.ZipFile(epub_path, 'r') as z:
                container_data = z.read("META-INF/container.xml")
                c_root = ET.fromstring(container_data)
                rf_el = c_root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
                if rf_el is None:
                    rf_el = c_root.find(".//rootfile")
                opf_rel_path = rf_el.attrib["full-path"]
                opf_dir = os.path.dirname(opf_rel_path)
                
                full_rel_path = os.path.join(opf_dir, href) if opf_dir else href
                full_rel_path = full_rel_path.replace("\\", "/")
                
                raw_bytes = z.read(full_rel_path)
                
                content_type = "application/octet-stream"
                if lower_href.endswith(('.jpg', '.jpeg')):
                    content_type = "image/jpeg"
                elif lower_href.endswith('.png'):
                    content_type = "image/png"
                elif lower_href.endswith('.gif'):
                    content_type = "image/gif"
                elif lower_href.endswith('.svg'):
                    content_type = "image/svg+xml"
                elif lower_href.endswith('.css'):
                    content_type = "text/css"
                
                from flask import Response
                return Response(raw_bytes, mimetype=content_type)
        except Exception as e:
            return jsonify({"status": "error", "message": str(e)}), 404

    opf_dir = ""
    try:
        with zipfile.ZipFile(epub_path, 'r') as z:
            container_data = z.read("META-INF/container.xml")
            c_root = ET.fromstring(container_data)
            rf_el = c_root.find(".//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile")
            if rf_el is None:
                rf_el = c_root.find(".//rootfile")
            opf_rel_path = rf_el.attrib["full-path"]
            opf_dir = os.path.dirname(opf_rel_path)
            
            full_rel_path = os.path.join(opf_dir, href) if opf_dir else href
            full_rel_path = full_rel_path.replace("\\", "/")
            
            try:
                raw_bytes = z.read(full_rel_path)
            except KeyError:
                return jsonify({"status": "error", "message": f"File {full_rel_path} not found in EPUB"}), 404
                
        sanitized = sanitize_xhtml_for_xml_parser(raw_bytes)
        ET.register_namespace('', 'http://www.w3.org/1999/xhtml')
        
        cache = {}
        if os.path.exists(paths["translate_cache"]):
            try:
                with open(paths["translate_cache"], "r", encoding="utf-8") as cf:
                    cache = json.load(cf)
            except Exception:
                pass
                
        orig_root = ET.fromstring(sanitized.encode('utf-8'))
        trans_root = ET.fromstring(sanitized.encode('utf-8'))
        
        block_tags = [
            "{http://www.w3.org/1999/xhtml}p", "{http://www.w3.org/1999/xhtml}li",
            "{http://www.w3.org/1999/xhtml}h1", "{http://www.w3.org/1999/xhtml}h2",
            "{http://www.w3.org/1999/xhtml}h3", "{http://www.w3.org/1999/xhtml}h4",
            "{http://www.w3.org/1999/xhtml}h5", "{http://www.w3.org/1999/xhtml}h6",
            "{http://www.w3.org/1999/xhtml}blockquote", "{http://www.w3.org/1999/xhtml}td",
            "{http://www.w3.org/1999/xhtml}th",
            "p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "td", "th"
        ]
        
        for el in trans_root.iter():
            if el.tag in block_tags:
                text = el.text or ''
                children_str = ''.join(ET.tostring(child, encoding='utf-8').decode('utf-8') for child in el)
                inner_xml = text + children_str
                
                if not inner_xml.strip():
                    continue
                    
                h = hashlib.sha256(inner_xml.encode('utf-8')).hexdigest()
                if h in cache:
                    translated_inner_xml = cache[h]
                    dummy_xml = f'<div xmlns="http://www.w3.org/1999/xhtml">{translated_inner_xml}</div>'
                    try:
                        sanitized_dummy = sanitize_xhtml_for_xml_parser(dummy_xml.encode('utf-8'))
                        dummy_root = ET.fromstring(sanitized_dummy.encode('utf-8'))
                        el.text = None
                        el.tail = None
                        for child in list(el):
                            el.remove(child)
                        el.text = dummy_root.text
                        for child in dummy_root:
                            el.append(child)
                    except Exception:
                        plain_text = re.sub(r'<[^>]+>', '', translated_inner_xml)
                        el.text = None
                        el.tail = None
                        for child in list(el):
                            el.remove(child)
                        el.text = plain_text
                else:
                    existing_class = el.attrib.get("class", "")
                    el.attrib["class"] = (existing_class + " untranslated-block").strip()
                    
        orig_html = ET.tostring(orig_root, encoding='utf-8').decode('utf-8')
        trans_html = ET.tostring(trans_root, encoding='utf-8').decode('utf-8')
        
        style_inject = """
        <style>
            body {
                background-color: #09090b !important;
                color: #f4f4f5 !important;
                font-family: 'Outfit', system-ui, -apple-system, sans-serif !important;
                line-height: 1.65 !important;
                padding: 1.5rem !important;
                margin: 0 !important;
                font-size: 1.05rem !important;
            }
            p, li {
                margin-bottom: 1.2rem !important;
            }
            h1, h2, h3, h4, h5, h6 {
                color: #a78bfa !important;
                margin-top: 1.6rem !important;
                margin-bottom: 0.8rem !important;
                font-weight: 600 !important;
            }
            .untranslated-block {
                color: #71717a !important;
                border-left: 2px solid #d97706 !important;
                padding-left: 10px !important;
                background-color: rgba(217, 119, 6, 0.04) !important;
                border-radius: 0 4px 4px 0 !important;
            }
        </style>
        """
        
        base_tag = f'<base href="/api/preview/book-page/{slug}/{opf_dir}/" />' if opf_dir else f'<base href="/api/preview/book-page/{slug}/" />'
        style_inject_with_base = f"\n        {base_tag}\n" + style_inject
        
        def inject_style(html_str):
            if "</head>" in html_str:
                return html_str.replace("</head>", f"{style_inject_with_base}</head>")
            elif "<body>" in html_str:
                return html_str.replace("<body>", f"<body>{style_inject_with_base}")
            else:
                return style_inject_with_base + html_str
                
        orig_html = inject_style(orig_html)
        trans_html = inject_style(trans_html)
        
        def clean_prefixes(html_str):
            import re
            # Replace tags like <ns1:svg -> <svg, </ns1:svg -> </svg
            html_str = re.sub(r'</?ns\d+:', lambda m: '</' if m.group().startswith('</') else '<', html_str)
            # Replace attributes like ns2:href -> xlink:href or href
            html_str = re.sub(r'\bns\d+:href\b', 'xlink:href', html_str)
            # Remove namespace declarations for ns1, ns2
            html_str = re.sub(r'\s*xmlns:ns\d+=\"[^\"]*\"', '', html_str)
            return html_str
            
        orig_html = clean_prefixes(orig_html)
        trans_html = clean_prefixes(trans_html)
        
        return jsonify({
            "status": "success",
            "original_html": orig_html,
            "translated_html": trans_html
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error loading book page: {e}"}), 500

@app.route("/downloads")
@auth.login_required
def downloads_page():
    return render_template("downloads.html")

@app.route("/api/downloads")
@auth.login_required
def api_all_downloads():
    import os
    import json
    all_files = []
    books_dir = os.path.join(repo_dir, "books")
    if not os.path.exists(books_dir):
        return jsonify([])
        
    for entry in os.listdir(books_dir):
        entry_path = os.path.join(books_dir, entry)
        if not os.path.isdir(entry_path) or entry.startswith('.'):
            continue
            
        config_path = os.path.join(entry_path, "config.json")
        title = entry
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    title = cfg.get("title", entry)
            except Exception:
                pass
                
        output_dir = os.path.join(entry_path, "output")
        if os.path.exists(output_dir):
            for f in os.listdir(output_dir):
                if f.endswith((".epub", ".azw3", ".mp3", ".md", ".cbz", ".cbr", ".cb7", ".zip")):
                    fpath = os.path.join(output_dir, f)
                    if os.path.isfile(fpath):
                        size_bytes = os.path.getsize(fpath)
                        if size_bytes >= 1024*1024:
                            size_str = f"{size_bytes / (1024*1024):.1f} MB"
                        else:
                            size_str = f"{size_bytes / 1024:.1f} KB"
                            
                        desc = "Скомпільований файл проекту."
                        target = "Будь-який пристрій"
                        fname_lower = f.lower()
                        
                        if fname_lower.endswith(".azw3"):
                            target = "Amazon Kindle"
                            if "translated" in fname_lower:
                                desc = "Перекладена книга/манга у форматі AZW3. Оптимізовано для рідерів Amazon Kindle (включаючи Paperwhite, Oasis, Scribe та Basic)."
                            else:
                                desc = "Книга/манга у форматі AZW3. Готова до завантаження на рідер Kindle."
                        elif fname_lower.endswith(".cbz"):
                            target = "Комікс-рідери / Планшети"
                            desc = "Перекладений комікс-архів (CBZ) з оригінальним роздільним дозволом. Підходить для перегляду на комп'ютерах, планшетах чи сторонніх читалках."
                        elif fname_lower.endswith(".epub"):
                            target = "Kobo, PocketBook, Apple Books, Android"
                            desc = "Перекладена електронна книга у стандартному форматі EPUB. Підходить для будь-яких пристроїв читання (окрім старих Kindle)."
                        elif fname_lower.endswith(".mp3"):
                            target = "Будь-який аудіоплеєр / Смартфон"
                            desc = "Синтезована аудіокнига у форматі MP3. Високоякісне озвучування розділів."
                        elif fname_lower.endswith(".md"):
                            target = "Текстовий редактор / Obsidian"
                            desc = "Текстовий файл у форматі Markdown. Містить чистий перекладений текст або розділи книги."
                            
                        all_files.append({
                            "slug": entry,
                            "book_title": title,
                            "filename": f,
                            "size": size_str,
                            "target": target,
                            "description": desc,
                            "download_url": f"/api/download/{entry}/{f}"
                        })
                        
    return jsonify(all_files)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KBG Web Service Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the dashboard on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Run in Flask debug mode")
    args = parser.parse_args()
    
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)

