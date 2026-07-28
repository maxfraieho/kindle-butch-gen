import React, { useEffect, useState, useCallback } from 'react';
import { Modal } from '../components/ui/Modal';
import { Button } from '../components/ui/Button';
import { apiFetch } from '../api/client';
import { ExternalLink, Loader2, Play, Pause } from 'lucide-react';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface BookSettings {
  is_manga: boolean;
  enable_agent_editor: boolean;
  generate_audiobook: boolean;
  enable_asr_verify: boolean;
  keep_honorifics: boolean;
  manga_resolution: string;
  enable_mqm_review: boolean;
  batch_pages: number;
  cooldown_seconds: number;
  entitled: boolean;
  target_lang?: string;
  tts_engine?: string;
  tts_speaker_id?: number;
  tts_speed?: number;
  tts_noise_scale?: number;
  tts_noise_w?: number;
  tts_voice_quality?: string;
}

interface ModelsStatus {
  gemma?: { ready: boolean; bytes: number };
  mmproj?: { ready: boolean; bytes: number };
  asr_whisper?: {
    ready: boolean;
    bytes: number;
    expected_bytes: number;
  };
  downloading: boolean;
}

// ---------------------------------------------------------------------------
// Resolution options — verbatim from openBookSettings() in dashboard.js
// ---------------------------------------------------------------------------

const RESOLUTION_OPTIONS: { value: string; label: string }[] = [
  { value: '1280x1920', label: 'Safe Default (1280x1920)' },
  { value: '1860x2480', label: 'Kindle Scribe (1860x2480)' },
  { value: '1264x1680', label: 'Paperwhite 6 / 2024 (1264x1680)' },
  { value: '1236x1648', label: 'Paperwhite 5 / Oasis 3 (1236x1648)' },
  { value: '1072x1448', label: 'Paperwhite 3/4 / Voyage / Basic 11 (1072x1448)' },
  { value: '600x800',   label: 'Kindle Basic / Older (600x800)' },
  { value: 'original',  label: 'Original (без зміни розміру)' },
];

// ---------------------------------------------------------------------------
// BookSettingsModal
// ---------------------------------------------------------------------------

interface BookSettingsModalProps {
  slug: string | null;
  bookTitle?: string;
  isOpen: boolean;
  onClose: () => void;
}

