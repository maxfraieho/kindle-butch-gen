import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import {
  ArrowLeft,
  Play,
  Pause,
  FileText,
  CheckCircle2,
  Edit3,
  Save,
  X,
  RotateCw,
  AlertTriangle,
  ShieldAlert,
  Check,
  Trash2,
  VolumeX,
} from 'lucide-react';

interface Paragraph {
  hash: string;
  original: string;
  translated: string;
  stressed?: string;
  has_audio?: boolean;
}

interface StageData {
  paragraphs?: Paragraph[];
  total_pages?: number;
  total_chunks?: number;
}

interface PendingEdit {
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
  applied_at?: string;
}

interface AsrFlag {
  chunk_id: string;
  audio_path?: string;
  original_text?: string;
  transcribed_text?: string;
  levenshtein_distance?: number;
  char_error_rate?: number;
  mismatch?: boolean;
  reason?: string;
}

interface MqmFlag {
  segment_id: string;
  original?: string;
  translated?: string;
  source_lang?: string;
  target_lang?: string;
  score?: number;
  accept?: boolean;
  issues?: string[];
  reason?: string;
  mqm_model?: string;
}

export const StagesView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const [data, setData] = useState<StageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<'translated' | 'original'>('translated');

  // Audio state
  const [playingHash, setPlayingHash] = useState<string | null>(null);
  const [audio, setAudio] = useState<HTMLAudioElement | null>(null);
  const [newAudioHashes, setNewAudioHashes] = useState<Record<string, string>>({});

  // Editing state
  const [editingHash, setEditingHash] = useState<string | null>(null);
  const [editTranslated, setEditTranslated] = useState('');
  const [editStressed, setEditStressed] = useState('');
  const [savingEdit, setSavingEdit] = useState(false);
  const [regeneratingHash, setRegeneratingHash] = useState<string | null>(null);

  // Queue and Quality Flags state
  const [pendingEdits, setPendingEdits] = useState<PendingEdit[]>([]);
  const [asrFlags, setAsrFlags] = useState<AsrFlag[]>([]);
  const [mqmFlags, setMqmFlags] = useState<MqmFlag[]>([]);
  const [processingEditId, setProcessingEditId] = useState<string | null>(null);
  const [processingFlagId, setProcessingFlagId] = useState<string | null>(null);

  const fetchStageData = async () => {
    if (!slug) return;
    try {
      const res = await apiFetch<StageData>(`/api/preview/book/${slug}`);
      setData(res);
    } catch (err) {
      console.error('Помилка прев\'ю книги:', err);
    } finally {
      setLoading(false);
    }
  };

  const fetchPendingEdits = async () => {
    if (!slug) return;
    try {
      const res = await apiFetch<PendingEdit[] | { queue: PendingEdit[] }>(
        `/api/edit/queue/${slug}?status=pending`
      );
      const queueList = Array.isArray(res) ? res : res.queue || [];
      setPendingEdits(queueList);
    } catch (err) {
      console.error('Помилка завантаження черги редагувань:', err);
    }
  };

  const fetchQualityFlags = async () => {
    if (!slug) return;
    try {
      const [asrRes, mqmRes] = await Promise.all([
        apiFetch<{ status: string; flags?: AsrFlag[] }>(`/api/preview/asr-quality-flags/${slug}`),
        apiFetch<{ status: string; flags?: MqmFlag[] }>(`/api/preview/mqm-quality-flags/${slug}`),
      ]);
      if (asrRes && asrRes.flags) setAsrFlags(asrRes.flags);
      if (mqmRes && mqmRes.flags) setMqmFlags(mqmRes.flags);
    } catch (err) {
      console.error('Помилка завантаження флагів якості:', err);
    }
  };

  useEffect(() => {
    fetchStageData();
    fetchPendingEdits();
    fetchQualityFlags();
  }, [slug]);

  const handlePlayAudio = (hash: string) => {
    const effectiveHash = newAudioHashes[hash] || hash;

    if (playingHash === hash && audio) {
      audio.pause();
      setPlayingHash(null);
      return;
    }

    if (audio) {
      audio.pause();
    }

    const newAudio = new Audio(`/api/preview/audio/${slug}/${effectiveHash}`);
    newAudio.onended = () => setPlayingHash(null);
    newAudio.onerror = () => {
      alert('Помилка завантаження аудіозапису');
      setPlayingHash(null);
    };
    newAudio.play();
    setAudio(newAudio);
    setPlayingHash(hash);
  };

  const handleStartEdit = (p: Paragraph) => {
    setEditingHash(p.hash);
    setEditTranslated(p.translated || '');
    setEditStressed(p.stressed || p.translated || '');
  };

  const handleCancelEdit = () => {
    setEditingHash(null);
    setEditTranslated('');
    setEditStressed('');
  };

  const handleSaveEdit = async (p: Paragraph) => {
    if (!slug) return;
    setSavingEdit(true);

    try {
      const origTranslated = p.translated || '';
      const origStressed = p.stressed || origTranslated;

      const hasTextChanged = editTranslated.trim() !== origTranslated.trim();
      const hasStressChanged = editStressed.trim() !== origStressed.trim();

      if (!hasTextChanged && !hasStressChanged) {
        setEditingHash(null);
        return;
      }

      if (hasTextChanged) {
        await apiFetch(`/api/edit/text/${slug}/${p.hash}`, {
          method: 'PUT',
          body: JSON.stringify({
            original_text: origTranslated,
            new_text: editTranslated.trim(),
          }),
        });
      }

      if (hasStressChanged) {
        await apiFetch(`/api/edit/stress/${slug}/${p.hash}`, {
          method: 'PUT',
          body: JSON.stringify({
            original_stress: origStressed,
            new_stress: editStressed.trim(),
          }),
        });
      }

      await fetchStageData();
      await fetchPendingEdits();
      await fetchQualityFlags();
      setEditingHash(null);
    } catch (err: any) {
      alert(`Помилка збереження редагування: ${err.message}`);
    } finally {
      setSavingEdit(false);
    }
  };

  const handleRegenerateAudio = async (hash: string) => {
    if (!slug) return;
    setRegeneratingHash(hash);
    try {
      const res = await apiFetch<{ new_hash?: string }>(
        `/api/edit/regenerate-audio/${slug}/${hash}`,
        { method: 'POST' }
      );
      if (res && res.new_hash) {
        setNewAudioHashes((prev) => ({ ...prev, [hash]: res.new_hash! }));
        alert('Аудіо успішно згенеровано! Прослухайте результат кнопкою «Синтез» та підтвердіть зміни в черзі.');
      } else {
        alert('Аудіо відправлено на регенерацію.');
      }
      await fetchStageData();
      await fetchPendingEdits();
    } catch (err: any) {
      alert(`Помилка регенерації аудіо: ${err.message}`);
    } finally {
      setRegeneratingHash(null);
    }
  };

  const handleApproveEdit = async (editId: string) => {
    if (!slug) return;
    setProcessingEditId(editId);
    try {
      await apiFetch(`/api/edit/approve/${slug}/${editId}`, { method: 'POST' });
      await fetchStageData();
      await fetchPendingEdits();
    } catch (err: any) {
      alert(`Помилка підтвердження правки: ${err.message}`);
    } finally {
      setProcessingEditId(null);
    }
  };

  const handleDiscardEdit = async (editId: string) => {
    if (!slug) return;
    setProcessingEditId(editId);
    try {
      await apiFetch(`/api/edit/discard/${slug}/${editId}`, { method: 'POST' });
      await fetchPendingEdits();
    } catch (err: any) {
      alert(`Помилка відхилення правки: ${err.message}`);
    } finally {
      setProcessingEditId(null);
    }
  };

  const handleDiscardAsrFlag = async (chunkId: string) => {
    if (!slug) return;
    setProcessingFlagId(chunkId);
    try {
      await apiFetch(`/api/edit/stress/discard/${slug}/${chunkId}`, { method: 'POST' });
      await fetchQualityFlags();
    } catch (err: any) {
      alert(`Помилка відхилення ASR флага: ${err.message}`);
    } finally {
      setProcessingFlagId(null);
    }
  };

  const handleDiscardMqmFlag = async (segmentId: string) => {
    if (!slug) return;
    setProcessingFlagId(segmentId);
    try {
      await apiFetch(`/api/edit/mqm-discard/${slug}/${segmentId}`, { method: 'POST' });
      await fetchQualityFlags();
    } catch (err: any) {
      alert(`Помилка відхилення MQM флага: ${err.message}`);
    } finally {
      setProcessingFlagId(null);
    }
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Top Action Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-2 border-b border-slate-800/60">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <Button
            variant="outline"
            size="sm"
            icon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate('/')}
            className="shrink-0"
          >
            Назад
          </Button>
          <div className="min-w-0 flex-1">
            <h1 className="text-xl md:text-2xl font-bold text-slate-100 truncate">
              {slug}
            </h1>
            <p className="text-xs text-slate-400 font-mono truncate">
              Етапи перекладу, наголосів та аудіо
            </p>
          </div>
        </div>

        {/* View Toggle */}
        <div className="glass-panel p-1 rounded-xl flex items-center gap-1 border border-slate-800 shrink-0">
          <button
            onClick={() => setActiveTab('translated')}
            className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all active-scale ${
              activeTab === 'translated'
                ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            Українська (з наголосами)
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

      {/* Quality Flags Section */}
      {(asrFlags.length > 0 || mqmFlags.length > 0) && (
        <Card className="p-5 border-amber-500/30 bg-amber-950/10 space-y-4">
          <div className="flex items-center gap-2 text-amber-300 font-bold text-sm">
            <ShieldAlert className="w-5 h-5 text-amber-400 shrink-0" />
            <span>Проблеми якості (MQM / ASR): {asrFlags.length + mqmFlags.length}</span>
          </div>

          {/* ASR Flags */}
          {asrFlags.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-amber-400/90 uppercase tracking-wider">
                Невідповідність вимови (ASR)
              </h4>
              <div className="grid grid-cols-1 gap-2.5">
                {asrFlags.map((flag) => (
                  <div
                    key={flag.chunk_id}
                    className="p-3 rounded-xl bg-slate-900/60 border border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1 min-w-0 text-xs">
                      <div className="font-mono text-slate-400 text-[10px]">
                        Chunk: {flag.chunk_id.substring(0, 12)}... | CER: {((flag.char_error_rate || 0) * 100).toFixed(1)}%
                      </div>
                      <div className="text-slate-300">
                        <span className="text-slate-500">Очікувалось:</span> {flag.original_text}
                      </div>
                      <div className="text-amber-200">
                        <span className="text-slate-500">Розпізнано:</span> {flag.transcribed_text}
                      </div>
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Trash2 className="w-3.5 h-3.5 text-slate-400 hover:text-red-400" />}
                      isLoading={processingFlagId === flag.chunk_id}
                      onClick={() => handleDiscardAsrFlag(flag.chunk_id)}
                      className="shrink-0"
                    >
                      Відхилити
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MQM Flags */}
          {mqmFlags.length > 0 && (
            <div className="space-y-2">
              <h4 className="text-xs font-bold text-amber-400/90 uppercase tracking-wider">
                Зауваження до перекладу (MQM Review)
              </h4>
              <div className="grid grid-cols-1 gap-2.5">
                {mqmFlags.map((flag) => (
                  <div
                    key={flag.segment_id}
                    className="p-3 rounded-xl bg-slate-900/60 border border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1 min-w-0 text-xs">
                      <div className="font-mono text-slate-400 text-[10px]">
                        Segment: {flag.segment_id} | Оцінка: {flag.score ?? 'N/A'}/10 | Причина: {flag.reason}
                      </div>
                      <div className="text-slate-300">
                        <span className="text-slate-500">Оригінал:</span> {flag.original}
                      </div>
                      <div className="text-amber-200">
                        <span className="text-slate-500">Переклад:</span> {flag.translated}
                      </div>
                      {flag.issues && flag.issues.length > 0 && (
                        <div className="text-red-300 text-[11px]">
                          Проблеми: {flag.issues.join(', ')}
                        </div>
                      )}
                    </div>
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={<Trash2 className="w-3.5 h-3.5 text-slate-400 hover:text-red-400" />}
                      isLoading={processingFlagId === flag.segment_id}
                      onClick={() => handleDiscardMqmFlag(flag.segment_id)}
                      className="shrink-0"
                    >
                      Відхилити
                    </Button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Main Paragraphs Preview */}
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
          {data.paragraphs.map((p, idx) => {
            const hasAudioAvailable = p.has_audio === true || !!newAudioHashes[p.hash];
            const isEditingThis = editingHash === p.hash;

            return (
              <Card key={p.hash || idx} className="p-4 space-y-3 hover:border-slate-700/60 transition-colors">
                <div className="flex items-center justify-between gap-2 text-xs font-mono text-slate-400 border-b border-slate-800/50 pb-2">
                  <span className="tabular-nums font-semibold text-emerald-400">#{idx + 1}</span>
                  <div className="flex items-center gap-2">
                    {hasAudioAvailable ? (
                      <>
                        <Badge variant="emerald" size="sm">
                          <CheckCircle2 className="w-3 h-3" /> Згенеровано
                        </Badge>
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={playingHash === p.hash ? <Pause className="w-3.5 h-3.5 text-amber-400" /> : <Play className="w-3.5 h-3.5 text-emerald-400" />}
                          onClick={() => handlePlayAudio(p.hash)}
                        >
                          {playingHash === p.hash ? 'Пауза' : 'Синтез'}
                        </Button>
                      </>
                    ) : (
                      <Badge variant="slate" size="sm">
                        <VolumeX className="w-3 h-3" /> Без аудіо
                      </Badge>
                    )}

                    {!isEditingThis && (
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Edit3 className="w-3.5 h-3.5 text-cyan-400" />}
                        onClick={() => handleStartEdit(p)}
                      >
                        Редагувати
                      </Button>
                    )}
                  </div>
                </div>

                {isEditingThis ? (
                  <div className="space-y-3 pt-1">
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-slate-300">
                        Текст перекладу:
                      </label>
                      <textarea
                        value={editTranslated}
                        onChange={(e) => setEditTranslated(e.target.value)}
                        rows={2}
                        className="w-full p-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-slate-100 focus:border-emerald-500 focus:outline-none"
                      />
                    </div>

                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-slate-300">
                        Текст з наголосами (+ перед голосною або знак наголосу):
                      </label>
                      <textarea
                        value={editStressed}
                        onChange={(e) => setEditStressed(e.target.value)}
                        rows={2}
                        className="w-full p-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-emerald-300 font-sans focus:border-emerald-500 focus:outline-none"
                      />
                    </div>

                    <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<RotateCw className="w-3.5 h-3.5 text-indigo-400" />}
                        isLoading={regeneratingHash === p.hash}
                        onClick={() => handleRegenerateAudio(p.hash)}
                      >
                        Регенерувати аудіо
                      </Button>

                      <div className="flex items-center gap-2">
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={<X className="w-3.5 h-3.5" />}
                          onClick={handleCancelEdit}
                        >
                          Скасувати
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          icon={<Save className="w-3.5 h-3.5" />}
                          isLoading={savingEdit}
                          onClick={() => handleSaveEdit(p)}
                        >
                          Зберегти
                        </Button>
                      </div>
                    </div>
                  </div>
                ) : (
                  <p className="text-sm md:text-base leading-relaxed text-slate-200 font-sans">
                    {activeTab === 'translated' ? (p.stressed || p.translated) : p.original}
                  </p>
                )}
              </Card>
            );
          })}
        </div>
      )}

      {/* Pending Edits Section */}
      {pendingEdits.length > 0 && (
        <Card className="p-5 border-cyan-500/30 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-cyan-300 font-bold text-sm">
              <RotateCw className="w-4 h-4 text-cyan-400" />
              <span>Очікують підтвердження (Pending Edits)</span>
            </div>
            <Badge variant="cyan" size="sm">
              {pendingEdits.length}
            </Badge>
          </div>

          <div className="space-y-3">
            {pendingEdits.map((edit) => (
              <div
                key={edit.id}
                className="p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 flex flex-col md:flex-row md:items-center justify-between gap-3 text-xs"
              >
                <div className="space-y-1.5 min-w-0">
                  <div className="flex items-center gap-2 font-mono">
                    <Badge variant={edit.mode === 'text' ? 'emerald' : 'amber'} size="sm">
                      {edit.mode}
                    </Badge>
                    <span className="text-slate-400">Target: {edit.target_id.substring(0, 12)}...</span>
                  </div>
                  {edit.original_value && (
                    <div className="text-slate-400">
                      <span className="text-slate-500">Було:</span> {edit.original_value}
                    </div>
                  )}
                  {edit.edited_value && (
                    <div className="text-emerald-300 font-semibold">
                      <span className="text-slate-500">Стане:</span> {edit.edited_value}
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <Button
                    variant="outline"
                    size="sm"
                    icon={<X className="w-3.5 h-3.5 text-red-400" />}
                    isLoading={processingEditId === edit.id}
                    onClick={() => handleDiscardEdit(edit.id)}
                  >
                    Відхилити
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<Check className="w-3.5 h-3.5" />}
                    isLoading={processingEditId === edit.id}
                    onClick={() => handleApproveEdit(edit.id)}
                  >
                    Підтвердити
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
};
