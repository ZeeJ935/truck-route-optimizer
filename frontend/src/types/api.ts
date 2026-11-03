// Types for the backend API. The backend decides every value; the UI only renders them.

export type RiskLevel = 0 | 1 | 2 | 3 | 4
export type RouteStatus = 'SAFE' | 'CAUTION' | 'NOT_SAFE'
export type SamplingInterval = 10 | 25 | 50

export interface AnalyzeRequest {
  origin: string
  destination: string
  departure_time: string
  load_weight_lb: number
  sampling_interval_miles: SamplingInterval
}

export interface CheckpointWeather {
  forecast_time: string
  wind_mph: number
  rain_in_per_hour: number
  snow_in_per_hour: number
}

export interface Checkpoint {
  mile: number
  lat: number
  lng: number
  eta: string
  segment_miles: number
  weather: CheckpointWeather
  risk: RiskLevel
  risk_label: string
  reasons: string[]
}

export interface RouteResult {
  id: string
  rank: number
  label: string
  status: RouteStatus
  geometry: [number, number][]
  distance_miles: number
  duration_seconds: number
  no_travel_miles: number
  severe_miles: number
  high_miles: number
  average_risk: number
  checkpoints: Checkpoint[]
}

export interface Recommendation {
  route_id: string
  reason: string
  no_safe_route: boolean
}

export interface CorridorPoint {
  lat: number
  lng: number
  risk: (RiskLevel | null)[]
}

export interface ForecastData {
  timestamps: string[]
  corridor: CorridorPoint[]
  available_hours: number[]
  notice: string | null
}

export interface AnalysisResponse {
  routes: RouteResult[]
  recommendation: Recommendation
  route_notice: string | null
  forecast: ForecastData
}

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    fields?: Record<string, string>
  }
}
