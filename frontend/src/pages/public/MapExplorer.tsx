import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams, useLocation } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { FlyToInterpolator } from '@deck.gl/core';
import { Loader2 } from 'lucide-react';
import { fetchMapPoints, fetchPublicStats } from '@/lib/api';
import { useI18n } from '@/contexts/I18nContext';
import { CrimeMap, type MapViewState, type MapBounds, type ViewportSnapshot } from '@/components/map/CrimeMap';
import { LeftRail } from '@/components/portal/LeftRail';
import { SearchCard, type LocatedPlace } from '@/components/portal/SearchCard';
import { RightPanel } from '@/components/portal/RightPanel';
import { AboutModal } from '@/components/portal/AboutModal';
import { MethodologyPanel } from '@/components/portal/MethodologyPanel';
import { DensityLegend } from '@/components/portal/DensityLegend';
import {
  EMPTY_FILTERS,
  applyFilters,
  pointsInBounds,
  distinctValues,
  hasActiveFilters,
  type PortalFilters,
  type PortalMode,
} from '@/components/portal/types';

/** Default map data window — keeps initial payload bounded. */
const MAP_DAYS = 365;

const BRAZIL_VIEW: MapViewState = {
  longitude: -52,
  latitude: -14,
  zoom: 3.6,
  pitch: 0,
  bearing: 0,
};

type FilterGroup = 'types' | 'methods' | 'periods';

const PATH_FOR: Record<PortalMode, string> = {
  stats: '/',
  feed: '/eventos',
  data: '/dados',
};

interface MapExplorerProps {
  initialMode?: PortalMode;
  initialAbout?: boolean;
  initialMethodology?: boolean;
}

