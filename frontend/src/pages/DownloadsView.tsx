import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Download, Search, FileText, Music, BookOpen, Trash2, Filter } from 'lucide-react';

interface DownloadItem {
  slug: string;
  book_title?: string;
  filename: string;
  size?: string;
  target?: string;
  description?: string;
  download_url: string;
}

export const DownloadsView: React.FC = () => {
  const [items, setItems] = useState<DownloadItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [formatFilter, setFormatFilter] = useState<'all' | 'epub' | 'azw3' | 'mp3' | 'cbz' | 'md'>('all');

  const fetchDownloads = async () => {
    try {
      const data = await apiFetch<DownloadItem[]>('/api/downloads');
      setItems(Array.isArray(data) ? data : []);
    } catch (err) {
      console.error('Помилка завантаження архіву:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDownloads();
  }, []);

  const handleDeleteFile = async (slug: string, filename: string) => {
    if (!confirm(`Вилучити файл "${filename}"?`)) return;
    try {
      await apiFetch(`/api/delete-file/${slug}/${filename}`, { method: 'DELETE' });
      fetchDownloads();
    } catch (err: any) {
      alert(`Помилка вилучення: ${err.message}`);
    }
  };

  const getFormatBadge = (filename: string) => {
    const ext = filename.split('.').pop()?.toLowerCase();
    switch (ext) {
      case 'epub': return <Badge variant="emerald"><BookOpen className="w-3 h-3" /> EPUB</Badge>;
      case 'azw3': return <Badge variant="cyan"><BookOpen className="w-3 h-3" /> AZW3</Badge>;
      case 'mp3': return <Badge variant="amber"><Music className="w-3 h-3" /> MP3 Audio</Badge>;
      case 'cbz': return <Badge variant="emerald"><FileText className="w-3 h-3" /> CBZ Manga</Badge>;
      default: return <Badge variant="slate"><FileText className="w-3 h-3" /> {ext?.toUpperCase()}</Badge>;
    }
  };

  const filteredItems = items.filter((item) => {
    const matchesSearch =
      item.filename.toLowerCase().includes(search.toLowerCase()) ||
      (item.book_title && item.book_title.toLowerCase().includes(search.toLowerCase())) ||
      item.slug.toLowerCase().includes(search.toLowerCase());

    if (!matchesSearch) return false;

    if (formatFilter === 'all') return true;
    return item.filename.toLowerCase().endsWith(`.${formatFilter}`);
  });

  return (
    <div className="space-y-6">
      {/* Title & Filter Controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-slate-100 tracking-tight">
            Архів завантажень
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Готові книжкові формати (EPUB, AZW3, CBZ) та аудіокниги (MP3)
          </p>
        </div>

        {/* Search & Filter */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 sm:w-64">
            <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Пошук файлу або книги..."
              className="w-full pl-10 pr-4 py-2.5 rounded-xl bg-slate-950/80 border border-slate-800 text-slate-100 placeholder-slate-500 focus:outline-none focus:border-emerald-500/60 text-xs"
            />
          </div>

          <div className="glass-panel p-1 rounded-xl flex items-center gap-1 border border-slate-800">
            {(['all', 'epub', 'azw3', 'mp3', 'cbz'] as const).map((fmt) => (
              <button
                key={fmt}
                onClick={() => setFormatFilter(fmt)}
                className={`px-2.5 py-1.5 rounded-lg text-xs font-mono uppercase transition-all active-scale ${
                  formatFilter === fmt
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 font-semibold'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {fmt}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Downloads List */}
      {loading ? (
        <div className="space-y-3">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} className="h-20 animate-pulse bg-slate-900/40" />
          ))}
        </div>
      ) : filteredItems.length === 0 ? (
        <Card className="text-center py-12">
          <Download className="w-10 h-10 text-slate-500 mx-auto mb-3" />
          <p className="text-sm text-slate-400">Файлів не знайдено</p>
        </Card>
      ) : (
        <div className="space-y-3">
          {filteredItems.map((item, idx) => (
            <Card
              key={`${item.slug}-${item.filename}-${idx}`}
              className="p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:border-slate-700/60 transition-colors"
            >
              <div className="space-y-1.5 min-w-0 flex-1">
                <div className="flex items-center gap-2.5 flex-wrap">
                  {getFormatBadge(item.filename)}
                  <h3 className="font-semibold text-slate-100 truncate text-sm">
                    {item.filename}
                  </h3>
                  {item.size && (
                    <span className="text-xs text-slate-400 font-mono tabular-nums">
                      ({item.size})
                    </span>
                  )}
                </div>
                {item.description && (
                  <p className="text-xs text-slate-400 truncate">
                    {item.description}
                  </p>
                )}
              </div>

              <div className="flex items-center gap-2 flex-shrink-0 self-end sm:self-center">
                <a
                  href={item.download_url}
                  download={item.filename}
                  className="no-underline"
                >
                  <Button variant="primary" size="sm" icon={<Download className="w-3.5 h-3.5" />}>
                    Завантажити
                  </Button>
                </a>
                <button
                  onClick={() => handleDeleteFile(item.slug, item.filename)}
                  title="Вилучити файл"
                  className="p-2 text-slate-500 hover:text-rose-400 rounded-lg hover:bg-slate-800/60 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
