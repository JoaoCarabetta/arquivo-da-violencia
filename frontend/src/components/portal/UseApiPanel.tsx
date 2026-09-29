import { X } from 'lucide-react';
import { memo, useEffect } from 'react';
import { useI18n } from '@/contexts/I18nContext';

interface UseApiPanelProps {
  open: boolean;
  onClose: () => void;
}

const OPENAPI_URL = '/api/openapi.json';
const LLMS_URL = '/llms.txt';
const DOCS_URL = '/api/docs';

export const UseApiPanel = memo(function UseApiPanel({ open, onClose }: UseApiPanelProps) {
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
        className="av-scroll w-full max-w-[640px] overflow-y-auto rounded-2xl"
        style={{
          background: 'var(--color-surface)',
          maxHeight: '88dvh',
          boxShadow: '0 24px 70px rgba(12,14,18,.4)',
        }}
      >
        <div className="px-5 pb-7 pt-[30px] sm:px-[34px]">
          <div className="mb-[18px] flex items-start justify-between">
            <div className="font-mono text-[10px] uppercase tracking-[.14em]" style={{ color: 'var(--blue-600)' }}>
              {t.useApiEyebrow}
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
            {t.useApiTitle}
          </h2>
          <p className="mb-4 text-pretty" style={{ fontSize: 15, lineHeight: 1.65, color: 'var(--stone-700)' }}>
            {t.useApiIntro}
          </p>
          <ul className="mb-4 space-y-2" style={{ fontSize: 14, lineHeight: 1.55, color: 'var(--stone-800)' }}>
            <li>
              <a href={OPENAPI_URL} className="underline-offset-2 hover:underline" style={{ color: 'var(--blue-600)' }}>
                {t.useApiOpenapi}
              </a>
              <span style={{ color: 'var(--stone-500)' }}> — {OPENAPI_URL}</span>
            </li>
            <li>
              <a href={LLMS_URL} className="underline-offset-2 hover:underline" style={{ color: 'var(--blue-600)' }}>
                {t.useApiLlms}
              </a>
            </li>
            <li>
              <a href={DOCS_URL} className="underline-offset-2 hover:underline" style={{ color: 'var(--blue-600)' }}>
                Swagger UI
              </a>
            </li>
          </ul>
          <p className="mb-3 text-pretty" style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}>
            {t.useApiClaude}
          </p>
          <p className="text-pretty" style={{ fontSize: 13, lineHeight: 1.55, color: 'var(--stone-600)' }}>
            {t.useApiAttribution}
          </p>
        </div>
      </div>
    </div>
  );
});
