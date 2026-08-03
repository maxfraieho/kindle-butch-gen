import React, { useState, useEffect } from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { apiFetch } from '../../api/client';
import { Sparkles, Save, FileText, CheckCircle2, AlertCircle } from 'lucide-react';

export interface CopyrightMeta {
  translator_name: string;
  original_title: string;
  original_author: string;
  original_url: string;
  original_license: string;
  generated_text_uk: string;
  generated_text_en: string;
  edited_text_uk: string | null;
  edited_text_en: string | null;
}

export interface CopyrightMetaModalProps {
  slug: string | null;
  bookTitle?: string;
  isOpen: boolean;
  onClose: () => void;
}

export const CopyrightMetaModal: React.FC<CopyrightMetaModalProps> = ({
  slug,
  bookTitle,
  isOpen,
  onClose,
}) => {
  const [translatorName, setTranslatorName] = useState('');
  const [originalTitle, setOriginalTitle] = useState('');
  const [originalAuthor, setOriginalAuthor] = useState('');
  const [originalUrl, setOriginalUrl] = useState('');
  const [originalLicense, setOriginalLicense] = useState('');

  const [generatedUk, setGeneratedUk] = useState('');
  const [generatedEn, setGeneratedEn] = useState('');
  const [editedUk, setEditedUk] = useState('');
  const [editedEn, setEditedEn] = useState('');

  const [isLoadingMeta, setIsLoadingMeta] = useState(false);
  const [isGenerating, setIsGenerating] = useState(false);
  const [isSavingText, setIsSavingText] = useState(false);

  const [notice, setNotice] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    if (!isOpen || !slug) return;
    setNotice(null);
    setIsLoadingMeta(true);

    apiFetch<{ copyright_meta: CopyrightMeta }>(`/api/book/${slug}/copyright-meta`)
      .then((res) => {
        const meta = res.copyright_meta || ({} as Partial<CopyrightMeta>);
        setTranslatorName(meta.translator_name || '');
        setOriginalTitle(meta.original_title || '');
        setOriginalAuthor(meta.original_author || '');
        setOriginalUrl(meta.original_url || '');
        setOriginalLicense(meta.original_license || '');

        setGeneratedUk(meta.generated_text_uk || '');
        setGeneratedEn(meta.generated_text_en || '');

        setEditedUk(meta.edited_text_uk !== null && meta.edited_text_uk !== undefined ? meta.edited_text_uk : (meta.generated_text_uk || ''));
        setEditedEn(meta.edited_text_en !== null && meta.edited_text_en !== undefined ? meta.edited_text_en : (meta.generated_text_en || ''));
      })
      .catch((err) => {
        setNotice({ type: 'error', text: err.message || 'Не вдалося завантажити дані копірайту' });
      })
      .finally(() => {
        setIsLoadingMeta(false);
      });
  }, [isOpen, slug]);

  const handleGenerate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!slug) return;
    setIsGenerating(true);
    setNotice(null);

    try {
      const res = await apiFetch<{
        status: string;
        generated_text_uk: string;
        generated_text_en: string;
        copyright_meta: CopyrightMeta;
      }>(`/api/book/${slug}/copyright-meta`, {
        method: 'POST',
        body: JSON.stringify({
          translator_name: translatorName,
          original_title: originalTitle,
          original_author: originalAuthor,
          original_url: originalUrl,
          original_license: originalLicense,
        }),
      });

      const meta = res.copyright_meta;
      setGeneratedUk(res.generated_text_uk || meta.generated_text_uk || '');
      setGeneratedEn(res.generated_text_en || meta.generated_text_en || '');

      // Keep edited text if existing, or update with newly generated text
      setEditedUk(meta.edited_text_uk !== null ? meta.edited_text_uk : res.generated_text_uk);
      setEditedEn(meta.edited_text_en !== null ? meta.edited_text_en : res.generated_text_en);

      setNotice({ type: 'success', text: 'Текст копірайту успішно згенеровано!' });
    } catch (err: any) {
      setNotice({ type: 'error', text: err.message || 'Помилка при генерації тексту копірайту' });
    } finally {
      setIsGenerating(false);
    }
  };

  const handleSaveEdits = async () => {
    if (!slug) return;
    setIsSavingText(true);
    setNotice(null);

    try {
      const res = await apiFetch<{ status: string; copyright_meta: CopyrightMeta }>(
        `/api/book/${slug}/copyright-meta/text`,
        {
          method: 'PUT',
          body: JSON.stringify({
            edited_text_uk: editedUk,
            edited_text_en: editedEn,
          }),
        }
      );

      const meta = res.copyright_meta;
      if (meta) {
        setEditedUk(meta.edited_text_uk !== null ? meta.edited_text_uk : meta.generated_text_uk);
        setEditedEn(meta.edited_text_en !== null ? meta.edited_text_en : meta.generated_text_en);
      }
      setNotice({ type: 'success', text: 'Відредагований текст копірайту збережено!' });
    } catch (err: any) {
      setNotice({ type: 'error', text: err.message || 'Помилка при збереженні відредагованого тексту' });
    } finally {
      setIsSavingText(false);
    }
  };

  const inputStyles =
    'w-full bg-[#090e1c] border border-slate-700/60 rounded-xl px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-colors';

  const textareaStyles =
    'w-full font-mono text-xs p-3.5 bg-[#090e1c] border border-slate-700/60 rounded-xl text-slate-200 focus:outline-none focus:border-cyan-500 leading-relaxed resize-y';

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={bookTitle ? `Метадані копірайту — ${bookTitle}` : 'Метадані сторінки копірайту'}
    >
      <div className="space-y-6">
        {notice && (
          <div
            className={`p-3.5 rounded-xl border flex items-center gap-3 text-xs ${
              notice.type === 'success'
                ? 'bg-emerald-950/40 border-emerald-500/40 text-emerald-300'
                : 'bg-rose-950/40 border-rose-500/40 text-rose-300'
            }`}
          >
            {notice.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            ) : (
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
            )}
            <span>{notice.text}</span>
          </div>
        )}

        {isLoadingMeta ? (
          <div className="py-8 text-center text-xs text-slate-400">
            Завантаження даних копірайту...
          </div>
        ) : (
          <>
            {/* Form Section */}
            <form onSubmit={handleGenerate} className="space-y-4">
              <div className="flex items-center gap-2 pb-1 border-b border-slate-800/80">
                <FileText className="w-4 h-4 text-cyan-400" />
                <h4 className="text-sm font-semibold text-slate-200">Параметри книги</h4>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">Перекладач</label>
                  <input
                    type="text"
                    value={translatorName}
                    onChange={(e) => setTranslatorName(e.target.value)}
                    placeholder="Напр. Іван Франко"
                    className={inputStyles}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">Оригінальна назва</label>
                  <input
                    type="text"
                    value={originalTitle}
                    onChange={(e) => setOriginalTitle(e.target.value)}
                    placeholder="Напр. Clean Code"
                    className={inputStyles}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">Оригінальний автор</label>
                  <input
                    type="text"
                    value={originalAuthor}
                    onChange={(e) => setOriginalAuthor(e.target.value)}
                    placeholder="Напр. Robert C. Martin"
                    className={inputStyles}
                  />
                </div>

                <div className="space-y-1.5">
                  <label className="text-xs font-medium text-slate-300">Оригінальна ліцензія</label>
                  <input
                    type="text"
                    value={originalLicense}
                    onChange={(e) => setOriginalLicense(e.target.value)}
                    placeholder="Напр. CC-BY-4.0"
                    className={inputStyles}
                  />
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-slate-300">Оригінальний URL</label>
                <input
                  type="text"
                  value={originalUrl}
                  onChange={(e) => setOriginalUrl(e.target.value)}
                  placeholder="Напр. https://example.com/docs"
                  className={inputStyles}
                />
              </div>

              <div className="flex justify-end pt-1">
                <Button
                  type="submit"
                  variant="primary"
                  size="md"
                  isLoading={isGenerating}
                  icon={<Sparkles className="w-4 h-4" />}
                >
                  Згенерувати текст
                </Button>
              </div>
            </form>

            {/* Generated & Editable Text Section */}
            {(generatedUk || generatedEn || editedUk || editedEn) && (
              <div className="space-y-5 pt-4 border-t border-slate-800/80">
                <div className="flex items-center justify-between">
                  <h4 className="text-sm font-semibold text-slate-200">
                    Текст сторінки копірайту
                  </h4>
                  <span className="text-[11px] text-slate-400 font-mono">
                    Редагування доступне напряму
                  </span>
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-medium text-slate-300 flex items-center justify-between">
                    <span>Українська версія (UK)</span>
                  </label>
                  <textarea
                    rows={6}
                    value={editedUk}
                    onChange={(e) => setEditedUk(e.target.value)}
                    className={textareaStyles}
                  />
                </div>

                <div className="space-y-2">
                  <label className="text-xs font-medium text-slate-300 flex items-center justify-between">
                    <span>Англійська версія (EN)</span>
                  </label>
                  <textarea
                    rows={6}
                    value={editedEn}
                    onChange={(e) => setEditedEn(e.target.value)}
                    className={textareaStyles}
                  />
                </div>

                <div className="flex justify-end pt-2">
                  <Button
                    type="button"
                    variant="secondary"
                    size="md"
                    isLoading={isSavingText}
                    icon={<Save className="w-4 h-4" />}
                    onClick={handleSaveEdits}
                  >
                    Зберегти правки
                  </Button>
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </Modal>
  );
};
