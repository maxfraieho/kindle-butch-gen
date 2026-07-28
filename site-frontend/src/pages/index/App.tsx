import React from 'react';
import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import { ExternalLink, Smartphone, Monitor, ShieldCheck, HeartHandshake, Gift } from 'lucide-react';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#090d16] text-slate-100">
      <Navbar currentPage="index" />

      <main className="flex-1 max-w-4xl mx-auto px-4 py-8 space-y-10">
        {/* Hero Section */}
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-10 shadow-2xl space-y-6">
          <div className="flex flex-col sm:flex-row items-center gap-6">
            <img
              src="vydra.jpg"
              alt="Vydra — видра-маскот з книгою і навушниками"
              className="w-32 h-32 sm:w-40 sm:h-40 rounded-2xl object-cover shadow-xl border border-emerald-500/30"
            />
            <div className="space-y-3 text-center sm:text-left">
              <h1 className="text-3xl sm:text-4xl font-extrabold text-white tracking-tight flex items-center justify-center sm:justify-start gap-2">
                <span>🦦</span> Vydra
              </h1>
              <p className="text-sm sm:text-base text-slate-300 leading-relaxed max-w-xl">
                Vydra — інструмент, що перекладає книги українською, генерує аудіокниги та адаптує манґу — все локально, на вашому власному пристрої.
              </p>
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 text-xs font-semibold">
                <ShieldCheck className="w-4 h-4" />
                Без хмари • Без підписок • Без збору даних • Створено в Україні
              </div>
            </div>
          </div>

          {/* Action CTAs */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 pt-2">
            <a
              href="https://t.me/GetVydraBot"
              target="_blank"
              rel="noreferrer"
              className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-sm transition-all shadow-lg shadow-emerald-500/20 active:scale-[0.98]"
            >
              <span>🤖</span> Почати в Telegram
              <ExternalLink className="w-4 h-4" />
            </a>

            <a
              href="install.html"
              className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-cyan-600 hover:bg-cyan-500 text-white font-bold text-sm transition-all shadow-lg shadow-cyan-600/20 active:scale-[0.98]"
            >
              <Smartphone className="w-4 h-4" />
              📲 Android (Termux)
            </a>

            <a
              href="install_x86.html"
              className="flex-1 inline-flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 font-bold text-sm transition-all active:scale-[0.98]"
            >
              <Monitor className="w-4 h-4" />
              💻 x86 (WSL2 / CUDA)
            </a>
          </div>

          <p className="text-xs text-slate-400 text-center sm:text-left pt-1">
            Реєстрація — одна команда <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">/start</code> у боті. Жодних email і паролів. {' '}
            <a href="install.html" className="text-emerald-400 hover:underline">Інструкція Android →</a> · {' '}
            <a href="install_x86.html" className="text-emerald-400 hover:underline">Інструкція x86 / CUDA →</a>
          </p>
        </div>

        {/* Transparent Support Banner Details */}
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-3 border-b border-slate-800 pb-3">
            <HeartHandshake className="w-6 h-6 text-emerald-400" />
            <h2 className="text-xl font-bold text-white">Прозоро про підтримку</h2>
          </div>

          <p className="text-sm text-slate-300 leading-relaxed">
            У згенерованих книгах зрідка (раз на 50–70 сторінок, на паузах між розділами) з'являється коротка примітка з двома <em>окремими</em> посиланнями. Вимикається однією командою <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">/no_support_banner</code> — назавжди.
          </p>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 space-y-2">
              <h3 className="font-bold text-emerald-400 text-sm flex items-center gap-2">
                <span>🇺🇦</span> Track A — захисникам
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Офіційна сторінка фонду «Повернись живим» (публічна звітність). Розробник цих грошей не торкається взагалі.
              </p>
            </div>

            <div className="rounded-2xl border border-slate-800 bg-slate-900/60 p-5 space-y-2">
              <h3 className="font-bold text-amber-400 text-sm flex items-center gap-2">
                <span>☕</span> Track B — розробнику
              </h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Окреме, явно підписане посилання підтримати автора інструменту. Це не воєнний збір — і воно ніколи не подається як він.
              </p>
            </div>
          </div>
        </div>

        {/* Referrals Section */}
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-3">
          <div className="flex items-center gap-3">
            <Gift className="w-6 h-6 text-amber-400" />
            <h2 className="text-xl font-bold text-white">Реферали</h2>
          </div>
          <p className="text-sm text-slate-300 leading-relaxed">
            Команда <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-amber-400">/referral</code> дає персональний код. Хто приєднається за ним — обидва отримують пріоритет у черзі генерації. Бонуси тільки функціональні, жодних грошей.
          </p>
        </div>
      </main>

      <Footer />
    </div>
  );
};
