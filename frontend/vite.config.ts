import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

const optimizedDependencies = [
  'react',
  'react-dom',
  'react-dom/client',
  'react/jsx-runtime',
  'react/jsx-dev-runtime',
]

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const apiTarget = env.VITE_API_TARGET?.trim() || 'http://127.0.0.1:8002'

  return {
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
      strictPort: false,
      proxy: {
        '/api': {
          target: apiTarget,
          changeOrigin: true,
          proxyTimeout: 300000,
          timeout: 300000,
        },
        '/uploads': {
          target: apiTarget,
          changeOrigin: true,
          proxyTimeout: 300000,
          timeout: 300000,
        },
      },
    },
  }
})
