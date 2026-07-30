import React, { useState, useEffect } from 'react';
import { Modal } from './Modal';
import { Badge } from './Badge';
import { Button } from './Button';
import { apiFetch } from '../../api/client';
import {
  Upload,
  Users,
  Languages,
  ShieldCheck,
  BookOpen,
  Type,
  Volume2,
  Mic,
  Headphones,
  Lock,
  CheckCircle2,
  Play,
  Loader2,
  ChevronDown,
  ChevronUp,
  Sparkles,
} from 'lucide-react';

interface StageInfo {
  id: string;
  name: string;
  tier: 'standard' | 'premium';
  status: 'completed' | 'active' | 'pending' | 'skipped' | 'locked';
  icon: string;
  description: string;
}

interface ProtocolData {
  stages: StageInfo[];
  current_stage: string | null;
  mode: string;
  overall_progress: number;
  book_title: string;
  book_slug: string;
}

interface ProtocolModalProps {
  slug: string;
  bookTitle?: string;
  isOpen: boolean;
  onClose: () => void;
  onRunStage?: (stageId: string) => Promise<void> | void;
}

const ICON_MAP: Record<string, React.ReactNode> = {
  upload: <Upload className="w-4 h-4" />,
  users: <Users className="w-4 h-4" />,
  languages: <Languages className="w-4 h-4" />,
  'shield-check': <ShieldCheck className="w-4 h-4" />,
  'book-open': <BookOpen className="w-4 h-4" />,
  type: <Type className="w-4 h-4" />,
  'volume-2': <Volume2 className="w-4 h-4" />,
  mic: <Mic className="w-4 h-4" />,
  headphones: <Headphones className="w-4 h-4" />,
};

const STATUS_STYLES: Record<string, { bg: string; border: string; text: string; iconColor: string; line: string }> = {
  completed: {
    bg: 'bg-emerald-950/40',
    border: 'border-emerald-500/50',
    text: 'text-emerald-300',
    iconColor: 'text-emerald-400',
    line: 'bg-emerald-500/60',
  },
  active: {
    bg: 'bg-cyan-950/40',
    border: 'border-cyan-500/50',
    text: 'text-cyan-300',
    iconColor: 'text-cyan-400',
    line: 'bg-cyan-500/60',
  },
  pending: {
    bg: 'bg-slate-900/60',
    border: 'border-slate-700/50',
    text: 'text-slate-400',
    iconColor: 'text-slate-500',
    line: 'bg-slate-700/40',
  },
  skipped: {
    bg: 'bg-slate-900/30',
    border: 'border-slate-800/40',
    text: 'text-slate-500',
    iconColor: 'text-slate-600',
    line: 'bg-slate-800/30',
  },
  locked: {
    bg: 'bg-amber-950/20',
    border: 'border-amber-500/30',
    text: 'text-amber-400/60',
    iconColor: 'text-amber-500/50',
    line: 'bg-amber-500/20',
  },
};

const STATUS_LABELS: Record<string, string> = {
  completed: 'Виконано',
  active: 'Активний процес',
  pending: 'Очікує запуску',
  skipped: 'Пропущено (Стандарт)',
  locked: 'Преміум режим',
};

