import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { ArrowLeft, ChevronLeft, ChevronRight, Edit3, Save, RefreshCw, AlertTriangle, Layers, Eye } from 'lucide-react';

interface BubbleMeta {
  id: string;
  bbox: [number, number, number, number]; // [x, y, w, h] in natural px
  text: string;                           // Original OCR
  translated_text: string;               // Current translation
  quality_flags?: string[];
}

interface MangaPageData {
  page: string;
  image_url: string;
  bubbles: BubbleMeta[];
}

export const MangaEditor: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [pages, setPages] = useState<string[]>([]);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [viewMode, setViewMode] = useState<'translated' | 'cleaned' | 'original'>('translated');

  const [pageData, setPageData] = useState<MangaPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [selectedBubble, setSelectedBubble] = useState<BubbleMeta | null>(null);
  const [editedText, setEditedText] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  // Fetch list of manga pages
  useEffect(() => {
    if (!slug) return;
    const fetchMangaPages = async () => {
      try {
        const res = await apiFetch<{ pages: string[] }>(`/api/preview/manga/${slug}`);
        const pList = res.pages || [];
        setPages(pList);
      } catch (err) {
        console.error('Помилка завантаження сторінок манги:', err);
      }
    };
    fetchMangaPages();
  }, [slug]);

  // Fetch page bubbles metadata for active page
  const currentPageStem = pages[currentPageIndex] || '';

  useEffect(() => {
    if (!slug || !currentPageStem) return;
    const fetchPageBubbles = async () => {
      setLoading(true);
      try {
        const data = await apiFetch<{ bubbles: BubbleMeta[] }>(
          `/api/preview/manga-bubbles/${slug}/${currentPageStem}`
        );
        setPageData({
          page: currentPageStem,
          image_url: `/api/download/${slug}/manga_${viewMode}_${currentPageStem}.png`,
          bubbles: data.bubbles || [],
        });
        setSelectedBubble(null);
      } catch (err) {
        console.error('Помилка завантаження бульбашок манги:', err);
        setPageData({
          page: currentPageStem,
          image_url: `/api/download/${slug}/manga_${viewMode}_${currentPageStem}.png`,
          bubbles: [],
        });
      } finally {
        setLoading(false);
      }
    };
    fetchPageBubbles();
  }, [slug, currentPageStem, viewMode]);

  const handleSelectBubble = (bubble: BubbleMeta) => {
    setSelectedBubble(bubble);
    setEditedText(bubble.translated_text || '');
  };

  const handleSaveBubbleText = async () => {
    if (!slug || !currentPageStem || !selectedBubble) return;
    setSavingEdit(true);
    try {
      await apiFetch(`/api/edit/manga-text/${slug}/${currentPageStem}`, {
        method: 'PUT',
        body: JSON.stringify({
          bubble_id: selectedBubble.id,
          text: editedText,
        }),
      });
      // Update local state
      setPageData((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          bubbles: prev.bubbles.map((b) =>
            b.id === selectedBubble.id ? { ...b, translated_text: editedText } : b
          ),
        };
      });
      setSelectedBubble((prev) => (prev ? { ...prev, translated_text: editedText } : null));
      alert('Текст бульбашки збережено!');
    } catch (err: any) {
      alert(`Помилка збереження: ${err.message}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleRegeneratePage = async () => {
    if (!slug || !currentPageStem) return;
    setRegenerating(true);
    try {
      await apiFetch(`/api/edit/regenerate-manga-page/${slug}/${currentPageStem}`, {
        method: 'POST',
      });
      alert('Сторінку успішно перегенеровано!');
      // Refresh page data
      window.location.reload();
    } catch (err: any) {
      alert(`Помилка перегенерації сторінки: ${err.message}`);
    } finally {
      setRegenerating(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Navigation Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-[#131c2e] p-5 rounded-2xl border border-slate-700/60 shadow-xl">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            icon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate(`/view/${slug}`)}
          >
            Назад до етапів
          </Button>
          <div>
            <h1 className="text-xl font-extrabold text-white flex items-center gap-2">
              <Layers className="w-5 h-5 text-emerald-400" /> Манга-Редактор: <span className="font-mono text-emerald-300">{slug}</span>
            </h1>
            <p className="text-xs text-slate-300 mt-0.5">
              Сторінка {currentPageIndex + 1} з {pages.length || 1} • {currentPageStem}
            </p>
          </div>
        </div>

        {/* View Mode Controls */}
        <div className="flex items-center gap-2 bg-[#090e1c] p-1.5 rounded-xl border border-slate-700/80">
          {(['translated', 'cleaned', 'original'] as const).map((mode) => (
            <button
              key={mode}
              onClick={() => setViewMode(mode)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold uppercase tracking-wider transition-colors ${
                viewMode === mode
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              {mode === 'translated' ? 'Переклад' : mode === 'cleaned' ? 'Очищена' : 'Оригінал'}
            </button>
          ))}
        </div>
      </div>

      {/* Main Workspace Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Manga Canvas Viewer (2 Cols) */}
        <Card className="lg:col-span-2 bg-[#131c2e] border border-slate-700/60 p-4 relative overflow-hidden flex flex-col items-center justify-center min-h-[600px] shadow-xl">
          {/* Pagination Controls */}
          <div className="w-full flex items-center justify-between pb-4 mb-4 border-b border-slate-800">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPageIndex === 0}
              icon={<ChevronLeft className="w-4 h-4" />}
              onClick={() => setCurrentPageIndex((prev) => Math.max(0, prev - 1))}
            >
              Попередня
            </Button>
            <span className="text-xs font-mono text-slate-300 font-bold">
              {currentPageIndex + 1} / {pages.length}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={currentPageIndex >= pages.length - 1}
              icon={<ChevronRight className="w-4 h-4" />}
              onClick={() => setCurrentPageIndex((prev) => Math.min(pages.length - 1, prev + 1))}
            >
              Наступна
            </Button>
          </div>

          {/* Interactive Image Container */}
          {loading ? (
            <div className="flex items-center justify-center h-96 text-emerald-400">
              <div className="w-8 h-8 border-2 border-emerald-400 border-r-transparent rounded-full animate-spin" />
            </div>
          ) : (
            <div className="relative inline-block max-w-full max-h-[75vh] overflow-auto rounded-xl border border-slate-800 bg-black">
              <img
                src={pageData?.image_url}
                alt={`Manga Page ${currentPageStem}`}
                className="max-w-full h-auto block select-none"
              />

              {/* Clickable Overlay Bubbles */}
              {pageData?.bubbles.map((b) => {
                const isSelected = selectedBubble?.id === b.id;
                const hasFlags = b.quality_flags && b.quality_flags.length > 0;
                const [x, y, w, h] = b.bbox;

                return (
                  <div
                    key={b.id}
                    onClick={() => handleSelectBubble(b)}
                    style={{
                      left: `${x}px`,
                      top: `${y}px`,
                      width: `${w}px`,
                      height: `${h}px`,
                    }}
                    className={`absolute border-2 cursor-pointer transition-all ${
                      isSelected
                        ? 'border-emerald-400 bg-emerald-500/30 shadow-lg shadow-emerald-500/50 z-20 scale-105'
                        : hasFlags
                        ? 'border-amber-400 bg-amber-500/20 hover:bg-amber-500/30 z-10'
                        : 'border-cyan-500/50 bg-cyan-500/10 hover:bg-cyan-500/25 z-10'
                    }`}
                    title={b.translated_text || b.text}
                  />
                );
              })}
            </div>
          )}
        </Card>

        {/* Bubble Text Editor Side Panel (1 Col) */}
        <Card className="bg-[#131c2e] border border-slate-700/60 p-6 space-y-5 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <h3 className="font-extrabold text-lg text-white flex items-center gap-2">
              <Edit3 className="w-5 h-5 text-emerald-400" /> Редагування баблу
            </h3>
            {selectedBubble && (
              <Badge variant="emerald">{selectedBubble.id}</Badge>
            )}
          </div>

          {selectedBubble ? (
            <div className="space-y-5">
              {/* Quality Warning if present */}
              {selectedBubble.quality_flags && selectedBubble.quality_flags.length > 0 && (
                <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>Увага: {selectedBubble.quality_flags.join(', ')}</span>
                </div>
              )}

              {/* Original OCR Text */}
              <div className="space-y-1.5">
                <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
                  Оригінальний OCR текст
                </label>
                <div className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs font-mono text-slate-300 select-all">
                  {selectedBubble.text || '(Відсутній)'}
                </div>
              </div>

              {/* Editable Ukrainian Text */}
              <div className="space-y-1.5">
                <label className="block text-xs font-bold uppercase tracking-wider text-emerald-400 font-mono">
                  Переклад (Українська)
                </label>
                <textarea
                  rows={5}
                  value={editedText}
                  onChange={(e) => setEditedText(e.target.value)}
                  className="w-full p-3 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-sm font-medium leading-relaxed"
                />
              </div>

              <div className="flex items-center justify-between gap-3 pt-2">
                <Button
                  variant="primary"
                  size="md"
                  isLoading={savingEdit}
                  icon={<Save className="w-4 h-4" />}
                  onClick={handleSaveBubbleText}
                  className="w-full"
                >
                  Зберегти текст
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 space-y-3">
              <Eye className="w-10 h-10 text-slate-500 mx-auto" />
              <p className="text-sm text-slate-400">
                Оберіть рамку бульбашки на зображенні ліворуч, щоб відредагувати переклад
              </p>
            </div>
          )}

          {/* Regenerate Page Action */}
          <div className="pt-4 border-t border-slate-800">
            <Button
              variant="outline"
              size="md"
              isLoading={regenerating}
              icon={<RefreshCw className="w-4 h-4" />}
              onClick={handleRegeneratePage}
              className="w-full text-xs"
            >
              Перегенерувати сторінку ({currentPageStem})
            </Button>
          </div>
        </Card>
      </div>
    </div>
  );
};
