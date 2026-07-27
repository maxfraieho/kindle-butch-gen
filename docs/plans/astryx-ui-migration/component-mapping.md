# Маппінг компонентів: Vydra HTML → Astryx React

> Детальний перелік того, які HTML-елементи з Jinja2 шаблонів
> мають бути замінені на які Astryx React компоненти.

---

## Login Page (`LOGIN_PAGE` inline в app.py)

| Поточний HTML | Astryx компонент | Примітки |
|---------------|-----------------|----------|
| `<div class="box">` | `<Card>` | С кастомним стилем `vydra-theme` |
| `<img src="vydra-sm.png">` | `<Avatar src="...">` | Круглий з бордером |
| `<h1>Vydra</h1>` | `<Heading level={1}>` | З gradient text |
| `<form>` | `<Form>` | Astryx Form pattern |
| `<input name="username">` | `<TextInput label="Логін">` | З autocomplete |
| `<input type="password">` | `<TextInput type="password">` | З autocomplete |
| `<button type="submit">` | `<Button variant="primary">` | Увійти |
| `<div class="err">` | `<Alert variant="error">` | Помилка логіну |

---

## Dashboard (`dashboard.html` — 157KB)

### Верхній рівень

| Поточний HTML | Astryx компонент | Примітки |
|---------------|-----------------|----------|
| Navigation bar | `<TopBar>` / `<TabBar>` | Dashboard ↔ Downloads |
| Book list container | `<Stack spacing="md">` | Vertical stack of cards |
| Book card | `<Card>` | З actions у footer |
| Add book button | `<Button icon={PlusIcon}>` | Floating action |
| Settings gear | `<IconButton>` | У header |

### Book Card вміст

| Елемент | Astryx компонент |
|---------|-----------------|
| Book title | `<Heading level={3}>` |
| Author/language | `<Text variant="secondary">` |
| Status badge | `<Badge variant={status}>` |
| Progress bar | `<ProgressBar value={pct}>` |
| Run/Stop/Delete buttons | `<ButtonGroup>` |
| Download links | `<Link>` + `<IconButton>` |

### Add Book Dialog

| Елемент | Astryx компонент |
|---------|-----------------|
| Modal container | `<Dialog>` |
| File upload | `<FileInput>` / custom uploader |
| Directory browser | `<TreeView>` / custom |
| Slug input | `<TextInput>` |
| Title/Author fields | `<TextInput>` |
| Language selector | `<Select>` |
| Submit button | `<Button variant="primary">` |

### Settings Panel

| Елемент | Astryx компонент |
|---------|-----------------|
| Output root path | `<TextInput>` + `<Button>` |
| TTS voice selector | `<Select>` |
| Speaker ID slider | `<Slider>` |
| Speed control | `<Slider min={0.5} max={2.0}>` |
| TTS preview play | `<IconButton icon={PlayIcon}>` |

---

## Stages View (`stages.html` — 166KB)

### Структура сторінки

| Елемент | Astryx компонент |
|---------|-----------------|
| Original/Translated toggle | `<SegmentedControl>` |
| Chapter navigation | `<Sidebar>` + `<Nav>` |
| Page content area | `<ScrollArea>` |
| Audio player | Custom `<AudioPlayer>` |
| Edit button | `<Button variant="outline">` |

### Manga Triptych Viewer

| Елемент | Astryx компонент |
|---------|-----------------|
| Image panel (3-way) | Custom `<TriptychViewer>` |
| Bubble overlay | Custom `<BubbleOverlay>` |
| Quality flag border | Conditional `className` |
| Bubble edit side panel | `<Drawer side="right">` |
| OCR text display | `<Code>` |
| Translation textarea | `<TextArea>` |

### Live Edit Queue

| Елемент | Astryx компонент |
|---------|-----------------|
| Queue list | `<Table>` / `<Stack>` |
| Edit item | `<Card>` compact |
| Original text | `<Text>` |
| Edited text | `<TextArea>` |
| Approve button | `<Button variant="success">` |
| Discard button | `<Button variant="danger">` |
| Stress marks editor | Custom `<StressEditor>` |

---

## Downloads (`downloads.html` — 15KB)

| Елемент | Astryx компонент |
|---------|-----------------|
| Search bar | `<SearchInput>` |
| Filter controls | `<SegmentedControl>` |
| Book card (download) | `<Card>` |
| File type badge | `<Badge>` |
| File size text | `<Text variant="secondary">` |
| Download button | `<Button icon={DownloadIcon}>` |
| Delete button | `<IconButton variant="danger">` |

---

## Manual (`manual.html` — 24KB)

| Елемент | Astryx компонент |
|---------|-----------------|
| TOC sidebar | `<Sidebar>` + `<Nav>` |
| Content sections | `<Stack>` |
| Screenshot images | `<Image>` |
| Code blocks | `<Code>` |
| Step-by-step | `<OrderedList>` |

---

## Спільні компоненти (cross-page)

| Компонент | Astryx | Де використовується |
|-----------|--------|-------------------|
| `<AppShell>` | `<Frame>` / custom | Всі сторінки |
| `<TopNav>` | `<TopBar>` | Header на всіх сторінках |
| `<BottomNav>` | `<BottomBar>` | Mobile navigation |
| `<Toast>` | `<Toast>` | Нотифікації API |
| `<LoadingSpinner>` | `<Spinner>` | Всі async операції |
| `<ErrorBoundary>` | `<ErrorBoundary>` | Обгортка для кожної сторінки |
| `<ConfirmDialog>` | `<AlertDialog>` | Delete operations |

---

## React Hooks (нові)

```typescript
// useBooks() — керування списком книг
// useConversion(slug) — стан конвертації (polling)
// useCharacters(slug) — Cast Registry CRUD
// useEditQueue(slug) — черга редагувань
// useTTS(slug) — TTS налаштування та прев'ю
// useModels() — статус AI моделей
// useAuth() — логін/логаут/session
// useSettings() — глобальні налаштування
```

---

## API Client

```typescript
// api/client.ts
const BASE = '';  // Same origin (Flask)

export async function apiFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    credentials: 'same-origin',  // Session cookies
    headers: {
      'Content-Type': 'application/json',
      ...opts?.headers,
    },
  });
  if (res.status === 401) {
    window.location.href = '/login';
    throw new Error('Unauthorized');
  }
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}
```
