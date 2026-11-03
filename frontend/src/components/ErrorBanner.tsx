import type { ApiError } from '../api/client'

const TITLES: Record<string, string> = {
  validation_error: 'Check the trip details',
  geocoding_failed: 'Location not found',
  no_route_found: 'No truck route found',
  forecast_unavailable: 'Forecast not available',
  provider_rate_limited: 'Service busy',
  provider_timeout: 'Service timed out',
  provider_error: 'Service problem',
  client_timeout: 'No response',
  network_error: 'Connection problem',
}

export function ErrorBanner({ error }: { error: ApiError }) {
  return (
    <div className="banner banner-error" role="alert">
      <p className="banner-title">{TITLES[error.code] ?? 'Something went wrong'}</p>
      <p>{error.message}</p>
    </div>
  )
}
