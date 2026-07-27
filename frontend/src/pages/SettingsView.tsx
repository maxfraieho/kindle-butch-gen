import React, { useState, useEffect } from 'react';
import { apiFetch } from '../api/client';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { Cpu, Server, Lock, Folder, Play, Square, Save, CheckCircle, AlertCircle, RefreshCw, KeyRound } from 'lucide-react';

interface ModelsInfo {
  translation_model: string;
  available_models: string[];
  server_status: {
    running: boolean;
    loaded_model?: string;
  };
}

export const SettingsView: React.FC = () => {
  // Llama-server State
  const [modelsInfo, setModelsInfo] = useState<ModelsInfo | null>(null);
  const [selectedModel, setSelectedModel] = useState<string>('');
  const [modelLoading, setModelLoading] = useState(true);
  const [startingServer, setStartingServer] = useState(false);
  const [stoppingServer, setStoppingServer] = useState(false);

  // Output Path State
  const [outputRoot, setOutputRoot] = useState<string>('');
  const [savingOutputRoot, setSavingOutputRoot] = useState(false);

  // Password State
  const [oldPassword, setOldPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordMsg, setPasswordMsg] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const fetchModelsInfo = async () => {
    try {
      const data = await apiFetch<ModelsInfo>('/api/models');
      setModelsInfo(data);
      if (data.translation_model) {
        setSelectedModel(data.translation_model);
      }
    } catch (err) {
      console.error('Помилка завантаження інформації про моделі:', err);
    } finally {
      setModelLoading(false);
    }
  };

  useEffect(() => {
    fetchModelsInfo();
    const interval = setInterval(fetchModelsInfo, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSaveModel = async () => {
    try {
      await apiFetch('/api/models/configure', {
        method: 'POST',
        body: JSON.stringify({ translation_model: selectedModel }),
      });
      alert('Модель успішно збережено!');
      fetchModelsInfo();
    } catch (err: any) {
      alert(`Помилка збереження: ${err.message}`);
    }
  };

  const handleStartServer = async () => {
    setStartingServer(true);
    try {
      await apiFetch('/api/models/start', { method: 'POST' });
      await fetchModelsInfo();
    } catch (err: any) {
      alert(`Помилка запуску сервера: ${err.message}`);
    } finally {
      setStartingServer(false);
    }
  };

  const handleStopServer = async () => {
    setStoppingServer(true);
    try {
      await apiFetch('/api/models/stop', { method: 'POST' });
      await fetchModelsInfo();
    } catch (err: any) {
      alert(`Помилка зупинки сервера: ${err.message}`);
    } finally {
      setStoppingServer(false);
    }
  };

  const handleSaveOutputRoot = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingOutputRoot(true);
    try {
      await apiFetch('/api/settings/output-root', {
        method: 'POST',
        body: JSON.stringify({ output_root: outputRoot }),
      });
      alert('Шлях збереження оновлено!');
    } catch (err: any) {
      alert(`Помилка збереження: ${err.message}`);
    } finally {
      setSavingOutputRoot(false);
    }
  };

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordMsg(null);

    if (newPassword !== confirmPassword) {
      setPasswordMsg({ type: 'error', text: 'Новий пароль та підтвердження не збігаються' });
      return;
    }

    setPasswordLoading(true);
    try {
      await apiFetch('/api/change-password', {
        method: 'POST',
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      });
      setPasswordMsg({ type: 'success', text: 'Пароль успішно змінено!' });
      setOldPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: any) {
      setPasswordMsg({ type: 'error', text: err.message || 'Помилка зміни пароля' });
    } finally {
      setPasswordLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="bg-[#131c2e] p-6 rounded-2xl border border-slate-700/60 shadow-xl flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <Server className="w-7 h-7 text-emerald-400" /> Глобальні налаштування
          </h1>
          <p className="text-sm text-slate-300 mt-1">
            Керування локальним сервером перекладу Llama, шляхами файлів та безпекою
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          icon={<RefreshCw className={`w-4 h-4 ${modelLoading ? 'animate-spin' : ''}`} />}
          onClick={fetchModelsInfo}
        >
          Оновити
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Llama Server Model Card */}
        <Card className="bg-[#131c2e] border border-slate-700/60 p-6 space-y-5 md:col-span-2 shadow-xl">
          <div className="flex items-center justify-between border-b border-slate-800 pb-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center border border-emerald-500/30">
                <Cpu className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-extrabold text-lg text-white">Локальний сервер перекладу (Llama-Server)</h3>
                <p className="text-xs text-slate-400 font-mono">Port 8081 • Hy-MT2 / Qwen GGUF Models</p>
              </div>
            </div>

            <Badge variant={modelsInfo?.server_status.running ? 'emerald' : 'slate'}>
              {modelsInfo?.server_status.running ? 'Сервер працює' : 'Зупинено'}
            </Badge>
          </div>

          <div className="space-y-4">
            {/* Active Model Status */}
            {modelsInfo?.server_status.running && (
              <div className="p-3.5 rounded-xl bg-emerald-500/10 border border-emerald-500/30 text-emerald-300 text-xs font-mono flex items-center justify-between">
                <span className="truncate">Завантажена модель: <b>{modelsInfo.server_status.loaded_model || 'Hy-MT2-7B'}</b></span>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
              </div>
            )}

            {/* Model Selection Dropdown */}
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Вибір файлу GGUF моделі
              </label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full px-4 py-3 rounded-xl bg-[#090e1c] border border-slate-700 text-white focus:outline-none focus:border-emerald-400 text-xs font-mono"
              >
                {modelsInfo?.available_models.map((m) => (
                  <option key={m} value={m}>
                    {m.split('/').pop()} ({m})
                  </option>
                ))}
                {(!modelsInfo?.available_models || modelsInfo.available_models.length === 0) && (
                  <option value={modelsInfo?.translation_model}>
                    {modelsInfo?.translation_model.split('/').pop()} (За замовчуванням)
                  </option>
                )}
              </select>
            </div>

            {/* Server Controls */}
            <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
              <Button
                variant="outline"
                size="sm"
                icon={<Save className="w-4 h-4" />}
                onClick={handleSaveModel}
              >
                Зберегти вибір моделі
              </Button>

              <div className="flex items-center gap-3">
                {modelsInfo?.server_status.running ? (
                  <Button
                    variant="danger"
                    size="sm"
                    isLoading={stoppingServer}
                    icon={<Square className="w-4 h-4 fill-current" />}
                    onClick={handleStopServer}
                  >
                    Зупинити Llama-Server
                  </Button>
                ) : (
                  <Button
                    variant="primary"
                    size="sm"
                    isLoading={startingServer}
                    icon={<Play className="w-4 h-4 fill-current" />}
                    onClick={handleStartServer}
                  >
                    Запустити Llama-Server
                  </Button>
                )}
              </div>
            </div>
          </div>
        </Card>

        {/* Output Directory Card */}
        <Card className="bg-[#131c2e] border border-slate-700/60 p-6 space-y-5 shadow-xl">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
            <div className="w-10 h-10 rounded-xl bg-cyan-500/20 text-cyan-400 flex items-center justify-center border border-cyan-500/30">
              <Folder className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-extrabold text-lg text-white">Каталог зберігання</h3>
              <p className="text-xs text-slate-400 font-mono">Шлях для експорту книги</p>
            </div>
          </div>

          <form onSubmit={handleSaveOutputRoot} className="space-y-4">
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Системний шлях (Output Root)
              </label>
              <input
                type="text"
                value={outputRoot}
                onChange={(e) => setOutputRoot(e.target.value)}
                placeholder="/sdcard/Documents/VydraBooks"
                className="w-full px-4 py-3 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs font-mono"
              />
            </div>

            <Button
              type="submit"
              variant="outline"
              size="sm"
              isLoading={savingOutputRoot}
              icon={<CheckCircle className="w-4 h-4" />}
            >
              Зберегти шлях
            </Button>
          </form>
        </Card>

        {/* Change Password Card */}
        <Card className="bg-[#131c2e] border border-slate-700/60 p-6 space-y-5 shadow-xl">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
            <div className="w-10 h-10 rounded-xl bg-rose-500/20 text-rose-400 flex items-center justify-center border border-rose-500/30">
              <Lock className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-extrabold text-lg text-white">Безпека</h3>
              <p className="text-xs text-slate-400 font-mono">Зміна пароля доступу</p>
            </div>
          </div>

          {passwordMsg && (
            <div className={`p-3 rounded-xl text-xs font-medium flex items-center gap-2 ${
              passwordMsg.type === 'success'
                ? 'bg-emerald-500/15 border border-emerald-500/30 text-emerald-300'
                : 'bg-rose-500/15 border border-rose-500/30 text-rose-300'
            }`}>
              {passwordMsg.type === 'success' ? (
                <CheckCircle className="w-4 h-4 flex-shrink-0" />
              ) : (
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
              )}
              <span>{passwordMsg.text}</span>
            </div>
          )}

          <form onSubmit={handleChangePassword} className="space-y-4">
            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Поточний пароль
              </label>
              <div className="relative flex items-center">
                <KeyRound className="w-4 h-4 absolute left-3.5 text-slate-400 z-10 pointer-events-none" />
                <input
                  type="password"
                  value={oldPassword}
                  onChange={(e) => setOldPassword(e.target.value)}
                  required
                  placeholder="Введіть поточний пароль"
                  className="w-full pl-11 pr-4 py-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs"
                />
              </div>
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Новий пароль
              </label>
              <input
                type="password"
                value={newPassword}
                onChange={(e) => setNewPassword(e.target.value)}
                required
                placeholder="Введіть новий пароль"
                className="w-full px-4 py-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs"
              />
            </div>

            <div className="space-y-2">
              <label className="block text-xs font-bold uppercase tracking-wider text-slate-300 font-mono">
                Підтвердження пароля
              </label>
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                required
                placeholder="Повторіть новий пароль"
                className="w-full px-4 py-2.5 rounded-xl bg-[#090e1c] border border-slate-700 text-white placeholder-slate-500 focus:outline-none focus:border-emerald-400 text-xs"
              />
            </div>

            <Button
              type="submit"
              variant="primary"
              size="sm"
              isLoading={passwordLoading}
              className="w-full"
            >
              Змінити пароль
            </Button>
          </form>
        </Card>
      </div>
    </div>
  );
};
