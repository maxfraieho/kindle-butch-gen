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
  Users,
  UserPlus,
  Sparkles,
  Upload,
  Lock,
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

interface Character {
  id: string;
  name_source?: string[];
  name_target?: string;
  gender?: 'feminine' | 'masculine' | 'neutral' | '';
  grammar_rules?: string;
  speech_style?: string;
  is_pov_narrator?: boolean;
  status: 'auto_drafted' | 'unverified' | 'verified';
  sample_page?: string;
}

interface CastRegistryData {
  characters?: Character[];
  enabled?: boolean;
  entitled?: boolean;
  gender_templates?: Record<string, string>;
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

  // Cast Registry state
  const [castLoading, setCastLoading] = useState(false);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [castEnabled, setCastEnabled] = useState(false);
  const [castEntitled, setCastEntitled] = useState(false);
  const [genderTemplates, setGenderTemplates] = useState<Record<string, string>>({});
  const [thumbVersions, setThumbVersions] = useState<Record<string, number>>({});
  const [savingCast, setSavingCast] = useState(false);
  const [togglingCast, setTogglingCast] = useState(false);
  const [castMessage, setCastMessage] = useState<{ text: string; type: 'success' | 'error' | 'info' } | null>(null);

  // Scan state
  const [scanPageStart, setScanPageStart] = useState<string>('');
  const [scanPageEnd, setScanPageEnd] = useState<string>('');
  const [isScanning, setIsScanning] = useState(false);
  const [scanProgress, setScanProgress] = useState<{ stage: string | null; percent: number } | null>(null);
  const [startingScan, setStartingScan] = useState(false);

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

  const fetchCastRegistry = async () => {
    if (!slug) return;
    setCastLoading(true);
    try {
      const res = await apiFetch<CastRegistryData>(`/api/characters/${slug}`);
      if (res) {
        setCharacters(res.characters || []);
        setCastEnabled(!!res.enabled);
        setCastEntitled(!!res.entitled);
        setGenderTemplates(res.gender_templates || {});
      }
    } catch (err) {
      console.error('Помилка завантаження Cast Registry:', err);
    } finally {
      setCastLoading(false);
    }
  };

  useEffect(() => {
    fetchStageData();
    fetchPendingEdits();
    fetchQualityFlags();
    fetchCastRegistry();

    if (window.location.hash === '#cast') {
      setTimeout(() => {
        document.getElementById('cast')?.scrollIntoView({ behavior: 'smooth' });
      }, 300);
    }
  }, [slug]);

