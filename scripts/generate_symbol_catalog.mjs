import { spawnSync } from 'node:child_process'
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const outputPath = path.join(root, 'docs', 'SYMBOL_CATALOG.md')
const sourceRoots = [
  'main.py', 'config.py', 'core', 'database', 'exchange', 'intelligence',
  'learning', 'market', 'models', 'monitoring', 'notifications',
  'paper_trading', 'risk', 'scripts', 'src_tauri', 'strategies', 'terminal',
  'tests', 'benchmarks', 'blackmarket-desktop/src', 'blackmarket-desktop/src-tauri/src',
]
const excludedDirectories = new Set([
  '.git', '.venv', 'venv', '__pycache__', 'node_modules', '.next',
  'target', 'dist', 'build', 'release-output', '*.egg-info',
])
const sourceExtensions = new Set(['.py', '.ts', '.tsx', '.rs'])

function collectSources(relativePath, results) {
  const absolutePath = path.join(root, relativePath)
  if (!existsSync(absolutePath)) return
  if (path.extname(absolutePath)) {
    if (sourceExtensions.has(path.extname(absolutePath))) results.push(absolutePath)
    return
  }
  for (const entry of readdirSync(absolutePath, { withFileTypes: true })) {
    if (entry.isDirectory() && excludedDirectories.has(entry.name)) continue
    collectSources(path.join(relativePath, entry.name), results)
  }
}

const files = []
for (const sourceRoot of sourceRoots) collectSources(sourceRoot, files)
const uniqueFiles = [...new Set(files)].sort()
const relative = (filePath) => path.relative(root, filePath).replaceAll(path.sep, '/')
const symbols = []

const pythonFiles = uniqueFiles.filter((filePath) => path.extname(filePath) === '.py')
const pythonParser = String.raw`
import ast, json, sys

class Catalog(ast.NodeVisitor):
    def __init__(self, filename):
        self.filename = filename
        self.scopes = []
        self.rows = []
    def visit_ClassDef(self, node):
        self.scopes.append(node.name)
        self.generic_visit(node)
        self.scopes.pop()
    def visit_FunctionDef(self, node):
        self.add(node)
    def visit_AsyncFunctionDef(self, node):
        self.add(node)
    def add(self, node):
        name = '.'.join([*self.scopes, node.name])
        self.rows.append({'path': self.filename, 'line': node.lineno, 'language': 'Python', 'symbol': name})
        self.scopes.append(node.name)
        self.generic_visit(node)
        self.scopes.pop()

rows = []
for filename in json.load(sys.stdin):
    try:
        with open(filename, encoding='utf-8') as source:
            tree = ast.parse(source.read(), filename=filename)
    except (OSError, SyntaxError) as error:
        print(f'{filename}: {error}', file=sys.stderr)
        raise SystemExit(1)
    catalog = Catalog(filename)
    catalog.visit(tree)
    rows.extend(catalog.rows)
print(json.dumps(rows))
`
if (pythonFiles.length) {
  const venvPython = path.join(root, '.venv', 'Scripts', 'python.exe')
  const executable = process.env.PYTHON ?? (existsSync(venvPython) ? venvPython : 'python')
  const parsed = spawnSync(executable, ['-c', pythonParser], {
    input: JSON.stringify(pythonFiles),
    encoding: 'utf8',
    cwd: root,
  })
  if (parsed.status !== 0) throw new Error(parsed.stderr || `Python AST parser exited with ${parsed.status}`)
  symbols.push(...JSON.parse(parsed.stdout).map((symbol) => ({ ...symbol, path: relative(symbol.path) })))
}

for (const filePath of uniqueFiles) {
  const extension = path.extname(filePath)
  const source = readFileSync(filePath, 'utf8')
  const relativePath = relative(filePath)

  if (extension === '.ts' || extension === '.tsx') {
    const addMatch = (match, symbol) => {
      symbols.push({
        path: relativePath,
        line: source.slice(0, match.index).split('\n').length,
        language: 'TypeScript',
        symbol,
      })
    }
    const declarationPattern = /\b(?:async\s+)?function\s*\*?\s*([A-Za-z_$][\w$]*)?\s*\(/g
    for (const match of source.matchAll(declarationPattern)) {
      addMatch(match, match[1] ?? `<anonymous@${source.slice(0, match.index).split('\n').length}>`)
    }
    const arrowPattern = /=>/g
    for (const match of source.matchAll(arrowPattern)) {
      const lineStart = source.lastIndexOf('\n', match.index) + 1
      const prefix = source.slice(lineStart, match.index)
      const assignedName = prefix.match(/\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=]*)?=\s*(?:async\s*)?$/)?.[1]
      addMatch(match, assignedName ?? `<arrow@${source.slice(0, match.index).split('\n').length}>`)
    }
    const methodPattern = /^\s*(?:(?:public|private|protected|static|async|override|readonly|get|set)\s+)*([A-Za-z_$][\w$]*)\s*(?:<[^>\n]*>)?\s*\([^;\n]*\)\s*(?::[^{}\n]+)?\s*\{/gm
    const controlStatements = new Set(['if', 'for', 'while', 'switch', 'catch', 'with', 'function'])
    for (const match of source.matchAll(methodPattern)) {
      if (!controlStatements.has(match[1])) addMatch(match, match[1])
    }
  } else if (extension === '.rs') {
    const functionPattern = /^\s*(?:(?:pub(?:\([^)]*\))?|async|unsafe|const|extern(?:\s+"[^"]+")?)\s+)*fn\s+([A-Za-z_][A-Za-z0-9_]*)/gm
    for (const match of source.matchAll(functionPattern)) {
      const preceding = source.slice(0, match.index)
      symbols.push({
        path: relativePath,
        line: preceding.split('\n').length,
        language: 'Rust',
        symbol: match[1],
      })
    }
  }
}

symbols.sort((left, right) => left.path.localeCompare(right.path)
  || left.line - right.line
  || left.symbol.localeCompare(right.symbol))
const counts = Object.fromEntries(['Python', 'TypeScript', 'Rust'].map((language) => [
  language,
  symbols.filter((symbol) => symbol.language === language).length,
]))
const lines = [
  '# First-Party Symbol Catalog',
  '',
  'Generated from the current working tree by `node scripts/generate_symbol_catalog.mjs`.',
  '',
  `Definitions: Python ${counts.Python}; TypeScript/TSX ${counts.TypeScript}; Rust ${counts.Rust}; total ${symbols.length}.`,
  '',
  'This catalog lists source-level function candidates; it does not prove that a function is reachable, enabled, correct, or working at runtime. Python uses the standard-library AST. TypeScript/TSX function declarations, arrow tokens, and method-shaped signatures are found by source scanning because the installed TypeScript 7 package exposes a native compiler but no JavaScript parser API. Rust function signatures are also source-scanned; macro-generated symbols are not expanded. Review scanner false positives/omissions when using this as an exhaustive audit. Generated output, dependencies, virtual environments, caches, and build directories are excluded.',
  '',
  '| Source | Line | Language | Symbol |',
  '| --- | ---: | --- | --- |',
  ...symbols.map((symbol) => `| \`${symbol.path}\` | ${symbol.line} | ${symbol.language} | \`${symbol.symbol.replaceAll('|', '\\|')}\` |`),
  '',
]
writeFileSync(outputPath, lines.join('\n'), 'utf8')
console.log(`Wrote ${relative(outputPath)} (${symbols.length} symbols).`)