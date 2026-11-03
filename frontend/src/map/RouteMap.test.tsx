import { render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { makeCheckpoint, makeResponse, makeRoute } from '../test/fixtures'
import { Map as FakeMap } from '../test/maplibreFake'
import type { CorridorPoint, RouteResult } from '../types/api'
import { RouteMap } from './RouteMap'

const routes: RouteResult[] = [
  makeRoute(1, {
    distance_miles: 50,
    checkpoints: [
      makeCheckpoint({ mile: 0 }),
      makeCheckpoint({ mile: 25, risk: 2, risk_label: 'High' }),
      makeCheckpoint({ mile: 50, risk: 3, risk_label: 'Severe' }),
    ],
  }),
  makeRoute(2, { checkpoints: [makeCheckpoint({ mile: 0 }), makeCheckpoint({ mile: 50, risk: 4, risk_label: 'No Travel' })] }),
  makeRoute(3, { label: 'Alternative', status: 'CAUTION', severe_miles: 8, high_miles: 41, average_risk: 0.74 }),
]
const corridor: CorridorPoint[] = makeResponse().forecast.corridor

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  FakeMap.instances = []
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

function props(overrides: Partial<Parameters<typeof RouteMap>[0]> = {}) {
  return {
    routes,
    corridor,
    selectedHour: 0,
    selectedRouteId: 'route-1',
    recommendedRouteId: 'route-1',
    tripOffsetMinutes: 300,
    onSelectRoute: vi.fn(),
    ...overrides,
  }
}

async function renderMap(overrides: Partial<Parameters<typeof RouteMap>[0]> = {}) {
  const initial = props(overrides)
  const view = render(<RouteMap {...initial} />)
  const map = FakeMap.instances.at(-1)!
  await waitFor(() => expect(map.fitBoundsCalls).toHaveLength(1))
  const rerender = (next: Partial<Parameters<typeof RouteMap>[0]>) => view.rerender(<RouteMap {...initial} {...next} />)
  return { ...view, map, rerender, onSelectRoute: initial.onSelectRoute }
}

const featureCount = (map: FakeMap, source: string) => (map.sources[source].data as { features: unknown[] }).features.length

describe('RouteMap layers', () => {
  it('stacks the heatmap at the bottom and the selected route above every other route', async () => {
    const { map } = await renderMap()
    expect(map.addSourceCalls).toEqual(['corridor', 'routes', 'hazards', 'checkpoints'])
    expect(map.layers.map((layer) => layer.id)).toEqual([
      'corridor-heat',
      'routes-other-casing',
      'routes-other',
      'hazard-other',
      'checkpoints-other',
      'route-recommended',
      'route-selected-casing',
      'route-selected',
      'hazard-selected-casing',
      'hazard-selected',
      'routes-hit',
      'checkpoints-selected',
    ])
    expect(map.fitBoundsCalls[0][1]).toMatchObject({ padding: { top: 40, right: 48 } })
    expect(map.fitBoundsCalls[0][0]).toEqual([
      [-104.99, 32.78],
      [-96.8, 39.74],
    ])
  })

  it('draws High, Severe, and No Travel sections and checkpoints for every route', async () => {
    const { map } = await renderMap()
    const hazards = (map.sources.hazards.data as { features: { properties: { routeId: string; level: number } }[] })
      .features
    expect(hazards.map((feature) => [feature.properties.routeId, feature.properties.level])).toEqual([
      ['route-1', 2],
      ['route-1', 3],
      ['route-2', 4],
    ])
    expect(featureCount(map, 'checkpoints')).toBe(3 + 2 + 2)
    expect(featureCount(map, 'routes')).toBe(3)
  })

  it('switches routes with filters only: no data rewrite, refit, or request', async () => {
    const { map, rerender } = await renderMap()
    const writes = Object.fromEntries(Object.entries(map.sources).map(([id, source]) => [id, source.setDataCalls]))
    rerender({ selectedRouteId: 'route-2' })
    await waitFor(() => expect(map.filters['route-selected']).toEqual(['==', ['get', 'id'], 'route-2']))
    expect(map.filters['hazard-selected']).toEqual(['==', ['get', 'routeId'], 'route-2'])
    expect(map.filters['hazard-other']).toEqual(['!=', ['get', 'routeId'], 'route-2'])
    expect(map.filters['checkpoints-selected']).toEqual(['==', ['get', 'routeId'], 'route-2'])
    expect(map.filters['checkpoints-other']).toEqual(['!=', ['get', 'routeId'], 'route-2'])
    expect(map.filters['route-recommended']).toEqual([
      'all',
      ['==', ['get', 'id'], 'route-1'],
      ['!=', ['get', 'id'], 'route-2'],
    ])
    for (const [id, source] of Object.entries(map.sources)) expect(source.setDataCalls).toBe(writes[id])
    expect(map.fitBoundsCalls).toHaveLength(1)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('removes the map on unmount', async () => {
    const { map, unmount } = await renderMap()
    unmount()
    expect(map.removed).toBe(true)
  })
})

describe('route summaries on the map', () => {
  const hit = (id: string) => ({ point: { x: 1, y: 1 }, lngLat: { lng: -97, lat: 33 }, features: [{ properties: { id } }] })

  it('shows rank, label, status, distance, time, risk miles, and average risk on hover', async () => {
    const { map } = await renderMap()
    map.emit('mousemove', 'routes-hit', hit('route-3'))
    const popup = map.popups.at(-1)!
    expect(popup.pinned).toBe(false)
    for (const text of ['#3 · Route 3', 'Alternative · Caution', '830.0 mi · 12 h 30 min', 'No Travel 0.0 mi', 'Severe 8.0 mi', 'High 41.0 mi', 'Average risk 0.74']) {
      expect(popup.text).toContain(text)
    }
    map.emit('mouseleave', 'routes-hit')
    expect(popup.removed).toBe(true)
  })

  it('selects the route and pins its summary when its line is clicked', async () => {
    const { map, onSelectRoute } = await renderMap()
    map.emit('click', 'routes-hit', hit('route-3'))
    expect(onSelectRoute).toHaveBeenCalledWith('route-3')
    expect(map.popups.at(-1)!.pinned).toBe(true)
    expect(map.popups.at(-1)!.text).toContain('Route 3')
  })

  it('shows a checkpoint popup for a checkpoint on any route', async () => {
    const { map } = await renderMap()
    map.emit('mousemove', 'checkpoints-other', {
      point: { x: 1, y: 1 },
      lngLat: { lng: -97, lat: 33 },
      features: [{ properties: { routeId: 'route-2', index: 1 } }],
    })
    expect(map.popups.at(-1)!.text).toContain('Route 2 · Mile 50.0')
    expect(map.popups.at(-1)!.text).toContain('Risk: No Travel')
  })
})

describe('heatmap layer', () => {
  it('starts on the selected hour, drawing only hours with data', async () => {
    const { map } = await renderMap({ selectedHour: 0 })
    expect(map.filters['corridor-heat']).toEqual(['has', 'h0'])
  })

  it('changes hour by updating filter and paint only, never the source', async () => {
    const { map, rerender } = await renderMap()
    const corridorWrites = map.sources.corridor.setDataCalls
    const filterCalls = map.setFilterCalls
    for (let hour = 1; hour <= 48; hour++) rerender({ selectedHour: hour })
    await waitFor(() => expect(map.filters['corridor-heat']).toEqual(['has', 'h48']))
    expect(map.paint['corridor-heat']['circle-color']).toEqual(expect.arrayContaining([['get', 'h48']]))
    expect(map.paint['corridor-heat']['circle-opacity']).toEqual(expect.arrayContaining([['get', 'h48']]))
    expect(map.sources.corridor.setDataCalls).toBe(corridorWrites)
    expect(map.setFilterCalls - filterCalls).toBe(48)
    expect(fetchMock).not.toHaveBeenCalled()
  })
})
