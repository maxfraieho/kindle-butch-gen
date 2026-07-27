import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import {
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  Edit3,
  Save,
  RefreshCw,
  AlertTriangle,
  Layers,
  Eye,
  Bot,
  Play,
  Square,
  Check,
  X,
  Sliders,
  Sparkles,
  CheckCircle2,
  Minus,
  Plus,
} from 'lucide-react';

interface BubbleMeta {
  id: string;
  bbox: [number, number, number, number]; // [x1, y1, x2, y2]
  text: string;                           // Original OCR
  translated_text: string;               // Current translation
  quality_flags?: string[];
  font_size?: number;
  [key: string]: any;
}

interface MangaPageData {
  page: string;
  image_url: string;
  bubbles: BubbleMeta[];
}

interface AgentEditorStatus {
  running: boolean;
  log?: string[];
  flagged?: number;
  agent_pending?: number;
  llama_running?: boolean;
  ner_running?: boolean;
  case_total?: number | null;
  case_done?: number;
}

interface PendingMangaEdit {
  id: string;
  mode: string;
  target_id: string;
  field?: string;
  original_value?: string;
  edited_value?: string;
  status: string;
  source?: string;
  note?: string;
  created_at?: string;
}

export const MangaEditor: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [pages, setPages] = useState<string[]>([]);
  const [currentPageIndex, setCurrentPageIndex] = useState(0);
  const [jumpPageInput, setJumpPageInput] = useState('1');
  const [viewMode, setViewMode] = useState<'translated' | 'cleaned' | 'original'>('translated');

  const [pageData, setPageData] = useState<MangaPageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [naturalSize, setNaturalSize] = useState<[number, number]>([1000, 1400]);

  // Selected bubble state
  const [selectedBubble, setSelectedBubble] = useState<BubbleMeta | null>(null);
  const [editedText, setEditedText] = useState('');
  const [savingTextEdit, setSavingTextEdit] = useState(false);
  const [regenerating, setRegenerating] = useState(false);

  // Geometry / BBox & Font Size state
  const [bboxX1, setBboxX1] = useState<number>(0);
  const [bboxY1, setBboxY1] = useState<number>(0);
  const [bboxX2, setBboxX2] = useState<number>(0);
  const [bboxY2, setBboxY2] = useState<number>(0);
  const [fontSize, setFontSize] = useState<number>(18);
  const [savingBboxEdit, setSavingBboxEdit] = useState(false);

  // Agent Editor state
  const [agentTabActive, setAgentTabActive] = useState(false);
  const [agentLimit, setAgentLimit] = useState(5);
  const [agentPageStart, setAgentPageStart] = useState<string>('');
  const [agentPageEnd, setAgentPageEnd] = useState<string>('');
  const [agentStatus, setAgentStatus] = useState<AgentEditorStatus | null>(null);
  const [startingScan, setStartingScan] = useState(false);
  const [stoppingScan, setStoppingScan] = useState(false);
  const [agentPendingEdits, setAgentPendingEdits] = useState<PendingMangaEdit[]>([]);
  const [processingEditId, setProcessingEditId] = useState<string | null>(null);

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

  // Update jumpPageInput when currentPageIndex changes
  useEffect(() => {
    setJumpPageInput(String(currentPageIndex + 1));
  }, [currentPageIndex]);

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

  // Agent Status Polling (only when agent section/tab is visible or scan running)
  const fetchAgentStatus = async () => {
    if (!slug) return;
    try {
      const res = await apiFetch<AgentEditorStatus>(`/api/agent-editor/status/${slug}`);
      setAgentStatus(res);
    } catch (err) {
      console.error('Помилка статусу ШІ-Агента:', err);
    }
  };

  const fetchAgentPendingEdits = async () => {
    if (!slug) return;
    try {
      const res = await apiFetch<PendingMangaEdit[] | { queue: PendingMangaEdit[] }>(
        `/api/edit/queue/${slug}?mode=manga&status=pending`
      );
      const queue = Array.isArray(res) ? res : res.queue || [];
      const aiQueue = queue.filter((e) => e.source === 'gemma_agent' || !e.source);
      setAgentPendingEdits(aiQueue);
    } catch (err) {
      console.error('Помилка завантаження пропозицій агента:', err);
    }
  };

  useEffect(() => {
    if (!slug) return;
    fetchAgentStatus();
    fetchAgentPendingEdits();

    const interval = setInterval(() => {
      if (agentTabActive || agentStatus?.running) {
        fetchAgentStatus();
        fetchAgentPendingEdits();
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [slug, agentTabActive, agentStatus?.running]);

  const handleJumpToPage = () => {
    const pageNum = parseInt(jumpPageInput, 10);
    if (!isNaN(pageNum) && pageNum >= 1 && pageNum <= pages.length) {
      setCurrentPageIndex(pageNum - 1);
    }
  };

  const handleSelectBubble = (bubble: BubbleMeta) => {
    setSelectedBubble(bubble);
    setEditedText(bubble.translated_text || '');

    const [x1, y1, x2, y2] = bubble.bbox || [0, 0, 100, 100];
    setBboxX1(x1);
    setBboxY1(y1);
    setBboxX2(x2);
    setBboxY2(y2);
    setFontSize(bubble.font_size || 18);
  };

  const handleSaveBubbleText = async () => {
    if (!slug || !currentPageStem || !selectedBubble) return;
    setSavingTextEdit(true);
    try {
      await apiFetch(`/api/edit/manga-text/${slug}/${currentPageStem}`, {
        method: 'PUT',
        body: JSON.stringify({
          bubble_id: selectedBubble.id,
          translated_text: editedText,
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
      alert(`Помилка збереження тексту: ${err.message}`);
    } finally {
      setSavingTextEdit(false);
    }
  };

  const handleSaveBubbleGeometry = async () => {
    if (!slug || !currentPageStem || !selectedBubble) return;
    setSavingBboxEdit(true);
    try {
      const newBbox: [number, number, number, number] = [
        Number(bboxX1),
        Number(bboxY1),
        Number(bboxX2),
        Number(bboxY2),
      ];

      await apiFetch(`/api/edit/manga-bbox/${slug}/${currentPageStem}`, {
        method: 'PUT',
        body: JSON.stringify({
          bubble_id: selectedBubble.id,
          bbox: newBbox,
          ref_size: naturalSize,
          font_size: Number(fontSize),
        }),
      });

      setPageData((prev) => {
        if (!prev) return null;
        return {
          ...prev,
          bubbles: prev.bubbles.map((b) =>
            b.id === selectedBubble.id ? { ...b, bbox: newBbox, font_size: fontSize } : b
          ),
        };
      });
      setSelectedBubble((prev) =>
        prev ? { ...prev, bbox: newBbox, font_size: fontSize } : null
      );
      alert('Геометрію та шрифт збережено в чергу редагувань!');
    } catch (err: any) {
      alert(`Помилка збереження геометрії/шрифту: ${err.message}`);
    } finally {
      setSavingBboxEdit(false);
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
      window.location.reload();
    } catch (err: any) {
      alert(`Помилка перегенерації сторінки: ${err.message}`);
    } finally {
      setRegenerating(false);
    }
  };

  const handleStartAgentScan = async () => {
    if (!slug) return;
    setStartingScan(true);
    try {
      const body: Record<string, any> = { limit: agentLimit };
      if (agentPageStart) body.page_start = parseInt(agentPageStart, 10);
      if (agentPageEnd) body.page_end = parseInt(agentPageEnd, 10);

      await apiFetch(`/api/agent-editor/scan/${slug}`, {
        method: 'POST',
        body: JSON.stringify(body),
      });

      alert('Скан ШІ-Агента запущено!');
      await fetchAgentStatus();
    } catch (err: any) {
      if (err.status === 403) {
        alert('Розширена можливість: потрібен преміум-доступ. Перевірте /premium у @GetVydraBot.');
      } else if (err.status === 400) {
        alert(`Не вдалося запустити скан: ${err.message || 'Агент-редактор вимкнено у налаштуваннях книги.'}`);
      } else if (err.status === 409 && err.model_missing) {
        alert('Vision-модель агента (Gemma 3 4B) ще не завантажена. Перевірте модалку налаштувань книги.');
      } else {
        alert(`Помилка запуску сканування: ${err.message}`);
      }
    } finally {
      setStartingScan(false);
    }
  };

  const handleStopAgentScan = async () => {
    if (!slug) return;
    setStoppingScan(true);
    try {
      await apiFetch(`/api/agent-editor/stop/${slug}`, { method: 'POST' });
      alert('Скан ШІ-Агента зупинено.');
      await fetchAgentStatus();
    } catch (err: any) {
      alert(`Помилка зупинки сканування: ${err.message}`);
    } finally {
      setStoppingScan(false);
    }
  };

  const handleApproveAgentEdit = async (editId: string) => {
    if (!slug) return;
    setProcessingEditId(editId);
    try {
      await apiFetch(`/api/edit/approve/${slug}/${editId}`, { method: 'POST' });
      await fetchAgentPendingEdits();
      alert('Пропозицію підтверджено!');
    } catch (err: any) {
      alert(`Помилка підтвердження пропозиції: ${err.message}`);
    } finally {
      setProcessingEditId(null);
    }
  };

  const handleDiscardAgentEdit = async (editId: string) => {
    if (!slug) return;
    setProcessingEditId(editId);
    try {
      await apiFetch(`/api/edit/discard/${slug}/${editId}`, { method: 'POST' });
      await fetchAgentPendingEdits();
    } catch (err: any) {
      alert(`Помилка відхилення пропозиції: ${err.message}`);
    } finally {
      setProcessingEditId(null);
    }
  };

  return (
    <div className="space-y-6 pb-12">
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

        {/* Action Modes / View Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setAgentTabActive(!agentTabActive)}
            className={`px-3 py-1.5 rounded-xl text-xs font-semibold flex items-center gap-1.5 border transition-all ${
              agentTabActive
                ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 shadow-lg shadow-amber-500/20'
                : 'bg-[#090e1c] text-slate-300 border-slate-700 hover:border-amber-500/50'
            }`}
          >
            <Bot className="w-4 h-4 text-amber-400" />
            <span>ШІ Агент-Редактор</span>
            {agentStatus?.agent_pending ? (
              <Badge variant="amber" size="sm">
                {agentStatus.agent_pending}
              </Badge>
            ) : null}
          </button>

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
      </div>

      {/* Agent Editor Panel (When Tab Active) */}
      {agentTabActive && (
        <Card className="bg-[#131c2e] border-amber-500/30 p-6 space-y-5 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div className="flex items-center gap-2.5">
              <Sparkles className="w-5 h-5 text-amber-400" />
              <h3 className="font-extrabold text-lg text-white">
                Агент-Редактор (Gemma Vision)
              </h3>
            </div>
            <div className="flex items-center gap-2">
              <Badge variant={agentStatus?.running ? 'emerald' : 'slate'} size="md">
                {agentStatus?.running ? '⚡ Скан працює' : 'Очікує'}
              </Badge>
              <Button
                variant="ghost"
                size="sm"
                icon={<X className="w-4 h-4" />}
                onClick={() => setAgentTabActive(false)}
              >
                Закрити
              </Button>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            {/* Limit Input */}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">
                Кейсів за раз (макс 20):
              </label>
              <input
                type="number"
                min={1}
                max={20}
                value={agentLimit}
                onChange={(e) => setAgentLimit(Math.min(20, Math.max(1, parseInt(e.target.value, 10) || 1)))}
                className="w-full p-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-white font-mono"
              />
            </div>

            {/* Page Start Input */}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">
                З сторінки (опційно):
              </label>
              <input
                type="number"
                min={1}
                value={agentPageStart}
                onChange={(e) => setAgentPageStart(e.target.value)}
                placeholder="1"
                className="w-full p-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-white font-mono"
              />
            </div>

            {/* Page End Input */}
            <div className="space-y-1">
              <label className="text-xs font-semibold text-slate-300">
                По сторінку (опційно):
              </label>
              <input
                type="number"
                min={1}
                value={agentPageEnd}
                onChange={(e) => setAgentPageEnd(e.target.value)}
                placeholder={String(pages.length || '')}
                className="w-full p-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-white font-mono"
              />
            </div>

            {/* Scan Control Buttons */}
            <div className="flex items-end gap-2">
              {agentStatus?.running ? (
                <Button
                  variant="outline"
                  size="md"
                  icon={<Square className="w-4 h-4 text-red-400" />}
                  isLoading={stoppingScan}
                  onClick={handleStopAgentScan}
                  className="w-full text-red-400 border-red-500/40 hover:bg-red-500/10"
                >
                  Зупинити
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="md"
                  icon={<Play className="w-4 h-4" />}
                  isLoading={startingScan}
                  onClick={handleStartAgentScan}
                  className="w-full"
                >
                  Запустити скан
                </Button>
              )}
            </div>
          </div>

          {/* Progress and Counters */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-2">
            <div className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs">
              <span className="text-slate-400 block">Проблемних (Flagged):</span>
              <span className="text-lg font-bold text-amber-300 font-mono">
                {agentStatus?.flagged ?? 0}
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs">
              <span className="text-slate-400 block">Пропозицій у черзі:</span>
              <span className="text-lg font-bold text-emerald-300 font-mono">
                {agentStatus?.agent_pending ?? agentPendingEdits.length}
              </span>
            </div>
            <div className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs col-span-2">
              <span className="text-slate-400 block">Прогрес покадрового скану:</span>
              <span className="text-sm font-bold text-slate-200 font-mono">
                {agentStatus?.case_done ?? 0} / {agentStatus?.case_total ?? 'N/A'} оброблено
              </span>
            </div>
          </div>

          {/* Status Log Box */}
          {agentStatus?.log && agentStatus.log.length > 0 && (
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider font-mono">
                Лог роботи Агента:
              </label>
              <pre className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs font-mono text-emerald-400 max-h-36 overflow-y-auto leading-relaxed whitespace-pre-wrap">
                {agentStatus.log.join('\n')}
              </pre>
            </div>
          )}

          {/* AI Pending Suggestions Queue */}
          {agentPendingEdits.length > 0 && (
            <div className="space-y-3 pt-2 border-t border-slate-800">
              <h4 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                Пропозиції Агента, що очікують підтвердження ({agentPendingEdits.length})
              </h4>
              <div className="space-y-2.5 max-h-60 overflow-y-auto pr-1">
                {agentPendingEdits.map((edit) => (
                  <div
                    key={edit.id}
                    className="p-3.5 rounded-xl bg-[#090e1c] border border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs"
                  >
                    <div className="space-y-1 min-w-0">
                      <div className="font-mono text-slate-400 text-[10px]">
                        Target: {edit.target_id} | Джерело: {edit.source || 'gemma_agent'}
                      </div>
                      <div className="text-slate-400">
                        <span className="text-slate-500">Було:</span> {edit.original_value}
                      </div>
                      <div className="text-emerald-300 font-semibold">
                        <span className="text-slate-500">Пропозиція ШІ:</span> {edit.edited_value}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="outline"
                        size="sm"
                        icon={<X className="w-3.5 h-3.5 text-red-400" />}
                        isLoading={processingEditId === edit.id}
                        onClick={() => handleDiscardAgentEdit(edit.id)}
                      >
                        Відхилити
                      </Button>
                      <Button
                        variant="primary"
                        size="sm"
                        icon={<Check className="w-3.5 h-3.5" />}
                        isLoading={processingEditId === edit.id}
                        onClick={() => handleApproveAgentEdit(edit.id)}
                      >
                        Підтвердити
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Main Workspace Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 items-start">
        {/* Manga Canvas Viewer (2 Cols) */}
        <Card className="lg:col-span-2 bg-[#131c2e] border border-slate-700/60 p-4 relative overflow-hidden flex flex-col items-center justify-center min-h-[600px] shadow-xl">
          {/* Pagination Controls + Jump-to-page */}
          <div className="w-full flex flex-wrap items-center justify-between gap-3 pb-4 mb-4 border-b border-slate-800">
            <Button
              variant="outline"
              size="sm"
              disabled={currentPageIndex === 0}
              icon={<ChevronLeft className="w-4 h-4" />}
              onClick={() => setCurrentPageIndex((prev) => Math.max(0, prev - 1))}
            >
              Попередня
            </Button>

            {/* Jump To Page Inline Controls */}
            <div className="flex items-center gap-2">
              <span className="text-xs font-mono text-slate-300 font-bold hidden sm:inline">
                Сторінка:
              </span>
              <input
                type="number"
                min={1}
                max={pages.length || 1}
                value={jumpPageInput}
                onChange={(e) => setJumpPageInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleJumpToPage();
                }}
                className="w-16 p-1.5 rounded-lg bg-[#090e1c] border border-slate-700 text-xs text-center text-white focus:outline-none focus:border-emerald-500 font-mono"
              />
              <span className="text-xs font-mono text-slate-400">
                / {pages.length}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleJumpToPage}
                className="text-xs"
              >
                Go
              </Button>
            </div>

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
                onLoad={(e) => {
                  const img = e.currentTarget;
                  if (img.naturalWidth && img.naturalHeight) {
                    setNaturalSize([img.naturalWidth, img.naturalHeight]);
                  }
                }}
                className="max-w-full h-auto block select-none"
              />

              {/* Clickable Overlay Bubbles */}
              {pageData?.bubbles.map((b) => {
                const isSelected = selectedBubble?.id === b.id;
                const hasFlags = b.quality_flags && b.quality_flags.length > 0;
                const [rawX1, rawY1, rawX2, rawY2] = b.bbox;

                // Support both [x1,y1,x2,y2] and [x,y,w,h]
                const isTwoPoint = rawX2 > rawX1 && rawY2 > rawY1;
                const x = rawX1;
                const y = rawY1;
                const w = isTwoPoint ? rawX2 - rawX1 : rawX2;
                const h = isTwoPoint ? rawY2 - rawY1 : rawY2;

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
                        ? 'border-emerald-400 bg-emerald-500/30 shadow-lg shadow-emerald-500/50 z-20 scale-[1.02]'
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

        {/* Bubble Text & BBox / Font Size Editor Side Panel (1 Col) */}
        <Card className="bg-[#131c2e] border border-slate-700/60 p-6 space-y-6 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <h3 className="font-extrabold text-lg text-white flex items-center gap-2">
              <Edit3 className="w-5 h-5 text-emerald-400" /> Параметри баблу
            </h3>
            {selectedBubble && (
              <Badge variant="emerald">{selectedBubble.id}</Badge>
            )}
          </div>

          {selectedBubble ? (
            <div className="space-y-6">
              {/* Quality Warning if present */}
              {selectedBubble.quality_flags && selectedBubble.quality_flags.length > 0 && (
                <div className="p-3 rounded-xl bg-amber-500/15 border border-amber-500/30 text-amber-300 text-xs flex items-center gap-2">
                  <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                  <span>Увага: {selectedBubble.quality_flags.join(', ')}</span>
                </div>
              )}

              {/* SECTION A: Text Editing */}
              <div className="space-y-4 pb-4 border-b border-slate-800">
                <div className="space-y-1.5">
                  <label className="block text-xs font-bold uppercase tracking-wider text-slate-400 font-mono">
                    Оригінальний OCR текст
                  </label>
                  <div className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs font-mono text-slate-300 select-all">
                    {selectedBubble.text || '(Відсутній)'}
                  </div>
                </div>

                <div className="space-y-1.5">
                  <label className="block text-xs font-bold uppercase tracking-wider text-emerald-400 font-mono">
                    Переклад (Українська)
                  </label>
                  <textarea
                    rows={4}
                    value={editedText}
                    onChange={(e) => setEditedText(e.target.value)}
                    className="w-full p-3 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-sm font-medium leading-relaxed"
                  />
                </div>

                <Button
                  variant="primary"
                  size="md"
                  isLoading={savingTextEdit}
                  icon={<Save className="w-4 h-4" />}
                  onClick={handleSaveBubbleText}
                  className="w-full"
                >
                  Зберегти текст
                </Button>
              </div>

              {/* SECTION B: BBox & Font Size Manual Overrides (TASK-36) */}
              <div className="space-y-4">
                <div className="flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-cyan-400 font-mono">
                  <Sliders className="w-4 h-4 text-cyan-400" />
                  <span>Геометрія рамок (bbox) та шрифт</span>
                </div>

                {/* Font Size Adjust Controls */}
                <div className="space-y-1.5">
                  <label className="block text-xs text-slate-300">
                    Розмір шрифту (font_size: 8-200):
                  </label>
                  <div className="flex items-center gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Minus className="w-3.5 h-3.5" />}
                      onClick={() => setFontSize((prev) => Math.max(8, prev - 2))}
                    >
                      -2
                    </Button>
                    <input
                      type="number"
                      min={8}
                      max={200}
                      value={fontSize}
                      onChange={(e) => setFontSize(parseInt(e.target.value, 10) || 18)}
                      className="w-full p-2 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-center text-emerald-300 font-mono font-bold"
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      icon={<Plus className="w-3.5 h-3.5" />}
                      onClick={() => setFontSize((prev) => Math.min(200, prev + 2))}
                    >
                      +2
                    </Button>
                  </div>
                </div>

                {/* BBox 4-point Inputs */}
                <div className="space-y-1.5">
                  <label className="block text-xs text-slate-300">
                    Координати рамки [x1, y1, x2, y2]:
                  </label>
                  <div className="grid grid-cols-2 gap-2 text-xs">
                    <div>
                      <span className="text-[10px] text-slate-500 font-mono">X1:</span>
                      <input
                        type="number"
                        value={bboxX1}
                        onChange={(e) => setBboxX1(parseInt(e.target.value, 10) || 0)}
                        className="w-full p-2 rounded-lg bg-[#090e1c] border border-slate-700 text-white font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-mono">Y1:</span>
                      <input
                        type="number"
                        value={bboxY1}
                        onChange={(e) => setBboxY1(parseInt(e.target.value, 10) || 0)}
                        className="w-full p-2 rounded-lg bg-[#090e1c] border border-slate-700 text-white font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-mono">X2:</span>
                      <input
                        type="number"
                        value={bboxX2}
                        onChange={(e) => setBboxX2(parseInt(e.target.value, 10) || 0)}
                        className="w-full p-2 rounded-lg bg-[#090e1c] border border-slate-700 text-white font-mono"
                      />
                    </div>
                    <div>
                      <span className="text-[10px] text-slate-500 font-mono">Y2:</span>
                      <input
                        type="number"
                        value={bboxY2}
                        onChange={(e) => setBboxY2(parseInt(e.target.value, 10) || 0)}
                        className="w-full p-2 rounded-lg bg-[#090e1c] border border-slate-700 text-white font-mono"
                      />
                    </div>
                  </div>
                </div>

                <Button
                  variant="outline"
                  size="md"
                  isLoading={savingBboxEdit}
                  icon={<Sliders className="w-4 h-4 text-cyan-400" />}
                  onClick={handleSaveBubbleGeometry}
                  className="w-full border-cyan-500/40 text-cyan-300 hover:bg-cyan-500/10"
                >
                  Зберегти геометрію / шрифт
                </Button>
              </div>
            </div>
          ) : (
            <div className="text-center py-12 space-y-3">
              <Eye className="w-10 h-10 text-slate-500 mx-auto" />
              <p className="text-sm text-slate-400">
                Оберіть рамку бульбашки на зображенні ліворуч, щоб відредагувати текст або розмір шрифту та рамки
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
