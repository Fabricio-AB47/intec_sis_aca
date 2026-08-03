import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const apiTarget = 'http://127.0.0.1:8002'
const optimizedDependencies = [
  'react',
  'react-dom',
  'react-dom/client',
  'react/jsx-runtime',
  'react/jsx-dev-runtime',
]

// https://vite.dev/config/
export default defineConfig({
  base: './',
  cacheDir: 'node_modules/.vite',
  plugins: [react()],
  optimizeDeps: {
    include: optimizedDependencies,
    holdUntilCrawlEnd: false,
  },
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
