import { defineConfig } from '@playwright/test'
export default defineConfig({ testDir: './e2e', timeout: 180000, use: { baseURL: 'http://127.0.0.1:5173', viewport: { width: 1366, height: 768 }, screenshot: 'only-on-failure' }, workers: 1 })
