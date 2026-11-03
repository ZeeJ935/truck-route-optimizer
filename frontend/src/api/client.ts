// Base URL of the Django API. Empty in local dev (Vite proxies /api).
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? '').replace(/\/$/, '')

export interface HealthResponse {
  status: string
}

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`, { signal })
  if (!response.ok) {
    throw new Error(`Health check failed with HTTP ${response.status}`)
  }
  return (await response.json()) as HealthResponse
}
