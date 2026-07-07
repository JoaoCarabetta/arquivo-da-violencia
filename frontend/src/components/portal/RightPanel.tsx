import { memo, useMemo, useRef, useState, useEffect } from 'react';
import { RotateCcw, MapPin, Download } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { getExportUrl, type MapPoint } from '@/lib/api';
import { cn } from '@/lib/utils';
import {
  fmtNumber,
  fmtDateShort,
  translateMethod,
  translatePeriod,
  typeColor,
  ufName,
  dictionaryRows,
} from '@/lib/i18n';
import {
  DEFAULT_SELECTED_COLUMN_IDS,
  EXPORT_COLUMN_GROUPS,
  countSelectedFields,
  loadSelectedColumnIds,
  saveSelectedColumnIds,
  selectedExportFields,
} from '@/lib/exportColumns';
import {
  formatPointLabel,
  formatSubtype,
  pointSubtype,
  type HomicideSubtype,
} from '@/lib/taxonomy';
import type { MapBounds } from '@/components/map/CrimeMap';
import { EventDetailView } from '@/components/portal/EventDetailView';
import {
  computeStats,
  computeLast24hStats,
  buildTrendWeeks,
  sortPeriods,
  trendChartScale,
  dateRangeForLastDays,
  pointsInViewExcept,
  CITY_STATS_ZOOM_THRESHOLD,
  type FilterGroup,
  type PortalFilters,
  type PortalMode,
} from './types';

interface RightPanelProps {
  mode: PortalMode;
  allPoints: MapPoint[];
  panelBounds: MapBounds | null;
  pointsInView: MapPoint[];
  mapZoom: number;
  viewportReady: boolean;
  filters: PortalFilters;
  hasFilters: boolean;
  selectedId: number | null;
  onSelect: (id: number) => void;
  onCloseDetail: () => void;
  canReset: boolean;
  onResetView: () => void;
  onToggleFilter: (group: FilterGroup, value: string) => void;
  onSetDateRange: (startDate: string, endDate: string) => void;
  onClearFilters: () => void;
  onGeoSelect: (kind: 'states' | 'cities', value: string) => void;
  onSetMode: (mode: PortalMode) => void;
  filteredCount: number;
  /** When true, panel fills its container (e.g. mobile sheet) instead of fixed 392px sidebar. */
  embedded?: boolean;
  className?: string;
}


function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-[11px] font-mono text-[10px] uppercase tracking-[.1em] text-[color:var(--color-text-subtle)]">
      {children}
    </div>
  );
}

export const RightPanel = memo(function RightPanel(props: RightPanelProps) {
  const { selectedId, embedded = false, className } = props;
  return (
    <aside
      className={cn(
        'av-scroll z-[1250] flex flex-col overflow-y-auto overflow-x-hidden',
        embedded ? 'h-full w-full' : 'w-[392px] flex-none',
        className
      )}
      style={{ background: 'var(--color-surface)', borderLeft: embedded ? undefined : '1px solid var(--color-border)' }}
    >
      {selectedId != null ? (
        <EventDetailView id={selectedId} onClose={props.onCloseDetail} />
      ) : (
        <PanelContent {...props} />
      )}
    </aside>
  );
});