export const BookSettingsModal: React.FC<BookSettingsModalProps> = ({
  slug,
  bookTitle,
  isOpen,
  onClose,
}) => {
  const [settings, setSettings] = useState<BookSettings | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Manga bubble-tone state
  const [enableBubbleTone, setEnableBubbleTone] = useState<boolean>(false);

  // TTS settings state
  const [ttsEngine, setTtsEngine] = useState<string>('supertonic3');
  const [ttsSpeakerId, setTtsSpeakerId] = useState<number>(2);
  const [ttsSpeed, setTtsSpeed] = useState<number>(1.0);
  const [ttsNoiseScale, setTtsNoiseScale] = useState<number>(0.667);
  const [ttsNoiseW, setTtsNoiseW] = useState<number>(0.8);
  const [ttsVoiceQuality, setTtsVoiceQuality] = useState<string>('medium');
  const [previewText, setPreviewText] = useState<string>('Це приклад озвучення тексту');
  const [isPlayingPreview, setIsPlayingPreview] = useState<boolean>(false);
  const [previewAudio, setPreviewAudio] = useState<HTMLAudioElement | null>(null);
  const [savingTts, setSavingTts] = useState<boolean>(false);
  const [ttsNotice, setTtsNotice] = useState<{ text: string; type: 'success' | 'error' } | null>(null);

  // ---- load settings whenever modal opens ----
  useEffect(() => {
    if (!isOpen || !slug) return;
    setSettings(null);
    setLoadError(null);
    setTtsNotice(null);

    apiFetch<BookSettings>(`/api/book-settings/${slug}`, { cache: 'no-store' } as RequestInit)
      .then((s) => {
        setSettings(s);
        setTtsEngine(s.tts_engine || 'supertonic3');
        setTtsSpeakerId(s.tts_speaker_id ?? 2);
        setTtsSpeed(s.tts_speed ?? 1.0);
        setTtsNoiseScale(s.tts_noise_scale ?? 0.667);
        setTtsNoiseW(s.tts_noise_w ?? 0.8);
        setTtsVoiceQuality(s.tts_voice_quality || 'medium');

        if (s.is_manga) {
          apiFetch<{ enable_bubble_tone?: boolean }>(`/api/manga/${slug}/bubble-tone`)
            .then((bt) => setEnableBubbleTone(!!bt.enable_bubble_tone))
            .catch(() => {});
        }
      })
      .catch((err) => setLoadError(err.message || 'Не вдалося завантажити налаштування.'));
  }, [isOpen, slug]);

  // ---- best-effort save ----
  const save = useCallback(
    async (field: string, value: boolean | string | number) => {
      if (!slug) return;
      try {
        await apiFetch(`/api/book-settings/${slug}`, {
          method: 'POST',
          body: JSON.stringify({ [field]: value }),
        });
      } catch {
        // best-effort — intentionally swallowed
      }
    },
    [slug],
  );

  // ---- model-download consent flow ----
  const checkAndConsentModel = useCallback(
    async (
      field: string,
      targetState: boolean,
      modelKey: keyof ModelsStatus,
      downloadPromptText: string,
      downloadParam: string,
    ) => {
      if (!slug) return;

      if (!targetState) {
        setSettings((prev) => (prev ? { ...prev, [field]: false } : prev));
        save(field, false);
        return;
      }

      try {
        const st = await apiFetch<ModelsStatus>('/api/premium/model-status');
        const entry = st[modelKey];
        const isReady = typeof entry === 'object' ? !!entry.ready : false;

        if (!isReady) {
          if (!window.confirm(downloadPromptText)) {
            return;
          }
          await apiFetch('/api/premium/download-models', {
            method: 'POST',
            body: JSON.stringify({ models: downloadParam }),
          });
          alert('Завантаження моделей розпочато у фоновому режимі.');
        }
      } catch (err: any) {
        console.error('Помилка перевірки статусу моделей:', err);
      }

      setSettings((prev) => (prev ? { ...prev, [field]: true } : prev));
      save(field, true);
    },
    [slug, save],
  );

  // ---- handlers ----
  const handleCheckbox = (field: keyof BookSettings, checked: boolean) => {
    setSettings((prev) => (prev ? { ...prev, [field]: checked } : prev));
    save(field, checked);
  };

  const handleResolution = (val: string) => {
    setSettings((prev) => (prev ? { ...prev, manga_resolution: val } : prev));
    save('manga_resolution', val);
  };

  const handleBatchPages = (val: number) => {
    const clamped = Math.max(1, Math.min(500, val));
    setSettings((prev) => (prev ? { ...prev, batch_pages: clamped } : prev));
    save('batch_pages', clamped);
  };

  const handleCooldownSeconds = (val: number) => {
    const clamped = Math.max(0, Math.min(3600, val));
    setSettings((prev) => (prev ? { ...prev, cooldown_seconds: clamped } : prev));
    save('cooldown_seconds', clamped);
  };

  const handleBubbleToneToggle = async (checked: boolean) => {
    setEnableBubbleTone(checked);
    if (!slug) return;
    try {
      await apiFetch(`/api/manga/${slug}/bubble-tone`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enable_bubble_tone: checked }),
      });
    } catch (err) {
      console.error('Помилка перемикання bubble-tone:', err);
    }
  };

  const handlePlayTtsPreview = async () => {
    if (!slug || !previewText.trim()) return;
    setIsPlayingPreview(true);
    setTtsNotice(null);

    if (previewAudio) {
      previewAudio.pause();
      setPreviewAudio(null);
    }

    try {
      const response = await fetch(`/api/tts-preview/${slug}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text: previewText.trim(),
          tts_engine: ttsEngine,
          tts_speaker_id: ttsSpeakerId,
          tts_speed: ttsSpeed,
          tts_noise_scale: ttsNoiseScale,
          tts_noise_w: ttsNoiseW,
          tts_voice_quality: ttsVoiceQuality,
        }),
      });

      if (!response.ok) {
        let errText = 'Помилка генерації аудіо прикладу';
        try {
          const errJson = await response.json();
          if (errJson.message) errText = errJson.message;
        } catch {}
        throw new Error(errText);
      }

      const blob = await response.blob();
      const audioUrl = URL.createObjectURL(blob);
      const newAudio = new Audio(audioUrl);

      newAudio.onended = () => setIsPlayingPreview(false);
      newAudio.onerror = () => {
        setTtsNotice({ text: 'Помилка відтворення аудіо прикладу', type: 'error' });
        setIsPlayingPreview(false);
      };

      await newAudio.play();
      setPreviewAudio(newAudio);
    } catch (err: any) {
      console.error('Помилка прев\'ю TTS:', err);
      setTtsNotice({ text: err.message || 'Помилка генерації аудіо прикладу', type: 'error' });
      setIsPlayingPreview(false);
    }
  };

  const handleSaveTtsSettings = async () => {
    if (!slug) return;
    setSavingTts(true);
    setTtsNotice(null);

    try {
      const res = await apiFetch<{ status: string; message?: string }>(`/api/tts-settings/${slug}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tts_engine: ttsEngine,
          tts_voice: ttsEngine,
          tts_voice_quality: ttsVoiceQuality,
          tts_speaker_id: ttsSpeakerId,
          tts_speed: ttsSpeed,
          tts_noise_scale: ttsNoiseScale,
          tts_noise_w: ttsNoiseW,
        }),
      });

      if (res && res.status === 'success') {
        setTtsNotice({ text: 'Налаштування голосу збережено.', type: 'success' });
      }
    } catch (err: any) {
      console.error('Помилка збереження TTS:', err);
      const msg = err.data?.message || err.message || 'Помилка збереження налаштувань голосу';
      setTtsNotice({ text: msg, type: 'error' });
    } finally {
      setSavingTts(false);
    }
  };

  // ---- render ----
  const renderContent = () => {
    if (loadError) {
      return (
        <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-sm">
          {loadError}
        </div>
      );
    }

    if (!settings) {
      return (
        <div className="flex items-center justify-center gap-2 py-8 text-slate-400 text-sm">
          <Loader2 className="w-5 h-5 animate-spin" />
          Завантаження налаштувань…
        </div>
      );
    }

    const { entitled } = settings;

    return (
      <div className="space-y-3">
        {/* Entitlement status line */}
        <div className="text-xs text-slate-400 pb-1">
          {entitled ? (
            <span className="text-emerald-400 font-semibold">✓ Розблоковано</span>
          ) : (
            <span className="text-amber-400">
              🔒 Потребує підтримки проєкту —{' '}
              <a
                href="https://t.me/GetVydraBot"
                target="_blank"
                rel="noreferrer"
                className="text-emerald-400 hover:text-emerald-300 underline inline-flex items-center gap-0.5"
              >
                @GetVydraBot
                <ExternalLink className="w-3 h-3" />
              </a>
            </span>
          )}
        </div>

        {/* Manga-only section */}
        {settings.is_manga && (
          <>
            {/* Cast & Context link */}
            <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4">
              <p className="text-sm font-semibold text-white mb-2">🧬 Cast Registry</p>
              <p className="text-xs text-slate-400 mb-3">
                Граматичний рід персонажів у перекладі.
              </p>
              <a
                href={`/view/${slug}#cast`}
                className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
              >
                Відкрити «Cast &amp; Context» →
              </a>
            </div>

            {/* Bubble tone toggle */}
            <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4">
              <label className="flex items-start gap-3 cursor-pointer">
                <input
                  type="checkbox"
                  id="bs-bubble-tone"
                  checked={enableBubbleTone}
                  onChange={(e) => handleBubbleToneToggle(e.target.checked)}
                  className="mt-0.5 w-5 h-5 flex-shrink-0 accent-emerald-500 cursor-pointer"
                />
                <span className="text-sm text-slate-200">
                  <span className="font-semibold text-white">💭 Враховувати емоційний тон бульбашок</span>{' '}
                  — передавати теги ([КРИК], [ДУМКА], [НАРАЦІЯ]) у промпт перекладу.
                </span>
              </label>
            </div>

            {/* E-reader resolution */}
            <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4 space-y-2">
              <label
                htmlFor="bs-resolution"
                className="block text-xs font-semibold text-slate-300"
              >
                📖 Пристрій для читання (роздільність) — типово для цієї книги
              </label>
              <select
                id="bs-resolution"
                value={settings.manga_resolution}
                onChange={(e) => handleResolution(e.target.value)}
                className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-emerald-400 transition-colors"
              >
                {RESOLUTION_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {/* Honorifics */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4">
          <label className="flex items-start gap-3 cursor-pointer">
            <input
              type="checkbox"
              id="bs-honorifics"
              checked={settings.keep_honorifics}
              onChange={(e) => handleCheckbox('keep_honorifics', e.target.checked)}
              className="mt-0.5 w-5 h-5 flex-shrink-0 accent-emerald-500 cursor-pointer"
            />
            <span className="text-sm text-slate-200">
              <span className="font-semibold text-white">🈂️ Зберігати гоноративи</span>{' '}
              — не перекладати суфікси на кшталт -сан, -чан, -кун, залишати як у оригіналі.
            </span>
          </label>
        </div>

        {/* TTS Voice & Listen Preview section */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4 space-y-4">
          <div className="flex items-center justify-between border-b border-slate-700/40 pb-2">
            <span className="text-sm font-semibold text-white flex items-center gap-2">
              🔊 Голос озвучення (TTS)
            </span>
          </div>

          {ttsNotice && (
            <div
              className={`p-2.5 rounded-lg text-xs flex items-center justify-between gap-2 border ${
                ttsNotice.type === 'error'
                  ? 'bg-rose-950/30 border-rose-500/40 text-rose-300'
                  : 'bg-emerald-950/30 border-emerald-500/40 text-emerald-300'
              }`}
            >
              <span>{ttsNotice.text}</span>
              <button onClick={() => setTtsNotice(null)} className="text-slate-400 hover:text-slate-200">
                ✕
              </button>
            </div>
          )}

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {/* Engine select */}
            <div className="space-y-1">
              <label htmlFor="bs-tts-engine" className="block text-xs font-semibold text-slate-300">
                Рушій TTS
              </label>
              <select
                id="bs-tts-engine"
                value={ttsEngine}
                onChange={(e) => setTtsEngine(e.target.value)}
                className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-xs px-3 py-2 focus:outline-none focus:border-emerald-400"
              >
                <option value="supertonic3">Supertonic 3 (Flow Matching, 31 мова)</option>
                {(settings.target_lang || 'uk') === 'uk' && (
                  <option value="styletts2">StyleTTS2 (спеціалізована для української)</option>
                )}
              </select>
            </div>

            {/* Speaker ID */}
            {ttsEngine === 'supertonic3' && (
              <div className="space-y-1">
                <label htmlFor="bs-tts-speaker" className="block text-xs font-semibold text-slate-300">
                  Speaker ID (0–9)
                </label>
                <input
                  id="bs-tts-speaker"
                  type="number"
                  min={0}
                  max={9}
                  value={ttsSpeakerId}
                  onChange={(e) => setTtsSpeakerId(parseInt(e.target.value, 10) || 0)}
                  className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-xs px-3 py-2 focus:outline-none focus:border-emerald-400 font-mono"
                />
              </div>
            )}

            {/* Speed */}
            <div className="space-y-1">
              <label htmlFor="bs-tts-speed" className="block text-xs font-semibold text-slate-300">
                Швидкість озвучення ({ttsSpeed.toFixed(1)}x)
              </label>
              <input
                id="bs-tts-speed"
                type="range"
                min={0.5}
                max={2.0}
                step={0.1}
                value={ttsSpeed}
                onChange={(e) => setTtsSpeed(parseFloat(e.target.value) || 1.0)}
                className="w-full accent-emerald-500 cursor-pointer"
              />
            </div>
          </div>

          {/* StyleTTS2 specific fields */}
          {ttsEngine === 'styletts2' && (
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2 border-t border-slate-700/40">
              <div className="space-y-1">
                <label htmlFor="bs-tts-noise-scale" className="block text-xs font-semibold text-slate-300">
                  Noise Scale (0.1–1.5)
                </label>
                <input
                  id="bs-tts-noise-scale"
                  type="number"
                  min={0.1}
                  max={1.5}
                  step={0.05}
                  value={ttsNoiseScale}
                  onChange={(e) => setTtsNoiseScale(parseFloat(e.target.value) || 0.667)}
                  className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-xs px-2.5 py-1.5 focus:outline-none focus:border-emerald-400 font-mono"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="bs-tts-noise-w" className="block text-xs font-semibold text-slate-300">
                  Noise W (0.1–1.5)
                </label>
                <input
                  id="bs-tts-noise-w"
                  type="number"
                  min={0.1}
                  max={1.5}
                  step={0.05}
                  value={ttsNoiseW}
                  onChange={(e) => setTtsNoiseW(parseFloat(e.target.value) || 0.8)}
                  className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-xs px-2.5 py-1.5 focus:outline-none focus:border-emerald-400 font-mono"
                />
              </div>

              <div className="space-y-1">
                <label htmlFor="bs-tts-quality" className="block text-xs font-semibold text-slate-300">
                  Якість голосу
                </label>
                <select
                  id="bs-tts-quality"
                  value={ttsVoiceQuality}
                  onChange={(e) => setTtsVoiceQuality(e.target.value)}
                  className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-xs px-2.5 py-1.5 focus:outline-none focus:border-emerald-400"
                >
                  <option value="high">Висока (High)</option>
                  <option value="medium">Середня (Medium)</option>
                  <option value="low">Низька (Low)</option>
                  <option value="x_low">Швидка (Extra Low)</option>
                </select>
              </div>
            </div>
          )}

          {/* Listen Preview Phrase & Controls */}
          <div className="space-y-2 pt-2 border-t border-slate-700/40">
            <label htmlFor="bs-tts-preview-phrase" className="block text-xs font-semibold text-slate-300">
              Фраза для прослуховування прикладу
            </label>
            <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
              <input
                id="bs-tts-preview-phrase"
                type="text"
                value={previewText}
                onChange={(e) => setPreviewText(e.target.value)}
                placeholder="Введіть текст для прослуховування..."
                className="flex-1 rounded-lg bg-[#090e1c] border border-slate-700 text-white text-xs px-3 py-2 focus:outline-none focus:border-emerald-400"
              />
              <Button
                variant="outline"
                size="sm"
                icon={isPlayingPreview ? <Pause className="w-3.5 h-3.5 text-amber-400" /> : <Play className="w-3.5 h-3.5 text-emerald-400" />}
                isLoading={isPlayingPreview}
                onClick={handlePlayTtsPreview}
                className="shrink-0 text-xs"
              >
                {isPlayingPreview ? 'Програвання...' : '▶️ Прослухати приклад'}
              </Button>
            </div>
          </div>

          <div className="flex justify-end pt-1">
            <Button
              variant="primary"
              size="sm"
              isLoading={savingTts}
              onClick={handleSaveTtsSettings}
              className="text-xs"
            >
              Зберегти налаштування голосу
            </Button>
          </div>
        </div>

        {/* Batching & Cooldown Pause */}
        <div className="rounded-xl border border-slate-700/60 bg-slate-800/30 p-4 space-y-4">
          <div className="space-y-1.5">
            <label htmlFor="bs-batch-pages" className="block text-xs font-semibold text-slate-200">
              📦 Сторінок на батч (1–500)
            </label>
            <p className="text-xs text-slate-400 leading-relaxed">
              Кількість сторінок PDF, яка обробляється за один прогін розпізнавання та перекладу.
            </p>
            <input
              id="bs-batch-pages"
              type="number"
              min={1}
              max={500}
              value={settings.batch_pages ?? 50}
              onChange={(e) => handleBatchPages(parseInt(e.target.value, 10) || 50)}
              className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-emerald-400 font-mono transition-colors"
            />
          </div>

          <div className="space-y-1.5 pt-3 border-t border-slate-700/40">
            <label htmlFor="bs-cooldown" className="block text-xs font-semibold text-slate-200">
              ❄️ Пауза між батчами, сек. (охолодження, 0–3600)
            </label>
            <p className="text-xs text-slate-400 leading-relaxed">
              Пауза для охолодження процесора між батчами (0 = без паузи).
            </p>
            <input
              id="bs-cooldown"
              type="number"
              min={0}
              max={3600}
              value={settings.cooldown_seconds ?? 30}
              onChange={(e) => handleCooldownSeconds(parseInt(e.target.value, 10) || 0)}
              className="w-full rounded-lg bg-[#090e1c] border border-slate-700 text-white text-sm px-3 py-2 focus:outline-none focus:border-emerald-400 font-mono transition-colors"
            />
          </div>
        </div>

        {/* Premium section */}
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.03] p-4 space-y-3">
          <div className="flex items-center justify-between pb-3 border-b border-white/[0.08]">
            <span className="text-sm font-bold text-amber-400 flex items-center gap-1.5">
              👑 Преміум-можливості (UI 2.0)
            </span>
            {entitled ? (
              <span className="text-[11px] text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-2 py-0.5 rounded-md font-semibold">
                ✓ Активно
              </span>
            ) : (
              <span className="text-[11px] text-amber-300 bg-amber-500/15 border border-amber-500/30 px-2 py-0.5 rounded-md font-semibold">
                🔒 Потребує підтримки
              </span>
            )}
          </div>

          <PremiumToggle
            id="bs-asr"
            checked={settings.enable_asr_verify}
            entitled={entitled}
            title="🎙️ ASR-верифікація наголосів (Whisper)"
            description="Порівнює синтезоване аудіо з текстом через Whisper для виявлення помилок наголосів і направлення їх у чергу верифікації."
            onChange={(checked) =>
              checkAndConsentModel(
                'enable_asr_verify',
                checked,
                'asr_whisper',
                'Для роботи цієї функції потрібно завантажити додаткові нейромережеві моделі (наприклад, Whisper для розпізнавання мовлення, ~245 МБ). Рекомендовано Wi-Fi. Завантажити зараз?',
                'asr',
              )
            }
            divider
          />

          <PremiumToggle
            id="bs-mqm"
            checked={settings.enable_mqm_review}
            entitled={entitled}
            title="🧠 MQM-оцінка якості перекладу"
            description="Окрема модель-рецензент аналізує кожен перекладений абзац (1-10, шукає пропуски й смислові викривлення) і позначає сумнівні місця для перегляду."
            onChange={(checked) => {
              setSettings((prev) => prev ? { ...prev, enable_mqm_review: checked } : prev);
              save('enable_mqm_review', checked);
            }}
            divider
          />

          <PremiumToggle
            id="bs-agent"
            checked={settings.enable_agent_editor}
            entitled={entitled}
            title="🤖 Агент-редактор (Gemma 3 4B)"
            description="Автономний ШІ перевіряє складні й проблемні місця перекладу та пропонує виправлення з вашим підтвердженням."
            onChange={(checked) =>
              checkAndConsentModel(
                'enable_agent_editor',
                checked,
                'gemma',
                'Для роботи цієї функції потрібні моделі Gemma 3 4B та Vision Projector (~3.5 ГБ). Рекомендовано Wi-Fi. Завантажити зараз?',
                'gemma',
              )
            }
          />

          {!entitled && (
            <div className="pt-2 border-t border-white/[0.06]">
              <a
                href="https://t.me/GetVydraBot"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-amber-300 hover:text-amber-200 transition-colors font-medium"
              >
                Активувати підтримку через @GetVydraBot
                <ExternalLink className="w-3 h-3" />
              </a>
            </div>
          )}
        </div>
      </div>
    );
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={bookTitle ? `Налаштування — ${bookTitle}` : 'Налаштування книги'}
    >
      {renderContent()}
    </Modal>
  );
};

// ---------------------------------------------------------------------------
// PremiumToggle — reusable locked/unlocked checkbox row
// ---------------------------------------------------------------------------

interface PremiumToggleProps {
  id: string;
  checked: boolean;
  entitled: boolean;
  title: string;
  description: string;
  onChange: (checked: boolean) => void;
  divider?: boolean;
}

const PremiumToggle: React.FC<PremiumToggleProps> = ({
  id,
  checked,
  entitled,
  title,
  description,
  onChange,
  divider,
}) => {
  return (
    <div className={divider ? 'pb-3 border-b border-white/[0.06]' : ''}>
      <label
        htmlFor={id}
        className={`flex items-start gap-3 ${
          entitled ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'
        }`}
      >
        <input
          type="checkbox"
          id={id}
          checked={checked}
          disabled={!entitled}
          onChange={(e) => onChange(e.target.checked)}
          className="mt-0.5 w-5 h-5 flex-shrink-0 accent-amber-500 rounded border-slate-700 bg-[#090e1c]"
        />
        <div className="space-y-0.5">
          <div className="text-sm font-semibold text-slate-200">{title}</div>
          <div className="text-xs text-slate-400 leading-relaxed">{description}</div>
        </div>
      </label>
    </div>
  );
};
