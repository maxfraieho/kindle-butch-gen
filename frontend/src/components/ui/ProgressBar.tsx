import React from 'react';

export interface ProgressBarProps {
  progress: number; // 0 to 100
  label?: string;
  statusText?: string;
  showPercent?: boolean;
}

export const ProgressBar: React.FC<ProgressBarProps> = ({
  progress,
  label,
  statusText,
  showPercent = true,
}) => {
  const clampedProgress = Math.min(100, Math.max(0, Math.round(progress)));

  return (
    <div className="w-full space-y-1.5">
      {(label || showPercent) && (
        <div className="flex justify-between items-center text-xs font-medium text-slate-300">
          <span>{label}</span>
          {showPercent && (
            <span className="tabular-nums text-emerald-400 font-mono font-semibold">
              {clampedProgress}%
            </span>
          )}
        </div>
      )}
      <div className="w-full h-2.5 bg-slate-950/80 rounded-full overflow-hidden p-0.5 border border-slate-800/60 shadow-inner">
        <div
          className="h-full bg-gradient-to-r from-emerald-500 via-teal-400 to-cyan-400 rounded-full transition-all duration-300 ease-out shadow-[0_0_12px_rgba(16,185,129,0.5)]"
          style={{ width: `${clampedProgress}%` }}
        />
      </div>
      {statusText && (
        <div className="text-[11px] text-slate-400 truncate font-mono">
          {statusText}
        </div>
      )}
    </div>
  );
};
