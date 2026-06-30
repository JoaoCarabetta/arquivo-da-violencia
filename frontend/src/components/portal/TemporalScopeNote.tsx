import { memo } from 'react';
import { useI18n } from '@/contexts/I18nContext';
import { fmtDateLong } from '@/lib/i18n';

interface TemporalScopeNoteProps {
  since: string | null;
  variant?: 'subtle' | 'inline';
}

export const TemporalScopeNote = memo(function TemporalScopeNote({
  since,
  variant = 'subtle',
}: TemporalScopeNoteProps) {
  const { t, lang } = useI18n();

  if (!since) return null;

  const date = fmtDateLong(since, lang);
  const text = t.temporalScope.replace('{date}', date);

  if (variant === 'inline') {
    return (
      <span style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
        {text}
      </span>
    );
  }

  return (
    <p
      className="m-0"
      style={{
        fontSize: 11.5,
        lineHeight: 1.45,
        color: 'var(--color-text-subtle)',
      }}
    >
      {text}
    </p>
  );
});
