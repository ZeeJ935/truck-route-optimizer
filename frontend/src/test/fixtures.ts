import type { AnalysisResponse, Checkpoint, RouteResult } from '../types/api'

export function makeCheckpoint(overrides: Partial<Checkpoint> = {}): Checkpoint {
  return {
    mile: 0,
    lat: 32.78,
    lng: -96.8,
    eta: '2026-11-03T03:00:00Z',
    segment_miles: 12.5,
    weather: { forecast_time: '2026-11-03T03:00:00Z', wind_mph: 12.3, rain_in_per_hour: 0, snow_in_per_hour: 0 },
    risk: 0,
    risk_label: 'Low',
    reasons: [],
    ...overrides,
  }
}

export function makeRoute(rank: number, overrides: Partial<RouteResult> = {}): RouteResult {
  return {
    id: `route-${rank}`,
    rank,
    label: rank === 1 ? 'Recommended' : 'Alternative',
    status: 'SAFE',
    geometry: [
      [-96.8, 32.78],
      [-104.99, 39.74],
    ],
    distance_miles: 800 + rank * 10,
    duration_seconds: 43_200 + rank * 600,
    no_travel_miles: 0,
    severe_miles: 0,
    high_miles: 0,
    average_risk: 0,
    checkpoints: [
      makeCheckpoint({ mile: 0, eta: '2026-11-03T03:00:00Z' }),
      makeCheckpoint({ mile: 25 * rank, eta: '2026-11-03T03:30:00Z' }),
    ],
    ...overrides,
  }
}

export function makeResponse(overrides: Partial<AnalysisResponse> = {}): AnalysisResponse {
  const routes = overrides.routes ?? [makeRoute(1), makeRoute(2), makeRoute(3)]
  return {
    routes,
    recommendation: {
      route_id: routes[0].id,
      reason: 'Fewest Severe miles among the available routes.',
      no_safe_route: false,
    },
    route_notice: null,
    forecast: {
      timestamps: Array.from({ length: 49 }, (_, hour) =>
        new Date(Date.UTC(2026, 10, 3, 3 + hour)).toISOString().replace('.000', ''),
      ),
      corridor: [{ lat: 32.78, lng: -96.8, risk: Array.from({ length: 49 }, () => 0 as const) }],
      available_hours: Array.from({ length: 49 }, (_, hour) => hour),
      notice: null,
    },
    ...overrides,
  }
}

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}
