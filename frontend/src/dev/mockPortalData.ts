/**
 * Fake portal data for local UI demos (VITE_MOCK_PORTAL=true).
 * Covers all public homicide subtypes across major cities.
 */

import type { MapPoint, MapPointsResponse, PublicEvent } from '@/lib/api';
import type { HomicideSubtype } from '@/lib/taxonomy';

const SUBTYPES: HomicideSubtype[] = [
  'simples',
  'qualificado',
  'feminicidio',
  'latrocinio',
  'infanticidio',
  'intervencao_policial',
  'morte_transito_doloso',
];

const METHODS = ['Arma de fogo', 'Arma branca', 'Estrangulamento', 'Atropelamento'];
const PERIODS = ['madrugada', 'manhã', 'tarde', 'noite'];

const CITIES: { city: string; st: string; lat: number; lng: number }[] = [
  { city: 'São Paulo', st: 'SP', lat: -23.5505, lng: -46.6333 },
  { city: 'Rio de Janeiro', st: 'RJ', lat: -22.9068, lng: -43.1729 },
  { city: 'Belo Horizonte', st: 'MG', lat: -19.9167, lng: -43.9345 },
  { city: 'Salvador', st: 'BA', lat: -12.9714, lng: -38.5014 },
  { city: 'Fortaleza', st: 'CE', lat: -3.7172, lng: -38.5433 },
  { city: 'Recife', st: 'PE', lat: -8.0476, lng: -34.877 },
  { city: 'Curitiba', st: 'PR', lat: -25.4284, lng: -49.2733 },
  { city: 'Porto Alegre', st: 'RS', lat: -30.0346, lng: -51.2177 },
  { city: 'Brasília', st: 'DF', lat: -15.7939, lng: -47.8828 },
  { city: 'Manaus', st: 'AM', lat: -3.119, lng: -60.0217 },
];

const NEIGHBORHOODS = ['Centro', 'Copacabana', 'Tijuca', 'Boa Viagem', 'Savassi', 'Barra', 'Mooca'];

function pseudoRandom(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

function isoDaysAgo(days: number, hour: number): string {
  const d = new Date();
  d.setUTCDate(d.getUTCDate() - days);
  d.setUTCHours(hour, 30, 0, 0);
  return d.toISOString();
}

function buildPoints(): MapPoint[] {
  const points: MapPoint[] = [];
  let id = 1000;

  for (let i = 0; i < 72; i++) {
    const city = CITIES[i % CITIES.length];
    const subtype = SUBTYPES[i % SUBTYPES.length];
    const r1 = pseudoRandom(i + 1);
    const r2 = pseudoRandom(i + 17);
    const r3 = pseudoRandom(i + 31);

    points.push({
      id: id++,
      lat: city.lat + (r1 - 0.5) * 0.12,
      lng: city.lng + (r2 - 0.5) * 0.12,
      f: 'homicidio',
      su: subtype,
      t: null,
      m: METHODS[i % METHODS.length],
      d: isoDaysAgo(Math.floor(r3 * 280) + 1, i % 24),
      v: 1 + (i % 3),
      s: subtype === 'intervencao_policial' || i % 11 === 0,
      c: city.city,
      n: NEIGHBORHOODS[i % NEIGHBORHOODS.length],
      st: city.st,
      p: PERIODS[i % PERIODS.length],
    });
  }

  return points;
}

const MOCK_POINTS = buildPoints();

const MOCK_EVENTS: Map<number, PublicEvent> = new Map(
  MOCK_POINTS.map((p) => [
    p.id,
    {
      id: p.id,
      title: `Registro de teste — ${p.c}`,
      event_date: p.d,
      time_of_day: p.p,
      state: p.st,
      city: p.c,
      neighborhood: p.n,
      event_family: p.f ?? 'homicidio',
      event_subtype: p.su ?? 'simples',
      homicide_type: null,
      method_of_death: p.m,
      victim_count: p.v,
      victims_summary: p.v === 1 ? '1 vítima' : `${p.v} vítimas`,
      security_force_involved: p.s,
      chronological_description:
        'Dados fictícios para demonstração local do portal. O caso foi gerado automaticamente para testar filtros por subtipo, estatísticas e detalhe do evento.',
      latitude: p.lat,
      longitude: p.lng,
      formatted_address: `${p.n}, ${p.c} — ${p.st}`,
      source_count: 2 + (p.id % 3),
      merged_data: null,
      created_at: p.d ?? new Date().toISOString(),
      sources: [
        {
          id: p.id * 10,
          headline: `Notícia fictícia sobre o caso em ${p.c}`,
          publisher_name: 'Portal de teste',
          url: 'https://example.com/noticia',
          published_at: p.d,
        },
      ],
    },
  ])
);

export function mockMapPoints(): MapPointsResponse {
  return { count: MOCK_POINTS.length, points: MOCK_POINTS };
}

export function mockPublicEventById(id: number): PublicEvent | null {
  return MOCK_EVENTS.get(id) ?? null;
}

export const MOCK_PORTAL_ENABLED = import.meta.env.VITE_MOCK_PORTAL === 'true';
