import { useEffect, useMemo, useRef, useCallback } from 'react';
import DeckGL from '@deck.gl/react';
import { Map } from 'react-map-gl/maplibre';
import { GridLayer } from '@deck.gl/aggregation-layers';
import { ScatterplotLayer } from '@deck.gl/layers';
import {
  WebMercatorViewport,
  type PickingInfo,
  type Layer,
  type MapViewState as DeckViewState,
} from '@deck.gl/core';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapPoint } from '@/lib/api';
import { capPoints, pointsInBounds } from '@/components/portal/types';

export interface MapViewState {
  longitude: number;
  latitude: number;
  zoom: number;
  pitch?: number;
  bearing?: number;
  transitionDuration?: number;
  transitionInterpolator?: unknown;
}

/** [[minLng, minLat], [maxLng, maxLat]] */
export type MapBounds = [[number, number], [number, number]];

export interface ViewportSnapshot {
  bounds: MapBounds;
  zoom: number;
  longitude: number;
}

interface CrimeMapProps {
  points: MapPoint[];
  viewState: MapViewState;
  onViewStateChange: (vs: MapViewState) => void;
  /** Debounced (~100ms) — drives panel stats, not map rendering. */
  onViewportSettled?: (snapshot: ViewportSnapshot) => void;
  onPointClick: (id: number) => void;
  onCellClick?: (coordinate: [number, number]) => void;
  selectedId?: number | null;
  searchedLocation?: { lat: number; lng: number } | null;
}

const DEFAULT_MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty';
const MAP_STYLE = import.meta.env.VITE_MAP_STYLE || DEFAULT_MAP_STYLE;

const COLOR_RANGE: [number, number, number][] = [
  [247, 198, 192],
  [224, 138, 130],
  [200, 71, 63],
  [168, 55, 48],
  [135, 43, 38],
];

const BOUNDS_DEBOUNCE_MS = 100;
const SCATTER_ZOOM_THRESHOLD = 12;

function cellSizeForZoom(zoom: number): number {
  if (zoom < 5) return 40000;
  if (zoom < 7) return 15000;
  if (zoom < 9) return 5000;
  return 1500;
}

function boundsFromView(
  vs: MapViewState,
  size: { width: number; height: number }
): MapBounds | null {
  if (!size.width || !size.height) return null;
  try {
    const vp = new WebMercatorViewport({
      width: size.width,
      height: size.height,
      longitude: vs.longitude,
      latitude: vs.latitude,
      zoom: vs.zoom,
    });
    const [minLng, minLat, maxLng, maxLat] = vp.getBounds();
    return [
      [minLng, minLat],
      [maxLng, maxLat],
    ];
  } catch {
    return null;
  }
}

