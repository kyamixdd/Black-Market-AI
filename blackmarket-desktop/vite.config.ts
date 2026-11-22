import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectDirectory = dirname(fileURLToPath(import.meta.url))

export default defineConfig(({ mode }) => {\n  const env = loadEnv(mode, projectDirectory, '')\n  const backendTarget = env.VITE_BACKEND_PROXY_TARGET || 'http://127.0.0.1:8765'\n  const websocketTarget = backendTarget.replace(/^http/, 'ws')\n  return {
  plugins: [react()],
  resolve: {
    alias: {
      '@': resolve(projectDirectory, 'src'),
    },
  },
  server: {
    port: 3000,
    // Cargo writes and locks native build artifacts here while Tauri is running.
    // They are not frontend source and should never be part of Vite's watcher tree.
    watch: {
      ignored: ['**/src-tauri/target/**'],
    },
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8765',
        changeOrigin: true,
      },
      '/ws': {
        target: websocketTarget,
        ws: true,
      },
    },
  },
})
