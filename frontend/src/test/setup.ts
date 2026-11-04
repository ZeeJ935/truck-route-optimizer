import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no WebGL; every test uses the recording MapLibre stand-in.
vi.mock('maplibre-gl', () => import('./maplibreFake'))

// Place suggestions are optional; by default tests get none so they never use fetch.
// Suggestion tests override this mock or use the real module.
vi.mock('../api/places', () => ({ SUGGEST_TIMEOUT_MS: 8000, suggestPlaces: vi.fn().mockResolvedValue([]) }))

afterEach(() => {
  cleanup()
})