export function CrimeMap({
  points,
  viewState,
  onViewStateChange,
  onViewportSettled,
  onPointClick,
  onCellClick,
  selectedId,
  searchedLocation,
}: CrimeMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef<{ width: number; height: number }>({ width: 0, height: 0 });
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onViewportSettledRef = useRef(onViewportSettled);
  const onPointClickRef = useRef(onPointClick);
  const onCellClickRef = useRef(onCellClick);

  onViewportSettledRef.current = onViewportSettled;
  onPointClickRef.current = onPointClick;
  onCellClickRef.current = onCellClick;

  const showScatter = viewState.zoom >= SCATTER_ZOOM_THRESHOLD;
  const gridZoom = Math.floor(viewState.zoom);

  const scheduleViewportSettled = useCallback((vs: MapViewState) => {
    if (!onViewportSettledRef.current) return;
    const bounds = boundsFromView(vs, sizeRef.current);
    if (!bounds) return;

    if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
    settleTimerRef.current = setTimeout(() => {
      onViewportSettledRef.current?.({
        bounds,
        zoom: vs.zoom,
        longitude: vs.longitude,
      });
    }, BOUNDS_DEBOUNCE_MS);
  }, []);

  const emitViewportSettledImmediate = useCallback((vs: MapViewState) => {
    if (!onViewportSettledRef.current) return;
    const bounds = boundsFromView(vs, sizeRef.current);
    if (!bounds) return;
    onViewportSettledRef.current({
      bounds,
      zoom: vs.zoom,
      longitude: vs.longitude,
    });
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      sizeRef.current = { width: el.clientWidth, height: el.clientHeight };
      emitViewportSettledImmediate(viewState);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emitViewportSettledImmediate]);

  const scatterData = useMemo(() => {
    if (!showScatter) return [];
    const bounds = boundsFromView(viewState, sizeRef.current);
    if (!bounds) return [];
    return capPoints(pointsInBounds(points, bounds));
  }, [points, showScatter, viewState.longitude, viewState.latitude, viewState.zoom]);

  const layers = useMemo(() => {
    const result: Layer[] = [];

    if (showScatter) {
      result.push(
        new ScatterplotLayer<MapPoint>({
          id: 'events-scatter',
          data: scatterData,
          getPosition: (d) => [d.lng, d.lat],
          getRadius: (d) => 4 + Math.min(d.v ?? 1, 5) * 1.6,
          radiusUnits: 'pixels',
          radiusMinPixels: 3,
          getFillColor: (d) =>
            d.id === selectedId ? [47, 102, 207, 235] : [200, 71, 63, 225],
          getLineColor: (d) => (d.id === selectedId ? [27, 68, 144, 255] : [255, 255, 255, 220]),
          lineWidthUnits: 'pixels',
          getLineWidth: (d) => (d.id === selectedId ? 2.5 : 1.2),
          stroked: true,
          pickable: true,
          updateTriggers: {
            getFillColor: [selectedId],
            getLineColor: [selectedId],
            getLineWidth: [selectedId],
          },
          onClick: (info: PickingInfo) => {
            if (info.object) onPointClickRef.current((info.object as MapPoint).id);
            return true;
          },
        })
      );
    } else {
      result.push(
        new GridLayer<MapPoint>({
          id: 'events-grid',
          data: points,
          getPosition: (d) => [d.lng, d.lat],
          cellSize: cellSizeForZoom(gridZoom),
          colorRange: COLOR_RANGE,
          extruded: false,
          pickable: true,
          opacity: 0.78,
          onClick: (info: PickingInfo) => {
            if (info.coordinate) onCellClickRef.current?.(info.coordinate as [number, number]);
            return true;
          },
        })
      );
    }

    if (searchedLocation) {
      result.push(
        new ScatterplotLayer<{ lat: number; lng: number }>({
          id: 'search-marker',
          data: [searchedLocation],
          getPosition: (d) => [d.lng, d.lat],
          getRadius: 9,
          radiusUnits: 'pixels',
          getFillColor: [47, 102, 207, 255],
          getLineColor: [255, 255, 255, 255],
          lineWidthUnits: 'pixels',
          getLineWidth: 2,
          stroked: true,
          pickable: false,
        })
      );
    }

    return result;
  }, [points, scatterData, showScatter, gridZoom, searchedLocation, selectedId]);

  return (
    <div ref={containerRef} className="absolute inset-0">
      <DeckGL
        viewState={viewState as unknown as DeckViewState}
        controller={true}
        layers={layers}
        onViewStateChange={(params) => {
          const vs = params.viewState as unknown as MapViewState;
          onViewStateChange(vs);
          scheduleViewportSettled(vs);
        }}
        getTooltip={({ object }: PickingInfo) => {
          if (!object) return null;
          if (showScatter) {
            const p = object as MapPoint;
            return {
              text: [p.t || 'Evento', [p.n, p.c, p.st].filter(Boolean).join(', ')]
                .filter(Boolean)
                .join('\n'),
            };
          }
          const count = (object as { points?: unknown[] }).points?.length ?? 0;
          return { text: `${count} ${count === 1 ? 'evento' : 'eventos'}` };
        }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>
    </div>
  );
}
