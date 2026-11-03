import { render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Map as FakeMap } from '../test/maplibreFake'
import { makeCheckpoint, makeRoute } from '../test/fixtures'
import { RouteMap } from './RouteMap'

const routes = [
  makeRoute(1, {
    checkpoints: [makeCheckpoint({ mile: 0 }), makeCheckpoint({ mile: 25, risk: 3, risk_label: 'Severe' })],
    distance_miles: 50,
  }),
  makeRoute(2),
  makeRoute(3),
]

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  FakeMap.instances = []
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function renderMap(selectedRouteId: string, onSelectRoute = vi.fn()) {
  const view = render(
    <RouteMap
      routes={routes}
      selectedRouteId={selectedRouteId}
      recommendedRouteId="route-1"
      tripOffsetMinutes={300}
      onSelectRoute={onSelectRoute}
    />,
  )
  const map = FakeMap.instances.at(-1)!
  await waitFor(() => expect(map.fitBoundsCalls).toHaveLength(1))
  return { ...view, map, onSelectRoute }
}

describe('RouteMap', () => {
  it('adds the route, hazard, and checkpoint layers and fits the view to the routes', async () => {
    const { map } = await renderMap('route-1')
    expect(map.addSourceCalls).toEqual(['routes', 'hazards', 'checkpoints'])
    expect(map.layers.map((layer) => layer.id)).toEqual([
      'routes-other-casing',
      'routes-other',
      'route-recommended',
      'route-selected-casing',
      'route-selected',
      'hazard-casing',
      'hazard-line',
      'routes-hit',
      'checkpoints',
    ])
    expect(map.fitBoundsCalls[0][0]).toEqual([
      [-104.99, 32.78],
      [-96.8, 39.74],
    ])
    expect((map.sources.routes.data as { features: unknown[] }).features).toHaveLength(3)
  })

  it('emphasises the selected route and shows its hazards and checkpoints', async () => {
    const { map } = await renderMap('route-1')
    expect(map.filters['route-selected']).toEqual(['==', ['get', 'id'], 'route-1'])
    expect(map.filters['routes-other']).toEqual(['!=', ['get', 'id'], 'route-1'])
    expect((map.sources.hazards.data as { features: unknown[] }).features).toHaveLength(1)
    expect((map.sources.checkpoints.data as { features: unknown[] }).features).toHaveLength(2)
  })

  it('switches routes by changing filters only: no refetch, no new source, no refit', async () => {
    const { map, rerender, onSelectRoute } = await renderMap('route-1')
    const routeDataWrites = map.sources.routes.setDataCalls
    rerender(
      <RouteMap
        routes={routes}
        selectedRouteId="route-2"
        recommendedRouteId="route-1"
        tripOffsetMinutes={300}
        onSelectRoute={onSelectRoute}
      />,
    )
    await waitFor(() => expect(map.filters['route-selected']).toEqual(['==', ['get', 'id'], 'route-2']))
    expect(map.filters['route-recommended']).toEqual([
      'all',
      ['==', ['get', 'id'], 'route-1'],
      ['!=', ['get', 'id'], 'route-2'],
    ])
    expect((map.sources.hazards.data as { features: unknown[] }).features).toHaveLength(0)
    expect(map.sources.routes.setDataCalls).toBe(routeDataWrites)
    expect(map.addSourceCalls).toHaveLength(3)
    expect(map.fitBoundsCalls).toHaveLength(1)
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('selects a route when its line is clicked', async () => {
    const { map, onSelectRoute } = await renderMap('route-1')
    map.emit('click', 'routes-hit', { point: { x: 1, y: 1 }, features: [{ properties: { id: 'route-3' } }] })
    expect(onSelectRoute).toHaveBeenCalledWith('route-3')
  })

  it('removes the map on unmount', async () => {
    const { map, unmount } = await renderMap('route-1')
    unmount()
    expect(map.removed).toBe(true)
  })
})
