import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// In local dev, /api is proxied to the Django server so no CORS setup is needed.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8000',
    },
  },
})
