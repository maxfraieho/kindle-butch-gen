import React, { useState, useEffect } from 'react';
import { Modal } from './Modal';
import { Button } from './Button';
import { apiFetch } from '../../api/client';
import { Folder, FolderUp, ChevronRight, AlertCircle, RefreshCw, Check } from 'lucide-react';

export interface FolderBrowserModalProps {
  open: boolean;
  initialPath?: string;
  onClose: () => void;
  onSelect: (path: string) => void;
}

interface BrowseFsResponse {
  current?: string;
  parent?: string | null;
  dirs?: Array<{ name: string; path: string }>;
  hint?: string | null;
  error?: string | null;
}

export const FolderBrowserModal: React.FC<FolderBrowserModalProps> = ({
  open,
  initialPath,
  onClose,
  onSelect,
}) => {
  const [currentPath, setCurrentPath] = useState<string>('');
  const [inputPath, setInputPath] = useState<string>('');
  const [parentPath, setParentPath] = useState<string | null>(null);
  const [dirs, setDirs] = useState<Array<{ name: string; path: string }>>([]);
  const [hint, setHint] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(false);

  const loadDirectory = async (path?: string) => {
    setLoading(true);
    setError(null);
    try {
      const query = path ? `?path=${encodeURIComponent(path)}` : '';
      const data = await apiFetch<BrowseFsResponse>(`/api/browse-fs${query}`);

      if (data.error) {
        setError(data.error);
      } else {
        const resolvedCurrent = data.current || path || '';
        setCurrentPath(resolvedCurrent);
        setInputPath(resolvedCurrent);
        setParentPath(data.parent ?? null);
        setDirs(data.dirs || []);
        setHint(data.hint ?? null);
      }
    } catch (err: any) {
      setError(err.message || 'Помилка отримання вмісту директорії');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (open) {
      loadDirectory(initialPath);
    }
  }, [open, initialPath]);

  const handleConfirm = () => {
    const selected = inputPath.trim() || currentPath;
    if (selected) {
      onSelect(selected);
      onClose();
    }
  };

  return (
    <Modal isOpen={open} onClose={onClose} title="Вибір директорії зберігання">
      <div className="space-y-4">
        {/* Navigation bar: Current Path Input & Up Button */}
        <div className="space-y-2">
          <label className="text-xs font-semibold text-slate-300">Поточний шлях</label>
          <div className="flex gap-2">
            <div className="relative flex-1">
              <input
                type="text"
                value={inputPath}
                onChange={(e) => setInputPath(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    loadDirectory(inputPath);
                  }
                }}
                placeholder="/storage/emulated/0/..."
                className="w-full bg-slate-900 border border-slate-700/80 rounded-xl px-3 py-2 text-xs font-mono text-slate-100 focus:outline-none focus:border-emerald-500 transition-colors"
              />
            </div>
            <Button
              variant="outline"
              size="sm"
              disabled={!parentPath || loading}
              onClick={() => parentPath && loadDirectory(parentPath)}
              icon={<FolderUp className="w-4 h-4 text-emerald-400" />}
              title="Перейти у батьківську директорію"
            >
              Вгору
            </Button>
          </div>
        </div>

        {/* Hint alert if present */}
        {hint && (
          <div className="p-3 bg-amber-950/30 border border-amber-500/40 rounded-xl flex items-start gap-2 text-xs text-amber-200">
            <AlertCircle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <span>{hint}</span>
          </div>
        )}

        {/* Error alert if present */}
        {error && (
          <div className="p-3 bg-rose-950/30 border border-rose-500/40 rounded-xl flex items-start gap-2 text-xs text-rose-300">
            <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Directory List Container */}
        <div className="space-y-1">
          <div className="flex items-center justify-between text-xs text-slate-400 px-1 pb-1">
            <span>Підпапки</span>
            {loading && <RefreshCw className="w-3.5 h-3.5 animate-spin text-emerald-400" />}
          </div>

          <div className="max-h-56 min-h-[120px] overflow-y-auto space-y-1 rounded-xl border border-slate-800 bg-slate-950/50 p-2">
            {loading && dirs.length === 0 ? (
              <div className="flex items-center justify-center h-28 text-xs text-slate-400 gap-2">
                <RefreshCw className="w-4 h-4 animate-spin text-emerald-400" />
                <span>Завантаження директорії...</span>
              </div>
            ) : dirs.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-28 text-xs text-slate-400 gap-2">
                <Folder className="w-6 h-6 text-slate-600" />
                <span>Підпапок не знайдено</span>
              </div>
            ) : (
              dirs.map((dir) => (
                <button
                  key={dir.path}
                  type="button"
                  onClick={() => loadDirectory(dir.path)}
                  className="w-full flex items-center justify-between px-3 py-2 rounded-lg text-left text-xs text-slate-200 hover:bg-slate-800/70 hover:text-emerald-300 transition-colors group"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Folder className="w-4 h-4 text-emerald-400/80 group-hover:text-emerald-300 shrink-0" />
                    <span className="truncate font-medium">{dir.name}</span>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-emerald-400 shrink-0" />
                </button>
              ))
            )}
          </div>
        </div>

        {/* Modal Action Buttons */}
        <div className="flex items-center justify-end gap-3 pt-3 border-t border-slate-800/80">
          <Button variant="outline" size="md" onClick={onClose}>
            Скасувати
          </Button>
          <Button
            variant="primary"
            size="md"
            icon={<Check className="w-4 h-4" />}
            onClick={handleConfirm}
          >
            Обрати цю теку
          </Button>
        </div>
      </div>
    </Modal>
  );
};