export const ProtocolModal: React.FC<ProtocolModalProps> = ({
  slug,
  bookTitle,
  isOpen,
  onClose,
  onRunStage,
}) => {
  const [data, setData] = useState<ProtocolData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expandedStage, setExpandedStage] = useState<string | null>(null);
  const [runningStageId, setRunningStageId] = useState<string | null>(null);

  const fetchProtocol = async () => {
    if (!slug) return;
    try {
      const res = await apiFetch<ProtocolData>(`/api/books/${slug}/protocol`);
      setData(res);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Помилка завантаження протоколу');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && slug) {
      fetchProtocol();
      const interval = setInterval(fetchProtocol, 3000);
      return () => clearInterval(interval);
    }
  }, [isOpen, slug]);

  const handleTriggerStage = async (stageId: string, e?: React.MouseEvent) => {
    if (e) e.stopPropagation();
    if (!onRunStage) return;

    setRunningStageId(stageId);
    try {
      await onRunStage(stageId);
      await fetchProtocol();
    } catch (err: any) {
      setError(`Помилка запуску етапу: ${err.message}`);
    } finally {
      setRunningStageId(null);
    }
  };

  const completedCount = data?.stages.filter((s) => s.status === 'completed').length || 0;
  const totalStages = data?.stages.length || 9;

  const currentNextStage = data?.stages.find(
    (s) => (s.status === 'pending' || s.status === 'active') && s.tier === 'standard'
  );

  return (
    <Modal isOpen={isOpen} onClose={onClose} title="">
      <div className="space-y-4 -mt-2">
        {/* Header */}
        <div className="flex items-center justify-between gap-2 border-b border-slate-800 pb-3">
          <div className="space-y-0.5 min-w-0 flex-1">
            <h2 className="text-sm sm:text-base font-bold text-white flex items-center gap-1.5 min-w-0">
              <Sparkles className="w-4 h-4 text-cyan-400 shrink-0" />
              <span className="truncate">Протокол обробки</span>
            </h2>
            <p className="text-[11px] text-slate-400 truncate font-mono">
              {bookTitle || slug}
            </p>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <Badge variant={data?.mode === 'premium' ? 'amber' : 'slate'} size="sm">
              {data?.mode === 'premium' ? '⭐ PRO' : '📦 Стандарт'}
            </Badge>
            <Badge variant="emerald" size="sm">
              {completedCount}/{totalStages}
            </Badge>
          </div>
        </div>

        {/* Overall Progress Bar */}
        <div className="space-y-1">
          <div className="h-1.5 rounded-full bg-slate-800 overflow-hidden">
            <div
              className="h-full rounded-full bg-gradient-to-r from-emerald-500 to-cyan-400 transition-all duration-500"
              style={{ width: `${data?.overall_progress || 0}%` }}
            />
          </div>
          <div className="flex justify-between items-center text-[10px] text-slate-400">
            <span>
              Поточний етап: <strong className="text-cyan-300">{data?.current_stage || 'Очікування'}</strong>
            </span>
            <span>{Math.round(data?.overall_progress || 0)}% завершено</span>
          </div>
        </div>

        {/* Global Action Banner for Next Stage */}
        {currentNextStage && (
          <div className="p-3 rounded-xl bg-cyan-950/30 border border-cyan-500/40 flex items-center justify-between gap-3">
            <div className="space-y-0.5 min-w-0">
              <span className="text-[10px] uppercase font-bold text-cyan-400 tracking-wider block">
                Актуальний наступний крок
              </span>
              <p className="text-xs font-semibold text-white truncate">
                {currentNextStage.name}
              </p>
            </div>
            <Button
              variant="primary"
              size="sm"
              isLoading={runningStageId === currentNextStage.id}
              icon={<Play className="w-3.5 h-3.5 fill-current" />}
              onClick={(e) => handleTriggerStage(currentNextStage.id, e)}
              className="text-xs shrink-0 bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold"
            >
              Запустити
            </Button>
          </div>
        )}

        {/* Loading / Error states */}
        {loading && !data && (
          <div className="py-8 text-center">
            <Loader2 className="w-6 h-6 text-cyan-400 animate-spin mx-auto mb-2" />
            <p className="text-xs text-slate-400">Завантаження протоколу...</p>
          </div>
        )}
        {error && (
          <div className="p-3 rounded-xl bg-rose-950/30 border border-rose-500/30 text-xs text-rose-300 flex items-center justify-between">
            <span>⚠️ {error}</span>
            <button
              onClick={fetchProtocol}
              className="text-xs underline text-rose-300 hover:text-white"
            >
              Повторити
            </button>
          </div>
        )}

        {/* Stage Timeline */}
        {data && (
          <div className="space-y-1.5 max-h-[55vh] overflow-y-auto pr-1">
            {data.stages.map((stage, idx) => {
              const styles = STATUS_STYLES[stage.status] || STATUS_STYLES.pending;
              const isExpanded = expandedStage === stage.id;
              const isLast = idx === data.stages.length - 1;
              const isExecutingThis = runningStageId === stage.id;

              return (
                <div key={stage.id} className="relative">
                  {/* Connector line */}
                  {!isLast && (
                    <div
                      className={`absolute left-[19px] top-[40px] w-0.5 ${styles.line}`}
                      style={{ height: isExpanded ? 'calc(100% - 20px)' : '16px' }}
                    />
                  )}

                  {/* Stage Row Container */}
                  <div className={`w-full flex items-center justify-between gap-2 p-2.5 rounded-xl transition-all ${styles.bg} border ${styles.border} text-left`}>
                    {/* Clickable Title & Icon Area */}
                    <div
                      onClick={() => setExpandedStage(isExpanded ? null : stage.id)}
                      className="flex items-center gap-2.5 flex-1 min-w-0 cursor-pointer"
                    >
                      <div className={`w-[36px] h-[36px] sm:w-[38px] sm:h-[38px] rounded-full flex items-center justify-center shrink-0 border ${styles.border} ${styles.bg}`}>
                        {stage.status === 'completed' ? (
                          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                        ) : stage.status === 'active' || isExecutingThis ? (
                          <Loader2 className="w-4 h-4 text-cyan-400 animate-spin" />
                        ) : stage.status === 'locked' ? (
                          <Lock className="w-3.5 h-3.5 text-amber-500/60" />
                        ) : (
                          <span className={`text-xs font-bold ${styles.text}`}>{idx + 1}</span>
                        )}
                      </div>

                      <div className="flex-1 min-w-0 pr-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span className={`text-xs sm:text-sm font-semibold leading-tight ${stage.status === 'completed' ? 'text-emerald-300' : stage.status === 'active' ? 'text-cyan-200' : 'text-slate-300'}`}>
                            {stage.name}
                          </span>
                          {stage.tier === 'premium' && (
                            <span className="text-[9px] px-1.5 py-0.5 rounded-md bg-amber-500/20 text-amber-400 font-bold uppercase tracking-wider">PRO</span>
                          )}
                        </div>
                        <p className={`text-[10px] mt-0.5 ${styles.text}`}>
                          {STATUS_LABELS[stage.status]}
                        </p>
                      </div>
                    </div>

                    {/* Action Button & Expand Chevron */}
                    <div className="flex items-center gap-1.5 shrink-0">
                      {stage.tier === 'standard' && stage.status !== 'active' && onRunStage && (
                        <Button
                          variant="ghost"
                          size="sm"
                          isLoading={isExecutingThis}
                          icon={<Play className="w-3 h-3 text-cyan-400 fill-current" />}
                          onClick={(e) => handleTriggerStage(stage.id, e)}
                          title="Запустити цей етап"
                          className="px-2 py-1 h-7 text-[10px] sm:text-[11px] text-cyan-300 hover:bg-cyan-950/60 border border-cyan-500/30 whitespace-nowrap shrink-0 font-bold"
                        >
                          {stage.status === 'completed' ? 'Перезапустити' : 'Запустити'}
                        </Button>
                      )}
                      <button
                        onClick={() => setExpandedStage(isExpanded ? null : stage.id)}
                        className="p-1 hover:bg-slate-800/50 rounded-lg text-slate-400 transition-colors shrink-0"
                      >
                        {isExpanded ? (
                          <ChevronUp className="w-4 h-4 text-slate-400" />
                        ) : (
                          <ChevronDown className="w-4 h-4 text-slate-400" />
                        )}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className={`ml-[19px] pl-6 pb-2 border-l-2 ${styles.line} mt-1 mb-1`}>
                      <div className={`p-3 rounded-xl ${styles.bg} border ${styles.border} space-y-2.5`}>
                        <p className="text-xs text-slate-300 leading-relaxed">
                          {stage.description}
                        </p>

                        {stage.tier === 'standard' && onRunStage && (
                          <div className="pt-1 flex items-center gap-2">
                            <Button
                              variant="primary"
                              size="sm"
                              isLoading={isExecutingThis}
                              icon={<Play className="w-3 h-3 fill-current" />}
                              onClick={(e) => handleTriggerStage(stage.id, e)}
                              className="text-xs bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold"
                            >
                              {stage.status === 'completed' ? 'Перезапустити етап' : 'Запустити етап'}
                            </Button>
                          </div>
                        )}

                        {stage.status === 'locked' && (
                          <div className="flex items-center gap-2 text-[10px] text-amber-400/80 pt-1">
                            <Lock className="w-3 h-3" />
                            <span>Доступно лише в преміум-режимі через @GetVydraBot</span>
                          </div>
                        )}

                        {stage.status === 'active' && (
                          <div className="flex items-center gap-2 text-[10px] text-cyan-400 pt-1">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            <span>Цей етап зараз активно виконується...</span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </Modal>
  );
};
