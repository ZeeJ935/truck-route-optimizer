// FIXTURE scenario: replays a clearly labelled synthetic response
// (e2e/fixtures/FIXTURE-analysis-response.json). These are fixture results, not live data.
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import fixture from '../e2e/fixtures/FIXTURE-analysis-response.json'
import App from './App'
import { jsonResponse } from './test/fixtures'
import { Map as FakeMap } from './test/maplibreFake'

beforeEach(() => {
  FakeMap.instances = []
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse(fixture)))
})

afterEach(() => {
  vi.unstubAllGlobals()
})

async function loadFixture() {
  const user = userEvent.setup()
  render(<App />)
  await user.type(screen.getByLabelText('Origin'), 'FIXTURE origin')
  await user.type(screen.getByLabelText('Destination'), 'FIXTURE destination')
  await user.click(screen.getByRole('button', { name: 'Find the safest route' }))
  await screen.findByRole('region', { name: 'Recommendation' })
  const map = FakeMap.instances.at(-1)!
  await waitFor(() => expect(map.fitBoundsCalls).toHaveLength(1))
  return { user, map }
}

describe('FIXTURE scenario: every route has No Travel miles, partial forecast hours', () => {
  it('is labelled as a fixture', () => {
    expect(fixture._fixture_note).toMatch(/^FIXTURE: synthetic UI test data/)
  })

  it('shows the global warning and "Best available, not safe"', async () => {
    await loadFixture()
    expect(screen.getByText('No safe route for this trip')).toBeInTheDocument()
    const recommendation = screen.getByRole('region', { name: 'Recommendation' })
    expect(within(recommendation).getByText('Best available, not safe')).toBeInTheDocument()
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
  })

  it('draws High, Severe, and No Travel road sections for every route', async () => {
    const { map } = await loadFixture()
    const sections = (map.sources.hazards.data as { features: { properties: { routeId: string; level: number } }[] })
      .features
    expect(new Set(sections.map((section) => section.properties.level))).toEqual(new Set([2, 3, 4]))
    expect(new Set(sections.map((section) => section.properties.routeId))).toEqual(
      new Set(['route-1', 'route-2', 'route-3']),
    )
  })

  it('shows any route summary on the map', async () => {
    const { map } = await loadFixture()
    act(() => {
      map.emit('mousemove', 'routes-hit', {
        point: { x: 0, y: 0 },
        lngLat: { lng: -100, lat: 36 },
        features: [{ properties: { id: 'route-3' } }],
      })
    })
    const text = map.popups.at(-1)!.text
    expect(text).toContain('#3 · Route 3')
    expect(text).toContain('Alternative · Not Safe')
    expect(text).toContain('No Travel 150.0 mi')
  })

  it('disables hours 36-48 and explains why', async () => {
    const { map } = await loadFixture()
    const slider = screen.getByRole('slider', { name: 'Forecast hour after departure' })
    expect(screen.getByText(fixture.forecast.notice)).toBeInTheDocument()
    fireEvent.change(slider, { target: { value: '44' } })
    expect(slider).toHaveValue('35')
    expect(map.filters['corridor-heat']).toEqual(['has', 'h35'])
  })
})
