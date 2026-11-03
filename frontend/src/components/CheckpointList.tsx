import type { RouteResult } from '../types/api'
import { RISK_TONE } from '../utils/format'
import { formatTripTime } from '../utils/time'

interface CheckpointListProps {
  route: RouteResult
  tripOffsetMinutes: number
}

/** Weather at each checkpoint, taken from the forecast hour matched to the truck's ETA there. */
export function CheckpointList({ route, tripOffsetMinutes }: CheckpointListProps) {
  return (
    <section aria-label={`Checkpoints for Route ${route.rank}`}>
      <h2 className="section-title">Checkpoints · Route {route.rank}</h2>
      <p className="section-hint">Weather at each checkpoint's estimated arrival time (ETA).</p>
      <ol className="checkpoint-list">
        {route.checkpoints.map((checkpoint) => (
          <li key={checkpoint.mile} className="checkpoint">
            <div className="checkpoint-main">
              <span className="checkpoint-mile">Mile {checkpoint.mile.toFixed(1)}</span>
              <span className={`risk-pill ${RISK_TONE[checkpoint.risk]}`}>{checkpoint.risk_label}</span>
            </div>
            <p className="checkpoint-eta">ETA {formatTripTime(checkpoint.eta, tripOffsetMinutes)}</p>
            <p className="checkpoint-weather">
              Wind {checkpoint.weather.wind_mph} mph · Rain {checkpoint.weather.rain_in_per_hour} in/hr · Snow{' '}
              {checkpoint.weather.snow_in_per_hour} in/hr
            </p>
            {checkpoint.reasons.length > 0 && (
              <ul className="checkpoint-reasons">
                {checkpoint.reasons.map((reason) => (
                  <li key={reason}>{reason}</li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
    </section>
  )
}
