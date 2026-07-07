# project-memory: kindle-butch-gen
Last Updated: 2026-07-07T02:40:00Z
Agent: AGY3 (Termux environment)

## 1. Текущий статус проекта
Мы успешно провели рефакторинг и обобщили проект `kindle-butch-gen` для поддержки нескольких книг и гибких настроек TTS:
*   **Голос**: Поддерживается 3-дикторная модель `uk_UA-ukrainian_tts-medium` (lada: 0, mykyta: 1, tetiana: 2). Tetiana (Speaker 2) зафиксирована как дефолтный диктор.
*   **Интеграция Supertonic 3**: Успешно скомпилирован и установлен русифицированный C++ движок `sherpa-onnx` с использованием системного пакета `onnxruntime` нативно в Termux (без PRoot). Интегрирован Supertonic 3 (Flow Matching, ~99M параметров) как преимум-опция TTS с поддержкой 10 дикторов (0-9) нативного CD-качества (44100 Hz). Генерация в 4.5 раза быстрее Piper (RTF ~0.10 на CPU Oryon) без необходимости в Stressifier на нательном уровне.
*   **Веб-интерфейс**: Реализован Flask-дашборд на порту `5000` (`kbg_web/app.py`). Добавлена форма настроек TTS (включая выбор движка: Piper / Supertonic 3), быстрое превью и авто-сохранение фокуса. Добавлена загрузка файлов (PDF/EPUB/TXT/MD) через `/api/upload` с автоматическим извлечением текста из EPUB (`bin/extract_epub_text.py`) и точным расчетом прогресса TTS на основе общего объема абзацев в объединенном файле (`kbg_web/status_helper.py`).
*   **Скрипт развертывания**: Создан скрипт `deploy_oneplus13.sh` и технический гайд `docs/plans/deploy_oneplus13_guide.md` для запуска на OnePlus 13 с поддержкой нативного OpenCL ускорения (`GGML_OPENCL=ON`) на GPU Adreno 830.
*   **Репозиторий**: Код очищен от `.wav` и `__pycache__` и выложен на GitHub [maxfraieho/kindle-butch-gen](https://github.com/maxfraieho/kindle-butch-gen).

## 2. Последние измененные файлы
*   `common/book_paths.py` (добавлено поле `tts_engine`)
*   `bin/tts_helper.py` (новый общий диспетчер для Piper и Supertonic 3)
*   `audio_stage.py` (поддержка диспетчеризации движков и локального запуска для Supertonic 3)
*   `kbg_web/app.py` (добавлен выбор движка в настройки TTS, поддержка Supertonic 3 в превью и диспетчеры)
*   `deploy_oneplus13.sh` (скрипт сборки llama.cpp с OpenCL для OnePlus 13)
*   `docs/plans/deploy_oneplus13_guide.md` (гайд по OpenCL архитектуре)
*   `README.md`, `LICENSE`, `.gitignore`

## 3. Открытые вопросы и следующие шаги
1.  **Тестирование развертывания**: Запустить `deploy_oneplus13.sh` на чистом OnePlus 13 для проверки нативной компиляции `llama.cpp` и доступа к GPU через `/dev/kgsl`.
2.  **Очистка истории Git**: Согласовать, нужно ли делать полную перезапись истории коммитов (через `git-filter-repo` / `BFG`) для уменьшения размера базы данных `.git` на GitHub от старых тяжелых `.wav` файлов.
3.  **Использование ai-memory**: Новая сессия должна начать с вызова `memory_handoff_accept` для загрузки handoff-контекста `019f39c2-f12d-74d2-a09a-3ce8c70fd890`.
