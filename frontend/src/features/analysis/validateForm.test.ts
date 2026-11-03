import { describe, expect, it } from 'vitest'
import { toLocalInput } from '../../utils/time'
import { toAnalyzeRequest, validateForm, type FormValues } from './validateForm'

const NOW = new Date(2026, 10, 3, 8, 0)

function values(overrides: Partial<FormValues> = {}): FormValues {
  return {
    origin: 'Dallas, TX',
    destination: 'Denver, CO',
    departureLocal: toLocalInput(new Date(2026, 10, 3, 9, 0)),
    loadWeight: '40000',
    interval: '25',
    ...overrides,
  }
}

describe('validateForm', () => {
  it('accepts a valid trip', () => {
    expect(validateForm(values(), NOW)).toEqual({})
  })

  it('requires origin and destination', () => {
    const errors = validateForm(values({ origin: '  ', destination: '' }), NOW)
    expect(errors.origin).toBeDefined()
    expect(errors.destination).toBeDefined()
  })

  it('rejects the same origin and destination text', () => {
    expect(validateForm(values({ destination: ' dallas, tx ' }), NOW).destination).toMatch(/different/)
  })

  it('rejects a departure more than 5 minutes in the past but accepts the grace period', () => {
    const sixMinutesAgo = toLocalInput(new Date(NOW.getTime() - 6 * 60_000))
    const fourMinutesAgo = toLocalInput(new Date(NOW.getTime() - 4 * 60_000))
    expect(validateForm(values({ departureLocal: sixMinutesAgo }), NOW).departure_time).toMatch(/past/)
    expect(validateForm(values({ departureLocal: fourMinutesAgo }), NOW).departure_time).toBeUndefined()
  })

  it('rejects a missing or out-of-range departure', () => {
    expect(validateForm(values({ departureLocal: '' }), NOW).departure_time).toBeDefined()
    const tooFar = toLocalInput(new Date(NOW.getTime() + 17 * 24 * 3600_000))
    expect(validateForm(values({ departureLocal: tooFar }), NOW).departure_time).toMatch(/16 days/)
  })

  it.each(['', '0', '-5', 'abc'])('rejects load %j', (loadWeight) => {
    expect(validateForm(values({ loadWeight }), NOW).load_weight_lb).toBeDefined()
  })

  it.each(['10', '25', '50'])('accepts interval %s', (interval) => {
    expect(validateForm(values({ interval }), NOW).sampling_interval_miles).toBeUndefined()
  })

  it.each(['5', '30', ''])('rejects interval %j', (interval) => {
    expect(validateForm(values({ interval }), NOW).sampling_interval_miles).toBeDefined()
  })
})

describe('toAnalyzeRequest', () => {
  it('builds the API request with an explicit offset', () => {
    const request = toAnalyzeRequest(values({ origin: ' Dallas, TX ', loadWeight: '40000.5', interval: '10' }))
    expect(request).toMatchObject({
      origin: 'Dallas, TX',
      destination: 'Denver, CO',
      load_weight_lb: 40000.5,
      sampling_interval_miles: 10,
    })
    expect(request.departure_time).toMatch(/^2026-11-03T09:00:00[+-]\d{2}:\d{2}$/)
  })
})
