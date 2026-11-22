import { useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import {
  Activity,
  ArrowDownToLine,
  ArrowUpRight,
  Bell,
  Bot,
  CandlestickChart,
  Check,
  CircleHelp,
  FileClock,
  GraduationCap,
  LayoutDashboard,
  ListChecks,
  Network,
  SearchCheck,
  ShieldAlert,
  Minus,
  MinusCircle,
  MoreHorizontal,
  Search,
  Send,
  Settings2,
  SlidersHorizontal,
  Sparkles,
  Wallet,
  X,
} from 'lucide-react'
import { LiveMarketChart } from './components/charts/LiveMarketChart'
import { DashboardScreen } from './screens/DashboardScreens'
import { getApiAuthorization, setApiToken } from './services/localAuth'
import { backendBaseUrl, mutateJson, requestJson } from './services/backendClient'
import {
  assessMarketData,
  marketChartKey,
  mergeMarketCandles,
  parseMarketCandles,
} from './services/marketData'
import type { MarketCandle, MarketDataState, MarketSnapshotData } from './services/marketData'
import { destroyWebSocket, getWebSocket } from './services/websocket'
import type { WebSocketChannel } from './services/websocket'
import type {
  DashboardPreferences,
  ScreenName,
  WorkspaceData,
  WorkspaceEvent,
  WorkspaceLearning,
  WorkspacePortfolio,
  WorkspaceRisk,
  WorkspaceSignal,
} from './screens/DashboardScreens'

type MarketSnapshot = MarketSnapshotData

type HeatmapItem = {
  symbol?: string
  market?: string
  price?: number
  price_change_24h?: number
  volume_24h?: number
  relative_strength_pct?: number | null
  volume_rank_pct?: number | null
  volatility_24h_pct?: number | null
  atr_24h_pct?: number | null
  data_age_seconds?: number | null
  data_freshness?: string
  regime?: string
}

type Breadth = {
  advancing?: number
  declining?: number
  neutral?: number
  total_volume?: number
  avg_spread_bps?: number | null
  avg_orderbook_imbalance?: number | null
}

type VolumeStats = {
  buy_volume?: number | null
  sell_volume?: number | null
  total_volume?: number
  volume_change_24h?: number | null
  average_daily_quote_volume_7d?: number | null
  volume_change_vs_7d_avg_pct?: number | null
  comparison_period?: string | null
  data_timestamp?: string | null
  data_age_seconds?: number | null
  data_freshness?: string
  flow_is_estimated?: boolean
  flow_sample_size?: number
  flow_sample_scope?: string | null
  flow_last_trade_time?: string | null
}

type LongShortStats = {
  long_short_ratio?: number | null
  long_volume?: number | null
  short_volume?: number | null
  open_interest?: number | null
  funding_rate?: number | null
  sample_period?: string | null
  last_updated?: string | null
  history?: { timestamp?: string; ratio?: number }[]
}

type Signal = WorkspaceSignal
type LearningStatus = WorkspaceLearning
type SystemEvent = WorkspaceEvent
type Portfolio = WorkspacePortfolio
type RiskMetrics = WorkspaceRisk

type DashboardData = WorkspaceData & {
  market: MarketSnapshot | null
  candles: MarketCandle[]
  heatmap: HeatmapItem[]
  breadth: Breadth | null
  volume: VolumeStats | null
  longShort: LongShortStats | null
  health: Record<string, unknown> | null
}

type ChatMessage = {
  id: number
  role: 'assistant' | 'user'
  text: string
}

type Indicator = 'SMA20' | 'EMA20'
type Connection = 'connecting' | 'live' | 'degraded' | 'offline'
type Popup = 'notifications' | 'chart' | 'status' | null
type StartupStatus = {
  state: 'queued' | 'checking' | 'starting' | 'ready' | 'failed'
  message: string
  details?: string | null
  logPath?: string | null
}

async function invoke<T>(command: string): Promise<T> {
  const { invoke: tauriInvoke } = await import('@tauri-apps/api/core')
  return tauriInvoke<T>(command)
}
const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '4h', '6h', '12h', '1d', '1w']
const WEBSOCKET_CHANNELS: WebSocketChannel[] = [
  'market_updates',
  'price_updates',
  'signal_updates',
  'portfolio_updates',
  'position_updates',
  'risk_updates',
  'system_events',
  'learning_updates',
]
const NAV_ITEMS: { label: ScreenName; shortLabel: string; icon: ReactNode }[] = [
  { label: 'Overview', shortLabel: 'Overview', icon: <LayoutDashboard size={12} /> },
  { label: 'Markets', shortLabel: 'Markets', icon: <CandlestickChart size={12} /> },
  { label: 'AI Signals', shortLabel: 'Signals', icon: <Sparkles size={12} /> },
  { label: 'Market Analysis', shortLabel: 'Analysis', icon: <SearchCheck size={12} /> },
  { label: 'Portfolio', shortLabel: 'Portfolio', icon: <Wallet size={12} /> },
  { label: 'Positions', shortLabel: 'Positions', icon: <ListChecks size={12} /> },
  { label: 'Trade History', shortLabel: 'History', icon: <FileClock size={12} /> },
  { label: 'Intelligence', shortLabel: 'Intelligence', icon: <Network size={12} /> },
  { label: 'Learning', shortLabel: 'Learning', icon: <GraduationCap size={12} /> },
  { label: 'Strategy Lab', shortLabel: 'Strategy Lab', icon: <CandlestickChart size={12} /> },
  { label: 'Community Library', shortLabel: 'Community', icon: <Network size={12} /> },
  { label: 'Risk Management', shortLabel: 'Risk', icon: <ShieldAlert size={12} /> },
  { label: 'Activity', shortLabel: 'Activity', icon: <Activity size={12} /> },
  { label: 'Settings', shortLabel: 'Settings', icon: <Settings2 size={12} /> },
]
const QUICK_PROMPTS = [
  'Analyze BTCUSDT',
  'What are the strongest opportunities?',
  'What is the current market regime?',
  'How is the simulated portfolio performing?',
  'What is the current risk exposure?',
]

const EMPTY_DATA: DashboardData = {
  market: null,
  candles: [],
  portfolio: null,
  heatmap: [],
  breadth: null,
  volume: null,
  longShort: null,
  risk: null,
  signals: [],
  learning: null,
  events: [],
  markets: [],
  positions: [],
  openOrders: [],
  trades: [],
  tradeStats: null,
  strategies: [],
  strategyWeights: {},
  predictions: [],
  performance: null,
  strategyComparison: null,
  models: [],
  riskAlerts: [],
  settings: null,
  analysisCandles: {},
  volumeAnalytics: null,
  health: null,
}

const DEFAULT_PREFERENCES: DashboardPreferences = {
  autoScale: true,
  crosshair: true,
  showRiskAlerts: true,
}

function readPreferences(): DashboardPreferences {
  try {
    const stored = window.localStorage.getItem('blackmarket-dashboard-preferences')
    if (!stored) return DEFAULT_PREFERENCES
    const parsed: unknown = JSON.parse(stored)
    if (!parsed || typeof parsed !== 'object') return DEFAULT_PREFERENCES
    const value = parsed as Partial<DashboardPreferences>
    return {
      autoScale: typeof value.autoScale === 'boolean' ? value.autoScale : DEFAULT_PREFERENCES.autoScale,
      crosshair: typeof value.crosshair === 'boolean' ? value.crosshair : DEFAULT_PREFERENCES.crosshair,
      showRiskAlerts: typeof value.showRiskAlerts === 'boolean' ? value.showRiskAlerts : DEFAULT_PREFERENCES.showRiskAlerts,
    }
  } catch (error) {
    console.warn('Unable to read dashboard preferences', error)
    return DEFAULT_PREFERENCES
  }
}

function numberValue(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function formatPrice(value: number | undefined): string {
  if (value === undefined) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: 2,
    maximumFractionDigits: value < 1 ? 6 : 2,
  })
}

function formatMoney(value: number | undefined): string {
  return value === undefined ? '—' : `$${formatPrice(value)}`
}

function formatCompact(value: number | undefined): string {
  if (value === undefined) return '—'
  return new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

function formatChange(value: number | undefined): string {
  if (value === undefined) return '—'
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function formatTimestamp(value: string | undefined): string {
  if (!value) return '—'
  const timestamp = Date.parse(value)
  return Number.isFinite(timestamp)
    ? new Date(timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'UTC' })
    : '—'
}

function metricText(value: number | null | undefined, digits = 2): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(digits) : '—'
}

