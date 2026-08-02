import React, { useState, useEffect, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import {
  ArrowLeft,
  Play,
  Square,
  BookOpen,
  CheckCircle2,
  AlertTriangle,
  X,
  Check,
  ChevronRight,
  Loader2,
} from 'lucide-react';

// ─── Types ───────────────────────────────────────────────────────────────────

interface PipelineStatus {
  running: boolean;
  stage: string | null;
  log: string[];
  flags_pending: number;
}

interface EditorFlag {
  flag_id: string;
  chapter: string;
  para_index: number;
  category: 'artifact_loss' | 'structural_drift' | 'fact_drift' | 'translation_hostile';
  severity: number;
  source_excerpt: string;
  humanized_excerpt: string;
  issue: string;
  suggested_rewrite: string | null;
  detector: 'deterministic' | 'model';
  editor_model?: string;
  // resolved state (returned by backend after apply/discard):
  resolution?: 'applied' | 'discarded';
}

// ─── Constants ────────────────────────────────────────────────────────────────

const KNOWN_STAGES = [
  { key: 'docs_ingest', label: 'Ingesting docs' },
  { key: 'humanize', label: 'NotebookLM humanise' },
  { key: 'editor_review', label: 'Editor review' },
  { key: 'book_compile_en', label: 'Compile EN PDF' },
  { key: 'translation', label: 'Translation' },
  { key: 'book_compile_uk', label: 'Compile UK PDF' },
  { key: 'done', label: 'Done' },
];

const CATEGORY_VARIANT: Record<string, 'amber' | 'rose' | 'cyan' | 'slate'> = {
  artifact_loss: 'rose',
  structural_drift: 'amber',
  fact_drift: 'rose',
  translation_hostile: 'cyan',
};

// ─── Sub-components ───────────────────────────────────────────────────────────

const StageStepper: React.FC<{ currentStage: string | null; running: boolean }> = ({
  currentStage,
  running,
}) => {
  const currentIdx = currentStage
    ? KNOWN_STAGES.findIndex((s) => s.key === currentStage)
    : -1;
  const isUnknown = currentStage && currentIdx === -1;

  return (
    <div className="space-y-2">
      <div className="flex items-center flex-wrap gap-1">
        {KNOWN_STAGES.map((stage, idx) => {
          const isDone = currentIdx > idx || currentStage === 'done';
          const isActive = currentStage === stage.key && running;
          const isPast = currentIdx > idx;

          return (
            <React.Fragment key={stage.key}>
              <div
                className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold border transition-all ${
                  isActive
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50 shadow-sm shadow-emerald-500/20 animate-pulse'
                    : isPast || (currentStage === 'done' && stage.key !== 'done')
                    ? 'bg-slate-800/60 text-slate-400 border-slate-700/40 line-through'
                    : stage.key === 'done' && currentStage === 'done'
                    ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/50'
                    : 'bg-[#090e1c] text-slate-500 border-slate-800'
                }`}
              >
                {(isPast && stage.key !== 'done') || (currentStage === 'done' && stage.key === 'done') ? (
                  <CheckCircle2 className="w-3 h-3 text-emerald-400 flex-shrink-0" />
                ) : isActive ? (
                  <Loader2 className="w-3 h-3 flex-shrink-0 animate-spin" />
                ) : null}
                {stage.label}
              </div>
              {idx < KNOWN_STAGES.length - 1 && (
                <ChevronRight className="w-3 h-3 text-slate-600 flex-shrink-0" />
              )}
            </React.Fragment>
          );
        })}
      </div>
      {isUnknown && (
        <div className="text-xs font-mono text-amber-400 px-1">
          Current stage: <span className="font-bold">{currentStage}</span>
        </div>
      )}
    </div>
  );
};

const LogPanel: React.FC<{ lines: string[] }> = ({ lines }) => {
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [lines]);

  if (lines.length === 0) {
    return (
      <div className="text-xs text-slate-500 font-mono px-1 py-3">
        No log output yet…
      </div>
    );
  }

  return (
    <pre className="p-3 rounded-xl bg-[#090e1c] border border-slate-800 text-xs font-mono text-emerald-400 max-h-52 overflow-y-auto leading-relaxed whitespace-pre-wrap">
      {lines.join('\n')}
      <div ref={endRef} />
    </pre>
  );
};

const FlagCard: React.FC<{
  flag: EditorFlag;
  onApply: (id: string) => Promise<void>;
  onDiscard: (id: string) => Promise<void>;
  processing: boolean;
}> = ({ flag, onApply, onDiscard, processing }) => {
  const catVariant = CATEGORY_VARIANT[flag.category] ?? 'slate';
  const isResolved = flag.resolution === 'applied' || flag.resolution === 'discarded';

  return (
    <div
      className={`p-4 rounded-xl border space-y-3 text-xs transition-all ${
        isResolved
          ? 'bg-[#090e1c]/60 border-slate-800/50 opacity-60'
          : 'bg-[#090e1c] border-slate-800'
      }`}
    >
      {/* Header row */}
      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant={catVariant} size="sm">
          {flag.category.replace(/_/g, ' ')}
        </Badge>
        <Badge variant="amber" size="sm">
          severity {flag.severity}
        </Badge>
        <Badge variant="slate" size="sm">
          {flag.detector}
        </Badge>
        <span className="text-slate-500 font-mono ml-auto">
          {flag.chapter} §{flag.para_index}
        </span>
      </div>

      {/* Issue */}
      <p className="text-slate-300 leading-relaxed">{flag.issue}</p>

      {/* Side-by-side excerpts */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        <div className="space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-slate-500 font-mono">
            Source
          </span>
          <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 text-slate-300 leading-relaxed">
            {flag.source_excerpt}
          </div>
        </div>
        <div className="space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-emerald-500 font-mono">
            Humanised
          </span>
          <div className="p-2 rounded-lg bg-slate-900/60 border border-slate-800 text-emerald-200 leading-relaxed">
            {flag.humanized_excerpt}
          </div>
        </div>
      </div>

      {/* Suggested rewrite */}
      {flag.suggested_rewrite && (
        <div className="space-y-1">
          <span className="text-[10px] uppercase tracking-wider text-cyan-500 font-mono">
            Suggested rewrite
          </span>
          <div className="p-2 rounded-lg bg-cyan-500/5 border border-cyan-500/20 text-cyan-200 leading-relaxed">
            {flag.suggested_rewrite}
          </div>
        </div>
      )}

      {/* Action buttons */}
      {!isResolved ? (
        <div className="flex items-center gap-2 pt-1">
          <Button
            variant="outline"
            size="sm"
            icon={<X className="w-3.5 h-3.5 text-red-400" />}
            isLoading={processing}
            onClick={() => onDiscard(flag.flag_id)}
            className="text-red-400 border-red-500/30 hover:bg-red-500/10"
          >
            Discard
          </Button>
          {flag.suggested_rewrite && (
            <Button
              variant="primary"
              size="sm"
              icon={<Check className="w-3.5 h-3.5" />}
              isLoading={processing}
              onClick={() => onApply(flag.flag_id)}
            >
              Apply
            </Button>
          )}
        </div>
      ) : (
        <div className="text-[10px] font-mono text-slate-500 uppercase tracking-wider">
          {flag.resolution === 'applied' ? '✓ Applied' : '✗ Discarded'}
        </div>
      )}
    </div>
  );
};

// ─── Create Form ──────────────────────────────────────────────────────────────

interface CreateFormProps {
  onCreated: (slug: string) => void;
}

const CreateForm: React.FC<CreateFormProps> = ({ onCreated }) => {
  const [repoUrl, setRepoUrl] = useState('');
  const [title, setTitle] = useState('');
  const [docsSubdir, setDocsSubdir] = useState('docs');
  const [notebookId, setNotebookId] = useState('');
  const [author, setAuthor] = useState('');
  const [sourceLang, setSourceLang] = useState('en');
  const [targetLang, setTargetLang] = useState('uk');
  const [enableEditor, setEnableEditor] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) {
      setError('Repository URL is required.');
      return;
    }
    setCreating(true);
    setError(null);
    try {
      const res = await apiFetch<{ status: string; slug?: string; message?: string }>(
        '/api/book-pipeline/create',
        {
          method: 'POST',
          body: JSON.stringify({
            repo_url: repoUrl.trim(),
            title: title.trim() || undefined,
            docs_subdir: docsSubdir.trim() || 'docs',
            notebook_id: notebookId.trim() || undefined,
            author: author.trim() || undefined,
            source_lang: sourceLang || 'en',
            target_lang: targetLang || 'uk',
            enable_book_editor: enableEditor,
          }),
        }
      );
      if (res.status === 'success' && res.slug) {
        onCreated(res.slug);
      } else {
        setError(res.message || 'Unknown error from server.');
      }
    } catch (err: any) {
      setError(err.message || 'Failed to create book pipeline.');
    } finally {
      setCreating(false);
    }
  };

  const inputCls =
    'w-full p-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 transition-colors';
  const labelCls = 'block text-xs font-semibold text-slate-300 mb-1';

  return (
    <Card className="bg-[#131c2e] border-slate-700/60 p-6 max-w-2xl mx-auto shadow-xl">
      <div className="flex items-center gap-3 mb-6 pb-4 border-b border-slate-800">
        <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center">
          <BookOpen className="w-5 h-5 text-emerald-400" />
        </div>
        <div>
          <h2 className="text-lg font-extrabold text-white">New Docs Book Pipeline</h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Clone a docs repo, humanise via NotebookLM, compile EN + UK PDFs
          </p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Repo URL (required) */}
        <div>
          <label className={labelCls}>
            Repository URL <span className="text-rose-400">*</span>
          </label>
          <input
            type="url"
            value={repoUrl}
            onChange={(e) => setRepoUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
            required
            className={inputCls}
          />
        </div>

        {/* Title */}
        <div>
          <label className={labelCls}>Book title (optional — inferred from repo if blank)</label>
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="My Awesome Book"
            className={inputCls}
          />
        </div>

        {/* Docs subdir + Author (2-col) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Docs subdirectory</label>
            <input
              type="text"
              value={docsSubdir}
              onChange={(e) => setDocsSubdir(e.target.value)}
              placeholder="docs"
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Author (optional)</label>
            <input
              type="text"
              value={author}
              onChange={(e) => setAuthor(e.target.value)}
              placeholder="Author Name"
              className={inputCls}
            />
          </div>
        </div>

        {/* Source lang + Target lang (2-col) */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className={labelCls}>Source language</label>
            <input
              type="text"
              value={sourceLang}
              onChange={(e) => setSourceLang(e.target.value)}
              placeholder="en"
              maxLength={10}
              className={inputCls}
            />
          </div>
          <div>
            <label className={labelCls}>Target language</label>
            <input
              type="text"
              value={targetLang}
              onChange={(e) => setTargetLang(e.target.value)}
              placeholder="uk"
              maxLength={10}
              className={inputCls}
            />
          </div>
        </div>

        {/* NotebookLM notebook ID */}
        <div>
          <label className={labelCls}>NotebookLM Notebook ID (optional)</label>
          <input
            type="text"
            value={notebookId}
            onChange={(e) => setNotebookId(e.target.value)}
            placeholder="notebook_xxxxxxxxxxxxxxxx"
            className={inputCls}
          />
        </div>

        {/* Enable editor checkbox */}
        <label className="flex items-center gap-3 cursor-pointer group">
          <div
            className={`w-5 h-5 rounded-md border-2 flex items-center justify-center transition-all ${
              enableEditor
                ? 'bg-emerald-500 border-emerald-500'
                : 'bg-[#090e1c] border-slate-600 group-hover:border-slate-400'
            }`}
            onClick={() => setEnableEditor((v) => !v)}
          >
            {enableEditor && <Check className="w-3 h-3 text-slate-950" />}
          </div>
          <input
            type="checkbox"
            className="sr-only"
            checked={enableEditor}
            onChange={(e) => setEnableEditor(e.target.checked)}
          />
          <span className="text-sm text-slate-300">
            Enable AI editor review pass (generates flags for humanised content)
          </span>
        </label>

        {error && (
          <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-rose-300 text-xs flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        <Button
          type="submit"
          variant="primary"
          size="md"
          isLoading={creating}
          icon={<BookOpen className="w-4 h-4" />}
          className="w-full mt-2"
        >
          Create Book Pipeline
        </Button>
      </form>
    </Card>
  );
};

// ─── Main View ────────────────────────────────────────────────────────────────

export const BookPipelineView: React.FC = () => {
  const { slug } = useParams<{ slug: string }>();
  const navigate = useNavigate();

  const isNewMode = !slug || slug === 'new';

  // Pipeline status state
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [running, setRunning] = useState(false);
  const [startingRun, setStartingRun] = useState(false);
  const [stoppingRun, setStoppingRun] = useState(false);

  // Flags state
  const [showFlags, setShowFlags] = useState(false);
  const [flags, setFlags] = useState<EditorFlag[]>([]);
  const [loadingFlags, setLoadingFlags] = useState(false);
  const [processingFlagId, setProcessingFlagId] = useState<string | null>(null);

  // ── Status polling ──────────────────────────────────────────────────────────

  const fetchStatus = async () => {
    if (!slug || slug === 'new') return;
    try {
      const res = await apiFetch<PipelineStatus>(`/api/book-pipeline/status/${slug}`);
      setStatus(res);
      setRunning(res.running);
    } catch (err) {
      console.error('Book pipeline status error:', err);
    }
  };

  useEffect(() => {
    if (isNewMode) return;
    fetchStatus();
    const interval = setInterval(fetchStatus, 4000);
    return () => clearInterval(interval);
  }, [slug]);

  // ── Flags fetch ─────────────────────────────────────────────────────────────

  const fetchFlags = async () => {
    if (!slug || slug === 'new') return;
    setLoadingFlags(true);
    try {
      const res = await apiFetch<EditorFlag[]>(`/api/book-pipeline/editor-flags/${slug}`);
      setFlags(Array.isArray(res) ? res : []);
    } catch (err) {
      console.error('Editor flags error:', err);
    } finally {
      setLoadingFlags(false);
    }
  };

  useEffect(() => {
    if (showFlags && !isNewMode) {
      fetchFlags();
    }
  }, [showFlags, slug]);

  // Also auto-show flags panel when flags_pending becomes > 0
  useEffect(() => {
    if (status && status.flags_pending > 0 && !showFlags) {
      setShowFlags(true);
    }
  }, [status?.flags_pending]);

  // ── Pipeline control ────────────────────────────────────────────────────────

  const handleRun = async () => {
    if (!slug) return;
    setStartingRun(true);
    try {
      await apiFetch(`/api/book-pipeline/run/${slug}`, {
        method: 'POST',
        body: JSON.stringify({}),
      });
      await fetchStatus();
    } catch (err: any) {
      alert(`Failed to start pipeline: ${err.message}`);
    } finally {
      setStartingRun(false);
    }
  };

  const handleStop = async () => {
    if (!slug) return;
    setStoppingRun(true);
    try {
      await apiFetch(`/api/book-pipeline/stop/${slug}`, { method: 'POST' });
      await fetchStatus();
    } catch (err: any) {
      alert(`Failed to stop pipeline: ${err.message}`);
    } finally {
      setStoppingRun(false);
    }
  };

  // ── Flag actions ────────────────────────────────────────────────────────────

  const handleApplyFlag = async (flagId: string) => {
    if (!slug) return;
    setProcessingFlagId(flagId);
    try {
      await apiFetch(`/api/book-pipeline/editor-flags/${slug}/${flagId}/apply`, {
        method: 'POST',
      });
      setFlags((prev) =>
        prev.map((f) => (f.flag_id === flagId ? { ...f, resolution: 'applied' } : f))
      );
      await fetchStatus();
    } catch (err: any) {
      alert(`Failed to apply flag: ${err.message}`);
    } finally {
      setProcessingFlagId(null);
    }
  };

  const handleDiscardFlag = async (flagId: string) => {
    if (!slug) return;
    setProcessingFlagId(flagId);
    try {
      await apiFetch(`/api/book-pipeline/editor-flags/${slug}/${flagId}/discard`, {
        method: 'POST',
      });
      setFlags((prev) =>
        prev.map((f) => (f.flag_id === flagId ? { ...f, resolution: 'discarded' } : f))
      );
      await fetchStatus();
    } catch (err: any) {
      alert(`Failed to discard flag: ${err.message}`);
    } finally {
      setProcessingFlagId(null);
    }
  };

  // ── Create handler ──────────────────────────────────────────────────────────

  const handleCreated = (newSlug: string) => {
    navigate(`/book-pipeline/${newSlug}`);
  };

  // ─── Render ────────────────────────────────────────────────────────────────

  if (isNewMode) {
    return (
      <div className="space-y-6 pb-12">
        {/* Header */}
        <div className="flex items-center gap-3 bg-[#131c2e] p-5 rounded-2xl border border-slate-700/60 shadow-xl">
          <Button
            variant="ghost"
            size="sm"
            icon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate('/modes')}
          >
            Back to modes
          </Button>
          <div>
            <h1 className="text-xl font-extrabold text-white flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-emerald-400" /> Docs Book Pipeline
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">
              Clone → humanise → review → compile EN/UK PDFs
            </p>
          </div>
        </div>

        <CreateForm onCreated={handleCreated} />
      </div>
    );
  }

  return (
    <div className="space-y-6 pb-12">
      {/* Navigation Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-[#131c2e] p-5 rounded-2xl border border-slate-700/60 shadow-xl">
        <div className="flex items-center gap-3">
          <Button
            variant="ghost"
            size="sm"
            icon={<ArrowLeft className="w-4 h-4" />}
            onClick={() => navigate('/modes')}
          >
            Back to modes
          </Button>
          <div>
            <h1 className="text-xl font-extrabold text-white flex items-center gap-2">
              <BookOpen className="w-5 h-5 text-emerald-400" /> Docs Book Pipeline:{' '}
              <span className="font-mono text-emerald-300">{slug}</span>
            </h1>
            <p className="text-xs text-slate-400 mt-0.5">
              {status?.running
                ? `Running — stage: ${status.stage ?? 'starting…'}`
                : status?.stage === 'done'
                ? 'Pipeline complete'
                : status
                ? 'Idle'
                : 'Loading…'}
            </p>
          </div>
        </div>

        {/* Run / Stop control */}
        <div className="flex items-center gap-3">
          <Badge variant={running ? 'emerald' : 'slate'} size="md">
            {running ? '⚡ Running' : 'Idle'}
          </Badge>

          {running ? (
            <Button
              variant="outline"
              size="md"
              icon={<Square className="w-4 h-4 text-red-400" />}
              isLoading={stoppingRun}
              onClick={handleStop}
              className="text-red-400 border-red-500/40 hover:bg-red-500/10"
            >
              Stop
            </Button>
          ) : (
            <Button
              variant="primary"
              size="md"
              icon={<Play className="w-4 h-4" />}
              isLoading={startingRun}
              onClick={handleRun}
            >
              Run Pipeline
            </Button>
          )}
        </div>
      </div>

      {/* Stage stepper + log */}
      <Card className="bg-[#131c2e] border-slate-700/60 p-6 space-y-5 shadow-xl">
        <div className="space-y-2 pb-4 border-b border-slate-800">
          <h3 className="text-sm font-bold text-slate-300 uppercase tracking-wider font-mono">
            Pipeline stages
          </h3>
          <StageStepper
            currentStage={status?.stage ?? null}
            running={status?.running ?? false}
          />
        </div>

        <div className="space-y-2">
          <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider font-mono">
            Log (last 30 lines)
          </h3>
          <LogPanel lines={status?.log ?? []} />
        </div>
      </Card>

      {/* Editor flags panel */}
      {((status?.flags_pending ?? 0) > 0 || showFlags) && (
        <Card className="bg-[#131c2e] border-amber-500/30 p-6 space-y-5 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div className="flex items-center gap-2.5">
              <AlertTriangle className="w-5 h-5 text-amber-400" />
              <h3 className="font-extrabold text-lg text-white">Editor Review Flags</h3>
              {(status?.flags_pending ?? 0) > 0 && (
                <Badge variant="amber" size="md">
                  {status!.flags_pending} pending
                </Badge>
              )}
            </div>
            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                isLoading={loadingFlags}
                onClick={fetchFlags}
              >
                Refresh
              </Button>
              <Button
                variant="ghost"
                size="sm"
                icon={<X className="w-4 h-4" />}
                onClick={() => setShowFlags(false)}
              >
                Hide
              </Button>
            </div>
          </div>

          {loadingFlags && flags.length === 0 ? (
            <div className="flex items-center gap-2 text-sm text-slate-400 py-4">
              <Loader2 className="w-4 h-4 animate-spin" />
              Loading flags…
            </div>
          ) : flags.length === 0 ? (
            <div className="text-sm text-slate-500 py-4">
              No editor flags found for this book.
            </div>
          ) : (
            <div className="space-y-3 max-h-[600px] overflow-y-auto pr-1">
              {flags.map((flag) => (
                <FlagCard
                  key={flag.flag_id}
                  flag={flag}
                  onApply={handleApplyFlag}
                  onDiscard={handleDiscardFlag}
                  processing={processingFlagId === flag.flag_id}
                />
              ))}
            </div>
          )}
        </Card>
      )}

      {/* Show flags toggle when no pending but user might want to review */}
      {!showFlags && (status?.flags_pending ?? 0) === 0 && status !== null && (
        <div className="flex justify-center">
          <Button
            variant="ghost"
            size="sm"
            icon={<AlertTriangle className="w-4 h-4 text-amber-400" />}
            onClick={() => setShowFlags(true)}
            className="text-amber-400 hover:text-amber-300"
          >
            Show editor flags
          </Button>
        </div>
      )}
    </div>
  );
};
