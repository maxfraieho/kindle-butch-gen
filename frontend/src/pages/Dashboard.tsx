import React, { useState, useEffect } from 'react';
import { apiFetch, Book } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { ProgressBar } from '../components/ui/ProgressBar';
import { Badge } from '../components/ui/Badge';
import { BookOpen, Plus, Play, Square, Download, Trash2, RefreshCw, Layers } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

export const Dashboard: React.FC = () => {
  const [books, setBooks] = useState<Book[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
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
    const interval = setInterval(fetchBooks, 4000); // Polling status every 4s
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

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-100 tracking-tight">
            Бібліотека книг
          </h1>
          <p className="text-sm text-slate-400 mt-1">
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
            onClick={() => alert('Форма додавання книги у наступному розширенні')}
          >
            Додати книгу
          </Button>
        </div>
      </div>

      {/* Book Grid */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="h-48 animate-pulse bg-slate-900/40" />
          ))}
        </div>
      ) : books.length === 0 ? (
        <Card className="text-center py-12 px-4 space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-emerald-500/10 text-emerald-400 flex items-center justify-center mx-auto">
            <BookOpen className="w-6 h-6" />
          </div>
          <div>
            <h3 className="text-lg font-bold text-slate-200">Немає доданих книг</h3>
            <p className="text-sm text-slate-400 mt-1 max-w-sm mx-auto">
              Завантажте PDF або EPUB файл, щоб розпочати автоматичний переклад та синтез аудіо
            </p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {books.map((book) => {
            const isRunning = book.status === 'running' || book.status === 'in_progress';
            const isCompleted = book.status === 'completed' || book.progress === 100;

            return (
              <Card
                key={book.slug}
                hoverable
                onClick={() => navigate(`/view/${book.slug}`)}
                className="flex flex-col justify-between space-y-4 group"
              >
                {/* Header info */}
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-bold text-lg text-slate-100 group-hover:text-emerald-400 transition-colors line-clamp-1">
                      {book.title || book.slug}
                    </h3>
                    <Badge variant={isRunning ? 'emerald' : isCompleted ? 'amber' : 'slate'}>
                      {isRunning ? 'Обробка' : isCompleted ? 'Готово' : 'Очікує'}
                    </Badge>
                  </div>
                  {book.authors && (
                    <p className="text-xs text-slate-400 truncate font-medium">
                      {book.authors}
                    </p>
                  )}
                </div>

                {/* Progress section */}
                <div className="space-y-2 pt-2 border-t border-slate-800/60">
                  <ProgressBar
                    progress={book.progress || 0}
                    statusText={book.current_stage || 'Готовий до запуску'}
                  />
                </div>

                {/* Actions Footer */}
                <div className="flex items-center justify-between pt-2 border-t border-slate-800/40">
                  <div className="flex items-center gap-1.5">
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
                    className="p-2 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-slate-800/60 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
};
