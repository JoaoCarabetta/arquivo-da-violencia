import { useQuery } from '@tanstack/react-query';
import {
  ChevronLeft,
  Clock,
  ExternalLink,
  FileText,
  MapPin,
} from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { fetchPublicEventById } from '@/lib/api';
import { trackEvent } from '@/lib/analytics';
import {
  dictionaryLabel,
  formatCoordinates,
  formatCount,
  formatRecordDate,
  formatSubtypeSlug,
  hasDetailValue,
  resolveSourceUrl,
  sourceHeadline,
  translateLocationPrecisionLabel,
} from '@/lib/eventDetail';
import {
  fmtDateLong,
  fmtDateShort,
  fmtNumber,
  translateMethod,
  translatePeriod,
  ufName,
} from '@/lib/i18n';
import {
  formatTaxonomyFields,
  taxonomyColor,
} from '@/lib/taxonomy';

const EYEBROW =
  'font-mono text-[9.5px] uppercase tracking-[.12em] text-[color:var(--color-text-subtle)]';

function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <div className={`${EYEBROW} mb-[11px]`}>
      {children}
    </div>
  );
}

function DetailFieldRow({ label, value }: { label: string; value: React.ReactNode }) {
  if (value == null || value === '') return null;
  return (
    <div className="flex gap-2.5 px-[13px] py-[11px]" style={{ borderBottom: '1px solid var(--stone-100)' }}>
      <div className="w-[118px] flex-none font-mono" style={{ fontSize: 10, color: 'var(--color-text-subtle)', lineHeight: 1.35 }}>
        {label}
      </div>
      <div className="min-w-0 flex-1" style={{ fontSize: 13, color: 'var(--stone-800)', lineHeight: 1.4 }}>
        {value}
      </div>
    </div>
  );
}

function DetailCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-[18px] overflow-hidden rounded-[10px]" style={{ border: '1px solid var(--stone-200)' }}>
      {children}
    </div>
  );
}

interface EventDetailViewProps {
  id: number;
  onClose: () => void;
}

