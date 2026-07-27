import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'emerald' | 'amber' | 'cyan' | 'rose' | 'slate';
  size?: 'sm' | 'md';
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'emerald',
  size = 'md',
}) => {
  const variantStyles = {
    emerald: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30 shadow-[0_0_8px_rgba(16,185,129,0.15)]',
    amber: 'bg-amber-500/15 text-amber-300 border-amber-500/30 shadow-[0_0_8px_rgba(245,158,11,0.15)]',
    cyan: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.15)]',
    rose: 'bg-rose-500/15 text-rose-300 border-rose-500/30 shadow-[0_0_8px_rgba(239,68,68,0.15)]',
    slate: 'bg-slate-800/60 text-slate-300 border-slate-700/50',
  };

  const sizeStyles = {
    sm: 'text-[10px] px-2 py-0.5 font-medium',
    md: 'text-xs px-2.5 py-1 font-semibold',
  };

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border tracking-wide uppercase font-mono ${variantStyles[variant]} ${sizeStyles[size]}`}
    >
      {children}
    </span>
  );
};
