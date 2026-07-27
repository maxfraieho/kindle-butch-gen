import React, { useState, useEffect } from 'react';
import { apiFetch, Book } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Badge } from '../components/ui/Badge';
import { Modal } from '../components/ui/Modal';
import { BookOpen, Plus, Play, Square, Trash2, RefreshCw, Layers, Upload, Folder, CheckCircle } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const Dashboard: React.FC = () => {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [serverPath, setServerPath] = useState('');
  const [addingBook, setAddingBook] = useState(false);
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

  const handleAddBookSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setAddingBook(true);
    try {
      if (uploadFile) {
        const formData = new FormData();
        formData.append('file', uploadFile);
        await apiFetch('/api/upload', {
          method: 'POST',
          body: formData,
        });
      } else if (serverPath) {
        await apiFetch('/api/add-by-path', {
          method: 'POST',
          body: JSON.stringify({ path: serverPath }),
        });
      }
      setIsAddModalOpen(false);
      setUploadFile(null);
      setServerPath('');
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
          <div>
            <h3 className="text-xl font-bold text-white">Немає доданих книг</h3>
            <p className="text-sm text-slate-300 mt-1 max-w-sm mx-auto">
              Завантажте PDF або EPUB файл, щоб розпочати автоматичний переклад та синтез аудіо
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

                {/* Actions Footer */}
                <div className="flex items-center justify-between pt-4 mt-auto border-t border-slate-800/80">
                  <div className="flex items-center gap-2">
                    {isRunning ? (
                      <Button
                        variant="danger"
                        size="sm"
                        icon={<Square className="w-3.5 h-3.5 fill-current" />}
                        onClick={(e) => handleStop(book.slug, e)}
                      >
                        Зупинити
                      </Button>
                    ) : (
                      <Button
                        variant="primary"
                        size="sm"
                        icon={<Play className="w-3.5 h-3.5 fill-current" />}
                        onClick={(e) => handleRun(book.slug, e)}
                      >
                        Запустити
                      </Button>
                    )}
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Layers className="w-3.5 h-3.5" />}
                      onClick={(e) => { e.stopPropagation(); navigate(`/view/${book.slug}`); }}
                    >
                      Етапи
                    </Button>
                  </div>

                  <button
                    onClick={(e) => handleDelete(book.slug, e)}
                    title="Видалити"
                    className="p-2 text-slate-400 hover:text-rose-400 rounded-lg hover:bg-slate-800 transition-colors"
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
        <form onSubmit={handleAddBookSubmit} className="space-y-5">
          {/* File Upload Section */}
          <div className="space-y-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
              Завантажити файл (EPUB / PDF / CBZ)
            </label>
            <div className="relative border-2 border-dashed border-slate-700 hover:border-emerald-500/60 rounded-xl p-4 text-center cursor-pointer transition-colors bg-[#090e1c]">
              <input
                type="file"
                accept=".epub,.pdf,.cbz"
                onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                className="absolute inset-0 opacity-0 cursor-pointer"
              />
              <Upload className="w-8 h-8 text-emerald-400 mx-auto mb-2" />
              <p className="text-sm font-semibold text-slate-200">
                {uploadFile ? uploadFile.name : 'Натисніть або перетягніть файл сюди'}
              </p>
              <p className="text-xs text-slate-400 mt-1 font-mono">Підтримуються .epub, .pdf, .cbz (до 1GB)</p>
            </div>
          </div>

          <div className="relative text-center my-2">
            <div className="absolute inset-0 flex items-center"><div className="w-full border-t border-slate-800"></div></div>
            <span className="relative bg-[#131c2e] px-3 text-xs font-mono uppercase text-slate-400">або</span>
          </div>

          {/* Server Path Section */}
          <div className="space-y-2">
            <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
              Шлях до книги на сервері
            </label>
            <div className="relative flex items-center">
              <Folder className="w-4 h-4 absolute left-3.5 text-emerald-400 z-10 pointer-events-none" />
              <input
                type="text"
                value={serverPath}
                onChange={(e) => setServerPath(e.target.value)}
                placeholder="/sdcard/Documents/Books/my_book.epub"
                className="w-full pl-11 pr-4 py-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs font-mono"
              />
            </div>
          </div>

          <div className="flex justify-end gap-3 pt-2">
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
              disabled={!uploadFile && !serverPath}
              icon={<CheckCircle className="w-4 h-4" />}
            >
              Додати
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
};
