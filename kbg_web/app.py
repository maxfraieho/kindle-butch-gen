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

app = Flask(__name__)

# Registry of active background processes: {slug: subprocess.Popen}
active_processes = {}

def validate_slug(slug):
    return bool(re.match(r"^[a-z0-9_-]+$", slug))

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
                <form id="addBookForm">
                    <div class="form-group">
                        <label for="slug">Book Slug (lowercase, a-z0-9_-)</label>
                        <input type="text" id="slug" class="form-control" placeholder="e.g. clean-code" required pattern="^[a-z0-9_-]+$">
                    </div>
                    <div class="form-group">
                        <label for="pdf_path">Source PDF Path (on system)</label>
                        <input type="text" id="pdf_path" class="form-control" placeholder="e.g. /path/to/book.pdf" required>
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
                        <label for="lang">Target Language</label>
                        <select id="lang" class="form-control" required>
                            <option value="uk">Ukrainian (uk)</option>
                            <option value="en">English (en)</option>
                            <option value="ru">Russian (ru)</option>
                        </select>
                    </div>
                    <button type="submit" class="btn btn-primary" style="width: 100%;">Add Book</button>
                </form>
            </div>

            <!-- Right Column: Books List -->
            <div class="glass-card">
                <h2 class="card-title">Manage Books</h2>
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

        document.getElementById('addBookForm').addEventListener('submit', async function(e) {
            e.preventDefault();
            const slug = document.getElementById('slug').value.trim();
            const pdf_path = document.getElementById('pdf_path').value.trim();
            const title = document.getElementById('title').value.trim();
            const authors = document.getElementById('authors').value.trim();
            const lang = document.getElementById('lang').value;

            try {
                const response = await fetch('/api/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ slug, pdf_path, title, authors, lang })
                });
                const res = await response.json();
                if (response.ok) {
                    alert('Book added successfully!');
                    document.getElementById('addBookForm').reset();
                    fetchBooks();
                } else {
                    alert('Error: ' + res.message);
                }
            } catch (err) {
                alert('Request failed: ' + err.message);
            }
        });

        async function fetchBooks() {
            try {
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

                            <div class="controls">
                                ${book.is_running 
                                    ? `<button onclick="stopConversion('${book.slug}')" class="btn btn-danger">Stop Conversion</button>`
                                    : `<button onclick="runConversion('${book.slug}')" class="btn btn-success">Run Conversion</button>`
                                }
                                <button onclick="selectBookForLogs('${book.slug}', '${book.title}')" class="btn btn-secondary">Console Logs</button>
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

        // Initial load
        fetchBooks();
        // Periodically refresh book states to update progress bars
        setInterval(fetchBooks, 5000);
    </script>
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
                prog = {"marker_percent": 0.0, "translation_percent": 0.0, "tts_percent": 0.0}
                
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
                "output_files": sorted(output_files)
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
            "page_ranges": [[1, pages]]
        }
        
        with open(paths["config_path"], "w", encoding="utf-8") as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
            
        return jsonify({"status": "success", "message": f"Book '{slug}' added successfully with {pages} pages."})
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
    
    # Construct subprocess command securely (list of arguments, shell=False)
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

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="KBG Web Service Dashboard")
    parser.add_argument("--port", type=int, default=5000, help="Port to run the dashboard on (default: 5000)")
    parser.add_argument("--debug", action="store_true", help="Run in Flask debug mode")
    args = parser.parse_args()
    
    app.run(host="127.0.0.1", port=args.port, debug=args.debug)
