# API Контракт: Flask Backend ↔ React Frontend

> Повний перелік API endpoints, які React SPA має використовувати
> для комунікації з Flask backend. Всі endpoints вже існують
> у поточному `kbg_web/app.py`.

---

## Зміни у Flask Backend

Для підтримки React SPA потрібні **мінімальні** зміни у `app.py`:

### 1. SPA Catch-All Route

```python
# Додати в кінець app.py ПІСЛЯ всіх інших маршрутів

@app.route('/', defaults={'path': ''})
@app.route('/<path:path>')
def spa_fallback(path):
    """Serve React SPA for all non-API routes."""
    if path.startswith('api/'):
        return jsonify({"status": "error", "message": "Not found"}), 404
    
    # Serve React SPA index.html
    dist_dir = os.path.join(os.path.dirname(__file__), 'static', 'dist')
    index_path = os.path.join(dist_dir, 'index.html')
    
    if os.path.exists(index_path):
        return send_file(index_path)
    
    # Fallback to legacy Jinja2 templates during migration
    return redirect(url_for('dashboard'))
```

### 2. Login Endpoint (JSON)

Поточний `/login` повертає HTML. Додати JSON-версію:

```python
@app.route('/api/auth/login', methods=['POST'])
def api_login():
    data = request.get_json(silent=True) or {}
    username = data.get('username', '')
    password = data.get('password', '')
    if verify_password(username, password):
        session.clear()
        session['user'] = username
        session.permanent = True
        return jsonify({"status": "ok", "user": username})
    return jsonify({"status": "error", "message": "Invalid credentials"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route('/api/auth/check', methods=['GET'])
def api_auth_check():
    user = session.get('user')
    if user and user in users_data:
        return jsonify({"authenticated": True, "user": user})
    return jsonify({"authenticated": False}), 401
```

### 3. Static файли Vite

```python
# Додати у вже існуючий Flask static config або окремо:
@app.route('/assets/<path:filename>')
def vite_assets(filename):
    dist_dir = os.path.join(os.path.dirname(__file__), 'static', 'dist', 'assets')
    return send_from_directory(dist_dir, filename)
```

---

## Повна карта API Endpoints

### Аутентифікація

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| POST | `/api/auth/login` | `{username, password}` | `{status, user}` |
| POST | `/api/auth/logout` | — | `{status}` |
| GET | `/api/auth/check` | — | `{authenticated, user}` |
| POST | `/api/change-password` | `{old_password, new_password}` | `{status}` |

### Книги (CRUD)

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/books` | — | `[{slug, title, author, lang, status, ...}]` |
| POST | `/api/add` | `{slug, title, authors, lang, ...}` | `{status, message}` |
| POST | `/api/upload` | `multipart/form-data` | `{detected_title, detected_slug, detected_authors, detected_lang}` |
| POST | `/api/parse-metadata` | `{path}` | `{detected_title, ...}` |
| DELETE | `/api/delete/<slug>` | — | `{status}` |

### Конвертація

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| POST | `/api/run/<slug>` | — | `{status, message}` |
| POST | `/api/stop/<slug>` | — | `{status}` |
| GET | `/api/status/<slug>` | — | `{status, progress, current_stage, ...}` |
| POST | `/api/resume-stalled/<slug>` | — | `{status}` |

### Файли та Завантаження

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/download/<slug>/<filename>` | — | Binary file |
| DELETE | `/api/delete-file/<slug>/<filename>` | — | `{status}` |
| GET | `/api/downloads` | — | `[{slug, files: [...]}]` |
| GET | `/api/browse-fs` | `?path=...` | `{current, parent, dirs}` |

### Налаштування

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/settings` | — | `{output_root, ...}` |
| POST | `/api/settings/output-root` | `{path}` | `{status}` |
| GET | `/api/book-settings/<slug>` | — | `{tts_voice, tts_speaker_id, ...}` |
| POST | `/api/book-settings/<slug>` | `{...settings}` | `{status}` |
| GET | `/api/tts-settings/<slug>` | — | `{voice, speaker_id, speed}` |
| POST | `/api/tts-settings/<slug>` | `{voice, speaker_id, speed}` | `{status}` |
| GET | `/api/tts-preview/<slug>` | — | Audio binary |

### Персонажі (Cast Registry)

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/characters/<slug>` | — | `[{id, name, gender, ...}]` |
| PUT | `/api/characters/<slug>` | `[{id, name, gender, ...}]` | `{status}` |
| POST | `/api/characters/<slug>/scan` | — | `{status}` |
| GET | `/api/characters/<slug>/scan-progress` | — | `{progress, found_count}` |
| POST | `/api/characters/<slug>/scan/stop` | — | `{status}` |
| GET | `/api/characters/<slug>/settings` | — | `{auto_scan, ...}` |
| POST | `/api/characters/<slug>/settings` | `{...settings}` | `{status}` |
| GET | `/api/characters/<slug>/thumbnail/<char_id>` | — | Image binary |

