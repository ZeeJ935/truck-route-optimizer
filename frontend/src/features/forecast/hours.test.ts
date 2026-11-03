import { describe, expect, it } from 'vitest'
import { firstAvailableHour, missingHourRanges, snapToAvailable } from './hours'

const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, i) => from + i)
const allHours = new Set(range(0, 48))
const partial = new Set([...range(0, 9), ...range(14, 35)]) // 10-13 and 36-48 have no data

describe('snapToAvailable', () => {
  it('keeps an available hour as is', () => {
    expect(snapToAvailable(17, 16, allHours)).toBe(17)
    expect(snapToAvailable(0, 3, partial)).toBe(0)
  })

  it('never selects an hour without data: it skips ahead in the direction of movement', () => {
    expect(snapToAvailable(10, 9, partial)).toBe(14) // moving up past the gap
    expect(snapToAvailable(13, 14, partial)).toBe(9) // moving down past the gap
  })

  it('falls back the other way when nothing is available in that direction', () => {
    expect(snapToAvailable(36, 35, partial)).toBe(35)
    expect(snapToAvailable(48, 20, partial)).toBe(35) // End key
    expect(snapToAvailable(0, 20, new Set([5, 6]))).toBe(5) // Home key
  })

  it('clamps to the 0-48 range and returns null when no hour has data', () => {
    expect(snapToAvailable(60, 40, allHours)).toBe(48)
    expect(snapToAvailable(-3, 2, allHours)).toBe(0)
    expect(snapToAvailable(5, 0, new Set())).toBeNull()
  })
})

describe('hour helpers', () => {
  it('starts at the first available hour', () => {
    expect(firstAvailableHour(range(0, 48))).toBe(0)
    expect(firstAvailableHour([3, 4, 5])).toBe(3)
    expect(firstAvailableHour([])).toBe(0)
  })

  it('describes the hours without data as ranges', () => {
    expect(missingHourRanges(partial)).toEqual(['10-13', '36-48'])
    expect(missingHourRanges(allHours)).toEqual([])
    expect(missingHourRanges(new Set(range(0, 47)))).toEqual(['48'])
  })
})
