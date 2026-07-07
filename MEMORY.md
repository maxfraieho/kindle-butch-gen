# project-memory: kindle-butch-gen
Last Updated: 2026-07-07T02:40:00Z
Agent: AGY3 (Termux environment)

## 1. Текущий статус проекта
Мы успешно провели рефакторинг и обобщили проект `kindle-butch-gen` для поддержки нескольких книг и гибких настроек TTS:
*   **Голос**: Поддерживается 3-дикторная модель `uk_UA-ukrainian_tts-medium` (lada: 0, mykyta: 1, tetiana: 2). Tetiana (Speaker 2) зафиксирована как дефолтный диктор.
*   **Веб-интерфейс**: Реализован Flask-дашборд на порту `5000` (файл `kbg_web/app.py`) с формой изменения настроек TTS (Speed, Noise Scale/Width), генерацией мгновенного аудио-превью и механизмом сохранения состояния инпутов/фокуса при поллинге.
*   **Скрипт развертывания**: Создан скрипт `deploy_oneplus13.sh` и технический гайд `docs/plans/deploy_oneplus13_guide.md` для запуска на OnePlus 13 с поддержкой нативного OpenCL ускорения (`GGML_OPENCL=ON`) на GPU Adreno 830.
*   **Репозиторий**: Код полностью очищен от временных `.wav` и `__pycache__` и выложен в публичный репозиторий [maxfraieho/kindle-butch-gen](https://github.com/maxfraieho/kindle-butch-gen).

## 2. Последние измененные файлы
*   `deploy_oneplus13.sh` (скрипт сборки llama.cpp с OpenCL для OnePlus 13)
*   `docs/plans/deploy_oneplus13_guide.md` (гайд по OpenCL архитектуре)
*   `README.md` (инструкция по установке и командам `kbg.sh`)
*   `LICENSE` (MIT)
*   `.gitignore` (игнорирует wav, mp3, pdf, caches, models)
*   `books/vibe-programming/config.json` (дефолтные настройки книги и диктора)

## 3. Открытые вопросы и следующие шаги
1.  **Тестирование развертывания**: Запустить `deploy_oneplus13.sh` на чистом OnePlus 13 для проверки нативной компиляции `llama.cpp` и доступа к GPU через `/dev/kgsl`.
2.  **Очистка истории Git**: Согласовать, нужно ли делать полную перезапись истории коммитов (через `git-filter-repo` / `BFG`) для уменьшения размера базы данных `.git` на GitHub от старых тяжелых `.wav` файлов.
3.  **Использование ai-memory**: Новая сессия должна начать с вызова `memory_handoff_accept` для загрузки handoff-контекста `019f39c2-f12d-74d2-a09a-3ce8c70fd890`.
