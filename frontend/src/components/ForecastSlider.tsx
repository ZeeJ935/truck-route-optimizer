import { useId, useMemo } from 'react'
import { SLIDER_MAX_HOUR, missingHourRanges, snapToAvailable } from '../features/forecast/hours'
import type { ForecastData } from '../types/api'
import { formatTripTime } from '../utils/time'

interface ForecastSliderProps {
  forecast: ForecastData
  hour: number
  tripOffsetMinutes: number
  onHourChange: (hour: number) => void
}

/**
 * The 0-48 hour slider for the corridor heatmap. A native range input, so it
 * works with mouse, touch, and keyboard. Hours without data cannot be selected.
 * Moving it only changes local state; it never makes a request.
 */
export function ForecastSlider({ forecast, hour, tripOffsetMinutes, onHourChange }: ForecastSliderProps) {
  const id = useId()
  const available = useMemo(() => new Set(forecast.available_hours), [forecast.available_hours])
  const missing = useMemo(() => missingHourRanges(available), [available])
  const noData = available.size === 0
  const timestamp = forecast.timestamps[hour]
  const timeText = timestamp ? formatTripTime(timestamp, tripOffsetMinutes) : ''
  const valueText = noData ? 'No forecast data' : `Hour +${hour}: ${timeText}`

  const handleChange = (requested: number) => {
    const next = snapToAvailable(requested, hour, available)
    if (next !== null && next !== hour) onHourChange(next)
  }

  return (
    <section className="forecast-slider" aria-labelledby={`${id}-title`}>
      <div className="forecast-slider-header">
        <h2 id={`${id}-title`} className="forecast-slider-title">
          Corridor heatmap
        </h2>
        <p className="forecast-slider-time" aria-live="polite">
          {noData ? 'No forecast data' : `+${hour} h · ${timeText}`}
        </p>
      </div>
      <p className="forecast-slider-hint">
        Risk along the whole corridor at the selected time. Checkpoints show weather at each ETA instead.
      </p>
      <label className="visually-hidden" htmlFor={`${id}-range`}>
        Forecast hour after departure
      </label>
      <input
        id={`${id}-range`}
        className="forecast-range"
        type="range"
        min={0}
        max={SLIDER_MAX_HOUR}
        step={1}
        value={hour}
        disabled={noData}
        aria-valuetext={valueText}
        onChange={(event) => handleChange(Number(event.target.value))}
      />
      <div className="hour-strip" aria-hidden="true">
        {Array.from({ length: SLIDER_MAX_HOUR + 1 }, (_, index) => (
          <span
            key={index}
            className={[
              'hour-cell',
              available.has(index) ? '' : 'hour-cell-missing',
              index === hour ? 'hour-cell-selected' : '',
            ].join(' ')}
          />
        ))}
      </div>
      <div className="hour-scale" aria-hidden="true">
        <span>Departure</span>
        <span>+24 h</span>
        <span>+48 h</span>
      </div>
      {missing.length > 0 && (
        <p className="forecast-slider-notice">
          <span className="hour-cell hour-cell-missing legend-swatch" aria-hidden="true" />{' '}
          {forecast.notice ?? `No forecast data for hours ${missing.join(', ')} after departure; those positions are disabled.`}
        </p>
      )}
    </section>
  )
}
