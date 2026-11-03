// Forecast slider hour helpers. Availability comes from the backend's
// forecast.available_hours; nothing here decides risk.

export const SLIDER_MAX_HOUR = 48

/**
 * The hour to select when the user asks for `requested`. An hour without data
 * can never be selected: it snaps to the nearest available hour in the
 * direction of movement, then the other way. Returns null if none is available.
 */
export function snapToAvailable(requested: number, previous: number, available: ReadonlySet<number>): number | null {
  if (available.size === 0) return null
  const target = Math.min(SLIDER_MAX_HOUR, Math.max(0, Math.round(requested)))
  if (available.has(target)) return target
  const forward = target >= previous ? 1 : -1
  for (const direction of [forward, -forward]) {
    for (let hour = target + direction; hour >= 0 && hour <= SLIDER_MAX_HOUR; hour += direction) {
      if (available.has(hour)) return hour
    }
  }
  return null
}

export function firstAvailableHour(available: readonly number[]): number {
  return available.length > 0 ? Math.min(...available) : 0
}

/** "36-48" style ranges for hours that have no data. */
export function missingHourRanges(available: ReadonlySet<number>): string[] {
  const ranges: string[] = []
  let start: number | null = null
  for (let hour = 0; hour <= SLIDER_MAX_HOUR + 1; hour++) {
    const missing = hour <= SLIDER_MAX_HOUR && !available.has(hour)
    if (missing && start === null) start = hour
    if (!missing && start !== null) {
      ranges.push(start === hour - 1 ? `${start}` : `${start}-${hour - 1}`)
      start = null
    }
  }
  return ranges
}
