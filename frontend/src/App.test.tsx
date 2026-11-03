import { act, fireEvent, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { jsonResponse, makeCheckpoint, makeResponse, makeRoute } from './test/fixtures'
import type { AnalysisResponse } from './types/api'

let fetchMock: ReturnType<typeof vi.fn>

beforeEach(() => {
  fetchMock = vi.fn()
  vi.stubGlobal('fetch', fetchMock)
})

afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
})

async function submitTrip(reply: Response | (() => Promise<Response>)) {
  fetchMock.mockImplementationOnce(typeof reply === 'function' ? reply : () => Promise.resolve(reply))
  const user = userEvent.setup()
  render(<App />)
  await user.type(screen.getByLabelText('Origin'), 'Dallas, TX')
  await user.type(screen.getByLabelText('Destination'), 'Denver, CO')
  await user.click(screen.getByRole('button', { name: 'Find the safest route' }))
  return user
}

async function showResults(body: AnalysisResponse) {
  const user = await submitTrip(jsonResponse(body))
  await screen.findByRole('region', { name: 'Recommendation' })
  return user
}

describe('form and errors', () => {
  it('blocks submission when frontend validation fails', async () => {
    const user = userEvent.setup()
    render(<App />)
    await user.clear(screen.getByLabelText('Load weight (lb)'))
    await user.type(screen.getByLabelText('Load weight (lb)'), '0')
    await user.click(screen.getByRole('button', { name: 'Find the safest route' }))
    expect(screen.getByLabelText('Origin')).toHaveAccessibleDescription('Enter an origin.')
    expect(screen.getByLabelText('Load weight (lb)')).toHaveAccessibleDescription(
      'Load weight must be a number greater than 0.',
    )
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('sends the departure with an explicit UTC offset', async () => {
    await showResults(makeResponse())
    const body = JSON.parse(fetchMock.mock.calls[0][1].body)
    expect(body.departure_time).toMatch(/T\d{2}:\d{2}:00[+-]\d{2}:\d{2}$/)
    expect(body).toMatchObject({ origin: 'Dallas, TX', destination: 'Denver, CO', load_weight_lb: 40000 })
  })

  it('shows backend field errors under the matching inputs', async () => {
    await submitTrip(
      jsonResponse(
        {
          error: {
            code: 'validation_error',
            message: 'Please correct the highlighted fields.',
            fields: { departure_time: 'Departure is beyond the weather forecast range.' },
          },
        },
        400,
      ),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('Please correct the highlighted fields.')
    expect(screen.getByLabelText('Departure')).toHaveAccessibleDescription(
      'Departure is beyond the weather forecast range.',
    )
  })

  it.each([
    ['geocoding_failed', 422, '"Nowhere" could not be found.'],
    ['no_route_found', 422, 'No truck route was found between these locations.'],
    ['forecast_unavailable', 422, 'No weather forecast is available at mile 40.0.'],
    ['provider_rate_limited', 503, 'The weather service is receiving too many requests. Please wait about a minute.'],
    ['provider_timeout', 504, 'A data provider took too long to respond.'],
    ['provider_error', 502, 'A data provider returned an unexpected response.'],
    ['internal_error', 500, 'Something went wrong while analyzing the trip.'],
  ])('shows the backend message for %s', async (code, status, message) => {
    await submitTrip(jsonResponse({ error: { code, message } }, status))
    expect(await screen.findByRole('alert')).toHaveTextContent(message)
    expect(screen.queryByRole('region', { name: 'Recommendation' })).not.toBeInTheDocument()
  })

  it('explains a network failure', async () => {
    await submitTrip(() => Promise.reject(new TypeError('Failed to fetch')))
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the server.')
  })
})

describe('rendering backend decisions', () => {
  it('shows the backend status, label, order, and reason without recalculating them', async () => {
    // Values chosen so a frontend recalculation would disagree: route-1 is "SAFE" with
    // Severe miles, and the backend ranks a slower, riskier-looking route second.
    const routes = [
      makeRoute(1, { status: 'SAFE', severe_miles: 8, high_miles: 41, average_risk: 0.74, duration_seconds: 90_000 }),
      makeRoute(2, { label: 'Backup option', status: 'CAUTION', severe_miles: 0, duration_seconds: 3_600 }),
    ]
    await showResults(
      makeResponse({
        routes,
        recommendation: { route_id: 'route-1', reason: 'Custom backend reason.', no_safe_route: false },
      }),
    )

    const recommendation = screen.getByRole('region', { name: 'Recommendation' })
    expect(within(recommendation).getByText('Recommended')).toBeInTheDocument()
    expect(within(recommendation).getByText('Route 1')).toBeInTheDocument()
    expect(within(recommendation).getByText('Safe')).toBeInTheDocument()
    expect(within(recommendation).getByText('Custom backend reason.')).toBeInTheDocument()

    const cards = within(screen.getByRole('region', { name: 'Route comparison' })).getAllByRole('button')
    expect(cards.map((card) => card.getAttribute('aria-label'))).toEqual([
      'Route 1, Recommended',
      'Route 2, Backup option',
    ])
    expect(within(cards[0]).getByText('Safe')).toBeInTheDocument()
    expect(within(cards[0]).getByText('8.0 mi')).toBeInTheDocument()
    expect(within(cards[0]).getByText('41.0 mi')).toBeInTheDocument()
    expect(within(cards[0]).getByText('0.74')).toBeInTheDocument()
    expect(within(cards[1]).getByText('Caution')).toBeInTheDocument()
  })

  it('shows every route metric', async () => {
    await showResults(
      makeResponse({
        routes: [
          makeRoute(1, {
            no_travel_miles: 0.1,
            severe_miles: 2.5,
            high_miles: 12,
            average_risk: 1.05,
            distance_miles: 883.4,
            duration_seconds: 43_872,
          }),
        ],
      }),
    )
    const card = within(screen.getByRole('region', { name: 'Route comparison' })).getByRole('button')
    for (const text of ['#1', 'Route 1', 'Recommended', '883.4 mi · 12 h 11 min', '0.1 mi', '2.5 mi', '12.0 mi', '1.05']) {
      expect(card).toHaveTextContent(text)
    }
  })

  it('shows the global warning only when the backend says no route is safe', async () => {
    await showResults(makeResponse({ routes: [makeRoute(1, { no_travel_miles: 3, status: 'NOT_SAFE' })] }))
    expect(screen.queryByText('No safe route for this trip')).not.toBeInTheDocument()
  })

  it('uses "Best available, not safe" instead of "Recommended" in the warning state', async () => {
    const routes = [
      makeRoute(1, { label: 'Best available, not safe', status: 'NOT_SAFE', no_travel_miles: 3 }),
      makeRoute(2, { status: 'NOT_SAFE', no_travel_miles: 9 }),
    ]
    await showResults(
      makeResponse({
        routes,
        recommendation: { route_id: 'route-1', reason: 'Fewest No Travel miles among the available routes.', no_safe_route: true },
      }),
    )
    expect(screen.getByText('No safe route for this trip')).toBeInTheDocument()
    const recommendation = screen.getByRole('region', { name: 'Recommendation' })
    expect(within(recommendation).getByText('Best available, not safe')).toBeInTheDocument()
    expect(screen.queryByText('Recommended')).not.toBeInTheDocument()
  })

  it('shows the route notice when fewer than 3 routes are returned', async () => {
    await showResults(
      makeResponse({
        routes: [makeRoute(1), makeRoute(2)],
        route_notice: 'Only 2 distinct routes were available for this trip.',
      }),
    )
    expect(screen.getByRole('note')).toHaveTextContent('Only 2 distinct routes were available for this trip.')
  })

  it('shows checkpoints with ETA in the trip offset, weather, risk, and reasons', async () => {
    const checkpoint = makeCheckpoint({
      mile: 47.5,
      eta: '2026-11-03T05:10:00Z',
      weather: { forecast_time: '2026-11-03T05:00:00Z', wind_mph: 47, rain_in_per_hour: 0.02, snow_in_per_hour: 0 },
      risk: 4,
      risk_label: 'No Travel',
      reasons: ['No Travel: wind 47 mph with load over 30,000 lb.'],
    })
    await showResults(makeResponse({ routes: [makeRoute(1, { checkpoints: [checkpoint] })] }))
    const list = screen.getByRole('region', { name: 'Checkpoints for Route 1' })
    expect(list).toHaveTextContent('Mile 47.5')
    expect(list).toHaveTextContent(/ETA \w{3} \d{1,2}, \d{2}:\d{2} UTC[+-]\d{2}:\d{2}/)
    expect(list).toHaveTextContent('Wind 47 mph · Rain 0.02 in/hr · Snow 0 in/hr')
    expect(within(list).getByText('No Travel')).toBeInTheDocument()
    expect(list).toHaveTextContent('No Travel: wind 47 mph with load over 30,000 lb.')
  })

  it('switches the selected route without another request', async () => {
    const user = await showResults(makeResponse())
    expect(screen.getByRole('region', { name: 'Checkpoints for Route 1' })).toBeInTheDocument()
    const routeTwo = screen.getByRole('button', { name: 'Route 2, Alternative' })
    await user.click(routeTwo)
    expect(routeTwo).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('region', { name: 'Checkpoints for Route 2' })).toHaveTextContent('Mile 50.0')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})

describe('waiting state', () => {
  it('shows real elapsed time and explains a slow server start, with no percentages', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: false })
    fetchMock.mockReturnValueOnce(new Promise(() => {}))
    render(<App />)
    fireEvent.change(screen.getByLabelText('Origin'), { target: { value: 'Dallas, TX' } })
    fireEvent.change(screen.getByLabelText('Destination'), { target: { value: 'Denver, CO' } })
    fireEvent.click(screen.getByRole('button', { name: 'Find the safest route' }))

    const status = screen.getByRole('status')
    expect(status).toHaveTextContent('Analyzing routes and weather… 0 s')
    expect(status).not.toHaveTextContent('waking up')
    expect(screen.getByRole('button', { name: 'Analyzing…' })).toBeDisabled()

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10_000)
    })
    expect(status).toHaveTextContent('10 s')
    expect(status).toHaveTextContent('The server may be waking up after being idle. This can take up to a minute.')
    expect(status).not.toHaveTextContent('%')
  })
})