### Редагування (Live Editing)

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/edit/queue/<slug>` | — | `[{edit_id, chunk_hash, original, translated, ...}]` |
| POST | `/api/edit/text/<slug>/<chunk_hash>` | `{text}` | `{status}` |
| POST | `/api/edit/approve/<slug>/<edit_id>` | — | `{status}` |
| POST | `/api/edit/discard/<slug>/<edit_id>` | — | `{status}` |
| GET | `/api/edit/stress/<slug>/<chunk_hash>` | — | `{stressed_text}` |
| POST | `/api/edit/stress/discard/<slug>/<chunk_hash>` | — | `{status}` |
| POST | `/api/edit/regenerate-audio/<slug>/<chunk_hash>` | — | `{status}` |
| POST | `/api/edit/regenerate-manga-page/<slug>/<page>` | — | `{status}` |
| GET | `/api/edit/manga-bbox/<slug>/<page>` | — | `{bubbles: [{x,y,w,h,...}]}` |
| POST | `/api/edit/manga-text/<slug>/<page>` | `{bubble_id, text}` | `{status}` |

### Прев'ю контенту

| Метод | Endpoint | Response |
|-------|----------|----------|
| GET | `/api/preview/book/<slug>` | `{paragraphs, total_pages, ...}` |
| GET | `/api/preview/book-page/<slug>/<href>` | HTML content |
| GET | `/api/preview/book-chapters/<slug>` | `{chapters: [...]}` |
| GET | `/api/preview/audio/<slug>/<chunk_hash>` | Audio binary |
| GET | `/api/preview/manga/<slug>` | `{pages: [...]}` |
| GET | `/api/preview/manga-bubbles/<slug>/<page>` | `{bubbles: [...]}` |
| GET | `/api/preview/manga-file/<slug>/<folder>/<file>` | Image binary |
| GET | `/api/preview/manga-quality-flags/<slug>` | `{flags: [...]}` |
| GET | `/api/preview/asr-quality-flags/<slug>` | `{flags: [...]}` |
| POST | `/api/manga/<slug>/bubble-tone` | `{bubble_id, tone}` |

### AI Моделі

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/models` | — | `{server_status, available_models, translation_model}` |
| POST | `/api/models/configure` | `{model}` | `{status}` |
| POST | `/api/models/start` | — | `{status}` |
| POST | `/api/models/stop` | — | `{status}` |
| POST | `/api/premium/download-models` | `{model}` | `{status}` |
| GET | `/api/premium/models-status` | — | `{models: [...]}` |
| GET | `/api/premium/model-status` | — | `{model, status, progress}` |

### Режими та Система

| Метод | Endpoint | Request | Response |
|-------|----------|---------|----------|
| GET | `/api/mode` | — | `{mode, profile}` |
| POST | `/api/mode/switch` | `{mode, dry_run}` | `{status, message}` |
| POST | `/api/update` | — | `{status}` |
| GET | `/api/support/profile` | — | `{...profile}` |
| POST | `/api/support/link-telegram` | `{token}` | `{status}` |
| POST | `/api/support/local-optout` | `{optout}` | `{status}` |

---

## Vite Конфігурація

```typescript
// frontend/vite.config.ts
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: '../kbg_web/static/dist',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://localhost:5000',
      '/static': 'http://localhost:5000',
    },
  },
});
```

---

## Порядок міграції маршрутів

Flask views → React Router:

| Flask Route | React Route | Пріоритет |
|-------------|-------------|-----------|
| `/login` | `/login` | P0 (першим) |
| `/` (dashboard) | `/` | P0 |
| `/downloads` | `/downloads` | P1 |
| `/view/<slug>` | `/view/:slug` | P1 |
| `/manual` | `/manual` | P2 |
| `/modes` | `/modes` | P2 |
