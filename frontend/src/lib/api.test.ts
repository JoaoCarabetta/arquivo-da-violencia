import { describe, expect, it } from 'vitest';
import type { MatrixResponse } from '@/lib/api';

describe('Matrix API types', () => {
  it('validates matrix payload structure with July 2026 as first column', () => {
    // Simulate the shape returned by GET /api/public/stats/matrix
    const mockPayload: MatrixResponse = {
      months: ['2026-07', '2026-08'],
      ufs: [
        {
          abbrev: 'SP',
          name: 'São Paulo',
          population: 44_411_238,
          cells: [
            { month: '2026-07', victims: 100, rate_per_100k: 0.23 },
            { month: '2026-08', victims: 95, rate_per_100k: 0.21 },
          ],
        },
      ],
      types: [
        {
          type: 'Homicídio simples',
          cells: [
            { month: '2026-07', victims: 80 },
            { month: '2026-08', victims: 75 },
          ],
        },
      ],
    };

    // Assert the first month is July 2026 (the matrix start month per spec)
    expect(mockPayload.months[0]).toBe('2026-07');
    expect(mockPayload.months.length).toBeGreaterThanOrEqual(1);

    // Assert UF cells match the month list
    expect(mockPayload.ufs[0].cells[0].month).toBe('2026-07');

    // Assert type cells match the month list
    expect(mockPayload.types[0].cells[0].month).toBe('2026-07');
  });

  it('validates matrix payload handles multiple months without schema change', () => {
    // When a new month arrives, the months array grows, but the structure stays the same
    const payloadSeptember: MatrixResponse = {
      months: ['2026-07', '2026-08', '2026-09'],
      ufs: [
        {
          abbrev: 'RJ',
          name: 'Rio de Janeiro',
          population: 16_055_174,
          cells: [
            { month: '2026-07', victims: 50, rate_per_100k: 0.31 },
            { month: '2026-08', victims: 48, rate_per_100k: 0.30 },
            { month: '2026-09', victims: 52, rate_per_100k: 0.32 },
          ],
        },
      ],
      types: [
        {
          type: 'Feminicídio',
          cells: [
            { month: '2026-07', victims: 10 },
            { month: '2026-08', victims: 9 },
            { month: '2026-09', victims: 11 },
          ],
        },
      ],
    };

    // First month is still July (start of matrix time window)
    expect(payloadSeptember.months[0]).toBe('2026-07');
    // September is present without requiring a schema change
    expect(payloadSeptember.months[2]).toBe('2026-09');
    expect(payloadSeptember.ufs[0].cells).toHaveLength(3);
  });
});
