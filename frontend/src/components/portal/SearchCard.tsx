import { memo, useMemo, useState } from 'react';
import { Search, X, MapPin, Loader2 } from 'lucide-react';
import { useI18n } from '@/contexts/I18nContext';
import { geocode, type MapPoint } from '@/lib/api';
import { ufName } from '@/lib/i18n';
import { fmtNumber } from '@/lib/i18n';
export interface LocatedPlace {
  lat: number;
  lng: number;
  label: string;
  zoom: number;
}

interface SearchCardProps {
  points: MapPoint[];
  onLocate: (place: LocatedPlace) => void;
}

interface Place {
  kind: 'city' | 'uf' | 'hood';
  label: string;
  sub: string;
  lat: number;
  lng: number;
  n: number;
}

function buildPlaces(points: MapPoint[]): Place[] {
  const byCity: Record<string, { label: string; uf: string; lat: number; lng: number; n: number }> = {};
  const byHood: Record<string, { label: string; sub: string; lat: number; lng: number; n: number }> = {};
  const byUf: Record<string, { lat: number; lng: number; n: number }> = {};

  for (const e of points) {
    if (e.c && e.st) {
      const ck = `${e.c}|${e.st}`;
      const c = (byCity[ck] ??= { label: e.c, uf: e.st, lat: 0, lng: 0, n: 0 });
      c.lat += e.lat;
      c.lng += e.lng;
      c.n++;
    }
    if (e.n && e.c) {
      const hk = `${e.n}|${e.c}`;
      const h = (byHood[hk] ??= { label: e.n, sub: `${e.c} · ${e.st ?? ''}`, lat: 0, lng: 0, n: 0 });
      h.lat += e.lat;
      h.lng += e.lng;
      h.n++;
    }
    if (e.st) {
      const u = (byUf[e.st] ??= { lat: 0, lng: 0, n: 0 });
      u.lat += e.lat;
      u.lng += e.lng;
      u.n++;
    }
  }

  const places: Place[] = [];
  for (const c of Object.values(byCity)) {
    places.push({ kind: 'city', label: c.label, sub: c.uf, lat: c.lat / c.n, lng: c.lng / c.n, n: c.n });
  }
  for (const [uf, u] of Object.entries(byUf)) {
    places.push({ kind: 'uf', label: ufName(uf), sub: uf, lat: u.lat / u.n, lng: u.lng / u.n, n: u.n });
  }
  for (const h of Object.values(byHood)) {
    places.push({ kind: 'hood', label: h.label, sub: h.sub, lat: h.lat / h.n, lng: h.lng / h.n, n: h.n });
  }
  return places;
}

const ZOOM_FOR: Record<Place['kind'], number> = { uf: 6.5, city: 11, hood: 13.2 };
const BRAZIL_LOCATE: LocatedPlace = { lat: -14, lng: -52, label: 'Brasil', zoom: 3.6 };

function looksLikeCep(text: string): boolean {
  return /^\d{8}$/.test(text.replace(/\D/g, ''));
}

function isBrazilQuery(text: string): boolean {
  return /^(brasil|brazil)$/i.test(text.trim());
}

