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

## [ ] TASK-12: TTS Preview Stressification (IN_PROGRESS - CODE UPDATED, NEEDS MANUAL AUDIO VERIFICATION)
* **Problem:** При прослуховуванні прев'ю тексту (TTS Preview) через дашборд слова вимовляються без наголосів, оскільки текст відправлявся в TTS-рушій напряму, минаючи стадію Stress.
* **Solution:**
  1. Додано підтримку обробки поодиноких inline-рядків (`--inline <text>`) в утиліту `bin/stressify_batch.py` без використання тимчасових JSON-файлів (запобігає конфліктам з фоновими конвертаціями).
  2. Оновлено роут `/api/tts-preview/<slug>` в `app.py`: якщо мовою є українська (`uk`), перед синтезом текст пропускається через `stressify_batch.py` всередині PRoot Ubuntu контейнера.
  3. Додано безпечний fallback (якщо контейнер або наголошувач недоступні, прев'ю генерується на вихідному тексті без помилок).
* **Verification Method:** code updated, needs manual audio verification.
* **Type:** `direct`


