import { memo, useEffect, useRef, useState } from 'react';
import { ChevronDown, X } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { translateMethod, translatePeriod, translateType } from '@/lib/i18n';
import { cn } from '@/lib/utils';
import {
  dateRangeForLastDays,
  sortPeriods,
  type PortalFilters,
} from './types';

type FilterGroup = 'types' | 'methods' | 'periods';
type MenuId = FilterGroup | 'temporal';

interface MapFilterBarProps {
  filters: PortalFilters;
  availableTypes: string[];
  availableMethods: string[];
  availablePeriods: string[];
  dataLoading: boolean;
  hasFilters: boolean;
  onToggleFilter: (group: FilterGroup, value: string) => void;
  onSetDateRange: (startDate: string, endDate: string) => void;
  onClearFilters: () => void;
}

function FilterChip({
  label,
  active,
  onClick,
  className,
}: {
  label: string;
  active?: boolean;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5 transition-colors',
        className
      )}
      style={{
        border: `1px solid ${active ? 'var(--blue-500)' : 'var(--stone-200)'}`,
        background: active ? 'var(--blue-500)' : 'var(--color-surface)',
        color: active ? '#fff' : 'var(--stone-700)',
        fontSize: 12.5,
        boxShadow: active ? undefined : '0 1px 3px rgba(20,23,28,.06)',
      }}
    >
      {label}
    </button>
  );
}

function MenuChip({
  label,
  open,
  active,
  onClick,
}: {
  label: string;
  open: boolean;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex shrink-0 items-center gap-1 rounded-full px-3 py-1.5"
      style={{
        border: `1px solid ${open || active ? 'var(--blue-500)' : 'var(--stone-200)'}`,
        background: open || active ? 'var(--blue-50)' : 'var(--color-surface)',
        color: open || active ? 'var(--blue-700)' : 'var(--stone-700)',
        fontSize: 12.5,
        boxShadow: '0 1px 3px rgba(20,23,28,.06)',
      }}
    >
      {label}
      <ChevronDown
        className={cn('h-3.5 w-3.5 transition-transform', open && 'rotate-180')}
        style={{ opacity: 0.7 }}
      />
    </button>
  );
}

function OptionChip({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded-full px-2.5 py-1 transition-colors"
      style={{
        border: `1px solid ${active ? 'var(--blue-500)' : 'var(--stone-200)'}`,
        background: active ? 'var(--blue-500)' : 'var(--color-surface)',
        color: active ? '#fff' : 'var(--stone-600)',
        fontSize: 12,
      }}
    >
      {label}
    </button>
  );
}

