import { memo } from 'react';
import { useI18n } from '@/contexts/I18nContext';

export const DensityLegend = memo(function DensityLegend() {
  const { t } = useI18n();

  return (
    <div className="absolute bottom-5 left-[18px] z-[1100] flex flex-col gap-[9px]">
      <div
        className="rounded-[11px] px-[13px] py-2.5"
        style={{
          background: 'var(--color-surface)',
          border: '1px solid var(--color-border)',
          boxShadow: '0 4px 16px rgba(20,23,28,.1)',
        }}
      >
        <div
          className="mb-[7px] font-mono text-[9.5px] uppercase tracking-[.12em]"
          style={{ color: 'var(--color-text-subtle)' }}
        >
          {t.legendTitle}
        </div>
        <div className="flex items-center gap-[3px]">
          <span className="h-[11px] w-[26px] rounded-l-[2px]" style={{ background: 'rgba(247,198,192,.85)' }} />
          <span className="h-[11px] w-[26px]" style={{ background: 'rgba(224,138,130,.9)' }} />
          <span className="h-[11px] w-[26px]" style={{ background: 'rgba(200,71,63,.92)' }} />
          <span className="h-[11px] w-[26px]" style={{ background: 'rgba(168,55,48,.95)' }} />
          <span className="h-[11px] w-[26px] rounded-r-[2px]" style={{ background: 'rgba(135,43,38,1)' }} />
        </div>
        <div className="mt-1 flex justify-between" style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
          <span>{t.fewer}</span>
          <span>{t.more}</span>
        </div>
      </div>
    </div>
  );
});
