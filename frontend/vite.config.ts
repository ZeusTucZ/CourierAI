import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: { proxy: { '/demo': { target: process.env.BACKEND_URL || 'http://127.0.0.1:8001', ws: true }, '/geospatial': process.env.BACKEND_URL || 'http://127.0.0.1:8001' } },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], exclude: ['node_modules/**', 'e2e/**'] },
})
