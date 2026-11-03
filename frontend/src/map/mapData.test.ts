import { describe, expect, it } from 'vitest'
import { makeCheckpoint, makeRoute } from '../test/fixtures'
import type { RiskLevel, RouteResult } from '../types/api'
import {
  allCheckpointFeatures,
  checkpointFeatures,
  heatmapFeatures,
  hourKey,
  routeSummaryPopup,
  checkpointPopup,
  cumulativeMiles,
  hazardSections,
  representedRanges,
  routeFeatures,
  routesBounds,
  sliceLine,
  type LngLat,
} from './mapData'

// A straight line north along a meridian: 100 vertices, about 1 mile apart.
const NORTH: LngLat[] = Array.from({ length: 101 }, (_, i) => [-97, 32 + i / 69.09] as LngLat)

function routeWith(risks: RiskLevel[], miles: number[], distance = 100): RouteResult {
  return makeRoute(1, {
    geometry: NORTH,
    distance_miles: distance,
    checkpoints: miles.map((mile, i) => makeCheckpoint({ mile, risk: risks[i], risk_label: String(risks[i]) })),
  })
}

describe('cumulativeMiles', () => {
  it('ends at the route length the backend reported', () => {
    const totals = cumulativeMiles(NORTH, 103)
    expect(totals[0]).toBe(0)
    expect(totals[totals.length - 1]).toBeCloseTo(103, 9)
  })
})

describe('representedRanges', () => {
  it('uses midpoints between neighbouring checkpoints, like the backend', () => {
    const route = routeWith([0, 0, 0, 0], [0, 25, 50, 73], 73)
    expect(representedRanges(route.checkpoints, 73)).toEqual([
      [0, 12.5],
      [12.5, 37.5],
      [37.5, 61.5],
      [61.5, 73],
    ])
  })
})

describe('hazardSections', () => {
  it('returns nothing when every checkpoint is Low or Moderate', () => {
    expect(hazardSections(routeWith([0, 1, 1, 0, 0], [0, 25, 50, 75, 100])).features).toEqual([])
  })

  it('marks High as well as Severe and No Travel sections', () => {
    const sections = hazardSections(routeWith([0, 2, 1, 3, 4], [0, 25, 50, 75, 100])).features
    expect(sections.map((feature) => feature.properties.level)).toEqual([2, 3, 4])
  })

  it('covers exactly the represented range of each hazardous checkpoint', () => {
    const route = routeWith([0, 3, 0, 4, 0], [0, 25, 50, 75, 100])
    const sections = hazardSections(route).features.map((feature) => feature.properties)
    expect(sections).toEqual([
      { routeId: 'route-1', level: 3, fromMile: 12.5, toMile: 37.5 },
      { routeId: 'route-1', level: 4, fromMile: 62.5, toMile: 87.5 },
    ])
  })

  it('includes the first and last checkpoints up to the route ends', () => {
    const sections = hazardSections(routeWith([4, 0, 0, 0, 3], [0, 25, 50, 75, 100])).features
    expect(sections.map((feature) => feature.properties)).toEqual([
      { routeId: 'route-1', level: 4, fromMile: 0, toMile: 12.5 },
      { routeId: 'route-1', level: 3, fromMile: 87.5, toMile: 100 },
    ])
    expect(sections[0].geometry.coordinates[0]).toEqual(NORTH[0])
    expect(sections[1].geometry.coordinates.at(-1)).toEqual(NORTH.at(-1))
  })

  it('merges neighbouring sections of the same level', () => {
    const sections = hazardSections(routeWith([0, 3, 3, 4, 0], [0, 25, 50, 75, 100])).features
    expect(sections.map((feature) => feature.properties)).toEqual([
      { routeId: 'route-1', level: 3, fromMile: 12.5, toMile: 62.5 },
      { routeId: 'route-1', level: 4, fromMile: 62.5, toMile: 87.5 },
    ])
  })

  it('slices the drawn line at the right places', () => {
    const totals = cumulativeMiles(NORTH, 100)
    const line = sliceLine(NORTH, totals, 12.5, 37.5)
    expect(line[0][1]).toBeCloseTo(NORTH[0][1] + (NORTH[100][1] - NORTH[0][1]) * 0.125, 6)
    expect(line.at(-1)![1]).toBeCloseTo(NORTH[0][1] + (NORTH[100][1] - NORTH[0][1]) * 0.375, 6)
    expect(line.length).toBeGreaterThan(20)
  })
})

