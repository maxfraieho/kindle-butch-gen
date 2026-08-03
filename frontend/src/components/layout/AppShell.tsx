import React from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { BookOpen, Download, Settings, LogOut, User, Sparkles } from 'lucide-react';
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
    { label: 'Налаштування', path: '/settings', icon: <Settings className="w-5 h-5" /> },
  ];

  return (
    <div className="min-h-screen bg-[#080d1a] text-slate-100 flex flex-col md:flex-row">
      {/* Desktop Sidebar (>= 768px) */}
      <aside className="hidden md:flex flex-col w-64 border-r border-slate-800/80 bg-[#0f172a] p-6 justify-between sticky top-0 h-screen">
        <div className="space-y-8">
          {/* Logo */}
          <div className="flex items-center gap-3 px-2 cursor-pointer" onClick={() => navigate('/')}>
            <div className="w-11 h-11 rounded-2xl bg-gradient-to-br from-emerald-400 to-teal-600 flex items-center justify-center shadow-lg shadow-emerald-950/50 p-0.5">
              <img src="/static/vydra-sm.png" alt="Vydra" className="w-full h-full object-contain rounded-xl" />
            </div>
            <div>
              <h1 className="font-extrabold text-xl tracking-tight text-white flex items-center gap-1.5">
                Vydra <Sparkles className="w-4 h-4 text-emerald-400" />
              </h1>
              <p className="text-[10px] text-emerald-400 font-mono tracking-wider uppercase font-bold">Studio v2.0</p>
            </div>
          </div>

          {/* Navigation Links */}
          <nav className="space-y-2 pt-2">
            {navItems.map((item) => {
              const active = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={`w-full flex items-center gap-3 px-4 py-3.5 rounded-2xl text-sm font-semibold transition-all duration-150 active-scale ${
                    active
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-lg shadow-emerald-950/20 font-bold'
                      : 'text-slate-300 hover:text-white hover:bg-slate-800/60'
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
        <div className="pt-5 border-t border-slate-800/80 space-y-3">
          {user && (
            <div className="flex items-center justify-between px-2 text-xs">
              <div className="flex items-center gap-2 text-slate-200">
                <User className="w-4 h-4 text-emerald-400" />
                <span className="font-mono font-bold">{user}</span>
              </div>
              <button
                onClick={logout}
                title="Вийти"
                className="text-slate-400 hover:text-rose-400 p-2 rounded-xl hover:bg-slate-800 transition-colors"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 pb-36 md:pb-8">
        {/* Mobile Header (< 768px) */}
        <header className="flex md:hidden items-center justify-between px-5 py-4 bg-[#0f172a] border-b border-slate-800/80 sticky top-0 z-30 shadow-md">
          <div className="flex items-center gap-3" onClick={() => navigate('/')}>
            <img src="/static/vydra-sm.png" alt="Vydra" className="w-9 h-9 rounded-xl" />
            <span className="font-extrabold text-lg text-white tracking-tight">Vydra Studio</span>
          </div>
          {user && (
            <div className="flex items-center gap-3">
              <span className="text-xs text-slate-300 font-mono font-bold flex items-center gap-1.5 bg-slate-800/80 px-3 py-1.5 rounded-xl border border-slate-700/60">
                <User className="w-3.5 h-3.5 text-emerald-400" /> {user}
              </span>
              <button
                onClick={logout}
                className="p-2 text-slate-400 hover:text-rose-400 rounded-xl hover:bg-slate-800"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </header>

        {/* Content Body */}
        <main className="flex-1 p-4 sm:p-6 md:p-8 max-w-7xl mx-auto w-full space-y-6 md:space-y-8">
          {children}
        </main>

        {/* Mobile Floating Bottom Dock (< 768px) */}
        <div className="fixed bottom-3 left-3 right-3 md:hidden z-40">
          <nav className="bg-[#131c2e]/95 backdrop-blur-xl border border-slate-700/80 rounded-2xl p-1.5 flex items-center justify-between gap-1 shadow-2xl">
            {navItems.map((item) => {
              const active = location.pathname === item.path;
              return (
                <button
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  className={`flex-1 min-w-0 flex flex-col items-center justify-center gap-0.5 px-1 py-1.5 min-h-[48px] rounded-xl text-[11px] transition-all active-scale ${
                    active
                      ? 'text-emerald-300 bg-emerald-500/20 font-bold border border-emerald-500/40 shadow-md shadow-emerald-950/30'
                      : 'text-slate-300 hover:text-white'
                  }`}
                >
                  {React.cloneElement(item.icon, { className: active ? 'w-4 h-4 text-emerald-400' : 'w-4 h-4 text-slate-400' })}
                  <span className="truncate w-full text-center">{item.label}</span>
                </button>
              );
            })}
          </nav>
        </div>
      </div>
    </div>
  );
};

