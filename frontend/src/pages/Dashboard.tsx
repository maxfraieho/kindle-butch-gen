import React, { useState, useEffect } from 'react';
import { apiFetch, Book } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { BookSettingsModal } from './BookSettingsModal';
import { BookOpen, Plus, Play, Square, Trash2, RefreshCw, Layers, Upload, Folder, CheckCircle, Settings2 } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const Dashboard: React.FC = () => {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [serverPath, setServerPath] = useState('');
  const [slug, setSlug] = useState('');
  const [title, setTitle] = useState('');
  const [authors, setAuthors] = useState('');
  const [targetLang, setTargetLang] = useState('uk');
  const [sourceLang, setSourceLang] = useState('auto');
  const [isManga, setIsManga] = useState(false);
  const [addingBook, setAddingBook] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [settingsSlug, setSettingsSlug] = useState<string | null>(null);
  const navigate = useNavigate();


  const fetchBooks = async () => {
    try {
      const data = await apiFetch<Book[] | { books: Book[] }>('/api/books');
      const bookList = Array.isArray(data) ? data : data.books || [];
      setBooks(bookList);
    } catch (err) {
      console.error('Помилка завантаження книг:', err);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchBooks();
    const interval = setInterval(fetchBooks, 4000);
    return () => clearInterval(interval);
  }, []);

  const handleRun = async (slug: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiFetch(`/api/run/${slug}`, { method: 'POST' });
      fetchBooks();
    } catch (err: any) {
      alert(`Помилка запуску: ${err.message}`);
    }
  };

  const handleStop = async (slug: string, e: React.MouseEvent) => {
    e.stopPropagation();
    try {
      await apiFetch(`/api/stop/${slug}`, { method: 'POST' });
      fetchBooks();
    } catch (err: any) {
      alert(`Помилка зупинки: ${err.message}`);
    }
  };

  const handleDelete = async (slug: string, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Ви дійсно бажаєте видалити книгу "${slug}"?`)) return;
    try {
      await apiFetch(`/api/delete/${slug}`, { method: 'DELETE' });
      fetchBooks();
    } catch (err: any) {
      alert(`Помилка видалення: ${err.message}`);
    }
  };

  // Helper to generate slug from string
  const generateSlug = (str: string) => {
    const nameWithoutExt = str.replace(/\.[^/.]+$/, '');
    return nameWithoutExt
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9_-]/g, '-')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '') || 'new-book';
  };

  // Helper to format clean title from string
  const generateTitle = (str: string) => {
    const nameWithoutExt = str.replace(/\.[^/.]+$/, '');
    return nameWithoutExt
      .replace(/[_-]/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  };

  // Auto-fill metadata when file is selected
  const handleFileChange = (file: File | null) => {
    setUploadFile(file);
    if (file) {
      const suggestedSlug = generateSlug(file.name);
      const suggestedTitle = generateTitle(file.name);
      if (!slug || slug === 'new-book') setSlug(suggestedSlug);
      if (!title) setTitle(suggestedTitle);
      if (!authors) setAuthors('Невідомий автор');
      
      // Auto detect manga extension
      const ext = file.name.split('.').pop()?.toLowerCase();
      if (['cbz', 'cbr', 'cb7', 'zip', 'rar'].includes(ext || '')) {
        setIsManga(true);
      }
    }
  };

  // Auto-fill metadata when server path is typed
  const handleServerPathChange = (val: string) => {
    setServerPath(val);
    if (val && !uploadFile) {
      const fileName = val.split('/').pop() || '';
      if (fileName) {
        const suggestedSlug = generateSlug(fileName);
        const suggestedTitle = generateTitle(fileName);
        if (!slug || slug === 'new-book') setSlug(suggestedSlug);
        if (!title) setTitle(suggestedTitle);
        if (!authors) setAuthors('Невідомий автор');
        
        const ext = fileName.split('.').pop()?.toLowerCase();
        if (['cbz', 'cbr', 'cb7', 'zip', 'rar'].includes(ext || '')) {
          setIsManga(true);
        }
      }
    }
  };

  const handleAddBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const errors: Record<string, string> = {};

    if (!uploadFile && !serverPath.trim()) {
      errors.fileOrPath = 'Оберіть файл для завантаження або вкажіть шлях на сервері';
    }
    if (!title.trim()) {
      errors.title = "Назва книги є обов'язковою";
    }
    if (!slug.trim()) {
      errors.slug = "Ідентифікатор (slug) є обов'язковим";
    } else if (!/^[a-z0-9_-]+$/.test(slug)) {
      errors.slug = "Slug може містити лише латинські літери, цифри, дефіс та підкреслення";
    }
    if (!authors.trim()) {
      errors.authors = "Вкажіть авторів книги";
    }

    if (Object.keys(errors).length > 0) {
      setFieldErrors(errors);
      return;
    }

    setFieldErrors({});
    setAddingBook(true);

    try {
      if (uploadFile) {
        const formData = new FormData();
        formData.append('file', uploadFile);
        formData.append('slug', slug.trim());
        formData.append('title', title.trim());
        formData.append('authors', authors.trim());
        formData.append('lang', targetLang);
        formData.append('source_lang', sourceLang);
        formData.append('is_manga', isManga ? 'true' : 'false');

        await apiFetch('/api/upload', {
          method: 'POST',
          body: formData,
        });
      } else if (serverPath.trim()) {
        await apiFetch('/api/add-by-path', {
          method: 'POST',
          body: JSON.stringify({
            pdf_path: serverPath.trim(),
            slug: slug.trim(),
            title: title.trim(),
            authors: authors.trim(),
            lang: targetLang,
            source_lang: sourceLang,
            is_manga: isManga,
          }),
        });
      }

      setIsAddModalOpen(false);
      setUploadFile(null);
      setServerPath('');
      setSlug('');
      setTitle('');
      setAuthors('');
      fetchBooks();
    } catch (err: any) {
      alert(`Помилка додавання книги: ${err.message}`);
    } finally {
      setAddingBook(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 sm:gap-6 bg-[#131c2e] p-6 sm:p-8 rounded-3xl border border-slate-700/60 shadow-xl">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight">
            Бібліотека книг
          </h1>
          <p className="text-sm text-slate-300 mt-1">
            Керування конвертацією, перекладом та генерацією аудіо
          </p>
        </div>

        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="md"
            icon={<RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />}
            onClick={() => { setRefreshing(true); fetchBooks(); }}
          >
            Оновити
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => setIsAddModalOpen(true)}
          >
            Додати книгу
          </Button>
        </div>
      </div>

      {/* Book Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="h-48 p-6 animate-pulse bg-[#131c2e] border-slate-800" />
          ))}
        </div>
      ) : books.length === 0 ? (
        <Card className="text-center py-12 px-4 space-y-4 bg-[#131c2e] border-slate-700/60">
          <div className="w-14 h-14 rounded-2xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto border border-emerald-500/30">
            <BookOpen className="w-7 h-7" />
          </div>
          <div className="space-y-1">
            <h3 className="text-lg font-bold text-white">Бібліотека порожня</h3>
            <p className="text-sm text-slate-400 max-w-md mx-auto">
              Завантажте файл вашої книги (EPUB, PDF, CBZ) або вкажіть шлях на сервері, щоб розпочати обробку.
            </p>
          </div>
          <Button
            variant="primary"
            size="md"
            icon={<Plus className="w-4 h-4" />}
            onClick={() => setIsAddModalOpen(true)}
          >
            Додати першу книгу
          </Button>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {books.map((book) => {
            const isRunning = book.status === 'running' || book.status === 'in_progress';
            const isCompleted = book.status === 'completed' || book.progress === 100;
            const rawProgress = typeof book.progress === 'number' && !Number.isNaN(book.progress) ? book.progress : 0;

            return (
              <Card
                key={book.slug}
                hoverable
                onClick={() => navigate(`/view/${book.slug}`)}
                className="bg-[#131c2e] border border-slate-700/60 hover:border-emerald-500/50 flex flex-col justify-between space-y-5 p-6 shadow-xl transition-all"
              >
                {/* Header info */}
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-extrabold text-lg text-white group-hover:text-emerald-300 transition-colors line-clamp-1">
                      {book.title || book.slug}
                    </h3>
                    <Badge variant={isRunning ? 'emerald' : isCompleted ? 'amber' : 'slate'}>
                      {isRunning ? 'Обробка' : isCompleted ? 'Готово' : 'Очікує'}
                    </Badge>
                  </div>
                  <p className="text-xs text-slate-300 truncate font-medium">
                    {book.authors || 'Невідомий автор'}
                  </p>
                </div>

                {/* Progress section */}
                <div className="space-y-2 pt-2 border-t border-slate-800">
                  <ProgressBar
                    progress={rawProgress}
                    statusText={book.current_stage || (isCompleted ? 'Переклад завершено' : 'Готовий до запуску')}
                  />
                </div>

                {/* Actions Footer - Responsive Flex Wrap */}
                <div className="flex flex-wrap items-center justify-between gap-2 pt-4 mt-auto border-t border-slate-800/80">
                  <div className="flex flex-wrap items-center gap-2">
                    {isRunning ? (
                      <Button
                        variant="danger"
                        size="sm"
                        icon={<Square className="w-3.5 h-3.5 fill-current" />}
                        onClick={(e) => handleStop(book.slug, e)}
                        className="px-2.5 py-1.5 text-xs"
                      >
                        Зупинити
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        icon={<Play className="w-3.5 h-3.5 fill-current" />}
                        onClick={(e) => handleRun(book.slug, e)}
                        className="px-2.5 py-1.5 text-xs"
                      >
                        Запустити
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Layers className="w-3.5 h-3.5" />}
                      onClick={(e) => { e.stopPropagation(); navigate(`/view/${book.slug}`); }}
                      className="px-2.5 py-1.5 text-xs"
                    >
                      Етапи
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Settings2 className="w-3.5 h-3.5" />}
                      onClick={(e) => { e.stopPropagation(); setSettingsSlug(book.slug); }}
                      title="Налаштування книги"
                      className="px-2.5 py-1.5 text-xs"
                    >
                      Налаштування
                    </Button>
                  </div>

                  <button
                    onClick={(e) => handleDelete(book.slug, e)}
                    title="Видалити"
                    className="p-2 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors ml-auto"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      )}

      {/* Add Book Modal Dialog */}
      <Modal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        title="Додати книгу для обробки"
      >
        <form onSubmit={handleAddBookSubmit} className="space-y-4 max-h-[75vh] overflow-y-auto pr-1">
          {fieldErrors.fileOrPath && (
            <div className="p-3 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-xs font-medium">
              {fieldErrors.fileOrPath}
            </div>
          )}

          {/* File Upload Section */}
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-300">
              Завантажити файл (EPUB / PDF / CBZ)
            </label>
            <div className={`relative border-2 border-dashed rounded-xl p-4 text-center cursor-pointer transition-colors bg-[#090e1c] ${
              fieldErrors.fileOrPath ? 'border-rose-500/60 bg-rose-950/10' : 'border-slate-700 hover:border-emerald-500/60'
            }`}>
              <input
                type="file"
                accept=".epub,.pdf,.cbz,.zip,.rar"
                onChange={(e) => handleFileChange(e.target.files?.[0] || null)}
                className="absolute inset-0 opacity-0 cursor-pointer"
              />
              <Upload className="w-7 h-7 text-emerald-400 mx-auto mb-1.5" />
              <p className="text-xs font-semibold text-slate-200">
                {uploadFile ? uploadFile.name : 'Натисніть або перетягніть файл сюди'}
              </p>
              <p className="text-[11px] text-slate-400 mt-1 font-mono">.epub, .pdf, .cbz (до 1GB)</p>
            </div>
          </div>

          <div className="relative text-center my-1">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-800"></div></div>
            <span className="relative bg-[#131c2e] px-3 text-[11px] text-slate-400">або шлях на сервері</span>
          </div>

          {/* Server Path Section */}
          <div className="space-y-1.5">
            <label className="block text-xs font-semibold text-slate-300">
              Шлях до книги на сервері
            </label>
            <div className="relative flex items-center">
              <Folder className="w-4 h-4 absolute left-3 text-emerald-400 z-10 pointer-events-none" />
              <input
                type="text"
                value={serverPath}
                onChange={(e) => handleServerPathChange(e.target.value)}
                placeholder="/sdcard/Documents/Books/my_book.epub"
                className={`w-full pl-9 pr-3 py-2 rounded-xl bg-[#090e1c] text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs font-mono border ${
                  fieldErrors.fileOrPath ? 'border-rose-500/60 bg-rose-950/10' : 'border-slate-700'
                }`}
              />
            </div>
          </div>

          {/* Explicit Metadata Fields (Task 1 Fix) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2 border-t border-slate-800/80">
            {/* Title */}
            <div className="space-y-1 sm:col-span-2">
              <label className="block text-xs font-semibold text-slate-300">
                Назва книги <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                value={title}
                onChange={(e) => { setTitle(e.target.value); if (fieldErrors.title) setFieldErrors(prev => ({ ...prev, title: '' })); }}
                placeholder="Гаррі Поттер і філософський камінь"
                className={`w-full px-3 py-2 rounded-xl bg-[#090e1c] text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs border ${
                  fieldErrors.title ? 'border-rose-500 bg-rose-950/20' : 'border-slate-700'
                }`}
              />
              {fieldErrors.title && <p className="text-[11px] text-rose-400">{fieldErrors.title}</p>}
            </div>

            {/* Slug */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-300">
                Ідентифікатор (Slug) <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); if (fieldErrors.slug) setFieldErrors(prev => ({ ...prev, slug: '' })); }}
                placeholder="harry-potter"
                className={`w-full px-3 py-2 rounded-xl bg-[#090e1c] text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs font-mono border ${
                  fieldErrors.slug ? 'border-rose-500 bg-rose-950/20' : 'border-slate-700'
                }`}
              />
              {fieldErrors.slug && <p className="text-[11px] text-rose-400">{fieldErrors.slug}</p>}
            </div>

            {/* Authors */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-300">
                Автори <span className="text-rose-400">*</span>
              </label>
              <input
                type="text"
                value={authors}
                onChange={(e) => { setAuthors(e.target.value); if (fieldErrors.authors) setFieldErrors(prev => ({ ...prev, authors: '' })); }}
                placeholder="Дж. К. Роулінґ"
                className={`w-full px-3 py-2 rounded-xl bg-[#090e1c] text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs border ${
                  fieldErrors.authors ? 'border-rose-500 bg-rose-950/20' : 'border-slate-700'
                }`}
              />
              {fieldErrors.authors && <p className="text-[11px] text-rose-400">{fieldErrors.authors}</p>}
            </div>

            {/* Target Language */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-300">
                Мова перекладу
              </label>
              <select
                value={targetLang}
                onChange={(e) => setTargetLang(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-[#090e1c] border border-slate-700 text-white focus:outline-none focus:border-emerald-400 text-xs"
              >
                <option value="uk">Українська (uk)</option>
                <option value="en">English (en)</option>
                <option value="de">Deutsch (de)</option>
                <option value="fr">Français (fr)</option>
                <option value="pl">Polski (pl)</option>
              </select>
            </div>

            {/* Source Language */}
            <div className="space-y-1">
              <label className="block text-xs font-semibold text-slate-300">
                Вихідна мова
              </label>
              <select
                value={sourceLang}
                onChange={(e) => setSourceLang(e.target.value)}
                className="w-full px-3 py-2 rounded-xl bg-[#090e1c] border border-slate-700 text-white focus:outline-none focus:border-emerald-400 text-xs"
              >
                <option value="auto">Автовизначення (Auto)</option>
                <option value="en">English (en)</option>
                <option value="ja">Японська (ja)</option>
                <option value="de">Deutsch (de)</option>
                <option value="zh">Китайська (zh)</option>
              </select>
            </div>

            {/* Is Manga Checkbox */}
            <div className="sm:col-span-2 pt-1 flex items-center gap-2">
              <input
                type="checkbox"
                id="isMangaCheckbox"
                checked={isManga}
                onChange={(e) => setIsManga(e.target.checked)}
                className="w-4 h-4 rounded border-slate-700 bg-[#090e1c] text-emerald-500 focus:ring-emerald-500"
              />
              <label htmlFor="isMangaCheckbox" className="text-xs font-medium text-slate-200 cursor-pointer select-none">
                Це комікс / манґа (обробка сторінок та OCR)
              </label>
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-3 border-t border-slate-800">
            <Button
              type="button"
              variant="ghost"
              onClick={() => setIsAddModalOpen(false)}
            >
              Скасувати
            </Button>
            <Button
              type="submit"
              variant="primary"
              isLoading={addingBook}
              icon={<CheckCircle className="w-4 h-4" />}
            >
              Додати книгу
            </Button>
          </div>
        </form>
      </Modal>

      {/* Per-book Settings Modal */}
      <BookSettingsModal
        slug={settingsSlug}
        bookTitle={books.find((b) => b.slug === settingsSlug)?.title}
        isOpen={settingsSlug !== null}
        onClose={() => setSettingsSlug(null)}
      />
    </div>
  );
};
