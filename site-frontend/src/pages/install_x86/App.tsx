import React, { useState } from 'react';
import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import { Copy, Check, Monitor, Cpu, Server, Shield, Terminal, ArrowLeft, Info } from 'lucide-react';

export const App: React.FC = () => {
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null);

  const copyText = (text: string, key: string) => {
    navigator.clipboard.writeText(text);
    setCopiedCmd(key);
    setTimeout(() => setCopiedCmd(null), 2000);
  };

  const psCmd = `wsl bash -c "sudo apt update && sudo apt install -y curl && curl -fsSL https://raw.githubusercontent.com/maxfraieho/kindle-butch-gen/master/deploy.sh | bash -s -- -a"`;
  const gitCloneCmd = `git clone https://github.com/maxfraieho/kindle-butch-gen-x86.git\ncd kindle-butch-gen-x86`;

  return (
    <div className="min-h-screen flex flex-col bg-[#090d16] text-slate-100">
      <Navbar currentPage="install_x86" />

      <main className="flex-1 max-w-4xl mx-auto px-4 py-8 space-y-8">
        {/* Header */}
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <a href="index.html" className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline">
            <ArrowLeft className="w-3.5 h-3.5" /> Назад до опису проєкту
          </a>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight bg-gradient-to-r from-emerald-400 via-cyan-400 to-amber-400 bg-clip-text text-transparent">
            Розгортання Kindle-Butch-Gen (x86 / WSL2 / CUDA)
          </h1>
          <p className="text-sm text-slate-300 leading-relaxed">
            Повне керівництво по локальному та серверному деплою на настільних ПК, ноутбуках і робочих станціях (Windows 11 / WSL2 / Linux) з апаратним прискоренням NVIDIA CUDA.
          </p>

          {/* Quick Start Windows PowerShell Tip */}
          <div className="p-5 rounded-2xl bg-cyan-950/30 border border-cyan-500/30 text-xs text-cyan-200 space-y-3">
            <div className="flex items-center gap-2 font-bold text-cyan-300 text-sm">
              <span>🪟</span> Розгортання в один клік безпосередньо з Windows PowerShell:
            </div>
            <p className="text-slate-300">
              Якщо підсистему WSL ще не встановлено, виконайте в PowerShell (від Адміністратора): <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-cyan-300">wsl --install</code>
            </p>
            <p className="text-slate-300">Потім просто вставте та запустіть цю команду в <b>Windows PowerShell</b>:</p>

            <div className="relative group">
              <pre className="p-3.5 rounded-xl bg-[#090d16] border border-slate-700 text-cyan-300 font-mono text-xs overflow-x-auto whitespace-pre-wrap break-all pr-24">
                {psCmd}
              </pre>
              <button
                onClick={() => copyText(psCmd, 'ps')}
                className="absolute top-2.5 right-2.5 px-2.5 py-1 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs flex items-center gap-1 transition-all"
              >
                {copiedCmd === 'ps' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                {copiedCmd === 'ps' ? 'Скопійовано!' : 'Скопіювати'}
              </button>
            </div>

            <p className="text-[11px] text-slate-400">
              Скрипт автономно виявить CUDA GPU, встановить пакети, зкомпілює <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-cyan-300">llama.cpp</code> з <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-cyan-300">-DGGML_CUDA=ON</code>, завантажить моделі ШІ та підніме веб-панель на <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-emerald-400">http://localhost:5000</code>.
            </p>
          </div>

          {/* Table of Contents */}
          <nav className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 text-xs space-y-1.5">
            <div className="font-bold text-slate-200 mb-2">Зміст інструкції:</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-slate-400">
              <a href="#req" className="hover:text-emerald-400 transition-colors">1. Крок 1 — Передумови та системні вимоги</a>
              <a href="#repo" className="hover:text-emerald-400 transition-colors">2. Крок 2 — Підготовка репозиторію</a>
              <a href="#appwrite" className="hover:text-emerald-400 transition-colors">3. Крок 3 — Appwrite Sites</a>
              <a href="#env" className="hover:text-emerald-400 transition-colors">4. Крок 4 — Змінні середовища</a>
              <a href="#backend" className="hover:text-emerald-400 transition-colors">5. Крок 5 — Локальний запуск бекенду та CUDA</a>
              <a href="#verify" className="hover:text-emerald-400 transition-colors">6. Крок 6 — Перевірка працездатності</a>
            </div>
          </nav>
        </div>

        {/* Section 1: Prerequisites */}
        <section id="req" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Cpu className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-bold text-emerald-400">1. Крок 1. Передумови та системні вимоги</h2>
          </div>
          <p className="text-sm text-slate-300">Мінімальні вимоги до вашого комп'ютера (все інше скрипт встановить автоматично):</p>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900/80 text-slate-300">
                  <th className="p-3 font-semibold">Компонент</th>
                  <th className="p-3 font-semibold">Вимоги</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                <tr>
                  <td className="p-3 font-semibold text-slate-200">ОС</td>
                  <td className="p-3">Windows 11 із активованим <b>WSL2</b> (Ubuntu) або 64-бітний Linux.</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">GPU</td>
                  <td className="p-3 font-semibold text-emerald-400">Відеокарта NVIDIA (наприклад, RTX 3050 або новіша) — стандартний драйвер Windows автоматично прокидається у WSL2.</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">Пам'ять</td>
                  <td className="p-3 font-mono text-emerald-400">8+ GB RAM (рекомендовано 16GB+), 15+ GB вільного місця на SSD.</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">Підготовка</td>
                  <td className="p-3 font-semibold text-cyan-300">0 додаткових утиліт! Скрипт сам встановить Git, Python, CMake, FFmpeg та потрібні бібліотеки.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        {/* Section 2: Repository Prep */}
        <section id="repo" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-cyan-400" />
            <h2 className="text-xl font-bold text-cyan-400">2. Крок 2. Підготовка репозиторію</h2>
          </div>
          <p className="text-sm text-slate-300">
            Десктопна версія проєкту ізольована у репозиторії <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-cyan-300">kindle-butch-gen-x86</code>.
          </p>
          <ol className="list-decimal list-inside space-y-3 text-sm text-slate-300">
            <li>
              Клонуйте репозиторій на вашу робочу станцію у середовищі WSL2:
              <div className="relative group mt-2">
                <pre className="p-3.5 rounded-xl bg-[#090d16] border border-slate-700 text-cyan-300 font-mono text-xs overflow-x-auto pr-24">
                  {gitCloneCmd}
                </pre>
                <button
                  onClick={() => copyText(gitCloneCmd, 'git')}
                  className="absolute top-2.5 right-2.5 px-2.5 py-1 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-bold text-xs flex items-center gap-1 transition-all"
                >
                  {copiedCmd === 'git' ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
                  {copiedCmd === 'git' ? 'Скопійовано!' : 'Скопіювати'}
                </button>
              </div>
            </li>
            <li>
              Переконайтеся, що у корені каталогу присутній скрипт конфігурації <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">deploy.sh</code> та структура веб-панелі у папці <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">kbg_web/</code>.
            </li>
          </ol>
        </section>

        {/* Section 3: Appwrite Sites Integration */}
        <section id="appwrite" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Server className="w-5 h-5 text-amber-400" />
            <h2 className="text-xl font-bold text-amber-400">3. Крок 3. Інтеграція та деплой в Appwrite Sites</h2>
          </div>
          <p className="text-sm text-slate-300">
            Оскільки додаток має стабільну веб-панель керування, її можна задеплоїти через сервіси <b>Appwrite Sites</b>:
          </p>
          <ol className="list-decimal list-inside space-y-2 text-sm text-slate-300">
            <li>Увійдіть до вашої <b>Appwrite Console</b>.</li>
            <li>У боковому меню перейдіть до розділу <b>Deploy</b> і виберіть <b>Sites</b>.</li>
            <li>Натисніть <b>Create site</b>, підключіть ваш акаунт GitHub та оберіть репозиторій <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">kindle-butch-gen-x86</code>.</li>
            <li>
              Заповніть базові параметри:
              <ul className="list-disc list-inside pl-4 pt-1 space-y-1 text-xs text-slate-400">
                <li><b>Site Name:</b> Kindle Butch Gen x86</li>
                <li><b>Site ID:</b> <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-emerald-400">kindle-gen-x86</code></li>
              </ul>
            </li>
            <li>
              Налаштуйте кроки збірки (<b>Build settings</b>): вкажіть команду збірки та вихідну директорію (<b>Output Directory</b>).
            </li>
          </ol>
        </section>

        {/* Section 4: Environment Variables */}
        <section id="env" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Shield className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-bold text-emerald-400">4. Крок 4. Налаштування змінних середовища (Environment Variables)</h2>
          </div>
          <p className="text-sm text-slate-300">
            Для коректної авторизації та роботи преміум-функцій у консолі Appwrite:
          </p>
          <ol className="list-decimal list-inside space-y-2 text-sm text-slate-300">
            <li>Перейдіть до вкладки <b>Settings</b> вашого сайту в Appwrite Console та відкрийте секцію <b>Environment variables</b>.</li>
            <li>
              Додайте обов'язкові змінні конфігурації:
              <ul className="list-disc list-inside pl-4 pt-1 space-y-1 text-xs text-slate-400">
                <li><code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">KBG_WEB_PASSWORD</code> — надійний адміністративний пароль для доступу до веб-панелі.</li>
                <li><code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">KBG_APPWRITE_KEY</code> — ключ підключення до проєкту Appwrite (за потреби).</li>
              </ul>
            </li>
          </ol>
        </section>

        {/* Section 5: Local Backend & CUDA */}
        <section id="backend" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Monitor className="w-5 h-5 text-cyan-400" />
            <h2 className="text-xl font-bold text-cyan-400">5. Крок 5. Локальний запуск бекенду та CUDA-оточення (WSL2 / RTX 3050)</h2>
          </div>
          <p className="text-sm text-slate-300">
            Ресурсомісткі задачі (конвертація Marker, OCR манґи, LLM-переклад через llama.cpp та генерація аудіо) виконуються на ПК під прискоренням GPU:
          </p>
          <ol className="list-decimal list-inside space-y-3 text-sm text-slate-300">
            <li>Відкрийте термінал <b>WSL2 (Ubuntu 24.04)</b>.</li>
            <li>
              Запустіть скрипт автоматичного розгортання:
              <pre className="p-3 rounded-xl bg-[#090d16] border border-slate-700 text-emerald-400 font-mono text-xs mt-1">bash deploy.sh</pre>
            </li>
          </ol>

          <div className="p-4 rounded-2xl bg-cyan-950/20 border border-cyan-500/30 text-xs text-cyan-300 flex items-start gap-2.5">
            <Info className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
            <div>
              Скрипт автоматично налаштує збірку <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-cyan-300">llama.cpp</code> із прапорцем <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-cyan-300">-DGGML_CUDA=ON</code> та встановить десктопну CUDA-версію PyTorch (<code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-cyan-300">--index-url https://download.pytorch.org/whl/cu121</code>), що повністю задіє відеокарту NVIDIA RTX 3050 для прискорення обчислень.
            </div>
          </div>

          <p className="text-xs text-slate-300">
            Переконайтеся, що локальний Flask-бекенд успішно стартував і слухає порт <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">5000</code>.
          </p>
        </section>

        {/* Section 6: Verification */}
        <section id="verify" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <h2 className="text-xl font-bold text-slate-200">6. Крок 6. Перевірка працездатності</h2>
          <ol className="list-decimal list-inside space-y-2 text-xs sm:text-sm text-slate-300">
            <li>Перевірте статус збірки в панелі <b>Appwrite Sites</b> (статус має змінитись на <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">ready</code>).</li>
            <li>Перейдіть за згенерованим Appwrite доменом сайту або за адресою <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">http://localhost:5000</code>.</li>
            <li>Авторизуйтесь за допомогою адміністративних даних. У налаштуваннях книг вам будуть доступні всі елементи керування преміум-режимом (ASR-верифікація наголосів Whisper INT8, MQM-оцінка якості, Агент-редактор Gemma 3 4B) із інтерактивними діалогами згоди на завантаження моделей.</li>
          </ol>
        </section>
      </main>

      <Footer />
    </div>
  );
};
