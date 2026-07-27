import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { BookOpen, Download, Settings, SlidersHorizontal, LogOut, User } from 'lucide-react';
import { useAuth } from '../../context/AuthContext';

export interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();

  const navItems = [
    { label: 'Книги', path: '/', icon: <BookOpen className="w-5 h-5" /> },
    { label: 'Завантаження', path: '/downloads', icon: <Download className="w-5 h-5" /> },
    { label: 'Режими', path: '/modes', icon: <SlidersHorizontal className="w-5 h-5" /> },
    { label: 'Налаштування', path: '/settings', icon: <Settings className="w-5 h-5" /> },
  ];

  return (
    <div className="min-h-screen bg-[#090d16] text-slate-100 flex flex-col md:flex-row">
      {/* Desktop Sidebar (>= 768px) */}
      <aside className="hidden md:flex flex-col w-64 border-r border-slate-800/60 bg-[#111827]/90 backdrop-blur-xl p-5 justify-between sticky top-0 h-screen">
        <div className="space-y-6">
          {/* Logo */}
          <div className="flex items-center gap-3 px-2 cursor-pointer" onClick={() => navigate('/')}>
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-950/50 p-0.5">
              <img src="/static/vydra-sm.png" alt="Vydra" className="w-full h-full object-contain rounded-lg" />
            </div>
            <div>
              <h1 className="font-extrabold text-xl tracking-tight bg-gradient-to-r from-emerald-400 via-teal-300 to-cyan-400 bg-clip-text text-transparent">
                Vydra
              </h1>
              <p className="text-[10px] text-slate-400 font-mono tracking-wider uppercase">Studio v2.0</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-1.5 pt-4">
            {navItems.map((item) => {
              const active = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={`w-full flex items-center gap-3 px-3.5 py-3 rounded-xl text-sm font-medium transition-all duration-150 active-scale ${
                    active
                      ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-[0_0_12px_rgba(16,185,129,0.15)] font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
                  }`}
                >
                  <span className={active ? 'text-emerald-400' : 'text-slate-400'}>{item.icon}</span>
                  {item.label}
                </button>
              );
            })}
          </nav>
        </div>

        {/* User Info & Logout */}
        <div className="pt-4 border-t border-slate-800/60 space-y-3">
          {user && (
            <div className="flex items-center justify-between px-2 text-xs">
              <div className="flex items-center gap-2 text-slate-300">
                <User className="w-4 h-4 text-emerald-400" />
                <span className="font-mono">{user}</span>
              </div>
              <button
                onClick={logout}
                title="Вийти"
                className="text-slate-400 hover:text-rose-400 p-1.5 rounded-lg hover:bg-slate-800 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 pb-20 md:pb-0">
        {/* Mobile Header (< 768px) */}
        <header className="flex md:hidden items-center justify-between px-4 py-3 bg-[#111827]/90 backdrop-blur-md border-b border-slate-800/60 sticky top-0 z-30">
          <div className="flex items-center gap-2.5" onClick={() => navigate('/')}>
            <img src="/static/vydra-sm.png" alt="Vydra" className="w-8 h-8 rounded-lg" />
            <span className="font-bold text-lg text-emerald-400 tracking-tight">Vydra</span>
          </div>
          {user && (
            <button
              onClick={logout}
              className="p-2 text-slate-400 hover:text-rose-400 rounded-lg"
            >
              <LogOut className="w-5 h-5" />
            </button>
          )}
        </header>

        {/* Content Body */}
        <main className="flex-1 p-4 md:p-8 max-w-7xl mx-auto w-full">
          {children}
        </main>

        {/* Mobile Floating Bottom Dock (< 768px) */}
        <div className="fixed bottom-3 left-3 right-3 md:hidden z-40">
          <nav className="glass-panel rounded-2xl p-1.5 flex items-center justify-around shadow-2xl border border-slate-700/50">
            {navItems.map((item) => {
              const active = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={`flex flex-col items-center gap-1 p-2 rounded-xl text-[11px] font-medium transition-all active-scale ${
                    active ? 'text-emerald-400 bg-emerald-500/10 font-semibold' : 'text-slate-400'
                  }`}
                >
                  {item.icon}
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </div>
    </div>
  );
};
