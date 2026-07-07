# Kindle Butch Gen (Ukrainization & Audiobook Generation)

A tool suite to automate EPUB/Markdown translation and generate Ukrainian audiobooks using high-quality neural TTS models.

## TTS Engine, Voice Support & License Details

This project uses the **Piper text-to-speech synthesis** engine to generate high-quality audiobooks. The system dynamically resolves and downloads voice models from Hugging Face based on the book's target language:

### 1. Ukrainian (`uk_UA`) Voices
*   **ukrainian_tts**
    *   **Quality**: `medium`
    *   **Speakers**: Multi-speaker model (Lada `[0]`, Mykyta `[1]`, Tetiana `[2]`).
    *   **License**: CC0 (Public Domain).
*   **lada**
    *   **Quality**: `x_low`
    *   **Speakers**: Single-speaker model (Default `[0]`).
    *   **License**: Apache 2.0.

### 2. Russian (`ru_RU`) Voices
*   **irina** (Default Russian voice)
    *   **Quality**: `medium`
    *   **Speakers**: Single-speaker model (Default `[0]`).
*   **denis**
    *   **Quality**: `medium`
    *   **Speakers**: Single-speaker model (Default `[0]`).
*   **dmitri**
    *   **Quality**: `medium`
    *   **Speakers**: Single-speaker model (Default `[0]`).
*   **ruslan**
    *   **Quality**: `medium`
    *   **Speakers**: Single-speaker model (Default `[0]`).

- **Piper Engine License**: MIT License.

### How to Configure Voice in `config.json`

You can specify the desired voice, speaker, and quality in your book's `config.json` file. 

For example, to configure **Ukrainian CC0 Tetiana** voice:
```json
{
  "target_lang": "uk",
  "tts_voice": "ukrainian_tts",
  "tts_voice_quality": "medium",
  "tts_speaker_id": 2
}
```

For **Russian Irina** voice:
```json
{
  "target_lang": "ru",
  "tts_voice": "irina",
  "tts_voice_quality": "medium",
  "tts_speaker_id": 0
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

### 4. Пряме завантаження файлів та автопереклад

Веб-інтерфейс підтримує пряме завантаження файлів форматів `.pdf`, `.epub`, `.txt`, `.md`.
* **Автоматичний парсинг метаданих**: При виборі файлу система автоматично зчитує заголовок, авторів та мову (для `.epub`) й пропонує попередньо заповнені поля форми.
* **Переклад книг (PDF-less Mode)**: Ви можете завантажити книгу будь-якою мовою (`Source Language`) та обрати іншу мову для аудіокниги (`Target Language`). Якщо мови відрізняються, система автоматично запустить етап перекладу всього тексту книги перед озвученням та створенням кінцевих файлів.

