import { latLngToCell } from 'h3-js';
import type { MapPoint } from '@/lib/api';

export interface H3GridCell {
  hexagon: string;
  count: number;
}

/** Map viewport zoom to a fixed H3 resolution tier. */
export function h3ResolutionForZoom(zoom: number): number {
  if (zoom < 5) return 4;
  if (zoom < 7) return 5;
  if (zoom < 9) return 6;
  return 7;
}

/** Aggregate map points into globally fixed H3 cells at the given resolution. */
export function aggregatePointsToH3Cells(
  points: MapPoint[],
  resolution: number
): H3GridCell[] {
  const counts = new Map<string, number>();
  for (const p of points) {
    const hexagon = latLngToCell(p.lat, p.lng, resolution);
    counts.set(hexagon, (counts.get(hexagon) ?? 0) + (p.v ?? 1));
  }
  return Array.from(counts.entries()).map(([hexagon, count]) => ({ hexagon, count }));
}

/** Peak victim count across aggregated H3 cells. */
export function peakH3Count(cells: H3GridCell[]): number {
  let peak = 0;
  for (const cell of cells) {
    if (cell.count > peak) peak = cell.count;
  }
  return peak;
}

/** Map a cell count to a step in the density color ramp. */
export function colorForH3Count(
  count: number,
  peak: number,
  colorRange: [number, number, number][]
): [number, number, number, number] {
  if (peak <= 0 || count <= 0) {
    const [r, g, b] = colorRange[0];
    return [r, g, b, 198];
  }
  const ratio = Math.min(count / peak, 1);
  const idx = Math.min(colorRange.length - 1, Math.floor(ratio * (colorRange.length - 1)));
  const [r, g, b] = colorRange[idx];
  return [r, g, b, 198];
}