  useEffect(() => {
    let interval: any = null;
    if (isScanning && slug) {
      interval = setInterval(async () => {
        try {
          const prog = await apiFetch<{ stage: string | null; percent: number }>(
            `/api/characters/${slug}/scan-progress`
          );
          if (prog) {
            setScanProgress(prog);
            if (prog.percent >= 100) {
              setIsScanning(false);
              fetchCastRegistry();
            }
          }
        } catch (err) {
          console.error('Помилка оновлення прогресу сканування:', err);
        }
      }, 3000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [isScanning, slug]);

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
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            original_text: origTranslated,
            new_text: editTranslated,
          }),
        });
      }

      if (hasStressChanged) {
        await apiFetch(`/api/edit/stress/${slug}/${p.hash}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            original_stress: origStressed,
            new_stress: editStressed,
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

  // Cast Registry handlers
  const handleToggleCast = async (enable: boolean) => {
    if (!slug) return;
    setTogglingCast(true);
    setCastMessage(null);
    try {
      const res = await apiFetch<{ status: string; enable_cast_registry?: boolean; message?: string }>(
        `/api/characters/${slug}/settings`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ enable_cast_registry: enable }),
        }
      );
      if (res.status === 'success') {
        setCastEnabled(!!res.enable_cast_registry);
        setCastMessage({
          text: enable ? 'Cast Registry увімкнено для цієї книги.' : 'Cast Registry вимкнено.',
          type: 'success',
        });
      }
    } catch (err: any) {
      console.error('Помилка перемикання Cast Registry:', err);
      const msg = err.data?.message || err.message || 'Помилка оновлення налаштувань Cast Registry';
      setCastMessage({ text: msg, type: 'error' });
    } finally {
      setTogglingCast(false);
    }
  };

  const handleStartScan = async () => {
    if (!slug) return;
    setStartingScan(true);
    setCastMessage(null);

    const body: { page_start?: number; page_end?: number } = {};
    if (scanPageStart) body.page_start = Number(scanPageStart);
    if (scanPageEnd) body.page_end = Number(scanPageEnd);

    try {
      const res = await apiFetch<{ status: string; message?: string; model_missing?: boolean }>(
        `/api/characters/${slug}/scan`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        }
      );

      if (res && res.status === 'started') {
        setIsScanning(true);
        setCastMessage({
          text: res.message || 'Сканування персонажів запущено (кілька хвилин)...',
          type: 'success',
        });
      }
    } catch (err: any) {
      console.error('Помилка запуску сканування:', err);
      const msg = err.data?.message || err.message || 'Не вдалося запустити сканування персонажів';
      setCastMessage({ text: msg, type: 'error' });
    } finally {
      setStartingScan(false);
    }
  };

  const handleStopScan = async () => {
    if (!slug) return;
    try {
      await apiFetch(`/api/characters/${slug}/scan/stop`, { method: 'POST' });
      setIsScanning(false);
      setScanProgress(null);
      setCastMessage({ text: 'Сканування зупинено.', type: 'info' });
    } catch (err: any) {
      console.error('Помилка зупинки сканування:', err);
    }
  };

  const handleSaveCast = async () => {
    if (!slug) return;
    setSavingCast(true);
    setCastMessage(null);

    for (const ch of characters) {
      if (ch.gender && !['feminine', 'masculine', 'neutral'].includes(ch.gender)) {
        setCastMessage({
          text: `Некоректний рід "${ch.gender}" у персонажа ${ch.name_target || ch.id}`,
          type: 'error',
        });
        setSavingCast(false);
        return;
      }
    }

    try {
      const res = await apiFetch<{ status: string; count?: number; message?: string }>(
        `/api/characters/${slug}`,
        {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ characters }),
        }
      );
      if (res && res.status === 'success') {
        setCastMessage({
          text: `Реєстр персонажів збережено (${res.count ?? characters.length} осіб).`,
          type: 'success',
        });
        fetchCastRegistry();
      }
    } catch (err: any) {
      console.error('Помилка збереження Cast Registry:', err);
      const msg = err.data?.message || err.message || 'Помилка збереження персонажів';
      setCastMessage({ text: msg, type: 'error' });
    } finally {
      setSavingCast(false);
    }
  };

  const handleUploadThumbnail = async (charId: string, file: File) => {
    if (!slug) return;
    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await apiFetch<{ status: string; message?: string }>(
        `/api/characters/${slug}/thumbnail/${charId}`,
        {
          method: 'POST',
          body: formData,
        }
      );
      if (res && res.status === 'success') {
        setThumbVersions((prev) => ({ ...prev, [charId]: Date.now() }));
        setCastMessage({ text: 'Мініатюру персонажа оновлено.', type: 'success' });
      }
    } catch (err: any) {
      console.error('Помилка завантаження мініатюри:', err);
      const msg = err.data?.message || err.message || 'Помилка завантаження мініатюри';
      setCastMessage({ text: msg, type: 'error' });
    }
  };

  const handleDeleteThumbnail = async (charId: string) => {
    if (!slug) return;
    try {
      await apiFetch(`/api/characters/${slug}/thumbnail/${charId}`, { method: 'DELETE' });
      setThumbVersions((prev) => ({ ...prev, [charId]: Date.now() }));
      setCastMessage({ text: 'Мініатюру видалено.', type: 'info' });
    } catch (err: any) {
      console.error('Помилка видалення мініатюри:', err);
    }
  };

  const updateCharacterField = <K extends keyof Character>(index: number, field: K, value: Character[K]) => {
    setCharacters((prev) => {
      const next = [...prev];
      next[index] = { ...next[index], [field]: value };
      return next;
    });
  };

  const handleAddCharacter = () => {
    const newChar: Character = {
      id: `char_${Date.now()}`,
      name_source: [],
      name_target: '',
      gender: '',
      grammar_rules: '',
      speech_style: '',
      is_pov_narrator: false,
      status: 'unverified',
    };
    setCharacters((prev) => [...prev, newChar]);
  };

  const handleDeleteCharacter = (index: number) => {
    setCharacters((prev) => prev.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-6 pb-12">
      {/* Top Action Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/60">
        <div className="flex items-center gap-2.5 min-w-0">
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
            <h1 className="text-lg md:text-2xl font-bold text-slate-100 truncate">
              {slug}
            </h1>
            <p className="text-[11px] sm:text-xs text-slate-400 font-mono truncate">
              Етапи перекладу, наголосів та аудіо
            </p>
          </div>
        </div>

        {/* View & Anchor Controls */}
        <div className="flex items-center gap-2 w-full sm:w-auto overflow-x-auto no-scrollbar pb-0.5 shrink-0">
          <Button
            variant="outline"
            size="sm"
            icon={<Users className="w-3.5 h-3.5 text-indigo-400" />}
            onClick={() => {
              document.getElementById('cast')?.scrollIntoView({ behavior: 'smooth' });
            }}
            className="shrink-0 text-xs whitespace-nowrap"
          >
            Персонажі ({characters.length})
          </Button>

          <div className="glass-panel p-1 rounded-xl flex items-center gap-1 border border-slate-800 shrink-0">
            <button
              onClick={() => setActiveTab('translated')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all active-scale whitespace-nowrap ${
                activeTab === 'translated'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Українська<span className="hidden sm:inline"> (з наголосами)</span>
            </button>
            <button
              onClick={() => setActiveTab('original')}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all active-scale whitespace-nowrap ${
                activeTab === 'original'
                  ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              Оригінал
            </button>
          </div>
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
                        <span className="text-slate-500">Текст:</span> {flag.original_text}
                      </div>
                      <div className="text-amber-300 font-semibold">
                        <span className="text-slate-500">Розпізнано з аудіо:</span> {flag.transcribed_text}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<X className="w-3.5 h-3.5 text-slate-400" />}
                        isLoading={processingFlagId === flag.chunk_id}
                        onClick={() => handleDiscardAsrFlag(flag.chunk_id)}
                      >
                        Приховати
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* MQM Flags */}
          {mqmFlags.length > 0 && (
            <div className="space-y-2 pt-2 border-t border-amber-500/20">
              <h4 className="text-xs font-bold text-amber-400/90 uppercase tracking-wider">
                Низька якість перекладу (MQM Score)
              </h4>
              <div className="grid grid-cols-1 gap-2.5">
                {mqmFlags.map((flag) => (
                  <div
                    key={flag.segment_id}
                    className="p-3 rounded-xl bg-slate-900/60 border border-amber-500/20 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
                  >
                    <div className="space-y-1 min-w-0 text-xs">
                      <div className="flex items-center gap-2 font-mono text-[10px]">
                        <Badge variant="amber" size="sm">Score: {flag.score ?? 'N/A'}</Badge>
                        <span className="text-slate-400">Segment: {flag.segment_id}</span>
                      </div>
                      {flag.original && (
                        <div className="text-slate-400">
                          <span className="text-slate-500">Оригінал:</span> {flag.original}
                        </div>
                      )}
                      {flag.translated && (
                        <div className="text-slate-200">
                          <span className="text-slate-500">Переклад:</span> {flag.translated}
                        </div>
                      )}
                      {flag.issues && flag.issues.length > 0 && (
                        <div className="text-rose-300">
                          <span className="text-slate-500">Зауваження:</span> {flag.issues.join(', ')}
                        </div>
                      )}
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<X className="w-3.5 h-3.5 text-slate-400" />}
                        isLoading={processingFlagId === flag.segment_id}
                        onClick={() => handleDiscardMqmFlag(flag.segment_id)}
                      >
                        Приховати
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </Card>
      )}

      {/* Paragraphs List */}
      {loading ? (
        <div className="py-12 text-center text-slate-400">Завантаження...</div>
      ) : !data || !data.paragraphs || data.paragraphs.length === 0 ? (
        <Card className="p-8 text-center text-slate-400 space-y-3">
          <FileText className="w-12 h-12 text-slate-600 mx-auto" />
          <p className="text-sm">Текст цієї книги ще не оброблено або він порожній.</p>
        </Card>
      ) : (
        <div className="space-y-4">
          {data.paragraphs.map((p, idx) => {
            const isEditingThis = editingHash === p.hash;

            return (
              <Card key={p.hash || idx} className="p-4 space-y-3">
                <div className="flex items-center justify-between gap-2 border-b border-slate-800/60 pb-2">
                  <span className="text-xs font-mono text-slate-400">
                    #{idx + 1} | Hash: {p.hash ? p.hash.substring(0, 8) : 'N/A'}
                  </span>

                  <div className="flex items-center gap-2">
                    {p.has_audio ? (
                      <Button
                        variant={playingHash === p.hash ? 'primary' : 'ghost'}
                        size="sm"
                        icon={playingHash === p.hash ? <Pause className="w-3.5 h-3.5" /> : <Play className="w-3.5 h-3.5 text-emerald-400" />}
                        onClick={() => handlePlayAudio(p.hash)}
                      >
                        {playingHash === p.hash ? 'Пауза' : 'Синтез'}
                      </Button>
                    ) : (
                      <Badge variant="slate" size="sm">
                        <VolumeX className="w-3 h-3 inline mr-1 text-slate-500" /> Без аудіо
                      </Badge>
                    )}

                    {!isEditingThis && (
                      <Button
                        variant="ghost"
                        size="sm"
                        icon={<Edit3 className="w-3.5 h-3.5 text-slate-400" />}
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

      {/* Cast Registry Section */}
      <div id="cast" className="space-y-4 pt-4">
        <Card className="p-5 border-indigo-500/30 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2 text-indigo-300 font-bold text-base">
              <Users className="w-5 h-5 text-indigo-400 shrink-0" />
              <span>Реєстр персонажів (Cast Registry)</span>
              {castEntitled ? (
                <Badge variant="emerald" size="sm">Premium</Badge>
              ) : (
                <Badge variant="amber" size="sm">🔒 Locked</Badge>
              )}
            </div>

            <div className="flex items-center gap-3">
              <label className="flex items-center gap-2 cursor-pointer text-xs font-semibold text-slate-200">
                <input
                  type="checkbox"
                  checked={castEnabled}
                  disabled={!castEntitled || togglingCast}
                  onChange={(e) => handleToggleCast(e.target.checked)}
                  className="w-4 h-4 rounded bg-slate-900 border-slate-700 text-emerald-500 focus:ring-emerald-500/30"
                />
                <span>Увімкнути Cast Registry для цієї книги</span>
              </label>
            </div>
          </div>

          {!castEntitled && (
            <div className="p-3 rounded-xl bg-amber-950/20 border border-amber-500/30 text-xs text-amber-300 flex items-center gap-2">
              <Lock className="w-4 h-4 shrink-0 text-amber-400" />
              <span>🔒 Розширена можливість. Активуйте через @GetVydraBot (/premium).</span>
            </div>
          )}

          {castMessage && (
            <div
              className={`p-3 rounded-xl text-xs border flex items-center justify-between gap-2 ${
                castMessage.type === 'error'
                  ? 'bg-rose-950/20 border-rose-500/30 text-rose-300'
                  : castMessage.type === 'success'
                    ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-300'
                    : 'bg-slate-900 border-slate-800 text-slate-300'
              }`}
            >
              <span>{castMessage.text}</span>
              <button onClick={() => setCastMessage(null)} className="text-slate-400 hover:text-slate-200">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          )}

          {/* NER Character Scan Panel */}
          {castEnabled && castEntitled && (
            <div className="p-4 rounded-xl bg-slate-900/60 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2 text-xs font-bold text-slate-200">
                  <Sparkles className="w-4 h-4 text-cyan-400" />
                  <span>ШІ Авто-сканування персонажів (NER Scan)</span>
                </div>
                {isScanning && (
                  <Badge variant="cyan" size="sm">
                    Сканування...
                  </Badge>
                )}
              </div>

              <p className="text-xs text-slate-400">
                Сканує сторінки книги, автоматично знаходить імена персонажів та чернетки їхнього роду.
              </p>

              <div className="flex flex-wrap items-center gap-3 pt-1">
                <div className="flex items-center gap-1.5 text-xs text-slate-300">
                  <span>З сторінки:</span>
                  <input
                    type="number"
                    placeholder="1"
                    value={scanPageStart}
                    onChange={(e) => setScanPageStart(e.target.value)}
                    className="w-16 p-1.5 rounded-lg bg-[#090e1c] border border-slate-700 text-xs text-slate-100 text-center focus:border-cyan-500 focus:outline-none"
                  />
                </div>

                <div className="flex items-center gap-1.5 text-xs text-slate-300">
                  <span>по сторінку:</span>
                  <input
                    type="number"
                    placeholder="30"
                    value={scanPageEnd}
                    onChange={(e) => setScanPageEnd(e.target.value)}
                    className="w-16 p-1.5 rounded-lg bg-[#090e1c] border border-slate-700 text-xs text-slate-100 text-center focus:border-cyan-500 focus:outline-none"
                  />
                </div>

                {isScanning ? (
                  <Button
                    variant="danger"
                    size="sm"
                    icon={<X className="w-3.5 h-3.5" />}
                    onClick={handleStopScan}
                  >
                    Зупинити
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    icon={<Sparkles className="w-3.5 h-3.5" />}
                    isLoading={startingScan}
                    onClick={handleStartScan}
                  >
                    Сканувати персонажів
                  </Button>
                )}
              </div>

              {scanProgress && scanProgress.percent > 0 && (
                <div className="space-y-1.5 pt-2 border-t border-slate-800/80">
                  <div className="flex items-center justify-between text-xs text-slate-300">
                    <span>{scanProgress.stage || 'Обробка...'}</span>
                    <span className="font-mono">{scanProgress.percent}%</span>
                  </div>
                  <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
                    <div
                      className="bg-cyan-500 h-2 transition-all duration-300"
                      style={{ width: `${scanProgress.percent}%` }}
                    />
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Characters List */}
          {castLoading ? (
            <div className="text-center py-6 text-xs text-slate-400">Завантаження персонажів...</div>
          ) : characters.length === 0 ? (
            <div className="text-center py-6 border border-dashed border-slate-800 rounded-xl space-y-2">
              <Users className="w-8 h-8 text-slate-600 mx-auto" />
              <p className="text-xs text-slate-400">Реєстр персонажів порожній.</p>
              {castEnabled && castEntitled && (
                <p className="text-xs text-slate-500">Запустіть сканування вище або додайте персонажа вручну.</p>
              )}
            </div>
          ) : (
            <div className="space-y-4 pt-2">
              <div className="grid grid-cols-1 gap-4">
                {characters.map((char, index) => (
                  <div
                    key={char.id || index}
                    className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3"
                  >
                    <div className="flex flex-col sm:flex-row items-start gap-4">
                      {/* Thumbnail Column */}
                      <div className="flex flex-col items-center gap-2 shrink-0">
                        <div className="w-20 h-24 rounded-lg bg-slate-950 border border-slate-800 overflow-hidden flex items-center justify-center relative group">
                          <img
                            src={`/api/characters/${slug}/thumbnail/${char.id}?v=${thumbVersions[char.id] || 0}`}
                            alt={char.name_target || char.id}
                            className="w-full h-full object-cover"
                            onError={(e) => {
                              (e.currentTarget as HTMLElement).style.display = 'none';
                            }}
                          />
                          <div className="absolute inset-0 bg-slate-950/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center gap-1">
                            <label title="Завантажити зображення" className="cursor-pointer p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200">
                              <Upload className="w-3.5 h-3.5" />
                              <input
                                type="file"
                                accept="image/*"
                                className="hidden"
                                onChange={(e) => {
                                  if (e.target.files && e.target.files[0]) {
                                    handleUploadThumbnail(char.id, e.target.files[0]);
                                  }
                                }}
                              />
                            </label>
                            <button
                              title="Видалити зображення"
                              onClick={() => handleDeleteThumbnail(char.id)}
                              className="p-1.5 rounded-lg bg-rose-950/80 hover:bg-rose-900 text-rose-300"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        </div>
                      </div>

                      {/* Info Fields */}
                      <div className="space-y-3 flex-1 min-w-0 w-full">
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-800/60 pb-2">
                          {/* Source aliases / names */}
                          <div className="flex flex-wrap items-center gap-1.5">
                            <span className="text-[11px] text-slate-400 font-semibold">Оригінальні імена:</span>
                            {char.name_source && char.name_source.length > 0 ? (
                              char.name_source.map((ns, i) => (
                                <span key={i} className="px-2 py-0.5 rounded-md bg-slate-800 text-slate-300 text-xs font-mono">
                                  {ns}
                                </span>
                              ))
                            ) : (
                              <span className="text-xs text-slate-500 italic">немає</span>
                            )}
                          </div>

                          {/* Status Select */}
                          <div className="flex items-center gap-2">
                            <select
                              value={char.status}
                              onChange={(e) => updateCharacterField(index, 'status', e.target.value as any)}
                              className="bg-[#090e1c] border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none"
                            >
                              <option value="verified">Verified (Перевірено)</option>
                              <option value="unverified">Unverified (Неперевірено)</option>
                              <option value="auto_drafted">Auto-drafted (Чернетка)</option>
                            </select>

                            <button
                              onClick={() => handleDeleteCharacter(index)}
                              className="text-slate-500 hover:text-rose-400 p-1"
                              title="Видалити персонажа"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {/* Target Name */}
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-300">
                              Ім'я українською (target):
                            </label>
                            <input
                              type="text"
                              value={char.name_target || ''}
                              placeholder="напр. Геральт"
                              onChange={(e) => updateCharacterField(index, 'name_target', e.target.value)}
                              className="w-full p-2 rounded-xl bg-[#090e1c] border border-slate-700 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                            />
                          </div>

                          {/* Gender Select */}
                          <div className="space-y-1">
                            <label className="text-xs font-semibold text-slate-300" title={genderTemplates[char.gender || ''] || ''}>
                              Рід у мові (gender):
                            </label>
                            <select
                              value={char.gender || ''}
                              onChange={(e) => updateCharacterField(index, 'gender', e.target.value as any)}
                              title={genderTemplates[char.gender || ''] || ''}
                              className="w-full p-2 rounded-xl bg-[#090e1c] border border-slate-700 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                            >
                              <option value="">Не вказано (за замовчуванням)</option>
                              <option value="masculine">Чоловічий (він / говорив / пішов)</option>
                              <option value="feminine">Жіночий (вона / говорила / пішла)</option>
                              <option value="neutral">Нейтральний / неістота</option>
                            </select>
                          </div>
                        </div>

                        {/* Speech style / Grammar rules */}
                        <div className="space-y-1">
                          <label className="text-xs font-semibold text-slate-300">
                            Стиль мовлення / граматичні правила:
                          </label>
                          <input
                            type="text"
                            value={char.speech_style || char.grammar_rules || ''}
                            placeholder="напр. Говорить поважно, архаїчні слова..."
                            onChange={(e) => {
                              updateCharacterField(index, 'speech_style', e.target.value);
                              updateCharacterField(index, 'grammar_rules', e.target.value);
                            }}
                            className="w-full p-2 rounded-xl bg-[#090e1c] border border-slate-700 text-xs text-slate-100 focus:border-indigo-500 focus:outline-none"
                          />
                        </div>

                        {/* POV Narrator checkbox */}
                        <div className="pt-1">
                          <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300">
                            <input
                              type="checkbox"
                              checked={!!char.is_pov_narrator}
                              onChange={(e) => updateCharacterField(index, 'is_pov_narrator', e.target.checked)}
                              className="w-3.5 h-3.5 rounded bg-slate-900 border-slate-700 text-indigo-500 focus:ring-indigo-500/30"
                            />
                            <span>Розповідач від першої особи (POV)</span>
                          </label>
                        </div>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Bottom Actions */}
          <div className="flex items-center justify-between gap-2 sm:gap-3 pt-4 border-t border-slate-800">
            <Button
              variant="outline"
              size="sm"
              icon={<UserPlus className="w-3.5 h-3.5 shrink-0" />}
              onClick={handleAddCharacter}
              className="flex-1 sm:flex-initial text-xs whitespace-nowrap justify-center"
            >
              Додати персонажа
            </Button>

            {castEntitled && (
              <Button
                variant="primary"
                size="sm"
                icon={<Save className="w-3.5 h-3.5 shrink-0" />}
                isLoading={savingCast}
                onClick={handleSaveCast}
                className="flex-1 sm:flex-initial text-xs whitespace-nowrap justify-center"
              >
                Зберегти реєстр
              </Button>
            )}
          </div>
        </Card>
      </div>

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
