import { apiBaseUrl } from './client'

// Suggestions are a convenience: a slow or failed request never blocks typing.
export const SUGGEST_TIMEOUT_MS = 8_000

export interface PlaceSuggestion {
  label: string
  type: string
}

function isSuggestionList(value: unknown): value is { suggestions: PlaceSuggestion[] } {
  if (typeof value !== 'object' || value === null) return false
  const list = (value as { suggestions?: unknown }).suggestions
  return (
    Array.isArray(list) &&
    list.every(
      (item) =>
        typeof item === 'object' &&
        item !== null &&
        typeof (item as PlaceSuggestion).label === 'string' &&
        typeof (item as PlaceSuggestion).type === 'string',
    )
  )
}

/** Place suggestions for the origin and destination fields, from the backend (which holds the key). */
export async function suggestPlaces(query: string, signal?: AbortSignal): Promise<PlaceSuggestion[]> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), SUGGEST_TIMEOUT_MS)
  const forwardAbort = () => controller.abort()
  signal?.addEventListener('abort', forwardAbort)
  try {
    const response = await fetch(`${apiBaseUrl()}/api/places/suggest?q=${encodeURIComponent(query)}`, {
      headers: { Accept: 'application/json' },
      signal: controller.signal,
    })
    if (!response.ok) throw new Error(`Suggestions failed with HTTP ${response.status}`)
    const body: unknown = await response.json()
    if (!isSuggestionList(body)) throw new Error('Unexpected suggestion response')
    return body.suggestions
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', forwardAbort)
  }
}
