import { useState } from 'react'
import { MAP_COLORS, RISK_LEGEND } from './mapStyle'

const NARROW_QUERY = '(max-width: 800px)'

function startsOpen(): boolean {
  // Collapsed by default on narrow screens so it does not cover the small map.
  return typeof window.matchMedia !== 'function' || !window.matchMedia(NARROW_QUERY).matches
}

/**
 * Explains map colours with text, so nothing relies on colour alone.
 * topRouteLabel is the backend label of the top-ranked route ("Recommended" or
 * "Best available, not safe"), so the legend never contradicts the warning state.
 */
export function MapLegend({ topRouteLabel }: { topRouteLabel: string }) {
  const [open, setOpen] = useState(startsOpen)

  return (
    <details
      className="map-legend"
      open={open}
      onToggle={(event) => setOpen((event.currentTarget as HTMLDetailsElement).open)}
    >
      <summary className="map-legend-title">Legend</summary>
      <p className="map-legend-title">Routes</p>
      <ul>
        <li>
          <span className="legend-line" style={{ background: MAP_COLORS.selected }} /> Selected route
        </li>
        <li>
          <span className="legend-line legend-dashed" style={{ color: MAP_COLORS.recommended }} /> {topRouteLabel}
        </li>
        <li>
          <span className="legend-line" style={{ background: MAP_COLORS.otherRoute }} /> Other route
        </li>
      </ul>
      <p className="map-legend-title">Checkpoint risk</p>
      <ul>
        {RISK_LEGEND.map(({ level, label }) => (
          <li key={level}>
            <span className="legend-dot" style={{ background: MAP_COLORS.risk[level] }} /> {label}
          </li>
        ))}
      </ul>
      <p className="map-legend-note">Thick red or purple sections are Severe or No Travel road.</p>
    </details>
  )
}
