# Kindle Butch Gen (Ukrainization & Audiobook Generation)

A tool suite to automate EPUB/Markdown translation and generate Ukrainian audiobooks using high-quality neural TTS models.

## TTS Engine, Voice Quality & License Details

This project uses the Piper text-to-speech synthesis engine to generate Ukrainian audio. The following voice models are supported:

1. **uk_UA-lada-x_low**
   - **Quality**: `x_low`
   - **Dataset**: Lada dataset (Apache 2.0 License).
   - **License**: Apache 2.0.
   
2. **uk_UA-ukrainian_tts-medium**
   - **Quality**: `medium`
   - **Dataset**: OHF voice datasets (CC0 Public Domain).
   - **License**: CC0.

- **Piper Engine**: Licensed under the **MIT License**.

### How to Configure Voice in `config.json`

You can specify the desired voice and quality in your book's `config.json` file. For example, to use the high-quality CC0 medium voice, configure it as follows:

```json
{
  "tts_voice": "ukrainian_tts",
  "tts_voice_quality": "medium"
}
```

For the low-complexity Lada voice, use:

```json
{
  "tts_voice": "lada",
  "tts_voice_quality": "x_low"
}
```

## Встановлення та швидкий старт

Інструментарій `kindle-butch-gen` розроблений для запуску в середовищі **Termux (Android)** з інтеграцією Ubuntu-контейнера через `proot-distro` для виконання важких завдань (OCR, Calibre, Piper).

### 1. Передумови та встановлення

Скрипт `kbg.sh` автоматизує запуск етапів. Для роботи Calibre, OCR та Piper необхідно, щоб у вашому Ubuntu-контейнері (`proot-distro login ubuntu`) були встановлені:
- `python3` з бібліотекою `ukrainian-word-stress`
- `ffmpeg` та `calibre` (для конвертації книг)

### 2. Керування книгами через CLI (`kbg.sh`)

Усі підкоманди запускаються через головний скрипт керування:

*   **Додати нову книгу до обробки**:
    ```bash
    ./kbg.sh add --slug <унікальний_слаг> --pdf </шлях/до/файлу.pdf> --title "<Назва книги>" --authors "<Автори>" --lang <uk|ru>
    ```
    Ця команда створює конфігураційний шаблон за шляхом `books/<slug>/config.json`.

*   **Запустити повний пайплайн конвертації**:
    ```bash
    ./kbg.sh run <slug>
    ```
    Команда автоматично виконає:
    1. Екстракцію сторінок PDF у Markdown за допомогою Marker.
    2. Поабзацний переклад (за наявності локального сервера перекладу).
    3. Збірку книжкових форматів EPUB та AZW3.
    4. Синтез аудіокниги в MP3 через Piper TTS.

*   **Переглянути статус та прогрес конвертації**:
    ```bash
    ./kbg.sh status <slug>
    ```

*   **Запустити веб-дашборд**:
    ```bash
    ./kbg.sh serve --port 5000
    ```
    Для розробки веб-панелі з дебаг-режимом додайте прапорець `--dev`:
    ```bash
    ./kbg.sh serve --port 5000 --dev
    ```

### 3. Веб-інтерфейс (Дашборд)

Після запуску веб-сервера перейдіть у браузері за адресою `http://127.0.0.1:5000`. 
Панель дозволяє:
- Відстежувати прогрес кожного етапу у реальному часі.
- Змінювати налаштування голосу, швидкості мовлення (`Speed`) та емоційного забарвлення (`Noise Scale`/`Noise Width`).
- Слухати швидке аудіо-прев'ю голосу перед запуском повної обробки книги.
- Завантажувати готові файли (`.epub`, `.azw3`, `.mp3`) в один клік.

