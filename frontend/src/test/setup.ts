import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach, vi } from 'vitest'

// jsdom has no WebGL; every test uses the recording MapLibre stand-in.
vi.mock('maplibre-gl', () => import('./maplibreFake'))

afterEach(() => {
  cleanup()
})
