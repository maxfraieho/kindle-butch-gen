import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
  size?: 'sm' | 'md' | 'lg';
  icon?: React.ReactNode;
  isLoading?: boolean;
}

export const Button: React.FC<ButtonProps> = ({
  children,
  variant = 'primary',
  size = 'md',
  icon,
  isLoading = false,
  className = '',
  disabled,
  ...props
}) => {
  const baseStyles = 'inline-flex items-center justify-center font-medium rounded-[10px] active-scale transition-all duration-150 focus:outline-none min-touch-target cursor-pointer select-none';
  
  const variantStyles = {
    primary: 'bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-semibold shadow-md shadow-emerald-900/20 border border-emerald-400/30',
    secondary: 'bg-cyan-500 hover:bg-cyan-600 text-slate-950 font-semibold shadow-md shadow-cyan-900/20',
    outline: 'bg-slate-900/60 hover:bg-slate-800 text-slate-200 border border-slate-700/60 hover:border-slate-500',
    ghost: 'bg-transparent hover:bg-slate-800/60 text-slate-300 hover:text-white',
    danger: 'bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/30',
  };

  const sizeStyles = {
    sm: 'text-xs px-3 py-1.5 gap-1.5 min-h-[36px]',
    md: 'text-sm px-4 py-2.5 gap-2 min-h-[44px]',
    lg: 'text-base px-6 py-3.5 gap-2.5 min-h-[50px]',
  };

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${disabled || isLoading ? 'opacity-50 pointer-events-none' : ''} ${className}`}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading ? (
        <span className="inline-block w-4 h-4 border-2 border-current border-r-transparent rounded-full animate-spin" />
      ) : icon ? (
        <span className="flex-shrink-0">{icon}</span>
      ) : null}
      {children}
    </button>
  );
};
