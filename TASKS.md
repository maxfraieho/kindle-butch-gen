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
