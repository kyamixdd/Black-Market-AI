import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectDirectory = dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, resolve(projectDirectory, '..'), '')
  // Public URL only; authentication remains on the server or in the native session.
  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || 'http://127.0.0.1:8765'
  const websocketTarget = backendTarget.replace(/^http/, 'ws')
  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': resolve(projectDirectory, 'src'),
      },
    },
    server: {
      port: 3000,
      watch: {
        ignored: ['**/src-tauri/target/**'],
      },
      proxy: {
        '/api/backend': {
          target: backendTarget,
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/backend/, '/api'),
        },
        '/api/health': {
          target: backendTarget,
          changeOrigin: true,
          rewrite: () => '/health',
        },
        '/ws': {
          target: websocketTarget,
          ws: true,
        },
      },
    },
  }
})
