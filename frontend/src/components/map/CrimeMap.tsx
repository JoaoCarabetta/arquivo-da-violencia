import { useEffect, useMemo, useRef, useCallback, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { Map } from 'react-map-gl/maplibre';
import { H3HexagonLayer } from '@deck.gl/geo-layers';
import { ScatterplotLayer } from '@deck.gl/layers';
import { cellToLatLng } from 'h3-js';
import {
  WebMercatorViewport,
  type PickingInfo,
  type Layer,
  type MapViewState as DeckViewState,
} from '@deck.gl/core';
import 'maplibre-gl/dist/maplibre-gl.css';
import type { MapPoint } from '@/lib/api';
import {
  aggregatePointsToH3Cells,
  colorForH3Count,
  h3ResolutionForZoom,
  peakH3Count,
  type H3GridCell,
} from '@/lib/h3Grid';
import { capPoints, pointsInBounds, SCATTER_ZOOM_THRESHOLD } from '@/components/portal/types';
import { useI18n } from '@/contexts/I18nContext';
import { formatPointLabel } from '@/lib/taxonomy';

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
  /** Called when the viewport stops moving (debounced). Drives panel stats. */
  onViewportSettled?: (snapshot: ViewportSnapshot) => void;
  onPointClick: (id: number) => void;
  onCellClick?: (coordinate: [number, number]) => void;
  selectedId?: number | null;
  searchedLocation?: { lat: number; lng: number } | null;
}

const DEFAULT_MAP_STYLE = 'https://basemaps.cartocdn.com/gl/positron-gl-style/style.json';
const MAP_STYLE = import.meta.env.VITE_MAP_STYLE || DEFAULT_MAP_STYLE;

const COLOR_RANGE: [number, number, number][] = [
  [247, 198, 192],
  [224, 138, 130],
  [200, 71, 63],
  [168, 55, 48],
  [135, 43, 38],
];

/** Debounce panel stats updates — avoids recomputing RightPanel on every zoom frame. */
const BOUNDS_DEBOUNCE_MS = 200;
/** Skip viewport culling below this count (cheaper to pass all points). */
const CULL_MIN_POINTS = 1500;

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

function expandBounds(bounds: MapBounds, padding: number): MapBounds {
  const [[minLng, minLat], [maxLng, maxLat]] = bounds;
  const padLng = (maxLng - minLng) * padding;
  const padLat = (maxLat - minLat) * padding;
  return [
    [minLng - padLng, minLat - padLat],
    [maxLng + padLng, maxLat + padLat],
  ];
}

function cullPointsToBounds(points: MapPoint[], bounds: MapBounds | null): MapPoint[] {
  if (!bounds || points.length < CULL_MIN_POINTS) return points;
  return pointsInBounds(points, expandBounds(bounds, 0.25));
}

function viewStateKey(vs: MapViewState): string {
  return `${vs.longitude},${vs.latitude},${vs.zoom},${vs.transitionDuration ?? 0}`;
}