describe('features and bounds', () => {
  it('builds one line per route and marks the recommended one', () => {
    const routes = [makeRoute(1), makeRoute(2)]
    const features = routeFeatures(routes, 'route-2').features
    expect(features.map((feature) => feature.properties)).toEqual([
      { id: 'route-1', rank: 1, recommended: false },
      { id: 'route-2', rank: 2, recommended: true },
    ])
  })

  it('builds checkpoint points with the backend risk', () => {
    const route = routeWith([0, 4], [0, 50], 50)
    expect(checkpointFeatures(route).features.map((feature) => feature.properties)).toEqual([
      { routeId: 'route-1', index: 0, risk: 0, mile: 0 },
      { routeId: 'route-1', index: 1, risk: 4, mile: 50 },
    ])
  })

  it('builds checkpoints for every route, tagged with routeId', () => {
    const features = allCheckpointFeatures([makeRoute(1), makeRoute(2)]).features
    expect(features.map((feature) => feature.properties.routeId)).toEqual(['route-1', 'route-1', 'route-2', 'route-2'])
  })

  it('bounds every route', () => {
    expect(routesBounds([makeRoute(1)])).toEqual([
      [-104.99, 32.78],
      [-96.8, 39.74],
    ])
    expect(routesBounds([])).toBeNull()
  })
})

describe('checkpointPopup', () => {
  it('shows ETA with an offset label, weather, risk, and reasons from the backend', () => {
    const checkpoint = makeCheckpoint({
      mile: 47.5,
      eta: '2026-11-03T05:10:00Z',
      weather: { forecast_time: '2026-11-03T05:00:00Z', wind_mph: 47, rain_in_per_hour: 0.02, snow_in_per_hour: 0 },
      risk: 4,
      risk_label: 'No Travel',
      reasons: ['No Travel: wind 47 mph with load over 30,000 lb.'],
    })
    const popup = checkpointPopup(makeRoute(2), checkpoint, 300)
    expect(popup.title).toBe('Route 2 · Mile 47.5')
    expect(popup.risk).toBe('No Travel')
    expect(popup.lines).toEqual([
      'ETA Nov 3, 10:10 UTC+05:00',
      'Forecast hour Nov 3, 10:00 UTC+05:00',
      'Wind 47 mph',
      'Rain 0.02 in/hr',
      'Snow 0 in/hr',
    ])
    expect(popup.reasons).toEqual(['No Travel: wind 47 mph with load over 30,000 lb.'])
  })
})

describe('routeSummaryPopup', () => {
  it('shows the backend summary for a route', () => {
    const route = makeRoute(2, {
      label: 'Alternative',
      status: 'NOT_SAFE',
      distance_miles: 883.4,
      duration_seconds: 43_872,
      no_travel_miles: 0.1,
      severe_miles: 8,
      high_miles: 41,
      average_risk: 0.74,
    })
    expect(routeSummaryPopup(route)).toEqual({
      title: '#2 · Route 2',
      label: 'Alternative',
      status: 'Not Safe',
      lines: ['883.4 mi · 12 h 11 min', 'No Travel 0.1 mi', 'Severe 8.0 mi', 'High 41.0 mi', 'Average risk 0.74'],
    })
  })
})

describe('heatmapFeatures', () => {
  it('stores each hour as a flat property, keeping 0 and omitting null', () => {
    const risk = Array.from({ length: 49 }, (_, hour) => (hour === 5 ? null : hour === 6 ? 0 : hour % 5)) as (
      | 0
      | 1
      | 2
      | 3
      | 4
      | null
    )[]
    const [feature] = heatmapFeatures([{ lat: 32.9, lng: -97.2, risk }]).features
    expect(feature.geometry.coordinates).toEqual([-97.2, 32.9])
    expect(hourKey(5) in feature.properties).toBe(false)
    expect(feature.properties[hourKey(6)]).toBe(0)
    expect(feature.properties[hourKey(4)]).toBe(4)
    expect(Object.keys(feature.properties)).toHaveLength(48)
  })
})
