import { X } from 'lucide-react';
import { memo, useEffect } from 'react';
import { useI18n } from '@/contexts/I18nContext';
import { methodologyContent } from '@/lib/methodology';

interface MethodologyPanelProps {
  open: boolean;
  onClose: () => void;
  onSetMode: (mode: 'data') => void;
}

export const MethodologyPanel = memo(function MethodologyPanel({
  open,
  onClose,
  onSetMode,
}: MethodologyPanelProps) {
  const { t, lang } = useI18n();
  const content = methodologyContent(lang);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      onClick={onClose}
      className="av-fade fixed inset-0 z-[2000] flex items-center justify-center p-6"
      style={{ background: 'var(--color-overlay)' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="av-scroll w-full max-w-[720px] overflow-y-auto rounded-2xl"
        style={{ background: 'var(--color-surface)', maxHeight: '88vh', boxShadow: '0 24px 70px rgba(12,14,18,.4)' }}
      >
        <div className="px-[34px] pb-7 pt-[30px]">
          <div className="mb-[18px] flex items-start justify-between">
            <div className="font-mono text-[10px] uppercase tracking-[.14em]" style={{ color: 'var(--blue-600)' }}>
              {content.eyebrow}
            </div>
            <button
              onClick={onClose}
              className="flex h-[30px] w-[30px] items-center justify-center rounded-lg border-none"
              style={{ background: 'var(--stone-100)', color: 'var(--stone-600)' }}
            >
              <X className="h-4 w-4" />
            </button>
          </div>

          <h2
            className="mb-3.5"
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 30,
              fontWeight: 600,
              letterSpacing: '-.015em',
              lineHeight: 1.12,
              color: 'var(--stone-900)',
            }}
          >
            {content.title}
          </h2>

          <p className="mb-5 text-pretty" style={{ fontSize: 15, lineHeight: 1.65, color: 'var(--stone-700)' }}>
            {content.intro}
          </p>

          <div
            className="mb-6 rounded-[11px] px-4 py-3.5"
            style={{ background: 'var(--stone-50)', border: '1px solid var(--stone-200)' }}
          >
            <div className="mb-2 font-mono text-[9.5px] uppercase tracking-[.1em]" style={{ color: 'var(--stone-500)' }}>
              Pipeline
            </div>
            <div className="flex flex-wrap items-center gap-1.5" style={{ fontSize: 12, color: 'var(--stone-700)' }}>
              {content.pipelineSteps.map((step, i) => (
                <span key={step} className="inline-flex items-center gap-1.5">
                  {i > 0 && <span style={{ color: 'var(--stone-400)' }}>→</span>}
                  <span>{step}</span>
                </span>
              ))}
            </div>
          </div>

          {content.sections.map((section) => (
            <section key={section.id} className="mb-6">
              <h3
                className="mb-2"
                style={{
                  fontFamily: 'var(--font-serif)',
                  fontSize: 18,
                  fontWeight: 600,
                  color: 'var(--stone-900)',
                }}
              >
                {section.title}
              </h3>
              {section.paragraphs.map((p, i) => (
                <p
                  key={i}
                  className="mb-2.5 text-pretty"
                  style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}
                >
                  {p}
                </p>
              ))}
              {section.bullets && (
                <ul className="mb-2 ml-4 list-disc space-y-1" style={{ fontSize: 13.5, color: 'var(--stone-700)' }}>
                  {section.bullets.map((b) => (
                    <li key={b}>{b}</li>
                  ))}
                </ul>
              )}
            </section>
          ))}

          <div className="mt-1.5 rounded-[11px] px-4 py-3.5" style={{ background: 'var(--gold-50)', border: '1px solid var(--gold-500)' }}>
            <p style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--stone-700)' }}>{content.disclaimer}</p>
          </div>

          <button
            onClick={() => {
              onClose();
              onSetMode('data');
            }}
            className="mt-4 w-full rounded-[10px] border-none px-4 py-2.5"
            style={{ background: 'var(--blue-500)', color: '#fff', fontSize: 14, fontWeight: 500 }}
          >
            {t.navData}
          </button>
        </div>
      </div>
    </div>
  );
});
