import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = 'http://127.0.0.1:8002'

// https://vite.dev/config/
export default defineConfig({
  base: './',
  plugins: [react()],
  server: {
    host: '127.0.0.1',
    port: 5174,
    strictPort: true,
    proxy: {
      '/api': {
        target: apiTarget,
        changeOrigin: true,
        proxyTimeout: 120000,
        timeout: 120000,
      },
      '/uploads': {
        target: apiTarget,
        changeOrigin: true,
        proxyTimeout: 120000,
        timeout: 120000,
      },
    },
  },
})
