import type { AnalyzeRequest, SamplingInterval } from '../../types/api'
import { localInputToOffsetIso } from '../../utils/time'

// Frontend checks are for usability only. The backend validates every request
// independently and is the authority.

export type FieldName = 'origin' | 'destination' | 'departure_time' | 'load_weight_lb' | 'sampling_interval_miles'
export type FieldErrors = Partial<Record<FieldName, string>>

export interface FormValues {
  origin: string
  destination: string
  departureLocal: string
  loadWeight: string
  interval: string
}

export const SAMPLING_INTERVALS: SamplingInterval[] = [10, 25, 50]
const PAST_GRACE_MS = 5 * 60_000
const FORECAST_RANGE_MS = 16 * 24 * 60 * 60_000

export function validateForm(values: FormValues, now: Date = new Date()): FieldErrors {
  const errors: FieldErrors = {}
  const origin = values.origin.trim()
  const destination = values.destination.trim()

  if (!origin) errors.origin = 'Enter an origin.'
  if (!destination) errors.destination = 'Enter a destination.'
  else if (origin && origin.toLowerCase() === destination.toLowerCase()) {
    errors.destination = 'Choose a destination different from the origin.'
  }

  const departure = new Date(values.departureLocal)
  if (!values.departureLocal) {
    errors.departure_time = 'Choose a departure date and time.'
  } else if (Number.isNaN(departure.getTime())) {
    errors.departure_time = 'Enter a valid date and time.'
  } else if (departure.getTime() < now.getTime() - PAST_GRACE_MS) {
    errors.departure_time = 'Departure time is in the past.'
  } else if (departure.getTime() > now.getTime() + FORECAST_RANGE_MS) {
    errors.departure_time = 'Choose a departure within the next 16 days, the weather forecast range.'
  }

  const load = Number(values.loadWeight)
  if (values.loadWeight.trim() === '') {
    errors.load_weight_lb = 'Enter the load weight.'
  } else if (!Number.isFinite(load) || load <= 0) {
    errors.load_weight_lb = 'Load weight must be a number greater than 0.'
  }

  if (!SAMPLING_INTERVALS.includes(Number(values.interval) as SamplingInterval)) {
    errors.sampling_interval_miles = 'Choose 10, 25, or 50 miles.'
  }
  return errors
}

export function toAnalyzeRequest(values: FormValues): AnalyzeRequest {
  return {
    origin: values.origin.trim(),
    destination: values.destination.trim(),
    departure_time: localInputToOffsetIso(values.departureLocal),
    load_weight_lb: Number(values.loadWeight),
    sampling_interval_miles: Number(values.interval) as SamplingInterval,
  }
}
