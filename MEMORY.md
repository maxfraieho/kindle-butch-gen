# Memory: Kindle Butch Gen (Translation & E-Book Compiler)

## 1. Поточний статус проекту (Активний)
Сесію перекладу книги **"Three Days of Happiness"** (three-days-of-happiness) **успішно відновлено**. Усі сервіси (сервер моделі Qwen на порту 8081, скрипт перекладу `translate_epub.py` та Flask веб-сервер панелі на порту 5000) працюють у фоні.

### Результати та поточний прогрес:
*   **Статус**: 🟢 **ACTIVE** (усі сервіси запущені, переклад триває).
*   **Прогрес перекладу Qwen**: переклад виконується автоматично. Прогрес можна відстежувати у файлі `books/three-days-of-happiness/cache/epub_progress.json` або через веб-панель.
*   **Збереження**: Прогрес записується у кеш-файл `translate_cache.json` кожні кілька абзаців.
*   **Активні завдання**:
    *   `llama-server` (модель Qwen 7B) на порту `8081`
    *   `translate_epub.py` (скрипт перекладу)
    *   Flask веб-сервер на порту `5000`

---

## 2. Ключові зміни та налаштування
*   **Прямий переклад через Qwen-2.5-Coder-7B**: Успішно налаштовано в один прохід через порт `8081` (з OpenCL GPU прискоренням). Якість перекладу висока, плейсхолдери зберігаються ідеально завдяки новому строгому промпту перекладача в `translate_epub.py`.
*   **Поабзацний прогрес**: Додано поабзацне оновлення файлів прогресу (`epub_progress.json` та `edit_progress.json`), що дозволяє спостерігати реальний рух перекладу без зависань на великих розділах.

---

## 3. Дальнейшие шаги (Інструкція для відновлення)
Щоб відновити роботу після паузи, виконайте такі дії:
1.  **Запустіть сервер перекладу (Qwen 7B)**:
    ```bash
    bash ~/start-translation-server.sh
    ```
    *(зачекайте 20-30 секунд, поки модель завантажиться у VRAM/RAM)*
2.  **Запустіть скрипт перекладу**:
    ```bash
    python3 translate_epub.py --input /data/data/com.termux/files/home/kindle-butch-gen/books/three-days-of-happiness/three-days-of-happiness.epub --output /data/data/com.termux/files/home/kindle-butch-gen/books/three-days-of-happiness/output/three-days-of-happiness_translated_uk.epub --target-lang uk --book three-days-of-happiness
    ```
3.  *(Опціонально)* **Запустіть веб-панель Flask**:
    ```bash
    ./kbg.sh serve --port 5000
    ```