function PanelModeTabs({
  mode,
  onSetMode,
}: {
  mode: PortalMode;
  onSetMode: (mode: PortalMode) => void;
}) {
  const { t } = useI18n();
  const tabs: { id: PortalMode; label: string }[] = [
    { id: 'stats', label: t.statistics },
    { id: 'feed', label: t.navFeed },
    { id: 'data', label: t.navData },
  ];

  return (
    <div
      className="mb-3 flex gap-0.5 rounded-[10px] p-1"
      role="tablist"
      aria-label={t.statistics}
      style={{ background: 'var(--stone-100)' }}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          type="button"
          role="tab"
          aria-selected={mode === tab.id}
          onClick={() => onSetMode(tab.id)}
          className={cn('av-panel-tab flex-1 rounded-lg px-2 py-1.5 transition-colors', mode === tab.id && 'av-panel-tab-active')}
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 9.5,
            letterSpacing: '.04em',
            textTransform: 'uppercase',
          }}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function PanelContent(props: RightPanelProps) {
  const { mode } = props;

  return (
    <div>
      <div className="px-5 pb-[14px] pt-[18px]" style={{ borderBottom: '1px solid var(--color-border)' }}>
        <PanelModeTabs mode={mode} onSetMode={props.onSetMode} />
        <StatsHeader {...props} />
      </div>

      {mode === 'stats' && <StatsMode {...props} />}
      {mode === 'feed' && <FeedMode {...props} />}
      {mode === 'data' && <DataMode {...props} />}
    </div>
  );
}

const HEADER_SERIF = {
  fontFamily: 'var(--font-serif)',
  fontSize: 20,
  fontWeight: 600,
  letterSpacing: '-.01em',
  color: 'var(--stone-900)',
} as const;

const BAR_PREVIEW_LIMIT = 5;
const FILTER_BAR_COLOR = 'var(--stone-500)';
const WEEKLY_BAR_COLOR = 'var(--red-600)';

function visibleBarRows<T>(
  rows: T[],
  getKey: (row: T) => string,
  activeKeys: string[],
  expanded: boolean,
): T[] {
  if (expanded || rows.length <= BAR_PREVIEW_LIMIT) return rows;
  const preview = rows.slice(0, BAR_PREVIEW_LIMIT);
  const previewKeys = new Set(preview.map(getKey));
  const pinned = rows.filter(
    (row) => activeKeys.includes(getKey(row)) && !previewKeys.has(getKey(row))
  );
  return [...preview, ...pinned];
}

function BarExpandToggle({
  expanded,
  total,
  onToggle,
}: {
  expanded: boolean;
  total: number;
  onToggle: () => void;
}) {
  const { t } = useI18n();
  if (total <= BAR_PREVIEW_LIMIT) return null;

  return (
    <button
      type="button"
      onClick={onToggle}
      className="mt-1 self-start rounded-md px-2 py-1 transition-colors"
      style={{ fontSize: 11.5, color: 'var(--blue-600)' }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--stone-100)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
    >
      {expanded ? t.fewer : `${t.more} (${total - BAR_PREVIEW_LIMIT})`}
    </button>
  );
}

function fmtDateInline(iso: string, lang: 'pt' | 'en'): string {
  const parts = iso.split('-').map(Number);
  const [y, m, d] = parts;
  if (!y || !m || !d) return iso;
  return lang === 'en' ? `${m}/${d}/${y}` : `${d}/${m}/${y}`;
}

function EditableDateField({
  value,
  onChange,
  title,
}: {
  value: string;
  onChange: (value: string) => void;
  title: string;
}) {
  const { lang } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);

  const openPicker = () => {
    const input = inputRef.current;
    if (!input) return;
    input.showPicker?.();
  };

  return (
    <span className="av-date-inline group relative inline shrink-0 whitespace-nowrap">
      <button
        type="button"
        className="av-date-text m-0 cursor-pointer border-0 bg-transparent p-0"
        style={HEADER_SERIF}
        title={title}
        aria-label={title}
        onClick={openPicker}
      >
        {fmtDateInline(value, lang)}
      </button>
      <input
        ref={inputRef}
        type="date"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="absolute h-px w-px overflow-hidden opacity-0"
        tabIndex={-1}
        aria-hidden
      />
    </span>
  );
}

