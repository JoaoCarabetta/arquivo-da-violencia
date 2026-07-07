import { describe, expect, it } from 'vitest';
import { latLngToCell } from 'h3-js';
import type { MapPoint } from '@/lib/api';
import {
  aggregatePointsToH3Cells,
  h3ResolutionForZoom,
  peakH3Count,
} from '@/lib/h3Grid';
import { computeGridPeakCount, pointsForHexGrid } from '@/components/portal/types';

function point(lat: number, lng: number, v = 1, id = 1): MapPoint {
  return {
    id,
    lat,
    lng,
    t: null,
    m: null,
    d: null,
    v,
    s: null,
    c: null,
    n: null,
    st: null,
    p: null,
  };
}

describe('h3ResolutionForZoom', () => {
  it('maps zoom tiers to fixed H3 resolutions', () => {
    expect(h3ResolutionForZoom(3.9)).toBe(4);
    expect(h3ResolutionForZoom(4)).toBe(4);
    expect(h3ResolutionForZoom(5)).toBe(5);
    expect(h3ResolutionForZoom(6.9)).toBe(5);
    expect(h3ResolutionForZoom(7)).toBe(6);
    expect(h3ResolutionForZoom(8.9)).toBe(6);
    expect(h3ResolutionForZoom(9)).toBe(7);
    expect(h3ResolutionForZoom(11)).toBe(7);
  });
});

describe('aggregatePointsToH3Cells', () => {
  it('maps the same lat/lng to the same H3 index at a given resolution', () => {
    const resolution = 7;
    const p = point(-23.55, -46.63, 2, 1);
    const cells = aggregatePointsToH3Cells([p], resolution);
    expect(cells).toHaveLength(1);
    expect(cells[0].hexagon).toBe(latLngToCell(p.lat, p.lng, resolution));
    expect(cells[0].count).toBe(2);
  });

  it('sums victim counts for points in the same cell', () => {
    const resolution = 8;
    const baseLat = -22.9068;
    const baseLng = -43.1729;
    const cells = aggregatePointsToH3Cells(
      [
        point(baseLat, baseLng, 1, 1),
        point(baseLat + 0.0001, baseLng + 0.0001, 3, 2),
      ],
      resolution
    );
    expect(cells).toHaveLength(1);
    expect(cells[0].count).toBe(4);
  });

  it('reports peak count across cells', () => {
    const resolution = 6;
    const cells = aggregatePointsToH3Cells(
      [
        point(-23.55, -46.63, 2, 1),
        point(-22.9, -43.2, 5, 2),
      ],
      resolution
    );
    expect(peakH3Count(cells)).toBe(5);
  });
});

describe('pointsForHexGrid', () => {
  it('returns empty when bounds are not ready', () => {
    const points = [point(-23.55, -46.63, 2, 1)];
    expect(pointsForHexGrid(points, null)).toEqual([]);
  });

  it('excludes out-of-bounds points so hex counts stay viewport-scoped', () => {
    const bounds: [[number, number], [number, number]] = [
      [-47, -24],
      [-43, -22],
    ];
    const inView = point(-23.55, -46.63, 5, 1);
    const outOfView = point(-10, -50, 99, 2);
    const resolution = h3ResolutionForZoom(8);

    const scoped = pointsForHexGrid([inView, outOfView], bounds);
    const cells = aggregatePointsToH3Cells(scoped, resolution);

    expect(scoped).toHaveLength(1);
    expect(cells).toHaveLength(1);
    expect(cells[0].count).toBe(5);
  });
});

describe('computeGridPeakCount', () => {
  it('matches manual H3 aggregation for in-view points', () => {
    const zoom = 8;
    const bounds: [[number, number], [number, number]] = [
      [-47, -24],
      [-43, -22],
    ];
    const points = [
      point(-23.55, -46.63, 2, 1),
      point(-23.56, -46.64, 4, 2),
      point(-10, -50, 99, 3),
    ];
    const resolution = h3ResolutionForZoom(zoom);
    const inView = points.filter(
      (p) =>
        p.lng >= bounds[0][0] &&
        p.lng <= bounds[1][0] &&
        p.lat >= bounds[0][1] &&
        p.lat <= bounds[1][1]
    );
    const expected = peakH3Count(aggregatePointsToH3Cells(inView, resolution));
    expect(computeGridPeakCount(points, bounds, zoom)).toBe(expected);
  });
});
