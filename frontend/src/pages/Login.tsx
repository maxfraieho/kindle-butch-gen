import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { Button } from '../components/ui/Button';
import { Card } from '../components/ui/Card';
import { KeyRound, User, AlertCircle, Sparkles } from 'lucide-react';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const { login } = useAuth();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);

    try {
      await login(username, password);
      navigate('/');
    } catch (err: any) {
      setError(err.message || 'Невірний логін або пароль');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#080d1a] flex items-center justify-center p-4 selection:bg-emerald-500 selection:text-slate-950">
      <div className="w-full max-w-md">
        {/* Branding Header */}
        <div className="text-center space-y-3 mb-8">
          <div className="relative inline-block">
            <div className="absolute -inset-1 rounded-full bg-gradient-to-r from-emerald-500 to-teal-500 blur-md opacity-40 animate-pulse" />
            <div className="relative p-3.5 rounded-2xl bg-[#131c2e] border border-slate-700/60 shadow-xl">
              <img src="/static/vydra-sm.png" alt="Vydra" className="w-16 h-16 object-contain rounded-xl" />
            </div>
          </div>

          <div>
            <h1 className="text-3xl font-extrabold tracking-tight text-white flex items-center justify-center gap-2">
              Vydra Studio <Sparkles className="w-5 h-5 text-emerald-400" />
            </h1>
            <p className="text-sm text-slate-300 mt-1">
              Локальна платформа перекладу книг та синтезу мовлення
            </p>
          </div>
        </div>

        {/* Form Card */}
        <Card className="bg-[#131c2e] border border-slate-700/60 p-6 md:p-8 space-y-6 shadow-2xl">
          {error && (
            <div className="p-3.5 rounded-xl bg-rose-500/15 border border-rose-500/30 text-rose-300 text-sm flex items-center gap-2.5">
              <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-400" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Логін
              </label>
              <div className="flex items-center rounded-xl bg-[#090e1c] border border-slate-700/80 focus-within:border-emerald-400 focus-within:ring-1 focus-within:ring-emerald-400 transition-colors">
                <span className="pl-3.5 flex items-center pointer-events-none">
                  <User className="w-4 h-4 text-emerald-400" />
                </span>
                <input
                  type="text"
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  placeholder="Введіть логін"
                  required
                  className="flex-1 pl-2.5 pr-4 py-3 bg-transparent text-white placeholder-slate-500 focus:outline-none text-sm font-medium"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Пароль
              </label>
              <div className="flex items-center rounded-xl bg-[#090e1c] border border-slate-700/80 focus-within:border-emerald-400 focus-within:ring-1 focus-within:ring-emerald-400 transition-colors">
                <span className="pl-3.5 flex items-center pointer-events-none">
                  <KeyRound className="w-4 h-4 text-emerald-400" />
                </span>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Введіть пароль"
                  required
                  className="flex-1 pl-2.5 pr-4 py-3 bg-transparent text-white placeholder-slate-500 focus:outline-none text-sm font-medium"
                />
              </div>
            </div>

            <Button
              type="submit"
              variant="primary"
              size="lg"
              isLoading={loading}
              className="w-full mt-2 font-bold tracking-wide shadow-lg shadow-emerald-950/40"
            >
              Увійти в систему
            </Button>
          </form>
        </Card>

        <p className="text-center text-xs text-slate-400 font-mono mt-8">
          Vydra self-hosted • Termux & Linux Ready
        </p>
      </div>
    </div>
  );
};