function StatsHeader(props: RightPanelProps) {
  const { t, lang } = useI18n();

  const dateRangeInvalid = Boolean(
    props.filters.startDate &&
      props.filters.endDate &&
      props.filters.startDate > props.filters.endDate
  );

  const dateEditHint = lang === 'pt' ? 'Clique para alterar a data' : 'Click to change the date';

  return (
    <div>
      <h2
        className="m-0"
        style={{ ...HEADER_SERIF, lineHeight: 1.35 }}
      >
        <span className="block">{t.homicidesBetween}</span>
        <span className="mt-0.5 flex flex-wrap items-baseline gap-x-1.5">
          <EditableDateField
            value={props.filters.startDate}
            onChange={(startDate) => props.onSetDateRange(startDate, props.filters.endDate)}
            title={dateEditHint}
          />
          <span className="shrink-0">{t.and}</span>
          <EditableDateField
            value={props.filters.endDate}
            onChange={(endDate) => props.onSetDateRange(props.filters.startDate, endDate)}
            title={dateEditHint}
          />
        </span>
      </h2>
      {dateRangeInvalid && (
        <p className="mt-2" style={{ fontSize: 11.5, color: 'var(--red-700)' }}>
          {t.exportDateRangeInvalid}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap items-center justify-between gap-1.5">
        <div className="flex flex-wrap gap-1.5">
        {([
          { days: 30, label: t.temporal30d },
          { days: 90, label: t.temporal90d },
          { days: 365, label: t.temporal365d },
        ] as const).map(({ days, label }) => (
          <button
            key={days}
            type="button"
            onClick={() => {
              const range = dateRangeForLastDays(days);
              props.onSetDateRange(range.startDate, range.endDate);
            }}
            className="rounded-full px-2.5 py-1 transition-colors"
            style={{
              border: '1px solid var(--stone-200)',
              background: 'var(--color-surface)',
              fontSize: 11.5,
              color: 'var(--stone-600)',
            }}
          >
            {label}
          </button>
        ))}
        </div>
        <div className="flex shrink-0 items-center gap-1.5">
          {props.hasFilters && (
            <button
              type="button"
              onClick={props.onClearFilters}
              className="inline-flex items-center whitespace-nowrap rounded-[7px] px-[9px] py-[5px]"
              style={{
                border: '1px solid var(--stone-200)',
                background: 'var(--color-surface)',
                fontSize: 11.5,
                color: 'var(--blue-600)',
              }}
            >
              {t.clear}
            </button>
          )}
          {props.canReset && (
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
      </div>
    </div>
  );
}

function ClickableBarRow({
  label,
  count,
  max,
  barColor,
  active,
  onClick,
  lang,
  hint,
}: {
  label: React.ReactNode;
  count: number;
  max: number;
  barColor: string;
  active: boolean;
  onClick: () => void;
  lang: 'pt' | 'en';
  hint: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={hint}
      data-active={active ? 'true' : undefined}
      className="av-filter-bar w-full rounded-lg px-2 py-1.5 text-left font-sans"
      style={{ fontFamily: 'var(--font-sans)' }}
    >
      <div className="av-filter-bar-label mb-1 flex justify-between" style={{ fontSize: 12.5 }}>
        <span style={{ color: 'var(--stone-700)' }}>{label}</span>
        <span
          className="font-mono tabular-nums"
          style={{ fontFamily: 'var(--font-mono)', color: 'var(--stone-500)' }}
        >
          {fmtNumber(count, lang)}
        </span>
      </div>
      <div className="h-[7px] overflow-hidden rounded" style={{ background: 'var(--stone-100)' }}>
        <div
          className="av-filter-bar-fill h-full rounded transition-[width] duration-300"
          style={{ background: barColor, width: `${Math.round((count / max) * 100)}%` }}
        />
      </div>
    </button>
  );
}

function WeekBar({
  weekKey,
  count,
  heightPct,
  lang,
}: {
  weekKey: string;
  count: number;
  heightPct: number;
  lang: 'pt' | 'en';
}) {
  const { t } = useI18n();
  const weekLabel = fmtDateShort(weekKey, lang);
  const countLabel = `${fmtNumber(count, lang)} ${t.violentDeathsLabel}`;

  return (
    <div className="group relative flex h-full min-w-0 flex-1 cursor-default flex-col items-center justify-end">
      <div
        className="pointer-events-none absolute bottom-full left-1/2 z-20 mb-1 -translate-x-1/2 whitespace-nowrap rounded-md px-2 py-1 font-sans opacity-0 transition-opacity duration-150 group-hover:opacity-100"
        style={{
          fontSize: 10,
          lineHeight: 1.35,
          background: 'var(--stone-800)',
          color: '#fff',
          boxShadow: '0 2px 8px rgba(20,23,28,.18)',
        }}
      >
        <div style={{ fontWeight: 600 }}>{countLabel}</div>
        <div style={{ opacity: 0.85 }}>{weekLabel}</div>
      </div>
      <div
        className="w-full rounded-t-[2px] transition-[height,filter] duration-300 group-hover:brightness-110"
        style={{
          background: count > 0 ? WEEKLY_BAR_COLOR : 'var(--stone-200)',
          height: `${Math.max(heightPct, 2)}%`,
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------- Stats mode

function StatsMode(props: RightPanelProps) {
  const { t, lang } = useI18n();
  const { allPoints, panelBounds, pointsInView, viewportReady, mapZoom, filters } = props;
  const [typesExpanded, setTypesExpanded] = useState(false);
  const [methodsExpanded, setMethodsExpanded] = useState(false);
  const [placesExpanded, setPlacesExpanded] = useState(false);

  const stats = useMemo(() => computeStats(pointsInView), [pointsInView]);
  const last24h = useMemo(() => computeLast24hStats(pointsInView), [pointsInView]);

  const typeStats = useMemo(
    () => computeStats(pointsInViewExcept(allPoints, filters, panelBounds, 'types')),
    [allPoints, filters, panelBounds]
  );
  const methodStats = useMemo(
    () => computeStats(pointsInViewExcept(allPoints, filters, panelBounds, 'methods')),
    [allPoints, filters, panelBounds]
  );
  const cityMode = mapZoom >= CITY_STATS_ZOOM_THRESHOLD;

  useEffect(() => {
    setPlacesExpanded(false);
  }, [cityMode]);

  const geoStats = useMemo(
    () => computeStats(pointsInViewExcept(allPoints, filters, panelBounds, cityMode ? 'cities' : 'states')),
    [allPoints, filters, panelBounds, cityMode]
  );
  const periodStats = useMemo(
    () => computeStats(pointsInViewExcept(allPoints, filters, panelBounds, 'periods')),
    [allPoints, filters, panelBounds]
  );

  const weeks = useMemo(
    () => buildTrendWeeks(filters.startDate, filters.endDate),
    [filters.startDate, filters.endDate]
  );

  const weekCounts = weeks.map((w) => stats.byWeek[w.key] ?? 0);
  const weekPeak = Math.max(0, ...weekCounts);
  const { scaleMax: weekScaleMax, ticks: weekTicks } = trendChartScale(weekPeak);

  const typeMax = Math.max(1, ...Object.values(typeStats.bySubtype));
  const typeRows = Object.entries(typeStats.bySubtype)
    .sort((a, b) => b[1] - a[1])
    .map(([subtype, count]) => ({ subtype: subtype as HomicideSubtype, count }));

  const methodMax = Math.max(1, ...Object.values(methodStats.byMethod));
  const methodRows = Object.entries(methodStats.byMethod)
    .sort((a, b) => b[1] - a[1])
    .map(([method, count]) => ({ method, count }));

  const placeEntries = Object.entries(cityMode ? geoStats.byCity : geoStats.byState)
    .sort((a, b) => b[1] - a[1]);
  const placeMax = Math.max(1, ...placeEntries.map((x) => x[1]));

  const visibleTypeRows = visibleBarRows(typeRows, (r) => r.subtype, filters.types, typesExpanded);
  const visibleMethodRows = visibleBarRows(methodRows, (r) => r.method, filters.methods, methodsExpanded);
  const visiblePlaceEntries = visibleBarRows(
    placeEntries,
    ([label]) => label,
    cityMode ? filters.cities : filters.states,
    placesExpanded,
  );

  const periodVals = sortPeriods(Object.keys(periodStats.byPeriod));
  const periodMax = Math.max(1, ...periodVals.map((p) => periodStats.byPeriod[p] ?? 0));
  const filterHint = lang === 'pt' ? 'Clique para filtrar' : 'Click to filter';

  return (
    <div className="px-5 pb-[30px] pt-4">
      {/* headline numbers */}
      <div className="mb-5 grid grid-cols-3 gap-[9px]">
        <div className="rounded-xl px-3 py-[11px]" style={{ border: '1px solid var(--stone-200)' }}>
          <div
            className="leading-none"
            style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-.02em', color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}
          >
            {viewportReady ? fmtNumber(stats.total, lang) : '—'}
          </div>
          <div className="mt-[5px] leading-snug lowercase" style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
            {t.events}
          </div>
        </div>
        <div className="rounded-xl px-3 py-[11px]" style={{ border: '1px solid var(--stone-200)' }}>
          <div
            className="leading-none"
            style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-.02em', color: 'var(--red-700)', fontVariantNumeric: 'tabular-nums' }}
          >
            {viewportReady ? fmtNumber(stats.victims, lang) : '—'}
          </div>
          <div className="mt-[5px] leading-snug lowercase" style={{ fontSize: 11, color: 'var(--red-700)', opacity: 0.85 }}>
            {t.victims}
          </div>
        </div>
        <div
          className="relative rounded-xl px-3 py-[11px]"
          style={{ border: '1px solid var(--stone-200)', background: 'var(--red-50)' }}
        >
          <span className="av-live-dot absolute right-2.5 top-2.5" aria-hidden />
          <div
            className="leading-none"
            style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-.02em', color: 'var(--red-700)', fontVariantNumeric: 'tabular-nums' }}
          >
            {viewportReady ? fmtNumber(last24h.victims, lang) : '—'}
          </div>
          <div className="mt-[5px] leading-snug lowercase" style={{ fontSize: 11, color: 'var(--red-700)', opacity: 0.9 }}>
            {t.last24h}
          </div>
        </div>
      </div>

      {/* weekly trend */}
      <SectionLabel>{t.homicideCount}</SectionLabel>
      {weeks.length > 0 ? (
        <>
          <div className="mb-1.5 flex gap-1 pt-6">
            {weekTicks.length > 0 && (
              <div
                className="flex w-[22px] shrink-0 flex-col font-mono tabular-nums"
                style={{
                  height: 74,
                  fontSize: 9.5,
                  color: 'var(--stone-400)',
                  justifyContent: weekTicks.length === 1 ? 'flex-start' : 'space-between',
                }}
              >
                {[...weekTicks].sort((a, b) => b - a).map((v) => (
                  <span key={v}>{fmtNumber(v, lang)}</span>
                ))}
              </div>
            )}
            <div className="relative min-w-0 flex-1 overflow-visible" style={{ height: 74 }}>
              {weekTicks.map((v) => (
                <div
                  key={v}
                  className="pointer-events-none absolute left-0 right-0"
                  style={{
                    bottom: `${(v / weekScaleMax) * 100}%`,
                    borderTop: '1px dashed var(--stone-200)',
                  }}
                />
              ))}
              <div className="relative z-[1] flex h-full items-end gap-px overflow-visible">
                {weeks.map((w) => {
                  const c = stats.byWeek[w.key] ?? 0;
                  const h = Math.round((c / weekScaleMax) * 100);
                  return (
                    <WeekBar
                      key={w.key}
                      weekKey={w.key}
                      count={c}
                      heightPct={h}
                      lang={lang}
                    />
                  );
                })}
              </div>
            </div>
          </div>
          <div className="mb-[26px] flex justify-between font-mono" style={{ fontSize: 9.5, color: 'var(--stone-400)' }}>
            <span>{fmtDateShort(weeks[0].key, lang)}</span>
            <span>{fmtDateShort(weeks[weeks.length - 1].key, lang)}</span>
          </div>
        </>
      ) : (
        <div className="mb-[26px]">
          <EmptyArea />
        </div>
      )}

      {/* by type */}
      <SectionLabel>{t.byType}</SectionLabel>
      <div className="mb-[26px] flex flex-col gap-[5px]">
        {visibleTypeRows.map((r) => (
          <ClickableBarRow
            key={r.subtype}
            label={formatSubtype(r.subtype, lang)}
            count={r.count}
            max={typeMax}
            barColor={FILTER_BAR_COLOR}
            active={filters.types.includes(r.subtype)}
            onClick={() => props.onToggleFilter('types', r.subtype)}
            lang={lang}
            hint={filterHint}
          />
        ))}
        {typeRows.length === 0 && <EmptyArea />}
        <BarExpandToggle
          expanded={typesExpanded}
          total={typeRows.length}
          onToggle={() => setTypesExpanded((v) => !v)}
        />
      </div>

      {/* by method */}
      <SectionLabel>{t.byMethod}</SectionLabel>
      <div className="mb-[26px] flex flex-col gap-[5px]">
        {visibleMethodRows.map((r) => (
          <ClickableBarRow
            key={r.method}
            label={translateMethod(r.method, lang)}
            count={r.count}
            max={methodMax}
            barColor={FILTER_BAR_COLOR}
            active={filters.methods.includes(r.method)}
            onClick={() => props.onToggleFilter('methods', r.method)}
            lang={lang}
            hint={filterHint}
          />
        ))}
        {methodRows.length === 0 && <EmptyArea />}
        <BarExpandToggle
          expanded={methodsExpanded}
          total={methodRows.length}
          onToggle={() => setMethodsExpanded((v) => !v)}
        />
      </div>

      {/* by state or city */}
      <SectionLabel>{cityMode ? t.byCity : t.byState}</SectionLabel>
      <div className="mb-[26px] flex flex-col gap-[5px]">
        {visiblePlaceEntries.map(([label, c]) => (
          <ClickableBarRow
            key={label}
            label={
              cityMode ? (
                label
              ) : (
                <>
                  <span
                    className="mr-1.5 font-mono"
                    style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--stone-400)' }}
                  >
                    {label}
                  </span>
                  {ufName(label)}
                </>
              )
            }
            count={c}
            max={placeMax}
            barColor={FILTER_BAR_COLOR}
            active={cityMode ? filters.cities.includes(label) : filters.states.includes(label)}
            onClick={() => props.onGeoSelect(cityMode ? 'cities' : 'states', label)}
            lang={lang}
            hint={filterHint}
          />
        ))}
        {placeEntries.length === 0 && <EmptyArea />}
        <BarExpandToggle
          expanded={placesExpanded}
          total={placeEntries.length}
          onToggle={() => setPlacesExpanded((v) => !v)}
        />
      </div>

      {/* time of day */}
      {periodVals.length > 0 && (
        <>
          <SectionLabel>{t.timeOfDay}</SectionLabel>
          <div className="grid grid-cols-4 gap-2">
            {periodVals.map((p) => {
              const count = periodStats.byPeriod[p] ?? 0;
              const active = filters.periods.includes(p);
              return (
                <button
                  key={p}
                  type="button"
                  title={filterHint}
                  data-active={active ? 'true' : undefined}
                  onClick={() => props.onToggleFilter('periods', p)}
                  className="av-filter-card rounded-[10px] px-2 py-[10px] text-center font-sans"
                  style={{ fontFamily: 'var(--font-sans)' }}
                >
                  <div
                    className="tabular-nums"
                    style={{ fontSize: 18, fontWeight: 600, color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}
                  >
                    {fmtNumber(count, lang)}
                  </div>
                  <div className="mt-0.5" style={{ fontSize: 10, color: 'var(--color-text-muted)' }}>
                    {translatePeriod(p, lang)}
                  </div>
                  <div className="mt-1.5 h-1 overflow-hidden rounded" style={{ background: 'var(--stone-100)' }}>
                    <div className="h-full" style={{ background: FILTER_BAR_COLOR, width: `${Math.round((count / periodMax) * 100)}%` }} />
                  </div>
                </button>
              );
            })}
          </div>
        </>
      )}
    </div>
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
        {props.viewportReady ? t.feedNote : t.mapLoadingStats}
      </div>
      <div className="flex flex-col gap-2">
        {!props.viewportReady ? (
          <div className="px-2.5 py-[30px] text-center" style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
            {t.mapLoadingStats}
          </div>
        ) : (
        feed.map((e) => {
          const victims = e.v ?? 0;
          const subtype = pointSubtype(e);
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
                  style={{ fontSize: 10, letterSpacing: '.03em', color: '#fff', background: typeColor(subtype) }}
                >
                  {formatSubtype(subtype, lang)}
                </span>
                <span className="font-mono" style={{ fontSize: 11, color: 'var(--stone-400)' }}>
                  {e.d ? fmtDateShort(e.d, lang) : ''}
                </span>
              </div>
              <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--stone-900)', lineHeight: 1.3 }}>
                {formatPointLabel(e, lang)}
                {e.n ? ` — ${e.n}` : ''}
              </div>
              <div className="flex items-center gap-1.5" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                <MapPin className="h-[13px] w-[13px] flex-none" />
                {[e.c, e.st].filter(Boolean).join(' · ')}
                {victims > 0 && ` · ${victims} ${victims > 1 ? t.victimsLower : t.victim}`}
              </div>
            </button>
          );
        })
        )}
        {props.viewportReady && feed.length === 0 && (
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
  const [selectedColumnIds, setSelectedColumnIds] = useState<string[]>(loadSelectedColumnIds);

  useEffect(() => {
    saveSelectedColumnIds(selectedColumnIds);
  }, [selectedColumnIds]);

  const selectedDictionaryFields = useMemo(
    () => new Set(
      EXPORT_COLUMN_GROUPS
        .filter((group) => selectedColumnIds.includes(group.id))
        .map((group) => group.dictionaryField)
    ),
    [selectedColumnIds]
  );
  const visibleDict = useMemo(
    () => dict.filter((row) => selectedDictionaryFields.has(row.field)),
    [dict, selectedDictionaryFields]
  );
  const exportFilters = useMemo(
    () => ({
      types: props.filters.types,
      methods: props.filters.methods,
      periods: props.filters.periods,
      states: props.filters.states,
      cities: props.filters.cities,
      days: 365,
      columns: selectedExportFields(selectedColumnIds),
      startDate: props.filters.startDate || undefined,
      endDate: props.filters.endDate || undefined,
    }),
    [props.filters, selectedColumnIds]
  );

  const exportDateRangeInvalid = Boolean(
    props.filters.startDate &&
      props.filters.endDate &&
      props.filters.startDate > props.filters.endDate
  );

  const toggleColumn = (id: string) => {
    setSelectedColumnIds((current) =>
      current.includes(id)
        ? current.filter((value) => value !== id)
        : [...current, id]
    );
  };

  return (
    <div className="px-5 pb-[30px] pt-4">
      <p className="mb-[18px] text-pretty" style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}>
        {t.dataIntro}
      </p>

      <div className="mb-[18px] rounded-xl p-4" style={{ border: '1px solid var(--stone-200)', background: 'var(--stone-50)' }}>
        <div className="mb-3" style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>
          {t.exportDateRangeOptional}
        </div>
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
              {countSelectedFields(selectedColumnIds)}
            </div>
            <div className="mt-1" style={{ fontSize: 11.5, color: 'var(--color-text-muted)' }}>
              {t.columns}
            </div>
          </div>
        </div>
        {exportDateRangeInvalid ? (
          <div
            className="flex w-full cursor-not-allowed items-center justify-center gap-2 rounded-[10px] p-3"
            style={{ background: 'var(--stone-300)', color: '#fff', fontSize: 14, fontWeight: 500 }}
            title={t.exportDateRangeInvalid}
          >
            <Download className="h-[17px] w-[17px]" />
            {t.downloadCsv}
          </div>
        ) : (
          <a
            href={getExportUrl(exportFilters)}
            download="eventos.csv"
            className="flex w-full items-center justify-center gap-2 rounded-[10px] p-3 transition-colors"
            style={{ background: 'var(--blue-500)', color: '#fff', fontSize: 14, fontWeight: 500 }}
            onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--blue-600)')}
            onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--blue-500)')}
          >
            <Download className="h-[17px] w-[17px]" />
            {t.downloadCsv}
          </a>
        )}
        <div className="mt-2 text-center" style={{ fontSize: 11, color: 'var(--color-text-subtle)' }}>
          {props.hasFilters ? t.dataNote : t.allEvents}
        </div>
      </div>

      <SectionLabel>{t.selectColumns}</SectionLabel>
      <div className="mb-[18px] overflow-hidden rounded-[10px] p-3" style={{ border: '1px solid var(--stone-200)' }}>
        <div className="mb-2 flex gap-2">
          <button
            type="button"
            className="rounded-md px-2 py-1"
            style={{ fontSize: 11, color: 'var(--blue-700)', background: 'var(--stone-100)' }}
            onClick={() => setSelectedColumnIds(DEFAULT_SELECTED_COLUMN_IDS)}
          >
            {t.selectAllColumns}
          </button>
          <button
            type="button"
            className="rounded-md px-2 py-1"
            style={{ fontSize: 11, color: 'var(--stone-600)', background: 'var(--stone-100)' }}
            onClick={() => setSelectedColumnIds([])}
          >
            {t.clearColumnSelection}
          </button>
        </div>
        <div className="grid gap-2">
          {EXPORT_COLUMN_GROUPS.map((group) => {
            const row = dict.find((entry) => entry.field === group.dictionaryField);
            return (
              <label
                key={group.id}
                className="flex cursor-pointer items-start gap-2 rounded-md px-1 py-0.5"
              >
                <input
                  type="checkbox"
                  checked={selectedColumnIds.includes(group.id)}
                  onChange={() => toggleColumn(group.id)}
                  className="mt-0.5"
                />
                <span style={{ fontSize: 12, color: 'var(--stone-700)', lineHeight: 1.35 }}>
                  <span className="font-mono" style={{ color: 'var(--blue-700)' }}>
                    {group.dictionaryField}
                  </span>
                  {row ? ` — ${row.desc}` : ''}
                </span>
              </label>
            );
          })}
        </div>
      </div>

      <SectionLabel>{t.dictionary}</SectionLabel>
      <div className="overflow-hidden rounded-[10px]" style={{ border: '1px solid var(--stone-200)' }}>
        {visibleDict.length === 0 ? (
          <div className="px-3 py-4 text-center" style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
            {t.clearColumnSelection}
          </div>
        ) : (
          visibleDict.map((d) => (
            <div key={d.field} className="flex gap-2.5 px-3 py-[9px]" style={{ borderBottom: '1px solid var(--stone-100)' }}>
              <span className="w-[128px] flex-none break-all font-mono" style={{ fontSize: 11, color: 'var(--blue-700)' }}>
                {d.field}
              </span>
              <span style={{ fontSize: 12, color: 'var(--stone-600)', lineHeight: 1.35 }}>{d.desc}</span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