export const MapFilterBar = memo(function MapFilterBar(props: MapFilterBarProps) {
  const { t, lang } = useI18n();
  const [openMenu, setOpenMenu] = useState<MenuId | null>(null);
  const [draftStart, setDraftStart] = useState(props.filters.startDate);
  const [draftEnd, setDraftEnd] = useState(props.filters.endDate);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setDraftStart(props.filters.startDate);
    setDraftEnd(props.filters.endDate);
  }, [props.filters.startDate, props.filters.endDate]);

  useEffect(() => {
    if (openMenu == null) return;
    const onPointerDown = (event: MouseEvent) => {
      if (rootRef.current?.contains(event.target as Node)) return;
      setOpenMenu(null);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [openMenu]);

  const toggleMenu = (id: MenuId) => {
    setOpenMenu((cur) => (cur === id ? null : id));
  };

  const temporalActive = Boolean(props.filters.startDate || props.filters.endDate);
  const dateRangeInvalid = Boolean(draftStart && draftEnd && draftStart > draftEnd);

  const activeChips: { key: string; label: string; onRemove: () => void }[] = [
    ...props.filters.types.map((v) => ({
      key: `t-${v}`,
      label: translateType(v, lang),
      onRemove: () => props.onToggleFilter('types', v),
    })),
    ...props.filters.methods.map((v) => ({
      key: `m-${v}`,
      label: translateMethod(v, lang),
      onRemove: () => props.onToggleFilter('methods', v),
    })),
    ...props.filters.periods.map((v) => ({
      key: `p-${v}`,
      label: translatePeriod(v, lang),
      onRemove: () => props.onToggleFilter('periods', v),
    })),
  ];

  if (temporalActive) {
    const from = props.filters.startDate || '…';
    const to = props.filters.endDate || '…';
    activeChips.push({
      key: 'temporal',
      label: `${from} – ${to}`,
      onRemove: () => props.onSetDateRange('', ''),
    });
  }

  const renderOptions = (
    group: FilterGroup,
    values: string[],
    render: (v: string) => string
  ) => {
    if (props.dataLoading) {
      return (
        <p className="px-1 py-1" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
          {t.filtersLoading}
        </p>
      );
    }
    if (values.length === 0) {
      return (
        <p className="px-1 py-1" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
          {t.filtersNoOptions}
        </p>
      );
    }
    return (
      <div className="flex flex-wrap gap-1.5">
        {values.map((v) => (
          <OptionChip
            key={v}
            label={render(v)}
            active={props.filters[group].includes(v)}
            onClick={() => props.onToggleFilter(group, v)}
          />
        ))}
      </div>
    );
  };

  return (
    <div ref={rootRef} className="relative">
      <div
        className="av-scroll flex min-w-0 items-center gap-1.5 overflow-x-auto py-0.5"
        style={{ scrollbarWidth: 'none' }}
      >
        <MenuChip
          label={t.fPeriod}
          open={openMenu === 'periods'}
          active={props.filters.periods.length > 0}
          onClick={() => toggleMenu('periods')}
        />
        <MenuChip
          label={t.fType}
          open={openMenu === 'types'}
          active={props.filters.types.length > 0}
          onClick={() => toggleMenu('types')}
        />
        <MenuChip
          label={t.fMethod}
          open={openMenu === 'methods'}
          active={props.filters.methods.length > 0}
          onClick={() => toggleMenu('methods')}
        />
        <MenuChip
          label={t.fTemporal}
          open={openMenu === 'temporal'}
          active={temporalActive}
          onClick={() => toggleMenu('temporal')}
        />

        {activeChips.length > 0 && (
          <span className="mx-0.5 h-5 w-px shrink-0" style={{ background: 'var(--stone-200)' }} />
        )}

        {activeChips.map((chip) => (
          <button
            key={chip.key}
            type="button"
            onClick={chip.onRemove}
            className="inline-flex shrink-0 items-center gap-1 rounded-full py-1.5 pl-3 pr-2"
            style={{
              border: '1px solid var(--blue-500)',
              background: 'var(--blue-500)',
              color: '#fff',
              fontSize: 12.5,
            }}
          >
            {chip.label}
            <X className="h-3.5 w-3.5 opacity-90" />
          </button>
        ))}

        {props.hasFilters && (
          <button
            type="button"
            onClick={props.onClearFilters}
            className="inline-flex shrink-0 items-center rounded-full px-3 py-1.5"
            style={{
              fontSize: 12,
              color: 'var(--blue-600)',
              background: 'var(--color-surface)',
              border: '1px solid var(--stone-200)',
              boxShadow: '0 1px 3px rgba(20,23,28,.06)',
            }}
          >
            {t.clear}
          </button>
        )}
      </div>

      {openMenu != null && (
        <div
          className="absolute left-0 top-[calc(100%+6px)] z-40 min-w-[240px] max-w-[min(360px,calc(100vw-36px))] rounded-xl p-3"
          style={{
            background: 'var(--color-surface)',
            border: '1px solid var(--color-border)',
            boxShadow: '0 12px 30px rgba(20,23,28,.16)',
          }}
        >
          {openMenu === 'types' &&
            renderOptions('types', props.availableTypes, (v) => translateType(v, lang))}
          {openMenu === 'methods' &&
            renderOptions('methods', props.availableMethods, (v) => translateMethod(v, lang))}
          {openMenu === 'periods' &&
            renderOptions('periods', sortPeriods(props.availablePeriods), (v) => translatePeriod(v, lang))}

          {openMenu === 'temporal' && (
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap gap-1.5">
                {([
                  { days: 30, label: t.temporal30d },
                  { days: 90, label: t.temporal90d },
                  { days: 365, label: t.temporal365d },
                ] as const).map(({ days, label }) => (
                  <FilterChip
                    key={days}
                    label={label}
                    onClick={() => {
                      const range = dateRangeForLastDays(days);
                      props.onSetDateRange(range.startDate, range.endDate);
                      setOpenMenu(null);
                    }}
                  />
                ))}
              </div>
              <div>
                <div
                  className="mb-2 font-mono text-[10px] uppercase tracking-[.08em]"
                  style={{ color: 'var(--color-text-subtle)' }}
                >
                  {t.temporalCustom}
                </div>
                <div className="grid grid-cols-2 gap-2">
                  <label className="flex flex-col gap-1">
                    <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{t.exportStartDate}</span>
                    <input
                      type="date"
                      value={draftStart}
                      onChange={(e) => setDraftStart(e.target.value)}
                      className="rounded-md px-2 py-1.5"
                      style={{ border: '1px solid var(--stone-200)', fontSize: 12 }}
                    />
                  </label>
                  <label className="flex flex-col gap-1">
                    <span style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>{t.exportEndDate}</span>
                    <input
                      type="date"
                      value={draftEnd}
                      onChange={(e) => setDraftEnd(e.target.value)}
                      className="rounded-md px-2 py-1.5"
                      style={{ border: '1px solid var(--stone-200)', fontSize: 12 }}
                    />
                  </label>
                </div>
                {dateRangeInvalid && (
                  <p className="mt-2" style={{ fontSize: 11.5, color: 'var(--red-700)' }}>
                    {t.exportDateRangeInvalid}
                  </p>
                )}
                <div className="mt-2 flex gap-2">
                  <FilterChip
                    label={t.temporalApply}
                    active
                    onClick={() => {
                      if (dateRangeInvalid) return;
                      props.onSetDateRange(draftStart, draftEnd);
                      setOpenMenu(null);
                    }}
                  />
                  {(draftStart || draftEnd) && (
                    <FilterChip
                      label={t.clear}
                      onClick={() => {
                        setDraftStart('');
                        setDraftEnd('');
                        props.onSetDateRange('', '');
                        setOpenMenu(null);
                      }}
                    />
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
});
