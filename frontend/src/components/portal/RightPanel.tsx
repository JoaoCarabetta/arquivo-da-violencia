import { memo, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ChevronLeft, RotateCcw, SlidersHorizontal, MapPin, Clock, FileText, Download } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { fetchPublicEventById, getExportUrl, type MapPoint } from '@/lib/api';
import {
  fmtNumber,
  fmtDateShort,
  fmtDateLong,
  monthShort,
  translateType,
  translateMethod,
  translatePeriod,
  typeColor,
  ufName,
  dictionaryRows,
} from '@/lib/i18n';
import { TemporalScopeNote } from './TemporalScopeNote';
import {
  computeStats,
  buildTrendMonths,
  type PortalFilters,
  type PortalMode,
} from './types';

type FilterGroup = 'types' | 'methods' | 'periods';

interface RightPanelProps {
  mode: PortalMode;
  sinceDate: string | null;
  pointsInView: MapPoint[];
  filteredCount: number;
  filters: PortalFilters;
  availableTypes: string[];
  availableMethods: string[];
  availablePeriods: string[];
  onToggleFilter: (group: FilterGroup, value: string) => void;
  onClearFilters: () => void;
  hasFilters: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onCloseDetail: () => void;
  canReset: boolean;
  onResetView: () => void;
}

const EYEBROW =
  'font-mono text-[9.5px] uppercase tracking-[.12em] text-[color:var(--color-text-subtle)]';

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-[11px] font-mono text-[10px] uppercase tracking-[.1em] text-[color:var(--color-text-subtle)]">
      {children}
    </div>
  );
}

const PERIOD_ORDER = ['madrugada', 'manhã', 'manha', 'tarde', 'noite'];

function sortPeriods(values: string[]): string[] {
  return [...values].sort((a, b) => {
    const ia = PERIOD_ORDER.indexOf(a.toLowerCase());
    const ib = PERIOD_ORDER.indexOf(b.toLowerCase());
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
}

export const RightPanel = memo(function RightPanel(props: RightPanelProps) {
  const { selectedId } = props;
  return (
    <aside
      className="av-scroll z-[1250] flex w-[392px] flex-none flex-col overflow-y-auto overflow-x-hidden"
      style={{ background: 'var(--color-surface)', borderLeft: '1px solid var(--color-border)' }}
    >
      {selectedId != null ? (
        <DetailView id={selectedId} onClose={props.onCloseDetail} />
      ) : (
        <PanelContent {...props} />
      )}
    </aside>
  );
});

function PanelContent(props: RightPanelProps) {
  const { t } = useI18n();
  const { mode } = props;

  const eyebrow = mode === 'feed' ? t.navFeed : mode === 'data' ? t.navData : t.statistics;
  const title = mode === 'feed' ? t.navFeed : mode === 'data' ? t.navData : t.inThisView;

  return (
    <div>
      <div className="px-5 pb-[14px] pt-[18px]" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <div className={`${EYEBROW} mb-[3px]`}>{eyebrow}</div>
        <div className="flex items-center justify-between gap-2.5">
          <h2
            className="m-0"
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 22,
              fontWeight: 600,
              letterSpacing: '-.01em',
              color: 'var(--stone-900)',
            }}
          >
            {title}
          </h2>
          {mode === 'stats' && props.canReset && (
            <button
              onClick={props.onResetView}
              className="inline-flex items-center gap-[5px] whitespace-nowrap rounded-[7px] px-[9px] py-[5px]"
              style={{
                border: '1px solid var(--stone-200)',
                background: 'var(--color-surface)',
                fontSize: 11.5,
                color: 'var(--color-text-muted)',
              }}
            >
              <RotateCcw className="h-[13px] w-[13px]" />
              {t.reset}
            </button>
          )}
        </div>
        <div className="mt-2">
          <TemporalScopeNote since={props.sinceDate} />
        </div>
      </div>

      {mode === 'stats' && <StatsMode {...props} />}
      {mode === 'feed' && <FeedMode {...props} />}
      {mode === 'data' && <DataMode {...props} />}
    </div>
  );
}

// ---------------------------------------------------------------- Stats mode

