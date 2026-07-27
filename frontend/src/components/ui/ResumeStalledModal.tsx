import React from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { Book } from '../../api/client';
import { AlertTriangle, Play, XCircle } from 'lucide-react';

export interface ResumeStalledModalProps {
  book: Book | null;
  onResume: (slug: string) => void;
  onDismiss: (slug: string) => void;
}

export const ResumeStalledModal: React.FC<ResumeStalledModalProps> = ({
  book,
  onResume,
  onDismiss,
}) => {
  if (!book) return null;

  const handleResume = () => {
    onResume(book.slug);
  };

  const handleDismiss = () => {
    onDismiss(book.slug);
  };

  return (
    <Modal
      isOpen={!!book}
      onClose={handleDismiss}
      title="Перервана конвертація"
    >
      <div className="space-y-4">
        <div className="p-4 bg-amber-950/30 border border-amber-500/40 rounded-xl flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
          <div className="space-y-1.5 min-w-0">
            <h4 className="text-sm font-bold text-amber-200 truncate">
              {book.title || book.slug}
            </h4>
            <p className="text-xs text-amber-300/90 leading-relaxed">
              {book.stalled_reason || 'Виявлено перерваний процес обробки цієї книги. Бажаєте відновити конвертацію?'}
            </p>
          </div>
        </div>

        <p className="text-xs text-slate-300">
          Ви можете відновити процес зараз або відкласти дію та виконати відновлення пізніше.
        </p>

        <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800/80">
          <Button
            variant="outline"
            size="md"
            icon={<XCircle className="w-4 h-4" />}
            onClick={handleDismiss}
          >
            Не зараз
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Play className="w-4 h-4" />}
            onClick={handleResume}
          >
            Відновити
          </Button>
        </div>
      </div>
    </Modal>
  );
};
