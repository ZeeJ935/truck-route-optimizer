import type { Recommendation, RouteResult } from '../types/api'
import { formatDuration, formatMiles } from '../utils/format'
import { StatusBadge } from './StatusBadge'

interface RecommendationPanelProps {
  recommendation: Recommendation
  route: RouteResult
}

/** Shows the backend's recommendation as given: its label, status, and reason. */
export function RecommendationPanel({ recommendation, route }: RecommendationPanelProps) {
  return (
    <section
      className={`recommendation ${recommendation.no_safe_route ? 'recommendation-unsafe' : ''}`}
      aria-label="Recommendation"
    >
      <p className="recommendation-label">{route.label}</p>
      <div className="recommendation-heading">
        <h2>Route {route.rank}</h2>
        <StatusBadge status={route.status} />
      </div>
      <p className="recommendation-meta">
        {formatMiles(route.distance_miles)} · {formatDuration(route.duration_seconds)}
      </p>
      <p className="recommendation-reason">{recommendation.reason}</p>
    </section>
  )
}
