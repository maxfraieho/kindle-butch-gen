# 🦦 Vydra × Astryx — Планування міграції UI

> **Дата аналізу:** 2026-07-26
> **Проєкт:** kindle-butch-gen (Vydra)
> **Цільова платформа:** Astryx Design System
> **Статус:** 📋 Планування (без практичних змін)

---

## Зміст

1. [Резюме](#резюме)
2. [Аналіз поточного стану Vydra](#аналіз-поточного-стану-vydra)
3. [Аналіз Astryx Design System](#аналіз-astryx-design-system)
4. [Оцінка сумісності](#оцінка-сумісності)
5. [Архітектурні рішення](#архітектурні-рішення)
6. [План міграції по фазах](#план-міграції-по-фазах)
7. [Ризики та обмеження](#ризики-та-обмеження)
8. [Оцінка трудовитрат](#оцінка-трудовитрат)

---

## Резюме

### Що таке Vydra?

**Vydra (kindle-butch-gen)** — self-hosted інструментарій для автоматизованого перекладу EPUB/Markdown книг та генерації високоякісних українських аудіокниг на базі Android (Termux). Проєкт повністю працює локально на смартфоні.

### Що таке Astryx?

**Astryx** — відкрита дизайн-система від Meta з 150+ React-компонентами, побудована на React + StyleX. Підтримує SSR, модульні теми, Tailwind v4 bridge, та AI-ready API (MCP-сервер).

### Головний виклик

Vydra використовує **Flask (Python) + Jinja2 шаблони + vanilla JS**, а Astryx — це **React-бібліотека**. Пряма інтеграція неможлива — потрібна архітектурна перебудова UI-шару.

---

## Аналіз поточного стану Vydra

### Технологічний стек (поточний)

| Компонент | Технологія | Деталі |
|-----------|-----------|--------|
| Backend | **Flask (Python)** | Монолітний `app.py` — 3695 рядків, 175KB |
| Шаблони | **Jinja2 HTML** | 4 файли: `dashboard.html` (157KB), `stages.html` (166KB), `downloads.html` (15KB), `manual.html` (24KB) |
| Frontend JS | **Vanilla JavaScript** | `dashboard.js` (37 fetch calls), `stages.js` (57 fetch calls) |
| Стилізація | **Inline CSS + CSS Variables** | OLED-оптимізована тема, glassmorphism |
| Аутентифікація | **Session + HTTP Basic Auth** | `flask_httpauth`, persistent cookie (365 днів) |
| Assets | **Static files** | `vydra.png`, `vydra-sm.png`, manual screenshots |

### Карта маршрутів (68 маршрутів)

#### Сторінки (views)
| Маршрут | Опис |
|---------|------|
| `/` | Dashboard — головна панель |
| `/login` | Сторінка входу |
| `/logout` | Вихід з системи |
| `/downloads` | Архів завантажень |
| `/manual` | Документація/мануал |
| `/modes` | Перемикач режимів |
| `/view/<slug>` | Перегляд конкретної книги |

#### API — Книги
| Маршрут | Метод | Опис |
|---------|-------|------|
| `/api/books` | GET | Список всіх книг |
| `/api/add` | POST | Додати книгу |
| `/api/upload` | POST | Завантажити файл |
| `/api/parse-metadata` | POST | Парсинг метаданих |
| `/api/run/<slug>` | POST | Запуск конвертації |
| `/api/stop/<slug>` | POST | Зупинка конвертації |
| `/api/delete/<slug>` | DELETE | Видалення книги |
| `/api/status/<slug>` | GET | Статус конвертації |
| `/api/resume-stalled/<slug>` | POST | Відновити застрягшу конвертацію |

#### API — Файли та Завантаження
| Маршрут | Опис |
|---------|------|
| `/api/download/<slug>/<filename>` | Завантаження файлу |
| `/api/delete-file/<slug>/<filename>` | Видалення вихідного файлу |
| `/api/downloads` | API для архіву завантажень |
| `/api/browse-fs` | Перегляд файлової системи |

#### API — Налаштування
| Маршрут | Опис |
|---------|------|
| `/api/settings` | Глобальні налаштування |
| `/api/settings/output-root` | Шлях для вихідних файлів |
| `/api/book-settings/<slug>` | Налаштування книги |
| `/api/tts-settings/<slug>` | Налаштування TTS |
| `/api/tts-preview/<slug>` | Прев'ю TTS |

#### API — Персонажі (Cast Registry)
| Маршрут | Опис |
|---------|------|
| `/api/characters/<slug>` | CRUD для персонажів |
| `/api/characters/<slug>/scan` | Сканування персонажів |
| `/api/characters/<slug>/scan-progress` | Прогрес сканування |
| `/api/characters/<slug>/scan/stop` | Зупинка сканування |
| `/api/characters/<slug>/settings` | Налаштування персонажів |
| `/api/characters/<slug>/thumbnail/<char_id>` | Мініатюри персонажів |

#### API — Редагування (Live Editing)
| Маршрут | Опис |
|---------|------|
| `/api/edit/queue/<slug>` | Черга редагувань |
| `/api/edit/text/<slug>/<chunk_hash>` | Редагування тексту |
| `/api/edit/approve/<slug>/<edit_id>` | Затвердження правки |
| `/api/edit/discard/<slug>/<edit_id>` | Відхилення правки |
| `/api/edit/stress/<slug>/<chunk_hash>` | Наголоси |
| `/api/edit/regenerate-audio/<slug>/<chunk_hash>` | Перегенерація аудіо |
| `/api/edit/regenerate-manga-page/<slug>/<page>` | Перегенерація сторінки манги |
| `/api/edit/manga-bbox/<slug>/<page>` | Bounding boxes манги |
| `/api/edit/manga-text/<slug>/<page>` | Текст бульбашок манги |

#### API — Манга
| Маршрут | Опис |
|---------|------|
| `/api/preview/manga/<slug>` | Прев'ю манги |
| `/api/preview/manga-bubbles/<slug>/<page>` | Бульбашки сторінки |
| `/api/preview/manga-file/<slug>/<folder>/<file>` | Файл сторінки |
| `/api/preview/manga-quality-flags/<slug>` | QA прапорці |
| `/api/manga/<slug>/bubble-tone` | Тон бульбашок |

#### API — Моделі та Сервіси
| Маршрут | Опис |
|---------|------|
| `/api/models` | Статус моделей |
| `/api/models/configure` | Конфігурація моделей |
| `/api/models/start` | Запуск сервера перекладу |
| `/api/models/stop` | Зупинка сервера |
| `/api/premium/download-models` | Завантаження моделей |
| `/api/premium/models-status` | Статус преміум моделей |
| `/api/premium/model-status` | Статус окремої моделі |

#### API — Підтримка та Інше
| Маршрут | Опис |
|---------|------|
| `/api/support/profile` | Профіль підтримки |
| `/api/support/link-telegram` | Прив'язка Telegram |
| `/api/support/local-optout` | Відмова від локальних сервісів |
| `/api/change-password` | Зміна пароля |
| `/api/update` | Оновлення системи |
| `/api/mode` | Поточний режим |
| `/api/mode/switch` | Зміна режиму |

### Ключові модулі бекенду

| Файл | Розмір | Відповідальність |
|------|--------|-----------------|
| `kbg_web/app.py` | 175KB | Монолітний Flask-додаток, всі маршрути |
| `kbg_web/status_helper.py` | 16KB | Розрахунок прогресу конвертації |
| `kbg_web/edit_store.py` | 3KB | Сховище редагувань |
| `common/utils.py` | 17KB | Утиліти загального призначення |
| `common/book_paths.py` | 4KB | Шляхи до книг |
| `common/cast_registry.py` | 5KB | Реєстр персонажів |
| `common/support_profile.py` | 8KB | Профіль підтримки |
| `translate_manga.py` | 111KB | Переклад манги |
| `audio_stage.py` | 24KB | Синтез аудіо |

### UI дизайн (поточний)

- **OLED-адаптивна тема**: глибокий темний фон (`#09090b`, `#0d0d14`)
- **Glassmorphism**: напівпрозорі картки з backdrop-blur
- **CSS Variables**: `--bg-base`, `--surface-card`, `--primary` тощо
- **Шрифти**: 'Outfit', 'Fira Code', system-ui
- **Колірна схема**: градієнт `#4fd1c5 → #2b7a78 → #f0b429` для брендингу
- **Mobile-first**: оптимізовано для смартфонів (Termux + Android)
- **Видрочка 🦦**: іконка — видра (otter) як талісман проєкту

---

## Аналіз Astryx Design System

### Ключові характеристики

| Аспект | Деталі |
|--------|--------|
| **Розробник** | Meta (8+ років розвитку) |
| **Компоненти** | 150+ React UI компонентів |
| **Стилізація** | StyleX (atomic CSS-in-JS) |
| **Теми** | Модульні: `theme-neutral`, `theme-gothic` тощо |
| **CLI** | `@astryxdesign/cli` — scaffolding, docs, `--dense`, `--json` |
| **AI-ready** | MCP-сервер для AI-агентів, спеціальні інструкції |
| **SSR** | Повна підтримка (Next.js, Remix) |
| **Tailwind bridge** | Tailwind v4 bridge для CSS utility classes |

### Структура пакетів

```
@astryxdesign/core          — React-компоненти + theming
@astryxdesign/cli           — CLI для scaffolding та docs
@astryxdesign/theme-neutral — Нейтральна тема
@astryxdesign/theme-gothic  — Готична тема
```

### Стилізація: "No Lock-in"

Astryx не вимагає StyleX від споживачів:
- **`xstyle` prop** — для StyleX overrides
- **`className` prop** — для standard CSS
- **`style` prop** — для inline styles
- **Tailwind v4 bridge** — маппінг всіх токенів на Tailwind utilities
- **Підтримка**: MUI, Chakra, Panda, Emotion, styled-components, UnoCSS, Sass

### 3 стовпи архітектури

1. **Foundations**: typography, color, spacing, shape, motion tokens
2. **Components**: 150+ reusable UI building blocks (Button, TextInput, Dialog, CommandPalette, Selector...)
3. **Patterns**: form wizards, table pages, data entry flows, navigation

---

## Оцінка сумісності

### ⚠️ Критичний конфлікт: Flask + Jinja2 vs React

| Аспект | Vydra (поточний) | Astryx (цільовий) |
|--------|-----------------|-------------------|
| Рендеринг | **Серверний (Jinja2)** | **Клієнтський (React)** |
| Компоненти | HTML-шаблони | React JSX |
| Стилі | Inline CSS + CSS vars | StyleX / Tailwind |
| Стан | Vanilla JS + fetch | React state / hooks |
| Маршрутизація | Flask `@app.route` | React Router |
| Шаблонізатор | Jinja2 `{{ }}` | JSX `{}` |

### Можливі стратегії інтеграції

#### Стратегія A: Flask API + React SPA (Рекомендована) ✅

```
┌─────────────────────────────┐
│      React SPA (Astryx)     │
│   ┌────────┐  ┌──────────┐  │
│   │ Vite   │  │ React    │  │
│   │ Build  │  │ Router   │  │
│   └────────┘  └──────────┘  │
│          fetch/API           │
└──────────────┬──────────────┘
               │ HTTP JSON
┌──────────────┴──────────────┐
│    Flask API Backend        │
│   /api/books, /api/run...   │
│   (без змін у бізнес-логіці)│
└─────────────────────────────┘
```

**Плюси:**
- Flask backend залишається без змін
- Всі 60+ API маршрутів вже готові
- Astryx React компоненти працюють нативно
- SSR через Vite або Next.js
- Повна підтримка тем та дизайн-токенів

**Мінуси:**
- Потрібно переписати всю логіку з 4 Jinja2 шаблонів
- Додатковий build pipeline (npm/Vite)
- Збільшення бандлу (React + Astryx)

#### Стратегія B: Часткова інтеграція через CDN/Web Components ⚡

```
Flask + Jinja2 → серверний рендеринг
  ↓ вставляємо
<astryx-button>, <astryx-dialog> (Web Components)
```

**Плюси:**
- Мінімальні зміни у Flask
- Поступова міграція
- Не потрібен build pipeline

**Мінуси:**
- ❌ Astryx НЕ має Web Components API
- Потрібно створювати власні обгортки
- Втрачається більшість переваг дизайн-системи

#### Стратегія C: Flask подає React-бандл (гібрид)

```
Flask route "/" → serve index.html (React SPA)
Flask /api/* → JSON endpoints
Flask /static/* → Vite build output
```

**Плюси:**
- Один сервер (Flask)
- Мінімальне DevOps навантаження
- Ідеально для Termux

**Мінуси:**
- Потрібен Vite build → output у static/
- Не зовсім стандартний патерн

---

## Архітектурні рішення

### Рекомендована архітектура: **Стратегія C (Flask + React SPA)** 🏆

Для Vydra рекомендується **гібридний підхід (Стратегія C)**, оскільки:

1. **Termux-сумісність**: один Flask-процес — критично для Android
2. **Мінімум DevOps**: не потрібен окремий Node.js сервер
3. **API вже готові**: 60+ JSON endpoints залишаються як є
4. **Offline-first**: весь UI запакований у `static/`

### Запропонована файлова структура

```
kindle-butch-gen/
├── kbg_web/
│   ├── app.py              # Flask backend (мінімальні зміни)
│   ├── status_helper.py    # Без змін
│   ├── edit_store.py       # Без змін
│   ├── static/
│   │   ├── dist/           # NEW: Vite build output
│   │   │   ├── index.html
│   │   │   ├── assets/
│   │   │   └── ...
│   │   ├── vydra.png
│   │   └── vydra-sm.png
│   └── templates/          # DEPRECATED: поступово замінюються
│       ├── dashboard.html  # → React Dashboard
│       ├── stages.html     # → React StagesView
│       ├── downloads.html  # → React Downloads
│       └── manual.html     # → React Manual
├── frontend/               # NEW: React + Astryx проєкт
│   ├── package.json
│   ├── vite.config.ts
│   ├── src/
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   ├── theme/
│   │   │   └── vydra-theme.ts   # Кастомна тема Astryx
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx
│   │   │   ├── Login.tsx
│   │   │   ├── Downloads.tsx
│   │   │   ├── Manual.tsx
│   │   │   ├── Stages.tsx
│   │   │   └── BookView.tsx
│   │   ├── components/
│   │   │   ├── BookCard.tsx
│   │   │   ├── ConversionProgress.tsx
│   │   │   ├── MangaViewer.tsx
│   │   │   ├── TTSPreview.tsx
│   │   │   ├── CharacterEditor.tsx
│   │   │   ├── EditQueue.tsx
│   │   │   └── ...
│   │   ├── hooks/
│   │   │   ├── useBooks.ts
│   │   │   ├── useConversion.ts
│   │   │   └── useApi.ts
│   │   └── api/
│   │       └── client.ts       # Fetch wrapper для Flask API
│   └── dist/                   # Build output → symlink to kbg_web/static/dist
```

### Кастомна тема Vydra для Astryx

```typescript
// frontend/src/theme/vydra-theme.ts
import { defineTheme } from '@astryxdesign/core';

export const vydraTheme = defineTheme({
  name: 'vydra',
  tokens: {
    // OLED-оптимізовані кольори
    colorBgBase: '#09090b',
    colorBgSurface: '#0d0d14',
    colorBgCard: '#14141f',
    colorBorderDefault: '#2a2a3d',
    
    // Брендові кольори Vydra
    colorPrimary: '#8b5cf6',         // Purple accent
    colorSecondary: '#4fd1c5',       // Teal
    colorGradientStart: '#4fd1c5',
    colorGradientMid: '#2b7a78',
    colorGradientEnd: '#f0b429',
    
    // Типографіка
    fontFamilyBody: "'Outfit', system-ui, sans-serif",
    fontFamilyCode: "'Fira Code', monospace",
    
    // Radius
    radiusCard: '14px',
    radiusButton: '8px',
    radiusInput: '8px',
  },
  components: {
    Card: {
      background: 'rgba(20, 20, 31, 0.8)',
      backdropFilter: 'blur(12px)',
      border: '1px solid var(--border-default)',
    },
  },
});
```

---

## План міграції по фазах

### Фаза 0: Підготовка (1-2 дні)

- [ ] Ініціалізація `frontend/` проєкту (Vite + React + TypeScript)
- [ ] Встановлення `@astryxdesign/core`, `@astryxdesign/cli`
- [ ] Створення кастомної теми `vydra-theme`
- [ ] Налаштування Vite build → `kbg_web/static/dist/`
- [ ] Модифікація Flask: catch-all route для SPA fallback
- [ ] Тест: React "Hello World" подається через Flask

### Фаза 1: Login + Layout Shell (2-3 дні)

- [ ] `Login.tsx` — форма логіну (Astryx `TextInput`, `Button`)
- [ ] `AppShell.tsx` — навігація, sidebar, header
- [ ] React Router: `/`, `/login`, `/downloads`, `/manual`
- [ ] API client: fetch wrapper з auth cookies
- [ ] Тест: логін → дашборд через React

### Фаза 2: Dashboard (3-5 днів)

- [ ] `Dashboard.tsx` — список книг
- [ ] `BookCard.tsx` — картка книги (Astryx `Card`)
- [ ] `AddBookDialog.tsx` — діалог додавання книги (Astryx `Dialog`)
- [ ] `ConversionProgress.tsx` — прогрес конвертації
- [ ] `FileUploader.tsx` — завантаження файлів
- [ ] Polling: `/api/status/<slug>` → стан у реальному часі
- [ ] Тест: повний цикл add → run → monitor → download

### Фаза 3: Stages Viewer (3-5 днів)

- [ ] `StagesView.tsx` — перегляд етапів (Original/Translated toggle)
- [ ] `ChapterList.tsx` — список розділів
- [ ] `PagePreview.tsx` — прев'ю сторінок
- [ ] `AudioPlayer.tsx` — прослуховування аудіо
- [ ] Manga triptych viewer (Original/Cleaned/Translated)
- [ ] Тест: перегляд та навігація між етапами

### Фаза 4: Live Editing (3-5 днів)

- [ ] `EditQueue.tsx` — черга редагувань
- [ ] `TextEditor.tsx` — редактор тексту з наголосами
- [ ] `MangaBubbleEditor.tsx` — редактор бульбашок манги
- [ ] `SidePanel.tsx` — бічна панель (не modal!)
- [ ] QA прапорці з кольоровою кодіфікацією
- [ ] Тест: повний цикл edit → approve/discard

### Фаза 5: Решта сторінок (2-3 дні)

- [ ] `Downloads.tsx` — архів завантажень
- [ ] `Manual.tsx` — мануал/документація
- [ ] `Settings.tsx` — глобальні налаштування
- [ ] `Models.tsx` — управління AI моделями
- [ ] `CharacterEditor.tsx` — Cast Registry UI
- [ ] `ModeSwitcher.tsx` — перемикач режимів

### Фаза 6: Polish та Termux-тестування (2-3 дні)

- [ ] Оптимізація бандлу для мобільних
- [ ] Тестування на реальному Android/Termux
- [ ] PWA manifest для "Add to Home Screen"
- [ ] Офлайн-fallback (Service Worker)
- [ ] Прибирання legacy Jinja2 шаблонів

---

## Ризики та обмеження

### 🔴 Критичні ризики

| Ризик | Деталі | Мітигація |
|-------|--------|-----------|
| **Node.js на Termux** | Vite/React build потребує Node.js | Build на десктопі → deploy як статичні файли |
| **Розмір бандлу** | React + Astryx ~300-500KB gzipped | Code splitting, lazy loading, tree shaking |
| **Монолітний app.py** | 175KB, 3695 рядків — складно рефакторити | Залишити як є, працювати тільки з API |

### 🟡 Помірні ризики

| Ризик | Деталі | Мітигація |
|-------|--------|-----------|
| **Offline-first** | React SPA потребує хоча б JS для рендеру | Pre-render + Service Worker |
| **Стилістична відмінність** | Astryx-стиль vs поточний glassmorphism | Кастомна тема `vydra-theme` |
| **Manga viewer** | Складна інтерактивна логіка | Поступова міграція, спочатку read-only |

### 🟢 Низькі ризики

| Ризик | Деталі |
|-------|--------|
| API сумісність | Всі 60+ endpoints вже повертають JSON |
| Auth | Session cookies працюють із fetch/React |
| Маршрутизація | Flask catch-all + React Router = стандартний патерн |

---

## Оцінка трудовитрат

| Фаза | Обсяг | Оцінка |
|------|-------|--------|
| Фаза 0: Підготовка | Scaffolding, тема, Vite | 1-2 дні |
| Фаза 1: Login + Shell | Auth, layout | 2-3 дні |
| Фаза 2: Dashboard | Книги, прогрес, upload | 3-5 днів |
| Фаза 3: Stages | Viewer, manga, audio | 3-5 днів |
| Фаза 4: Editing | Text/manga editors | 3-5 днів |
| Фаза 5: Решта | Downloads, settings, models | 2-3 дні |
| Фаза 6: Polish | Termux, PWA, cleanup | 2-3 дні |
| **Загалом** | | **16-26 днів** |

> **Примітка:** Оцінка для одного розробника (або AI-агента). При паралельній роботі час може бути зменшений на 30-40%.

---

## Альтернативи (якщо Astryx не підходить)

Якщо повна міграція на Astryx виявиться занадто масштабною, розглянемо полегшені варіанти:

1. **Astryx Design Tokens Only** — використати лише токени (кольори, шрифти, spacing) без React-компонентів, залишивши Jinja2 шаблони
2. **Tailwind v4 з Astryx Bridge** — використати Tailwind utilities, маппити на Astryx токени
3. **Поступова міграція**: спочатку один view (наприклад, Downloads), потім решта

---

*Документ створено на основі аналізу:*
- *NotebookLM записник "Astryx" (ace65e5c)*
- *NotebookLM записник "kbg-redesign" (0c18b603)*
- *GitNexus індекс kindle-butch-gen (93 файли, 1453 вузли)*
- *Локальний аналіз кодової бази*
