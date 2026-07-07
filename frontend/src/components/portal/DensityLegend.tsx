import { useMemo } from 'react';
import type { MapPoint } from '@/lib/api';
import { useI18n } from '@/contexts/I18nContext';
import type { MapBounds } from '@/components/map/CrimeMap';
import {
  SCATTER_ZOOM_THRESHOLD,
  computeGridPeakCount,
  densityLegendScale,
} from '@/components/portal/types';

const GRADIENT =
  'linear-gradient(90deg, rgb(247,198,192) 0%, rgb(224,138,130) 25%, rgb(200,71,63) 55%, rgb(168,55,48) 78%, rgb(135,43,38) 100%)';

interface DensityLegendProps {
  points: MapPoint[];
  bounds: MapBounds | null;
  zoom: number;
}

export function DensityLegend({ points, bounds, zoom }: DensityLegendProps) {
  const { t } = useI18n();

  const { labels } = useMemo(() => {
    const peak = computeGridPeakCount(points, bounds, zoom);
    return densityLegendScale(peak);
  }, [points, bounds, zoom]);

  if (zoom >= SCATTER_ZOOM_THRESHOLD) return null;

  return (
    <div
      className="pointer-events-none absolute bottom-[calc(18px+env(safe-area-inset-bottom,0px))] left-[18px] z-[1200] w-[min(220px,calc(100%-36px))] rounded-xl px-3 py-2.5 shadow-md max-md:bottom-[calc(72px+env(safe-area-inset-bottom,0px))]"
      style={{
        background: 'rgba(255,255,255,0.94)',
        border: '1px solid var(--stone-200)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div className="mb-1.5">
        <div
          className="font-semibold uppercase tracking-[0.06em]"
          style={{ fontSize: 10, color: 'var(--stone-500)' }}
        >
          {t.legendTitle}
        </div>
        <div style={{ fontSize: 10.5, color: 'var(--stone-600)', lineHeight: 1.3 }}>
          {t.legendSubtitle}
        </div>
      </div>
      <div className="h-2.5 w-full rounded-full" style={{ background: GRADIENT }} />
      <div
        className="mt-1 flex justify-between tabular-nums"
        style={{ fontSize: 10, color: 'var(--stone-500)' }}
      >
        {labels.map((value) => (
          <span key={value}>{value}</span>
        ))}
      </div>
    </div>
  );
}
