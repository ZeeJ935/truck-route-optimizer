import type { RouteResult } from '../types/api'
import { formatAverageRisk, formatDuration, formatMiles } from '../utils/format'
import { StatusBadge } from './StatusBadge'

interface RouteListProps {
  routes: RouteResult[]
  selectedId: string | null
  onSelect: (routeId: string) => void
}

/** Route comparison in the backend's rank order. Selecting a route never refetches. */
export function RouteList({ routes, selectedId, onSelect }: RouteListProps) {
  return (
    <section aria-label="Route comparison">
      <h2 className="section-title">Compare routes</h2>
      <ul className="route-list">
        {routes.map((route) => (
          <li key={route.id}>
            <RouteCard route={route} selected={route.id === selectedId} onSelect={() => onSelect(route.id)} />
          </li>
        ))}
      </ul>
    </section>
  )
}

interface RouteCardProps {
  route: RouteResult
  selected: boolean
  onSelect: () => void
}

function RouteCard({ route, selected, onSelect }: RouteCardProps) {
  return (
    <button
      type="button"
      className={`route-card ${selected ? 'route-card-selected' : ''}`}
      aria-pressed={selected}
      aria-label={`Route ${route.rank}, ${route.label}`}
      onClick={onSelect}
    >
      <span className="route-card-header">
        <span className="route-rank">#{route.rank}</span>
        <span className="route-name">Route {route.rank}</span>
        <StatusBadge status={route.status} />
      </span>
      <span className="route-label">{route.label}</span>
      <span className="route-summary">
        {formatMiles(route.distance_miles)} · {formatDuration(route.duration_seconds)}
      </span>
      <dl className="route-metrics">
        <div className={route.no_travel_miles > 0 ? 'metric metric-alert' : 'metric'}>
          <dt>No Travel</dt>
          <dd>{formatMiles(route.no_travel_miles)}</dd>
        </div>
        <div className={route.severe_miles > 0 ? 'metric metric-alert' : 'metric'}>
          <dt>Severe</dt>
          <dd>{formatMiles(route.severe_miles)}</dd>
        </div>
        <div className={route.high_miles > 0 ? 'metric metric-warn' : 'metric'}>
          <dt>High</dt>
          <dd>{formatMiles(route.high_miles)}</dd>
        </div>
        <div className="metric">
          <dt>Avg. risk</dt>
          <dd>{formatAverageRisk(route.average_risk)}</dd>
        </div>
      </dl>
    </button>
  )
}
