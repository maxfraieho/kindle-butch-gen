import React, { useEffect, useState, useCallback } from 'react';
import { Modal } from '../components/ui/Modal';
import { Button } from '../components/ui/Button';
import { apiFetch } from '../api/client';
import { ExternalLink, Loader2 } from 'lucide-react';

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

  // ---- load settings whenever modal opens ----
  useEffect(() => {
    if (!isOpen || !slug) return;
    setSettings(null);
    setLoadError(null);

    apiFetch<BookSettings>(`/api/book-settings/${slug}`, { cache: 'no-store' } as RequestInit)
      .then((s) => setSettings(s))
      .catch((err) => setLoadError(err.message || 'Не вдалося завантажити налаштування.'));
  }, [isOpen, slug]);

  // ---- best-effort save (user can retry by reopening, same as old UI) ----
  const save = useCallback(
    async (field: string, value: boolean | string | number) => {
      if (!slug) return;
      try {
        await apiFetch(`/api/book-settings/${slug}`, {
          method: 'POST',
          body: JSON.stringify({ [field]: value }),
        });
      } catch {
        // best-effort — intentionally swallowed, same behavior as dashboard.js
      }
    },
    [slug],
  );


  // ---- model-download consent flow, ported verbatim from dashboard.js ----
  const checkAndConsentModel = useCallback(
    async (
      field: string,
      newChecked: boolean,
      modelKey: 'asr_whisper' | 'gemma' | 'none',
      consentText: string,
      downloadTarget: string,
    ) => {
      if (!newChecked) {
        setSettings((prev) => prev ? { ...prev, [field]: false } : prev);
        await save(field, false);
        return;
      }

      if (modelKey && modelKey !== 'none') {
        try {
          const status = await apiFetch<ModelsStatus>('/api/premium/models-status');

          let modelReady = false;
          if (modelKey === 'asr_whisper' && status.asr_whisper) {
            modelReady = status.asr_whisper.ready;
          } else if (modelKey === 'gemma' && status.gemma) {
            modelReady = status.gemma.ready && (status.mmproj ? status.mmproj.ready : true);
          }

          if (!modelReady) {
            const userConfirmed = window.confirm(consentText);
            if (!userConfirmed) {
              // leave checkbox unchecked
              return;
            }
            // User consented — kick off download
            const dlData = await apiFetch<{ message?: string; status?: string }>(
              '/api/premium/download-models',
              {
                method: 'POST',
                body: JSON.stringify({
                  target: downloadTarget,
                  consent_accepted: true,
                  gemma_terms_accepted: true,
                }),
              },
            );
            alert(dlData.message || 'Завантаження моделей розпочато у фоні.');
          }
        } catch (e) {
          console.warn('Could not verify model status:', e);
        }
      }

      setSettings((prev) => prev ? { ...prev, [field]: true } : prev);
      await save(field, true);
    },
    [save],
  );

  // ---- simple checkbox save (no consent needed) ----
  const handleCheckbox = useCallback(
    (field: string, checked: boolean) => {
      setSettings((prev) => prev ? { ...prev, [field]: checked } : prev);
      save(field, checked);
    },
    [save],
  );

  // ---- resolution select ----
  const handleResolution = useCallback(
    (value: string) => {
      setSettings((prev) => prev ? { ...prev, manga_resolution: value } : prev);
      save('manga_resolution', value);
    },
    [save],
  );

  // ---- batch size and cooldown handlers ----
  const handleBatchPages = useCallback(
    (value: number) => {
      const clamped = Math.max(1, Math.min(500, value));
      setSettings((prev) => prev ? { ...prev, batch_pages: clamped } : prev);
      save('batch_pages', clamped);
    },
    [save],
  );

  const handleCooldownSeconds = useCallback(
    (value: number) => {
      const clamped = Math.max(0, Math.min(3600, value));
      setSettings((prev) => prev ? { ...prev, cooldown_seconds: clamped } : prev);
      save('cooldown_seconds', clamped);
    },
    [save],
  );


  // ---------------------------------------------------------------------------
  // Render helpers
  // ---------------------------------------------------------------------------

  const renderContent = () => {
    if (loadError) {
      return (
        <p className="text-center text-rose-400 text-sm py-4">{loadError}</p>
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
        {/* --- Entitlement status line (verbatim lock text from dashboard.js) --- */}
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

        {/* ------------------------------------------------------------------ */}
        {/* Manga-only section                                                  */}
        {/* ------------------------------------------------------------------ */}
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

        {/* ------------------------------------------------------------------ */}
        {/* Honorifics (free, always available)                                */}
        {/* ------------------------------------------------------------------ */}
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

        {/* ------------------------------------------------------------------ */}
        {/* Batching & Cooldown Pause (Per-book settings)                      */}
        {/* ------------------------------------------------------------------ */}
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


        {/* ------------------------------------------------------------------ */}
        {/* Premium section                                                     */}
        {/* ------------------------------------------------------------------ */}
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/[0.03] p-4 space-y-3">
          {/* Section header */}
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

          {/* ---- ASR verify ---- */}
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

          {/* ---- MQM review ---- */}
          <PremiumToggle
            id="bs-mqm"
            checked={settings.enable_mqm_review}
            entitled={entitled}
            title="🧠 MQM-оцінка якості перекладу"
            description="Окрема модель-рецензент аналізує кожен перекладений абзац (1-10, шукає пропуски й смислові викривлення) і позначає сумнівні місця для перегляду."
            onChange={(checked) => {
              // MQM has no model-download gate per old JS (no modelKey check)
              setSettings((prev) => prev ? { ...prev, enable_mqm_review: checked } : prev);
              save('enable_mqm_review', checked);
            }}
            divider
          />

          {/* ---- Agent editor ---- */}
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

          {/* Upgrade CTA when not entitled */}
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
  divider = false,
}) => (
  <div className={divider ? 'pb-3 border-b border-white/[0.06]' : ''}>
    <label
      className={`flex items-start gap-3 ${entitled ? 'cursor-pointer' : 'cursor-not-allowed opacity-60'}`}
    >
      <input
        type="checkbox"
        id={id}
        checked={checked}
        disabled={!entitled}
        onChange={(e) => onChange(e.target.checked)}
        className="mt-0.5 w-5 h-5 flex-shrink-0 accent-emerald-500 cursor-pointer disabled:cursor-not-allowed"
      />
      <div>
        <span className="text-sm font-semibold text-white block">{title}</span>
        <p className="text-xs text-slate-400 mt-1 leading-relaxed">{description}</p>
      </div>
    </label>
    {!entitled && (
      <p className="mt-1.5 ml-8 text-[11px] text-amber-400/80 font-medium">
        🔒 Потребує підтримки —{' '}
        <a
          href="https://t.me/GetVydraBot"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-amber-300"
        >
          @GetVydraBot
        </a>
      </p>
    )}
  </div>
);
