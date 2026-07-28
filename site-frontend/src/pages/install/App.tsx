import React, { useState } from 'react';
import { Navbar } from '../../components/Navbar';
import { Footer } from '../../components/Footer';
import { Copy, Check, AlertTriangle, Info, Terminal, Battery, Power, HelpCircle, ArrowLeft } from 'lucide-react';

export const App: React.FC = () => {
  const [copied, setCopied] = useState(false);
  const installCmd = 'bash <(curl -fsSL https://raw.githubusercontent.com/maxfraieho/kindle-butch-gen/master/deploy.sh) -a';

  const handleCopy = () => {
    navigator.clipboard.writeText(installCmd);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#090d16] text-slate-100">
      <Navbar currentPage="install" />

      <main className="flex-1 max-w-4xl mx-auto px-4 py-8 space-y-8">
        {/* Header */}
        <div className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <a href="index.html" className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline">
            <ArrowLeft className="w-3.5 h-3.5" /> Назад до опису проєкту
          </a>
          <h1 className="text-2xl sm:text-3xl font-extrabold text-white tracking-tight bg-gradient-to-r from-emerald-400 via-cyan-400 to-amber-400 bg-clip-text text-transparent">
            Встановлення Vydra на свій смартфон (Android)
          </h1>
          <p className="text-sm text-slate-300 leading-relaxed">
            Vydra працює <b>повністю локально</b> на вашому Android: книги, переклад, аудіо і манґа не залишають пристрій. Встановлення — три кроки і одна команда; скрипт сам перевірить, чи телефон підходить, і зробить решту. Супровід: <a href="https://t.me/GetVydraBot" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">@GetVydraBot</a> (команда <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">/install</code> — ця сама інструкція в Telegram).
          </p>

          {/* Table of Contents */}
          <nav className="p-4 rounded-2xl bg-slate-900/80 border border-slate-800 text-xs space-y-1.5">
            <div className="font-bold text-slate-200 mb-2">Зміст інструкції:</div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-4 gap-y-1 text-slate-400">
              <a href="#req" className="hover:text-emerald-400 transition-colors">0. Чи підійде ваш телефон</a>
              <a href="#termux" className="hover:text-emerald-400 transition-colors">1. Крок 1 — Termux (з F-Droid)</a>
              <a href="#battery" className="hover:text-emerald-400 transition-colors">2. Крок 2 — Вимкнути батарею</a>
              <a href="#boot" className="hover:text-emerald-400 transition-colors">3. Крок 3 — Termux:Boot</a>
              <a href="#run" className="hover:text-emerald-400 transition-colors">4. Крок 4 — Одна команда</a>
              <a href="#during" className="hover:text-emerald-400 transition-colors">5. Перебіг встановлення</a>
              <a href="#first" className="hover:text-emerald-400 transition-colors">6. Перший вхід</a>
              <a href="#update" className="hover:text-emerald-400 transition-colors">7. Оновлення</a>
              <a href="#faq" className="hover:text-emerald-400 transition-colors">8. Часті питання</a>
            </div>
          </nav>
        </div>

        {/* Section 0: Requirements */}
        <section id="req" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <h2 className="text-xl font-bold text-emerald-400 border-b border-slate-800 pb-2">
            0. Чи підійде ваш телефон
          </h2>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-900/80 text-slate-300">
                  <th className="p-3 font-semibold">Параметр</th>
                  <th className="p-3 font-semibold">Мінімум</th>
                  <th className="p-3 font-semibold">Комфортно</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-slate-300">
                <tr>
                  <td className="p-3 font-semibold text-slate-200">Android</td>
                  <td className="p-3">64-бітний (aarch64) — практично всі телефони після ~2017</td>
                  <td className="p-3">—</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">Оперативна пам'ять</td>
                  <td className="p-3 font-mono text-emerald-400">6 GB</td>
                  <td className="p-3 font-mono text-emerald-400">10+ GB</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">Вільне місце</td>
                  <td className="p-3 font-mono text-emerald-400">15 GB</td>
                  <td className="p-3 font-mono text-emerald-400">25+ GB</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">GPU</td>
                  <td className="p-3">не обов'язково</td>
                  <td className="p-3">Adreno (Snapdragon) — переклад значно швидший</td>
                </tr>
                <tr>
                  <td className="p-3 font-semibold text-slate-200">Інтернет</td>
                  <td colSpan={2} className="p-3">Wi-Fi на час встановлення — завантажується ~6 GB (модель перекладу та пакети)</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-400">
            Не впевнені — просто запускайте: перший крок скрипта — <b>діагностика</b>, яка перевірить усе сама і зрозуміло скаже, чого бракує, ще до будь-яких завантажень.
          </p>
        </section>

        {/* Section 1: Termux */}
        <section id="termux" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Terminal className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-bold text-emerald-400">1. Крок 1 — Termux (тільки з F-Droid)</h2>
          </div>
          <p className="text-sm text-slate-300">Termux — це термінал Linux для Android, у якому житиме Vydra.</p>
          <ol className="list-decimal list-inside space-y-2 text-sm text-slate-300">
            <li>
              Відкрийте сторінку <a href="https://f-droid.org/packages/com.termux/" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">f-droid.org/packages/com.termux</a>.
            </li>
            <li>Натисніть «Завантажити APK» (найновіша версія) і встановіть. Android спитає дозвіл на встановлення з невідомих джерел — дозвольте для браузера один раз.</li>
            <li>Відкрийте Termux — побачите чорний екран із запрошенням <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">$</code>. Це все, він готовий.</li>
          </ol>

          <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-500/30 text-xs text-amber-300 flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <b>Не встановлюйте Termux із Google Play Market</b> — та версія покинута роками і не працює. Тільки F-Droid.
            </div>
          </div>

          <div className="p-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 text-center text-xs text-slate-400">
            📸 СКРІНШОТ: сторінка Termux на F-Droid + перший запуск Termux
          </div>
        </section>

        {/* Section 2: Battery */}
        <section id="battery" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Battery className="w-5 h-5 text-amber-400" />
            <h2 className="text-xl font-bold text-amber-400">2. Крок 2 — вимкніть оптимізацію батареї для Termux</h2>
          </div>
          <p className="text-sm text-slate-300">
            <b>Це найчастіша причина невдалих встановлень.</b> Android може вбити Termux у фоні навіть з увімкненим екраном — багатогігабайтне завантаження моделі обривається без жодної помилки, просто зникає процес.
          </p>
          <ol className="list-decimal list-inside space-y-2 text-sm text-slate-300">
            <li>
              Налаштування телефона → Застосунки → <b>Termux</b> → Батарея → <b>Без обмежень</b> (на деяких пристроях: Оптимізація батареї → Усі застосунки → Termux → <b>Не оптимізувати</b>).
            </li>
          </ol>

          <div className="p-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 text-center text-xs text-slate-400">
            📸 СКРІНШОТ: екран налаштувань батареї для Termux
          </div>
        </section>

        {/* Section 3: Termux:Boot */}
        <section id="boot" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <Power className="w-5 h-5 text-cyan-400" />
            <h2 className="text-xl font-bold text-cyan-400">3. Крок 3 — Termux:Boot (автостарт після перезавантаження)</h2>
          </div>
          <ol className="list-decimal list-inside space-y-2 text-sm text-slate-300">
            <li>
              З того самого F-Droid встановіть <a href="https://f-droid.org/packages/com.termux.boot/" target="_blank" rel="noreferrer" className="text-cyan-400 hover:underline">Termux:Boot</a>.
            </li>
            <li><b>Відкрийте його один раз</b> — цього достатньо (він попросить дозвіл автозапуску).</li>
          </ol>
          <p className="text-xs text-slate-400">
            Навіщо: після перезавантаження телефона сервіси Vydra піднімуться самі. Без цього додатка теж усе працює — просто після ребута треба буде раз відкрити Termux вручну.
          </p>

          <div className="p-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 text-center text-xs text-slate-400">
            📸 СКРІНШОТ: Termux:Boot на F-Droid
          </div>
        </section>

        {/* Section 4: One Command */}
        <section id="run" className="rounded-3xl border border-emerald-500/40 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4 shadow-xl shadow-emerald-500/5">
          <h2 className="text-xl font-bold text-white flex items-center gap-2">
            <Terminal className="w-5 h-5 text-emerald-400" />
            <span>4. Крок 4 — одна команда</span>
          </h2>
          <p className="text-sm text-slate-300">Відкрийте Termux і вставте (довге натискання → Paste):</p>

          <div className="relative group">
            <pre className="p-4 rounded-2xl bg-[#090d16] border border-slate-700 text-emerald-400 font-mono text-xs sm:text-sm overflow-x-auto whitespace-pre-wrap break-all pr-24">
              {installCmd}
            </pre>
            <button
              onClick={handleCopy}
              className="absolute top-3 right-3 px-3 py-1.5 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold text-xs flex items-center gap-1.5 transition-all shadow-md active:scale-95"
            >
              {copied ? <Check className="w-3.5 h-3.5" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? 'Скопійовано!' : 'Скопіювати'}
            </button>
          </div>

          <p className="text-xs text-slate-300">Натисніть Enter — далі все автоматично.</p>

          <div className="p-4 rounded-2xl bg-amber-950/20 border border-amber-500/30 text-xs text-amber-300 flex items-start gap-2.5">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div>
              ⚠️ <b>Тримайте екран увімкненим і Termux відкритим</b> до напису <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-emerald-400">Deployment complete!</code> (30–60 хв залежно від мережі). Android агресивно вбиває важкі фонові процеси — це головна причина невдалих установок.
            </div>
          </div>

          <div className="p-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 text-center text-xs text-slate-400">
            📸 СКРІНШОТ: команда вставлена в Termux
          </div>
        </section>

        {/* Section 5: During Installation */}
        <section id="during" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <h2 className="text-xl font-bold text-slate-200">5. Що відбувається під час встановлення</h2>
          <ol className="list-decimal list-inside space-y-2.5 text-xs sm:text-sm text-slate-300">
            <li><b>Діагностика</b> — таблиця PASS/WARN/FAIL: архітектура, пам'ять, місце, мережа, GPU, Termux:Boot. Якщо є FAIL — скрипт зупиниться і пояснить що виправити.</li>
            <li><b>Пакети Termux</b> — git, python, компілятор тощо (~5 хв).</li>
            <li><b>Ubuntu-контейнер</b> (24.04 LTS) — ізольоване середовище для обробки книг: розпізнавання, конвертація, збірка EPUB (~15 хв, ~700 пакетів).</li>
            <li><b>Компіляція перекладача</b> (llama.cpp) — найдовший крок, 10–20 хв; з Adreno GPU збирається з апаратним прискоренням.</li>
            <li><b>Модель перекладу</b> — запит на завантаження Hy-MT2-7B (4.4 GB): відповідайте <code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-emerald-400">1</code> (стандартне завантаження). Обрив мережі не страшний — докачується з місця зупинки.</li>
            <li><b>Голос озвучення</b> (TTS) — завантажується автоматично (~130 MB).</li>
          </ol>

          <div className="p-4 rounded-2xl bg-cyan-950/20 border border-cyan-500/30 text-xs text-cyan-300 flex items-start gap-2.5">
            <Info className="w-5 h-5 text-cyan-400 shrink-0 mt-0.5" />
            <div>
              Скрипт можна безпечно запускати повторно: все вже встановлене він пропускає і продовжує з місця зупинки.
            </div>
          </div>

          <div className="p-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 text-center text-xs text-slate-400">
            📸 СКРІНШОТ: таблиця діагностики + Deployment complete
          </div>
        </section>

        {/* Section 6: First Login */}
        <section id="first" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <h2 className="text-xl font-bold text-slate-200">6. Перший вхід</h2>
          <ol className="list-decimal list-inside space-y-2 text-xs sm:text-sm text-slate-300">
            <li>У браузері телефона відкрийте <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">http://localhost:5000</code>.</li>
            <li>Логін <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">admin</code>; пароль скрипт друкує прямо наприкінці встановлення (рядок «Пароль: ...» у зеленому блоці «Deployment complete!») — прогорніть трохи вгору, якщо проґавили.</li>
            <li>Дайте Termux доступ до пам'яті телефона (щоб готові книги падали в зручну теку): виконайте в Termux <code className="font-mono bg-slate-900 px-1.5 py-0.5 rounded text-emerald-400">termux-setup-storage</code> і підтвердьте дозвіл.</li>
            <li>Натисніть <b>➕ Add Book</b> — і додавайте першу книгу. Далі вас поведе <b>📖 Посібник</b> прямо в інтерфейсі.</li>
          </ol>

          <div className="p-4 rounded-2xl border border-dashed border-slate-700 bg-slate-900/40 text-center text-xs text-slate-400">
            📸 СКРІНШОТ: головний екран Vydra після входу
          </div>
        </section>

        {/* Section 7: Update */}
        <section id="update" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-3">
          <h2 className="text-xl font-bold text-slate-200">7. Оновлення</h2>
          <p className="text-sm text-slate-300 leading-relaxed">
            Кнопка <b>🔄 Update</b> на головному екрані: сервіс сам стягне свіжий код з GitHub і перезапуститься. Під час активної генерації оновлення чемно відмовиться — дочекайтесь завершення.
          </p>
        </section>

        {/* Section 8: FAQ */}
        <section id="faq" className="rounded-3xl border border-slate-800 bg-[#111827]/80 backdrop-blur-xl p-6 sm:p-8 space-y-4">
          <div className="flex items-center gap-2">
            <HelpCircle className="w-5 h-5 text-emerald-400" />
            <h2 className="text-xl font-bold text-emerald-400">8. Часті питання (FAQ)</h2>
          </div>
          <ul className="space-y-4 text-xs sm:text-sm text-slate-300">
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">Завантаження моделі почалось заново, хоча вже було завантажилось.</b>
              <span>Це майже завжди означає, що не виконано крок 2 (оптимізація батареї) — Android вбив процес у фоні. Вимкніть оптимізацію і запустіть команду ще раз.</span>
            </li>
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">Скрипт упав / телефон перезавантажився.</b>
              <span>Просто запустіть ту саму команду ще раз — продовжить з місця зупинки.</span>
            </li>
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">«pkg: command not found».</b>
              <span>У вас Termux із Play Market — видаліть і встановіть з F-Droid (крок 1).</span>
            </li>
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">Діагностика FAIL по пам'яті чи місцю.</b>
              <span>Вимоги жорсткі через 7-мільярдну модель перекладу — на слабшому пристрої, на жаль, ніяк.</span>
            </li>
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">Сервіс не відповідає після ребута.</b>
              <span>Відкрийте Termux (усе підніметься само) або поставте Termux:Boot (крок 2).</span>
            </li>
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">Це безкоштовно?</b>
              <span>Так, базова генерація — назавжди. Є опційні преміум-функції якості після донату і добровільна підтримка — деталі в <a href="https://t.me/GetVydraBot" target="_blank" rel="noreferrer" className="text-emerald-400 hover:underline">боті</a> (<code className="font-mono bg-slate-900 px-1 py-0.5 rounded text-emerald-400">/premium</code>) та на <a href="index.html" className="text-emerald-400 hover:underline">головній</a>.</span>
            </li>
            <li className="p-4 rounded-2xl bg-slate-900/60 border border-slate-800 space-y-1">
              <b className="text-slate-100 block">Мої книги кудись відправляються?</b>
              <span>Ні. Вся обробка локальна; хмара використовується лише для реєстрації профілю і рефералів.</span>
            </li>
          </ul>
        </section>
      </main>

      <Footer />
    </div>
  );
};
