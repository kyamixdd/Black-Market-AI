import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'
import type { ProxyOptions } from 'vite'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const projectDirectory = dirname(fileURLToPath(import.meta.url))
const browserOrigins = new Set(['http://localhost:3000', 'http://127.0.0.1:3000'])
const browserHosts = new Set(['localhost:3000', '127.0.0.1:3000'])

function getApiTokenPath() {
  if (process.env.BLACKMARKET_API_TOKEN_FILE) {
    return resolve(process.env.BLACKMARKET_API_TOKEN_FILE)
  }

  let dataDirectory: string
  if (process.platform === 'win32') {
    dataDirectory = process.env.APPDATA || join(homedir(), 'AppData', 'Roaming')
  } else if (process.platform === 'darwin') {
    dataDirectory = join(homedir(), 'Library', 'Application Support')
  } else {
    dataDirectory = process.env.XDG_DATA_HOME || join(homedir(), '.local', 'share')
  }

  return join(dataDirectory, 'com.blackmarket.ai', 'api-token')
}

const apiTokenPath = getApiTokenPath()
let apiTokenReadErrorLogged = false

function configureLocalApiProxy(proxy: Parameters<NonNullable<ProxyOptions['configure']>>[0]) {
  proxy.on('proxyReq', (proxyRequest, request) => {
    proxyRequest.removeHeader('Authorization')
    const origin = request.headers.origin
    const isAllowedBrowserOrigin = typeof origin === 'string' && browserOrigins.has(origin)
    const isSafeMethod = request.method === 'GET' || request.method === 'HEAD'
    if (
      !browserHosts.has(request.headers.host || '')
      || (origin !== undefined && !isAllowedBrowserOrigin)
      || (!isAllowedBrowserOrigin && !isSafeMethod)
    ) {
      return
    }

    try {
      const token = readFileSync(apiTokenPath, 'utf8').trim()
      if (!/^[a-f0-9]{32}$/i.test(token)) {
        throw new Error('The saved local API token has an invalid format.')
      }
      proxyRequest.setHeader('Authorization', `Bearer ${token}`)
      apiTokenReadErrorLogged = false
    } catch (error) {
      if (!apiTokenReadErrorLogged) {
        console.error(`[vite] Unable to read the local API token at ${apiTokenPath}. Start the app with START_BLACKMARKET_DEV.bat first.`, error)
        apiTokenReadErrorLogged = true
      }
    }
  })
}

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, resolve(projectDirectory, '..'), '')
  const backendTarget = new URL(env.VITE_BACKEND_PROXY_TARGET || 'http://127.0.0.1:8765')
  if (
    backendTarget.protocol !== 'http:'
    || !new Set(['localhost', '127.0.0.1', '[::1]']).has(backendTarget.hostname)
    || backendTarget.username
    || backendTarget.password
    || backendTarget.pathname !== '/'
    || backendTarget.search
    || backendTarget.hash
  ) {
    throw new Error('VITE_BACKEND_PROXY_TARGET must be a loopback HTTP origin with no path, query, or credentials.')
  }
  const websocketTarget = backendTarget.origin.replace(/^http/, 'ws')
  return {
    plugins: [react()],
    define: {
      __BLACKMARKET_LOCAL_BROWSER_DEV__: JSON.stringify(mode === 'development'),
    },
    resolve: {
      alias: {
        '@': resolve(projectDirectory, 'src'),
      },
    },
    server: {
      host: 'localhost',
      port: 3000,
      strictPort: true,
      watch: {
        ignored: ['**/src-tauri/target/**'],
      },
      proxy: {
        '/api/backend': {
          target: backendTarget.origin,
          changeOrigin: true,
          rewrite: (path: string) => path.replace(/^\/api\/backend/, '/api'),
          configure: configureLocalApiProxy,
        },
        '/api/health': {
          target: backendTarget.origin,
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
