import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// In local dev, /api is proxied to the Django server so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
  build: {
    // The lazily loaded map chunk is mostly the MapLibre library itself (~1 MB, ~290 kB gzip).
    chunkSizeWarningLimit: 1100,
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    restoreMocks: true,
  },
})
