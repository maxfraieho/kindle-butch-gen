import React from 'react';

interface NavbarProps {
  currentPage?: 'index' | 'install' | 'install_x86' | 'legal' | 'privacy';
}

export const Navbar: React.FC<NavbarProps> = ({ currentPage }) => {
  return (
    <header className="sticky top-0 z-50 bg-[#090d16]/80 backdrop-blur-md border-b border-white/10">
      <div className="max-w-4xl mx-auto px-4 py-3 flex items-center justify-between">
        <a href="index.html" className="flex items-center gap-2.5 group">
          <img
            src="vydra.jpg"
            alt="Vydra Logo"
            className="w-9 h-9 rounded-full border border-emerald-500/40 group-hover:scale-105 transition-transform"
          />
          <span className="font-extrabold text-lg text-white tracking-tight flex items-center gap-1.5">
            <span>🦦</span> Vydra
          </span>
        </a>

        <nav className="flex items-center gap-2 sm:gap-4 text-xs font-semibold">
          <a
            href="index.html"
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              currentPage === 'index'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            Про проєкт
          </a>
          <a
            href="install.html"
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              currentPage === 'install'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            📲 Android
          </a>
          <a
            href="install_x86.html"
            className={`px-3 py-1.5 rounded-lg transition-colors ${
              currentPage === 'install_x86'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            💻 x86 / WSL2
          </a>
        </nav>
      </div>
    </header>
  );
};
