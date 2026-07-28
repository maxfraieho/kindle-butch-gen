import React from 'react';
import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import { ShieldCheck, ArrowLeft } from 'lucide-react';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#090d16] text-slate-100">
      <Navbar currentPage="privacy" />

      <main className="flex-1 max-w-4xl mx-auto px-4 py-8 space-y-8">
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-6">
          <a href="index.html" className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline">
            <ArrowLeft className="w-3.5 h-3.5" /> Назад до опису проєкту
          </a>

          <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
            <ShieldCheck className="w-7 h-7 text-emerald-400" />
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
                Політика приватності Vydra
              </h1>
              <p className="text-xs text-slate-400 mt-1">Оновлено: липень 2026</p>
            </div>
          </div>

          <div className="space-y-6 text-sm text-slate-300">
            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">Хто розпорядник даних</h2>
              <p className="leading-relaxed">Команда розробників проєкту Vydra.</p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">Які дані ми збираємо</h2>
              <p className="leading-relaxed">
                Лише через Telegram-бот <a href="https://t.me/GetVydraBot" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">@GetVydraBot</a>: ваш Telegram ID, автоматично згенерований реферальний код і статус увімкнених преміум-функцій.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">Навіщо</h2>
              <p className="leading-relaxed">
                Автентифікація вашого застосунку, керування чергою генерації та синхронізація налаштувань між пристроями.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">Де зберігається</h2>
              <p className="leading-relaxed">
                У базі даних Appwrite, розміщеній у Франкфурті, Німеччина (ЄС). <b>Ми не збираємо, не обробляємо і не маємо доступу до ваших книг, документів, перекладів чи аудіо — уся обробка контенту виконується виключно офлайн на вашому пристрої.</b>
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">Передача третім сторонам</h2>
              <p className="leading-relaxed">
                Ми не продаємо, не передаємо і не розкриваємо ваші персональні дані стороннім особам.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">Ваші права (GDPR)</h2>
              <p className="leading-relaxed">
                Ви маєте право на доступ, виправлення та видалення своїх даних. Щоб назавжди видалити акаунт і всі пов'язані дані з наших серверів, надішліть команду <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">/delete_my_data</code> боту.
              </p>
            </section>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
};