function Chip({
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
      onClick={onClick}
      className="rounded-[20px] px-[11px] py-[5px] transition-all"
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

function StatsMode(props: RightPanelProps) {
  const { t, lang } = useI18n();
  const { pointsInView, filters, hasFilters } = props;

  const stats = useMemo(() => computeStats(pointsInView), [pointsInView]);
  const months = useMemo(() => buildTrendMonths(pointsInView), [pointsInView]);

  const scopeNote = t.inVisibleArea + (hasFilters ? t.filtersActive : '');

  const trendMax = Math.max(1, ...months.map((m) => stats.trend[m.key] ?? 0));
  const typeMax = Math.max(1, ...Object.values(stats.byType));
  const typeRows = Object.entries(stats.byType)
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({ type, count }));
  const stateEntries = Object.entries(stats.byState)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6);
  const stateMax = Math.max(1, ...stateEntries.map((x) => x[1]));
  const periodVals = sortPeriods(props.availablePeriods.filter((p) => stats.byPeriod[p] != null || true)).slice(0, 4);
  const periodMax = Math.max(1, ...periodVals.map((p) => stats.byPeriod[p] ?? 0));

  return (
    <div className="px-5 pb-[30px] pt-4">
      {/* headline numbers */}
      <div className="mb-2 grid grid-cols-2 gap-[11px]">
        <div className="rounded-xl px-[15px] py-[13px]" style={{ border: '1px solid var(--stone-200)' }}>
          <div
            className="leading-none"
            style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-.02em', color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}
          >
            {fmtNumber(stats.total, lang)}
          </div>
          <div className="mt-[5px]" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
            {t.events}
          </div>
        </div>
        <div className="rounded-xl px-[15px] py-[13px]" style={{ border: '1px solid var(--stone-200)', background: 'var(--red-50)' }}>
          <div
            className="leading-none"
            style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-.02em', color: 'var(--red-700)', fontVariantNumeric: 'tabular-nums' }}
          >
            {fmtNumber(stats.victims, lang)}
          </div>
          <div className="mt-[5px]" style={{ fontSize: 12, color: 'var(--red-700)', opacity: 0.85 }}>
            {t.victims}
          </div>
        </div>
      </div>
      <div className="mb-5" style={{ fontSize: 11.5, color: 'var(--color-text-subtle)' }}>
        {scopeNote}
      </div>

      {/* filters */}
      <div className="mb-[9px] flex items-center justify-between">
        <div className="flex items-center gap-[7px] font-mono text-[10px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
          <SlidersHorizontal className="h-[13px] w-[13px]" />
          {t.filters}
        </div>
        {hasFilters && (
          <button onClick={props.onClearFilters} className="border-none bg-transparent p-0" style={{ fontSize: 11.5, color: 'var(--blue-600)' }}>
            {t.clear}
          </button>
        )}
      </div>

      <FilterGroupBlock
        label={t.fType}
        values={props.availableTypes}
        active={filters.types}
        render={(v) => translateType(v, lang)}
        onToggle={(v) => props.onToggleFilter('types', v)}
      />
      <FilterGroupBlock
        label={t.fMethod}
        values={props.availableMethods}
        active={filters.methods}
        render={(v) => translateMethod(v, lang)}
        onToggle={(v) => props.onToggleFilter('methods', v)}
      />
      <FilterGroupBlock
        label={t.fPeriod}
        values={sortPeriods(props.availablePeriods)}
        active={filters.periods}
        render={(v) => translatePeriod(v, lang)}
        onToggle={(v) => props.onToggleFilter('periods', v)}
        extraMargin
      />

      {/* monthly trend */}
      <SectionLabel>{t.trend}</SectionLabel>
      <div className="mb-1.5 flex h-[74px] items-end gap-1">
        {months.map((m) => {
          const c = stats.trend[m.key] ?? 0;
          const h = Math.round((c / trendMax) * 100);
          return (
            <div
              key={m.key}
              title={`${monthShort(m.m, lang)}/${String(m.y).slice(2)}: ${c}`}
              className="flex h-full flex-1 flex-col items-center justify-end"
            >
              <div
                className="w-full rounded-t-[3px] transition-[height] duration-300"
                style={{ background: c > 0 ? 'var(--blue-500)' : 'var(--stone-200)', height: `${Math.max(h, 2)}%` }}
              />
            </div>
          );
        })}
      </div>
      <div className="mb-[26px] flex justify-between font-mono" style={{ fontSize: 9.5, color: 'var(--stone-400)' }}>
        <span>{`${monthShort(months[0].m, lang)}/${String(months[0].y).slice(2)}`}</span>
        <span>{`${monthShort(months[11].m, lang)}/${String(months[11].y).slice(2)}`}</span>
      </div>

      {/* by type */}
      <SectionLabel>{t.byType}</SectionLabel>
      <div className="mb-[26px] flex flex-col gap-[9px]">
        {typeRows.map((r) => (
          <div key={r.type}>
            <div className="mb-1 flex justify-between" style={{ fontSize: 12.5 }}>
              <span style={{ color: 'var(--stone-700)' }}>{translateType(r.type, lang)}</span>
              <span className="font-mono" style={{ color: 'var(--stone-500)', fontVariantNumeric: 'tabular-nums' }}>
                {fmtNumber(r.count, lang)}
              </span>
            </div>
            <div className="h-[7px] overflow-hidden rounded" style={{ background: 'var(--stone-100)' }}>
              <div className="h-full rounded transition-[width] duration-300" style={{ background: typeColor(r.type), width: `${Math.round((r.count / typeMax) * 100)}%` }} />
            </div>
          </div>
        ))}
        {typeRows.length === 0 && <EmptyArea />}
      </div>

      {/* by state */}
      <SectionLabel>{t.byState}</SectionLabel>
      <div className="mb-[26px] flex flex-col gap-[9px]">
        {stateEntries.map(([uf, c]) => (
          <div key={uf}>
            <div className="mb-1 flex justify-between" style={{ fontSize: 12.5 }}>
              <span style={{ color: 'var(--stone-700)' }}>
                <span className="mr-1.5 font-mono" style={{ fontSize: 11, color: 'var(--stone-400)' }}>
                  {uf}
                </span>
                {ufName(uf)}
              </span>
              <span className="font-mono" style={{ color: 'var(--stone-500)', fontVariantNumeric: 'tabular-nums' }}>
                {fmtNumber(c, lang)}
              </span>
            </div>
            <div className="h-[7px] overflow-hidden rounded" style={{ background: 'var(--stone-100)' }}>
              <div className="h-full rounded transition-[width] duration-300" style={{ background: 'var(--blue-500)', width: `${Math.round((c / stateMax) * 100)}%` }} />
            </div>
          </div>
        ))}
        {stateEntries.length === 0 && <EmptyArea />}
      </div>

      {/* time of day */}
      {periodVals.length > 0 && (
        <>
          <SectionLabel>{t.timeOfDay}</SectionLabel>
          <div className="grid grid-cols-4 gap-2">
            {periodVals.map((p) => {
              const count = stats.byPeriod[p] ?? 0;
              return (
                <div key={p} className="rounded-[10px] px-2 py-[10px] text-center" style={{ border: '1px solid var(--stone-200)' }}>
                  <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}>
                    {fmtNumber(count, lang)}
                  </div>
                  <div className="mt-0.5" style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                    {translatePeriod(p, lang)}
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded" style={{ background: 'var(--stone-100)' }}>
                    <div className="h-full" style={{ background: 'var(--blue-400)', width: `${Math.round((count / periodMax) * 100)}%` }} />
                  </div>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}

function FilterGroupBlock({
  label,
  values,
  active,
  render,
  onToggle,
  extraMargin,
}: {
  label: string;
  values: string[];
  active: string[];
  render: (v: string) => string;
  onToggle: (v: string) => void;
  extraMargin?: boolean;
}) {
  if (values.length === 0) return null;
  return (
    <>
      <div className="mb-1.5" style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
        {label}
      </div>
      <div className={`flex flex-wrap gap-1.5 ${extraMargin ? 'mb-6' : 'mb-[13px]'}`}>
        {values.map((v) => (
          <Chip key={v} label={render(v)} active={active.includes(v)} onClick={() => onToggle(v)} />
        ))}
      </div>
    </>
  );
}

function EmptyArea() {
  const { t } = useI18n();
  return <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>{t.emptyArea}</div>;
}

// ---------------------------------------------------------------- Feed mode

function FeedMode(props: RightPanelProps) {
  const { t, lang } = useI18n();
  const feed = useMemo(
    () =>
      [...props.pointsInView]
        .sort((a, b) => {
          const da = a.d ? Date.parse(a.d) : 0;
          const db = b.d ? Date.parse(b.d) : 0;
          return db - da;
        })
        .slice(0, 50),
    [props.pointsInView]
  );

  return (
    <div className="px-[14px] pb-[30px] pt-2">
      <div className="px-1.5 pb-3 pt-2" style={{ fontSize: 11.5, color: 'var(--color-text-subtle)' }}>
        {t.feedNote}
      </div>
      <div className="flex flex-col gap-2">
        {feed.map((e) => {
          const victims = e.v ?? 0;
          return (
            <button
              key={e.id}
              onClick={() => props.onSelect(e.id)}
              className="flex flex-col gap-1.5 rounded-[11px] px-[13px] py-3 text-left transition-[border-color,box-shadow]"
              style={{ border: '1px solid var(--stone-200)', background: 'var(--color-surface)' }}
              onMouseEnter={(ev) => {
                ev.currentTarget.style.borderColor = 'var(--stone-300)';
                ev.currentTarget.style.boxShadow = '0 3px 12px rgba(20,23,28,.07)';
              }}
              onMouseLeave={(ev) => {
                ev.currentTarget.style.borderColor = 'var(--stone-200)';
                ev.currentTarget.style.boxShadow = 'none';
              }}
            >
              <div className="flex items-center justify-between gap-2">
                <span
                  className="rounded-[5px] px-[7px] py-[3px] font-mono uppercase"
                  style={{ fontSize: 10, letterSpacing: '.03em', color: '#fff', background: typeColor(e.t) }}
                >
                  {translateType(e.t, lang)}
                </span>
                <span className="font-mono" style={{ fontSize: 11, color: 'var(--stone-400)' }}>
                  {e.d ? fmtDateShort(e.d, lang) : ''}
                </span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--stone-900)', lineHeight: 1.3 }}>
                {translateType(e.t, lang)}
                {e.n ? ` — ${e.n}` : ''}
              </div>
              <div className="flex items-center gap-1.5" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                <MapPin className="h-[13px] w-[13px] flex-none" />
                {[e.c, e.st].filter(Boolean).join(' · ')}
                {victims > 0 && ` · ${victims} ${victims > 1 ? t.victimsLower : t.victim}`}
              </div>
            </button>
          );
        })}
        {feed.length === 0 && (
          <div className="px-2.5 py-[30px] text-center" style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
            {t.emptyArea}
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Data mode

function DataMode(props: RightPanelProps) {
  const { t, lang } = useI18n();
  const dict = dictionaryRows(lang);

  return (
    <div className="px-5 pb-[30px] pt-[18px]">
      <p className="mb-[18px] text-pretty" style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}>
        {t.dataIntro}
      </p>
      <div className="mb-[18px] rounded-xl p-4" style={{ border: '1px solid var(--stone-200)', background: 'var(--stone-50)' }}>
        <div className="mb-[13px] flex justify-between">
          <div>
            <div className="leading-none" style={{ fontSize: 26, fontWeight: 600, color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}>
              {fmtNumber(props.filteredCount, lang)}
            </div>
            <div className="mt-1" style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
              {t.recordsExport}
            </div>
          </div>
          <div className="text-right">
            <div className="leading-none" style={{ fontSize: 26, fontWeight: 600, color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}>
              {dict.length}
            </div>
            <div className="mt-1" style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
              {t.columns}
            </div>
          </div>
        </div>
        <a
          href={getExportUrl('csv')}
          className="flex w-full items-center justify-center gap-2 rounded-[10px] p-3 transition-colors"
          style={{ background: 'var(--blue-500)', color: '#fff', fontSize: 14, fontWeight: 500 }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--blue-600)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--blue-500)')}
        >
          <Download className="h-[17px] w-[17px]" />
          {t.downloadCsv}
        </a>
        <a
          href={getExportUrl('json')}
          className="mt-2 flex w-full items-center justify-center gap-2 rounded-[10px] p-2.5 transition-colors"
          style={{ border: '1px solid var(--stone-300)', color: 'var(--stone-700)', fontSize: 13, fontWeight: 500 }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--stone-100)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
        >
          <Download className="h-4 w-4" />
          {t.downloadJson}
        </a>
        <div className="mt-2 text-center" style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>
          {props.hasFilters ? t.dataNote : t.allEvents}
        </div>
      </div>

      <SectionLabel>{t.dictionary}</SectionLabel>
      <div className="overflow-hidden rounded-[10px]" style={{ border: '1px solid var(--stone-200)' }}>
        {dict.map((d) => (
          <div key={d.field} className="flex gap-2.5 px-3 py-[9px]" style={{ borderBottom: '1px solid var(--stone-100)' }}>
            <span className="w-[128px] flex-none break-all font-mono" style={{ fontSize: 11, color: 'var(--blue-700)' }}>
              {d.field}
            </span>
            <span style={{ fontSize: 12, color: 'var(--stone-600)', lineHeight: 1.35 }}>{d.desc}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- Detail view

function DetailView({ id, onClose }: { id: number; onClose: () => void }) {
  const { t, lang } = useI18n();
  const { data: event, isLoading } = useQuery({
    queryKey: ['public-event', id],
    queryFn: () => fetchPublicEventById(id),
  });

  if (isLoading) {
    return (
      <div className="flex flex-col items-center gap-3.5 px-5 py-20" style={{ color: 'var(--color-text-muted)' }}>
        <span className="font-mono text-[11px] uppercase tracking-[.1em]">{t.loadingEvent}</span>
      </div>
    );
  }
  if (!event) {
    return (
      <div className="px-5 py-20 text-center" style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
        <button onClick={onClose} className="mb-4 inline-flex items-center gap-1.5" style={{ color: 'var(--blue-600)', fontSize: 13, fontWeight: 500 }}>
          <ChevronLeft className="h-4 w-4" />
          {t.back}
        </button>
        <div>{t.eventNotFound}</div>
      </div>
    );
  }

  const tColor = typeColor(event.homicide_type);
  const place = [event.neighborhood, event.city].filter(Boolean).join(', ');
  const cityLine = [event.city, ufName(event.state)].filter(Boolean).join(' · ');
  const srcCount = event.source_count ?? 0;
  const sourceWord = srcCount > 1 ? t.newsSources : t.newsSource;

  return (
    <div className="av-fade px-5 pb-7 pt-[18px]">
      <button onClick={onClose} className="mb-4 inline-flex items-center gap-1.5 border-none bg-transparent p-0" style={{ color: 'var(--blue-600)', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500 }}>
        <ChevronLeft className="h-4 w-4" />
        {t.back}
      </button>

      <div className="mb-[13px] flex flex-wrap gap-2">
        <span className="inline-flex items-center gap-1.5 rounded-md px-[9px] py-1 font-mono uppercase" style={{ fontSize: 10.5, letterSpacing: '.04em', color: '#fff', background: tColor }}>
          {translateType(event.homicide_type, lang)}
        </span>
        {event.security_force_involved && (
          <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-[3px] font-mono uppercase" style={{ fontSize: 10.5, letterSpacing: '.04em', color: 'var(--gold-700)', background: 'var(--gold-50)', border: '1px solid var(--gold-500)' }}>
            {t.securityForce}
          </span>
        )}
      </div>

      <h2 className="mb-1.5" style={{ fontFamily: 'var(--font-serif)', fontSize: 23, lineHeight: 1.18, fontWeight: 600, letterSpacing: '-.01em', color: 'var(--stone-900)' }}>
        {event.title || `${translateType(event.homicide_type, lang)}${event.neighborhood ? ` — ${event.neighborhood}` : ''}`}
      </h2>
      <div className="mb-[18px]" style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
        {event.event_date ? fmtDateLong(event.event_date, lang) : ''}
      </div>

      <div className="mb-[18px] grid grid-cols-2 gap-2.5">
        <div className="rounded-[10px] px-[13px] py-[11px]" style={{ background: 'var(--stone-50)', border: '1px solid var(--stone-200)' }}>
          <div className="mb-[3px] font-mono text-[9px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
            {t.victims}
          </div>
          <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--red-600)', fontVariantNumeric: 'tabular-nums' }}>
            {fmtNumber(event.victim_count ?? 0, lang)}
          </div>
        </div>
        <div className="rounded-[10px] px-[13px] py-[11px]" style={{ background: 'var(--stone-50)', border: '1px solid var(--stone-200)' }}>
          <div className="mb-[3px] font-mono text-[9px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
            {t.method}
          </div>
          <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--stone-900)', lineHeight: 1.3 }}>
            {translateMethod(event.method_of_death, lang)}
          </div>
        </div>
      </div>

      <div className="mb-[18px] flex flex-col overflow-hidden rounded-[10px]" style={{ border: '1px solid var(--stone-200)' }}>
        <div className="flex gap-2.5 px-[13px] py-[11px]" style={{ borderBottom: '1px solid var(--stone-100)' }}>
          <MapPin className="mt-px h-4 w-4 flex-none" style={{ color: 'var(--stone-500)' }} />
          <div>
            <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--stone-900)' }}>{event.formatted_address || place || '—'}</div>
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{cityLine}</div>
          </div>
        </div>
        {event.time_of_day && (
          <div className="flex gap-2.5 px-[13px] py-[11px]">
            <Clock className="mt-px h-4 w-4 flex-none" style={{ color: 'var(--stone-500)' }} />
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--stone-900)' }}>{translatePeriod(event.time_of_day, lang)}</div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{t.timeNote}</div>
            </div>
          </div>
        )}
      </div>

      {event.chronological_description && (
        <>
          <div className="mb-[7px] font-mono text-[9.5px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
            {t.summary}
          </div>
          <p className="mb-[18px] text-pretty" style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}>
            {event.chronological_description}
          </p>
        </>
      )}

      <div className="flex items-center gap-2 pt-3.5" style={{ borderTop: '1px solid var(--stone-100)', fontSize: 12, color: 'var(--color-text-muted)' }}>
        <FileText className="h-[15px] w-[15px]" />
        {`${t.reportedBy}${srcCount}${sourceWord} · #${event.id}`}
      </div>
    </div>
  );
}
