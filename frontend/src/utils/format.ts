import type { RiskLevel, RouteStatus } from '../types/api'

export function formatMiles(miles: number): string {
  return `${miles.toFixed(1)} mi`
}

export function formatDuration(seconds: number): string {
  const totalMinutes = Math.round(seconds / 60)
  const hours = Math.floor(totalMinutes / 60)
  const minutes = totalMinutes % 60
  return hours > 0 ? `${hours} h ${minutes} min` : `${minutes} min`
}

export function formatAverageRisk(value: number): string {
  return value.toFixed(2)
}

// Display only: these map backend values to a label and a colour tone.
// There are no thresholds or rules here; the backend decides every value.
export const STATUS_DISPLAY: Record<RouteStatus, { label: string; tone: string }> = {
  SAFE: { label: 'Safe', tone: 'safe' },
  CAUTION: { label: 'Caution', tone: 'caution' },
  NOT_SAFE: { label: 'Not Safe', tone: 'danger' },
}

export const RISK_TONE: Record<RiskLevel, string> = {
  0: 'risk-low',
  1: 'risk-moderate',
  2: 'risk-high',
  3: 'risk-severe',
  4: 'risk-no-travel',
}
