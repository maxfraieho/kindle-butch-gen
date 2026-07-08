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
                        body: JSON.stringify({ slug, pdf_path, title, authors, lang })
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
                    
                    return `
                        <div class="glass-card book-card">
                            <div class="book-header">
                                <div class="book-info">
                                    <h3>${book.title}</h3>
                                    <p>by ${book.authors} | Slug: <code>${book.slug}</code> | Lang: ${book.target_lang}</p>
                                </div>
                                <span class="badge ${badgeClass}">${badgeText}</span>
                            </div>

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

                            <div class="options-group" id="opts-${book.slug}">
                                <label class="option-checkbox"><input type="checkbox" id="clean-${book.slug}"> Clean</label>
                                <label class="option-checkbox"><input type="checkbox" id="notrans-${book.slug}"> No Translate</label>
                                <label class="option-checkbox"><input type="checkbox" id="noebook-${book.slug}"> No Ebook</label>
                                <label class="option-checkbox"><input type="checkbox" id="noaudio-${book.slug}"> No Audio</label>
                            </div>

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
            const clean = document.getElementById(`clean-${slug}`).checked;
            const no_translate = document.getElementById(`notrans-${slug}`).checked;
            const no_ebook = document.getElementById(`noebook-${slug}`).checked;
            const no_audio = document.getElementById(`noaudio-${slug}`).checked;

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
            
            document.getElementById("fsCurrentPath").textContent = path;
            
            try {
                const res = await fetch(`/api/browse-fs?path=${encodeURIComponent(path)}`);
                const data = await res.json();
                
                if (data.error) {
                    listEl.innerHTML = `<p style="padding: 1rem; color: var(--danger); text-align: center;">${data.error}</p>`;
                    return;
                }
                
                activeFsPath = data.current;
                parentFsPath = data.parent;
                
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
            
            try {
                const res = await fetch("/api/settings/output-root", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({ path: activeFsPath })
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
                    <label style="font-size: 0.8rem; color: var(--text-secondary); font-weight: 500;">Currently selected path:</label>
                    <div class="fs-path-container" id="fsCurrentPath">/storage/emulated/0</div>
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
                    
            # Calculate progress
            prog = calculate_progress(entry)
            if "error" in prog:
                prog = {"marker_percent": 0.0, "translation_percent": 0.0, "stress_percent": 0.0, "tts_percent": 0.0}
                
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
    
    if not slug or not pdf_path or not title or not authors or not lang:
        return jsonify({"status": "error", "message": "All fields are required"}), 400
        
    if not validate_slug(slug):
        return jsonify({"status": "error", "message": "Invalid slug format"}), 400
        
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
        
        # Copy PDF
        dest_pdf = os.path.join(book_dir, f"{slug}.pdf")
        shutil.copy2(pdf_path, dest_pdf)
        
        # Detect page count
        pages = get_pdf_page_count(dest_pdf)
        
        # Write config.json
        config_data = {
            "slug": slug,
            "title": title,
            "authors": authors,
            "source_lang": "ru",
            "target_lang": lang,
            "pdf_path": f"books/{slug}/{slug}.pdf",
            "generate_audiobook": True,
            "tts_voice": "ukrainian_tts",
            "tts_voice_quality": "medium",
            "tts_speaker_id": 2,
            "tts_speed": 1.0,
            "tts_noise_scale": 0.667,
            "tts_noise_w": 0.8,
            "page_ranges": [[1, pages]]
        }
        
        with open(paths["config_path"], "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": f"Book '{slug}' added successfully with {pages} pages."})
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
    manga_extensions = [".cbz", ".cbr", ".cb7", ".zip", ".rar"]
    if ext not in [".pdf", ".epub", ".txt", ".md"] + manga_extensions:
        return jsonify({"status": "error", "message": f"Unsupported file extension '{ext}'"}), 400
        
    try:
        book_dir = paths["book_dir"]
        os.makedirs(book_dir, exist_ok=True)
        os.makedirs(paths["cache_dir"], exist_ok=True)
        os.makedirs(paths["batches_dir"], exist_ok=True)
        os.makedirs(paths["translated_dir"], exist_ok=True)
        os.makedirs(paths["output_dir"], exist_ok=True)
        os.makedirs(paths["audio_dir"], exist_ok=True)
        
        pdf_path = ""
        page_ranges = []
        
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
            
        is_manga = ext in manga_extensions or request.form.get("is_manga", "false").lower() == "true"
        
        if is_manga and ext in manga_extensions:
            dest_manga = os.path.join(book_dir, f"{slug}{ext}")
            uploaded_file.save(dest_manga)
            
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
        
    # Check if already running
    if slug in active_processes:
        proc = active_processes[slug]
        if proc.poll() is None:
            return jsonify({"status": "error", "message": "Conversion is already running"}), 400
            
    data = request.get_json() or {}
    
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
        for possible_ext in [".cbz", ".cbr", ".cb7", ".zip", ".rar", ".pdf"]:
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
            grid-template-columns: 1fr 1fr;
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
                    No manga pages found. Run the Manga Translation pipeline first.
                </div>`;
                return;
            }

            const showPage = (idx) => {
                currentMangaPage = idx;
                const srcFile = bookData.source_pages[idx];
                const tgtFile = bookData.translated_pages && bookData.translated_pages.length > idx ? bookData.translated_pages[idx] : null;

                document.getElementById("manga-page-img-src").src = `/api/preview/manga-file/${slug}/source/${srcFile}`;
                document.getElementById("manga-page-title-src").textContent = `Original Page: ${srcFile}`;

                const tgtImg = document.getElementById("manga-page-img-tgt");
                const tgtTitle = document.getElementById("manga-page-title-tgt");

                if (tgtFile) {
                    tgtImg.src = `/api/preview/manga-file/${slug}/translated/${tgtFile}`;
                    tgtImg.style.display = "block";
                    tgtTitle.textContent = `Translated Page (Ukrainian): ${tgtFile}`;
                    document.getElementById("manga-empty-tgt").style.display = "none";
                } else {
                    tgtImg.style.display = "none";
                    tgtTitle.textContent = "Translated Page";
                    document.getElementById("manga-empty-tgt").style.display = "flex";
                }

                document.getElementById("page-indicator").textContent = `Page ${idx + 1} of ${bookData.source_pages.length}`;
                document.getElementById("btn-prev").disabled = idx === 0;
                document.getElementById("btn-next").disabled = idx === bookData.source_pages.length - 1;
            };

            area.innerHTML = `
                <div class="manga-viewer">
                    <div class="manga-panel">
                        <div class="panel-header" id="manga-page-title-src">Original Page</div>
                        <img id="manga-page-img-src" class="manga-img" src="" alt="Source Page">
                    </div>
                    <div class="manga-panel">
                        <div class="panel-header" id="manga-page-title-tgt">Translated Page</div>
                        <div id="manga-empty-tgt" style="display:flex; flex-direction:column; justify-content:center; align-items:center; height:50vh; color:var(--text-secondary)">
                            <div>Not translated yet</div>
                            <div style="font-size:0.8rem; margin-top:0.5rem">Start manga translation pipeline in dashboard</div>
                        </div>
                        <img id="manga-page-img-tgt" class="manga-img" src="" alt="Translated Page" style="display:none">
                    </div>
                </div>
                <div class="manga-controls">
                    <button class="manga-btn" id="btn-prev">← Previous</button>
                    <span class="page-indicator" id="page-indicator">Page ...</span>
                    <button class="manga-btn" id="btn-next">Next →</button>
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
            if (!bookData.paragraphs || bookData.paragraphs.length === 0) {
                area.innerHTML = `<div style="text-align:center;color:var(--text-secondary);padding:3rem 0;">
                    No paragraphs found. Run the translation pipeline first.
                </div>`;
                return;
            }

            area.innerHTML = `
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
            
    tgt_preview_dir = os.path.join(preview_cache, "translated")
    os.makedirs(tgt_preview_dir, exist_ok=True)
    if os.path.exists(translated_file) and not os.listdir(tgt_preview_dir):
        try:
            subprocess.run(["unzip", "-j", translated_file, "*.png", "*.jpg", "*.jpeg", "-d", tgt_preview_dir], capture_output=True)
        except Exception:
            pass
            
    from natsort import natsorted
    src_files = natsorted([f for f in os.listdir(src_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
    tgt_files = natsorted([f for f in os.listdir(tgt_preview_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg'))])
    
    return jsonify({
        "status": "success",
        "source_pages": src_files[:10],
        "translated_pages": tgt_files[:10]
    })

@app.route("/api/preview/manga-file/<slug>/<folder>/<filename>")
@auth.login_required
def serve_manga_preview_file(slug, folder, filename):
    if not validate_slug(slug) or folder not in ["source", "translated"]:
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
            
    return jsonify({
        "status": "success",
        "tts_engine": tts_engine,
        "paragraphs": paragraphs
    })

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KBG Web Service Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the dashboard on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Run in Flask debug mode")
    args = parser.parse_args()
    
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)

