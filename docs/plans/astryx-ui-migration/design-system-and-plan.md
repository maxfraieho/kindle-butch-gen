# 🦦 Vydra UI — Концепція дизайну "Emerald Slate Studio" та Покроковий План Розробки

> **Статус:** 🎨 Дизайн-система та План розробки (React + Vite + Astryx)  
> **Принципи дизайну:** `frontend-design` + `make-interfaces-feel-better`  
> **Адаптивність:** Mobile-First Ergonomics + Desktop Studio Layout  

---

## 1. Візуальна концепція та Дизайн-Система "Emerald Slate Studio"

Ми відмовляємося від шаблонних AI-градієнтів та копіювання застарілих Jinja2 стилів. Створюється **преміальна, високотехнологічна студія локалізації**.

```
  ┌─────────────────────────────────────────────────────────────────────────┐
  │                           COLOR PALETTE                                 │
  ├─────────────────────────────────────────────────────────────────────────┤
  │ Base Background : #090d16 (Deep Ocean Slate)                            │
  │ Surface Card    : #111827 (Dark Velvet Slate, 80% opacity + blur)       │
  │ Border Neutral  : rgba(255, 255, 255, 0.08)                             │
  │ Primary Accent  : #10b981 (Emerald Spark)                               │
  │ Secondary Accent: #06b6d4 (Cyan Bioluminescence)                       │
  │ Gold Status     : #f59e0b (Amber Warmth for Completed/Audio)             │
  │ Alert Danger    : #ef4444 (Crimson for QA Flags)                        │
  └─────────────────────────────────────────────────────────────────────────┘
```

### 1.1 Типографіка
- **Display / Заголовки:** `'Outfit', sans-serif` — геометричний, преміальний шрифт.
- **Основний текст:** `'Plus Jakarta Sans', sans-serif` — надзвичайно читабельний для мобільних екранів.
- **Код та метрики:** `'JetBrains Mono', monospace` з обов'язковим `font-variant-numeric: tabular-nums` (запобігає смиканню інтерфейсу при зміні відсотків прогресу).

### 1.2 Принципи Polish (make-interfaces-feel-better)
1. **Concentric Border Radius**: `Outer Radius = Inner Radius + Padding` (наприклад, картка `18px`, внутрішня кнопка `10px`, padding `8px`).
2. **Tactile Feedback**: Всі кнопки та клікабельні картки реагують `active:scale-[0.96]` з кривою `cubic-bezier(0.2, 0, 0, 1)`.
3. **Layered Shadows замість грубих бордерів**: Використання 2-3 прозорих шарів тіней для об'єму та глибини.
4. **Тач-зони 48px+**: Для мобільних пристроїв всі елементи керування мають мінімальну зону натискання 48×48px.
5. **Staggered Animations**: Поліпшена анімація появи списку книг та сторінок з затримкою `~60ms` між елементами.

---

## 2. Двохрежимний адаптивний Layout (Mobile Dock vs Desktop Studio)

```
MOBILE VIEW (< 768px)                       DESKTOP VIEW (≥ 768px)
┌───────────────────────────┐      ┌─────────────┬──────────────────────────┐
│ 🦦 Vydra        [⚙️] [👤] │      │ 🦦 Vydra    │ 🔍 Пошук книги...   [👤] │
├───────────────────────────┤      ├─────────────┼──────────────────────────┤
│ ┌───────────────────────┐ │      │ 📑 Книги    │ ┌─────────┐  ┌─────────┐ │
│ │ 📖 Книга 1            │ │      │ 🎧 Аудіо    │ │ Книга 1 │  │ Книга 2 │ │
│ │ ▓▓▓▓▓▓▓░░░ 72%        │ │      │ 🎨 Манга    │ └─────────┘  └─────────┘ │
│ └───────────────────────┘ │      │ 📥 Завантаж │ ┌──────────────────────┐ │
├───────────────────────────┤      │ ⚙️ Моделі   │ │ Деталі та статус     │ │
│ [📑 Книги] [🎨] [📥] [⚙️]  │      │             │ └──────────────────────┘ │
└───────────────────────────┘      └─────────────┴──────────────────────────┘
  Floating Bottom Dock               Sidebar Studio + Dynamic Main Canvas
```

---

## 3. Детальний покроковий план розробки React UI

### **Крок 1: Ініціалізація та розгортання Vite + Astryx в `frontend/`**

- [ ] **1.1** Створення Vite проєкту в `frontend/`:
  ```bash
  cd /home/vokov/agy-work/kindle-butch-gen-research
  npx -y create-vite@latest frontend --template react-ts
  ```
- [ ] **1.2** Встановлення залежностей:
  ```bash
  cd frontend
  npm install @astryxdesign/core @astryxdesign/theme-neutral lucide-react react-router-dom
  ```
