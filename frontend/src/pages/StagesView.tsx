import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { ArrowLeft, Play, Pause, Volume2, FileText, CheckCircle2, RotateCw } from 'lucide-react';

interface StageData {
  paragraphs?: Array<{ hash: string; original: string; translated: string }>;
  total_pages?: number;
  total_chunks?: number;
}

export const StagesView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<StageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'translated' | 'original'>('translated');
  const [playingHash, setPlayingHash] = useState<string | null>(null);
  const [audio, setAudio] = useState<HTMLAudioElement | null>(null);

  useEffect(() => {
    if (!slug) return;
    apiFetch<StageData>(`/api/preview/book/${slug}`)
      .then(setData)
      .catch((err) => console.error('Помилка прев\'ю книги:', err))
      .finally(() => setLoading(false));
  }, [slug]);

  const handlePlayAudio = (hash: string) => {
    if (playingHash === hash && audio) {
      audio.pause();
      setPlayingHash(null);
      return;
    }

    if (audio) {
      audio.pause();
    }

    const newAudio = new Audio(`/api/preview/audio/${slug}/${hash}`);
    newAudio.onended = () => setPlayingHash(null);
    newAudio.onerror = () => {
      alert('Помилка завантаження аудіозапису');
      setPlayingHash(null);
    };
    newAudio.play();
    setAudio(newAudio);
    setPlayingHash(hash);
  };

  return (
    <div className="space-y-6">
      {/* Top Action Bar */}
      <div className="flex items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            size="sm"
            icon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate('/')}
          >
            Назад
          </Button>
          <div>
            <h1 className="text-xl md:text-2xl font-bold text-slate-100 truncate">
              {slug}
            </h1>
            <p className="text-xs text-slate-400 font-mono">
              Етапи перекладу та озвучення
            </p>
          </div>
        </div>

        {/* View Toggle */}
        <div className="glass-panel p-1 rounded-xl flex items-center gap-1 border border-slate-800">
          <button
            onClick={() => setActiveTab('translated')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all active-scale ${
              activeTab === 'translated'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Українська
          </button>
          <button
            onClick={() => setActiveTab('original')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all active-scale ${
              activeTab === 'original'
                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Оригінал
          </button>
        </div>
      </div>

      {/* Main Preview Content */}
      {loading ? (
        <div className="space-y-4">
          {[1, 2, 3, 4].map((i) => (
            <Card key={i} className="h-24 p-5 animate-pulse bg-slate-900/40" />
          ))}
        </div>
      ) : !data?.paragraphs || data.paragraphs.length === 0 ? (
        <Card className="text-center py-12 px-4">
          <FileText className="w-10 h-10 text-slate-500 mx-auto mb-3" />
          <p className="text-sm text-slate-400">Текстові абзаци ще не вилучені або розпарсені</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {data.paragraphs.map((p, idx) => (
            <Card key={p.hash || idx} className="p-4 space-y-3 hover:border-slate-700/60 transition-colors">
              <div className="flex items-center justify-between gap-2 text-xs font-mono text-slate-400 border-b border-slate-800/50 pb-2">
                <span className="tabular-nums font-semibold text-emerald-400">#{idx + 1}</span>
                <div className="flex items-center gap-2">
                  <Badge variant="emerald" size="sm">
                    <CheckCircle2 className="w-3 h-3" /> Озвучено Supertonic 3
                  </Badge>
                  <Button
                    variant="ghost"
                    size="sm"
                    icon={playingHash === p.hash ? <Pause className="w-3.5 h-3.5 text-amber-400" /> : <Play className="w-3.5 h-3.5 text-emerald-400" />}
                    onClick={() => handlePlayAudio(p.hash)}
                  >
                    {playingHash === p.hash ? 'Пауза' : 'Синтез'}
                  </Button>
                </div>
              </div>

              <p className="text-sm md:text-base leading-relaxed text-slate-200 font-sans">
                {activeTab === 'translated' ? p.translated : p.original}
              </p>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