function PanelHeading({
  title,
  detail,
  action,
}: {
  title: string
  detail?: ReactNode
  action?: ReactNode
}) {
  return (
    <div className="panel-heading">
      <h2>{title}</h2>
      <div className="panel-heading-right">{detail}{action}</div>
    </div>
  )
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  const alertNumber = /\b(SELL|LOW|RISK|ALERT)\b/i.test(label)
  return <div className="stat"><span>{label}</span><b className={`${tone ?? ''}${alertNumber ? ' alert-digit' : ''}`.trim()}>{value}</b></div>
}

function App() {
  const isTauri = typeof window !== 'undefined' && '__TAURI_INTERNALS__' in window
  const hasBootstrappedRef = useRef(false)
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [searchValue, setSearchValue] = useState('BTCUSDT')
  const [marketType, setMarketType] = useState<'SPOT' | 'FUTURES'>('SPOT')
  const [timeframe, setTimeframe] = useState('1h')
  const [data, setData] = useState(EMPTY_DATA)
  const [startupStatus, setStartupStatus] = useState<StartupStatus>({
    state: 'checking',
    message: 'Checking the backend connection.',
  })
  const [apiReady, setApiReady] = useState(false)
  const [websocketConnected, setWebsocketConnected] = useState(false)
  const [websocketInitialized, setWebsocketInitialized] = useState(false)
  const [marketDataStatus, setMarketDataStatus] = useState<MarketDataState>('disconnected')
  const [marketDataStatusKey, setMarketDataStatusKey] = useState('')
  const [historyLoadingKeys, setHistoryLoadingKeys] = useState<Set<string>>(() => new Set())
  const [historyExhaustedKey, setHistoryExhaustedKey] = useState('')
  const [historyFailure, setHistoryFailure] = useState<{ key: string; message: string } | null>(null)
  const [socketError, setSocketError] = useState('')
  const [retryToken, setRetryToken] = useState(0)
  const [connection, setConnection] = useState<Connection>('connecting')
  const [loadedMarketKey, setLoadedMarketKey] = useState('')
  const [loadedAnalyticsKey, setLoadedAnalyticsKey] = useState('')
  const [indicators, setIndicators] = useState<Indicator[]>([])
  const [preferences, setPreferences] = useState<DashboardPreferences>(readPreferences)
  const [popup, setPopup] = useState<Popup>(null)
  const [activeScreen, setActiveScreen] = useState<ScreenName>('Overview')
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  useEffect(() => {
    if (!mobileMenuOpen && !popup) return
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return
      setMobileMenuOpen(false)
      setPopup(null)
    }
    window.addEventListener('keydown', handleEscape)
    return () => window.removeEventListener('keydown', handleEscape)
  }, [mobileMenuOpen, popup])
  const [assistantHelpOpen, setAssistantHelpOpen] = useState(false)
  const [searchError, setSearchError] = useState('')
  const [messages, setMessages] = useState<ChatMessage[]>([
    { id: 1, role: 'assistant', text: 'Local assistant ready. Answers use only market, signal, portfolio, risk, learning, and activity data from this BlackMarket AI session.' },
  ])
  const [messageInput, setMessageInput] = useState('')
  const refreshMarketRef = useRef<() => void>(() => {})
  const refreshAnalyticsRef = useRef<() => void>(() => {})
  const refreshScreenDataRef = useRef<() => void>(() => {})
  const historyRequestsRef = useRef(new Set<string>())
  const historyKeyRef = useRef('')
  const historyGenerationRef = useRef(0)
  const lastHistoryRequestAtRef = useRef(0)
  const loadedMarketKeyRef = useRef('')

  useEffect(() => {
    let active = true
    let checking = false
    const startedAt = Date.now()
    const checkStartup = async () => {
      if (checking) return
      checking = true
      let nativeStatus: StartupStatus | null = null
      if (isTauri) {
        try {
          nativeStatus = await invoke<StartupStatus>('backend_startup_status')
        } catch (error) {
          nativeStatus = {
            state: 'failed',
            message: 'The desktop backend supervisor could not be contacted.',
            details: String(error),
          }
        }
      }

      let ready = false
      let authenticationFailed = false
      let healthError = isTauri ? 'The local API is not responding yet.' : 'The hosted API is not responding yet.'
      const controller = new AbortController()
      const requestTimeout = window.setTimeout(() => controller.abort(), 5000)
      try {
        const response = await fetch(isTauri ? `${backendBaseUrl().replace(/\/api$/, '')}/health` : '/api/health', {
          signal: controller.signal,
          cache: 'no-store',
        })
        if (!response.ok) {
          healthError = `The ${isTauri ? 'local' : 'hosted'} API returned HTTP ${response.status}.`
        } else {
          const healthPayload: unknown = await response.json()
          const health = !isTauri && typeof healthPayload === 'object' && healthPayload !== null && 'backend' in healthPayload
            ? healthPayload.backend
            : healthPayload
          if (typeof health === 'object' && health !== null && 'backend_ready' in health
            && health.backend_ready === true && 'database_connected' in health
            && health.database_connected === true) {
            if (isTauri) {
              const token = await invoke<string>('backend_api_token')
              if (!token) throw new Error('The desktop supervisor returned an empty API token.')
              setApiToken(token)
            }
            const authenticatedResponse = await fetch(
              isTauri ? `${backendBaseUrl()}/system/status` : `${backendBaseUrl()}/system/status`,
              {
                headers: isTauri ? getApiAuthorization() : undefined,
                signal: controller.signal,
                cache: 'no-store',
              },
            )
            if (authenticatedResponse.ok) ready = true
            else {
              authenticationFailed = authenticatedResponse.status === 401
              healthError = `The authenticated API check returned HTTP ${authenticatedResponse.status}.`
              setApiToken(null)
            }
          } else {
            setApiToken(null)
            healthError = 'The backend is responding but has not reported database readiness.'
          }
        }
      } catch (error) {
        setApiToken(null)
        healthError = error instanceof Error && error.message.includes('API token')
          ? error.message
          : `The ${isTauri ? 'local' : 'hosted'} API is unreachable or its authenticated startup check failed.`
        authenticationFailed = isTauri && nativeStatus?.state === 'ready'
      } finally {
        window.clearTimeout(requestTimeout)
      }

      if (active) {
        setApiReady(ready)
        if (ready) {
          setStartupStatus({
            state: 'ready',
            message: isTauri ? 'The local backend API and database are ready.' : 'The hosted backend API and database are ready.',
          })
        } else {
          setMarketDataStatus('disconnected')
          setMarketDataStatusKey('')
          setApiToken(null)
          setLoadedMarketKey('')
          setLoadedAnalyticsKey('')
          setData(EMPTY_DATA)
          setWebsocketConnected(false)
          setWebsocketInitialized(false)
          if (isTauri && nativeStatus) {
            setStartupStatus(authenticationFailed
              ? {
                  state: 'failed',
                  message: healthError,
                  details: nativeStatus.details,
                  logPath: nativeStatus.logPath,
                }
              : nativeStatus.state === 'ready'
              ? {
                  state: 'starting',
                  message: healthError,
                  details: nativeStatus.details,
                  logPath: nativeStatus.logPath,
                }
              : nativeStatus)
          } else if (!isTauri && Date.now() - startedAt >= 30000) {
            setStartupStatus({
              state: 'failed',
              message: 'The hosted backend is unavailable.',
              details: 'The website cannot launch the Python engine. Check the hosted backend service and its health endpoint.'
            })
          } else {
            setStartupStatus({
              state: 'checking',
              message: isTauri ? nativeStatus?.message ?? healthError : healthError,
            })
          }
        }
      }
      checking = false
    }

    void checkStartup()
    const timer = window.setInterval(() => void checkStartup(), 1000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [isTauri, retryToken])

  useEffect(() => {
    if (!apiReady) {
      return
    }

    let active = true
    let marketTimer: ReturnType<typeof setTimeout> | undefined
    let analyticsTimer: ReturnType<typeof setTimeout> | undefined
    const socket = getWebSocket()
    let initialized = false

    const scheduleMarketRefresh = () => {
      if (marketTimer) clearTimeout(marketTimer)
      marketTimer = setTimeout(() => refreshMarketRef.current(), 350)
    }
    const scheduleAnalyticsRefresh = () => {
      if (analyticsTimer) clearTimeout(analyticsTimer)
      analyticsTimer = setTimeout(() => {
        refreshAnalyticsRef.current()
        refreshScreenDataRef.current()
      }, 500)
    }
    const removeStateListener = socket.on('stateChange', (state) => {
      if (!active || typeof state !== 'string') return
      setWebsocketConnected(state === 'connected')
      if (state === 'connected') {
        initialized = true
        setWebsocketInitialized(true)
        setSocketError('')
      }
    })
    const removeErrorListener = socket.on('error', (error) => {
      if (active && !initialized) {
        setSocketError(error instanceof Error ? error.message : String(error))
      }
    })
    const unsubscribe = WEBSOCKET_CHANNELS.map((channel) => socket.subscribe(channel, () => {
      if (channel === 'price_updates' || channel === 'market_updates') scheduleMarketRefresh()
      if (channel !== 'price_updates') scheduleAnalyticsRefresh()
    }))
    void socket.connect().catch((error: unknown) => {
      if (active) setSocketError(error instanceof Error ? error.message : String(error))
    })

    return () => {
      active = false
      if (marketTimer) clearTimeout(marketTimer)
      if (analyticsTimer) clearTimeout(analyticsTimer)
      removeStateListener()
      removeErrorListener()
      unsubscribe.forEach((remove) => remove())
      destroyWebSocket()
    }
  }, [apiReady, retryToken])

  useEffect(() => {
    try {
      window.localStorage.setItem('blackmarket-dashboard-preferences', JSON.stringify(preferences))
    } catch (error) {
      console.warn('Unable to save dashboard preferences', error)
    }
  }, [preferences])

  useEffect(() => {
    let active = true
    const marketKey = marketChartKey(symbol, marketType, timeframe)
    const analyticsKey = `${symbol}:${marketType}`
    historyGenerationRef.current += 1
    historyKeyRef.current = marketKey
    lastHistoryRequestAtRef.current = 0
    let marketRequestGeneration = 0
    const refreshMarket = async () => {
      const requestGeneration = ++marketRequestGeneration
      const marketQuery = `?market=${marketType}`
      const candleQuery = `?market=${marketType}&timeframe=${timeframe}&limit=1000`
      const [snapshotPayload, candlePayload] = await Promise.all([
        requestJson<MarketSnapshot>(`/markets/${encodeURIComponent(symbol)}${marketQuery}`),
        requestJson<unknown>(`/markets/${encodeURIComponent(symbol)}/candles${candleQuery}`),
      ])
      // Polling and websocket-triggered refreshes can overlap. Only the newest
      // request for this market key may update the visible quote and candles.
      if (!active || requestGeneration !== marketRequestGeneration) return
      const emptyCandleSeries = typeof candlePayload === 'object'
        && candlePayload !== null
        && 'candles' in candlePayload
        && Array.isArray(candlePayload.candles)
        && candlePayload.candles.length === 0
      if (!snapshotPayload && emptyCandleSeries && symbol !== 'BTCUSDT') {
        setSearchValue('BTCUSDT')
        setSymbol('BTCUSDT')
        return
      }
      const assessment = assessMarketData(snapshotPayload, candlePayload, symbol, marketType)
      const marketDataIsUsable = assessment.dataLoaded
      setData((current) => {
        const olderHistory = marketDataIsUsable
          && loadedMarketKeyRef.current === marketKey
          && assessment.candles.length
          ? current.candles.filter((candle) => candle.time < assessment.candles[0].time)
          : []
        return {
          ...current,
          market: assessment.snapshot,
          candles: marketDataIsUsable
            ? mergeMarketCandles(olderHistory, assessment.candles)
            : [],
        }
      })
      setMarketDataStatus(assessment.state)
      setMarketDataStatusKey(marketKey)
      loadedMarketKeyRef.current = marketDataIsUsable ? marketKey : ''
      setLoadedMarketKey(marketDataIsUsable ? marketKey : '')
      setConnection(
        assessment.state === 'ready' ? 'live' : assessment.state === 'degraded' ? 'degraded' : 'offline',
      )
    }

    const refreshAnalytics = async () => {
      const query = `?symbol=${encodeURIComponent(symbol)}&market=${marketType}`
      const [
        portfolio,
        heatmapPayload,
        breadth,
        volume,
        longShort,
        risk,
        signalPayload,
        learning,
        activityPayload,
        health,
      ] = await Promise.all([
        requestJson<Portfolio>('/portfolio/summary'),
        requestJson<{ heatmap?: HeatmapItem[] }>('/markets/heatmap'),
        requestJson<Breadth>('/markets/breadth'),
        requestJson<VolumeStats>(`/markets/volume${query}`),
        requestJson<LongShortStats>(`/markets/long-short?symbol=${encodeURIComponent(symbol)}`),
        requestJson<RiskMetrics>('/risk/status'),
        requestJson<{ signals?: Signal[] }>('/signals'),
        requestJson<LearningStatus>('/learning/status'),
        requestJson<{ events?: SystemEvent[] }>('/activity?limit=100'),
        requestJson<Record<string, unknown>>('/health', false),
      ])
      if (!active) return
      setData((current) => ({
        ...current,
        portfolio,
        heatmap: heatmapPayload?.heatmap ?? [],
        breadth,
        volume,
        longShort,
        risk,
        signals: signalPayload?.signals ?? [],
        learning,
        events: activityPayload?.events ?? [],
        health,
        riskAlerts: (activityPayload?.events ?? []).filter((event) => event.event_type === 'RISK_ALERT'),
      }))
      setLoadedAnalyticsKey(analyticsKey)
    }

    refreshMarketRef.current = () => { void refreshMarket() }
    refreshAnalyticsRef.current = () => { void refreshAnalytics() }
    if (!apiReady) {
      return () => {
        active = false
      }
    }

    void refreshMarket()
    void refreshAnalytics()
    const marketTimer = window.setInterval(() => void refreshMarket(), 10_000)
    const analyticsTimer = window.setInterval(() => void refreshAnalytics(), 30_000)
    return () => {
      active = false
      window.clearInterval(marketTimer)
      window.clearInterval(analyticsTimer)
    }
  }, [apiReady, marketType, symbol, timeframe])

  useEffect(() => {
    let active = true
    const refreshScreenData = async () => {
      if (activeScreen === 'Markets' || activeScreen === 'Intelligence') {
        const [marketPayload, strategyPayload, strategyWeights] = await Promise.all([
          requestJson<{ markets?: WorkspaceData['markets'] }>('/markets'),
          activeScreen === 'Intelligence'
            ? requestJson<{ metrics?: WorkspaceData['strategies'] }>('/intelligence/strategies')
            : Promise.resolve(null),
          activeScreen === 'Intelligence'
            ? requestJson<Record<string, unknown>>('/intelligence/weights')
            : Promise.resolve(null),
        ])
        if (!active) return
        setData((current) => ({
          ...current,
          markets: marketPayload?.markets ?? current.markets,
          strategies: strategyPayload?.metrics ?? current.strategies,
          strategyWeights: strategyWeights ?? current.strategyWeights,
        }))
      }

      if (activeScreen === 'Portfolio' || activeScreen === 'Positions' || activeScreen === 'Trade History') {
        const [positionsPayload, tradesPayload, ordersPayload] = await Promise.all([
          requestJson<{ positions?: WorkspaceData['positions'] }>('/positions'),
          requestJson<{
            trades?: WorkspaceData['trades']
            total?: number
            total_pnl?: number
            win_rate?: number
            profit_factor?: number
            max_drawdown_pct?: number
          }>('/trades?limit=1000'),
          activeScreen === 'Positions' ? requestJson<{ orders?: WorkspaceData['openOrders'] }>('/trades/orders') : Promise.resolve(null),
        ])
        if (!active) return
        setData((current) => ({
          ...current,
          positions: positionsPayload?.positions ?? current.positions,
          openOrders: ordersPayload?.orders ?? current.openOrders,
          trades: tradesPayload?.trades ?? current.trades,
          tradeStats: tradesPayload ? {
            total: tradesPayload.total,
            total_pnl: tradesPayload.total_pnl,
            win_rate: tradesPayload.win_rate,
            profit_factor: tradesPayload.profit_factor,
            max_drawdown_pct: tradesPayload.max_drawdown_pct,
          } : current.tradeStats,
        }))
      }

      if (activeScreen === 'Learning') {
        const [predictionsPayload, modelPayload, performancePayload, comparisonPayload] = await Promise.all([
          requestJson<{ predictions?: WorkspaceData['predictions'] }>('/learning/predictions?limit=1000'),
          requestJson<{ models?: WorkspaceData['models'] }>('/learning/models'),
          requestJson<WorkspaceData['performance']>('/learning/performance'),
          requestJson<WorkspaceData['strategyComparison']>(`/learning/strategy-comparison?symbol=${encodeURIComponent(symbol)}&market=${marketType}&timeframe=1h&limit=1000`),
        ])
        if (!active) return
        setData((current) => ({
          ...current,
          predictions: predictionsPayload?.predictions ?? current.predictions,
          performance: performancePayload ?? current.performance,
          strategyComparison: comparisonPayload ?? current.strategyComparison,
          models: modelPayload?.models ?? current.models,
        }))
      }

      if (activeScreen === 'Settings') {
        const settings = await requestJson<WorkspaceData['settings']>('/settings')
        if (active) setData((current) => ({ ...current, settings: settings ?? current.settings }))
      }

      if (activeScreen === 'Market Analysis') {
        const results = await Promise.all(TIMEFRAMES.map(async (interval) => {
          const response = await requestJson<unknown>(
            `/markets/${encodeURIComponent(symbol)}/candles?market=${marketType}&timeframe=${interval}&limit=500`,
          )
          return [interval, parseMarketCandles(response)] as const
        }))
        if (!active) return
        setData((current) => ({
          ...current,
          analysisCandles: Object.fromEntries(results),
        }))
      }
    }

    refreshScreenDataRef.current = () => { void refreshScreenData() }
    if (!apiReady) {
      return () => {
        active = false
      }
    }

    void refreshScreenData()
    const timer = window.setInterval(() => void refreshScreenData(), 30_000)
    return () => {
      active = false
      window.clearInterval(timer)
    }
  }, [activeScreen, apiReady, marketType, symbol])

  const currentMarketKey = marketChartKey(symbol, marketType, timeframe)
  const currentAnalyticsKey = `${symbol}:${marketType}`
  const currentMarketDataStatus = marketDataStatusKey === currentMarketKey
    ? marketDataStatus
    : apiReady ? 'loading' : 'disconnected'
  const historyLoading = historyLoadingKeys.has(currentMarketKey)
  const hasMoreHistory = historyExhaustedKey !== currentMarketKey
  const historyError = historyFailure?.key === currentMarketKey ? historyFailure.message : ''
  const marketDataLoaded = loadedMarketKey === currentMarketKey
    && (currentMarketDataStatus === 'ready' || currentMarketDataStatus === 'degraded')
  const marketReady = marketDataLoaded && currentMarketDataStatus === 'ready'
  const analyticsReady = loadedAnalyticsKey === currentAnalyticsKey
  const appReady = apiReady && websocketInitialized && marketDataLoaded && analyticsReady
  useEffect(() => {
    if (appReady) hasBootstrappedRef.current = true
  }, [appReady])
  const visibleMarket = marketDataLoaded ? data.market : null
  const visibleCandles = marketDataLoaded ? data.candles : []
  const visibleVolume = analyticsReady ? data.volume : null
  const visibleLongShort = analyticsReady ? data.longShort : null
  const visibleConnection = !marketDataLoaded
    ? apiReady ? currentMarketDataStatus === 'error' ? 'offline' : 'connecting' : 'offline'
    : currentMarketDataStatus === 'ready' ? connection : 'degraded'
  const currentPrice = numberValue(visibleMarket?.price) ?? visibleCandles.at(-1)?.close
  const priceChange = numberValue(visibleMarket?.price_change_24h)
  const currentRegime = visibleMarket?.regime
  const portfolio = data.portfolio
  const totalBalance = numberValue(portfolio?.total_balance)
  const spotBalance = numberValue(portfolio?.spot_balance)
  const futuresBalance = numberValue(portfolio?.futures_balance)
  const totalReturn = numberValue(portfolio?.total_return_pct)
  const spotShare = totalBalance && spotBalance !== undefined ? Math.round((spotBalance / totalBalance) * 100) : undefined
  const breadthTotal = (data.breadth?.advancing ?? 0) + (data.breadth?.declining ?? 0) + (data.breadth?.neutral ?? 0)
  const advancePct = breadthTotal ? ((data.breadth?.advancing ?? 0) / breadthTotal) * 100 : 0
  const declinePct = breadthTotal ? ((data.breadth?.declining ?? 0) / breadthTotal) * 100 : 0
  const longRatio = numberValue(visibleLongShort?.long_short_ratio)
  const longPct = numberValue(visibleLongShort?.long_volume)
  const shortPct = numberValue(visibleLongShort?.short_volume)
  const riskCapacity = numberValue(data.risk?.used_risk_capacity_pct)
  const riskStatus = data.risk?.risk_manager_status
  const marketActivity = numberValue(visibleMarket?.volume_24h)
  const heatCells = data.heatmap.slice(0, 48)
  const latestSignals = data.signals.slice(0, 5)
  const riskAlerts = data.events.filter((event) => event.event_type === 'RISK_ALERT').slice(0, 6)
  const connectionText = !marketDataLoaded
    ? currentMarketDataStatus === 'error' ? 'ERROR' : apiReady ? 'LOADING' : 'DISCONNECTED'
    : marketReady ? 'READY' : 'DEGRADED'
  const historyPath = useMemo(() => {
    const history = (visibleLongShort?.history ?? []).filter((row) => numberValue(row.ratio) !== undefined)
    if (history.length < 2) return ''
    const values = history.map((row) => row.ratio as number)
    const min = Math.min(...values)
    const max = Math.max(...values)
    const range = max - min || 1
    return values.map((value, index) => {
      const x = (index / (values.length - 1)) * 360
      const y = 40 - ((value - min) / range) * 32
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(1)} ${y.toFixed(1)}`
    }).join(' ')
  }, [visibleLongShort?.history])

  const submitSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    const nextSymbol = searchValue.trim().toUpperCase().replace(/[^A-Z0-9]/g, '')
    if (nextSymbol.length < 2) {
      setSearchError('Enter at least two letters or digits.')
      return
    }
    setSearchError('')
    setSymbol(nextSymbol)
    setSearchValue(nextSymbol)
    setPopup(null)
  }

  const indicatorToggle = (indicator: Indicator) => {
    setIndicators((current) => current.includes(indicator)
      ? current.filter((item) => item !== indicator)
      : [...current, indicator])
  }

  const changePreferences = (next: DashboardPreferences) => setPreferences(next)

  const assistantAnswer = (question: string): string => {
    const normalized = question.toLowerCase()
    if (normalized.includes('strongest') || normalized.includes('opportunit')) {
      const opportunities = data.heatmap
        .filter((item) => numberValue(item.price_change_24h) !== undefined && (item.price_change_24h ?? 0) > 0)
        .sort((left, right) => (right.relative_strength_pct ?? right.price_change_24h ?? 0) - (left.relative_strength_pct ?? left.price_change_24h ?? 0))
        .slice(0, 3)
      return opportunities.length
        ? `Strongest positive relative-strength markets in the loaded ticker set: ${opportunities.map((item) => `${item.symbol} (${formatChange(item.price_change_24h)}, relative strength ${formatChange(item.relative_strength_pct ?? undefined)})`).join('; ')}. These are market observations, not trade recommendations.`
        : 'No eligible opportunity data is currently available in the local market snapshot.'
    }
    if (normalized.includes('signal') || normalized.includes('explain')) {
      const signal = latestSignals[0]
      return signal
        ? `${signal.symbol} ${signal.direction} · ${signal.strategy} · ${signal.status} · ${signal.data_freshness ?? 'freshness unavailable'}. ${signal.reasons?.length ? `Recorded reasons: ${signal.reasons.join('; ')}.` : 'No recorded rationale is attached to this signal.'}`
        : 'No persisted AI signal is available in the local event history.'
    }
    if (normalized.includes('reject')) {
      const rejected = data.events.find((event) => event.event_type === 'SIGNAL_REJECTED')
      if (!rejected) return 'No persisted rejected-signal event is available in the local activity history.'
      const payload = rejected.payload ?? {}
      const reason = payload.reason ?? payload.rejection_reason ?? payload.message
      return `${rejected.symbol ?? 'Signal'} rejection${reason ? `: ${String(reason)}` : ' is recorded'}. ${Array.isArray(payload.reasons) ? payload.reasons.join('; ') : 'Inspect the Activity event for the full risk decision.'}`
    }
    if (normalized.includes('regime')) {
      return currentRegime
        ? `${symbol} ${marketType} is classified as ${currentRegime} in the latest loaded market snapshot.`
        : `The local market snapshot does not currently include a regime classification for ${symbol}.`
    }
    if (normalized.includes('portfolio') || normalized.includes('perform')) {
      return portfolio
        ? `Combined virtual equity ${formatMoney(totalBalance)}; realized P&L ${formatMoney(numberValue(portfolio.realized_pnl))}; unrealized P&L ${formatMoney(numberValue(portfolio.unrealized_pnl))}; daily realized P&L ${formatMoney(numberValue(portfolio.daily_pnl))}; drawdown ${formatChange(numberValue(portfolio.drawdown_pct))}. Spot and Futures remain separate.`
        : 'Portfolio data is unavailable until the local backend responds.'
    }
    if (normalized.includes('learning') || normalized.includes('improv')) {
      const learning = data.learning
      if (!learning) return 'Learning engine status is unavailable until the local backend responds.'
      const resolved = learning.predictions_resolved ?? 0
      return resolved
        ? `${learning.model_status ?? 'Model status unavailable'}${learning.version ? ` (${learning.version})` : ''}; ${resolved} predictions resolved from ${learning.predictions_total ?? 0}; measured accuracy ${metricText(learning.accuracy)}%. This records outcome accuracy, not a causal claim of improvement.`
        : `${learning.model_status ?? 'Model status unavailable'}; there are not yet resolved predictions to measure learning performance.`
    }
    if (normalized.includes('risk') || normalized.includes('exposure')) {
      return data.risk
        ? `Risk manager ${riskStatus ?? 'status unavailable'}. Exposure ${formatChange(numberValue(data.risk.current_exposure_pct))}; used capacity ${formatChange(riskCapacity)}; available capacity ${formatChange(numberValue(data.risk.available_risk_capacity_pct))}; daily loss capacity ${formatChange(numberValue(data.risk.daily_loss_capacity_pct))}.`
        : 'Risk metrics are unavailable until the local backend responds.'
    }
    const marketInfo = visibleMarket
      ? `${symbol} ${marketType}: ${formatPrice(currentPrice)} (${formatChange(priceChange)} over 24h), regime ${currentRegime ?? 'unavailable'}.`
      : `${symbol} market data is unavailable.`
    return `${marketInfo} Ask about opportunities, signals, rejected trades, regime, portfolio, learning, or risk for a local-data summary.`
  }

  const sendMessage = async (text: string) => {
    const trimmed = text.trim()
    if (!trimmed) return
    const userId = Date.now()
    const assistantId = userId + 1
    setMessages((current) => [
      ...current,
      { id: userId, role: 'user', text: trimmed },
      { id: assistantId, role: 'assistant', text: 'Checking the local market data…' },
    ])
    setMessageInput('')
    try {
      const payload = await mutateJson<{
        answer?: string
        status?: string
        tool?: string
        sources?: string[]
        disclaimer?: string
      }>('/assistant/query', 'POST', {
        query: trimmed,
        symbol,
        market: marketType,
        timeframe,
      })
      const answer = payload?.answer
        ? `${payload.answer}${payload.sources?.length ? `\n\nSource: ${payload.sources.join(', ')}` : ''}${payload.disclaimer ? `\n\n${payload.disclaimer}` : ''}`
        : 'The local assistant endpoint returned no answer. Check the backend connection and try again.'
      setMessages((current) => current.map((message) =>
        message.id === assistantId ? { ...message, text: answer } : message,
      ))
    } catch (error) {
      const fallback = assistantAnswer(trimmed)
      setMessages((current) => current.map((message) =>
        message.id === assistantId
          ? { ...message, text: `Local assistant unavailable (${String(error)}).\\n\\nFallback summary from currently loaded dashboard data: ${fallback}` }
          : message,
      ))
    }
  }

  const submitMessage = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void sendMessage(messageInput)
  }

  const changeNavigation = (label: ScreenName) => {
    setActiveScreen(label)
    setMobileMenuOpen(false)
    setPopup(null)
  }

  const runWindowAction = (action: 'minimize' | 'toggleMaximize' | 'close') => {
    if (!isTauri) return
    void import('@tauri-apps/api/window').then(({ getCurrentWindow }) => getCurrentWindow()[action]()).catch((error: unknown) => console.error(`Unable to ${action} application window`, error))
  }

  const downloadRiskData = () => {
    if (!data.risk) return
    const exportData = {
      exported_at: new Date().toISOString(),
      risk: data.risk,
      alerts: riskAlerts,
    }
    const url = URL.createObjectURL(new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url
    link.download = `blackmarket-risk-${new Date().toISOString().replace(/[:.]/g, '-')}.json`
    document.body.append(link)
    link.click()
    link.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }

  const retryStartup = async () => {
    setSocketError('')
    setApiToken(null)
    setStartupStatus({ state: 'checking', message: 'Retrying local startup checks.' })
    setWebsocketInitialized(false)
    setWebsocketConnected(false)
    if (isTauri && (!apiReady || startupStatus.state === 'failed')) {
      try {
        await invoke('retry_backend_startup')
      } catch (error) {
        setStartupStatus({
          state: 'failed',
          message: 'The desktop application could not restart the backend.',
          details: String(error),
        })
      }
    }
    setRetryToken((current) => current + 1)
  }

  const loadOlderCandles = async () => {
    if (
      historyRequestsRef.current.has(currentMarketKey)
      || !hasMoreHistory
      || loadedMarketKeyRef.current !== currentMarketKey
      || historyKeyRef.current !== currentMarketKey
      || Date.now() - lastHistoryRequestAtRef.current < 1000
    ) return
    const oldest = data.candles[0]
    if (!oldest) return

    if (historyRequestsRef.current.has(currentMarketKey)) return
    const requestGeneration = historyGenerationRef.current
    historyRequestsRef.current.add(currentMarketKey)
    lastHistoryRequestAtRef.current = Date.now()
    setHistoryLoadingKeys((current) => new Set(current).add(currentMarketKey))
    setHistoryFailure((current) => current?.key === currentMarketKey ? null : current)
    const endTime = oldest.time * 1000 - 1
    try {
      const payload = await requestJson<unknown>(
        `/markets/${encodeURIComponent(symbol)}/candles?market=${marketType}&timeframe=${timeframe}&limit=500&end_time=${endTime}`,
      )
      if (historyKeyRef.current !== currentMarketKey || historyGenerationRef.current !== requestGeneration) return
      if (!payload || typeof payload !== 'object' || !('candles' in payload) || !Array.isArray(payload.candles)) {
        setHistoryFailure({
          key: currentMarketKey,
          message: 'Unable to load older candles. Pan left to retry.',
        })
        return
      }

      const now = Date.now()
      const older = parseMarketCandles(payload).filter((candle) =>
        candle.time < oldest.time
        && candle.closeTime !== undefined
        && candle.closeTime <= endTime
        && candle.closeTime < now)
      const merged = mergeMarketCandles(data.candles, older)
      if (merged.length === data.candles.length) {
        setHistoryExhaustedKey(currentMarketKey)
        return
      }
      setData((current) => ({
        ...current,
        candles: mergeMarketCandles(current.candles, older),
      }))
    } finally {
      historyRequestsRef.current.delete(currentMarketKey)
      setHistoryLoadingKeys((current) => {
        if (!current.has(currentMarketKey)) return current
        const next = new Set(current)
        next.delete(currentMarketKey)
        return next
      })
    }
  }

  return (
    <main className="terminal">
      {!appReady && (
        <aside className={`startup-toast ${startupStatus.state === 'failed' || socketError || currentMarketDataStatus === 'error' ? 'is-error' : 'is-loading'}`} role="status" aria-live="polite">
          <span className="startup-toast-indicator" aria-hidden="true" />
          <span className="startup-toast-copy">
            <strong>{startupStatus.state === 'failed' ? 'Backend unavailable' : !apiReady ? 'Connecting to backend' : !websocketInitialized ? 'Connecting live updates' : 'Loading market data'}</strong>
            <small>{startupStatus.state === 'failed' ? startupStatus.message : socketError || (!apiReady ? startupStatus.message : currentMarketDataStatus === 'error' ? 'Market data is unavailable. Dashboard remains accessible.' : 'Dashboard is available while services initialize.')}</small>
          </span>
          {startupStatus.state === 'failed' && (
            <button type="button" className="startup-toast-action" onClick={() => void retryStartup()}>Retry</button>
          )}
          <button type="button" className="startup-toast-dismiss" aria-label="Dismiss connection notice" onClick={(event) => event.currentTarget.parentElement?.remove()}>×</button>
        </aside>
      )}
      <header className="topbar" data-tauri-drag-region>
        <button className={`mobile-menu icon-button ${mobileMenuOpen ? 'selected' : ''}`} type="button" aria-label="Toggle navigation" aria-expanded={mobileMenuOpen} aria-controls="application-navigation" onClick={() => setMobileMenuOpen((open) => !open)}>
          <MoreHorizontal size={16} />
        </button>
        <a className="brand" href="#" aria-label="BlackMarket AI home" onClick={() => changeNavigation('Overview')}>
          <span className="brand-mark"><Activity size={17} strokeWidth={1.8} /></span>
          <span>BlackMarket<span className="brand-ai"> AI</span></span>
        </a>
        <form className="global-search" onSubmit={submitSearch}>
          <Search size={13} />
          <input
            aria-label="Search a market symbol"
            aria-describedby={searchError ? 'market-search-error' : undefined}
            aria-invalid={Boolean(searchError)}
            value={searchValue}
            onChange={(event) => {
              setSearchValue(event.target.value)
              setSearchError('')
            }}
            placeholder="Search any market"
          />
          <kbd>↵</kbd>
          {searchError && <span id="market-search-error" className="search-error" role="alert">{searchError}</span>}
        </form>
        <div className="top-actions">
          <button className="header-status" onClick={() => setPopup((current) => current === 'status' ? null : 'status')} aria-label="System status">
            <i className={`status-light ${visibleConnection}`} />{connectionText}
          </button>
          <button className="icon-button notification-button" aria-label="Notifications" onClick={() => setPopup((current) => current === 'notifications' ? null : 'notifications')}>
            <Bell size={14} />{preferences.showRiskAlerts && riskAlerts.length > 0 && <i />}
          </button>
          <button className="icon-button" aria-label="Settings" onClick={() => changeNavigation('Settings')}><Settings2 size={14} /></button>
          {isTauri && (
            <div className="window-controls" aria-label="Window controls">
              <button aria-label="Minimize window" onClick={() => runWindowAction('minimize')}><Minus size={12} /></button>
              <button aria-label="Toggle maximize window" onClick={() => runWindowAction('toggleMaximize')}><MinusCircle size={11} /></button>
              <button aria-label="Close window" onClick={() => runWindowAction('close')}><X size={12} /></button>
            </div>
          )}
        </div>
        {popup && (
          <div className={`nav-popover ${popup}`} role="dialog" aria-label={`${popup} panel`}>
            <div className="popover-heading">
              <strong>{popup === 'notifications' ? 'Recent risk alerts' : popup === 'status' ? 'System status' : 'Chart settings'}</strong>
              <button className="icon-button" aria-label="Close panel" onClick={() => setPopup(null)}><X size={13} /></button>
            </div>
            {popup === 'notifications' && (
              <div className="popover-list">
                {riskAlerts.length ? riskAlerts.map((event, index) => (
                  <div className="popover-row" key={event.event_id ?? index}>
                    <span><b>{event.symbol ?? 'Risk manager'}</b><small>{String(event.payload?.message ?? event.event_type ?? 'Risk alert')}</small></span>
                    <span className="popover-value">{formatTimestamp(event.timestamp)}</span>
                  </div>
                )) : <p className="popover-empty">No risk alerts in the loaded activity history.</p>}
              </div>
            )}
            {popup === 'status' && (
              <div className="popover-learning">
                <span>MARKET DATA <b>{connectionText}</b></span>
                <span>BACKEND <b>{String(data.health?.backend_ready === true ? 'READY' : data.health?.status ?? 'UNAVAILABLE').toUpperCase()}</b></span>
                <span>SCANNER <b>{data.health?.market_data_active === true ? 'ACTIVE' : 'INACTIVE / UNKNOWN'}</b></span>
                <span>PAPER TRADING <b>SIMULATED ONLY</b></span>
              </div>
            )}
            {popup === 'chart' && (
              <div className="settings-options">
                <button onClick={() => setPreferences((current) => ({ ...current, autoScale: !current.autoScale }))}><span>Auto-scale price</span><b>{preferences.autoScale ? 'ON' : 'OFF'}</b></button>
                <button onClick={() => setPreferences((current) => ({ ...current, crosshair: !current.crosshair }))}><span>Crosshair</span><b>{preferences.crosshair ? 'ON' : 'OFF'}</b></button>
                {(['SMA20', 'EMA20'] as const).map((indicator) => (
                  <button key={indicator} onClick={() => indicatorToggle(indicator)}>
                    <span>{indicator} indicator</span><b>{indicators.includes(indicator) ? <Check size={12} /> : 'OFF'}</b>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </header>

      <nav id="application-navigation" className={`screen-navigation ${mobileMenuOpen ? 'mobile-open' : ''}`} aria-label="Application screens">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.label}
            className={`screen-tab ${activeScreen === item.label ? 'active' : ''}`}
            onClick={() => changeNavigation(item.label)}
            aria-current={activeScreen === item.label ? 'page' : undefined}
            title={item.label}
          >
            {item.icon}<span>{item.shortLabel}</span>
          </button>
        ))}
      </nav>

      {activeScreen === 'Overview' ? <div className="dashboard">
        <section className="market-column">
          <section className="panel chart-panel" id="market-chart">
            <div className="market-toolbar">
              <div className="instrument">
                <span className="coin-mark">{symbol.slice(0, 1)}</span>
                <div>
                  <strong>{symbol.replace(/USDT$/, '')}<span className="quote"> / {symbol.endsWith('USDT') ? 'USDT' : 'QUOTE'}</span></strong>
                  <small>{marketType} · Binance public market</small>
                </div>
                <span className={`connection-state ${visibleConnection}`}><i />{connectionText}</span>
              </div>
              <div className="instrument-actions">
                <button className={`market-switch ${marketType === 'SPOT' ? 'selected' : ''}`} onClick={() => setMarketType('SPOT')}>SPOT</button>
                <button className={`market-switch ${marketType === 'FUTURES' ? 'selected' : ''}`} onClick={() => setMarketType('FUTURES')}>FUTURES</button>
                <button className="icon-button" aria-label="Chart settings" onClick={() => setPopup((current) => current === 'chart' ? null : 'chart')}><Settings2 size={14} /></button>
                <button className="icon-button chart-expand" aria-label="Open detailed market analysis" onClick={() => changeNavigation('Market Analysis')}><SearchCheck size={13} /></button>
              </div>
            </div>
            <div className="chart-subbar">
              <div className="chart-quote">
                <span className="price">{formatPrice(currentPrice)}</span>
                <span className={priceChange === undefined ? 'muted' : priceChange >= 0 ? 'positive' : 'negative'}>{formatChange(priceChange)}</span>
                <span className="quote-divider" />
                <span>24H QUOTE VOL <b>{formatCompact(marketActivity)}</b></span>
                {currentRegime && <span className="regime-badge">{currentRegime}</span>}
              </div>
              <div className="chart-controls">
                <span className="control-label">INTERVAL</span>
                {TIMEFRAMES.map((item) => (
                  <button
                    key={item}
                    type="button"
                    className={`timeframe-button ${timeframe === item ? 'selected' : ''}`}
                    aria-pressed={timeframe === item}
                    onClick={() => setTimeframe(item)}
                  >
                    {item}
                  </button>
                ))}
                <button className="icon-button chart-tools" aria-label="Chart options" onClick={() => setPopup((current) => current === 'chart' ? null : 'chart')}><SlidersHorizontal size={13} /></button>
              </div>
            </div>
            <div className="live-chart-wrap">
              {visibleCandles.length
                ? <>
                  <LiveMarketChart
                    key={currentMarketKey}
                    candles={visibleCandles}
                    symbol={symbol}
                    marketType={marketType}
                    timeframe={timeframe}
                    indicators={indicators}
                    autoScale={preferences.autoScale}
                    crosshair={preferences.crosshair}
                    onLoadOlder={() => { void loadOlderCandles() }}
                  />
                  <span className="chart-history-status" aria-live="polite">
                    {historyLoading ? 'Loading older candles…' : historyError || (!hasMoreHistory ? 'No older candles available.' : '')}
                  </span>
                </>
                : <div className="chart-empty">{visibleConnection === 'offline' ? 'Binance market data is unavailable.' : 'Loading Binance candles…'}</div>}
            </div>
            <div className="chart-footer">
              <span>DATA SOURCE <b>{visibleConnection === 'live' ? 'BINANCE · PUBLIC REST' : visibleConnection === 'degraded' ? 'STALE / PARTIAL' : visibleConnection === 'offline' ? 'UNAVAILABLE' : 'CONNECTING'}</b></span>
              <span>{visibleCandles.length ? `${visibleCandles.length} CANDLES` : 'NO CANDLE DATA'}</span>
              <span>UTC <b>{timeframe}</b></span>
            </div>
          </section>

          <div className="middle-grid">
            <section className="panel heatmap-panel">
              <PanelHeading title="Market heatmap" detail="24H · BINANCE TICKERS" />
              <div className="heatmap-grid">
                {heatCells.length ? heatCells.map((item, index) => {
                  const change = numberValue(item.price_change_24h)
                  const activity = Math.max(0, Math.min(1, (item.volume_rank_pct ?? 0) / 100))
                  const intensity = Math.min(4, Math.floor(Math.min(1, Math.abs(change ?? 0) / 20 + activity * 0.45) * 5))
                  const heatmapTones = ['#19191E', '#29292F', '#414149', '#66666F', '#A1A1AA']
                  const color = heatmapTones[intensity]
                  const title = `${item.symbol ?? 'Market'} ${item.market ?? ''} · 24h ${formatChange(change)} · relative strength ${formatChange(item.relative_strength_pct ?? undefined)} · volume rank ${metricText(item.volume_rank_pct)}% · volatility ${item.volatility_24h_pct == null ? 'unavailable' : `${metricText(item.volatility_24h_pct)}%`}`
                  return (
                    <button
                      key={`${item.market ?? 'market'}-${item.symbol ?? index}`}
                      className="heat-cell"
                      style={{ backgroundColor: color }}
                      title={title}
                      onClick={() => {
                        if (!item.symbol) return
                        setSymbol(item.symbol)
                        setSearchValue(item.symbol)
                        if (item.market === 'SPOT' || item.market === 'FUTURES') setMarketType(item.market)
                      }}
                    >
                      {item.symbol?.replace(/USDT$/, '') ?? '—'}
                    </button>
                  )
                }) : <span className="empty-panel-note">Waiting for ticker snapshots</span>}
              </div>
              <div className="heatmap-footer"><span>Markets tracked <b>{data.heatmap.length || '—'}</b></span><span>24h return · activity rank · relative strength</span></div>
            </section>

            <section className="panel breadth-panel">
              <PanelHeading title="Market breadth" detail="SPOT + FUTURES" />
              <div className="breadth-summary">
                <div className="breadth-big"><strong>{breadthTotal ? Math.round(advancePct) : '—'}<small>{breadthTotal ? '%' : ''}</small></strong><span>ADVANCING</span></div>
                <div className="breadth-side">
                  <div><i className="legend-dot up" /><span>Advancing</span><b>{data.breadth?.advancing ?? '—'}</b></div>
                  <div><i className="legend-dot down" /><span>Declining</span><b>{data.breadth?.declining ?? '—'}</b></div>
                  <div><i className="legend-dot neutral" /><span>Neutral</span><b>{data.breadth?.neutral ?? '—'}</b></div>
                </div>
              </div>
              <div className="breadth-bar"><span style={{ width: `${advancePct}%` }} /><span style={{ width: `${Math.max(0, 100 - advancePct - declinePct)}%` }} /><span style={{ width: `${declinePct}%` }} /></div>
              <div className="breadth-metrics">
                <span>24H QUOTE LIQUIDITY <b>{formatCompact(numberValue(data.breadth?.total_volume))}</b></span>
                <span>AVG SPREAD <b>{data.breadth?.avg_spread_bps == null ? '—' : `${metricText(data.breadth.avg_spread_bps)} bps`}</b></span>
                <span>AVG BOOK IMBALANCE <b>{data.breadth?.avg_orderbook_imbalance == null ? '—' : metricText(data.breadth.avg_orderbook_imbalance, 3)}</b></span>
              </div>
              <div className="holder-labels"><span>MARKETS WITH SNAPSHOTS</span><span>{breadthTotal || '—'}</span></div>
            </section>
          </div>

          <div className="bottom-grid">
            <section className="panel volume-panel">
              <PanelHeading title="Buy / sell volume" detail={visibleVolume?.flow_is_estimated === false ? 'MEASURED AGGRESSOR FLOW' : visibleVolume?.flow_is_estimated ? 'ESTIMATED FLOW' : 'FLOW UNAVAILABLE'} />
              <div className="stat-row volume-stats">
                <Stat label="BUY FLOW · QUOTE" value={formatCompact(numberValue(visibleVolume?.buy_volume ?? undefined))} tone="positive" />
                <Stat label="SELL FLOW · QUOTE" value={formatCompact(numberValue(visibleVolume?.sell_volume ?? undefined))} tone="negative" />
                <Stat label="24H QUOTE TOTAL" value={formatCompact(numberValue(visibleVolume?.total_volume))} />
              </div>
              <div className="volume-chart">
                {visibleCandles.slice(-22).length
                  ? visibleCandles.slice(-22).map((bar, index, bars) => {
                    const max = Math.max(1, ...bars.map((item) => item.volume ?? 0))
                    return <span key={`${bar.time}-${index}`} className={bar.close >= bar.open ? 'up' : 'down'} style={{ height: `${Math.max(4, ((bar.volume ?? 0) / max) * 100)}%` }} title={`${timeframe} candle base-asset volume: ${formatCompact(bar.volume)}`} />
                  })
                  : <span className="empty-chart-note">Candle volume unavailable</span>}
              </div>
              <div className="micro-labels">
                <span>BUY</span><span>SELL</span>
                <span className="flow-note">{visibleVolume ? `${visibleVolume.flow_sample_size ?? 0} agg trades · ${visibleVolume.flow_sample_scope ?? 'sample scope unavailable'}` : 'Aggressor-flow sample unavailable'} · 24h comparison {visibleVolume?.volume_change_24h == null ? 'unavailable' : formatChange(visibleVolume.volume_change_24h)}</span>
              </div>
            </section>

            <section className="panel ratio-panel">
              <PanelHeading title="Long / short analytics" detail="FUTURES · PUBLIC DATA" />
              <div className="ratio-hero">
                <span className="ratio-number">{longRatio === undefined ? '—' : longRatio.toFixed(2)}</span>
                <span className="ratio-caption">LONG / SHORT ACCOUNTS</span>
                <span className="ratio-change">{visibleLongShort?.funding_rate == null ? 'Funding —' : `Funding ${(visibleLongShort.funding_rate * 100).toFixed(4)}%`}</span>
              </div>
              <div className="ratio-track" style={{ background: longPct === undefined ? '#303336' : undefined }}><span style={{ width: `${longPct === undefined ? 0 : Math.max(0, Math.min(100, longPct))}%` }} /></div>
              <div className="ratio-labels">
                <span><i className="legend-dot up" />Long <b>{longPct === undefined ? '—' : `${longPct.toFixed(1)}%`}</b></span>
                <span><i className="legend-dot down" />Short <b>{shortPct === undefined ? '—' : `${shortPct.toFixed(1)}%`}</b></span>
                <span>OI <b>{formatCompact(numberValue(visibleLongShort?.open_interest ?? undefined))}</b></span>
              </div>
              <svg className="ratio-sparkline" viewBox="0 0 360 44" preserveAspectRatio="none" aria-label="Historical long short ratio">
                {historyPath
                  ? <path d={historyPath} />
                  : <text x="180" y="24" textAnchor="middle">Historical ratio unavailable</text>}
                <line x1="0" x2="360" y1="41" y2="41" />
              </svg>
            </section>
          </div>
        </section>

        <aside className="analytics-column">
          <section className="panel portfolio-panel" id="portfolio-panel">
            <PanelHeading title="Paper portfolio" detail={<span className="paper-pill">PAPER ONLY</span>} action={<button className="icon-button" aria-label="Open portfolio screen" onClick={() => changeNavigation('Portfolio')}><MoreHorizontal size={15} /></button>} />
            <div className="portfolio-total">
              <span>COMBINED VIRTUAL EQUITY</span>
              <strong>{formatMoney(totalBalance)}</strong>
              <em className={totalReturn === undefined ? 'muted' : totalReturn >= 0 ? 'positive' : 'negative'}>
                <ArrowUpRight size={12} /> {totalReturn === undefined ? 'Initial equity $1,000 USDT' : `${formatChange(totalReturn)} total return`}
              </em>
            </div>
            <div className="portfolio-split">
              <div><span>SPOT EQUITY</span><b>{formatMoney(spotBalance)}</b><small>Initial $500 USDT</small></div>
              <div><span>FUTURES EQUITY</span><b>{formatMoney(futuresBalance)}</b><small>Initial $500 USDT</small></div>
            </div>
            <div className="portfolio-allocation" aria-label="Spot and Futures equity allocation">
              <span style={{ width: `${spotShare ?? 0}%` }} />
              <i style={{ width: `${spotShare === undefined ? 0 : 100 - spotShare}%` }} />
            </div>
            <div className="portfolio-metrics">
              <Stat label="DAILY REALIZED" value={formatMoney(numberValue(portfolio?.daily_pnl))} tone={(portfolio?.daily_pnl ?? 0) >= 0 ? 'positive' : 'negative'} />
              <Stat label="MONTHLY REALIZED" value={formatMoney(numberValue(portfolio?.monthly_pnl))} tone={(portfolio?.monthly_pnl ?? 0) >= 0 ? 'positive' : 'negative'} />
              <Stat label="REALIZED" value={formatMoney(numberValue(portfolio?.realized_pnl))} />
              <Stat label="UNREALIZED" value={formatMoney(numberValue(portfolio?.unrealized_pnl))} />
              <Stat label="MAX DRAWDOWN" value={formatChange(numberValue(portfolio?.drawdown_pct))} />
              <Stat label="ALLOCATION" value={spotShare === undefined ? '—' : `${spotShare}% / ${100 - spotShare}%`} />
            </div>
          </section>

          <section className="panel risk-panel">
            <PanelHeading title="Risk analytics" detail={<span className={`risk-state ${riskStatus?.toLowerCase() ?? 'unknown'}`}>{riskStatus ?? 'UNAVAILABLE'}</span>} action={<button className="icon-button" aria-label="Download risk data as JSON" title={data.risk ? 'Download the loaded risk snapshot and alerts' : 'Risk data is not available'} disabled={!data.risk} onClick={downloadRiskData}><ArrowDownToLine size={14} /></button>} />
            <div className="risk-content">
              <div className="risk-dial" style={{ background: `conic-gradient(from -90deg, #d9dbdc 0 ${riskCapacity ?? 0}%, #303336 ${riskCapacity ?? 0}% 100%)` }}>
                <div><strong className="risk-digit">{riskCapacity === undefined ? '—' : `${riskCapacity.toFixed(0)}%`}</strong><span>CAPACITY USED</span></div>
              </div>
              <div className="risk-stats">
                <div><span>Current exposure</span><b className="risk-digit">{formatChange(numberValue(data.risk?.current_exposure_pct))}</b></div>
                <div><span>Open trade risk</span><b className="risk-digit">{formatChange(numberValue(data.risk?.open_trade_risk_pct))}</b></div>
                <div><span>Available capacity</span><b className="risk-digit">{formatChange(numberValue(data.risk?.available_risk_capacity_pct))}</b></div>
                <div><span>Daily loss capacity</span><b className="risk-digit">{formatChange(numberValue(data.risk?.daily_loss_capacity_pct))}</b></div>
                {data.risk?.unmeasured_positions ? <div className="risk-warning"><span>Positions without stop risk</span><b className="alert-digit">{data.risk.unmeasured_positions}</b></div> : null}
              </div>
            </div>
            <div className="risk-foot"><span>LIMITS {data.risk ? `${metricText(data.risk.max_total_open_pct)}% OPEN · ${metricText(data.risk.max_daily_loss_pct)}% DAILY` : '—'}</span><span>LOCAL RISK MANAGER</span></div>
          </section>

          <section className="panel assistant-panel">
            <PanelHeading title="AI assistant" detail={<span className="assistant-status"><i /> LOCAL DATA</span>} action={<button className="icon-button" aria-label="Assistant help" aria-expanded={assistantHelpOpen} onClick={() => setAssistantHelpOpen((open) => !open)}><CircleHelp size={14} /></button>} />
            <div className="assistant-context"><Bot size={13} /><span>{symbol} · {marketType} · {currentRegime ?? 'regime unavailable'}</span><span className="assistant-context-time">{connectionText}</span></div>
            {assistantHelpOpen && (
              <div className="assistant-help-card" role="note">
                <span>Answers are generated locally from loaded market, signal, portfolio, risk, learning, and activity data. They are summaries, not trade instructions.</span>
                <button className="icon-button" aria-label="Close assistant help" onClick={() => setAssistantHelpOpen(false)}><X size={12} /></button>
              </div>
            )}
            <div className="chat-messages" aria-live="polite">
              {messages.slice(-8).map((message) => (
                <div key={message.id} className={`chat-message ${message.role}`}>
                  {message.role === 'assistant' && <Bot size={12} />}
                  <p>{message.text}</p>
                </div>
              ))}
            </div>
            <div className="assistant-suggestion">
              <select aria-label="Assistant prompt suggestions" value="" onChange={(event) => {
                if (event.target.value) sendMessage(event.target.value)
              }}>
                <option value="">Ask about local market intelligence…</option>
                {QUICK_PROMPTS.map((prompt) => <option key={prompt} value={prompt}>{prompt}</option>)}
                <option value="Explain the latest AI signal">Explain the latest AI signal</option>
                <option value="Why was a trade rejected?">Why was a trade rejected?</option>
                <option value="What has the learning engine improved?">What has the learning engine improved?</option>
              </select>
            </div>
            <form className="assistant-input" onSubmit={submitMessage}>
              <input aria-label="Ask the local assistant" value={messageInput} onChange={(event) => setMessageInput(event.target.value)} placeholder="Ask a local-data question…" />
              <button type="submit" disabled={!messageInput.trim()} aria-label="Send message"><Send size={14} /></button>
            </form>
          </section>
        </aside>
      </div> : (
        <DashboardScreen
          screen={activeScreen}
          symbol={symbol}
          marketType={marketType}
          data={data}
          preferences={preferences}
          onPreferencesChange={changePreferences}
          onStrategyLabRun={async (payload) => mutateJson('/learning/strategy-lab', 'POST', payload)}
          onStrategyLabCompare={async (payload) => mutateJson('/learning/strategy-lab/compare', 'POST', { ...payload, strategies: ['momentum', 'breakout', 'trend_following', 'mean_reversion', 'reversal'] })}
          onWorkspaceLoad={(workspace) => {
            const payload = workspace?.payload
            if (!payload || typeof payload !== 'object') return
            if (payload.dashboardData && typeof payload.dashboardData === 'object') {
              setData((current) => ({ ...current, ...payload.dashboardData }))
            }
            if (payload.preferences && typeof payload.preferences === 'object') {
              changePreferences(payload.preferences as DashboardPreferences)
            }
            if (typeof payload.symbol === 'string' && /^[A-Z0-9]{3,20}$/i.test(payload.symbol)) {
              setSymbol(payload.symbol.toUpperCase())
              setSearchValue(payload.symbol.toUpperCase())
            }
            if (payload.marketType === 'SPOT' || payload.marketType === 'FUTURES') setMarketType(payload.marketType)
            if (typeof payload.screen === 'string' && ['Overview','Markets','AI Signals','Market Analysis','Portfolio','Positions','Trade History','Intelligence','Learning','Strategy Lab','Community Library','Risk Management','Activity','Settings'].includes(payload.screen)) {
              setActiveScreen(payload.screen as ScreenName)
            }
          }}
          onSettingsSave={async (payload) => {
            await mutateJson('/settings', 'POST', payload)
            refreshScreenDataRef.current?.()
          }}
          onManualTrade={async (payload) => {
            await mutateJson('/trades', 'POST', payload)
            refreshScreenDataRef.current?.()
          }}
          onPositionAction={async (positionId, action, values) => {
            if (!positionId) throw new Error('Missing position identifier.')
            if (action === 'close') {
              await mutateJson(`/positions/${encodeURIComponent(positionId)}/close`, 'POST')
            } else if (action === 'partial-close') {
              await mutateJson(`/positions/${encodeURIComponent(positionId)}/partial-close`, 'POST', { quantity: values?.quantity })
            } else {
              await mutateJson(`/positions/${encodeURIComponent(positionId)}`, 'PATCH', values ?? {})
            }
            refreshScreenDataRef.current?.()
          }}
          onCancelOrder={async (orderId) => {
            await mutateJson(`/trades/orders/${encodeURIComponent(orderId)}`, 'DELETE')
            refreshScreenDataRef.current?.()
          }}
          onSelectMarket={(selectedSymbol, selectedMarket) => {
            setSymbol(selectedSymbol)
            setSearchValue(selectedSymbol)
            setMarketType(selectedMarket)
            setActiveScreen('Market Analysis')
          }}
        />
      )}

      <footer className="statusbar">
        <span><i className={`status-light ${visibleConnection}`} /> BINANCE PUBLIC DATA · {connectionText}</span>
        <span><i className={`status-light ${data.health?.backend_ready === true ? 'live' : 'offline'}`} /> BACKEND {data.health?.backend_ready === true ? 'READY' : 'UNAVAILABLE'}</span>
        <span><i className={`status-light ${websocketConnected ? 'live' : 'offline'}`} /> WEBSOCKET {websocketConnected ? 'CONNECTED' : 'RECONNECTING'}</span>
        <span><i className={`status-light ${data.health?.market_data_active === true ? 'live' : 'offline'}`} /> SCANNER {data.health?.market_data_active === true ? 'ACTIVE' : 'INACTIVE'}</span>
        <span className="status-right">PAPER MODE <b>·</b> NO LIVE TRADING</span>
      </footer>
    </main>
  )
}

export default App
