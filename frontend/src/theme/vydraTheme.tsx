import React from 'react';

export interface ThemeTokens {
  colorBgBase: string;
  colorBgSurface: string;
  colorBgCard: string;
  colorBorderDefault: string;
  colorPrimary: string;
  colorSecondary: string;
  colorWarning: string;
  colorDanger: string;
  fontFamilyBody: string;
  fontFamilyHeading: string;
  fontFamilyCode: string;
  radiusContainer: string;
  radiusElement: string;
  radiusInner: string;
}

export interface AstryxTheme {
  name: string;
  tokens: ThemeTokens;
}

export function defineTheme(config: { name: string; tokens: ThemeTokens }): AstryxTheme {
  return config;
}

export const vydraTheme = defineTheme({
  name: 'vydra-emerald-slate',
  tokens: {
    colorBgBase: '#090d16',
    colorBgSurface: '#111827',
    colorBgCard: '#161e31',
    colorBorderDefault: 'rgba(255, 255, 255, 0.08)',
    colorPrimary: '#10b981',
    colorSecondary: '#06b6d4',
    colorWarning: '#f59e0b',
    colorDanger: '#ef4444',
    fontFamilyBody: "'Plus Jakarta Sans', system-ui, sans-serif",
    fontFamilyHeading: "'Outfit', system-ui, sans-serif",
    fontFamilyCode: "'JetBrains Mono', monospace",
    radiusContainer: '18px',
    radiusElement: '10px',
    radiusInner: '8px',
  },
});

export const Theme: React.FC<{ theme: AstryxTheme; mode?: 'dark' | 'light' | 'system'; children: React.ReactNode }> = ({ children }) => {
  return <div className="dark bg-[#090d16] min-h-screen text-slate-100">{children}</div>;
};
