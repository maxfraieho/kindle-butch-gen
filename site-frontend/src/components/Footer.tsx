import React from 'react';

export const Footer: React.FC = () => {
  return (
    <footer className="mt-16 border-t border-white/10 py-8 bg-[#090d16]/60">
      <div className="max-w-4xl mx-auto px-4 text-center space-y-3 text-xs text-slate-400">
        <div className="flex flex-wrap justify-center items-center gap-4">
          <a
            href="https://github.com/maxfraieho/kindle-butch-gen"
            target="_blank"
            rel="noreferrer"
            className="hover:text-emerald-400 transition-colors"
          >
            GitHub: github.com/maxfraieho/kindle-butch-gen
          </a>
          <span>•</span>
          <a href="legal.html" className="hover:text-emerald-400 transition-colors">
            Правові застереження
          </a>
          <span>•</span>
          <a href="privacy.html" className="hover:text-emerald-400 transition-colors">
            Політика приватності
          </a>
          <span>•</span>
          <a
            href="https://t.me/GetVydraBot"
            target="_blank"
            rel="noreferrer"
            className="hover:text-emerald-400 transition-colors"
          >
            Telegram: @GetVydraBot
          </a>
        </div>
        <p className="text-slate-500">
          Vydra — відкритий інструмент для локального перекладу книг, генерування аудіокниг та адаптації манґи.
        </p>
      </div>
    </footer>
  );
};
