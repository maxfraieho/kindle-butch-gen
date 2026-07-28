import React from 'react';
import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import { AlertTriangle, ArrowLeft, Shield } from 'lucide-react';

export const App: React.FC = () => {
  return (
    <div className="min-h-screen flex flex-col bg-[#090d16] text-slate-100">
      <Navbar currentPage="legal" />

      <main className="flex-1 max-w-4xl mx-auto px-4 py-8 space-y-8">
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-6">
          <a href="index.html" className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline">
            <ArrowLeft className="w-3.5 h-3.5" /> Назад до опису проєкту
          </a>

          <div className="flex items-center gap-3 border-b border-slate-800 pb-4">
            <Shield className="w-7 h-7 text-emerald-400" />
            <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight">
              Правові застереження та умови використання
            </h1>
          </div>

          <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-500/30 text-xs text-amber-300 flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              ⚠️ Це не юридична консультація — стандартна практика подібних інструментів, не професійна юридична експертиза.
            </div>
          </div>

          <div className="space-y-6 text-sm text-slate-300">
            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">1. Що таке Vydra</h2>
              <p className="leading-relaxed">
                Інструмент для <b>особистого, приватного</b> перекладу книг і манґи, які у вас вже є на законних підставах. Vydra не містить, не хостить і не поширює чужий захищений контент, не обходить DRM. Код відкритий (MIT), ліцензія стосується коду, не контенту, який ви обробляєте.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">2. Відповідальність користувача</h2>
              <ul className="list-disc list-inside space-y-1.5 text-xs sm:text-sm">
                <li>Ви маєте законне право на будь-який файл, який завантажуєте.</li>
                <li>
                  Переклад для особистого користування зазвичай підпадає під виключення особистого копіювання (в Україні — ст. 25 ЗУ «Про авторське право») — перевірте закон вашої країни.
                </li>
                <li>
                  <b>Публічне поширення отриманого перекладу заборонено</b> без згоди правовласника оригинала.
                </li>
              </ul>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">3. Дані боту підтримки</h2>
              <p className="leading-relaxed">
                Реєстрація через <a href="https://t.me/GetVydraBot" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">@GetVydraBot</a> зберігає мінімум: Telegram ID, реферальний код, статус преміум. <b>Ваші книги й переклади ніколи не залишають ваш пристрій.</b>
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">4. Донати (Track A / Track B)</h2>
              <p className="leading-relaxed">
                <b>Track A</b> — офіційний фонд, Vydra не посередник у платежах, не бере комісії, не контролює використання коштів. <b>Track B</b> — добровільна підтримка розробника, не оплата послуги (генерація безкоштовна незалежно від донату).
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">5. Відмова від гарантій</h2>
              <p className="leading-relaxed">
                ПЗ надається "як є" (MIT License), без гарантій. Розробники не відповідають за збитки, пов'язані з використанням Vydra.
              </p>
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-bold text-emerald-400">6. Товарні знаки</h2>
              <p className="leading-relaxed">
                «Kindle»/«Amazon» — товарні знаки Amazon.com, Inc., згадуються лише для опису сумісності форматів. Vydra не афілійована з Amazon чи жодним видавництвом.
              </p>
            </section>

            <div className="pt-4 border-t border-slate-800 text-xs text-slate-400">
              Повний текст: <a href="https://github.com/maxfraieho/kindle-butch-gen/blob/master/docs/uk/legal.md" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">docs/uk/legal.md</a> · Питання: <a href="https://t.me/GetVydraBot" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">@GetVydraBot</a>
            </div>
          </div>
        </div>
      </main>

      <Footer />
    </div>
  );
};