export function CrimeMap({
  points,
  viewState: viewStateProp,
  onViewportSettled,
  onPointClick,
  onCellClick,
  selectedId,
  searchedLocation,
}: CrimeMapProps) {
  const { lang, t } = useI18n();
  const containerRef = useRef<HTMLDivElement>(null);
  const sizeRef = useRef<{ width: number; height: number }>({ width: 0, height: 0 });
  const [hasSize, setHasSize] = useState(false);
  const settleTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const onViewportSettledRef = useRef(onViewportSettled);
  const onPointClickRef = useRef(onPointClick);
  const onCellClickRef = useRef(onCellClick);
  const externalViewKeyRef = useRef(viewStateKey(viewStateProp));

  // Local view state keeps zoom/pan off the React root — MapExplorer no longer
  // re-renders RightPanel on every animation frame.
  const [localViewState, setLocalViewState] = useState<MapViewState>(viewStateProp);
  const [renderBounds, setRenderBounds] = useState<MapBounds | null>(null);

  onViewportSettledRef.current = onViewportSettled;
  onPointClickRef.current = onPointClick;
  onCellClickRef.current = onCellClick;

  // Sync programmatic moves (flyTo, cell click, event select) from parent.
  useEffect(() => {
    const key = viewStateKey(viewStateProp);
    if (key !== externalViewKeyRef.current) {
      externalViewKeyRef.current = key;
      setLocalViewState(viewStateProp);
    }
  }, [viewStateProp]);

  const showScatter = localViewState.zoom >= SCATTER_ZOOM_THRESHOLD;
  const gridZoom = Math.floor(localViewState.zoom);
  const h3Resolution = h3ResolutionForZoom(gridZoom);

  const emitViewportSettled = useCallback((vs: MapViewState) => {
    if (!onViewportSettledRef.current) return;
    const bounds = boundsFromView(vs, sizeRef.current);
    if (!bounds) return;
    setRenderBounds(bounds);
    onViewportSettledRef.current({
      bounds,
      zoom: vs.zoom,
      longitude: vs.longitude,
    });
  }, []);

  const scheduleViewportSettled = useCallback(
    (vs: MapViewState) => {
      if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
      settleTimerRef.current = setTimeout(() => emitViewportSettled(vs), BOUNDS_DEBOUNCE_MS);
    },
    [emitViewportSettled]
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const update = () => {
      const width = el.clientWidth;
      const height = el.clientHeight;
      sizeRef.current = { width, height };
      setHasSize(width > 0 && height > 0);
      emitViewportSettled(localViewState);
    };
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      ro.disconnect();
      if (settleTimerRef.current) clearTimeout(settleTimerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [emitViewportSettled]);

  // Layer data updates on viewport settle (not every zoom frame).
  const culledGridPoints = useMemo(
    () => (showScatter ? [] : cullPointsToBounds(points, renderBounds)),
    [points, showScatter, renderBounds]
  );

  const aggregatedCells = useMemo(
    () => (showScatter ? [] : aggregatePointsToH3Cells(culledGridPoints, h3Resolution)),
    [culledGridPoints, showScatter, h3Resolution]
  );

  const gridPeakCount = useMemo(() => peakH3Count(aggregatedCells), [aggregatedCells]);

  const scatterData = useMemo(() => {
    if (!showScatter) return [];
    return capPoints(cullPointsToBounds(points, renderBounds));
  }, [points, showScatter, renderBounds]);

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
        new H3HexagonLayer<H3GridCell>({
          id: 'events-grid',
          data: aggregatedCells,
          getHexagon: (d) => d.hexagon,
          getFillColor: (d) => colorForH3Count(d.count, gridPeakCount, COLOR_RANGE),
          extruded: false,
          pickable: true,
          opacity: 0.78,
          highPrecision: true,
          updateTriggers: {
            getFillColor: [gridPeakCount],
          },
          onClick: (info: PickingInfo) => {
            const cell = info.object as H3GridCell | undefined;
            if (cell?.hexagon) {
              const [lat, lng] = cellToLatLng(cell.hexagon);
              onCellClickRef.current?.([lng, lat]);
            }
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
  }, [aggregatedCells, scatterData, showScatter, gridPeakCount, searchedLocation, selectedId]);

  return (
    <div ref={containerRef} className="absolute inset-0">
      {!hasSize ? null : (
      <DeckGL
        viewState={localViewState as unknown as DeckViewState}
        controller={true}
        layers={layers}
        onViewStateChange={(params) => {
          const vs = params.viewState as unknown as MapViewState;
          setLocalViewState(vs);
          scheduleViewportSettled(vs);
        }}
        getTooltip={({ object }: PickingInfo) => {
          if (!object) return null;
          if (showScatter) {
            const p = object as MapPoint;
            return {
              text: [formatPointLabel(p, lang), [p.n, p.c, p.st].filter(Boolean).join(', ')]
                .filter(Boolean)
                .join('\n'),
            };
          }
          const cell = object as H3GridCell;
          const count = cell.count ?? 0;
          const unit = count === 1 ? t.victim : t.victimsLower;
          return { text: `${count} ${unit}` };
        }}
      >
        <Map mapStyle={MAP_STYLE} />
      </DeckGL>
      )}
    </div>
  );
}
