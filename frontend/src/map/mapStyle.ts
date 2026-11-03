import type { RiskLevel } from '../types/api'

// OpenFreeMap: free vector tiles, no key or registration. Positron is a quiet
// basemap, so route and risk colours stand out.
export const MAP_STYLE_URL = 'https://tiles.openfreemap.org/styles/positron'

// Open-Meteo data is CC BY 4.0, which requires attribution.
export const WEATHER_ATTRIBUTION =
  'Weather: <a href="https://open-meteo.com/" target="_blank" rel="noopener">Open-Meteo.com</a> (CC BY 4.0)'

// Display colours only. Every risk value and decision comes from the backend.
export const MAP_COLORS: {
  selected: string
  otherRoute: string
  recommended: string
  hazardCasing: string
  risk: Record<RiskLevel, string>
} = {
  selected: '#1f5fbf',
  otherRoute: '#64748b',
  recommended: '#15803d',
  hazardCasing: '#1b2430',
  risk: {
    0: '#2e8b57',
    1: '#c9a400',
    2: '#e07b00',
    3: '#d1342a',
    4: '#6e1b8f',
  },
}

export const RISK_LEGEND: { level: RiskLevel; label: string }[] = [
  { level: 0, label: 'Low' },
  { level: 1, label: 'Moderate' },
  { level: 2, label: 'High' },
  { level: 3, label: 'Severe' },
  { level: 4, label: 'No Travel' },
]
