import { useEffect, useState } from 'react'
import { suggestPlaces, type PlaceSuggestion } from '../../api/places'

export const SUGGEST_MIN_CHARS = 3
export const SUGGEST_DEBOUNCE_MS = 300

// Repeat searches in this browser session are answered without a request.
const cache = new Map<string, PlaceSuggestion[]>()

export function clearPlaceSuggestionCache() {
  cache.clear()
}

const cacheKey = (query: string) => query.trim().replace(/\s+/g, ' ').toLowerCase()

/**
 * Suggestions for what the user is typing. Searches only from SUGGEST_MIN_CHARS
 * characters, waits SUGGEST_DEBOUNCE_MS after the last keystroke, cancels any
 * outdated request, and caches results. Failures simply yield no suggestions.
 */
export function usePlaceSuggestions(query: string, enabled: boolean): PlaceSuggestion[] {
  const [result, setResult] = useState<{ key: string; suggestions: PlaceSuggestion[] }>({ key: '', suggestions: [] })
  const key = cacheKey(query)
  const active = enabled && key.length >= SUGGEST_MIN_CHARS

  useEffect(() => {
    if (!active || cache.has(key)) return
    const controller = new AbortController()
    const timer = setTimeout(() => {
      suggestPlaces(query.trim(), controller.signal)
        .then((suggestions) => {
          cache.set(key, suggestions)
          if (!controller.signal.aborted) setResult({ key, suggestions })
        })
        .catch(() => {
          // Suggestions are optional: on failure the user keeps typing a full address.
          if (!controller.signal.aborted) setResult({ key, suggestions: [] })
        })
    }, SUGGEST_DEBOUNCE_MS)
    return () => {
      clearTimeout(timer)
      controller.abort()
    }
  }, [active, key, query])

  if (!active) return []
  const cached = cache.get(key)
  if (cached) return cached
  return result.key === key ? result.suggestions : []
}