export const SearchCard = memo(function SearchCard({ points, onLocate }: SearchCardProps) {
  const { t, lang } = useI18n();
  const [query, setQuery] = useState('');
  const [geocoding, setGeocoding] = useState(false);
  const [geocodeError, setGeocodeError] = useState(false);

  const places = useMemo(() => buildPlaces(points), [points]);

  const q = query.trim().toLowerCase();
  const results = useMemo(() => {
    if (q.length < 1) return [];
    const matched = places.filter(
      (p) =>
        p.label.toLowerCase().includes(q) ||
        p.sub.toLowerCase().includes(q) ||
        (p.kind === 'uf' && p.sub.toLowerCase() === q)
    );
    matched.sort((a, b) => {
      if (a.kind === b.kind) return b.n - a.n;
      const rank = { city: 0, uf: 1, hood: 2 } as const;
      return rank[a.kind] - rank[b.kind];
    });
    return matched.slice(0, 8);
  }, [places, q]);

  const showResults = q.length >= 1;
  const noResults = showResults && results.length === 0;

  function selectPlace(p: Place) {
    setQuery('');
    onLocate({ lat: p.lat, lng: p.lng, label: p.label, zoom: ZOOM_FOR[p.kind] });
  }

  function locateBrazil() {
    setQuery('');
    setGeocodeError(false);
    onLocate(BRAZIL_LOCATE);
  }

  async function geocodeQuery() {
    const raw = query.trim();
    if (!raw) return;
    if (isBrazilQuery(raw)) {
      locateBrazil();
      return;
    }
    setGeocoding(true);
    setGeocodeError(false);
    try {
      const isCep = looksLikeCep(raw);
      const r = await geocode(isCep ? { cep: raw.replace(/\D/g, '') } : { q: raw });
      setQuery('');
      onLocate({ lat: r.latitude, lng: r.longitude, label: r.label, zoom: r.zoom ?? 13 });
    } catch {
      setGeocodeError(true);
    } finally {
      setGeocoding(false);
    }
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    const raw = query.trim();
    if (isBrazilQuery(raw)) {
      locateBrazil();
      return;
    }
    if (looksLikeCep(raw)) {
      geocodeQuery();
      return;
    }
    if (results.length > 0) selectPlace(results[0]);
    else geocodeQuery();
  }

  return (
    <div
      className="overflow-hidden rounded-[14px]"
      style={{
        background: 'var(--color-surface)',
        border: '1px solid var(--color-border)',
        boxShadow: '0 6px 26px rgba(20,23,28,.13)',
      }}
    >
        <div className="px-[15px] pb-[11px] pt-[13px]" style={{ borderBottom: '1px solid var(--stone-100)' }}>
          <div
            style={{
              fontFamily: 'var(--font-serif)',
              fontSize: 18,
              fontWeight: 600,
              letterSpacing: '-.01em',
              color: 'var(--stone-900)',
              lineHeight: 1.25,
            }}
          >
            {t.appTitle}
          </div>
          <div className="mt-0.5 text-pretty" style={{ fontSize: 11.5, color: 'var(--color-text-muted)', lineHeight: 1.4 }}>
            {t.appSubtitle}
          </div>
        </div>

        <div className="relative px-[13px] py-[11px]">
          <form onSubmit={handleSubmit}>
            <div
              className="flex items-center gap-[9px] rounded-[10px] px-3 py-[9px]"
              style={{ background: 'var(--stone-100)', border: '1px solid var(--stone-200)' }}
            >
              {geocoding ? (
                <Loader2 className="h-[17px] w-[17px] shrink-0 animate-spin" style={{ color: 'var(--stone-500)' }} />
              ) : (
                <Search className="h-[17px] w-[17px] shrink-0" style={{ color: 'var(--stone-500)' }} />
              )}
              <input
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setGeocodeError(false);
                }}
                placeholder={t.searchPlaceholder}
                className="min-w-0 flex-1 border-none bg-transparent outline-none"
                style={{ fontFamily: 'var(--font-sans)', fontSize: 14, color: 'var(--stone-900)' }}
              />
              {query.length > 0 && (
                <button
                  type="button"
                  onClick={() => setQuery('')}
                  className="flex border-none bg-transparent p-0"
                  style={{ color: 'var(--stone-400)' }}
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          </form>

          {geocodeError && (
            <p className="mt-2 px-1" style={{ fontSize: 12, color: 'var(--red-700)' }}>
              {t.geocodeFailed}
            </p>
          )}

          {showResults && (
            <div
              className="av-scroll av-fade absolute left-[13px] right-[13px] top-full z-30 mt-[5px] max-h-[300px] overflow-y-auto rounded-[11px]"
              style={{
                background: 'var(--color-surface)',
                border: '1px solid var(--color-border)',
                boxShadow: '0 12px 30px rgba(20,23,28,.16)',
              }}
            >
              {results.map((r, i) => (
                <button
                  key={`${r.kind}-${r.label}-${i}`}
                  onClick={() => selectPlace(r)}
                  className="flex w-full items-center gap-[11px] border-none bg-transparent px-[13px] py-[10px] text-left"
                  style={{ borderBottom: '1px solid var(--stone-100)' }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--stone-50)')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  <span
                    className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-lg"
                    style={{ background: 'var(--blue-50)', color: 'var(--blue-600)' }}
                  >
                    <MapPin className="h-[15px] w-[15px]" />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span
                      className="block overflow-hidden text-ellipsis whitespace-nowrap"
                      style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--stone-900)' }}
                    >
                      {r.label}
                    </span>
                    <span className="block" style={{ fontSize: 11, color: 'var(--color-text-muted)' }}>
                      {r.kind === 'uf' ? t.state : r.sub}
                    </span>
                  </span>
                  <span style={{ fontFamily: 'var(--font-mono)', fontSize: 11, color: 'var(--stone-400)' }}>
                    {fmtNumber(r.n, lang)}
                  </span>
                </button>
              ))}
              {noResults && (
                <button
                  onClick={geocodeQuery}
                  className="w-full border-none bg-transparent px-4 py-4 text-center"
                  style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}
                >
                  {t.noResults}
                </button>
              )}
            </div>
          )}
        </div>
    </div>
  );
});