- [ ] **1.3** Конфігурація `vite.config.ts` для збірки в `../kbg_web/static/dist`:
  ```typescript
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
- [ ] **1.4** Підключення шрифтів Google Fonts (`Outfit`, `Plus Jakarta Sans`, `JetBrains Mono`) у `index.html`.

---

### **Крок 2: Створення теми "Emerald Slate Studio" та Базових Компонентів**

- [ ] **2.1** Створення `frontend/src/theme/vydraTheme.ts`:
  - Налаштування токенів Astryx (OLED Slate `#090d16`, Emerald `#10b981`, Cyan `#06b6d4`, Amber `#f59e0b`).
  - Підключення `vydraTheme` до коду через `<Theme theme={vydraTheme} mode="dark">`.
- [ ] **2.2** Створення базових обгорток з покращеним фідбеком (`frontend/src/components/ui/`):
  - `Button.tsx`: з додаванням `active:scale-[0.96] transition-transform` та чітких тач-зон 48px.
  - `Card.tsx`: з підтримкою concentric border-radius (`rounded-2xl` снаружи, `rounded-xl` всередині).
  - `ProgressBar.tsx`: з підтримкою `tabular-nums` для тексту відсотків.
  - `Badge.tsx`: з неоновим свіченням статусу (glow effect).

---

### **Крок 3: API Клієнт та Авторизація (`useAuth` + `Login.tsx`)**

- [ ] **3.1** Створення `frontend/src/api/client.ts`:
  - `apiFetch<T>()` з автоматичною обробкою авторизаційних cookies та 401 помилок.
- [ ] **3.2** Створення `frontend/src/context/AuthContext.tsx`:
  - Стан авторизації, `login()`, `logout()`, перевірка сесії через `/api/auth/check`.
- [ ] **3.3** Розробка сторінки `Login.tsx`:
  - Анімований видровий логотип з ефектом м'якого пульсу.
  - Смарагдова форма входу Astryx `Card` з валідацією полів та гладкими помилками.

---

### **Крок 4: Адаптивна Навігація та Каркас (`AppShell.tsx`)**

- [ ] **4.1** Розробка `TopHeader.tsx`:
  - Відображення статусу сервера моделей (`/api/models`), перемикач режимів та профіль.
- [ ] **4.2** Розробка `DesktopSidebar.tsx` (≥ 768px):
  - Вертикальна панель з іконками `Lucide` та швидкими гарячими клавішами.
- [ ] **4.3** Розробка `MobileBottomDock.tsx` (< 768px):
  - Плаваюча нижня панель з розмиттям фону (`backdrop-blur-md`) та активними haptic-індикаторами.

---

### **Крок 5: Дашборд Книг та Керування Конвертацією (`Dashboard.tsx`)**

- [ ] **5.1** `BookCard.tsx`:
  - Картка книги з динамічним індикатором прогресу, статусами (переклад, наголоси, TTS), обкладинкою та швидкими діями (Run / Stop / Edit / Delete).
- [ ] **5.2** `AddBookModal.tsx`:
  - Astryx `Dialog` для завантаження PDF/EPUB/CBZ або вибору папки з сервера (`/api/browse-fs`).
- [ ] **5.3** `RealtimeStatusTracker.tsx`:
  - Хук `useBookStatus` для живого оновлення прогресу без смикання макету (`tabular-nums`).

---

### **Крок 6: Студія Перегляду та Манга-Триптих (`StagesView.tsx` & `MangaEditor.tsx`)**

- [ ] **6.1** `StagesTextTab.tsx`:
  - Перегляд оригінального та перекладеного тексту поруч або через Toggle.
  - Аудіоплеєр із візуалізатором для перевірки Supertonic 3 TTS.
- [ ] **6.2** `MangaTriptychViewer.tsx`:
  - 3-панельний перегляд манги: [Оригінал | Очищена сторінка | Перекладена манга].
  - Плаваючий оверлей над бульбашками з QA-рамками (Червона = текст не вліз, Жовта = малий шрифт, Зелена = OK).
  - Висувний `Drawer` бічної панелі для миттєвого редагування тексту бульбашки без перекриття усієї сторінки.

---

### **Крок 7: Архів Завантажень, Налаштування та Інтеграція з Flask**

- [ ] **7.1** `DownloadsView.tsx`:
  - Швидка фільтрація за типом (.epub, .azw3, .mp3, .cbz) та пошуком.
- [ ] **7.2** `SettingsView.tsx`:
  - Налаштування TTS голосів (0-9 Supertonic 3), тест швидкості, вибір мовних моделей.
- [ ] **7.3** Модифікація `kbg_web/app.py`:
  - Додавання `spa_fallback` маршруту та обробки статики з `static/dist`.
- [ ] **7.4** Збірка та Перевірка:
  - `npm run build` у `frontend/`.
  - Запуск `./kbg.sh serve` та тестування як на мобільних пристроях, так і на десктопі.

---

## 4. Контрольна таблиця якості (Checklist Polish)

- [x] Ніколи не використовувати `transition: all` — тільки конкретні властивості.
- [x] Тач-зони кнопкок на мобільному ≥ 48px.
- [x] Всі числові лічильники мають `tabular-nums`.
- [x] Кнопки мають `scale(0.96)` при натисканні.
- [x] Радіуси внутрішніх блоків строго вираховані за формулою `r_outer = r_inner + padding`.
- [x] Жодних стандартних сірих рамок — використовуємо багатошарову тінь та прозорі акценти.
