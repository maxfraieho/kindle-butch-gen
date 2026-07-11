import os
import sys
import re
import json
import subprocess
import shutil
from datetime import datetime
from flask import Flask, jsonify, request, render_template_string, send_file

# Resolve repository root
repo_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if repo_dir not in sys.path:
    sys.path.insert(0, repo_dir)

from common.book_paths import resolve_book_paths
from kbg_web.status_helper import calculate_progress, get_pdf_page_count

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

@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, post-check=0, pre-check=0, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '-1'
    return response

from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

auth = HTTPBasicAuth()

credentials_file = os.path.join(repo_dir, "web_credentials.json")
if os.path.exists(credentials_file):
    try:
        with open(credentials_file, "r") as f:
            users_data = json.load(f)
    except Exception:
        users_data = {"vokov": generate_password_hash("0523")}
else:
    users_data = {"vokov": generate_password_hash("0523")}
    try:
        with open(credentials_file, "w") as f:
            json.dump({"vokov": generate_password_hash("0523")}, f)
    except Exception:
        pass

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
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kindle Butch Gen - Dashboard</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #8b5cf6;
            --primary-hover: #7c3aed;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg-dark: #09090b;
            --card-bg: rgba(20, 20, 35, 0.65);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f4f4f5;
            --text-secondary: #a1a1aa;
        }

        * {
            box-sizing: border-box;
        }

        body {
            margin: 0;
            font-family: 'Outfit', sans-serif;
            background: radial-gradient(circle at top right, #1e1b4b, #09090b);
            background-attachment: fixed;
            color: var(--text-primary);
            min-height: 100vh;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }

        header {
            margin-bottom: 2.5rem;
            text-align: center;
        }

        header h1 {
            font-size: 2.5rem;
            font-weight: 700;
            margin: 0 0 0.5rem 0;
            background: linear-gradient(135deg, #a78bfa, #8b5cf6, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }

        header p {
            color: var(--text-secondary);
            font-size: 1.1rem;
            margin: 0;
        }

        .dashboard-grid {
            display: grid;
            grid-template-columns: 1fr 2fr;
            gap: 2rem;
        }

        @media (max-width: 900px) {
            .dashboard-grid {
                grid-template-columns: 1fr;
            }
        }

        .glass-card {
            background: var(--card-bg);
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            border: 1px solid var(--border-color);
            border-radius: 16px;
            padding: 1.75rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.4);
            transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .glass-card:hover {
            border-color: rgba(255, 255, 255, 0.15);
            box-shadow: 0 12px 40px 0 rgba(0, 0, 0, 0.5);
        }

        .card-title {
            font-size: 1.25rem;
            font-weight: 600;
            margin: 0 0 1.5rem 0;
            color: #fff;
            border-bottom: 1px solid rgba(255, 255, 255, 0.05);
            padding-bottom: 0.75rem;
        }

        /* Forms */
        .form-group {
            margin-bottom: 1.25rem;
        }

        .form-group label {
            display: block;
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin-bottom: 0.5rem;
            font-weight: 500;
        }

        .form-control {
            width: 100%;
            padding: 0.75rem 1rem;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #fff;
            font-family: inherit;
            font-size: 0.95rem;
            transition: all 0.2s ease;
        }

        .form-control:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(139, 92, 246, 0.25);
            background: rgba(0, 0, 0, 0.5);
        }

        /* Buttons */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            padding: 0.75rem 1.25rem;
            border-radius: 8px;
            font-family: inherit;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s ease;
            border: none;
            gap: 0.5rem;
        }

        .btn-primary {
            background: linear-gradient(135deg, #a78bfa, #8b5cf6);
            color: #fff;
        }

        .btn-primary:hover {
            background: linear-gradient(135deg, #c084fc, #7c3aed);
            transform: translateY(-1px);
        }

        .btn-success {
            background: var(--success);
            color: #fff;
        }

        .btn-success:hover {
            background: #059669;
        }

        .btn-danger {
            background: var(--danger);
            color: #fff;
        }

        .btn-danger:hover {
            background: #dc2626;
        }

        .btn-secondary {
            background: rgba(255, 255, 255, 0.08);
            color: var(--text-primary);
            border: 1px solid var(--border-color);
        }

        .btn-secondary:hover {
            background: rgba(255, 255, 255, 0.15);
        }

        .btn:active {
            transform: translateY(1px);
        }

        /* Book Grid & Cards */
        .books-container {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }

        .book-card {
            border: 1px solid rgba(255, 255, 255, 0.05);
            background: rgba(15, 15, 25, 0.4);
        }

        .book-header {
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            margin-bottom: 1rem;
        }

        .book-info h3 {
            font-size: 1.3rem;
            font-weight: 600;
            margin: 0;
            color: #fff;
        }

        .book-info p {
            font-size: 0.875rem;
            color: var(--text-secondary);
            margin: 0.25rem 0 0 0;
        }

        /* Badges */
        .badge {
            display: inline-flex;
            padding: 0.25rem 0.6rem;
            border-radius: 9999px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
        }

        .badge-running {
            background: rgba(139, 92, 246, 0.2);
            color: #c084fc;
            border: 1px solid rgba(139, 92, 246, 0.4);
            animation: pulse 2s infinite;
        }

        .badge-idle {
            background: rgba(255, 255, 255, 0.05);
            color: var(--text-secondary);
            border: 1px solid rgba(255, 255, 255, 0.1);
        }

        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.6; }
        }

        /* Progress Sections */
        .progress-section {
            margin: 1.25rem 0;
        }

        .progress-item {
            margin-bottom: 0.85rem;
        }

        .progress-label {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-bottom: 0.35rem;
        }

        .progress-bar-bg {
            width: 100%;
            height: 8px;
            background: rgba(255, 255, 255, 0.05);
            border-radius: 4px;
            overflow: hidden;
        }

        .progress-bar-fill {
            height: 100%;
            border-radius: 4px;
            transition: width 0.5s ease-out;
        }

        .fill-marker { background: #3b82f6; }
        .fill-translation { background: #8b5cf6; }
        .fill-edit { background: #ec4899; }
        .fill-stress { background: #f59e0b; }
        .fill-tts { background: #10b981; }

        /* Control Panel */
        .controls {
            display: flex;
            flex-wrap: wrap;
            gap: 0.75rem;
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        /* Options checkboxes */
        .options-group {
            display: flex;
            flex-wrap: wrap;
            gap: 1rem;
            margin-bottom: 1rem;
            background: rgba(0, 0, 0, 0.2);
            padding: 0.75rem;
            border-radius: 8px;
        }

        .option-checkbox {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.85rem;
            color: var(--text-secondary);
            cursor: pointer;
        }

        .option-checkbox input {
            cursor: pointer;
            accent-color: var(--primary);
        }

        /* Downloads */
        .downloads {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-top: 1rem;
        }

        .download-link {
            display: inline-flex;
            align-items: center;
            padding: 0.4rem 0.75rem;
            background: rgba(16, 185, 129, 0.1);
            border: 1px solid rgba(16, 185, 129, 0.2);
            border-radius: 6px;
            font-size: 0.8rem;
            color: #34d399;
            text-decoration: none;
            font-weight: 500;
            transition: all 0.2s ease;
        }

        .download-link:hover {
            background: rgba(16, 185, 129, 0.2);
            border-color: rgba(16, 185, 129, 0.4);
        }

        /* Terminal log */
        .terminal-card {
            grid-column: 1 / -1;
            margin-top: 1.5rem;
        }

        .terminal-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 1rem;
        }

        .terminal-indicator {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            font-size: 0.875rem;
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: var(--text-secondary);
        }

        .status-dot.active {
            background: var(--success);
            box-shadow: 0 0 8px var(--success);
            animation: pulse 1.5s infinite;
        }

        .terminal-container {
            background-color: #0c0b14;
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 1.25rem;
            height: 280px;
            overflow-y: auto;
            font-family: 'Fira Code', 'Courier New', Courier, monospace;
            font-size: 0.875rem;
            color: #38bdf8;
            line-height: 1.5;
            white-space: pre-wrap;
        }

        /* TTS Settings Collapsible styling */
        .settings-details {
            margin-top: 1rem;
            padding-top: 1rem;
            border-top: 1px solid rgba(255, 255, 255, 0.05);
        }

        .settings-details[open] summary {
            margin-bottom: 1rem;
        }

        .settings-details summary {
            font-size: 0.95rem;
            font-weight: 600;
            color: var(--text-secondary);
            cursor: pointer;
            user-select: none;
            transition: color 0.2s;
            outline: none;
        }

        .settings-details summary:hover {
            color: #fff;
        }

        .settings-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.25rem;
            margin-top: 0.5rem;
            background: rgba(0, 0, 0, 0.15);
            padding: 1.25rem;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.03);
        }

        @media (max-width: 600px) {
            .settings-grid {
                grid-template-columns: 1fr;
            }
        }

        .slider-group {
            display: flex;
            flex-direction: column;
            gap: 0.5rem;
        }

        .slider-header {
            display: flex;
            justify-content: space-between;
            font-size: 0.85rem;
            color: var(--text-secondary);
            font-weight: 500;
        }

        .range-slider {
            width: 100%;
            height: 6px;
            border-radius: 3px;
            background: rgba(255, 255, 255, 0.1);
            outline: none;
            accent-color: var(--primary);
            cursor: pointer;
            transition: background 0.3s;
        }

        .range-slider:hover {
            background: rgba(255, 255, 255, 0.15);
        }

        .preview-section {
            grid-column: 1 / -1;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.05);
            padding: 1rem;
            border-radius: 8px;
            display: flex;
            flex-direction: column;
            gap: 0.75rem;
            margin-top: 0.5rem;
        }

        .preview-text {
            width: 100%;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 6px;
            color: #fff;
            font-family: inherit;
            font-size: 0.9rem;
            padding: 0.6rem;
            resize: vertical;
            min-height: 50px;
        }

        .preview-text:focus {
            outline: none;
            border-color: var(--primary);
        }

        .preview-controls {
            display: flex;
            gap: 1rem;
            align-items: center;
            flex-wrap: wrap;
        }

        audio {
            accent-color: var(--primary);
        }

        /* Upload and notification styling */
        .upload-status {
            padding: 0.75rem 1rem;
            border-radius: 8px;
            font-size: 0.9rem;
            margin-bottom: 1.25rem;
            display: none;
            line-height: 1.4;
        }
        .upload-status.success {
            background: rgba(16, 185, 129, 0.15);
            border: 1px solid rgba(16, 185, 129, 0.3);
            color: #34d399;
            display: block;
        }
        .upload-status.error {
            background: rgba(239, 68, 68, 0.15);
            border: 1px solid rgba(239, 68, 68, 0.3);
            color: #f87171;
            display: block;
        }
        .upload-status.info {
            background: rgba(59, 130, 246, 0.15);
            border: 1px solid rgba(59, 130, 246, 0.3);
            color: #60a5fa;
            display: block;
        }

        /* Modal Styles */
        .modal-overlay {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background: rgba(9, 9, 11, 0.8);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            z-index: 1000;
            display: none;
            align-items: center;
            justify-content: center;
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .modal-overlay.active {
            display: flex;
            opacity: 1;
        }

        .modal-content {
            background: rgba(20, 20, 35, 0.95);
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 16px;
            width: 90%;
            max-width: 600px;
            max-height: 80vh;
            display: flex;
            flex-direction: column;
            box-shadow: 0 24px 64px rgba(0, 0, 0, 0.7);
            transform: scale(0.95);
            transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        }

        .modal-overlay.active .modal-content {
            transform: scale(1);
        }

        .modal-header {
            padding: 1.25rem 1.5rem;
            border-bottom: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .modal-header h3 {
            margin: 0;
            font-size: 1.25rem;
            font-weight: 600;
            color: #fff;
        }

        .modal-close {
            background: none;
            border: none;
            color: var(--text-secondary);
            font-size: 1.5rem;
            cursor: pointer;
            transition: color 0.2s;
            padding: 0.25rem;
            line-height: 1;
        }

        .modal-close:hover {
            color: #fff;
        }

        .modal-body {
            padding: 1.5rem;
            overflow-y: auto;
            flex: 1;
            display: flex;
            flex-direction: column;
            gap: 1rem;
        }

        .fs-path-container {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 8px;
            padding: 0.75rem;
            font-family: 'Fira Code', monospace;
            font-size: 0.85rem;
            color: #a78bfa;
            word-break: break-all;
        }

        .fs-list {
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 8px;
            max-height: 250px;
            overflow-y: auto;
            background: rgba(0, 0, 0, 0.2);
        }

        .fs-item {
            display: flex;
            align-items: center;
            gap: 0.75rem;
            padding: 0.75rem 1rem;
            cursor: pointer;
            transition: background 0.2s;
            border-bottom: 1px solid rgba(255, 255, 255, 0.03);
            color: var(--text-primary);
        }

        .fs-item:last-child {
            border-bottom: none;
        }

        .fs-item:hover {
            background: rgba(255, 255, 255, 0.05);
            color: #fff;
        }

        .fs-item-icon {
            color: #3b82f6;
            font-size: 1.1rem;
        }

        .fs-parent-btn {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            color: #a78bfa;
            cursor: pointer;
            padding: 0.5rem;
            font-weight: 500;
            font-size: 0.9rem;
            width: fit-content;
            transition: color 0.2s;
        }

        .fs-parent-btn:hover {
            color: #c084fc;
        }

        .modal-footer {
            padding: 1.25rem 1.5rem;
            border-top: 1px solid rgba(255, 255, 255, 0.08);
            display: flex;
            justify-content: flex-end;
            gap: 0.75rem;
        }

        .btn-outline {
            background: transparent;
            border: 1px solid rgba(255, 255, 255, 0.15);
            color: var(--text-primary);
            padding: 0.625rem 1.25rem;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }

        .btn-outline:hover {
            background: rgba(255, 255, 255, 0.05);
            border-color: rgba(255, 255, 255, 0.25);
            color: #fff;
        }

        .save-location-info {
            font-size: 0.85rem;
            color: var(--text-secondary);
            margin-top: -0.75rem;
            margin-bottom: 1.5rem;
            font-family: 'Fira Code', monospace;
            word-break: break-all;
            background: rgba(0, 0, 0, 0.2);
            padding: 0.5rem 0.75rem;
            border-radius: 6px;
            border: 1px solid rgba(255, 255, 255, 0.03);
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>Kindle Butch Gen</h1>
            <p>EPUB / AZW3 Translation and Audio Synthesis System</p>
        </header>

        <div class="dashboard-grid">
            <!-- Left Column: Add Form -->
            <div class="glass-card">
                <h2 class="card-title">Add New Book</h2>
                <div id="uploadStatus" class="upload-status"></div>
                <form id="addBookForm">
                    <div class="form-group">
                        <label for="file_upload">Upload File (PDF / EPUB / TXT / MD)</label>
                        <input type="file" id="file_upload" class="form-control" accept=".pdf,.epub,.txt,.md">
                    </div>
                    <div class="form-group">
                        <label for="pdf_path">Or Enter Source PDF Path (on system)</label>
                        <input type="text" id="pdf_path" class="form-control" placeholder="e.g. /path/to/book.pdf">
                    </div>
                    <div class="form-group">
                        <label for="slug">Book Slug (lowercase, a-z0-9_-)</label>
                        <input type="text" id="slug" class="form-control" placeholder="e.g. clean-code" required pattern="^[a-z0-9_-]+$">
                    </div>
                    <div class="form-group">
                        <label for="title">Title</label>
                        <input type="text" id="title" class="form-control" placeholder="e.g. Clean Code" required>
                    </div>
                    <div class="form-group">
                        <label for="authors">Authors</label>
                        <input type="text" id="authors" class="form-control" placeholder="e.g. Robert C. Martin" required>
                    </div>
                    <div class="form-group">
                        <label for="source_lang">Source Language</label>
                        <select id="source_lang" class="form-control" required>
                            <option value="auto">Auto-detect (EPUB only)</option>
                            <option value="en">English (en)</option>
                            <option value="ru">Russian (ru)</option>
                            <option value="uk">Ukrainian (uk)</option>
                        </select>
                    </div>
                    <div class="form-group">
                        <label for="lang">Target Language (TTS & E-Book)</label>
                        <select id="lang" class="form-control" required>
                            <option value="uk">Ukrainian (uk)</option>
                            <option value="ru">Russian (ru)</option>
                            <option value="en">English (en)</option>
                        </select>
                    </div>
                    <div class="form-group" style="display: flex; align-items: center; gap: 0.5rem; margin-top: 1rem; margin-bottom: 1.5rem;">
                        <input type="checkbox" id="is_manga" style="width: auto; margin: 0; cursor: pointer;">
                        <label for="is_manga" style="margin: 0; cursor: pointer; font-weight: bold; color: var(--text-primary);">Is Manga / Comic (Images)</label>
                    </div>
                    <button type="submit" id="addBookSubmit" class="btn btn-primary" style="width: 100%;">Add Book</button>
                </form>
            </div>

            <!-- Right Column: Books List -->
            <div class="glass-card">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
                    <h2 class="card-title" style="margin: 0; border-bottom: none; padding-bottom: 0; flex: 1;">Manage Books</h2>
                    <button class="btn-outline" style="padding: 0.4rem 0.8rem; font-size: 0.85rem; display: flex; align-items: center; gap: 0.3rem; border-radius: 8px; cursor: pointer;" onclick="openFolderSelector()">
                        <span>⚙</span> Save Location
                    </button>
                </div>
                <div class="save-location-info">
                    <span>📁</span> <strong>Save Location:</strong> <span id="currentSaveLocation">Loading...</span>
                </div>
                <div id="booksList" class="books-container">
                    <p style="color: var(--text-secondary); text-align: center;">Loading books...</p>
                </div>
            </div>

            <!-- Full Width: Terminal Logs -->
            <div id="terminalCard" class="glass-card terminal-card" style="display: none;">
                <div class="terminal-header">
                    <h2 class="card-title" style="margin: 0; border: none; padding: 0;" id="terminalTitle">Live Progress Console</h2>
                    <div class="terminal-indicator">
                        <span class="status-dot" id="terminalDot"></span>
                        <span id="terminalStatusText">Inactive</span>
                    </div>
                </div>
                <div class="terminal-container" id="terminalLog">Select a book to display live logs.</div>
            </div>
        </div>
    </div>

    <script>
        let currentLogsSlug = null;
        let logsInterval = null;

        function showUploadStatus(msg, type) {
            const statusDiv = document.getElementById('uploadStatus');
            statusDiv.className = 'upload-status ' + type;
            statusDiv.innerHTML = msg;
            statusDiv.style.display = 'block';
        }

        function clearUploadStatus() {
            const statusDiv = document.getElementById('uploadStatus');
            statusDiv.style.display = 'none';
        }

        // Auto-detect metadata on file selection
        document.getElementById('file_upload').addEventListener('change', async function(e) {
            if (this.files.length === 0) return;
            
            const file = this.files[0];
            showUploadStatus('Parsing file metadata...', 'info');
            
            const formData = new FormData();
            formData.append('file', file);
            
            try {
                const response = await fetch('/api/parse-metadata', {
                    method: 'POST',
                    body: formData
                });
                const res = await response.json();
                if (response.ok) {
                    if (res.detected_slug) {
                        document.getElementById('slug').value = res.detected_slug;
                    }
                    if (res.detected_title) {
                        document.getElementById('title').value = res.detected_title;
                    }
                    if (res.detected_authors) {
                        document.getElementById('authors').value = res.detected_authors;
                    }
                    if (res.detected_lang && res.detected_lang !== 'auto') {
                        document.getElementById('source_lang').value = res.detected_lang;
                    } else {
                        document.getElementById('source_lang').value = 'auto';
                    }
                    showUploadStatus('Metadata detected and pre-filled successfully!', 'success');
                } else {
                    showUploadStatus('Failed to parse metadata: ' + res.message, 'error');
                }
            } catch (err) {
                showUploadStatus('Metadata detection failed: ' + err.message, 'error');
            }
        });

        document.getElementById('addBookForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const slug = document.getElementById('slug').value.trim();
            const title = document.getElementById('title').value.trim();
            const authors = document.getElementById('authors').value.trim();
            const lang = document.getElementById('lang').value;
            const source_lang = document.getElementById('source_lang').value;
            const fileInput = document.getElementById('file_upload');
            const pdf_path = document.getElementById('pdf_path').value.trim();
            const is_manga = document.getElementById('is_manga').checked;
            
            const submitBtn = document.getElementById('addBookSubmit');
            submitBtn.disabled = true;
            submitBtn.innerText = 'Adding Book...';

            if (fileInput.files.length > 0) {
                showUploadStatus('Uploading book file and extracting content (this may take a few seconds)...', 'info');
                
                const formData = new FormData();
                formData.append('slug', slug);
                formData.append('title', title);
                formData.append('authors', authors);
                formData.append('lang', lang);
                formData.append('source_lang', source_lang);
                formData.append('file', fileInput.files[0]);
                formData.append('is_manga', is_manga ? 'true' : 'false');

                try {
                    const response = await fetch('/api/upload', {
                        method: 'POST',
                        body: formData
                    });
                    const res = await response.json();
                    if (response.ok) {
                        showUploadStatus('Book uploaded and added successfully!', 'success');
                        document.getElementById('addBookForm').reset();
                        fetchBooks();
                    } else {
                        showUploadStatus('Error: ' + res.message, 'error');
                    }
                } catch (err) {
                    showUploadStatus('Upload failed: ' + err.message, 'error');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.innerText = 'Add Book';
                }
            } else {
                if (!pdf_path) {
                    showUploadStatus('Please upload a file or specify a local PDF path.', 'error');
                    submitBtn.disabled = false;
                    submitBtn.innerText = 'Add Book';
                    return;
                }
                showUploadStatus('Adding local book on system...', 'info');
                try {
                    const response = await fetch('/api/add', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ slug, pdf_path, title, authors, lang, source_lang, is_manga })
                    });
                    const res = await response.json();
                    if (response.ok) {
                        showUploadStatus('Book added successfully!', 'success');
                        document.getElementById('addBookForm').reset();
                        fetchBooks();
                    } else {
                        showUploadStatus('Error: ' + res.message, 'error');
                    }
                } catch (err) {
                    showUploadStatus('Request failed: ' + err.message, 'error');
                } finally {
                    submitBtn.disabled = false;
                    submitBtn.innerText = 'Add Book';
                }
            }
        });

        function handleVoiceChange(slug, voiceValue) {
            const speakerSelect = document.getElementById(`speaker-${slug}`);
            if (!speakerSelect) return;
            
            if (voiceValue === 'ukrainian_tts') {
                speakerSelect.innerHTML = `
                    <option value="0">Lada [0]</option>
                    <option value="1">Mykyta [1]</option>
                    <option value="2" selected>Tetiana [2]</option>
                `;
            } else {
                speakerSelect.innerHTML = `<option value="0" selected>Default [0]</option>`;
            }
        }

        function handleEngineChange(slug, engineValue, targetLang) {
            const speakerSelect = document.getElementById(`speaker-${slug}`);
            if (!speakerSelect) return;
            
            if (engineValue === 'styletts2') {
                if (targetLang !== 'uk') {
                    alert(`StyleTTS2 supports only Ukrainian language. This book's language is '${targetLang}'. Switching back to Supertonic 3.`);
                    document.getElementById(`engine-${slug}`).value = 'supertonic3';
                    handleEngineChange(slug, 'supertonic3', targetLang);
                    return;
                }
                speakerSelect.innerHTML = `<option value="0" selected>Single Speaker (Filatov)</option>`;
                speakerSelect.disabled = true;
            } else if (engineValue === 'supertonic3') {
                speakerSelect.disabled = false;
                speakerSelect.innerHTML = Array.from({length: 10}, (_, i) => 
                    `<option value="${i}">Speaker [${i}]</option>`
                ).join('');
            }
        }

        async function fetchBooks() {
            try {
                const openDetails = {};
                const formValues = {};
                const activeId = document.activeElement ? document.activeElement.id : null;
                let selStart = null, selEnd = null;
                if (document.activeElement && document.activeElement.selectionStart !== undefined) {
                    selStart = document.activeElement.selectionStart;
                    selEnd = document.activeElement.selectionEnd;
                }

                const cards = document.querySelectorAll('.book-card');
                cards.forEach(card => {
                    const slugEl = card.querySelector('code');
                    if (slugEl) {
                        const slug = slugEl.innerText.trim();
                        const detailsEl = document.getElementById(`details-${slug}`);
                        if (detailsEl) {
                            openDetails[slug] = detailsEl.open;
                            
                            const engineEl = document.getElementById(`engine-${slug}`);
                            const speakerEl = document.getElementById(`speaker-${slug}`);
                            const speedEl = document.getElementById(`speed-${slug}`);
                            const noiseEl = document.getElementById(`noise-scale-${slug}`);
                            const noiseWEl = document.getElementById(`noise-w-${slug}`);
                            const previewEl = document.getElementById(`preview-text-${slug}`);
                            
                            formValues[slug] = {
                                engine: engineEl ? engineEl.value : null,
                                speaker: speakerEl ? speakerEl.value : null,
                                speed: speedEl ? speedEl.value : null,
                                noise_scale: noiseEl ? noiseEl.value : null,
                                noise_w: noiseWEl ? noiseWEl.value : null,
                                preview_text: previewEl ? previewEl.value : ''
                            };
                        }
                    }
                });

                const response = await fetch('/api/books');
                const books = await response.json();
                const container = document.getElementById('booksList');
                
                if (books.length === 0) {
                    container.innerHTML = '<p style="color: var(--text-secondary); text-align: center;">No books configured yet.</p>';
                    return;
                }

                container.innerHTML = books.map(book => {
                    const badgeClass = book.is_running ? 'badge-running' : 'badge-idle';
                    const badgeText = book.is_running ? 'Running' : 'Idle';
                    const detailsOpenAttr = openDetails[book.slug] ? 'open' : '';
                    
                    let speakerOptions = '';
                    let speakerDisabled = '';
                    if (book.tts_engine === 'styletts2') {
                        speakerOptions = `<option value="0" selected>Single Speaker (Filatov)</option>`;
                        speakerDisabled = 'disabled';
                    } else {
                        speakerOptions = Array.from({length: 10}, (_, i) => 
                            `<option value="${i}" ${book.tts_speaker_id === i ? 'selected' : ''}>Speaker [${i}]</option>`
                        ).join('');
                    }
                    
                    let progressHtml = '';
                    let optionsHtml = '';
                    if (book.progress.is_manga) {
                        const comp = book.progress.manga_pages_completed || 0;
                        const tot = book.progress.manga_total_pages || 0;
                        const pct = book.progress.manga_percent || 0;
                        progressHtml = `
                            <div class="progress-section">
                                <div class="progress-item">
                                    <div class="progress-label">
                                        <span>Manga Page Translation</span>
                                        <span>${pct}% (${comp} of ${tot} pages)</span>
                                    </div>
                                    <div class="progress-bar-bg">
                                        <div class="progress-bar-fill fill-translation" style="width: ${pct}%"></div>
                                    </div>
                                </div>
                            </div>
                        `;
                        optionsHtml = `
                            <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top: 1rem; padding: 0.75rem; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.05); border-radius: 8px;">
                                📖 <strong>Manga Mode:</strong> Translates speech bubbles and packs layout images into a .cbz archive.
                            </div>
                        `;
                    } else {
                        progressHtml = `
                            <div class="progress-section">
                                <div class="progress-item">
                                    <div class="progress-label">
                                        <span>Marker (OCR)</span>
                                        <span>${book.progress.marker_percent}%</span>
                                    </div>
                                    <div class="progress-bar-bg">
                                        <div class="progress-bar-fill fill-marker" style="width: ${book.progress.marker_percent}%"></div>
                                    </div>
                                </div>
                                <div class="progress-item">
                                    <div class="progress-label">
                                        <span>Translation</span>
                                        <span>${book.progress.translation_percent}%</span>
                                    </div>
                                    <div class="progress-bar-bg">
                                        <div class="progress-bar-fill fill-translation" style="width: ${book.progress.translation_percent}%"></div>
                                    </div>
                                </div>
                                <div class="progress-item">
                                    <div class="progress-label">
                                        <span>Proofreading (GEC)</span>
                                        <span>${book.progress.edit_percent || 0}%</span>
                                    </div>
                                    <div class="progress-bar-bg">
                                        <div class="progress-bar-fill fill-edit" style="width: ${book.progress.edit_percent || 0}%"></div>
                                    </div>
                                </div>
                                <div class="progress-item">
                                    <div class="progress-label">
                                        <span>Stressifier (NLP)</span>
                                        <span>${book.progress.stress_percent}%</span>
                                    </div>
                                    <div class="progress-bar-bg">
                                        <div class="progress-bar-fill fill-stress" style="width: ${book.progress.stress_percent}%"></div>
                                    </div>
                                </div>
                                <div class="progress-item">
                                    <div class="progress-label">
                                        <span>TTS Audio</span>
                                        <span>${book.progress.tts_percent}%</span>
                                    </div>
                                    <div class="progress-bar-bg">
                                        <div class="progress-bar-fill fill-tts" style="width: ${book.progress.tts_percent}%"></div>
                                    </div>
                                </div>
                            </div>
                        `;
                        optionsHtml = `
                            <div class="options-group" id="opts-${book.slug}">
                                <label class="option-checkbox"><input type="checkbox" id="clean-${book.slug}"> Clean</label>
                                <label class="option-checkbox"><input type="checkbox" id="notrans-${book.slug}"> No Translate</label>
                                <label class="option-checkbox"><input type="checkbox" id="noebook-${book.slug}"> No Ebook</label>
                                <label class="option-checkbox"><input type="checkbox" id="noaudio-${book.slug}"> No Audio</label>
                            </div>
                        `;
                    }

                    return `
                        <div class="glass-card book-card">
                            <div class="book-header">
                                <div class="book-info">
                                    <h3>${book.title}</h3>
                                    <p>by ${book.authors} | Slug: <code>${book.slug}</code> | Lang: ${book.target_lang}</p>
                                </div>
                                <span class="badge ${badgeClass}">${badgeText}</span>
                            </div>

                            ${progressHtml}

                            ${optionsHtml}

                            <details class="settings-details" id="details-${book.slug}" ${detailsOpenAttr}>
                                <summary>🛠️ TTS Settings</summary>
                                <form onsubmit="saveTtsSettings(event, '${book.slug}')" class="settings-grid">

                                    <div class="form-group" style="margin-bottom:0;">
                                        <label for="engine-${book.slug}">TTS Engine</label>
                                        <select id="engine-${book.slug}" class="form-control" style="padding: 0.5rem;" onchange="handleEngineChange('${book.slug}', this.value, '${book.target_lang}')">
                                            <option value="supertonic3" ${book.tts_engine === 'supertonic3' ? 'selected' : ''}>Supertonic 3 (Flow Matching, 31 мова)</option>
                                            <option value="styletts2" ${book.tts_engine === 'styletts2' ? 'selected' : ''}>StyleTTS2 (українська)</option>
                                        </select>
                                    </div>
                                    <div class="form-group" style="margin-bottom:0;">
                                        <label for="speaker-${book.slug}">Speaker / Voice</label>
                                        <select id="speaker-${book.slug}" class="form-control" style="padding: 0.5rem;" ${speakerDisabled}>
                                            ${speakerOptions}
                                        </select>
                                    </div>
                                    <div class="slider-group">
                                        <div class="slider-header">
                                            <span>Speed</span>
                                            <span><span id="speed-val-${book.slug}">${book.tts_speed}</span>x</span>
                                        </div>
                                        <input type="range" id="speed-${book.slug}" class="range-slider" min="0.5" max="2.0" step="0.1" value="${book.tts_speed}" oninput="document.getElementById('speed-val-${book.slug}').innerText = this.value">
                                    </div>
                                    <div class="slider-group">
                                        <div class="slider-header">
                                            <span>Noise Scale</span>
                                            <span id="noise-scale-val-${book.slug}">${book.tts_noise_scale}</span>
                                        </div>
                                        <input type="range" id="noise-scale-${book.slug}" class="range-slider" min="0.1" max="1.5" step="0.05" value="${book.tts_noise_scale}" oninput="document.getElementById('noise-scale-val-${book.slug}').innerText = this.value">
                                    </div>
                                    <div class="slider-group">
                                        <div class="slider-header">
                                            <span>Noise Width</span>
                                            <span id="noise-w-val-${book.slug}">${book.tts_noise_w}</span>
                                        </div>
                                        <input type="range" id="noise-w-${book.slug}" class="range-slider" min="0.1" max="1.5" step="0.05" value="${book.tts_noise_w}" oninput="document.getElementById('noise-w-val-${book.slug}').innerText = this.value">
                                    </div>
                                    <div style="display: flex; align-items: flex-end;">
                                        <button type="submit" class="btn btn-primary" style="width: 100%; padding: 0.5rem 1rem; font-size: 0.875rem;">Save Settings</button>
                                    </div>
                                    
                                    <div class="preview-section">
                                        <label style="font-size: 0.85rem; font-weight: 600; color: var(--text-secondary);">Live Preview (TTS Language)</label>
                                        <textarea id="preview-text-${book.slug}" class="preview-text" placeholder="Enter test sentence..."></textarea>
                                        <div class="preview-controls">
                                            <button type="button" onclick="generatePreview('${book.slug}')" id="preview-btn-${book.slug}" class="btn btn-secondary" style="padding: 0.5rem 1rem; font-size: 0.85rem;">Hear Preview</button>
                                            <audio id="preview-audio-${book.slug}" controls style="display: none; height: 32px; flex-grow: 1;"></audio>
                                        </div>
                                    </div>
                                </form>
                            </details>

                            <div class="controls">
                                ${book.is_running 
                                    ? `<button onclick="stopConversion('${book.slug}')" class="btn btn-danger">Stop Conversion</button>`
                                    : `<button onclick="runConversion('${book.slug}')" class="btn btn-success">Run Conversion</button>`
                                }
                                ${!book.is_running && book.output_files && book.output_files.length > 0
                                    ? `<button onclick="rerunConversion('${book.slug}')" class="btn" style="background: linear-gradient(135deg, #f97316, #ea580c); color: white; border: none;">🔄 Re-run</button>`
                                    : ''
                                }
                                <button onclick="selectBookForLogs('${book.slug}', '${book.title}')" class="btn btn-secondary">Console Logs</button>
                                <a href="/view/${book.slug}" class="btn btn-secondary" style="text-decoration: none; text-align: center; display: inline-flex; align-items: center; justify-content: center;">Visual Preview</a>
                            </div>

                            ${book.output_files && book.output_files.length > 0 ? `
                                <div class="downloads">
                                    ${book.output_files.map(file => `
                                        <a class="download-link" href="/api/download/${book.slug}/${file}" target="_blank">
                                            📥 ${file}
                                        </a>
                                    `).join('')}
                                </div>
                            ` : ''}
                        </div>
                    `;
                }).join('');

                // Restore input values that were not saved yet
                books.forEach(book => {
                    const slug = book.slug;
                    const vals = formValues[slug];
                    if (vals) {
                        if (vals.engine !== null && document.getElementById(`engine-${slug}`)) {
                            document.getElementById(`engine-${slug}`).value = vals.engine;
                            handleEngineChange(slug, vals.engine, book.target_lang);
                        }
                        if (vals.speaker !== null && document.getElementById(`speaker-${slug}`)) {
                            document.getElementById(`speaker-${slug}`).value = vals.speaker;
                        }
                        if (vals.speed !== null) {
                            document.getElementById(`speed-${slug}`).value = vals.speed;
                            document.getElementById(`speed-val-${slug}`).innerText = vals.speed;
                        }
                        if (vals.noise_scale !== null) {
                            document.getElementById(`noise-scale-${slug}`).value = vals.noise_scale;
                            document.getElementById(`noise-scale-val-${slug}`).innerText = vals.noise_scale;
                        }
                        if (vals.noise_w !== null) {
                            document.getElementById(`noise-w-${slug}`).value = vals.noise_w;
                            document.getElementById(`noise-w-val-${slug}`).innerText = vals.noise_w;
                        }
                        if (vals.preview_text !== '') {
                            document.getElementById(`preview-text-${slug}`).value = vals.preview_text;
                        }
                    }
                });

                // Restore active cursor focus and selection
                if (activeId) {
                    const activeEl = document.getElementById(activeId);
                    if (activeEl) {
                        activeEl.focus();
                        if (selStart !== null && selEnd !== null) {
                            activeEl.selectionStart = selStart;
                            activeEl.selectionEnd = selEnd;
                        }
                    }
                }
            } catch (err) {
                console.error('Failed to fetch books:', err);
            }
        }

        async function runConversion(slug) {
            const clean = document.getElementById(`clean-${slug}`)?.checked || false;
            const no_translate = document.getElementById(`notrans-${slug}`)?.checked || false;
            const no_ebook = document.getElementById(`noebook-${slug}`)?.checked || false;
            const no_audio = document.getElementById(`noaudio-${slug}`)?.checked || false;

            try {
                const response = await fetch(`/api/run/${slug}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ clean, no_translate, no_ebook, no_audio })
                });
                const res = await response.json();
                if (response.ok) {
                    fetchBooks();
                    selectBookForLogs(slug, slug);
                } else {
                    alert('Error starting conversion: ' + res.message);
                }
            } catch (err) {
                alert('Request failed: ' + err.message);
            }
        }

        async function rerunConversion(slug) {
            if (!confirm(`Re-run full conversion for "${slug}"? This will restart the pipeline from scratch (translation cache is preserved).`)) return;
            const clean = document.getElementById(`clean-${slug}`)?.checked || false;
            const no_translate = document.getElementById(`notrans-${slug}`)?.checked || false;
            const no_ebook = document.getElementById(`noebook-${slug}`)?.checked || false;
            const no_audio = document.getElementById(`noaudio-${slug}`)?.checked || false;
            try {
                const response = await fetch(`/api/run/${slug}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ force: true, clean, no_translate, no_ebook, no_audio })
                });
                const res = await response.json();
                if (response.ok) {
                    fetchBooks();
                    selectBookForLogs(slug, slug);
                } else {
                    alert('Error re-running conversion: ' + res.message);
                }
            } catch (err) {
                alert('Request failed: ' + err.message);
            }
        }

        async function stopConversion(slug) {
            try {
                const response = await fetch(`/api/stop/${slug}`, { method: 'POST' });
                const res = await response.json();
                if (response.ok) {
                    fetchBooks();
                } else {
                    alert('Error stopping conversion: ' + res.message);
                }
            } catch (err) {
                alert('Request failed: ' + err.message);
            }
        }

        function selectBookForLogs(slug, title) {
            currentLogsSlug = slug;
            document.getElementById('terminalCard').style.display = 'block';
            document.getElementById('terminalTitle').innerText = `Console Logs: ${title}`;
            
            // Clear previous interval
            if (logsInterval) clearInterval(logsInterval);
            
            // Poll logs immediately and then on interval
            pollLogs();
            logsInterval = setInterval(pollLogs, 1500);
            
            // Scroll to terminal card
            document.getElementById('terminalCard').scrollIntoView({ behavior: 'smooth' });
        }

        async function pollLogs() {
            if (!currentLogsSlug) return;
            try {
                const response = await fetch(`/api/status/${currentLogsSlug}`);
                if (!response.ok) return;
                const status = await response.json();
                
                const logBox = document.getElementById('terminalLog');
                const prevScrollHeight = logBox.scrollHeight;
                const prevScrollTop = logBox.scrollTop;
                const prevClientHeight = logBox.clientHeight;
                
                // Update terminal text
                if (status.logs && status.logs.length > 0) {
                    logBox.innerText = status.logs.join('');
                } else {
                    logBox.innerText = 'No log entries found. Job may be starting...';
                }
                
                // Update active indicator
                const dot = document.getElementById('terminalDot');
                const statusText = document.getElementById('terminalStatusText');
                if (status.is_running) {
                    dot.className = 'status-dot active';
                    statusText.innerText = 'Converting';
                } else {
                    dot.className = 'status-dot';
                    statusText.innerText = 'Inactive';
                }
                
                // Autoscroll if user wasn't scrolled up
                if (prevScrollHeight - prevScrollTop <= prevClientHeight + 50) {
                    logBox.scrollTop = logBox.scrollHeight;
                }
            } catch (err) {
                console.error('Failed to poll logs:', err);
            }
        }

        async function saveTtsSettings(event, slug) {
            event.preventDefault();
            const tts_engine = document.getElementById(`engine-${slug}`).value;
            const tts_voice = tts_engine;
            const tts_voice_quality = 'medium';
            const tts_speaker_id = parseInt(document.getElementById(`speaker-${slug}`).value);
            const tts_speed = parseFloat(document.getElementById(`speed-${slug}`).value);
            const tts_noise_scale = parseFloat(document.getElementById(`noise-scale-${slug}`).value);
            const tts_noise_w = parseFloat(document.getElementById(`noise-w-${slug}`).value);
            
            try {
                const response = await fetch(`/api/tts-settings/${slug}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ tts_engine, tts_voice, tts_voice_quality, tts_speaker_id, tts_speed, tts_noise_scale, tts_noise_w })
                });
                const res = await response.json();
                if (response.ok) {
                    alert('Settings saved successfully!');
                    fetchBooks();
                } else {
                    alert('Error saving settings: ' + res.message);
                }
            } catch (err) {
                alert('Request failed: ' + err.message);
            }
        }

        async function generatePreview(slug) {
            const text = document.getElementById(`preview-text-${slug}`).value.trim();
            if (!text) {
                alert('Please enter some text first.');
                return;
            }
            
            const btn = document.getElementById(`preview-btn-${slug}`);
            const audio = document.getElementById(`preview-audio-${slug}`);
            
            btn.disabled = true;
            btn.innerText = 'Generating...';
            audio.style.display = 'none';
            
            // Read current unsaved form values
            const tts_engine = document.getElementById(`engine-${slug}`).value;
            const tts_speaker_id = parseInt(document.getElementById(`speaker-${slug}`).value);
            const tts_speed = parseFloat(document.getElementById(`speed-${slug}`).value);
            const tts_noise_scale = parseFloat(document.getElementById(`noise-scale-${slug}`).value);
            const tts_noise_w = parseFloat(document.getElementById(`noise-w-${slug}`).value);
            
            try {
                const response = await fetch(`/api/tts-preview/${slug}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ text, tts_engine, tts_speaker_id, tts_speed, tts_noise_scale, tts_noise_w })
                });
                
                if (response.ok) {
                    const blob = await response.blob();
                    const blobUrl = URL.createObjectURL(blob);
                    audio.src = blobUrl;
                    audio.style.display = 'block';
                    audio.play();
                } else {
                    const res = await response.json();
                    alert('Error generating preview: ' + (res.message || 'unknown error'));
                }
            } catch (err) {
                alert('Request failed: ' + err.message);
            } finally {
                btn.disabled = false;
                btn.innerText = 'Hear Preview';
            }
        }

        // Initial load
        fetchBooks();
        // Periodically refresh book states to update progress bars
        setInterval(fetchBooks, 5000);

        let activeFsPath = "/storage/emulated/0";
        let parentFsPath = null;

        async function initSettings() {
            try {
                const res = await fetch("/api/settings");
                const settings = await res.json();
                document.getElementById("currentSaveLocation").textContent = settings.output_root;
                activeFsPath = settings.output_root;
            } catch (err) {
                console.error("Failed to load settings:", err);
            }
        }

        async function openFolderSelector() {
            const modal = document.getElementById("folderModal");
            modal.classList.add("active");
            
            // Load current path
            try {
                const res = await fetch("/api/settings");
                const settings = await res.json();
                activeFsPath = settings.output_root;
            } catch (e) {
                activeFsPath = "/storage/emulated/0";
            }
            await loadDirectory(activeFsPath);
        }

        function closeFolderSelector() {
            const modal = document.getElementById("folderModal");
            modal.classList.remove("active");
        }

        async function loadDirectory(path) {
            const listEl = document.getElementById("fsList");
            listEl.innerHTML = `<p style="padding: 1rem; color: var(--text-secondary); text-align: center;">Loading folder contents...</p>`;
            
            try {
                const res = await fetch(`/api/browse-fs?path=${encodeURIComponent(path)}`);
                const data = await res.json();
                
                if (data.error) {
                    listEl.innerHTML = `<p style="padding: 1rem; color: var(--danger); text-align: center;">${data.error}</p>`;
                    return;
                }
                
                activeFsPath = data.current;
                parentFsPath = data.parent;
                
                document.getElementById("fsCurrentPath").value = data.current;
                
                // Show/hide up button
                const parentBtn = document.getElementById("fsParentBtn");
                if (parentFsPath) {
                    parentBtn.style.display = "flex";
                } else {
                    parentBtn.style.display = "none";
                }
                
                // List folders
                listEl.innerHTML = "";
                if (data.dirs.length === 0) {
                    listEl.innerHTML = `<p style="padding: 1.5rem; color: var(--text-secondary); text-align: center;">No subfolders found</p>`;
                    return;
                }
                
                data.dirs.forEach(item => {
                    const div = document.createElement("div");
                    div.className = "fs-item";
                    div.onclick = () => loadDirectory(item.path);
                    
                    const icon = document.createElement("span");
                    icon.className = "fs-item-icon";
                    icon.textContent = "📁";
                    
                    const name = document.createElement("span");
                    name.textContent = item.name;
                    
                    div.appendChild(icon);
                    div.appendChild(name);
                    listEl.appendChild(div);
                });
            } catch (err) {
                listEl.innerHTML = `<p style="padding: 1rem; color: var(--danger); text-align: center;">Failed to load directories</p>`;
            }
        }

        async function navigateFsParent() {
            if (parentFsPath) {
                await loadDirectory(parentFsPath);
            }
        }

        async function confirmFolderSelection() {
            const btn = document.getElementById("fsSelectBtn");
            btn.disabled = true;
            btn.textContent = "Saving...";
            
            const selectedPath = document.getElementById("fsCurrentPath").value.trim();
            
            try {
                const res = await fetch("/api/settings/output-root", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ path: selectedPath })
                });
                const data = await res.json();
                if (data.status === "success") {
                    document.getElementById("currentSaveLocation").textContent = data.output_root;
                    closeFolderSelector();
                } else {
                    alert("Error: " + (data.message || "Failed to set output directory"));
                }
            } catch (err) {
                alert("Failed to connect to server: " + err);
            } finally {
                btn.disabled = false;
                btn.textContent = "✓ Select This Folder";
            }
        }

        // Initialize settings on page load
        initSettings();
    </script>

    <!-- Folder Selector Modal -->
    <div id="folderModal" class="modal-overlay">
        <div class="modal-content">
            <div class="modal-header">
                <h3>Select Output Directory</h3>
                <button class="modal-close" onclick="closeFolderSelector()">&times;</button>
            </div>
            <div class="modal-body">
                <p style="margin: 0; font-size: 0.9rem; color: var(--text-secondary);">Choose where translated books and audio files should be saved.</p>
                <div class="fs-parent-btn" id="fsParentBtn" onclick="navigateFsParent()" style="display: none;">
                    <span>⬆</span> Up to parent folder
                </div>
                <div class="fs-list" id="fsList">
                    <!-- Dynamic folder list -->
                </div>
                <div style="display: flex; flex-direction: column; gap: 0.3rem; margin-top: 0.5rem;">
                    <label style="font-size: 0.8rem; color: var(--text-secondary); font-weight: 500;">Currently selected path (press Enter to browse):</label>
                    <input type="text" class="fs-path-container" id="fsCurrentPath" style="width: 100%; border: 1px solid rgba(255, 255, 255, 0.15); box-sizing: border-box; outline: none; background: rgba(0,0,0,0.4);" value="/storage/emulated/0" onkeydown="if(event.key === 'Enter') loadDirectory(this.value)">
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn-outline" onclick="closeFolderSelector()">Cancel</button>
                <button class="btn btn-primary" onclick="confirmFolderSelection()" id="fsSelectBtn" style="background: var(--primary); border: none; color: #fff; padding: 0.625rem 1.25rem; border-radius: 8px; font-weight: 500; cursor: pointer; transition: background 0.2s;">✓ Select This Folder</button>
            </div>
        </div>
    </div>