export function MapExplorer({
  initialMode = 'stats',
  initialAbout = false,
  initialMethodology = false,
}: MapExplorerProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { id } = useParams();
  const { t } = useI18n();

  const selectedId = id ? Number(id) : null;
  const mode = initialMode;

  const [viewState, setViewState] = useState<MapViewState>(BRAZIL_VIEW);
  const [panelBounds, setPanelBounds] = useState<MapBounds | null>(null);
  const [panelZoom, setPanelZoom] = useState(BRAZIL_VIEW.zoom);
  const [panelLng, setPanelLng] = useState(BRAZIL_VIEW.longitude);
  const [filters, setFilters] = useState<PortalFilters>(EMPTY_FILTERS);
  const [searchedLocation, setSearchedLocation] = useState<{ lat: number; lng: number } | null>(null);
  const [aboutOpen, setAboutOpen] = useState(initialAbout);
  const [methodologyOpen, setMethodologyOpen] = useState(initialMethodology);

  const { data, isLoading } = useQuery({
    queryKey: ['map-points', MAP_DAYS],
    queryFn: () => fetchMapPoints({ days: MAP_DAYS }),
  });

  const { data: publicStats } = useQuery({
    queryKey: ['public-stats'],
    queryFn: fetchPublicStats,
    staleTime: 60_000,
  });

  const sinceDate = publicStats?.since ?? null;

  const allPoints = useMemo(() => data?.points ?? [], [data]);

  const availableTypes = useMemo(() => distinctValues(allPoints, 't'), [allPoints]);
  const availableMethods = useMemo(() => distinctValues(allPoints, 'm'), [allPoints]);
  const availablePeriods = useMemo(() => distinctValues(allPoints, 'p'), [allPoints]);

  const filteredPoints = useMemo(() => applyFilters(allPoints, filters), [allPoints, filters]);
  const pointsInView = useMemo(() => {
    if (!panelBounds) return filteredPoints;
    return pointsInBounds(filteredPoints, panelBounds);
  }, [filteredPoints, panelBounds]);

  const canReset = panelZoom > 4.2 || Math.abs(panelLng - BRAZIL_VIEW.longitude) > 6;
  const filtersActive = hasActiveFilters(filters);

  const handleViewportSettled = useCallback((snapshot: ViewportSnapshot) => {
    setPanelBounds(snapshot.bounds);
    setPanelZoom(snapshot.zoom);
    setPanelLng(snapshot.longitude);
  }, []);

  const toggleFilter = useCallback((group: FilterGroup, value: string) => {
    setFilters((prev) => {
      const cur = prev[group];
      const next = cur.includes(value) ? cur.filter((v) => v !== value) : [...cur, value];
      return { ...prev, [group]: next };
    });
  }, []);

  const clearFilters = useCallback(() => {
    setFilters(EMPTY_FILTERS);
  }, []);

  const onMode = useCallback(
    (next: PortalMode) => {
      navigate(PATH_FOR[next]);
    },
    [navigate]
  );

  const flyTo = useCallback((lat: number, lng: number, zoom: number) => {
    setViewState((prev) => ({
      ...prev,
      longitude: lng,
      latitude: lat,
      zoom,
      transitionDuration: 900,
      transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }),
    }));
  }, []);

  const onSelect = useCallback(
    (eventId: number) => {
      const point = allPoints.find((p) => p.id === eventId);
      if (point) {
        setViewState((prev) => ({
          ...prev,
          longitude: point.lng,
          latitude: point.lat,
          zoom: Math.max(prev.zoom, 12.5),
          transitionDuration: 900,
          transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }),
        }));
      }
      navigate(`/eventos/${eventId}`);
    },
    [allPoints, navigate]
  );

  const onCloseDetail = useCallback(() => {
    navigate(PATH_FOR[mode]);
  }, [navigate, mode]);

  const onLocate = useCallback(
    (place: LocatedPlace) => {
      setSearchedLocation({ lat: place.lat, lng: place.lng });
      flyTo(place.lat, place.lng, place.zoom);
    },
    [flyTo]
  );

  const onCellClick = useCallback(
    (coordinate: [number, number]) => {
      setViewState((prev) => ({
        ...prev,
        longitude: coordinate[0],
        latitude: coordinate[1],
        zoom: Math.min(prev.zoom + 2.5, 13),
        transitionDuration: 900,
        transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }),
      }));
    },
    []
  );

  const onResetView = useCallback(() => {
    setSearchedLocation(null);
    setViewState({
      ...BRAZIL_VIEW,
      transitionDuration: 700,
      transitionInterpolator: new FlyToInterpolator({ speed: 1.4 }),
    });
  }, []);

  const openAbout = useCallback(() => {
    setAboutOpen(true);
    if (location.pathname === '/metodologia') navigate('/');
  }, [location.pathname, navigate]);

  const closeAbout = useCallback(() => {
    setAboutOpen(false);
    if (location.pathname === '/sobre') navigate('/');
  }, [location.pathname, navigate]);

  const openMethodology = useCallback(() => {
    setMethodologyOpen(true);
    if (location.pathname === '/sobre') setAboutOpen(false);
  }, [location.pathname]);

  const closeMethodology = useCallback(() => {
    setMethodologyOpen(false);
    if (location.pathname === '/metodologia') navigate('/');
  }, [location.pathname, navigate]);

  useEffect(() => {
    setAboutOpen(initialAbout);
  }, [initialAbout]);

  useEffect(() => {
    setMethodologyOpen(initialMethodology);
  }, [initialMethodology]);

  return (
    <div
      className="fixed inset-0 flex overflow-hidden"
      style={{ background: 'var(--stone-100)', color: 'var(--color-text)' }}
    >
      <LeftRail mode={mode} onMode={onMode} onAbout={openAbout} onMethodology={openMethodology} />

      <div className="relative min-w-0 flex-1">
        <CrimeMap
          points={filteredPoints}
          viewState={viewState}
          onViewportSettled={handleViewportSettled}
          onPointClick={onSelect}
          onCellClick={onCellClick}
          selectedId={selectedId}
          searchedLocation={searchedLocation}
        />

        {isLoading && (
          <div
            className="absolute inset-0 z-[600] flex items-center justify-center"
            style={{ background: 'var(--stone-100)' }}
          >
            <div className="flex flex-col items-center gap-3.5" style={{ color: 'var(--color-text-muted)' }}>
              <Loader2 className="h-[30px] w-[30px] animate-spin" style={{ color: 'var(--blue-500)' }} />
              <span className="font-mono text-[11px] uppercase tracking-[.1em]">{t.loadingMap}</span>
            </div>
          </div>
        )}

        <SearchCard points={allPoints} onLocate={onLocate} />
        <DensityLegend />
      </div>

      <RightPanel
        mode={mode}
        sinceDate={sinceDate}
        pointsInView={pointsInView}
        filteredCount={filteredPoints.length}
        filters={filters}
        availableTypes={availableTypes}
        availableMethods={availableMethods}
        availablePeriods={availablePeriods}
        onToggleFilter={toggleFilter}
        onClearFilters={clearFilters}
        hasFilters={filtersActive}
        selectedId={selectedId}
        onSelect={onSelect}
        onCloseDetail={onCloseDetail}
        canReset={canReset}
        onResetView={onResetView}
      />

      <AboutModal open={aboutOpen} onClose={closeAbout} onOpenMethodology={openMethodology} />
      <MethodologyPanel open={methodologyOpen} onClose={closeMethodology} />
    </div>
  );
}
