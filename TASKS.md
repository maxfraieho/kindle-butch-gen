# Tasks Log

## [x] TASK-1: Refactor Codebase & Consolidate Utilities
* **Problem:** `get_hash`, `split_into_segments`, and `to_xml_format` were duplicated across 5 different scripts, violating DRY.
* **Solution:** Extracted them into [common/utils.py](file:///data/data/com.termux/files/home/kindle-butch-gen/common/utils.py) and updated imports in:
  * [translate_epub.py](file:///data/data/com.termux/files/home/kindle-butch-gen/translate_epub.py)
  * [translate_stage.py](file:///data/data/com.termux/files/home/kindle-butch-gen/translate_stage.py)
  * [audio_stage.py](file:///data/data/com.termux/files/home/kindle-butch-gen/audio_stage.py)
  * [clean_cache.py](file:///data/data/com.termux/files/home/kindle-butch-gen/clean_cache.py)
  * [kbg_web/app.py](file:///data/data/com.termux/files/home/kindle-butch-gen/kbg_web/app.py)
* **Verification:** Compiled all files successfully.

## [x] TASK-2: Extract Inline Templates & Apply UI/UX Polish
* **Problem:** Monolithic `kbg_web/app.py` contained inline HTML string templates, and transitions had default/linear easings with bad hover/active properties and broken modal overlay fade animations.
* **Solution:**
  * Created `kbg_web/templates/` folder.
  * Extracted dashboard HTML to [kbg_web/templates/dashboard.html](file:///data/data/com.termux/files/home/kindle-butch-gen/kbg_web/templates/dashboard.html).
  * Extracted visualizer HTML to [kbg_web/templates/stages.html](file:///data/data/com.termux/files/home/kindle-butch-gen/kbg_web/templates/stages.html).
  * Replaced transitions with hardware-accelerated, specific CSS properties using custom snappy ease curves (`cubic-bezier(0.23, 1, 0.32, 1)`).
  * Fixed the modal display:none transition bug using `pointer-events: none` and `opacity` properties.
  * Added responsive `@media (hover: hover) and (pointer: fine)` gates for touch/mobile devices.
  * Added organic staggered entry animations for book lists and visualizer cards.
  * Refactored [kbg_web/app.py](file:///data/data/com.termux/files/home/kindle-butch-gen/kbg_web/app.py) to use Flask's `render_template` instead of `render_template_string`.

## [x] TASK-3: Fix llama-server CLI Argument
* **Problem:** `start-translation-server.sh` used obsolete `--n-parallel 1` argument, causing newer versions of llama-server to crash.
* **Solution:** Replaced with `--parallel 1` in `~/start-translation-server.sh`.

## [x] TASK-4: UI/UX Labeling & Checkbox Logic
* **Problem:** Чекбокси стадій у `dashboard.html` використовують подвійне заперечення (`id="noaudio-${book.slug}"`), що плутає оператора.
* **Solution:** Перейменувати лейбли на позитивні (напр. "Generate Audio", "Build Ebook"). У JS-функції `runConversion` зчитувати їхній стан, інвертувати його (`const no_audio = !document.getElementById(...)`) і лише після цього відправляти у payload `/api/run/<slug>`.
* **Verification:** Перевірити правильність інвертування булевих значень та відправки payload, щоб не зламати контракт з `app.py` (де очікується `no_audio`).
* **Type:** `direct`

## [x] TASK-5: Focus Flow & Layout Refactoring
* **Problem:** Форма додавання книги займає перший екран на мобільному телефоні, прогрес-бари з'їдають вертикальний простір, термінал відірваний від контексту книги.
* **Solution:**
  1. Перенести `<form id="addBookForm">` у модальне вікно (перевикористати існуючий клас `.modal-overlay`).
  2. Згорнути 5 прогрес-барів у єдиний багатосегментний бар або текстовий індикатор "Поточна стадія".
  3. Перемістити `div id="terminalCard"` всередину розширеного стану картки книги, щоб лог був видимий одразу под кнопкою "Run / Stop".
* **Verification Method:** Manually verified in browser on mobile device by user. Fixed terminal log rendering to cache outputs and prevent flickering during background refreshes.
* **Type:** `delegate`

## [x] TASK-6: Unified stages.html Viewer Pattern
* **Problem:** У `stages.html` існують три різні архітектури перегляду: `manga-viewer` (3 колонки), `paragraphs-list` (список карток) та `page-split-viewer` (два iframes). На мобільному телефоні side-by-side працює погано.
* **Solution:** Створити єдиний патерн `Toggle Viewer`. На екрані є лише одне вікно перегляду контенту (зображення, iframe або текст) та перемикач внизу (Original | Processed/Translated). Для манги додати проміжний стейт "Cleaned". Навігаційні стрілки (Попередня/Наступна) уніфікувати для всіх типів контенту. Оновити JS-функції `renderManga` та `loadEpubPage`, щоб вони монтували дані у цей єдиний DOM-вузол.
* **Verification Method:** Manually verified in browser on mobile device by user. Fixed EPUB asset routing (images/CSS) and dynamic <base> tag injection (including SVG namespace cleanup) to support previewing compiled PDF-to-EPUB books.
* **Type:** `delegate`

## [ ] TASK-7: [SECURITY] Remove Hardcoded Auth Credentials (IN_PROGRESS - NEEDS MANUAL ACTION)
* **Problem:** У `app.py` хардкодиться пароль "0523" для користувача "vokov", якщо файл `web_credentials.json` відсутній або пошкоджений.
* **Solution:** Замість фолбеку на хардкод пароль, зчитувати значення з ENV-змінної (наприклад, `KBG_WEB_PASSWORD`), або, якщо файл відсутній, генерувати випадковий пароль, виводити його в консоль при запуску Flask і записувати у файл.
* **Verification Method:** The fallback to insecure hardcoded password "0523" has been eliminated in code. However, since 'web_credentials.json' already exists on the dev server with the hash of "0523", the old password remains active. Real-world mitigation requires either setting the `KBG_WEB_PASSWORD` env variable or deleting the old json file to let it generate a secure token on start.
* **Type:** `direct`

## [x] TASK-8: OLED Adaptive Contrast Visual Theme
* **Problem:** Поточна тема не оптимізована для OLED (багато blur, напівпрозорі картинки, низький контраст меж) та складні умови освітлення (наприклад, під сонячним світлом або вночі). Також відсутні специфікації фокус-станів для клавіатурної та тачпадної навігації, а прогрес-бари використовують забагато різних яскравих кольорів.
* **Solution:** 
  1. Впроваджено OLED-оптимізовану систему токенів: глибокий OLED-чорний фон, непрозорі поверхні карток, чіткі межі без розмиття.
  2. Підвищено контрастність шрифтів до WCAG AA+ для легшого зчитування на сонці.
  3. Уніфіковано кольори статусів (idle/active/done/error), прив'язавши їх до головного фіолетового брендового кольору замість "веселки".
  4. Замінено багатокольоровий градієнт загального прогрес-бару на фіолетовий градієнт бренду.
  5. Створено чіткі фокус-стани `:focus-visible` для кнопок, чекбоксів та елементів введення.
* **Verification Method:** Manually verified by user on OnePlus 13 screen.
* **Type:** `delegate`

## [x] TASK-9: Terminal Log Cache (Flicker Fix) (DONE - RETROACTIVELY DOCUMENTED)
* **Problem:** Термінал логів оновлюється періодично, що призводить до повного очищення DOM і перерендерингу. На мобільних пристроях це викликає мерехтіння і скидає позицію прокрутки.
* **Solution:** Додати кешування логів у JavaScript (`lastLogsCache`), щоб при повторному рендерингу спочатку показувати попередньо завантажений текст, а потім оновлювати його лише при зміні контенту.
* **Verification Method:** Manually verified on OnePlus 13 in Termux. Rendered terminal logs are fully cached per-book slug and updated smoothly. (Commit `69c2b73`).
* **Type:** `direct`

## [x] TASK-10: PDF-to-EPUB Asset Serving and Namespace Cleanup (DONE - RETROACTIVELY DOCUMENTED)
* **Problem:** При перегляді сконвертованих PDF-книг (які компілюються в EPUB) у вікні stages/viewer виникає чорний екран або порожній вміст через те, що: (а) бінарні ресурси (зображення, стилі) не завантажуються з OPF-директорії всередині EPUB, (б) SVG-зображення містять префікси просторів імен (напр., `ns1:svg`), які є некоректними для стандарту HTML5 і не рендерилися браузером.
* **Solution:** 
  1. Оновити `app.py` для пошуку EPUB-файлів у теці `output` книги, якщо вони відсутні в `input`.
  2. Додати пряме сервування бінарних ресурсів (зображення, CSS) із Zip-файлу EPUB через Flask-ендпоінт.
  3. Впровадити автоматичне очищення SVG просторів імен та префіксів перед рендерингом HTML-сторінки.
  4. Додати динамічне впорскування тегу `<base>` для правильного дозволу відносних шляхів ресурсів.
* **Verification Method:** Manually verified on OnePlus 13. PDF-to-EPUB conversion previews successfully, assets are served dynamically, and namespaces are stripped cleanly without a black screen. (Commit `69c2b73`).
* **Type:** `direct`

## [x] TASK-11: No-Translate Suffix Fix (DONE - RETROACTIVELY DOCUMENTED)
* **Problem:** При запуску конвеєра з прапорцем `--no-translate` суфікс вихідних файлів розраховувався некоректно, що спричиняло збій у генерації назв результуючих файлів.
* **Solution:** Завжди додавати суфікс `_translated_<lang>`, якщо цільова мова відрізняється від початкової, незалежно від наявності прапорця `no_translate` в аргументах.
* **Verification Method:** Verified on OnePlus 13 during translation runs. (Commit `e775e46`).
* **Type:** `direct`

## [x] TASK-12: TTS Preview Stressification
* **Problem:** При прослуховуванні прев'ю тексту (TTS Preview) через дашборд слова вимовляються без наголосів, оскільки текст відправлявся в TTS-рушій напряму, минаючи стадію Stress.
* **Solution:**
  1. Додано підтримку обробки поодиноких inline-рядків (`--inline <text>`) в утиліту `bin/stressify_batch.py` без використання тимчасових JSON-файлів (запобігає конфліктам з фоновими конвертаціями).
  2. Оновлено роут `/api/tts-preview/<slug>` в `app.py`: якщо мовою є українська (`uk`), перед синтезом текст пропускається через `stressify_batch.py` всередині PRoot Ubuntu контейнера.
  3. Додано безпечний fallback (якщо контейнер або наголошувач недоступні, прев'ю генерується на вихідному тексті без помилок).
* **Verification Method:** Manually verified by user via TTS preview audio on OnePlus 13.
* **Type:** `direct`

## [ ] TASK-14: Audio Pauses, Markdown Cleaning, and Preview Pagination (IN_PROGRESS - needs manual audio verification)
* **Problem:** 
  1. Аудіокниги містять замало пауз між реченнями та заголовками, а іноді виникають кліки або зрізи складів на кінцях чанків.
  2. Розмітка (таблиці, mermaid-діаграми, коментарі HTML) попадає в аудіо-синтез та прев'ю.
  3. Перегляд списку чанків у веб-інтерфейсі обмежувався лише першими 30 чанками (TOC), і не давав доступу до решти книги, до того ж запити були повільними через O(N) операції дискової перевірки на кожен запит.
* **Solution:**
  1. Реалізовано генерацію WAV-файлів тиші (500мс для звичайних переходів, 3000мс для заголовків розділів) та накладання 15мс fade-out на кінці чанків через ffmpeg у PRoot контейнері перед склеюванням.
  2. Збільшено безпечний trailing-ліміт зрізання тиші в `tts_helper.py` для непунктуйованих чанків зі 100мс до 250мс для уникнення зрізів.
  3. Додано повне вилучення HTML-коментарів та Markdown-таблиць у `PlaceholderManager.strip_formatting`.
  4. Додано пагінацію списку чанків (по 30 на сторінку) у веб-роут `/api/preview/book/<slug>` та інтерфейс `stages.html`, оптимізовано час обробки до 10мс шляхом обмеження дискових і кеш-перевірок лише для поточної сторінки.
* **Verification Method:** In progress (synthesis running on phone). Needs manual audio listening to verify pause length, fade-out, lack of clicks, and markdown text removal.
* **Type:** `direct`



## [x] TASK-15: Deployment Script for OnePlus
* **Problem:** Non-professional users struggle to set up the environment and models on Termux manually. Large model files (like the 4.4GB GGUF translator and Supertonic 3 TTS) are prone to download interruptions on mobile/Wi-Fi networks, and missing critical packages (like `stress-uk` or `num2words`) inside PRoot Ubuntu cause the text stressifier to fail silently.
* **Solution:**
  1. Updated `deploy_oneplus13.sh` to include an interactive service autostart setup and a comprehensive model downloader.
  2. Implemented a robust `check_and_download` helper function with resume support (`curl -C -`) and strict size verification checks to prevent corrupt downloads.
  3. Added checks and automatic installation for `stress-uk` and `num2words` inside the PRoot Ubuntu setup script (Step 3).
  4. Updated `README_Termux.md` to clearly explain downloaded files, expected sizes, and system storage requirements prior to showing the one-line installer command.
* **Verification Method:** Verified size check, download, and resume functionality by simulating partial downloads and checking logs. Verified that `stress-uk` is correctly installed and imported during deployment tests.
* **Type:** `direct`

## [x] TASK-16: Manga export to Kindle-compatible format (AZW3 via Mapaki)
* **Problem:** There was no option to export translated manga in a Kindle-compatible format. Additionally, when exporting manga, the web interface displayed an irrelevant audio/TTS settings block.
* **Solution:**
  1. Integrated the native Go-based `Mapaki` tool into the manga translation pipeline inside the PRoot Ubuntu container.
  2. Implemented Pillow-based downscaling prior to packing so that any image exceeding 1920px in height is scaled down to exactly 1920px (preserving aspect ratio) to prevent Scribe/Kindle blank page render bugs.
  3. Added a new `--left-to-right` CLI option to `translate_manga.py` and passed it dynamically to Mapaki.
  4. Modified `kbg_web/templates/dashboard.html` to hide the audiobook/TTS settings section for manga books (where `book.progress.is_manga` is true).
  5. The Flask app output scanner automatically detects and exposes the resulting `.azw3` file alongside the `.cbz` archive for download.
* **Verification Method:** Verified on the OnePlus 13 phone by successfully compiling Mapaki, running the updated `translate_manga.py` on Frieren manga, confirming image downscaling from 1500x2250 to 1280x1920, and successfully producing a valid 1.4MB `test_manga_out.azw3` file. Verified that the dashboard successfully hides the settings block when loading manga.
* **Type:** `direct`

## [x] TASK-17: Onboarding sweep — delete actions, page-jump pagination, verify UI-model-management, remove Proofreading stage
* **Problem:** Following `AGENT_ONBOARDING_kindle-butch-gen.md`'s 7-item list:
  1. Books could not be removed from the dashboard once added.
  2. Output files (per-book and in the newly-added Downloads Archive) could not be deleted.
  3. The chunk/paragraph previewer only had Prev/Next (30 chunks/page), so reaching page 100+ of a long book required dozens of clicks.
  4. Repeat manga conversion with `--no-translate` was re-copying the *original* untranslated page into output, discarding prior translation work.
  5. The Proofreading stage (`edit_epub.py`, a second-pass LLM re-check of translated text run via `kbg.sh edit <slug>`) turned out not to be needed in practice, but its backend logic and UI (progress-bar step, Editor Model selector) were still present.
* **Solution:**
  1. Added `POST /api/delete/<slug>` (refuses while running) + a Delete button on each book card.
  2. Added `POST /api/delete-file/<slug>/<filename>` (reuses the existing path-traversal guard from `download_output_file`) + delete buttons in `downloads.html` and the per-book downloads list in `dashboard.html`.
  3. Added a numeric page-jump input + Go button to `stages.html`'s paragraph pagination controls, reusing the existing `fetchParagraphsPage()`/`/api/preview/book/<slug>?page=` machinery — no backend change needed.
  4. Recovered and applied a stale-but-correct fix found uncommitted on the dev server: `--no-translate` now looks up the already-translated image first, falling back to the original only if it hasn't been translated yet.
  5. Confirmed `/api/models`, `/api/models/configure`, `/api/models/start`, `/api/models/stop` (run the translation model server from the UI) were already implemented — no new code needed, just live-verified.
  6. Deleted `edit_epub.py`, removed the `kbg.sh edit` action, and stripped `edit_percent`/`edit_progress.json`/`editor_model` from `status_helper.py`, `app.py`, `monitor_book.sh`, and the dashboard's progress tracker + Settings modal.
  7. Also recovered/committed a global Downloads Archive page (`/downloads`, `kbg_web/templates/downloads.html`) and a `dashboard.html` bug fix (missing null-checks in the `formValues` restore logic) found alongside the manga fix on the dev server.
* **Verification Method:** `python3 -m py_compile` on all touched Python files; grepped the full repo to confirm no dangling `edit_epub`/`edit_percent`/`editor_model` references after removal; deployed to the OnePlus 13 via scp (git pull wasn't possible — phone has no SSH key to reach GitHub or the dev server) and restarted `kbg_web`; live-verified via `https://kindle.exodus.pp.ua`: `/api/status` no longer returns `edit_percent`, `/api/models` no longer returns `editor_model`, `/api/downloads` and `/downloads` respond correctly, `/api/delete*` correctly reject nonexistent targets, and `/api/preview/book/vibe-programming` confirmed real-world need for item 4 (169 pages of 30 chunks each). Did not destructively test delete against real book data.
* **Type:** `delegate` (dev-server WIP recovery) + `direct` (remaining items)

## [x] TASK-18: [BUG][FIXED] Race condition in /api/models/start allows duplicate llama-server processes
* **Problem:** `/api/models/start` kills any existing `llama-server` on port 8081 (`pkill -f "llama-server.*8081"`) then launches `~/start-translation-server.sh`, which *itself* does its own pkill + 2s sleep before launching. Two Start requests fired close together (e.g. an impatient double-tap on the "Start Server" button) race past both pkill checkpoints and each spawns its own server. Reproduced empirically: firing two `/api/models/start` calls 0.3s apart left **two full 4.4GB Hy-MT2-7B llama-server processes running simultaneously** (confirmed via `ps aux` on the phone), and the state did not self-correct over a 60s observation window — required a manual `kill -9` to clean up. On a memory-constrained phone this is a real resource-exhaustion risk.
* **Solution:**
  1. Replaced `pkill -f "llama-server.*8081"` pattern-matching with a PID file (`~/llama-server-8081.pid`) as the single source of truth for the tracked process — `_read_llama_pid()` / `_stop_llama_server()` in `app.py` verify liveness via `os.kill(pid, 0)` and always clear the file afterward so a stale entry never lingers.
  2. Added an `O_CREAT|O_EXCL` start lock (`~/llama-server-8081.lock`) around the stop-old+launch-new critical section in `/api/models/start`. A concurrent start request now gets an explicit `409 "A start is already in progress"` instead of silently racing through. The lock self-clears if older than 15s (far longer than the section normally takes), so a crashed request can't permanently block future starts.
  3. Removed the duplicate `pkill`+`sleep 2` from `~/start-translation-server.sh` (phone-only, not tracked in git) — stopping is now exclusively the API layer's responsibility; the script only launches and writes its own PID to the file path passed in as `$1`.
  4. `dashboard.html`'s Start Server button now stays disabled ("Starting...") for up to 90s, polling `/api/models` until it reports `running: true`, instead of re-enabling right after the fire-and-forget POST returns — closes the double-click window client-side too.
* **Verification Method:** All via `curl`+SSH against the live phone (agent-workspace/AGY3 still unreachable). (a) Fired two `/api/models/start` 0.2s apart → first got `200`, second got `409 "A start is already in progress"`; after model load, exactly 1 `llama-server` process and the PID file matched it. (b) Normal Stop→Start: confirmed PID file removed on stop (and process actually gone via `ps aux`, not just a UI illusion), then correctly re-created with the new PID on start. (c) Simulated a stale lock (manually aged to 20s) and confirmed the next start self-healed past it (`200`, not `409`) instead of being permanently blocked. Device restored to normal running state afterward. Full report: ai-memory `notes/2026-07-15-models-manager-test-report.md` and follow-up fix notes (project `kindle-butch-gen`).
* **Type:** `direct`