</body>
</html>
"""
    return render_template_string(html_content)

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
                prog = {"marker_percent": 0.0, "translation_percent": 0.0, "edit_percent": 0.0, "stress_percent": 0.0, "tts_percent": 0.0}
                
            # Scan output files
            output_dir = os.path.join(entry_path, "output")
            output_files = []
            if os.path.exists(output_dir):
                for f in os.listdir(output_dir):
                    if f.endswith((".epub", ".azw3", ".mp3", ".md")):
                        output_files.append(f)
                        
            books.append({
                "slug": entry,
                "title": title,
                "authors": authors,
                "target_lang": target_lang,
                "is_running": is_running,
                "progress": prog,
                "output_files": sorted(output_files),
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
        # Determine source file
        source_ext = ""
        for possible_ext in [".cbz", ".cbr", ".cb7", ".zip", ".rar", ".pdf", ".epub"]:
            if os.path.exists(os.path.join(paths["book_dir"], f"{slug}{possible_ext}")):
                source_ext = possible_ext
                break
                
        if not source_ext:
            return jsonify({"status": "error", "message": "Manga source file not found"}), 400
            
        manga_input = os.path.join(paths["book_dir"], f"{slug}{source_ext}")
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
            "python3", "/data/data/com.termux/files/home/kindle-butch-gen/translate_manga.py",
            "--input", manga_input,
            "--output", manga_output,
            "--lang", cfg.get("source_lang", "en"),
            "--progress-file", progress_file
        ]
        # Include glossary if it exists
        glossary_path = os.path.join(paths["book_dir"], "glossary.json")
        if os.path.exists(glossary_path):
            cmd.extend(["--glossary", glossary_path])
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
            
        paths = resolve_book_paths(repo_dir, slug)
        with open(paths["log_path"], "a", encoding="utf-8") as f:
            f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] --- Conversion process terminated by user ---\n")
            
        return jsonify({"status": "success", "message": "Process terminated successfully"})
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
        "edit_percent": prog.get("edit_percent", 0.0),
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

# -------------------------------------------------------------
# VISUAL STAGE VIEWER / QUALITY ASSURANCE ROUTES
# -------------------------------------------------------------

@app.route("/view/<slug>")
@auth.login_required
def view_book_stages(slug):
    if not validate_slug(slug):
        return "Invalid slug format", 400
    # Serve visualizer page
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Kindle Butch Gen - Quality Visualizer</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&family=Fira+Code:wght@400;500&display=swap" rel="stylesheet">
    <style>
        :root {
            --primary: #8b5cf6;
            --primary-hover: #7c3aed;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --bg-dark: #09090b;
            --card-bg: rgba(20, 20, 35, 0.65);
            --border-color: rgba(255, 255, 255, 0.08);
            --text-primary: #f4f4f5;
            --text-secondary: #a1a1aa;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            font-family: 'Outfit', sans-serif;
            background: radial-gradient(circle at top right, #1e1b4b, #09090b);
            background-attachment: fixed;
            color: var(--text-primary);
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
            padding: 2rem 1rem;
        }
        header {
            margin-bottom: 2rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        h1 {
            font-size: 2.2rem;
            font-weight: 700;
            margin: 0;
            background: linear-gradient(135deg, #a78bfa, #8b5cf6, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .subtitle {
            color: var(--text-secondary);
            font-size: 0.95rem;
            margin-top: 0.2rem;
        }
        .btn-back {
            display: inline-flex;
            align-items: center;
            padding: 0.6rem 1.2rem;
            background: rgba(255, 255, 255, 0.06);
            border: 1px solid var(--border-color);
            border-radius: 8px;
            color: var(--text-primary);
            text-decoration: none;
            font-weight: 500;
            font-size: 0.9rem;
            transition: all 0.2s ease;
        }
        .btn-back:hover {
            background: rgba(255, 255, 255, 0.12);
            border-color: rgba(255, 255, 255, 0.2);
        }
        .visualizer-card {
            background: var(--card-bg);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 1.5rem;
            backdrop-filter: blur(8px);
            margin-bottom: 2rem;
        }
        .loader {
            display: flex;
            justify-content: center;
            align-items: center;
            height: 200px;
            color: var(--text-secondary);
        }
        .loader-spinner {
            border: 3px solid rgba(255,255,255,0.1);
            border-top: 3px solid var(--primary);
            border-radius: 50%;
            width: 30px;
            height: 30px;
            animation: spin 1s linear infinite;
            margin-bottom: 1rem;
        }
        @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
        
        /* Manga Side-by-Side Viewer */
        .manga-viewer {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
            gap: 1.5rem;
            margin-top: 1rem;
        }
        .manga-panel {
            background: rgba(0, 0, 0, 0.3);
            border-radius: 8px;
            border: 1px solid var(--border-color);
            overflow: hidden;
            display: flex;
            flex-direction: column;
            align-items: center;
        }
        .panel-header {
            padding: 0.8rem;
            background: rgba(255,255,255,0.03);
            width: 100%;
            text-align: center;
            border-bottom: 1px solid var(--border-color);
            font-weight: 600;
            color: var(--text-secondary);
        }
        .manga-img {
            max-width: 100%;
            max-height: 70vh;
            object-fit: contain;
            background: #18181b;
        }
        .manga-controls {
            display: flex;
            justify-content: center;
            align-items: center;
            gap: 1.5rem;
            margin-top: 1.5rem;
        }
        .manga-btn {
            background: var(--primary);
            color: white;
            border: none;
            border-radius: 8px;
            padding: 0.7rem 1.5rem;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .manga-btn:hover { background: var(--primary-hover); }
        .manga-btn:disabled {
            background: rgba(255,255,255,0.06);
            color: var(--text-secondary);
            cursor: not-allowed;
        }
        .page-indicator {
            font-size: 1.1rem;
            font-weight: 600;
        }

        /* Regular Book Stage Table */
        .book-stages-list {
            display: flex;
            flex-direction: column;
            gap: 1.5rem;
        }
        .paragraph-card {
            background: rgba(15, 15, 25, 0.4);
            border: 1px solid var(--border-color);
            border-radius: 10px;
            padding: 1.2rem;
            transition: border-color 0.2s ease;
        }
        .paragraph-card:hover {
            border-color: rgba(139, 92, 246, 0.3);
        }
        .card-meta {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.8rem;
            color: var(--text-secondary);
            margin-bottom: 0.8rem;
            border-bottom: 1px solid rgba(255,255,255,0.04);
            padding-bottom: 0.5rem;
        }
        .grid-stages {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 1.5rem;
        }
        .stage-box {
            display: flex;
            flex-direction: column;
            gap: 0.4rem;
        }
        .stage-title {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--primary);
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }
        .stage-content {
            font-size: 0.95rem;
            line-height: 1.5;
            background: rgba(255,255,255,0.02);
            padding: 0.8rem;
            border-radius: 6px;
            border: 1px solid rgba(255,255,255,0.03);
            white-space: pre-wrap;
        }
        .audio-wrapper {
            margin-top: 1rem;
            padding: 0.8rem;
            background: rgba(139, 92, 246, 0.08);
            border: 1px solid rgba(139, 92, 246, 0.2);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .audio-label {
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-primary);
        }
        audio {
            height: 34px;
            border-radius: 4px;
        }
        .stage-stressed {
            font-family: 'Outfit', sans-serif;
            color: #d8b4fe; /* Accentuated color */
        }
        .badge {
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-audio { background: rgba(16, 185, 129, 0.15); color: var(--success); }
        .badge-no-audio { background: rgba(239, 68, 68, 0.15); color: var(--danger); }
        
        .filters {
            display: flex;
            gap: 1rem;
            margin-bottom: 1.5rem;
        }
        .filter-btn {
            background: rgba(255,255,255,0.05);
            border: 1px solid var(--border-color);
            color: var(--text-secondary);
            padding: 0.5rem 1rem;
            border-radius: 6px;
            font-size: 0.85rem;
            cursor: pointer;
            transition: all 0.2s ease;
        }
        .filter-btn.active {
            background: var(--primary);
            color: white;
            border-color: var(--primary);
        }
        .filter-btn:hover:not(.active) {
            background: rgba(255,255,255,0.1);
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div>
                <h1 id="book-title">Loading book...</h1>
                <div class="subtitle" id="book-slug">Slug: ...</div>
            </div>
            <a href="/" class="btn-back">← Back to Dashboard</a>
        </header>

        <div id="viewer-container" class="visualizer-card">
            <div class="loader" id="loader">
                <div style="text-align: center;">
                    <div class="loader-spinner" style="margin: 0 auto 1rem auto;"></div>
                    <div>Loading visualizer dataset...</div>
                </div>
            </div>
            <div id="content-area" style="display: none;"></div>
        </div>
    </div>

    <script>
        const slug = "{{ slug }}";
        let isManga = false;
        let bookData = null;
        let currentMangaPage = 0;

        async function fetchBookData() {
            try {
                // First, check list of books to find metadata
                const resBooks = await fetch("/api/books");
                const books = await resBooks.json();
                const book = books.find(b => b.slug === slug);
                if (book) {
                    document.getElementById("book-title").textContent = book.title;
                    document.getElementById("book-slug").textContent = `Author: ${book.authors} | Target: ${book.target_lang.toUpperCase()} | Engine: ${book.tts_engine}`;
                    isManga = book.is_manga || false;
                }

                if (isManga) {
                    const resManga = await fetch(`/api/preview/manga/${slug}`);
                    bookData = await resManga.json();
                    renderManga();
                } else {
                    const resBook = await fetch(`/api/preview/book/${slug}`);
                    bookData = await resBook.json();
                    renderBook();
                }
                
                document.getElementById("loader").style.display = "none";
                document.getElementById("content-area").style.display = "block";
            } catch (err) {
                console.error(err);
                document.getElementById("loader").innerHTML = `<div style="color:var(--danger)">Failed to load preview data. Make sure pipeline has run.</div>`;
            }
        }

        function renderManga() {
            const area = document.getElementById("content-area");
            if (!bookData.source_pages || bookData.source_pages.length === 0) {
                area.innerHTML = `<div style="text-align:center;color:var(--text-secondary);padding:3rem 0;">
                    Сторінок манги не знайдено. Запустіть процес перекладу манги.
                </div>`;
                return;
            }

            const showPage = (idx) => {
                currentMangaPage = idx;
                const srcFile = bookData.source_pages[idx];
                const cleanFile = bookData.cleaned_pages && bookData.cleaned_pages.length > idx ? bookData.cleaned_pages[idx] : null;
                const tgtFile = bookData.translated_pages && bookData.translated_pages.length > idx ? bookData.translated_pages[idx] : null;

                document.getElementById("manga-page-img-src").src = `/api/preview/manga-file/${slug}/source/${srcFile}`;
                document.getElementById("manga-page-title-src").textContent = `Оригінал: ${srcFile}`;

                // Clean Page
                const cleanImg = document.getElementById("manga-page-img-clean");
                const cleanTitle = document.getElementById("manga-page-title-clean");
                const cleanEmpty = document.getElementById("manga-empty-clean");
                if (cleanFile) {
                    cleanImg.src = `/api/preview/manga-file/${slug}/cleaned/${cleanFile}`;
                    cleanImg.style.display = "block";
                    cleanTitle.textContent = `Очищено: ${cleanFile}`;
                    cleanEmpty.style.display = "none";
                } else {
                    cleanImg.style.display = "none";
                    cleanTitle.textContent = "Очищено";
                    cleanEmpty.style.display = "flex";
                }

                // Translated Page
                const tgtImg = document.getElementById("manga-page-img-tgt");
                const tgtTitle = document.getElementById("manga-page-title-tgt");
                const tgtEmpty = document.getElementById("manga-empty-tgt");
                if (tgtFile) {
                    tgtImg.src = `/api/preview/manga-file/${slug}/translated/${tgtFile}`;
                    tgtImg.style.display = "block";
                    tgtTitle.textContent = `Переклад (Українська): ${tgtFile}`;
                    tgtEmpty.style.display = "none";
                } else {
                    tgtImg.style.display = "none";
                    tgtTitle.textContent = "Переклад";
                    tgtEmpty.style.display = "flex";
                }

                document.getElementById("page-indicator").textContent = `Сторінка ${idx + 1} з ${bookData.source_pages.length}`;
                document.getElementById("btn-prev").disabled = idx === 0;
                document.getElementById("btn-next").disabled = idx === bookData.source_pages.length - 1;
            };

            area.innerHTML = `
                <div class="manga-viewer">
                    <div class="manga-panel">
                        <div class="panel-header" id="manga-page-title-src">Оригінал</div>
                        <img id="manga-page-img-src" class="manga-img" src="" alt="Source Page">
                    </div>
                    <div class="manga-panel">
                        <div class="panel-header" id="manga-page-title-clean">Очищено від тексту</div>
                        <div id="manga-empty-clean" style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:50vh; color:var(--text-secondary)">
                            <div>Не очищено</div>
                            <div style="font-size:0.8rem; margin-top:0.5rem">Запустіть процес перекладу манги</div>
                        </div>
                        <img id="manga-page-img-clean" class="manga-img" src="" alt="Clean Page" style="display:none">
                    </div>
                    <div class="manga-panel">
                        <div class="panel-header" id="manga-page-title-tgt">Переклад</div>
                        <div id="manga-empty-tgt" style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:50vh; color:var(--text-secondary)">
                            <div>Не перекладено</div>
                            <div style="font-size:0.8rem; margin-top:0.5rem">Запустіть процес перекладу манги</div>
                        </div>
                        <img id="manga-page-img-tgt" class="manga-img" src="" alt="Translated Page" style="display:none">
                    </div>
                </div>
                <div class="manga-controls">
                    <button class="manga-btn" id="btn-prev">← Назад</button>
                    <span class="page-indicator" id="page-indicator">Сторінка ...</span>
                    <button class="manga-btn" id="btn-next">Вперед →</button>
                </div>
            `;

            document.getElementById("btn-prev").addEventListener("click", () => {
                if (currentMangaPage > 0) showPage(currentMangaPage - 1);
            });
            document.getElementById("btn-next").addEventListener("click", () => {
                if (currentMangaPage < bookData.source_pages.length - 1) showPage(currentMangaPage + 1);
            });

            // Keyboard navigation
            document.addEventListener("keydown", (e) => {
                if (e.key === "ArrowLeft" && currentMangaPage > 0) {
                    showPage(currentMangaPage - 1);
                } else if (e.key === "ArrowRight" && currentMangaPage < bookData.source_pages.length - 1) {
                    showPage(currentMangaPage + 1);
                }
            });

            showPage(0);
        }

        function renderBook() {
            const area = document.getElementById("content-area");
            const isEpub = bookData.epub_available || bookData.is_epub_book;
            const hasParagraphs = bookData.paragraphs && bookData.paragraphs.length > 0;

            // For EPUB books without MD paragraphs — go straight to Full Page Viewer
            if (!hasParagraphs && isEpub) {
                renderEpubOnlyView(area);
                return;
            }

            if (!hasParagraphs && !isEpub) {
                area.innerHTML = `<div style="text-align:center;color:var(--text-secondary);padding:3rem 0;">
                    <div style="font-size:3rem;margin-bottom:1rem;">📚</div>
                    <div style="font-size:1.1rem;margin-bottom:0.5rem;">Немає даних для перегляду</div>
                    <div style="font-size:0.9rem;">Запустіть конвеєр перекладу щоб побачити результат</div>
                </div>`;
                return;
            }

            area.innerHTML = `
                <div class="tabs" style="display: flex; gap: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 1rem; margin-bottom: 1.5rem;">
                    <button class="tab-btn active" id="tab-paragraphs" style="background: none; border: none; color: var(--primary); font-size: 1.1rem; font-weight: 600; cursor: pointer; border-bottom: 2px solid var(--primary); padding: 0.5rem 1rem; outline: none; transition: all 0.2s ease;">📋 Paragraphs & Audio</button>
                    <button class="tab-btn" id="tab-page-viewer" style="background: none; border: none; color: var(--text-secondary); font-size: 1.1rem; font-weight: 600; cursor: pointer; padding: 0.5rem 1rem; border-bottom: 2px solid transparent; outline: none; transition: all 0.2s ease;">📖 Full Page Viewer</button>
                </div>
                <div id="tab-content-area"></div>
            `;

            const tabContent = document.getElementById("tab-content-area");
            const btnParagraphs = document.getElementById("tab-paragraphs");
            const btnPageViewer = document.getElementById("tab-page-viewer");

            btnParagraphs.addEventListener("click", () => {
                btnParagraphs.style.color = "var(--primary)";
                btnParagraphs.style.borderBottomColor = "var(--primary)";
                btnPageViewer.style.color = "var(--text-secondary)";
                btnPageViewer.style.borderBottomColor = "transparent";
                showParagraphsTab();
            });

            btnPageViewer.addEventListener("click", () => {
                btnPageViewer.style.color = "var(--primary)";
                btnPageViewer.style.borderBottomColor = "var(--primary)";
                btnParagraphs.style.color = "var(--text-secondary)";
                btnParagraphs.style.borderBottomColor = "transparent";
                showPageViewerTab();
            });

            function showParagraphsTab() {
                tabContent.innerHTML = `
                    <div class="filters">
                        <button class="filter-btn active" data-filter="all">Show All</button>
                        <button class="filter-btn" data-filter="audio">With Audio Only</button>
                        <button class="filter-btn" data-filter="no-audio">Without Audio Only</button>
                    </div>
                    <div class="book-stages-list" id="paragraphs-list"></div>
                `;

                const list = document.getElementById("paragraphs-list");

                const renderItems = (filter) => {
                    list.innerHTML = "";
                    bookData.paragraphs.forEach((p, idx) => {
                        if (filter === "audio" && !p.has_audio) return;
                        if (filter === "no-audio" && p.has_audio) return;

                        const card = document.createElement("div");
                        card.className = "paragraph-card";
                        card.innerHTML = `
                            <div class="card-meta">
                                <span>Paragraph #${idx + 1} | Hash: ${p.hash.substring(0, 8)}...</span>
                                <span class="badge ${p.has_audio ? 'badge-audio' : 'badge-no-audio'}">
                                    ${p.has_audio ? 'Audio Synthesized' : 'No Audio'}
                                </span>
                            </div>
                            <div class="grid-stages">
                                <div class="stage-box">
                                    <div class="stage-title">Original (RU / EN)</div>
                                    <div class="stage-content">${p.original}</div>
                                </div>
                                <div class="stage-box">
                                    <div class="stage-title">Translated & Accents (UK)</div>
                                    <div class="stage-content stage-stressed">${p.stressed}</div>
                                </div>
                            </div>
                            ${p.has_audio ? `
                            <div class="audio-wrapper">
                                <span class="audio-label">🔊 Listen Segment Preview:</span>
                                <audio controls src="/api/preview/audio/${slug}/${p.hash}"></audio>
                            </div>
                            ` : ''}
                        `;
                        list.appendChild(card);
                    });
                };

                const filters = document.querySelectorAll(".filter-btn");
                filters.forEach(btn => {
                    btn.addEventListener("click", (e) => {
                        filters.forEach(b => b.classList.remove("active"));
                        btn.classList.add("active");
                        renderItems(btn.dataset.filter);
                    });
                });

                renderItems("all");
            }

            async function showPageViewerTab() {
                tabContent.innerHTML = `
                    <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; background: rgba(255,255,255,0.02); padding: 0.8rem; border-radius: 8px; border: 1px solid var(--border-color);">
                        <label for="chapter-select" style="font-weight: 600; color: var(--text-secondary); min-width: 120px;">Select Page/File:</label>
                        <select id="chapter-select" style="background: #18181b; color: white; border: 1px solid var(--border-color); padding: 0.5rem 1rem; border-radius: 6px; flex-grow: 1; outline: none; font-family: inherit; font-size: 0.95rem; cursor: pointer;">
                            <option value="">-- Loading files from EPUB... --</option>
                        </select>
                    </div>
                    <div class="page-split-viewer" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; height: 75vh;">
                        <div class="viewer-panel" style="display: flex; flex-direction: column; background: rgba(0,0,0,0.2); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden; height: 100%;">
                            <div style="padding: 0.8rem; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border-color); font-weight: 600; text-align: center; color: var(--text-secondary);">Original Text</div>
                            <iframe id="iframe-original" style="width: 100%; height: 100%; border: none; background: #09090b;"></iframe>
                        </div>
                        <div class="viewer-panel" style="display: flex; flex-direction: column; background: rgba(0,0,0,0.2); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden; height: 100%;">
                            <div style="padding: 0.8rem; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border-color); font-weight: 600; text-align: center; color: var(--primary);">Translated Text (Ukrainian)</div>
                            <iframe id="iframe-translated" style="width: 100%; height: 100%; border: none; background: #09090b;"></iframe>
                        </div>
                    </div>
                `;

                try {
                    const res = await fetch(`/api/preview/book-chapters/${slug}`);
                    const data = await res.json();
                    if (data.status === "success" && data.chapters) {
                        const select = document.getElementById("chapter-select");
                        select.innerHTML = "";
                        data.chapters.forEach(ch => {
                            const opt = document.createElement("option");
                            opt.value = ch.href;
                            opt.textContent = ch.href;
                            select.appendChild(opt);
                        });

                        select.addEventListener("change", (e) => {
                            if (e.target.value) loadPage(e.target.value);
                        });

                        if (data.chapters.length > 0) {
                            loadPage(data.chapters[0].href);
                        }
                    } else {
                        document.getElementById("chapter-select").innerHTML = `<option value="">Error: ${data.message || 'Failed to parse EPUB'}</option>`;
                    }
                } catch (err) {
                    console.error(err);
                    document.getElementById("chapter-select").innerHTML = `<option value="">Failed to load chapters</option>`;
                }
            }

            async function loadPage(href) {
                const iframeOrig = document.getElementById("iframe-original");
                const iframeTrans = document.getElementById("iframe-translated");
                
                [iframeOrig, iframeTrans].forEach(iframe => {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    doc.open();
                    doc.write(`
                        <body style="background:#09090b; color:#a1a1aa; font-family:sans-serif; display:flex; justify-content:center; align-items:center; height:100vh; margin:0;">
                            <div>Loading content...</div>
                        </body>
                    `);
                    doc.close();
                });

                try {
                    const res = await fetch(`/api/preview/book-page/${slug}/${href}`);
                    const data = await res.json();
                    if (data.status === "success") {
                        let docOrig = iframeOrig.contentDocument || iframeOrig.contentWindow.document;
                        docOrig.open();
                        docOrig.write(data.original_html);
                        docOrig.close();

                        let docTrans = iframeTrans.contentDocument || iframeTrans.contentWindow.document;
                        docTrans.open();
                        docTrans.write(data.translated_html);
                        docTrans.close();
                    } else {
                        throw new Error(data.message || "Failed to load page content");
                    }
                } catch (err) {
                    console.error(err);
                    [iframeOrig, iframeTrans].forEach(iframe => {
                        const doc = iframe.contentDocument || iframe.contentWindow.document;
                        doc.open();
                        doc.write(`
                            <body style="background:#09090b; color:#ef4444; font-family:sans-serif; padding:20px;">
                                <h3>Failed to load page content</h3>
                                <p>${err.message}</p>
                            </body>
                        `);
                        doc.close();
                    });
                }
            }

            // For EPUB books — default to Full Page Viewer tab
            if (bookData.is_epub_book || bookData.epub_available) {
                showPageViewerTab();
                btnPageViewer.style.color = "var(--primary)";
                btnPageViewer.style.borderBottomColor = "var(--primary)";
                btnParagraphs.style.color = "var(--text-secondary)";
                btnParagraphs.style.borderBottomColor = "transparent";
            } else {
                showParagraphsTab();
            }
        }

        async function renderEpubOnlyView(area) {
            // Show stats banner + Full Page Viewer for pure EPUB books
            const stats = bookData.cache_stats || {};
            const pct = stats.percent || 0;
            const currentFile = stats.current_file || 0;
            const totalFiles = stats.total_files || 0;
            const translatedBlocks = stats.translated_blocks || 0;

            area.innerHTML = `
                <div style="background: rgba(139,92,246,0.08); border: 1px solid rgba(139,92,246,0.25); border-radius: 12px; padding: 1.2rem 1.5rem; margin-bottom: 1.5rem; display: flex; align-items: center; gap: 1.5rem; flex-wrap: wrap;">
                    <div style="flex: 1; min-width: 200px;">
                        <div style="font-size: 0.8rem; color: var(--text-secondary); margin-bottom: 0.3rem;">Прогрес перекладу EPUB</div>
                        <div style="font-size: 1.4rem; font-weight: 700; color: var(--primary);">${pct.toFixed(1)}%</div>
                        <div style="font-size: 0.85rem; color: var(--text-secondary); margin-top:0.2rem;">Файл ${currentFile}/${totalFiles} · ${translatedBlocks} блоків у кеші</div>
                    </div>
                    <div style="flex: 2; min-width: 200px;">
                        <div style="background: rgba(255,255,255,0.05); border-radius: 6px; height: 8px; overflow: hidden;">
                            <div style="background: linear-gradient(90deg, var(--primary), #3b82f6); height: 100%; width: ${Math.min(pct,100)}%; border-radius: 6px; transition: width 0.5s ease;"></div>
                        </div>
                    </div>
                    <div>
                        <span style="font-size: 0.8rem; color: #10b981; background: rgba(16,185,129,0.1); padding: 0.3rem 0.8rem; border-radius: 20px; border: 1px solid rgba(16,185,129,0.2);">📖 EPUB Book</span>
                    </div>
                </div>

                <div class="tabs" style="display: flex; gap: 1rem; border-bottom: 1px solid var(--border-color); padding-bottom: 1rem; margin-bottom: 1.5rem;">
                    <button class="tab-btn active" id="tab-page-viewer-only" style="background: none; border: none; color: var(--primary); font-size: 1.1rem; font-weight: 600; cursor: pointer; border-bottom: 2px solid var(--primary); padding: 0.5rem 1rem; outline: none; transition: all 0.2s ease;">📖 Переклад по сторінках</button>
                </div>
                <div id="epub-page-viewer-area"></div>
            `;

            await loadEpubPageViewer(document.getElementById("epub-page-viewer-area"));
        }

        async function loadEpubPageViewer(container) {
            container.innerHTML = `
                <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1.5rem; background: rgba(255,255,255,0.02); padding: 0.8rem; border-radius: 8px; border: 1px solid var(--border-color);">
                    <label for="chapter-select-epub" style="font-weight: 600; color: var(--text-secondary); min-width: 140px;">📄 Файл розділу:</label>
                    <select id="chapter-select-epub" style="background: #18181b; color: white; border: 1px solid var(--border-color); padding: 0.5rem 1rem; border-radius: 6px; flex-grow: 1; outline: none; font-family: inherit; font-size: 0.95rem; cursor: pointer;">
                        <option value="">⏳ Завантаження файлів EPUB...</option>
                    </select>
                </div>
                <div class="page-split-viewer" style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; height: 75vh;">
                    <div class="viewer-panel" style="display: flex; flex-direction: column; background: rgba(0,0,0,0.2); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden; height: 100%;">
                        <div style="padding: 0.8rem; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border-color); font-weight: 600; text-align: center; color: var(--text-secondary);">🔤 Оригінал</div>
                        <iframe id="iframe-original-epub" style="width: 100%; height: 100%; border: none; background: #09090b;"></iframe>
                    </div>
                    <div class="viewer-panel" style="display: flex; flex-direction: column; background: rgba(0,0,0,0.2); border-radius: 10px; border: 1px solid var(--border-color); overflow: hidden; height: 100%;">
                        <div style="padding: 0.8rem; background: rgba(255,255,255,0.03); border-bottom: 1px solid var(--border-color); font-weight: 600; text-align: center; color: var(--primary);">🇺🇦 Переклад (Українська)</div>
                        <iframe id="iframe-translated-epub" style="width: 100%; height: 100%; border: none; background: #09090b;"></iframe>
                    </div>
                </div>
            `;

            try {
                const res = await fetch(`/api/preview/book-chapters/${slug}`);
                const data = await res.json();
                if (data.status === "success" && data.chapters) {
                    const select = document.getElementById("chapter-select-epub");
                    select.innerHTML = "";
                    data.chapters.forEach(ch => {
                        const opt = document.createElement("option");
                        opt.value = ch.href;
                        opt.textContent = ch.href;
                        select.appendChild(opt);
                    });
                    select.addEventListener("change", e => { if (e.target.value) loadEpubPage(e.target.value); });
                    if (data.chapters.length > 0) loadEpubPage(data.chapters[0].href);
                } else {
                    document.getElementById("chapter-select-epub").innerHTML = `<option>❌ ${data.message || 'Не вдалося завантажити розділи'}</option>`;
                }
            } catch(err) {
                document.getElementById("chapter-select-epub").innerHTML = `<option>❌ Помилка: ${err.message}</option>`;
            }
        }

        async function loadEpubPage(href) {
            const iframeOrig = document.getElementById("iframe-original-epub");
            const iframeTrans = document.getElementById("iframe-translated-epub");
            if (!iframeOrig || !iframeTrans) return;

            [iframeOrig, iframeTrans].forEach(iframe => {
                const doc = iframe.contentDocument || iframe.contentWindow.document;
                doc.open();
                doc.write(`<body style="background:#09090b;color:#a1a1aa;font-family:sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;margin:0;"><div>⏳ Завантаження...</div></body>`);
                doc.close();
            });

            try {
                const res = await fetch(`/api/preview/book-page/${slug}/${href}`);
                const data = await res.json();
                if (data.status === "success") {
                    let docO = iframeOrig.contentDocument || iframeOrig.contentWindow.document;
                    docO.open(); docO.write(data.original_html); docO.close();
                    let docT = iframeTrans.contentDocument || iframeTrans.contentWindow.document;
                    docT.open(); docT.write(data.translated_html); docT.close();
                } else {
                    throw new Error(data.message || "Не вдалося завантажити сторінку");
                }
            } catch(err) {
                [iframeOrig, iframeTrans].forEach(iframe => {
                    const doc = iframe.contentDocument || iframe.contentWindow.document;
                    doc.open();
                    doc.write(`<body style="background:#09090b;color:#ef4444;font-family:sans-serif;padding:20px;"><h3>Помилка</h3><p>${err.message}</p></body>`);
                    doc.close();
                });
            }
        }

        fetchBookData();
    </script>
</body>
</html>"""
    return render_template_string(html_content, slug=slug)

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
    for possible_ext in [".cbz", ".cbr", ".cb7", ".zip", ".rar", ".pdf"]:
        if os.path.exists(os.path.join(paths["book_dir"], f"{slug}{possible_ext}")):
            source_ext = possible_ext
            break
            
    if not source_ext:
        return jsonify({"status": "error", "message": "Manga source file not found"}), 400
        
    source_file = os.path.join(paths["book_dir"], f"{slug}{source_ext}")
    translated_file = os.path.join(paths["book_dir"], "output", f"{slug}_translated_{cfg.get('target_lang', 'uk')}.cbz")
    
    preview_cache = os.path.join(paths["book_dir"], "preview_cache")
    os.makedirs(preview_cache, exist_ok=True)
    
    # 1. Source pages extraction
    src_preview_dir = os.path.join(preview_cache, "source")
    os.makedirs(src_preview_dir, exist_ok=True)
    if not os.listdir(src_preview_dir):
        try:
            if source_ext in [".zip", ".cbz"]:
                subprocess.run(["unzip", "-j", source_file, "*.png", "*.jpg", "*.jpeg", "-d", src_preview_dir], capture_output=True)
            elif source_ext in [".rar", ".cbr"]:
                subprocess.run(["unrar", "e", source_file, "-d", src_preview_dir], capture_output=True)
            elif source_ext == ".pdf":
                subprocess.run(["pdftoppm", "-png", "-f", "1", "-l", "5", "-r", "100", source_file, os.path.join(src_preview_dir, "page")], capture_output=True)
        except Exception:
            pass
            
    # 2. Cleaned pages extraction (copying from books/slug/cleaned/)
    cleaned_preview_dir = os.path.join(preview_cache, "cleaned")
    os.makedirs(cleaned_preview_dir, exist_ok=True)
    actual_cleaned_dir = os.path.join(paths["book_dir"], "cleaned")
    if os.path.exists(actual_cleaned_dir) and not os.listdir(cleaned_preview_dir):
        try:
            for f in os.listdir(actual_cleaned_dir):
                if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
                    shutil.copy(os.path.join(actual_cleaned_dir, f), os.path.join(cleaned_preview_dir, f))
        except Exception:
            pass
            
    # 3. Translated pages extraction
    tgt_preview_dir = os.path.join(preview_cache, "translated")
    os.makedirs(tgt_preview_dir, exist_ok=True)
    if os.path.exists(translated_file) and not os.listdir(tgt_preview_dir):
        try:
            subprocess.run(["unzip", "-j", translated_file, "*.png", "*.jpg", "*.jpeg", "-d", tgt_preview_dir], capture_output=True)
        except Exception:
            pass
            
    from natsort import natsorted
    src_files = natsorted([f for f in os.listdir(src_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    clean_files = natsorted([f for f in os.listdir(cleaned_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    tgt_files = natsorted([f for f in os.listdir(tgt_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))])
    
    return jsonify({
        "status": "success",
        "source_pages": src_files[:10],
        "cleaned_pages": clean_files[:10],
        "translated_pages": tgt_files[:10]
    })

@app.route("/api/preview/manga-file/<slug>/<folder>/<filename>")
@auth.login_required
def serve_manga_preview_file(slug, folder, filename):
    if not validate_slug(slug) or folder not in ["source", "translated", "cleaned"]:
        return "Invalid parameters", 400
    paths = resolve_book_paths(repo_dir, slug)
    file_path = os.path.join(paths["book_dir"], "preview_cache", folder, filename)
    if os.path.exists(file_path):
        return send_file(file_path)
    return "Not found", 404

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
        
    paragraphs = []
    if os.path.exists(target_md_file):
        try:
            with open(target_md_file, "r", encoding="utf-8") as f:
                content = f.read()
            raw_paragraphs = re.split(r'\n\s*\n', content)
            
            max_chunk_chars = 150 if tts_engine == "styletts2" else 1000
            
            count = 0
            for p in raw_paragraphs:
                p = p.strip()
                if not p or p.startswith("#"):
                    continue
                chunks = split_paragraph_to_chunks(p, max_chars=max_chunk_chars)
                for chunk in chunks:
                    chunk = chunk.strip()
                    if not chunk:
                        continue
                    h = get_hash(chunk)
                    
                    original = ""
                    for k, v in trans_cache.items():
                        if v.strip() == chunk:
                            original = k
                            break
                    if not original:
                        original = chunk
                        
                    stressed = stress_cache.get(h, chunk)
                    has_audio = os.path.exists(os.path.join(chunks_dir, f"{h}.wav"))
                    
                    paragraphs.append({
                        "hash": h,
                        "original": original,
                        "translated": chunk,
                        "stressed": stressed,
                        "has_audio": has_audio
                    })
                    count += 1
                    if count >= 30:
                        break
                if count >= 30:
                    break
        except Exception as e:
            return jsonify({"status": "error", "message": f"Error parsing book: {e}"}), 500
            
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
        
        def inject_style(html_str):
            if "</head>" in html_str:
                return html_str.replace("</head>", f"{style_inject}</head>")
            elif "<body>" in html_str:
                return html_str.replace("<body>", f"<body>{style_inject}")
            else:
                return style_inject + html_str
                
        orig_html = inject_style(orig_html)
        trans_html = inject_style(trans_html)
        
        return jsonify({
            "status": "success",
            "original_html": orig_html,
            "translated_html": trans_html
        })
    except Exception as e:
        return jsonify({"status": "error", "message": f"Error loading book page: {e}"}), 500

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KBG Web Service Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the dashboard on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Run in Flask debug mode")
    args = parser.parse_args()
    
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)

