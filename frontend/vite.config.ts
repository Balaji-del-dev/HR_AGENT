import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The browser only ever talks to this dev server; it forwards API, auth and
// WebSocket traffic to Django (Uvicorn on 8050), so cookies and CSRF stay same-origin.
const backend = 'http://127.0.0.1:8050'

const proxy = {
  '/api': backend,
  '/api-auth': backend,
  '/admin': backend,
  '/static': backend,
  '/healthz': backend,
  '/readyz': backend,
  '/ws': { target: backend, ws: true },
}

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { '@': path.resolve(__dirname, './src') } },
  // `vite preview` serves the production build with the same proxy.
  preview: { port: 5180, strictPort: true, host: '127.0.0.1', proxy },
  test: { environment: 'jsdom', setupFiles: ['./src/test/setup.ts'], css: false },
  server: {
    port: 5180,
    strictPort: true,
    proxy: {
      '/api': backend,
      '/api-auth': backend,
      '/admin': backend,
      '/static': backend,
      '/healthz': backend,
      '/readyz': backend,
      '/ws': { target: backend, ws: true },
    },
  },
})