export function EventDetailView({ id, onClose }: EventDetailViewProps) {
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

  const typeLabel = formatTaxonomyFields(
    event.event_family,
    event.event_subtype,
    event.homicide_type,
    lang
  );
  const tColor = taxonomyColor(event.event_family, event.event_subtype, event.homicide_type);
  const place = [event.neighborhood, event.city].filter(Boolean).join(', ');
  const cityLine = [event.city, ufName(event.state)].filter(Boolean).join(' · ');
  const countryLine = [event.country, event.state ? ufName(event.state) : null].filter(Boolean).join(' · ');
  const articles = event.sources ?? [];
  const showSources = event.source_count > 0 || articles.length > 0;
  const srcCount = event.source_count ?? 0;
  const sourceWord = srcCount === 1 ? t.newsSource : t.newsSources;
  const coords = formatCoordinates(event.latitude, event.longitude);

  const hasVictimsSection =
    hasDetailValue(event.victim_count) ||
    hasDetailValue(event.victims_summary) ||
    hasDetailValue(event.perpetrator_count) ||
    hasDetailValue(event.method_of_death);

  const hasLocationSection =
    hasDetailValue(event.formatted_address) ||
    hasDetailValue(event.street) ||
    hasDetailValue(event.neighborhood) ||
    hasDetailValue(event.city) ||
    hasDetailValue(event.state) ||
    hasDetailValue(event.country) ||
    hasDetailValue(coords) ||
    hasDetailValue(event.location_precision) ||
    hasDetailValue(event.time_of_day);

  const hasRecordSection =
    hasDetailValue(event.id) ||
    hasDetailValue(event.event_family) ||
    hasDetailValue(event.event_subtype) ||
    hasDetailValue(event.homicide_type) ||
    hasDetailValue(event.created_at) ||
    hasDetailValue(event.updated_at);

  return (
    <div className="av-fade px-5 pb-7 pt-[18px]">
      <button
        onClick={onClose}
        className="mb-4 inline-flex min-h-11 items-center gap-1.5 border-none bg-transparent px-1 py-2"
        style={{ color: 'var(--blue-600)', fontFamily: 'var(--font-sans)', fontSize: 13, fontWeight: 500 }}
      >
        <ChevronLeft className="h-4 w-4" />
        {t.back}
      </button>

      <div className="mb-[13px] flex flex-wrap gap-2">
        <span
          className="inline-flex items-center gap-1.5 rounded-md px-[9px] py-1 font-mono uppercase"
          style={{ fontSize: 10.5, letterSpacing: '.04em', color: '#fff', background: tColor }}
        >
          {typeLabel}
        </span>
        {event.security_force_involved && (
          <span
            className="inline-flex items-center gap-1.5 rounded-md px-2 py-[3px] font-mono uppercase"
            style={{ fontSize: 10.5, letterSpacing: '.04em', color: 'var(--gold-700)', background: 'var(--gold-50)', border: '1px solid var(--gold-500)' }}
          >
            {t.securityForce}
          </span>
        )}
      </div>

      <h2
        className="mb-1.5"
        style={{ fontFamily: 'var(--font-serif)', fontSize: 23, lineHeight: 1.18, fontWeight: 600, letterSpacing: '-.01em', color: 'var(--stone-900)' }}
      >
        {event.title || `${typeLabel}${event.neighborhood ? ` — ${event.neighborhood}` : ''}`}
      </h2>
      <div className="mb-[18px]" style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>
        {event.event_date ? fmtDateLong(event.event_date, lang) : ''}
      </div>

      {hasVictimsSection && (
        <>
          <SectionLabel>{t.detailVictims}</SectionLabel>
          <div className="mb-[18px] grid grid-cols-2 gap-2.5">
            {hasDetailValue(event.victim_count) && (
              <div className="rounded-[10px] px-[13px] py-[11px]" style={{ background: 'var(--stone-50)', border: '1px solid var(--stone-200)' }}>
                <div className="mb-[3px] font-mono text-[9px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
                  {t.victims}
                </div>
                <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--red-600)', fontVariantNumeric: 'tabular-nums' }}>
                  {fmtNumber(event.victim_count ?? 0, lang)}
                </div>
              </div>
            )}
            {hasDetailValue(event.method_of_death) && (
              <div className="rounded-[10px] px-[13px] py-[11px]" style={{ background: 'var(--stone-50)', border: '1px solid var(--stone-200)' }}>
                <div className="mb-[3px] font-mono text-[9px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
                  {t.method}
                </div>
                <div style={{ fontSize: 14, fontWeight: 500, color: 'var(--stone-900)', lineHeight: 1.3 }}>
                  {translateMethod(event.method_of_death, lang)}
                </div>
              </div>
            )}
            {hasDetailValue(event.perpetrator_count) && (
              <div className="rounded-[10px] px-[13px] py-[11px]" style={{ background: 'var(--stone-50)', border: '1px solid var(--stone-200)' }}>
                <div className="mb-[3px] font-mono text-[9px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
                  {t.detailPerpetrators}
                </div>
                <div style={{ fontSize: 22, fontWeight: 600, color: 'var(--stone-900)', fontVariantNumeric: 'tabular-nums' }}>
                  {fmtNumber(event.perpetrator_count ?? 0, lang)}
                </div>
              </div>
            )}
          </div>
          {hasDetailValue(event.victims_summary) && (
            <p className="mb-[18px] text-pretty" style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}>
              <span className="mb-1 block font-mono text-[9px] uppercase tracking-[.1em]" style={{ color: 'var(--color-text-subtle)' }}>
                {t.detailVictimsSummary}
              </span>
              {event.victims_summary}
            </p>
          )}
        </>
      )}

      {hasLocationSection && (
        <>
          <SectionLabel>{t.detailLocation}</SectionLabel>
          <DetailCard>
            {(hasDetailValue(event.formatted_address) || hasDetailValue(place)) && (
              <div className="flex gap-2.5 px-[13px] py-[11px]" style={{ borderBottom: '1px solid var(--stone-100)' }}>
                <MapPin className="mt-px h-4 w-4 flex-none" style={{ color: 'var(--stone-500)' }} />
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--stone-900)' }}>
                    {event.formatted_address || place || '—'}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
                    {cityLine || countryLine}
                  </div>
                </div>
              </div>
            )}
            <DetailFieldRow label={t.detailStreet} value={event.street} />
            <DetailFieldRow label={dictionaryLabel('neighborhood', lang)} value={event.neighborhood} />
            <DetailFieldRow label={dictionaryLabel('city', lang)} value={event.city} />
            <DetailFieldRow label={t.state} value={event.state ? `${event.state} · ${ufName(event.state)}` : null} />
            <DetailFieldRow label={t.detailCountry} value={event.country} />
            <DetailFieldRow
              label={t.detailCoordinates}
              value={coords ? <span className="font-mono tabular-nums">{coords}</span> : null}
            />
            <DetailFieldRow
              label={dictionaryLabel('location_precision', lang)}
              value={translateLocationPrecisionLabel(event.location_precision, lang)}
            />
            {event.time_of_day && (
              <div className="flex gap-2.5 px-[13px] py-[11px]">
                <Clock className="mt-px h-4 w-4 flex-none" style={{ color: 'var(--stone-500)' }} />
                <div>
                  <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--stone-900)' }}>
                    {translatePeriod(event.time_of_day, lang)}
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{t.timeNote}</div>
                </div>
              </div>
            )}
          </DetailCard>
        </>
      )}

      {event.chronological_description && (
        <>
          <SectionLabel>{t.summary}</SectionLabel>
          <p className="mb-[18px] text-pretty" style={{ fontSize: 14, lineHeight: 1.6, color: 'var(--stone-700)' }}>
            {event.chronological_description}
          </p>
        </>
      )}

      {showSources && (
        <>
          <SectionLabel>{t.sourcesSection}</SectionLabel>
          {articles.length > 0 && srcCount > 0 && articles.length !== srcCount && (
            <p className="mb-2" style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.4 }}>
              {t.sourcesCountMismatch}
            </p>
          )}
          {articles.length > 0 ? (
            <ul className="mb-[18px] flex flex-col overflow-hidden rounded-[10px]" style={{ border: '1px solid var(--stone-200)' }}>
              {articles.map((source) => {
                const url = resolveSourceUrl(source);
                const title = sourceHeadline(source, t.sourceFallback);
                const showPublisher = Boolean(source.publisher_name && source.headline);
                const content = (
                  <>
                    <div style={{ fontSize: 13.5, fontWeight: 500, color: url ? 'var(--blue-600)' : 'var(--stone-900)', lineHeight: 1.35 }}>
                      {title}
                    </div>
                    {showPublisher && (
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{source.publisher_name}</div>
                    )}
                    {source.published_at && (
                      <div style={{ fontSize: 11.5, color: 'var(--color-text-subtle)' }}>
                        {fmtDateShort(source.published_at, lang)}
                      </div>
                    )}
                    {!url && (
                      <div style={{ fontSize: 11.5, color: 'var(--color-text-subtle)' }}>{t.sourceNoLink}</div>
                    )}
                  </>
                );

                return (
                  <li key={source.id} style={{ borderBottom: '1px solid var(--stone-100)' }} className="last:border-b-0">
                    {url ? (
                      <a
                        href={url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-start gap-2.5 px-[13px] py-[11px] no-underline transition-colors hover:bg-[var(--stone-50)]"
                        onClick={() => trackEvent('source_click', { event_id: id })}
                      >
                        <ExternalLink className="mt-0.5 h-4 w-4 flex-none" style={{ color: 'var(--blue-600)' }} />
                        <div className="min-w-0 flex-1">{content}</div>
                      </a>
                    ) : (
                      <div className="flex items-start gap-2.5 px-[13px] py-[11px]">
                        <FileText className="mt-0.5 h-4 w-4 flex-none" style={{ color: 'var(--stone-500)' }} />
                        <div className="min-w-0 flex-1">{content}</div>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          ) : (
            <div
              className="mb-[18px] rounded-[10px] px-[13px] py-[11px]"
              style={{ border: '1px solid var(--stone-200)', fontSize: 13, color: 'var(--color-text-muted)' }}
            >
              {t.sourcesCountMismatch}
            </div>
          )}
        </>
      )}

      {hasRecordSection && (
        <>
          <SectionLabel>{t.detailRecord}</SectionLabel>
          <DetailCard>
            <DetailFieldRow label={dictionaryLabel('id', lang)} value={formatCount(event.id, lang)} />
            <DetailFieldRow label={dictionaryLabel('event_family', lang)} value={event.event_family} />
            <DetailFieldRow
              label={dictionaryLabel('event_subtype', lang)}
              value={formatSubtypeSlug(event.event_subtype, lang)}
            />
            <DetailFieldRow label={dictionaryLabel('homicide_type', lang)} value={event.homicide_type} />
            <DetailFieldRow
              label={dictionaryLabel('event_date', lang)}
              value={formatRecordDate(event.event_date, lang)}
            />
            <DetailFieldRow
              label={dictionaryLabel('created_at', lang)}
              value={formatRecordDate(event.created_at, lang)}
            />
            <DetailFieldRow
              label={dictionaryLabel('updated_at', lang)}
              value={formatRecordDate(event.updated_at, lang)}
            />
          </DetailCard>
        </>
      )}

      {srcCount > 0 && (
        <div
          className="flex items-center gap-2 pt-3.5"
          style={{ borderTop: '1px solid var(--stone-100)', fontSize: 12, color: 'var(--color-text-muted)' }}
        >
          <FileText className="h-[15px] w-[15px]" />
          {`${t.reportedBy}${srcCount}${sourceWord} · #${event.id}`}
        </div>
      )}
    </div>
  );
}
