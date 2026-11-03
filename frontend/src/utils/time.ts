// Trip times are shown in the UTC offset of the entered departure, with a label,
// even when the route crosses time zones. The backend works in UTC.

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

const pad = (value: number) => String(value).padStart(2, '0')

/** The browser's UTC offset, in minutes east of UTC, at a local date-time such as "2026-11-03T08:00". */
export function browserOffsetMinutes(localInput: string): number {
  const date = new Date(localInput)
  const reference = Number.isNaN(date.getTime()) ? new Date() : date
  return -reference.getTimezoneOffset()
}

/** "+05:00", "-03:30", "+00:00". */
export function formatOffset(offsetMinutes: number): string {
  const sign = offsetMinutes < 0 ? '-' : '+'
  const absolute = Math.abs(offsetMinutes)
  return `${sign}${pad(Math.floor(absolute / 60))}:${pad(absolute % 60)}`
}

/** "UTC+05:00". */
export function offsetLabel(offsetMinutes: number): string {
  return `UTC${formatOffset(offsetMinutes)}`
}

/** A datetime-local value ("2026-11-03T08:00") as ISO 8601 with the browser's offset for that date. */
export function localInputToOffsetIso(localInput: string): string {
  return `${localInput}:00${formatOffset(browserOffsetMinutes(localInput))}`
}

/** The offset in minutes written in an ISO 8601 timestamp such as "...+05:00" or "...Z". */
export function offsetFromIso(iso: string): number {
  const match = /([+-])(\d{2}):(\d{2})$/.exec(iso)
  if (!match) return 0
  const minutes = Number(match[2]) * 60 + Number(match[3])
  return match[1] === '-' ? -minutes : minutes
}

/** A UTC timestamp shown in a fixed offset: "Nov 3, 13:30 UTC+05:00". */
export function formatTripTime(isoUtc: string, offsetMinutes: number): string {
  const shifted = new Date(Date.parse(isoUtc) + offsetMinutes * 60_000)
  const day = `${MONTHS[shifted.getUTCMonth()]} ${shifted.getUTCDate()}`
  return `${day}, ${pad(shifted.getUTCHours())}:${pad(shifted.getUTCMinutes())} ${offsetLabel(offsetMinutes)}`
}

/** A datetime-local value for a Date, in the browser's time zone. */
export function toLocalInput(date: Date): string {
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  )
}

/** Default departure: one hour from now, rounded up to the next 5 minutes. */
export function defaultDepartureInput(now: Date = new Date()): string {
  const date = new Date(now.getTime() + 60 * 60_000)
  date.setSeconds(0, 0)
  const remainder = date.getMinutes() % 5
  if (remainder !== 0) date.setMinutes(date.getMinutes() + 5 - remainder)
  return toLocalInput(date)
}
