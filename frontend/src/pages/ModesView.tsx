import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Card } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Badge } from '../components/ui/Badge';
import { SlidersHorizontal, BookOpen, Headphones, Image, Zap, CheckCircle, Sparkles, FileText } from 'lucide-react';

export const ModesView: React.FC = () => {
  const navigate = useNavigate();
  const [selectedProfile, setSelectedProfile] = useState<'standard' | 'fast' | 'audioonly' | 'manga'>('standard');

  const profiles = [
    {
      id: 'standard',
      name: 'Повний цикл (Стандарт)',
      icon: <Sparkles className="w-5 h-5 text-emerald-400" />,
      desc: 'Повна обробка PDF/EPUB: очищення, переклад через Llama-server та синтез мовлення Supertonic 3.',
      badge: 'Рекомендовано',
      badgeVar: 'emerald' as const,
    },
    {
      id: 'fast',
      name: 'Швидкий переклад (Без аудіо)',
      icon: <Zap className="w-5 h-5 text-amber-400" />,
      desc: 'Тільки конвертація та переклад тексту. Синтез мовлення вимкнено для прискорення на мобільних пристроях.',
      badge: 'Прискорений',
      badgeVar: 'amber' as const,
    },
    {
      id: 'audioonly',
      name: 'Тільки Синтез Аудіо',
      icon: <Headphones className="w-5 h-5 text-cyan-400" />,
      desc: 'Синтез мовлення для вже перекладених EPUB/Markdown файлів без повторного виклику нейромережі перекладу.',
      badge: 'Аудіокнига',
      badgeVar: 'cyan' as const,
    },
    {
      id: 'manga',
      name: 'Режим Манги / Коміксів',
      icon: <Image className="w-5 h-5 text-rose-400" />,
      desc: 'Детекція баблу `comic-text-detector`, OCR, переклад та верстка `Mapaki` в AZW3 для Kindle Scribe.',
      badge: 'Manga / CBZ',
      badgeVar: 'rose' as const,
    },
  ];

  return (
    <div className="space-y-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="bg-[#131c2e] p-6 rounded-2xl border border-slate-700/60 shadow-xl flex items-center justify-between">
        <div>
          <h1 className="text-2xl md:text-3xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
            <SlidersHorizontal className="w-7 h-7 text-emerald-400" /> Профілі та Режими обробки
          </h1>
          <p className="text-sm text-slate-300 mt-1">
            Налаштування швидкості перекладу, генерації аудіо та форматів експорту
          </p>
        </div>
      </div>

      {/* Docs Book Pipeline card (separate action, not a profile) */}
      <Card
        onClick={() => navigate('/book-pipeline/new')}
        className="bg-[#131c2e] border border-emerald-500/20 hover:border-emerald-400/50 p-6 space-y-4 cursor-pointer transition-all shadow-xl hover:shadow-emerald-950/40"
      >
        <div className="flex items-start justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center">
              <FileText className="w-5 h-5 text-emerald-400" />
            </div>
            <div>
              <h3 className="font-extrabold text-base text-white">Docs Book Pipeline</h3>
              <Badge variant="emerald">New</Badge>
            </div>
          </div>
        </div>
        <p className="text-xs text-slate-300 leading-relaxed">
          Clone a docs repo, humanise with NotebookLM, run an optional AI editor review, then compile English and Ukrainian PDFs automatically.
        </p>
        <Button variant="primary" size="sm" className="w-full text-xs">
          Open Book Pipeline →
        </Button>
      </Card>

      {/* Profiles Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
        {profiles.map((p) => {
          const isSelected = selectedProfile === p.id;
          return (
            <Card
              key={p.id}
              onClick={() => setSelectedProfile(p.id as any)}
              className={`bg-[#131c2e] border p-6 space-y-4 cursor-pointer transition-all shadow-xl ${
                isSelected
                  ? 'border-emerald-400 ring-1 ring-emerald-400/50 shadow-emerald-950/40'
                  : 'border-slate-700/60 hover:border-slate-500'
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-700 flex items-center justify-center">
                    {p.icon}
                  </div>
                  <div>
                    <h3 className="font-extrabold text-base text-white">{p.name}</h3>
                    <Badge variant={p.badgeVar}>{p.badge}</Badge>
                  </div>
                </div>

                {isSelected && (
                  <CheckCircle className="w-5 h-5 text-emerald-400 flex-shrink-0" />
                )}
              </div>

              <p className="text-xs text-slate-300 leading-relaxed">
                {p.desc}
              </p>

              <Button
                variant={isSelected ? 'primary' : 'outline'}
                size="sm"
                className="w-full text-xs"
              >
                {isSelected ? 'Активний режим' : 'Обрати режим'}
              </Button>
            </Card>
          );
        })}
      </div>
    </div>
  );
};
