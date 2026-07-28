import React from 'react';
import { Smartphone, Monitor, Info } from 'lucide-react';

interface NavbarProps {
  currentPage?: 'index' | 'install' | 'install_x86' | 'legal' | 'privacy';
}

export const Navbar: React.FC<NavbarProps> = ({ currentPage }) => {
  return (
    <header className="sticky top-0 z-50 bg-[#090d16]/90 backdrop-blur-md border-b border-white/10">
      <div className="max-w-4xl mx-auto px-3 sm:px-4 py-2.5 flex items-center justify-between gap-2 overflow-x-auto no-scrollbar">
        {/* Brand Logo */}
        <a href="index.html" className="flex items-center gap-2 group shrink-0">
          <img
            src="vydra.jpg"
            alt="Vydra Logo"
            className="w-8 h-8 rounded-full border border-emerald-500/40 group-hover:scale-105 transition-transform"
          />
          <span className="font-extrabold text-base text-white tracking-tight">
            Vydra
          </span>
        </a>

        {/* Navigation Links */}
        <nav className="flex items-center gap-1.5 sm:gap-3 text-xs font-semibold shrink-0">
          <a
            href="index.html"
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
              currentPage === 'index'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <Info className="w-3.5 h-3.5 hidden sm:inline-block" />
            <span>Про проєкт</span>
          </a>

          <a
            href="install.html"
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
              currentPage === 'install'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <Smartphone className="w-3.5 h-3.5" />
            <span>Android</span>
          </a>

          <a
            href="install_x86.html"
            className={`inline-flex items-center gap-1 px-2.5 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
              currentPage === 'install_x86'
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30'
                : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
            }`}
          >
            <Monitor className="w-3.5 h-3.5" />
            <span>x86 / WSL2</span>
          </a>
        </nav>
      </div>
    </header>
  );
};
