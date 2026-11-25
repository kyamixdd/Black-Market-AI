import react from '@vitejs/plugin-react'
import { createRequire } from 'node:module'
const requireFromConfig = createRequire(import.meta.url)
const tsEntry = requireFromConfig.resolve('typescript').replace(/version\\.js$/, 'typescript.js')
const ts: any = requireFromConfig(tsEntry)
import { defineConfig, loadEnv } from 'vite'
import type { ProxyOptions } from 'vite'
import { readFileSync } from 'node:fs'
import { homedir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'


function diagnosticFunctionTracing() {
  return {
    name: 'blackmarket-opt-in-function-tracing',
    enforce: 'pre' as const,
    transform(code: string, id: string) {
      const file = id.split('?')[0].replaceAll(String.fromCharCode(92), '/')
      if (
        !file.includes('/src/')
        || file.endsWith('/services/diagnosticLogger.ts')
        || /\\.(?:test|spec|stories)\\.[jt]sx?$/.test(file)
        || file.includes('/node_modules/')
        || file.endsWith('.d.ts')
      ) return null

      const kind = file.endsWith('.tsx') ? ts.ScriptKind.TSX : file.endsWith('.jsx') ? ts.ScriptKind.JSX : file.endsWith('.js') ? ts.ScriptKind.JS : ts.ScriptKind.TS
      const source = ts.createSourceFile(file, code, ts.ScriptTarget.Latest, true, kind)
      const edits: Array<{ start: number; end: number; text: string }> = []
      const relativeFile = file.slice(file.lastIndexOf('/src/') + 5)

      const functionName = (node: any): string => {
        if ((ts.isFunctionDeclaration(node) || ts.isMethodDeclaration(node) || ts.isGetAccessor(node) || ts.isSetAccessor(node)) && node.name) return node.name.getText(source)
        const parent = node.parent
        if (ts.isVariableDeclaration(parent) && ts.isIdentifier(parent.name)) return parent.name.text
        if (ts.isPropertyAssignment(parent)) return parent.name.getText(source)
        if (ts.isPropertyDeclaration(parent) && parent.name) return parent.name.getText(source)
        return 'anonymous'
      }
      const visit = (node: any) => {
        const supported = ts.isFunctionDeclaration(node) || ts.isFunctionExpression(node) || ts.isArrowFunction(node) || ts.isMethodDeclaration(node) || ts.isGetAccessor(node) || ts.isSetAccessor(node) || ts.isConstructorDeclaration(node)
        if (supported && node.body) {
          const name = functionName(node)
          const prefix = `const __bmTrace = __bmTraceStart(${JSON.stringify(relativeFile)}, ${JSON.stringify(name)});\nlet __bmTraceSuccess = true;\ntry {\n`
          const suffix = `\n} catch (__bmTraceError) {\n  __bmTraceSuccess = false;\n  __bmTraceFailure(__bmTrace, __bmTraceError);\n  throw __bmTraceError;\n} finally {\n  __bmTraceEnd(__bmTrace, __bmTraceSuccess);\n}\n`
          if (ts.isBlock(node.body)) {
            edits.push({ start: node.body.getStart(source) + 1, end: node.body.getStart(source) + 1, text: prefix })
            edits.push({ start: node.body.end - 1, end: node.body.end - 1, text: suffix })
          } else if (ts.isArrowFunction(node)) {
            edits.push({ start: node.body.getStart(source), end: node.body.getStart(source), text: `{ ${prefix}return (` })
            edits.push({ start: node.body.end, end: node.body.end, text: `); ${suffix} }` })
          }
        }
        ts.forEachChild(node, visit)
      }
      visit(source)
      if (!edits.length) return null
      edits.sort((a, b) => b.start - a.start || b.end - a.end)
      let transformed = code
      for (const edit of edits) transformed = transformed.slice(0, edit.start) + edit.text + transformed.slice(edit.end)
      transformed = `import { traceFunctionStart as __bmTraceStart, traceFunctionFailure as __bmTraceFailure, traceFunctionEnd as __bmTraceEnd } from '/src/services/diagnosticLogger.ts';\n` + transformed
      return { code: transformed, map: null }
    },
  }
}

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
    plugins: [diagnosticFunctionTracing(), react()],
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
