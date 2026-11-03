import { describe, expect, it } from 'vitest'
import { defaultDepartureInput, formatOffset, formatTripTime, offsetFromIso, offsetLabel } from './time'

describe('offsets', () => {
  it.each([
    [300, '+05:00'],
    [330, '+05:30'],
    [-210, '-03:30'],
    [-300, '-05:00'],
    [0, '+00:00'],
  ])('formats %i minutes as %s', (minutes, text) => {
    expect(formatOffset(minutes)).toBe(text)
    expect(offsetLabel(minutes)).toBe(`UTC${text}`)
  })

  it.each([
    ['2026-11-03T08:00:00+05:00', 300],
    ['2026-11-03T08:00:00-03:30', -210],
    ['2026-11-03T08:00:00+00:00', 0],
    ['2026-11-03T08:00:00Z', 0],
  ])('reads the offset of %s', (iso, minutes) => {
    expect(offsetFromIso(iso)).toBe(minutes)
  })
})

describe('formatTripTime', () => {
  it('shows a UTC time in the trip offset with a label', () => {
    expect(formatTripTime('2026-11-03T08:30:00Z', 300)).toBe('Nov 3, 13:30 UTC+05:00')
    expect(formatTripTime('2026-11-03T02:15:00Z', -360)).toBe('Nov 2, 20:15 UTC-06:00')
    expect(formatTripTime('2026-11-03T22:00:00Z', 330)).toBe('Nov 4, 03:30 UTC+05:30')
  })
})

describe('defaultDepartureInput', () => {
  it('is one hour ahead, rounded up to 5 minutes', () => {
    expect(defaultDepartureInput(new Date(2026, 10, 3, 8, 2, 30))).toBe('2026-11-03T09:05')
    expect(defaultDepartureInput(new Date(2026, 10, 3, 8, 10))).toBe('2026-11-03T09:10')
  })
})
