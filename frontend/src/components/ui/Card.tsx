import React from 'react';

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  glass?: boolean;
  hoverable?: boolean;
}

export const Card: React.FC<CardProps> = ({
  children,
  glass = true,
  hoverable = false,
  className = '',
  ...props
}) => {
  const baseStyles = 'rounded-[18px] transition-all duration-200 border border-[rgba(255,255,255,0.08)] shadow-[0_4px_12px_rgba(0,0,0,0.5)]';
  const glassStyles = glass ? 'bg-[#111827]/80 backdrop-blur-md' : 'bg-[#111827]';
  const hoverStyles = hoverable ? 'hover:border-[rgba(16,185,129,0.3)] hover:shadow-[0_8px_24px_rgba(0,0,0,0.6)] hover:-translate-y-0.5 cursor-pointer active-scale' : '';

  return (
    <div className={`${baseStyles} ${glassStyles} ${hoverStyles} ${className}`} {...props}>
      {children}
    </div>
  );
};
