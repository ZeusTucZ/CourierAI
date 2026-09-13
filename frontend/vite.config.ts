import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  // Keep the development proxy aligned with the documented FastAPI command.
  server: { proxy: { '/demo': { target: process.env.BACKEND_URL || 'http://127.0.0.1:8000', ws: true }, '/geospatial': process.env.BACKEND_URL || 'http://127.0.0.1:8000' } },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], exclude: ['node_modules/**', 'e2e/**'] },
})
