import { X } from 'lucide-react';
import { memo, useEffect } from 'react';
import { useI18n } from '@/contexts/I18nContext';
interface AboutModalProps {
  open: boolean;
  onClose: () => void;
  onOpenMethodology: () => void;
}

export const AboutModal = memo(function AboutModal({
  open,
  onClose,
  onOpenMethodology,
}: AboutModalProps) {
  const { t, lang } = useI18n();
  const closeLabel = lang === 'pt' ? 'Fechar' : 'Close';

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
      className="av-fade fixed inset-0 z-[2000] flex items-center justify-center p-4 sm:p-6"
      style={{ background: 'var(--color-overlay)' }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="av-scroll w-full max-w-[540px] overflow-y-auto rounded-2xl"
        style={{ background: 'var(--color-surface)', maxHeight: '88dvh', boxShadow: '0 24px 70px rgba(12,14,18,.4)' }}
      >
        <div className="px-5 pb-7 pt-[30px] sm:px-[34px]">
          <div className="mb-[18px] flex items-start justify-between">
            <div className="font-mono text-[10px] uppercase tracking-[.14em]" style={{ color: 'var(--blue-600)' }}>
              {t.aboutEyebrow}
            </div>
            <button
              onClick={onClose}
              aria-label={closeLabel}
              className="flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border-none"
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
            {t.aboutTitle}
          </h2>
          <p className="mb-3.5 text-pretty" style={{ fontSize: 15, lineHeight: 1.65, color: 'var(--stone-700)' }}>
            {t.aboutP1}
          </p>
          <p className="mb-3.5 text-pretty" style={{ fontSize: 15, lineHeight: 1.65, color: 'var(--stone-700)' }}>
            {t.aboutP2}
          </p>
          <button
            onClick={() => {
              onClose();
              onOpenMethodology();
            }}
            className="mb-3.5 w-full rounded-[10px] border-none px-4 py-2.5"
            style={{ background: 'var(--blue-500)', color: '#fff', fontSize: 14, fontWeight: 500 }}
          >
            {t.aboutMethodologyLink}
          </button>
          <div className="mt-1.5 rounded-[11px] px-4 py-3.5" style={{ background: 'var(--gold-50)', border: '1px solid var(--gold-500)' }}>
            <div className="mb-[5px] font-mono text-[9.5px] uppercase tracking-[.1em]" style={{ color: 'var(--gold-700)' }}>
              {t.disclaimerLabel}
            </div>
            <p style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--stone-700)' }}>{t.disclaimer}</p>
          </div>
        </div>
      </div>
    </div>
  );
});
