import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import type { FormEvent } from 'react'
import { mutateJson, requestJson } from '../services/backendClient'
import { DataTable as Table, DetailCard, EmptyState, ScreenHeader, SummaryCard, TableHead } from '../components/ui/TerminalPrimitives'
import type { FrontendDiagnosticEvent } from '../services/frontendDiagnostics'

export type ScreenName =
  | 'Overview'
  | 'Markets'
  | 'AI Signals'
  | 'Market Analysis'
  | 'Portfolio'
  | 'Positions'
  | 'Trade History'
  | 'Intelligence'
  | 'Learning'
  | 'Autonomous'
  | 'Strategy Lab'
  | 'Community Library'
  | 'Risk Management'
  | 'Activity'
  | 'Diagnostics'
  | 'Settings'

export type WorkspaceMarket = {
  symbol?: string
  market?: string
  base_asset?: string
  quote_asset?: string
  status?: string
  is_eligible?: boolean
  price?: number
  price_change_24h?: number
  volume_24h?: number
  bid_ask_spread?: number | null
  orderbook_imbalance?: number | null
  regime?: string
  timestamp?: string
  volatility_24h_pct?: number | null
  atr_24h_pct?: number | null
  data_age_seconds?: number | null
  data_freshness?: string
}

export type WorkspaceSignal = {
  signal_id?: string
  symbol?: string
  market?: string
  strategy?: string
  direction?: string
  timeframe?: string
  entry?: number
  stop_loss?: number
  take_profit?: number[]
  confidence?: number
  regime?: string
  reasons?: string[]
  status?: string
  created_at?: string
  data_freshness?: string
}

export type WorkspacePortfolio = {
  spot_balance?: number
  futures_balance?: number
  total_balance?: number
  spot_pnl?: number
  futures_pnl?: number
  total_pnl?: number
  daily_pnl?: number
  monthly_pnl?: number
  realized_pnl?: number
  unrealized_pnl?: number
  drawdown_pct?: number
  total_return_pct?: number
}

export type WorkspacePosition = {
  position_id?: string
  symbol?: string
  market?: string
  side?: string
  entry_price?: number
  current_price?: number
  amount?: number
  leverage?: number
  unrealized_pnl?: number
  fees_paid?: number
  stop_loss?: number | null
  take_profit?: number | null
  liquidation_price?: number | null
  margin_ratio?: number | null
  opened_at?: string
  strategy?: string | null
}

export type WorkspaceOrder = {
  order_id?: string
  symbol?: string
  market?: string
  side?: string
  entry_price?: number
  amount?: number
  status?: string
  order_type?: string
  created_at?: string
}

export type WorkspaceTrade = {
  position_id?: string
  symbol?: string
  market?: string
  side?: string
  entry_price?: number
  exit_price?: number
  amount?: number
  leverage?: number
  pnl?: number
  pnl_pct?: number
  fee?: number
  strategy?: string
  opened_at?: string
  closed_at?: string
  close_reason?: string
  max_favorable_excursion_pct?: number
  max_adverse_excursion_pct?: number
  prediction_correct?: boolean | null
  risk_calculation_verified?: boolean | null
}

export type WorkspaceTradeStats = {
  total?: number
  total_pnl?: number
  win_rate?: number
  profit_factor?: number
  max_drawdown_pct?: number
}

export type WorkspaceStrategy = {
  strategy?: string
  market?: string
  total_signals?: number
  validated_signals?: number
  winning_trades?: number
  losing_trades?: number
  win_rate?: number
  total_pnl?: number
  profit_factor?: number
  weight?: number
}

export type WorkspacePrediction = {
  prediction_id?: string
  symbol?: string
  market?: string
  timeframe?: string
  model_version?: string
  regime?: string | null
  horizon_minutes?: number
  predicted_class?: string
  confidence?: number
  actual_outcome?: string | null
  actual_return_pct?: number | null
  simulated_pnl?: number | null
  is_correct?: boolean | null
  created_at?: string
}

export type WorkspaceModel = {
  version?: string
  model_type?: string
  trained_at?: string
  metrics?: Record<string, unknown> | string
  status?: string
  is_active?: boolean
  is_champion?: boolean
  parent_version?: string | null
}

export type WorkspaceRisk = {
  current_exposure_pct?: number
  used_risk_capacity_pct?: number
  available_risk_capacity_pct?: number
  open_trade_risk_pct?: number
  daily_loss_capacity_pct?: number
  risk_manager_status?: string
  max_spot_positions?: number
  max_futures_positions?: number
  max_leverage?: number
  risk_per_trade_pct?: number
  max_daily_loss_pct?: number
  max_total_open_pct?: number
  unmeasured_positions?: number
}

export type WorkspaceEvent = {
  event_id?: string
  event_type?: string
  timestamp?: string
  source?: string
  symbol?: string | null
  market?: string | null
  payload?: Record<string, unknown>
}

export type WorkspaceLearning = {
  model_status?: string
  version?: string | null
  rf_loaded?: boolean
  xgb_loaded?: boolean
  river_available?: boolean
  predictions_total?: number
  predictions_resolved?: number
  accuracy?: number
  training_state?: string
  training_samples?: number
  last_training_at?: string | null
  last_cycle_status?: string
  last_training_result?: {
    status?: string
    reason?: string
    validation?: {
      promotion_gate?: {
        failure_reasons?: string[]
        criteria?: Record<string, number>
        models?: Record<string, {
          passes?: boolean
          mean_f1?: number | null
          mean_accuracy?: number | null
          calibration_score?: number | null
          fold_count?: number
          failure_reasons?: string[]
          economic_evidence?: { net_expectancy?: number; max_drawdown_pct?: number; positive_net_folds?: number; regime_coverage?: number }
        }>
      }
      models?: Record<string, {
        aggregated?: { mean_f1?: number; mean_accuracy?: number; mean_precision?: number; mean_recall?: number }
        folds?: Array<{ fold?: number; train_size?: number; test_size?: number; accuracy?: number; precision_macro?: number; recall_macro?: number; f1_macro?: number; test_start_time?: number; test_end_time?: number }>
      }>
      validation_provenance?: { method?: string; out_of_sample?: boolean; purge_gap_ms?: number; sample_count?: number; rf_oof_count?: number; xgb_oof_count?: number }
    }
    batch_validation?: { promotion_gate?: { failure_reasons?: string[] } }
    river_metrics?: Record<string, unknown>
    holdout_report?: {
      holdout_samples?: number
      train_samples?: number
      accuracy?: number
      precision_macro?: number
      recall_macro?: number
      f1_macro?: number
      validation_method?: string
      holdout_untouched?: boolean
      train_end_timestamp?: number | null
      holdout_start_timestamp?: number | null
      holdout_end_timestamp?: number | null
      thresholds?: { accuracy_min?: number; f1_macro_min?: number }
      failure_reasons?: string[]
    }
  } | null
  river_updates?: number
}

export type WorkspaceSettings = {
  spot_enabled?: boolean
  futures_enabled?: boolean
  scan_all_eligible_symbols?: boolean
  timeframes?: string[]
  spot_initial_balance?: number
  futures_initial_balance?: number
  risk_per_trade_pct?: number
  risk_max_daily_loss_pct?: number
  risk_max_total_open_pct?: number
  risk_max_leverage?: number
  max_spot_positions?: number
  max_futures_positions?: number
  telegram_enabled?: boolean
  telegram_bot_token_configured?: boolean
  telegram_chat_id_configured?: boolean
  autonomous_enabled?: boolean
  telegram_notify_decisions?: boolean
  telegram_notify_executions?: boolean
  telegram_notify_risk?: boolean
  telegram_notify_learning?: boolean
}

export type AnalysisCandle = {
  time: number
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export type DashboardPreferences = {
  autoScale: boolean
  crosshair: boolean
  showRiskAlerts: boolean
}

export type StrategyComparisonResult = {
  strategy: string
  status: string
  total_return_pct?: number
  max_drawdown_pct?: number
  sharpe_ratio?: number | null
  win_rate_pct?: number
  profit_factor?: number | 'infinite' | null
  trades_evaluated?: number
  evaluation_bars?: number
}
export type StrategyComparison = {
  status: string
  symbol?: string
  market?: string
  timeframe?: string
  candles?: number
  evaluation_start_time?: string
  evaluation_end_time?: string
  walk_forward_folds?: number
  training_policy?: string
  cost_policy?: string
  strategies: StrategyComparisonResult[]
}

export type ModelPerformance = {
  prediction_count: number
  accuracy_pct: number | null
  precision_macro_pct: number | null
  recall_macro_pct: number | null
  trade_count: number
  profit_factor: number | 'infinite' | null
  win_rate_pct: number | null
  max_drawdown_pct: number | null
  sharpe_ratio: number | null
}

export type WorkspaceData = {
  volumeAnalytics?: {
    total_volume?: number
    average_daily_quote_volume_7d?: number | null
    volume_change_vs_7d_avg_pct?: number | null
    comparison_period?: string | null
    data_age_seconds?: number | null
    data_freshness?: string
    buy_volume?: number | null
    sell_volume?: number | null
    flow_sample_size?: number
    flow_sample_scope?: string | null
  } | null
  markets: WorkspaceMarket[]
  signals: WorkspaceSignal[]
  portfolio: WorkspacePortfolio | null
  positions: WorkspacePosition[]
  openOrders: WorkspaceOrder[]
  trades: WorkspaceTrade[]
  tradeStats: WorkspaceTradeStats | null
  strategies: WorkspaceStrategy[]
  strategyWeights: Record<string, unknown>
  intelligenceAnalysis: Record<string, any> | null
  predictions: WorkspacePrediction[]
  performance: ModelPerformance | null
  strategyComparison: StrategyComparison | null
  models: WorkspaceModel[]
  learning: WorkspaceLearning | null
  risk: WorkspaceRisk | null
  events: WorkspaceEvent[]
  riskAlerts: WorkspaceEvent[]
  settings: WorkspaceSettings | null
  analysisCandles: Record<string, AnalysisCandle[]>
}

type AutonomousStatus = {
  mode?: string; enabled?: boolean; running?: boolean; entry_ready?: boolean;
  readiness_reasons?: string[]; model_available?: boolean; model_version?: string | null;
  open_positions?: number; open_orders?: number; strategies?: string[];
  last_decision?: Record<string, any> | null;
  learning?: { state?: string; last_cycle_status?: string };
  telegram?: { enabled?: boolean; configured?: boolean; connected?: boolean; last_error?: string | null };
}

type Props = {
  screen: ScreenName
  symbol: string
  marketType: 'SPOT' | 'FUTURES'
  data: WorkspaceData
  activityLoadState: 'loading' | 'ready' | 'error'
  diagnostics: {
    isDesktop: boolean
    backendState: string
    apiReady: boolean
    websocketConnected: boolean
    marketDataStatus: string
    health: Record<string, unknown> | null
    logs: string[]
    logState: 'loading' | 'ready' | 'error' | 'unavailable'
    frontendEvents: FrontendDiagnosticEvent[]
      requestMetrics: {
        windowSeconds: number
        requestCount: number
        failureCount: number
        averageDurationMs: number
        p95DurationMs: number
      }
  }
  intelligenceLoadState: 'loading' | 'ready' | 'error'
  preferences: DashboardPreferences
  onPreferencesChange: (preferences: DashboardPreferences) => void
  onSelectMarket: (symbol: string, market: 'SPOT' | 'FUTURES') => void
  onPositionAction: (positionId: string, action: 'close' | 'update' | 'partial-close', values?: { stop_loss?: number; take_profit?: number; quantity?: number }) => Promise<void>
  onCancelOrder: (orderId: string) => Promise<void>
  onManualTrade: (payload: { symbol: string; market: 'SPOT' | 'FUTURES'; side: 'BUY' | 'SELL' | 'LONG' | 'SHORT'; order_type: 'MARKET' | 'LIMIT'; quantity: number; price?: number; stop_loss: number; take_profit?: number; leverage: number }) => Promise<void>
  onSettingsSave: (settings: Record<string, unknown>) => Promise<void>
  onStrategyLabRun: (payload: Record<string, unknown>) => Promise<any>
  onStrategyLabCompare: (payload: Record<string, unknown>) => Promise<any>
  onWorkspaceLoad: (workspace: any) => void
}

const TIMEFRAMES = ['1m', '3m', '5m', '15m', '30m', '1h', '4h', '1d', '1w']

function num(value: unknown): number | undefined {
  return typeof value === 'number' && Number.isFinite(value) ? value : undefined
}

function price(value: number | undefined): string {
  if (value === undefined) return '—'
  return value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: value < 1 ? 6 : 2 })
}

function money(value: number | undefined): string {
  return value === undefined ? '—' : `${value < 0 ? '-$' : '$'}${price(Math.abs(value))}`
}

function compact(value: number | undefined): string {
  return value === undefined ? '—' : new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 2 }).format(value)
}

function pct(value: number | undefined): string {
  return value === undefined ? '—' : `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

function timestamp(value: string | undefined): string {
  if (!value) return '—'
  const parsed = Date.parse(value)
  return Number.isFinite(parsed) ? new Date(parsed).toLocaleString() : '—'
}

function rr(signal: WorkspaceSignal): string {
  const entry = num(signal.entry)
  const stop = num(signal.stop_loss)
  const target = num(signal.take_profit?.[0])
  if (entry === undefined || stop === undefined || target === undefined || entry === stop) return '—'
  const risk = Math.abs(entry - stop)
  const reward = /SHORT|SELL/i.test(signal.direction ?? '') ? entry - target : target - entry
  return reward > 0 ? `${(reward / risk).toFixed(2)}R` : 'Invalid target'
}

function rsi(candles: AnalysisCandle[], period = 14): number | undefined {
  if (candles.length <= period) return undefined
  let gains = 0
  let losses = 0
  for (let index = candles.length - period; index < candles.length; index += 1) {
    const change = candles[index].close - candles[index - 1].close
    if (change > 0) gains += change
    else losses -= change
  }
  if (losses === 0) return gains === 0 ? 50 : 100
  const relativeStrength = gains / losses
  return 100 - 100 / (1 + relativeStrength)
}

function meanClose(candles: AnalysisCandle[], period: number): number | undefined {
  if (candles.length < period) return undefined
  const slice = candles.slice(-period)
  return slice.reduce((sum, candle) => sum + candle.close, 0) / period
}

function dateOfLastCandle(candles: AnalysisCandle[]): string {
  const time = candles.at(-1)?.time
  return time === undefined ? '—' : timestamp(new Date(time * 1000).toISOString())
}

function SignalInspector({
  signal,
  onClose,
  onSelectMarket,
}: {
  signal: WorkspaceSignal
  onClose: () => void
  onSelectMarket: Props['onSelectMarket']
}) {
  return (
    <section className="workspace-inspector" aria-label="Signal details">
      <div className="workspace-inspector-heading">
        <strong>{signal.symbol ?? 'Signal'} · {signal.direction ?? 'Decision unavailable'}</strong>
        <button className="table-action" onClick={onClose}>Close</button>
      </div>
      <div className="workspace-detail-grid">
        <DetailCard label="ACCOUNT" value={signal.market ?? '—'} />
        <DetailCard label="STRATEGY / TIMEFRAME" value={`${signal.strategy ?? '—'} · ${signal.timeframe ?? '—'}`} />
        <DetailCard label="ENTRY / STOP" value={`${price(num(signal.entry))} / ${price(num(signal.stop_loss))}`} />
        <DetailCard label="TARGETS" value={signal.take_profit?.length ? signal.take_profit.map(price).join(' / ') : 'Not supplied'} />
        <DetailCard label="RISK / REWARD" value={rr(signal)} />
        <DetailCard label="CONFIDENCE SCORE" value={signal.confidence == null ? '—' : signal.confidence.toFixed(3)} />
        <DetailCard label="STATUS / FRESHNESS" value={`${signal.status ?? '—'} / ${signal.data_freshness ?? 'UNKNOWN'}`} />
        <DetailCard label="RECORDED" value={timestamp(signal.created_at)} />
      </div>
      <div className="workspace-note">{signal.reasons?.length ? `Recorded rationale: ${signal.reasons.join('; ')}` : 'No rationale was recorded for this signal.'}</div>
      <button
        className="table-action"
        disabled={!signal.symbol}
        onClick={() => onSelectMarket(signal.symbol ?? '', signal.market === 'FUTURES' ? 'FUTURES' : 'SPOT')}
      >
        Analyze market
      </button>
    </section>
  )
}

function PositionInspector({
  position,
  onClose,
  onPositionAction,
}: {
  position: WorkspacePosition
  onClose: () => void
  onPositionAction: Props['onPositionAction']
}) {
  const [stopLoss, setStopLoss] = useState(position.stop_loss?.toString() ?? '')
  const [takeProfit, setTakeProfit] = useState(position.take_profit?.toString() ?? '')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [closeQuantity, setCloseQuantity] = useState('')
  return (
    <section className="workspace-inspector" aria-label="Position details">
      <div className="workspace-inspector-heading">
        <strong>{position.symbol ?? 'Position'} · {position.side ?? '—'} · {position.market ?? '—'}</strong>
        <button className="table-action" onClick={onClose}>Close</button>
      </div>
      <div className="workspace-detail-grid">
        <DetailCard label="POSITION ID" value={position.position_id ?? '—'} />
        <DetailCard label="ENTRY / CURRENT" value={`${price(num(position.entry_price))} / ${price(num(position.current_price))}`} />
        <DetailCard label="AMOUNT / LEVERAGE" value={`${num(position.amount)?.toPrecision(6) ?? '—'} / ${position.leverage ?? '—'}x`} />
        <DetailCard label="UNREALIZED P&L" value={money(num(position.unrealized_pnl))} />
        <DetailCard label="STOP / TARGET" value={`${price(num(position.stop_loss ?? undefined))} / ${price(num(position.take_profit ?? undefined))}`} />
        <DetailCard label="LIQUIDATION / MARGIN" value={`${price(num(position.liquidation_price ?? undefined))} / ${position.margin_ratio == null ? '—' : `${(position.margin_ratio * 100).toFixed(2)}%`}`} />
        <DetailCard label="FEES / STRATEGY" value={`${money(num(position.fees_paid))} / ${position.strategy ?? '—'}`} />
        <DetailCard label="OPENED" value={timestamp(position.opened_at)} />
      </div>
      <div className="workspace-inspector-actions">
        <label>Stop loss <input className="workspace-search" type="number" min="0" step="any" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)} /></label>
        <label>Take profit <input className="workspace-search" type="number" min="0" step="any" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} /></label>
        <button className="table-action" disabled={busy || (!stopLoss && !takeProfit)} onClick={async () => {
          setBusy(true); setMessage('')
          try {
            await onPositionAction(position.position_id ?? '', 'update', {
              ...(stopLoss ? { stop_loss: Number(stopLoss) } : {}),
              ...(takeProfit ? { take_profit: Number(takeProfit) } : {}),
            })
            setMessage('Risk levels updated.')
          } catch (error) { setMessage(error instanceof Error ? error.message : 'Update failed.') }
          finally { setBusy(false) }
        }}>Update risk levels</button>
        <label>Partial close quantity <input className="workspace-search" type="number" min="0" step="any" value={closeQuantity} onChange={(event) => setCloseQuantity(event.target.value)} placeholder="Less than open amount" /></label>
        <button className="table-action" disabled={busy || !Number.isFinite(Number(closeQuantity)) || Number(closeQuantity) <= 0 || Number(closeQuantity) >= (position.amount ?? 0)} onClick={async () => {
          if (!window.confirm(`Partially close ${closeQuantity} of this paper position?`)) return
          setBusy(true); setMessage('')
          try {
            await onPositionAction(position.position_id ?? '', 'partial-close', { quantity: Number(closeQuantity) })
            setCloseQuantity('')
            setMessage('Partial close completed.')
          } catch (error) { setMessage(error instanceof Error ? error.message : 'Partial close failed.') }
          finally { setBusy(false) }
        }}>Partial close</button>
        <button className="table-action" disabled={busy} onClick={async () => {
          if (!window.confirm('Close this paper position at the latest available market price?')) return
          setBusy(true); setMessage('')
          try { await onPositionAction(position.position_id ?? '', 'close'); onClose() }
          catch (error) { setMessage(error instanceof Error ? error.message : 'Close failed.') }
          finally { setBusy(false) }
        }}>Close position</button>
        {message && <span role="status">{message}</span>}
      </div>
    </section>
  )
}

function MarketScreen({ data, onSelectMarket }: Pick<Props, 'data' | 'onSelectMarket'>) {
  const [query, setQuery] = useState('')
  const [marketFilter, setMarketFilter] = useState<'ALL' | 'SPOT' | 'FUTURES'>('ALL')
  const markets = useMemo(() => {
    const needle = query.trim().toUpperCase()
    return data.markets
      .filter((market) => marketFilter === 'ALL' || market.market === marketFilter)
      .filter((market) => !needle || market.symbol?.includes(needle) || market.base_asset?.includes(needle))
      .sort((left, right) => (right.volume_24h ?? 0) - (left.volume_24h ?? 0))
  }, [data.markets, marketFilter, query])
  return (
    <>
      <ScreenHeader
        title="Markets"
        description={`Eligible monitored Binance Spot and USDⓈ-M Futures instruments · ${data.markets.length.toLocaleString()} ticker snapshots`}
        actions={(
          <>
            <input className="workspace-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter symbol" aria-label="Filter markets" />
            <select className="workspace-select" value={marketFilter} onChange={(event) => setMarketFilter(event.target.value as typeof marketFilter)} aria-label="Market type filter">
              <option value="ALL">All markets</option><option value="SPOT">Spot</option><option value="FUTURES">Futures</option>
            </select>
          </>
        )}
      />
      <div className="workspace-summary">
        <SummaryCard label="VISIBLE SNAPSHOTS" value={markets.length.toLocaleString()} />
        <SummaryCard label="SPOT" value={data.markets.filter((market) => market.market === 'SPOT').length.toLocaleString()} />
        <SummaryCard label="USDⓈ-M FUTURES" value={data.markets.filter((market) => market.market === 'FUTURES').length.toLocaleString()} />
        <SummaryCard label="DATA" value={data.markets.length ? 'PUBLIC TICKERS' : 'UNAVAILABLE'} detail="No private exchange credentials" />
      </div>
      {markets.length ? (
        <Table minWidth={900}>
          <TableHead labels={['SYMBOL', 'MARKET', 'LAST PRICE', '24H CHANGE', '24H QUOTE VOL', 'REALIZED VOL', 'ATR 24H', 'DATA AGE', 'FRESHNESS', 'ACTION']} />
          {markets.slice(0, 1000).map((market, index) => (
            <tr key={`${market.market}-${market.symbol}-${index}`}>
              <td className="table-primary">{market.symbol ?? '—'}</td><td>{market.market ?? '—'}</td>
              <td>{price(num(market.price))}</td>
              <td className={(market.price_change_24h ?? 0) >= 0 ? 'positive' : 'negative'}>{pct(num(market.price_change_24h))}</td>
              <td>{compact(num(market.volume_24h))}</td>
              <td>{market.volatility_24h_pct == null ? '—' : `${market.volatility_24h_pct.toFixed(2)}%`}</td>
              <td>{market.atr_24h_pct == null ? '—' : `${market.atr_24h_pct.toFixed(2)}%`}</td>
              <td>{market.data_age_seconds == null ? '—' : `${Math.round(market.data_age_seconds)}s`}</td>
              <td>{market.data_freshness ?? 'UNKNOWN'}</td>
              <td><button className="table-action" disabled={!market.symbol} onClick={() => onSelectMarket(market.symbol ?? '', market.market === 'FUTURES' ? 'FUTURES' : 'SPOT')}>Analyze</button></td>
            </tr>
          ))}
        </Table>
      ) : <EmptyState text="Market ticker snapshots are unavailable. Start the local backend and scanner to populate eligible assets." />}
    </>
  )
}

function SignalsScreen({ signals, onSelectMarket }: Pick<Props, 'onSelectMarket'> & { signals: WorkspaceSignal[] }) {
  const [filter, setFilter] = useState('ALL')
  const [selectedSignal, setSelectedSignal] = useState<WorkspaceSignal | null>(null)
  const filtered = signals.filter((signal) => filter === 'ALL' || signal.status === filter)
  return (
    <>
      <ScreenHeader title="AI Signals" description="Recorded strategy decisions · confidence is a model score, not a calibrated probability" actions={<select className="workspace-select" aria-label="Filter signals by status" value={filter} onChange={(event) => setFilter(event.target.value)}><option>ALL</option><option>PROPOSED</option><option>VALIDATED</option><option>REJECTED</option><option>EXPIRED</option></select>} />
      {filtered.length ? <Table minWidth={1200}>
        <TableHead labels={['ASSET', 'MARKET', 'DIRECTION', 'ENTRY REF', 'STOP', 'TARGETS', 'R/R', 'STRATEGY', 'TF', 'CONFIDENCE SCORE', 'STATUS / FRESHNESS', 'TIMESTAMP', 'VALIDITY', 'ACTION']} />
        {filtered.map((signal, index) => {
          const invalidation = signal.data_freshness === 'STALE' ? 'STALE · REVIEW' : signal.status === 'EXPIRED' ? 'EXPIRED' : 'No expiry supplied'
          return <tr key={signal.signal_id ?? `${signal.symbol}-${index}`}>
            <td className="table-primary">{signal.symbol ?? '—'}</td>
            <td>{signal.market ?? '—'}</td><td>{signal.direction ?? '—'}</td><td>{price(num(signal.entry))}</td><td>{price(num(signal.stop_loss))}</td>
            <td>{signal.take_profit?.length ? signal.take_profit.map(price).join(' / ') : '—'}</td><td>{rr(signal)}</td>
            <td>{signal.strategy ?? '—'}</td><td>{signal.timeframe ?? '—'}</td><td>{signal.confidence == null ? '—' : signal.confidence.toFixed(3)}</td>
            <td>{signal.status ?? '—'} · {signal.data_freshness ?? 'UNKNOWN'}</td><td>{timestamp(signal.created_at)}</td><td>{invalidation}</td>
            <td><button className="table-action" onClick={() => setSelectedSignal(signal)}>Inspect</button></td>
          </tr>
        })}
      </Table> : <EmptyState text="No signal decisions are available in persisted local history." />}
      {selectedSignal && <SignalInspector signal={selectedSignal} onClose={() => setSelectedSignal(null)} onSelectMarket={onSelectMarket} />}
      <div className="workspace-note">Confidence values are displayed on the backend’s score scale; the application does not label them as probabilities. Expiration is reported only when the persisted event supplies an expired state. Freshness alone does not establish trade validity.</div>
    </>
  )
}

function AnalysisScreen({ symbol, marketType, candles, volumeAnalytics }: { symbol: string; marketType: string; candles: WorkspaceData['analysisCandles']; volumeAnalytics: WorkspaceData['volumeAnalytics'] }) {
  return (
    <>
      <ScreenHeader title="Market Analysis" description={`${symbol} · ${marketType} · technical readings computed from loaded Binance public candles across configured intervals`} />
      <div className="workspace-summary"><SummaryCard label="SYMBOL" value={symbol} /><SummaryCard label="MARKET" value={marketType} /><SummaryCard label="TIMEFRAMES" value="9" detail="1m → 1w" /><SummaryCard label="ANALYSIS" value="DESCRIPTIVE" detail="Not a forecast" /></div>
      <div className="workspace-summary">
        <SummaryCard label="ROLLING 24H QUOTE VOLUME" value={compact(num(volumeAnalytics?.total_volume))} />
        <SummaryCard label="7D AVG DAILY QUOTE VOL" value={compact(num(volumeAnalytics?.average_daily_quote_volume_7d))} />
        <SummaryCard label="VS 7D DAILY AVG" value={pct(num(volumeAnalytics?.volume_change_vs_7d_avg_pct))} detail={volumeAnalytics?.comparison_period ?? 'Insufficient completed daily candles'} />
        <SummaryCard label="TRADE-FLOW SAMPLE" value={String(volumeAnalytics?.flow_sample_size ?? 0)} detail={volumeAnalytics?.flow_sample_scope ?? 'Unavailable'} />
      </div>
      <Table minWidth={980}>
        <TableHead labels={['TIMEFRAME', 'CANDLES', 'LAST CLOSE', 'PERIOD CHANGE', 'RSI (14)', 'SMA (20)', 'CLOSE VS SMA20', 'LAST CANDLE UTC']} />
        {TIMEFRAMES.map((timeframe) => {
          const rows = candles[timeframe] ?? []
          const last = rows.at(-1)
          const first = rows[0]
          const change = first && last && first.close !== 0 ? ((last.close - first.close) / first.close) * 100 : undefined
          const sma = meanClose(rows, 20)
          const rsiValue = rsi(rows)
          return <tr key={timeframe}>
            <td className="table-primary">{timeframe}</td><td>{rows.length || '—'}</td><td>{price(last?.close)}</td>
            <td className={(change ?? 0) >= 0 ? 'positive' : 'negative'}>{pct(change)}</td><td>{rsiValue === undefined ? '—' : rsiValue.toFixed(1)}</td>
            <td>{price(sma)}</td><td>{last && sma !== undefined ? last.close >= sma ? 'Above' : 'Below' : '—'}</td>
            <td>{dateOfLastCandle(rows)}</td>
          </tr>
        })}
      </Table>
      <div className="workspace-note">RSI and SMA are calculated from the displayed candle history. A timeframe without enough candles or available data is shown as unavailable. Readings are descriptive, not a signal or forecast.</div>
    </>
  )
}

function PortfolioScreen({ portfolio, positions, trades, stats, onPositionAction }: { portfolio: WorkspacePortfolio | null; positions: WorkspacePosition[]; trades: WorkspaceTrade[]; stats: WorkspaceTradeStats | null; onPositionAction: Props['onPositionAction'] }) {
  const [accountView, setAccountView] = useState<'ALL' | 'SPOT' | 'FUTURES'>('ALL')
  const [selectedPosition, setSelectedPosition] = useState<WorkspacePosition | null>(null)
  const visiblePositions = positions.filter((position) => accountView === 'ALL' || position.market === accountView)
  const visibleTrades = trades.filter((trade) => accountView === 'ALL' || trade.market === accountView)
  const selectedEquity = accountView === 'SPOT'
    ? portfolio?.spot_balance
    : accountView === 'FUTURES'
      ? portfolio?.futures_balance
      : portfolio?.total_balance
  return (
    <>
      <ScreenHeader title="Portfolio" description="Independent local Spot and USDⓈ-M Futures paper accounts · $500 USDT initial equity each" actions={(
        <div className="account-switch" role="group" aria-label="Portfolio account view">
          {(['ALL', 'SPOT', 'FUTURES'] as const).map((account) => (
            <button key={account} aria-pressed={accountView === account} className={accountView === account ? 'selected' : ''} onClick={() => setAccountView(account)}>
              {account === 'ALL' ? 'Combined' : account}
            </button>
          ))}
        </div>
      )} />
      <div className="workspace-summary portfolio-summary">
        <SummaryCard label="SELECTED VIEW EQUITY" value={money(num(selectedEquity))} detail={accountView === 'ALL' ? 'Spot + Futures' : `${accountView} paper account`} />
        <SummaryCard label="COMBINED EQUITY" value={money(num(portfolio?.total_balance))} detail={`Return ${pct(num(portfolio?.total_return_pct))}`} />
        <SummaryCard label="SPOT EQUITY" value={money(num(portfolio?.spot_balance))} detail={`P&L ${money(num(portfolio?.spot_pnl))}`} />
        <SummaryCard label="FUTURES EQUITY" value={money(num(portfolio?.futures_balance))} detail={`P&L ${money(num(portfolio?.futures_pnl))}`} />
        <SummaryCard label="REALIZED / UNREALIZED" value={`${money(num(portfolio?.realized_pnl))} / ${money(num(portfolio?.unrealized_pnl))}`} />
        <SummaryCard label="DAILY / MONTHLY REALIZED" value={`${money(num(portfolio?.daily_pnl))} / ${money(num(portfolio?.monthly_pnl))}`} />
        <SummaryCard label="MAX DRAWDOWN" value={pct(num(portfolio?.drawdown_pct))} />
      </div>
      <h2 className="workspace-section-title">Open positions · {visiblePositions.length}</h2>
      {visiblePositions.length ? <Table minWidth={1100}>
        <TableHead labels={['ASSET', 'ACCOUNT', 'SIDE', 'ENTRY', 'MARK', 'SIZE', 'LEVERAGE', 'UNREALIZED P&L', 'STOP', 'TARGET', 'LIQUIDATION', 'ACTION']} />
        {visiblePositions.map((position, index) => <tr key={position.position_id ?? index}>
          <td className="table-primary">{position.symbol ?? '—'}</td><td>{position.market ?? '—'}</td><td>{position.side ?? '—'}</td>
          <td>{price(num(position.entry_price))}</td><td>{price(num(position.current_price))}</td><td>{num(position.amount)?.toPrecision(5) ?? '—'}</td>
          <td>{position.leverage ?? '—'}x</td><td className={(position.unrealized_pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(position.unrealized_pnl))}</td>
          <td>{price(num(position.stop_loss ?? undefined))}</td><td>{price(num(position.take_profit ?? undefined))}</td><td>{price(num(position.liquidation_price ?? undefined))}</td>
          <td><button className="table-action" onClick={() => setSelectedPosition(position)}>Inspect</button></td>
        </tr>)}
      </Table> : <EmptyState text={`No open simulated ${accountView === 'ALL' ? '' : `${accountView} `}positions.`} />}
      {selectedPosition && <PositionInspector position={selectedPosition} onClose={() => setSelectedPosition(null)} onPositionAction={onPositionAction} />}
      <div className="workspace-note">Balances and trade activity are simulated only. No Binance order endpoints or live execution are used.</div>
      <h2 className="workspace-section-title">Recent completed trades · {visibleTrades.length} shown / {stats?.total ?? trades.length} total</h2>
      {visibleTrades.length ? <Table minWidth={900}>
        <TableHead labels={['ASSET', 'ACCOUNT', 'SIDE', 'ENTRY', 'EXIT', 'NET P&L', 'FEES', 'STRATEGY', 'CLOSED']} />
        {visibleTrades.slice(0, 8).map((trade, index) => <tr key={trade.position_id ?? index}>
          <td className="table-primary">{trade.symbol ?? '—'}</td><td>{trade.market ?? '—'}</td><td>{trade.side ?? '—'}</td>
          <td>{price(num(trade.entry_price))}</td><td>{price(num(trade.exit_price))}</td>
          <td className={(trade.pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(trade.pnl))}</td><td>{money(num(trade.fee))}</td><td>{trade.strategy ?? '—'}</td><td>{timestamp(trade.closed_at)}</td>
        </tr>)}
      </Table> : <EmptyState text="No completed simulated trades recorded." />}
    </>
  )
}

function PositionsScreen({ positions, openOrders, onPositionAction, onManualTrade, onCancelOrder }: { positions: WorkspacePosition[]; openOrders: WorkspaceOrder[]; onPositionAction: Props['onPositionAction']; onManualTrade: Props['onManualTrade']; onCancelOrder: Props['onCancelOrder'] }) {
  const [selectedPosition, setSelectedPosition] = useState<WorkspacePosition | null>(null)
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [market, setMarket] = useState<'SPOT' | 'FUTURES'>('SPOT')
  const [side, setSide] = useState<'BUY' | 'SELL' | 'LONG' | 'SHORT'>('BUY')
  const [orderType, setOrderType] = useState<'MARKET' | 'LIMIT'>('MARKET')
  const [quantity, setQuantity] = useState('')
  const [entryPrice, setEntryPrice] = useState('')
  const [stopLoss, setStopLoss] = useState('')
  const [takeProfit, setTakeProfit] = useState('')
  const [leverage, setLeverage] = useState('1')
  const [tradeBusy, setTradeBusy] = useState(false)
  const [tradeMessage, setTradeMessage] = useState('')
  return (
    <div className="positions-screen">
      <ScreenHeader title="Positions" description="Open simulated exposure across separate Spot and Futures paper accounts" />
      <section className="workspace-inspector positions-trade-panel" aria-label="Manual paper trade">
        <div className="workspace-inspector-heading"><strong>MANUAL PAPER TRADE</strong><span>Simulator only · risk checks enforced</span></div>
        <form className="workspace-inspector-actions" onSubmit={async (event) => {
          event.preventDefault(); setTradeBusy(true); setTradeMessage('')
          try {
            await onManualTrade({
              symbol: symbol.trim().toUpperCase(), market, side, order_type: orderType,
              quantity: Number(quantity), ...(orderType === 'LIMIT' ? { price: Number(entryPrice) } : {}),
              stop_loss: Number(stopLoss), ...(takeProfit ? { take_profit: Number(takeProfit) } : {}),
              leverage: Number(leverage),
            })
            setTradeMessage('Paper order accepted. Refreshing positions.')
          } catch (error) { setTradeMessage(error instanceof Error ? error.message : 'Order rejected.') }
          finally { setTradeBusy(false) }
        }}>
          <label>Symbol <input className="workspace-search" value={symbol} onChange={(event) => setSymbol(event.target.value)} required maxLength={30} /></label>
          <label>Market <select className="workspace-select" value={market} onChange={(event) => { const next = event.target.value as typeof market; setMarket(next); setSide(next === 'SPOT' ? 'BUY' : 'LONG') }}><option value="SPOT">Spot</option><option value="FUTURES">Futures</option></select></label>
          <label>Side <select className="workspace-select" value={side} onChange={(event) => setSide(event.target.value as typeof side)}>{(market === 'SPOT' ? ['BUY'] : ['LONG', 'SHORT']).map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Order <select className="workspace-select" value={orderType} onChange={(event) => setOrderType(event.target.value as typeof orderType)}><option value="MARKET">Market</option><option value="LIMIT">Limit</option></select></label>
          <label>Quantity <input className="workspace-search" type="number" min="0" step="any" value={quantity} onChange={(event) => setQuantity(event.target.value)} required /></label>
          {orderType === 'LIMIT' && <label>Limit price <input className="workspace-search" type="number" min="0" step="any" value={entryPrice} onChange={(event) => setEntryPrice(event.target.value)} required /></label>}
          <label>Stop loss <input className="workspace-search" type="number" min="0" step="any" value={stopLoss} onChange={(event) => setStopLoss(event.target.value)} required /></label>
          <label>Take profit <input className="workspace-search" type="number" min="0" step="any" value={takeProfit} onChange={(event) => setTakeProfit(event.target.value)} /></label>
          <label>Leverage <input className="workspace-search" type="number" min="1" max="125" step="1" value={leverage} onChange={(event) => setLeverage(event.target.value)} required /></label>
          <button className="table-action" type="submit" disabled={tradeBusy || !quantity || !stopLoss || (orderType === 'LIMIT' && !entryPrice)}>{tradeBusy ? 'Submitting…' : 'Place paper order'}</button>
          {tradeMessage && <span role="status">{tradeMessage}</span>}
        </form>
      </section>
      <section className="workspace-inspector positions-orders-panel" aria-label="Open limit orders">
        <div className="workspace-inspector-heading"><strong>OPEN LIMIT ORDERS</strong><span>{openOrders.length} pending</span></div>
        {openOrders.length ? <div className="positions-table-wrap"><Table minWidth={720}>
          <TableHead labels={['ORDER ID', 'ASSET', 'MARKET', 'SIDE', 'LIMIT PRICE', 'QUANTITY', 'STATUS', 'ACTION']} />
          {openOrders.map((order) => <tr key={order.order_id}>
            <td>{order.order_id ?? '—'}</td><td className="table-primary">{order.symbol ?? '—'}</td><td>{order.market ?? '—'}</td><td>{order.side ?? '—'}</td><td>{price(num(order.entry_price))}</td><td>{num(order.amount)?.toPrecision(6) ?? '—'}</td><td>{order.status ?? '—'}</td>
            <td><button className="table-action" disabled={!order.order_id || order.status !== 'OPEN'} onClick={async () => {
              if (!order.order_id || !window.confirm(`Cancel paper limit order ${order.order_id}?`)) return
              try { await onCancelOrder(order.order_id) } catch (error) { window.alert(error instanceof Error ? error.message : 'Cancellation failed.') }
            }}>Cancel order</button></td>
          </tr>)}
        </Table></div> : <EmptyState text="No open paper limit orders." />}
      </section>
      <div className="workspace-summary positions-summary"><SummaryCard label="OPEN POSITIONS" value={String(positions.length)} /><SummaryCard label="SPOT" value={String(positions.filter((position) => position.market === 'SPOT').length)} /><SummaryCard label="FUTURES" value={String(positions.filter((position) => position.market === 'FUTURES').length)} /><SummaryCard label="UNREALIZED P&L" value={money(positions.reduce((total, position) => total + (position.unrealized_pnl ?? 0), 0))} /></div>
      {positions.length ? <div className="positions-table-wrap positions-open-table"><Table minWidth={1200}>
        <TableHead labels={['POSITION', 'ASSET', 'ACCOUNT', 'SIDE', 'ENTRY PRICE', 'CURRENT PRICE', 'AMOUNT', 'LEVERAGE', 'UNREALIZED P&L', 'STOP LOSS', 'TAKE PROFIT', 'LIQ. PRICE', 'MARGIN RATIO', 'OPENED', 'ACTION']} />
        {positions.map((position, index) => <tr key={position.position_id ?? index}>
          <td>{position.position_id ?? '—'}</td><td className="table-primary">{position.symbol ?? '—'}</td><td>{position.market ?? '—'}</td><td>{position.side ?? '—'}</td>
          <td>{price(num(position.entry_price))}</td><td>{price(num(position.current_price))}</td><td>{num(position.amount)?.toPrecision(6) ?? '—'}</td><td>{position.leverage ?? '—'}x</td>
          <td className={(position.unrealized_pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(position.unrealized_pnl))}</td>
          <td>{price(num(position.stop_loss ?? undefined))}</td><td>{price(num(position.take_profit ?? undefined))}</td><td>{price(num(position.liquidation_price ?? undefined))}</td>
          <td>{position.margin_ratio == null ? '—' : `${(position.margin_ratio * 100).toFixed(2)}%`}</td><td>{timestamp(position.opened_at)}</td>
          <td><button className="table-action" onClick={() => setSelectedPosition(position)}>Inspect</button></td>
        </tr>)}
      </Table></div> : <div className="positions-empty"><EmptyState text="No open positions in the paper simulator." /></div>}
      {selectedPosition && <PositionInspector position={selectedPosition} onClose={() => setSelectedPosition(null)} onPositionAction={onPositionAction} />}
    </div>
  )
}

function TradeHistoryScreen({ trades, stats }: { trades: WorkspaceTrade[]; stats: WorkspaceTradeStats | null }) {
  const [query, setQuery] = useState('')
  const [accountFilter, setAccountFilter] = useState<'ALL' | 'SPOT' | 'FUTURES'>('ALL')
  const [outcomeFilter, setOutcomeFilter] = useState<'ALL' | 'WIN' | 'LOSS'>('ALL')
  const [period, setPeriod] = useState<'ALL' | '24H' | '7D' | '30D' | '90D'>('ALL')
  const [periodEnd, setPeriodEnd] = useState(0)
  const filteredTrades = useMemo(() => {
    const periodMs: Record<typeof period, number | undefined> = {
      ALL: undefined,
      '24H': 24 * 60 * 60 * 1000,
      '7D': 7 * 24 * 60 * 60 * 1000,
      '30D': 30 * 24 * 60 * 60 * 1000,
      '90D': 90 * 24 * 60 * 60 * 1000,
    }
    const duration = periodMs[period]
    const start = duration === undefined || periodEnd === 0 ? undefined : periodEnd - duration
    const needle = query.trim().toUpperCase()
    return trades.filter((trade) => {
      if (accountFilter !== 'ALL' && trade.market !== accountFilter) return false
      if (needle && !trade.symbol?.toUpperCase().includes(needle)) return false
      if (outcomeFilter === 'WIN' && (trade.pnl ?? 0) <= 0) return false
      if (outcomeFilter === 'LOSS' && (trade.pnl ?? 0) >= 0) return false
      if (start !== undefined) {
        const closedAt = Date.parse(trade.closed_at ?? '')
        if (!Number.isFinite(closedAt) || closedAt < start) return false
      }
      return true
    })
  }, [accountFilter, outcomeFilter, period, periodEnd, query, trades])
  const filteredPnl = filteredTrades.reduce((total, trade) => total + (trade.pnl ?? 0), 0)
  const filteredWins = filteredTrades.filter((trade) => (trade.pnl ?? 0) > 0)
  const filteredLosses = filteredTrades.filter((trade) => (trade.pnl ?? 0) < 0)
  const grossWins = filteredWins.reduce((total, trade) => total + (trade.pnl ?? 0), 0)
  const grossLosses = Math.abs(filteredLosses.reduce((total, trade) => total + (trade.pnl ?? 0), 0))
  const filteredProfitFactor = grossLosses ? grossWins / grossLosses : grossWins ? Infinity : undefined
  return (
    <>
      <ScreenHeader title="Trade History" description="Filter persisted closed paper trades by account, outcome, asset, and close time" actions={(
        <>
          <input className="workspace-search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Filter symbol" aria-label="Filter trade history by symbol" />
          <select className="workspace-select" aria-label="Filter trades by account" value={accountFilter} onChange={(event) => setAccountFilter(event.target.value as typeof accountFilter)}>
            <option value="ALL">All accounts</option><option value="SPOT">Spot</option><option value="FUTURES">Futures</option>
          </select>
          <select className="workspace-select" aria-label="Filter trades by outcome" value={outcomeFilter} onChange={(event) => setOutcomeFilter(event.target.value as typeof outcomeFilter)}>
            <option value="ALL">All outcomes</option><option value="WIN">Profitable</option><option value="LOSS">Losing</option>
          </select>
          <select className="workspace-select" aria-label="Filter trade analytics by close time" value={period} onChange={(event) => {
            setPeriod(event.target.value as typeof period)
            setPeriodEnd(Date.now())
          }}>
            <option value="ALL">All time</option><option value="24H">24 hours</option><option value="7D">7 days</option><option value="30D">30 days</option><option value="90D">90 days</option>
          </select>
        </>
      )} />
      <div className="workspace-summary">
        <SummaryCard label="MATCHED TRADES" value={String(filteredTrades.length)} detail="Loaded persisted trades" />
        <SummaryCard label="MATCHED NET P&L" value={money(filteredPnl)} />
        <SummaryCard label="MATCHED WIN RATE" value={filteredTrades.length ? `${(filteredWins.length / filteredTrades.length * 100).toFixed(1)}%` : '—'} />
        <SummaryCard label="MATCHED PROFIT FACTOR" value={filteredProfitFactor === undefined ? '—' : filteredProfitFactor === Infinity ? '∞' : filteredProfitFactor.toFixed(2)} />
        <SummaryCard label="FULL-HISTORY MAX DRAWDOWN" value={pct(num(stats?.max_drawdown_pct))} detail="Backend-reported" />
      </div>
      {filteredTrades.length ? <Table minWidth={1450}>
        <TableHead labels={['POSITION ID', 'ASSET', 'ACCOUNT', 'SIDE', 'ENTRY', 'EXIT', 'AMOUNT', 'LEVERAGE', 'NET P&L', 'P&L %', 'FEES', 'MFE %', 'MAE %', 'PREDICTION', 'CALC AUDIT', 'STRATEGY', 'EXIT REASON', 'OPENED', 'CLOSED']} />
        {filteredTrades.map((trade, index) => <tr key={trade.position_id ?? index}>
          <td>{trade.position_id ?? '—'}</td><td className="table-primary">{trade.symbol ?? '—'}</td><td>{trade.market ?? '—'}</td><td>{trade.side ?? '—'}</td>
          <td>{price(num(trade.entry_price))}</td><td>{price(num(trade.exit_price))}</td><td>{num(trade.amount)?.toPrecision(6) ?? '—'}</td><td>{trade.leverage ?? '—'}x</td>
          <td className={(trade.pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(trade.pnl))}</td><td>{pct(num(trade.pnl_pct))}</td><td>{money(num(trade.fee))}</td>
          <td>{pct(num(trade.max_favorable_excursion_pct))}</td><td>{pct(num(trade.max_adverse_excursion_pct))}</td><td>{trade.prediction_correct == null ? 'Unavailable' : trade.prediction_correct ? 'Correct' : 'Incorrect'}</td><td>{trade.risk_calculation_verified == null ? 'Not audited' : trade.risk_calculation_verified ? 'Verified' : 'Discrepancy'}</td>
          <td>{trade.strategy ?? '—'}</td><td>{trade.close_reason ?? '—'}</td><td>{timestamp(trade.opened_at)}</td><td>{timestamp(trade.closed_at)}</td>
        </tr>)}
      </Table> : <EmptyState text="No persisted closed trades are available." />}
      <div className="workspace-note">Performance metrics are based on recorded paper trades only; no historical performance is estimated or fabricated.</div>
    </>
  )
}

function IntelligenceScreen({ data, loadState }: { data: WorkspaceData; loadState: 'loading' | 'ready' | 'error' }) {
  const regimes = useMemo(() => {
    const counts = new Map<string, number>()
    for (const market of data.markets) {
      const regime = market.regime ?? 'UNKNOWN'
      counts.set(regime, (counts.get(regime) ?? 0) + 1)
    }
    return [...counts].sort((a, b) => b[1] - a[1])
  }, [data.markets])
  return (
    <div className="intelligence-screen">
      <ScreenHeader title="Intelligence" description="Observed market regimes and persisted strategy evaluation; decision rationale is shown only when recorded" />
      {loadState === 'error' && <p role="alert" className="intelligence-load-note">Intelligence could not be loaded from the backend. Retry after the backend connection is restored.</p>}
      {loadState === 'loading' && <p role="status" className="intelligence-load-note">Loading rule-based market evidence from the backend…</p>}

      <section className="intelligence-analysis-deck" aria-label="Current evidence analysis">
        {data.intelligenceAnalysis && data.intelligenceAnalysis.status !== 'UNAVAILABLE' ? <>
          <div className="intelligence-deck-heading">
            <span>01 / CURRENT EVIDENCE</span>
            <strong>Market classification</strong>
          </div>
          <div className="workspace-summary intelligence-summary">
            <SummaryCard label="ANALYSIS STATUS" value={String(data.intelligenceAnalysis.status ?? 'UNKNOWN')} />
            <SummaryCard label="REGIME" value={String(data.intelligenceAnalysis.regime?.regime ?? 'UNKNOWN')} detail={String(data.intelligenceAnalysis.regime?.method ?? 'Rule-based classification')} />
            <SummaryCard label="DATA FRESHNESS" value={String(data.intelligenceAnalysis.observed?.data_freshness ?? 'UNKNOWN')} detail={data.intelligenceAnalysis.observed?.data_age_seconds == null ? 'Age unavailable' : `${Number(data.intelligenceAnalysis.observed.data_age_seconds).toFixed(0)} seconds old`} />
            <SummaryCard label="OBSERVED PRICE" value={data.intelligenceAnalysis.observed?.price == null ? '—' : price(num(data.intelligenceAnalysis.observed.price))} detail="Exchange snapshot" />
          </div>
          {Array.isArray(data.intelligenceAnalysis.supporting_evidence) && data.intelligenceAnalysis.supporting_evidence.length > 0
            ? <div className="intelligence-evidence-note"><span>Evidence</span><p>{data.intelligenceAnalysis.supporting_evidence.join(' ')}</p></div>
            : <div className="intelligence-evidence-note"><span>Evidence</span><p>The classifier returned no supporting evidence for this analysis.</p></div>}
          {Array.isArray(data.intelligenceAnalysis.risk_factors) && data.intelligenceAnalysis.risk_factors.length > 0
            ? <div className="intelligence-evidence-note intelligence-limitation"><span>Limitations</span><p>{data.intelligenceAnalysis.risk_factors.join(' ')}</p></div> : null}
        </> : <div className="intelligence-empty-analysis">
          <span>01 / CURRENT EVIDENCE</span>
          <strong>Market classification unavailable</strong>
          <p>{data.intelligenceAnalysis ? String((data.intelligenceAnalysis.risk_factors as string[] | undefined)?.[0] ?? 'No market snapshot is available for this symbol.') : loadState === 'error' ? 'The evidence analysis request failed.' : 'Evidence analysis will appear when backend data is available.'}</p>
        </div>}
      </section>

      <div className="intelligence-grid">
        <section className="intelligence-panel intelligence-regimes">
          <header><span>02 / OBSERVED</span><strong>Market regimes</strong><small>{regimes.length} ACTIVE</small></header>
          {regimes.length ? <div className="intelligence-regime-list">
            {regimes.map(([regime, count]) => <div key={regime}><span>{regime}</span><strong>{count}</strong><small>ticker snapshots</small></div>)}
          </div> : <EmptyState text="Market regime snapshots unavailable." />}
        </section>

        <section className="intelligence-panel intelligence-weights">
          <header><span>03 / ADAPTATION</span><strong>Strategy weights</strong><small>{Object.keys(data.strategyWeights).length} MODELS</small></header>
          {Object.keys(data.strategyWeights).length ? <div className="intelligence-weight-list">{Object.entries(data.strategyWeights).map(([strategy, raw]) => {
            const weight = raw && typeof raw === 'object' ? raw as { base_weight?: number; regime_adjusted?: number } : {}
            return <div key={strategy}><span>{strategy.toUpperCase()}</span><strong>{weight.regime_adjusted == null ? '—' : Number(weight.regime_adjusted).toFixed(3)}</strong><small>{weight.base_weight == null ? 'No base weight reported' : `Base ${Number(weight.base_weight).toFixed(3)}`}</small></div>
          })}</div> : <EmptyState text="No strategy weights are available from the intelligence service." />}
        </section>

        <section className="intelligence-panel intelligence-strategies">
          <header><span>04 / PERFORMANCE</span><strong>Strategy evaluations</strong><small>{data.strategies.length} RECORDS</small></header>
          {data.strategies.length ? <div className="intelligence-table-wrap"><Table minWidth={850}>
            <TableHead labels={['STRATEGY', 'MARKET', 'SIGNALS', 'VALIDATED', 'WINS', 'LOSSES', 'WIN RATE', 'NET P&L', 'PROFIT FACTOR', 'WEIGHT']} />
            {data.strategies.map((strategy, index) => <tr key={`${strategy.market}-${strategy.strategy}-${index}`}>
              <td className="table-primary">{strategy.strategy ?? '—'}</td><td>{strategy.market ?? '—'}</td><td>{strategy.total_signals ?? '—'}</td><td>{strategy.validated_signals ?? '—'}</td>
              <td>{strategy.winning_trades ?? '—'}</td><td>{strategy.losing_trades ?? '—'}</td><td>{strategy.win_rate == null ? '—' : `${strategy.win_rate.toFixed(1)}%`}</td>
              <td className={(strategy.total_pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(strategy.total_pnl))}</td><td>{strategy.profit_factor == null ? '—' : strategy.profit_factor.toFixed(2)}</td><td>{strategy.weight == null ? '—' : strategy.weight.toFixed(3)}</td>
            </tr>)}
          </Table></div> : <EmptyState text="No persisted strategy performance metrics are available." />}
        </section>

        <section className="intelligence-panel intelligence-decisions">
          <header><span>05 / AUDIT TRAIL</span><strong>Recent decision records</strong><small>{Math.min(data.signals.length, 50)} OF {data.signals.length}</small></header>
          {data.signals.length ? <div className="intelligence-table-wrap"><Table minWidth={760}>
            <TableHead labels={['TIMESTAMP', 'ASSET', 'MARKET', 'STRATEGY', 'DECISION', 'REGIME', 'RECORDED REASONS']} />
            {data.signals.slice(0, 50).map((signal, index) => <tr key={signal.signal_id ?? index}>
              <td>{timestamp(signal.created_at)}</td><td className="table-primary">{signal.symbol ?? '—'}</td><td>{signal.market ?? '—'}</td><td>{signal.strategy ?? '—'}</td>
              <td>{signal.direction ?? '—'} · {signal.status ?? '—'}</td><td>{signal.regime ?? '—'}</td><td>{signal.reasons?.length ? signal.reasons.join('; ') : 'No rationale recorded'}</td>
            </tr>)}
          </Table></div> : <EmptyState text="No signal decision records are available." />}
        </section>
      </div>
    </div>
  )
}

function metricPercent(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '—' : `${value.toFixed(2)}%`
}
function metricNumber(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '—' : value.toFixed(2)
}
function LearningScreen({ data }: { data: WorkspaceData }) {
  const promotions = data.events.filter((event) => ['MODEL_PROMOTED', 'MODEL_ROLLED_BACK', 'MODEL_TRAINED'].includes(event.event_type ?? ''))
  const learning = data.learning
  const gate = learning?.last_training_result?.validation?.promotion_gate
  const failureReasons = gate?.failure_reasons ?? learning?.last_training_result?.batch_validation?.promotion_gate?.failure_reasons ?? []
  const holdout = learning?.last_training_result?.holdout_report
  const validation = learning?.last_training_result?.validation
  const predictionRate = learning?.predictions_total
    ? Math.round(((learning.predictions_resolved ?? 0) / learning.predictions_total) * 100)
    : null
  const activeModel = learning?.model_status === 'Trained'
  return (
    <div className="learning-screen">
      <ScreenHeader title="Learning" description="Model lifecycle, validation evidence, prediction outcomes, and promotion history" />
      <div className="learning-status-bar" aria-label="Model lifecycle summary">
        <div className="learning-status-main">
          <span className="learning-eyebrow">LOCAL LEARNING SYSTEM</span>
          <strong className={activeModel ? '' : 'learning-status-warn'}>{learning?.model_status ?? 'Unavailable'}</strong>
          <small>{learning?.last_cycle_status ?? 'No learning cycle reported'}</small>
        </div>
        <div><span>ACTIVE VERSION</span><strong>{learning?.version ?? '—'}</strong></div>
        <div><span>TRAINING STATE</span><strong>{learning?.training_state ?? '—'}</strong></div>
        <div><span>LAST TRAINED</span><strong>{learning?.last_training_at ? timestamp(learning.last_training_at) : '—'}</strong></div>
        <div className="learning-model-flags">
          <span>AVAILABLE MODELS</span>
          <strong>RF {learning?.rf_loaded ? 'READY' : '—'} / XGB {learning?.xgb_loaded ? 'READY' : '—'} / RIVER {learning?.river_available ? 'READY' : '—'}</strong>
        </div>
      </div>
      <div className="learning-cycle" aria-label="Learning lifecycle">
        <div><span>01</span><strong>COLLECT</strong><small>{learning?.training_samples ?? '—'} historical samples</small></div>
        <i aria-hidden="true">→</i>
        <div><span>02</span><strong>VALIDATE</strong><small>{learning?.last_training_result?.status ?? 'No candidate report'}</small></div>
        <i aria-hidden="true">→</i>
        <div><span>03</span><strong>PROMOTE</strong><small>{failureReasons.length ? 'Gate blocked' : activeModel ? 'Active model' : 'Not promoted'}</small></div>
        <i aria-hidden="true">→</i>
        <div><span>04</span><strong>RESOLVE</strong><small>{learning?.predictions_resolved ?? '—'} outcomes measured</small></div>
      </div>
      {!activeModel && <div className="learning-caution" role="note">
        <strong>NO VALIDATED MODEL ACTIVE</strong>
        <span>FLAT predictions with confidence 0.000 are the explicit untrained fallback, not learned or calibrated confidence. Resolved-prediction accuracy is historical outcome measurement, separate from holdout validation.</span>
      </div>}
      {learning?.last_training_result?.reason && <div className="learning-message" role="status"><span>LATEST TRAINING RESULT</span>{learning.last_training_result.reason}</div>}
      {failureReasons.length > 0 && <div className="learning-message learning-message-alert" role="status"><span>PROMOTION GATE</span>{failureReasons.join('; ')}</div>}
      <section className="learning-outcome-strip" aria-label="Learning activity summary">
        <div><span>BOOTSTRAP SAMPLES</span><strong>{learning?.training_samples ?? '—'}</strong><small>Historical labeled hourly candles</small></div>
        <div><span>ONLINE UPDATES</span><strong>{learning?.river_updates ?? '—'}</strong><small>Incremental learner updates</small></div>
        <div><span>PREDICTIONS</span><strong>{learning?.predictions_total ?? '—'}</strong><small>Recorded by the local system</small></div>
        <div><span>OUTCOMES RESOLVED</span><strong>{learning?.predictions_resolved ?? '—'}</strong><small>{predictionRate == null ? 'Resolution coverage unavailable' : `${predictionRate}% of recorded predictions`}</small></div>
        <div><span>RESOLVED ACCURACY</span><strong>{learning?.accuracy == null ? '—' : `${learning.accuracy.toFixed(2)}%`}</strong><small>Resolved outcomes only</small></div>
      </section>
      <details className="learning-section learning-promotion-evidence">
        <summary><span><small>01 / VALIDATION</small><strong>Promotion evidence</strong></span><span>{holdout || gate ? 'REPORT AVAILABLE' : 'NO REPORT'}</span></summary>
        <div className="learning-section-content">
          {holdout ? <div className="learning-evidence-block">
            <h3>Untouched holdout · River candidate</h3>
            <p>{holdout.validation_method ?? 'Holdout method unavailable'} · {holdout.holdout_samples ?? '—'} held-out samples from {holdout.train_samples ?? '—'} training samples · {holdout.holdout_untouched ? 'holdout labels were not used for model updates' : 'holdout was not untouched'}.</p>
            <div className="learning-evidence-grid">
              <div><span>ACCURACY / REQUIRED</span><strong>{holdout.accuracy == null ? '—' : `${(holdout.accuracy * 100).toFixed(2)}%`} / {holdout.thresholds?.accuracy_min == null ? '—' : `${(holdout.thresholds.accuracy_min * 100).toFixed(2)}%`}</strong></div>
              <div><span>MACRO F1 / REQUIRED</span><strong>{holdout.f1_macro == null ? '—' : `${(holdout.f1_macro * 100).toFixed(2)}%`} / {holdout.thresholds?.f1_macro_min == null ? '—' : `${(holdout.thresholds.f1_macro_min * 100).toFixed(2)}%`}</strong></div>
              <div><span>MACRO PRECISION</span><strong>{holdout.precision_macro == null ? '—' : `${(holdout.precision_macro * 100).toFixed(2)}%`}</strong></div>
              <div><span>MACRO RECALL</span><strong>{holdout.recall_macro == null ? '—' : `${(holdout.recall_macro * 100).toFixed(2)}%`}</strong></div>
            </div>
            <p>Training ends {holdout.train_end_timestamp ? new Date(holdout.train_end_timestamp).toLocaleString() : '—'}; holdout {holdout.holdout_start_timestamp ? new Date(holdout.holdout_start_timestamp).toLocaleString() : '—'} through {holdout.holdout_end_timestamp ? new Date(holdout.holdout_end_timestamp).toLocaleString() : '—'}.</p>
            {holdout.failure_reasons?.length ? <p className="learning-failure-text">Failures: {holdout.failure_reasons.join('; ')}</p> : <p>All reported holdout thresholds passed.</p>}
          </div> : <EmptyState text="No untouched holdout report is available." />}
          {gate && validation && <div className="learning-evidence-block">
            <h3>Random Forest &amp; XGBoost · purged walk-forward</h3>
            <p>{validation.validation_provenance?.sample_count ?? '—'} chronologically ordered samples; {validation.validation_provenance?.method ?? 'validation method unavailable'}; out of sample: {validation.validation_provenance?.out_of_sample ? 'yes' : 'no'}; purge gap {validation.validation_provenance?.purge_gap_ms ?? '—'} ms. Fold results are separate from resolved-prediction accuracy.</p>
            <p>Requirements: mean accuracy ≥ {metricPercent((gate.criteria?.min_mean_accuracy ?? 0) * 100)}, macro F1 ≥ {metricPercent((gate.criteria?.min_mean_f1 ?? 0) * 100)}, calibration ≥ {metricNumber(gate.criteria?.min_calibration_score)}, net expectancy ≥ {gate.criteria?.min_net_expectancy?.toFixed(6) ?? '—'}, max drawdown ≤ {metricPercent(gate.criteria?.max_drawdown_pct)}.</p>
            <Table minWidth={900}>
              <TableHead labels={['MODEL', 'FOLD', 'TRAIN / TEST', 'ACCURACY', 'PRECISION', 'RECALL', 'MACRO F1', 'PROMOTION CHECKS']} />
              {(['rf', 'xgb'] as const).flatMap((model) => {
                const modelGate = gate.models?.[model]
                const criteria = gate.criteria
                const folds = validation.models?.[model]?.folds ?? []
                const economic = modelGate?.economic_evidence
                const summary = `Mean accuracy ${metricPercent(modelGate?.mean_accuracy == null ? null : modelGate.mean_accuracy * 100)} / ≥${metricPercent(criteria?.min_mean_accuracy == null ? null : criteria.min_mean_accuracy * 100)}; mean macro F1 ${metricPercent(modelGate?.mean_f1 == null ? null : modelGate.mean_f1 * 100)} / ≥${metricPercent(criteria?.min_mean_f1 == null ? null : criteria.min_mean_f1 * 100)}; calibration ${metricNumber(modelGate?.calibration_score)} / ≥${metricNumber(criteria?.min_calibration_score)}; expectancy ${economic?.net_expectancy?.toFixed(6) ?? '—'} / ≥${criteria?.min_net_expectancy?.toFixed(6) ?? '—'}; drawdown ${metricPercent(economic?.max_drawdown_pct)} / ≤${metricPercent(criteria?.max_drawdown_pct)}; ${modelGate?.failure_reasons?.join('; ') || (modelGate?.passes ? 'All promotion checks passed' : 'No promotion result')}`
                return folds.length ? folds.map((fold) => <tr key={`${model}-${fold.fold}`}>
                  <td className="table-primary">{model.toUpperCase()}</td><td>{fold.fold ?? '—'}</td><td>{fold.train_size ?? '—'} / {fold.test_size ?? '—'}</td>
                  <td>{metricPercent(fold.accuracy == null ? null : fold.accuracy * 100)}</td><td>{metricPercent(fold.precision_macro == null ? null : fold.precision_macro * 100)}</td>
                  <td>{metricPercent(fold.recall_macro == null ? null : fold.recall_macro * 100)}</td><td>{metricPercent(fold.f1_macro == null ? null : fold.f1_macro * 100)}</td><td>{summary}</td>
                </tr>) : [<tr key={`${model}-summary`}><td className="table-primary">{model.toUpperCase()}</td><td colSpan={6}>No fold detail reported; mean accuracy {metricPercent(modelGate?.mean_accuracy == null ? null : modelGate.mean_accuracy * 100)}, macro F1 {metricPercent(modelGate?.mean_f1 == null ? null : modelGate.mean_f1 * 100)}</td><td>{summary}</td></tr>]
              })}
            </Table>
            <p>Net expectancy / maximum drawdown — RF: {(() => { const e = gate.models?.rf?.economic_evidence; return e ? `${e.net_expectancy?.toFixed(6) ?? '—'} / ${e.max_drawdown_pct?.toFixed(2) ?? '—'}%` : 'unavailable' })()} · XGBoost: {(() => { const e = gate.models?.xgb?.economic_evidence; return e ? `${e.net_expectancy?.toFixed(6) ?? '—'} / ${e.max_drawdown_pct?.toFixed(2) ?? '—'}%` : 'unavailable' })()}. Promotion thresholds remain unchanged.</p>
          </div>}
        </div>
      </details>
      <details className="learning-section learning-observed-performance">
        <summary><span><small>02 / EVALUATION</small><strong>Observed performance</strong></span><span>{data.performance?.prediction_count ?? 0} PREDICTIONS · {data.performance?.trade_count ?? 0} TRADES</span></summary>
        <div className="learning-section-content">
          <div className="learning-metric-grid">
            <SummaryCard label="PREDICTION ACCURACY" value={metricPercent(data.performance?.accuracy_pct)} detail={`${data.performance?.prediction_count ?? 0} resolved predictions`} />
            <SummaryCard label="PRECISION · MACRO" value={metricPercent(data.performance?.precision_macro_pct)} detail="Average across observed classes" />
            <SummaryCard label="RECALL · MACRO" value={metricPercent(data.performance?.recall_macro_pct)} detail="Average across observed classes" />
            <SummaryCard label="PROFIT FACTOR" value={data.performance?.profit_factor === 'infinite' ? '∞' : metricNumber(data.performance?.profit_factor)} detail="Gross profit / gross loss" />
            <SummaryCard label="WIN RATE" value={metricPercent(data.performance?.win_rate_pct)} detail={`${data.performance?.trade_count ?? 0} closed paper trades`} />
            <SummaryCard label="MAX DRAWDOWN" value={metricPercent(data.performance?.max_drawdown_pct)} detail="Closed-trade equity sequence" />
            <SummaryCard label="SHARPE RATIO" value={metricNumber(data.performance?.sharpe_ratio)} detail="Daily realized P&L; annualized" />
            <SummaryCard label="TRADES EVALUATED" value={String(data.performance?.trade_count ?? 0)} detail="Closed paper trades only" />
          </div>
          <p>Classification metrics use resolved predictions; trading metrics use closed paper trades. Sharpe uses daily realized P&amp;L divided by initial paper equity, annualized with √365, and is unavailable with fewer than two daily observations. Missing metrics are shown as unavailable, not zero.</p>
        </div>
      </details>
      <details className="learning-section learning-strategy-comparison">
        <summary><span><small>03 / STRATEGY RESEARCH</small><strong>Walk-forward comparison</strong></span><span>{data.strategyComparison?.status === 'ok' ? `${data.strategyComparison.walk_forward_folds ?? 0} FOLDS` : 'NO EVALUATION'}</span></summary>
        <div className="learning-section-content">
          {data.strategyComparison?.status === 'ok' ? <>
            <div className="learning-metric-grid learning-comparison-meta">
              <SummaryCard label="ASSET / MARKET" value={`${data.strategyComparison.symbol ?? '—'} · ${data.strategyComparison.market ?? '—'}`} detail={`${data.strategyComparison.timeframe ?? '—'} · ${data.strategyComparison.candles ?? 0} candles`} />
              <SummaryCard label="WALK-FORWARD FOLDS" value={String(data.strategyComparison.walk_forward_folds ?? 0)} detail="Expanding historical windows" />
              <SummaryCard label="UNSEEN TEST WINDOW" value={`${timestamp(data.strategyComparison.evaluation_start_time)} → ${timestamp(data.strategyComparison.evaluation_end_time)}`} detail="Same period across strategies" />
            </div>
            <Table minWidth={950}>
              <TableHead labels={['STRATEGY', 'RETURN', 'MAX DRAWDOWN', 'SHARPE', 'WIN RATE', 'PROFIT FACTOR', 'TRADES', 'BARS']} />
              {data.strategyComparison.strategies.map((item) => <tr key={item.strategy}>
                <td className="table-primary">{item.strategy}</td>
                <td className={(item.total_return_pct ?? 0) >= 0 ? 'positive' : 'negative'}>{item.total_return_pct == null ? '—' : pct(item.total_return_pct)}</td>
                <td>{item.max_drawdown_pct == null ? '—' : pct(item.max_drawdown_pct)}</td>
                <td>{item.sharpe_ratio == null ? '—' : item.sharpe_ratio.toFixed(2)}</td>
                <td>{item.win_rate_pct == null ? '—' : pct(item.win_rate_pct)}</td>
                <td>{item.profit_factor === 'infinite' ? '∞' : item.profit_factor == null ? '—' : item.profit_factor.toFixed(2)}</td>
                <td>{item.trades_evaluated ?? '—'}</td><td>{item.evaluation_bars ?? '—'}</td>
              </tr>)}
            </Table>
            <p>{data.strategyComparison.training_policy}. Costs: {data.strategyComparison.cost_policy}. No slippage or futures funding is included. Model rows remain flat until a valid out-of-sample fold prediction is available.</p>
          </> : <EmptyState text={data.strategyComparison?.status === 'insufficient_data' ? 'Not enough closed historical candles to compare strategies.' : 'Strategy comparison will appear when historical candle data is available.'} />}
        </div>
      </details>
      <details className="learning-section learning-model-registry">
        <summary><span><small>04 / MODEL REGISTRY</small><strong>Candidate &amp; champion history</strong></span><span>{data.models.length} VERSIONS</span></summary>
        <div className="learning-section-content">
          {data.models.length ? <Table minWidth={900}>
            <TableHead labels={['VERSION', 'MODEL', 'STATUS', 'ACTIVE', 'CHAMPION', 'PARENT', 'TRAINED']} />
            {data.models.map((model, index) => <tr key={model.version ?? index}><td className="table-primary">{model.version ?? '—'}</td><td>{model.model_type ?? '—'}</td><td>{model.status ?? '—'}</td><td>{model.is_active ? 'YES' : 'NO'}</td><td>{model.is_champion ? 'YES' : 'NO'}</td><td>{model.parent_version ?? '—'}</td><td>{timestamp(model.trained_at)}</td></tr>)}
          </Table> : <EmptyState text="Model registry is empty or unavailable; no candidate or champion state is inferred." />}
        </div>
      </details>
      <details className="learning-section learning-prediction-outcomes">
        <summary><span><small>05 / FEEDBACK LOOP</small><strong>Prediction outcomes</strong></span><span>{data.predictions.length} RECORDS</span></summary>
        <div className="learning-section-content">
          {data.predictions.length ? <Table minWidth={950}>
            <TableHead labels={['CREATED', 'ASSET', 'MARKET', 'TIMEFRAME', 'HORIZON', 'MODEL', 'PREDICTION', 'CONFIDENCE SCORE', 'OUTCOME', 'RETURN', 'SIMULATED P&L', 'CORRECT']} />
            {data.predictions.map((prediction, index) => <tr key={prediction.prediction_id ?? index}>
              <td>{timestamp(prediction.created_at)}</td><td className="table-primary">{prediction.symbol ?? '—'}</td><td>{prediction.market ?? '—'}</td><td>{prediction.timeframe ?? '—'}</td><td>{prediction.horizon_minutes == null ? '—' : `${prediction.horizon_minutes}m`}</td>
              <td>{prediction.model_version ?? '—'}</td><td>{prediction.predicted_class ?? '—'}</td><td>{prediction.confidence == null ? '—' : prediction.confidence.toFixed(3)}</td>
              <td>{prediction.actual_outcome ?? 'Pending'}</td><td>{pct(num(prediction.actual_return_pct ?? undefined))}</td><td>{money(num(prediction.simulated_pnl ?? undefined))}</td><td>{prediction.is_correct == null ? 'Pending' : prediction.is_correct ? 'YES' : 'NO'}</td>
            </tr>)}
          </Table> : <EmptyState text="No prediction history is available." />}
          <p>Confidence is a score unless the associated model and calibration metadata establish otherwise. Predictions describe movement classes over a horizon, not exact future prices.</p>
        </div>
      </details>
      <details className="learning-section learning-model-control">
        <summary><span><small>06 / MODEL CONTROL</small><strong>Promotion &amp; rollback events</strong></span><span>{promotions.length} EVENTS</span></summary>
        <div className="learning-section-content">
          {promotions.length ? <Table minWidth={700}><TableHead labels={['TIMESTAMP', 'EVENT', 'MODEL / VERSION', 'DETAIL']} />{promotions.map((event, index) => <tr key={event.event_id ?? index}><td>{timestamp(event.timestamp)}</td><td>{event.event_type ?? '—'}</td><td>{String(event.payload?.version ?? event.payload?.model_version ?? '—')}</td><td>{String(event.payload?.reason ?? event.payload?.message ?? 'No additional detail recorded')}</td></tr>)}</Table> : <EmptyState text="No promotion or rollback events are recorded. Experiment registry data is not exposed by the current API." />}
        </div>
      </details>
      <p className="learning-footnote">Learning may update validated models and strategy weights. It cannot change source code or risk limits. Missing metrics remain unavailable rather than being inferred as zero.</p>
    </div>
  )
}

function RiskScreen({ risk, portfolio, alerts }: { risk: WorkspaceRisk | null; portfolio: WorkspacePortfolio | null; alerts: WorkspaceEvent[] }) {
  const limits = [
    ['Risk per trade', risk?.risk_per_trade_pct, '%'],
    ['Maximum daily loss', risk?.max_daily_loss_pct, '%'],
    ['Maximum aggregate open risk', risk?.max_total_open_pct, '%'],
    ['Maximum Futures leverage', risk?.max_leverage, 'x'],
    ['Maximum Spot positions', risk?.max_spot_positions, ''],
    ['Maximum Futures positions', risk?.max_futures_positions, ''],
  ] as const
  return (
    <>
      <ScreenHeader title="Risk Management" description="Current risk manager metrics, hard limits, drawdown, and persisted risk events" />
      <div className="workspace-summary"><SummaryCard label="MANAGER STATUS" value={risk?.risk_manager_status ?? 'Unavailable'} /><SummaryCard label="OPEN EXPOSURE" value={pct(num(risk?.current_exposure_pct))} /><SummaryCard label="RISK CAPACITY USED" value={pct(num(risk?.used_risk_capacity_pct))} /><SummaryCard label="CAPACITY AVAILABLE" value={pct(num(risk?.available_risk_capacity_pct))} /><SummaryCard label="DAILY LOSS CAPACITY" value={pct(num(risk?.daily_loss_capacity_pct))} /><SummaryCard label="PORTFOLIO DRAWDOWN" value={pct(num(portfolio?.drawdown_pct))} /></div>
      <h2 className="workspace-section-title">Enforced limits · managed by local risk engine</h2>
      <div className="workspace-summary">{limits.map(([label, value, unit]) => <SummaryCard key={label} label={label.toUpperCase()} value={value == null ? '—' : `${value}${unit}`} />)}</div>
      <div className="workspace-note">Risk limits are enforced centrally by the simulator and cannot be increased by model learning or dashboard preferences.</div>
      <h2 className="workspace-section-title">Risk events · {alerts.length}</h2>
      {alerts.length ? <Table minWidth={700}><TableHead labels={['TIMESTAMP', 'EVENT', 'ASSET', 'MARKET', 'DETAIL']} />{alerts.map((event, index) => <tr key={event.event_id ?? index}><td>{timestamp(event.timestamp)}</td><td>{event.event_type ?? 'RISK_ALERT'}</td><td>{event.symbol ?? '—'}</td><td>{event.market ?? '—'}</td><td>{String(event.payload?.message ?? event.payload?.reason ?? 'No detail recorded')}</td></tr>)}</Table> : <EmptyState text="No risk events found in the loaded system activity." />}
    </>
  )
}

function ActivityScreen({ events, loadState }: { events: WorkspaceEvent[]; loadState: 'loading' | 'ready' | 'error' }) {
  const [filter, setFilter] = useState('')
  const eventDetail = (event: WorkspaceEvent) => String(event.payload?.message ?? event.payload?.reason ?? event.payload?.status ?? '—')
  const filtered = events.filter((event) => !filter || [
    event.event_type,
    event.source,
    event.symbol,
    event.market,
    eventDetail(event),
  ].join(' ').toLowerCase().includes(filter.trim().toLowerCase()))
  const alertCount = events.filter((event) => /ERROR|FAIL|REJECT|RISK_ALERT/i.test(event.event_type ?? '')).length
  const sourceCount = new Set(events.map((event) => event.source).filter((source): source is string => Boolean(source))).size
  const assetCount = new Set(events.map((event) => event.symbol).filter((symbol): symbol is string => Boolean(symbol))).size
  return (
    <div className="activity-screen">
      <ScreenHeader
        title="Activity"
        description="Persisted system events from the local application history"
        actions={
          <div className="activity-filter">
            <input className="workspace-search" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Search events, source, asset…" aria-label="Filter activity events" />
            {filter && <button type="button" className="activity-clear-filter" onClick={() => setFilter('')} aria-label="Clear activity filter">CLEAR</button>}
          </div>
        }
      />
      <div className="activity-metrics" aria-label="Activity summary">
        <div className="activity-metric"><span>EVENTS LOADED</span><strong>{events.length}</strong><small>Persisted records</small></div>
        <div className="activity-metric"><span>ALERTS &amp; FAILURES</span><strong className={alertCount ? 'negative' : ''}>{alertCount}</strong><small>Risk, rejected, or error events</small></div>
        <div className="activity-metric"><span>EVENT SOURCES</span><strong>{sourceCount}</strong><small>Distinct producers</small></div>
        <div className="activity-metric"><span>ASSETS</span><strong>{assetCount}</strong><small>Distinct symbols</small></div>
      </div>
      <section className="activity-ledger" aria-label="Persisted event ledger">
        <div className="activity-ledger-heading">
          <div>
            <span className="activity-kicker">LOCAL EVENT STORE</span>
            <h2>Event ledger</h2>
          </div>
          <span className="activity-ledger-count">{filtered.length} {filter ? 'MATCHES' : 'EVENTS'}</span>
        </div>
        {loadState === 'error' && <div role="alert" className="activity-empty-state activity-empty-alert"><span>BACKEND UNAVAILABLE</span><strong>Activity history could not be loaded</strong><p>Retry after the backend connection is restored.</p></div>}
        {loadState === 'loading' && <div role="status" className="activity-empty-state"><span>LOCAL EVENT STORE</span><strong>Loading persisted system events</strong><p>Waiting for backend history response…</p></div>}
        {filtered.length ? (
          <div className="activity-table">
            <Table minWidth={850}><TableHead labels={['TIMESTAMP', 'EVENT', 'SOURCE', 'ASSET', 'MARKET', 'DETAIL']} />{filtered.map((event, index) => (
              <tr key={event.event_id ?? index}>
                <td>{timestamp(event.timestamp)}</td>
                <td className={/ERROR|FAIL|REJECT|RISK_ALERT/i.test(event.event_type ?? '') ? 'negative' : ''}>{event.event_type ?? '—'}</td>
                <td>{event.source ?? '—'}</td>
                <td>{event.symbol ?? '—'}</td>
                <td>{event.market ?? '—'}</td>
                <td>{eventDetail(event)}</td>
              </tr>
            ))}</Table>
          </div>
        ) : loadState === 'ready' ? <div className="activity-empty-state"><span>{filter ? 'FILTER RESULT' : 'LOCAL EVENT STORE'}</span><strong>{filter ? 'No matching events' : 'No system events recorded'}</strong><p>{filter ? 'Adjust or clear the current filter.' : 'Persisted application events will appear here.'}</p></div> : null}
      </section>
      <p className="workspace-note activity-note">The API exposes persisted system events, not arbitrary process logs. Application errors remain visible in local backend logs.</p>
    </div>
  )
}


function DiagnosticStatusCard({ label, value, detail }: { label: string; value: string; detail: string }) {
  const tone = /FAILED|UNAVAILABLE|DISCONNECTED|INACTIVE|DEGRADED/i.test(value)
    ? 'negative'
    : /READY|CONNECTED|ACTIVE|HEALTHY|RUNNING/i.test(value)
      ? 'positive'
      : 'neutral'
  return (
    <article className={`diagnostics-status-card ${tone}`}>
      <div className="diagnostics-status-card-heading">
        <span className="diagnostics-status-light" />
        <span>{label}</span>
        <small>{tone === 'positive' ? 'OK' : tone === 'negative' ? 'ISSUE' : 'CHECK'}</small>
      </div>
      <strong>{value}</strong>
      <small>{detail}</small>
    </article>
  )
}

function DiagnosticsScreen({ data, activityLoadState, diagnostics }: {
  data: WorkspaceData
  activityLoadState: Props['activityLoadState']
  diagnostics: Props['diagnostics']
}) {
  const healthValue = (key: string) => {
    const value = diagnostics.health?.[key]
    return value === true ? 'READY' : value === false ? 'FAILED' : 'UNKNOWN'
  }
  const runtimeChecks = [
    ['Backend supervisor', diagnostics.backendState.toUpperCase(), 'Tauri-managed Python process'],
    ['Authenticated API', diagnostics.apiReady ? 'READY' : 'UNAVAILABLE', 'Bearer-authenticated REST status probe'],
    ['Database', healthValue('database_connected'), 'SQLite connection reported by backend'],
    ['Realtime event channel', diagnostics.websocketConnected ? 'CONNECTED' : 'DISCONNECTED', 'Authenticated WebSocket connection'],
    ['Market data', diagnostics.marketDataStatus.toUpperCase(), 'Current quote and candle freshness'],
    ['Market scanner', diagnostics.health?.market_data_active === true ? 'ACTIVE' : diagnostics.health?.market_data_active === false ? 'INACTIVE' : 'UNKNOWN', 'Scanner lifecycle state'],
    ['Learning model', diagnostics.health?.learning_active === true ? 'ACTIVE' : diagnostics.health?.learning_active === false ? 'INACTIVE' : 'UNKNOWN', 'A trained model is currently available'],
    ['Paper trading', diagnostics.health?.paper_trading_active === true ? 'ACTIVE' : diagnostics.health?.paper_trading_active === false ? 'INACTIVE' : 'UNKNOWN', 'Simulated execution only'],
    ['Risk manager', data.risk?.risk_manager_status?.toUpperCase() ?? 'UNKNOWN', 'Backend risk status from latest API response'],
    ['Persisted activity', activityLoadState === 'ready' ? 'READY' : activityLoadState === 'error' ? 'UNAVAILABLE' : 'CHECKING', 'Recent application events'],
  ]
  const readyChecks = runtimeChecks.filter(([, state]) => /READY|CONNECTED|ACTIVE|HEALTHY|RUNNING/i.test(state)).length
  const attentionRequired = runtimeChecks.some(([, state]) => /FAILED|UNAVAILABLE|DISCONNECTED|INACTIVE|DEGRADED/i.test(state))
  const readinessPercent = runtimeChecks.length ? Math.round((readyChecks / runtimeChecks.length) * 100) : 0
  const requestCount = diagnostics.requestMetrics.requestCount
  const failureCount = diagnostics.requestMetrics.failureCount
  const successCount = Math.max(0, requestCount - failureCount)
  const successPercent = requestCount ? Math.round((successCount / requestCount) * 100) : 0
  const failurePercent = requestCount ? Math.round((Math.min(requestCount, failureCount) / requestCount) * 100) : 0
  const components = diagnostics.health?.components
  const componentEntries = components && typeof components === 'object'
    ? Object.entries(components as Record<string, { healthy?: boolean; details?: string | null }>)
    : []
  const detailedMetrics = diagnostics.health?.metrics
  const metricsText = detailedMetrics && typeof detailedMetrics === 'object'
    ? JSON.stringify(detailedMetrics, null, 2).slice(0, 16_000)
    : ''
  const logMessage = diagnostics.logState === 'loading'
    ? 'Loading backend process logs…'
    : diagnostics.logState === 'error'
      ? 'Backend process logs could not be read.'
      : diagnostics.logState === 'unavailable'
        ? 'Process logs are available in the installed desktop application.'
        : diagnostics.logs.length === 0
          ? 'No backend process output has been recorded yet.'
          : ''

  return (
    <div className="diagnostics-screen">
      <header className="diagnostics-header">
        <div className="diagnostics-header-copy">
          <span className="diagnostics-eyebrow"><i /> LOCAL SYSTEM OBSERVABILITY</span>
          <h1>System Diagnostics</h1>
          <p>Service readiness, request health, backend activity, and persisted events.</p>
        </div>
        <aside className={`diagnostics-readiness ${attentionRequired ? 'attention' : readyChecks === runtimeChecks.length ? 'clear' : 'pending'}`} aria-label="Overall diagnostics status">
          <div className={`diagnostics-readiness-heading ${readyChecks < runtimeChecks.length && !attentionRequired ? 'pending' : ''}`}><span className="diagnostics-status-light" /><span>OVERALL STATUS</span><b>{attentionRequired ? 'ATTENTION REQUIRED' : readyChecks === runtimeChecks.length ? 'ALL CHECKS PASSING' : 'CHECKS PENDING'}</b></div>
          <div className="diagnostics-readiness-track" role="progressbar" aria-label="Passing service checks" aria-valuemin={0} aria-valuemax={runtimeChecks.length} aria-valuenow={readyChecks}>
            <span style={{ width: `${readinessPercent}%` }} />
          </div>
          <small>{readyChecks} of {runtimeChecks.length} service checks passing</small>
        </aside>
      </header>
      <section className="diagnostics-section diagnostics-overview">
        <div className="diagnostics-overview-heading">
          <div>
            <span className="diagnostics-eyebrow">CORE / SERVICE MAP</span>
            <h2 className="workspace-section-title">Live service status</h2>
          </div>
          <span className="diagnostics-live-tag"><i /> MONITORING</span>
        </div>
        <div className="diagnostics-health-grid">
          <DiagnosticStatusCard label="BACKEND SUPERVISOR" value={diagnostics.backendState.toUpperCase()} detail="Managed Python process" />
          <DiagnosticStatusCard label="AUTHENTICATED API" value={diagnostics.apiReady ? 'READY' : 'UNAVAILABLE'} detail="Local REST interface" />
          <DiagnosticStatusCard label="DATABASE" value={healthValue('database_connected')} detail="SQLite connection" />
          <DiagnosticStatusCard label="LIVE EVENT STREAM" value={diagnostics.websocketConnected ? 'CONNECTED' : 'DISCONNECTED'} detail="Authenticated WebSocket" />
          <DiagnosticStatusCard label="MARKET DATA" value={diagnostics.marketDataStatus.toUpperCase()} detail="Quote and candle freshness" />
          <DiagnosticStatusCard label="SCANNER" value={healthValue('market_data_active')} detail="Market scan lifecycle" />
        </div>
        <div className="diagnostics-telemetry">
          <div className="diagnostics-telemetry-card">
            <span>HTTP REQUESTS <small>/ 60 SEC</small></span>
            <strong>{requestCount}</strong>
            <small>Frontend API calls</small>
          </div>
          <div className="diagnostics-telemetry-card">
            <span>FAILED REQUESTS <small>/ 60 SEC</small></span>
            <strong className={failureCount ? 'negative' : 'positive'}>{failureCount}</strong>
            <small>Recent request errors</small>
          </div>
          <div className="diagnostics-telemetry-card">
            <span>LATENCY <small>AVG / P95</small></span>
            <strong>{diagnostics.requestMetrics.averageDurationMs}<small> / {diagnostics.requestMetrics.p95DurationMs} ms</small></strong>
            <small>Rolling request window</small>
          </div>
          <div className="diagnostics-request-health">
            <div className="diagnostics-request-health-heading"><span>REQUEST HEALTH</span><strong>{requestCount ? `${successPercent}%` : '—'}</strong></div>
            <div className="diagnostics-request-health-track" role="progressbar" aria-label="Successful API requests" aria-valuemin={0} aria-valuemax={requestCount} aria-valuenow={successCount}>
              <span className="success" style={{ width: `${successPercent}%` }} />
              <span className="failure" style={{ width: `${failurePercent}%` }} />
            </div>
            <small>{successCount} successful <i /> {failureCount} failed</small>
          </div>
        </div>
      </section>
      <details className="diagnostics-section diagnostics-collapsible">
        <summary className="diagnostics-section-heading">
          <div>
            <h2 className="workspace-section-title">Feature runtime checks</h2>
            <p>Health and availability checks reported by the running application.</p>
          </div>
          <span className="diagnostics-accordion-count">{runtimeChecks.length} CHECKS</span>
        </summary>
        <div className="diagnostics-content">
          <div className="diagnostics-table diagnostics-runtime-table">
            <Table minWidth={700}><TableHead labels={['SERVICE', 'STATE', 'CHECK']} />{runtimeChecks.map(([name, state, detail]) => (
              <tr key={name}><td>{name}</td><td className={/FAILED|UNAVAILABLE|DISCONNECTED|INACTIVE|DEGRADED/i.test(state) ? 'negative' : ''}>{state}</td><td>{detail}</td></tr>
            ))}</Table>
          </div>
        </div>
      </details>
      <details className="diagnostics-section diagnostics-collapsible">
        <summary className="diagnostics-section-heading">
          <div>
            <h2 className="workspace-section-title">Backend components</h2>
            <p>Subsystem health details and the latest backend metrics snapshot.</p>
          </div>
          <span className="diagnostics-accordion-count">{componentEntries.length} COMPONENTS</span>
        </summary>
        <div className="diagnostics-content">
          {componentEntries.length ? (
            <div className="diagnostics-table diagnostics-component-table">
              <Table minWidth={700}><TableHead labels={['COMPONENT', 'STATE', 'DETAIL']} />{componentEntries.map(([name, value]) => (
                <tr key={name}><td>{name}</td><td className={value.healthy ? '' : 'negative'}>{value.healthy ? 'HEALTHY' : 'DEGRADED'}</td><td>{value.details ?? 'No additional detail'}</td></tr>
              ))}</Table>
            </div>
          ) : <EmptyState text="Detailed backend component status is not available yet." />}
          {metricsText && <pre className="diagnostics-log" role="log" aria-label="Detailed subsystem health metrics">{metricsText}</pre>}
        </div>
      </details>
      <details className="diagnostics-section diagnostics-collapsible">
        <summary className="diagnostics-section-heading">
          <div>
            <h2 className="workspace-section-title">Frontend request &amp; render trace</h2>
            <p>Most recent operations first · up to 100 events.</p>
          </div>
          <span className="diagnostics-accordion-count">{diagnostics.frontendEvents.length} EVENTS</span>
        </summary>
        <div className="diagnostics-content">
          {diagnostics.frontendEvents.length ? (
            <div className="diagnostics-table diagnostics-trace-table">
              <Table minWidth={900}><TableHead labels={['TIMESTAMP', 'LEVEL', 'OPERATION', 'STATUS', 'MS', 'DETAIL / RECOMMENDATION']} />{diagnostics.frontendEvents.slice().reverse().slice(0, 100).map((event) => (
                <tr key={event.id}>
                  <td>{timestamp(event.timestamp)}</td>
                  <td className={event.level === 'ERROR' ? 'negative' : ''}>{event.level}</td>
                  <td>{event.operation}</td>
                  <td className={event.status === 'FAILURE' ? 'negative' : ''}>{event.status}{event.status_code ? ` · HTTP ${event.status_code}` : ''}</td>
                  <td>{event.duration_ms == null ? '—' : Math.round(event.duration_ms)}</td>
                  <td>{[event.detail, event.recommendation].filter(Boolean).join(' — ') || event.endpoint || '—'}</td>
                </tr>
              ))}</Table>
            </div>
          ) : <EmptyState text="Frontend traces appear as the app performs requests and renders updates." />}
          <p className="workspace-note">Frontend request and React render traces are kept in a bounded in-memory buffer and uploaded in small batches while the backend is available. Query strings and common credentials are removed; response bodies and trading payloads are never logged.</p>
        </div>
      </details>
      <details className="diagnostics-section diagnostics-collapsible">
        <summary className="diagnostics-section-heading">
          <div>
            <h2 className="workspace-section-title">Backend process logs</h2>
            <p>Recent output from the supervised backend process.</p>
          </div>
          <span className="diagnostics-accordion-count">{diagnostics.logs.length} LINES</span>
        </summary>
        <div className="diagnostics-content">
          {logMessage ? <p role={diagnostics.logState === 'error' ? 'alert' : 'status'} className="workspace-note">{logMessage}</p> : (
            <pre className="diagnostics-log" role="log" aria-live="polite">{diagnostics.logs.join('\n')}</pre>
          )}
        </div>
      </details>
      <details className="diagnostics-section diagnostics-collapsible">
        <summary className="diagnostics-section-heading">
          <div>
            <h2 className="workspace-section-title">Recent application activity</h2>
            <p>Latest persisted events from the local application history.</p>
          </div>
          <span className="diagnostics-accordion-count">{data.events.length} EVENTS</span>
        </summary>
        <div className="diagnostics-content">
          {activityLoadState === 'error' && <p role="alert" className="workspace-note">Persisted activity could not be loaded. The displayed events may be stale.</p>}
          {activityLoadState === 'loading' && <p role="status" className="workspace-note">Loading persisted system events…</p>}
          {data.events.length ? <div className="diagnostics-table diagnostics-activity-table"><Table minWidth={850}><TableHead labels={['TIMESTAMP', 'EVENT', 'SOURCE', 'ASSET', 'MARKET', 'DETAIL']} />{data.events.slice(0, 50).map((event, index) => <tr key={event.event_id ?? index}>
            <td>{timestamp(event.timestamp)}</td><td className={/ERROR|FAIL|REJECT|RISK_ALERT/i.test(event.event_type ?? '') ? 'negative' : ''}>{event.event_type ?? '—'}</td><td>{event.source ?? '—'}</td><td>{event.symbol ?? '—'}</td><td>{event.market ?? '—'}</td><td>{String(event.payload?.message ?? event.payload?.reason ?? event.payload?.status ?? '—')}</td>
          </tr>)}</Table></div> : activityLoadState === 'ready' ? <EmptyState text="No system events are available in local history." /> : null}
          {!diagnostics.isDesktop && <p className="workspace-note">Backend process logs are only exposed by the supervised desktop application.</p>}
        </div>
      </details>
    </div>
  )
}

function IntelligenceModePanel() {
  type Mode = 'balanced' | 'fast' | 'research' | 'conservative'
  type Profile = { mode: Mode; max_tool_calls: number; memory_enabled: boolean; feedback_enabled: boolean; provider_enabled: boolean; response_detail: 'brief' | 'normal' | 'detailed' }
  const [profile, setProfile] = useState<Profile | null>(null)
  const [selected, setSelected] = useState<Mode>('balanced')
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState('')
  useEffect(() => {
    let active = true
    void requestJson<Profile>('/settings/intelligence').then((result) => {
      if (active && result) { setProfile(result); setSelected(result.mode) }
    }).catch((error) => { if (active) setStatus(error instanceof Error ? error.message : 'Could not load intelligence mode.') })
    return () => { active = false }
  }, [])
  const descriptions: Record<Mode, string> = {
    balanced: 'Balanced evidence gathering, memory and optional provider interpretation.',
    fast: 'Single-tool requests, brief answers and no optional provider interpretation.',
    research: 'Multi-tool evidence requests with memory and detailed output.',
    conservative: 'Single-tool requests with provider interpretation and feedback adaptation disabled.',
  }
  return (
    <section className="settings-section settings-intelligence">
      <div className="settings-section-heading">
        <div>
          <span className="settings-index">01 / ASSISTANT PROFILE</span>
          <h2>Assistant intelligence</h2>
          <p>Choose how local market evidence is gathered and presented.</p>
        </div>
        <span className="settings-section-tag">PERSISTENT</span>
      </div>
      <div className="settings-intelligence-grid">
        <label className="settings-card settings-field"><span><b>Intelligence mode</b><small>{descriptions[selected]}</small></span>
          <select className="workspace-select" value={selected} onChange={(event) => setSelected(event.target.value as Mode)}>
            <option value="balanced">Balanced</option><option value="fast">Fast</option><option value="research">Research</option><option value="conservative">Conservative</option>
          </select>
        </label>
        <div className="settings-card settings-field settings-profile-readout"><span><b>Active profile</b><small>{profile ? `${profile.max_tool_calls} tool calls · ${profile.response_detail} response · memory ${profile.memory_enabled ? 'on' : 'off'} · provider ${profile.provider_enabled ? 'on' : 'off'}` : 'Loading configuration…'}</small></span></div>
        <button className="settings-card settings-field settings-apply-mode" disabled={saving || !profile} onClick={async () => {
          setSaving(true); setStatus('')
          try {
            const result = await mutateJson<Profile>('/settings/intelligence', 'PUT', { mode: selected })
            if (result) { setProfile(result); setSelected(result.mode) }
            setStatus('Intelligence mode saved and reloaded.')
          } catch (error) { setStatus(error instanceof Error ? error.message : 'Could not save intelligence mode.') }
          finally { setSaving(false) }
        }}><span><b>{saving ? 'Saving…' : 'Apply intelligence mode'}</b><small>Changes apply to subsequent assistant requests.</small></span></button>
      </div>
      {status && <p role="status" className="settings-status">{status}</p>}
    </section>
  )
}


function SettingsScreen({
  settings,
  preferences,
  onPreferencesChange,
  onSettingsSave,
}: {
  settings: WorkspaceSettings | null
  preferences: DashboardPreferences
  onPreferencesChange: (preferences: DashboardPreferences) => void
  onSettingsSave: Props['onSettingsSave']
}) {
  const [draft, setDraft] = useState<Record<string, string>>({})
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')
  const value = (key: keyof WorkspaceSettings) => {
    const setting = settings?.[key]
    return draft[key] ?? (Array.isArray(setting) ? setting.join(', ') : String(setting ?? ''))
  }
  const updatePreference = (key: keyof DashboardPreferences) => onPreferencesChange({ ...preferences, [key]: !preferences[key] })
  const capitalSettings = [
    ['spot_initial_balance', 'Spot paper starting balance'],
    ['futures_initial_balance', 'Futures paper starting balance'],
  ] as const
  const riskSettings = [
    ['risk_per_trade_pct', 'Risk per trade'],
    ['risk_max_daily_loss_pct', 'Maximum daily loss'],
    ['risk_max_total_open_pct', 'Maximum total open risk'],
    ['risk_max_leverage', 'Maximum Futures leverage'],
    ['max_spot_positions', 'Maximum Spot positions'],
    ['max_futures_positions', 'Maximum Futures positions'],
  ] as const
  const telegramSettings = [
    ['telegram_notify_decisions', 'Decision updates'],
    ['telegram_notify_executions', 'Paper trade executions'],
    ['telegram_notify_risk', 'Risk alerts'],
    ['telegram_notify_learning', 'Learning updates'],
  ] as const
  return (
    <div className="settings-page">
      <ScreenHeader title="Settings" description="Engine settings are validated, saved locally by the backend, and applied to the running scanner and risk controls." />
      <IntelligenceModePanel />
      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <span className="settings-index">02 / DISPLAY</span>
            <h2>Dashboard preferences</h2>
            <p>Personal controls saved on this device only.</p>
          </div>
          <span className="settings-section-tag">LOCAL</span>
        </div>
        <div className="settings-card-list settings-preferences-grid">
        {([
          ['autoScale', 'Chart auto-scale', 'Scale price to visible candle range'],
          ['crosshair', 'Chart crosshair', 'Show crosshair and axis labels'],
          ['showRiskAlerts', 'Show risk alert badge', 'Display a badge when risk events are present'],
        ] as [keyof DashboardPreferences, string, string][]).map(([key, label, detail]) => (
          <button key={key} className="settings-card settings-field" role="switch" aria-checked={preferences[key]} onClick={() => updatePreference(key)}>
            <span><b>{label}</b><small>{detail}</small></span><i className={preferences[key] ? 'switch-on' : ''} />
          </button>
        ))}
        </div>
      </section>
      <section className="settings-section settings-engine-section">
        <div className="settings-section-heading">
          <div>
            <span className="settings-index">03 / RUNTIME</span>
            <h2>Engine configuration</h2>
            <p>Persistent controls for markets, risk limits, and notifications.</p>
          </div>
          <span className="settings-section-tag">BACKEND</span>
        </div>
        <form className="settings-engine-form" onSubmit={async (event) => {
        event.preventDefault()
        setMessage('')
        const numberKeys = ['spot_initial_balance','futures_initial_balance','risk_per_trade_pct','risk_max_daily_loss_pct','risk_max_total_open_pct','risk_max_leverage','max_spot_positions','max_futures_positions']
        const numericValues: Record<string, number> = {}
        for (const key of numberKeys) {
          if (draft[key] === undefined || draft[key] === '') continue
          const parsed = Number(draft[key])
          if (!Number.isFinite(parsed) || parsed <= 0) {
            setMessage(`${key.replaceAll('_', ' ')} must be a finite number greater than zero.`)
            return
          }
          if (['risk_per_trade_pct','risk_max_daily_loss_pct','risk_max_total_open_pct'].includes(key) && parsed > 100) {
            setMessage(`${key.replaceAll('_', ' ')} cannot exceed 100%.`)
            return
          }
          if (['max_spot_positions','max_futures_positions'].includes(key) && !Number.isInteger(parsed)) {
            setMessage(`${key.replaceAll('_', ' ')} must be a whole number.`)
            return
          }
          numericValues[key] = parsed
        }
        const timeframeValues = draft.timeframes === undefined
          ? undefined
          : draft.timeframes.split(',').map((item) => item.trim()).filter(Boolean)
        if (timeframeValues && (!timeframeValues.length || timeframeValues.some((item) => !/^(\d+[smhdw]|1M)$/.test(item)))) {
          setMessage('Enter one or more valid interval values separated by commas (for example: 1m, 15m, 1h, 1d).')
          return
        }
        setSaving(true)
        const payload: Record<string, unknown> = {}
        const boolKeys = ['spot_enabled','futures_enabled','scan_all_eligible_symbols','telegram_enabled','telegram_notify_decisions','telegram_notify_executions','telegram_notify_risk','telegram_notify_learning']
        for (const key of boolKeys) if (draft[key] !== undefined) payload[key] = draft[key] === 'true'
        Object.assign(payload, numericValues)
        if (timeframeValues) payload.timeframes = timeframeValues
        try { await onSettingsSave(payload); setDraft({}); setMessage('Settings saved and applied.') }
        catch (error) { setMessage(error instanceof Error ? error.message : 'Settings could not be saved.') }
        finally { setSaving(false) }
      }}>
          <div className="settings-field-groups">
            <fieldset className="settings-group">
              <legend><span>01</span> Markets &amp; scanning</legend>
              <div className="settings-fields">
                <label className="settings-card settings-field"><span><b>Spot market data</b><small>Enable or pause Spot scanning</small></span><select className="workspace-select" value={value('spot_enabled')} onChange={(event) => setDraft((state) => ({ ...state, spot_enabled: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
                <label className="settings-card settings-field"><span><b>USDⓈ-M Futures</b><small>Enable or pause Futures scanning</small></span><select className="workspace-select" value={value('futures_enabled')} onChange={(event) => setDraft((state) => ({ ...state, futures_enabled: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
                <label className="settings-card settings-field"><span><b>Eligible symbol set</b><small>Scan up to 50 high-volume symbols per market</small></span><select className="workspace-select" value={value('scan_all_eligible_symbols')} onChange={(event) => setDraft((state) => ({ ...state, scan_all_eligible_symbols: event.target.value }))}><option value="true">Enabled</option><option value="false">Top 10</option></select></label>
                <label className="settings-card settings-field"><span><b>Analysis timeframes</b><small>Comma-separated Binance intervals</small></span><input className="workspace-search" value={value('timeframes')} onChange={(event) => setDraft((state) => ({ ...state, timeframes: event.target.value }))} /></label>
              </div>
            </fieldset>
            <fieldset className="settings-group">
              <legend><span>02</span> Paper capital</legend>
              <div className="settings-fields">
                {capitalSettings.map(([key, label]) => <label className="settings-card settings-field" key={key}><span><b>{label}</b><small>Virtual account starting balance</small></span><input className="workspace-search" type="number" min="0.01" step="any" value={value(key)} onChange={(event) => setDraft((state) => ({ ...state, [key]: event.target.value }))} /></label>)}
              </div>
            </fieldset>
            <fieldset className="settings-group">
              <legend><span>03</span> Risk boundaries</legend>
              <div className="settings-fields">
                {riskSettings.map(([key, label]) => <label className="settings-card settings-field" key={key}><span><b>{label}</b><small>{key.endsWith('_pct') ? 'Percent limit' : key.includes('positions') ? 'Maximum open positions' : 'Futures multiplier'}</small></span><input className="workspace-search" type="number" min="0.01" step="any" value={value(key)} onChange={(event) => setDraft((state) => ({ ...state, [key]: event.target.value }))} /></label>)}
              </div>
            </fieldset>
            <fieldset className="settings-group">
              <legend><span>04</span> Telegram notifications</legend>
              <div className="settings-fields">
                <label className="settings-card settings-field"><span><b>Telegram delivery</b><small>Uses credentials configured in the private environment</small></span><select className="workspace-select" value={value('telegram_enabled')} onChange={(event) => setDraft((state) => ({ ...state, telegram_enabled: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
                {telegramSettings.map(([key, label]) => <label className="settings-card settings-field" key={key}><span><b>{label}</b><small>Send this category to the authorized chat</small></span><select className="workspace-select" value={value(key)} onChange={(event) => setDraft((state) => ({ ...state, [key]: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>)}
              </div>
            </fieldset>
          </div>
          <div className="settings-form-footer">
            <span className="settings-form-hint">Validated before applying · real exchange trading remains disabled.</span>
            <button className="table-action" type="submit" disabled={saving || !Object.keys(draft).length}>{saving ? 'Saving…' : 'Save engine settings'}</button>
            {message && <span role="status" className="settings-form-message">{message}</span>}
          </div>
        </form>
      </section>
      <section className="settings-section">
        <div className="settings-section-heading">
          <div>
            <span className="settings-index">04 / CURRENT CONFIGURATION</span>
            <h2>Engine status</h2>
            <p>Read-only snapshot of current saved values.</p>
          </div>
        </div>
        <div className="workspace-summary settings-readout-grid">
        <SummaryCard label="SPOT MARKET DATA" value={settings ? settings.spot_enabled ? 'ENABLED' : 'DISABLED' : 'Unavailable'} />
        <SummaryCard label="USDⓈ-M FUTURES" value={settings ? settings.futures_enabled ? 'ENABLED' : 'DISABLED' : 'Unavailable'} />
        <SummaryCard label="MARKET SCANNING" value={settings ? settings.scan_all_eligible_symbols ? 'ALL ELIGIBLE' : 'CONFIGURED SET' : 'Unavailable'} />
        <SummaryCard label="SPOT PAPER CAPITAL" value={money(num(settings?.spot_initial_balance))} />
        <SummaryCard label="FUTURES PAPER CAPITAL" value={money(num(settings?.futures_initial_balance))} />
        <SummaryCard label="TELEGRAM" value={settings ? settings.telegram_enabled ? 'ENABLED' : 'DISABLED' : 'Unavailable'} detail={settings?.telegram_enabled ? `Token ${settings.telegram_bot_token_configured ? 'configured' : 'missing'} · chat ${settings.telegram_chat_id_configured ? 'configured' : 'missing'}` : 'No credentials are exposed'} />
        </div>
      </section>
      <section className="settings-section settings-risk-readout">
        <div className="settings-section-heading">
          <div>
            <span className="settings-index">05 / SAFETY</span>
            <h2>Risk controls</h2>
            <p>These values are configured by the engine and are not changed here.</p>
          </div>
          <span className="settings-section-tag">READ ONLY</span>
        </div>
        <div className="workspace-summary settings-readout-grid">
        <SummaryCard label="RISK / TRADE" value={settings?.risk_per_trade_pct == null ? '—' : `${settings.risk_per_trade_pct}%`} />
        <SummaryCard label="MAX DAILY LOSS" value={settings?.risk_max_daily_loss_pct == null ? '—' : `${settings.risk_max_daily_loss_pct}%`} />
        <SummaryCard label="MAX OPEN RISK" value={settings?.risk_max_total_open_pct == null ? '—' : `${settings.risk_max_total_open_pct}%`} />
        <SummaryCard label="FUTURES LEVERAGE" value={settings?.risk_max_leverage == null ? '—' : `${settings.risk_max_leverage}x`} />
        <SummaryCard label="POSITION LIMITS" value={settings ? `${settings.max_spot_positions ?? '—'} Spot / ${settings.max_futures_positions ?? '—'} Futures` : '—'} />
        <SummaryCard label="TIMEFRAMES" value={settings?.timeframes?.length ? settings.timeframes.join(', ') : '—'} />
        </div>
      </section>
      <div className="workspace-note settings-safety-note">Telegram credentials remain secret and cannot be changed here. Starting balances can only be changed before the first paper trade. Real exchange trading remains disabled.</div>
    </div>
  )
}


type CommunityStrategy = {
  public_id: string
  name: string
  description: string
  strategy_key: string
  rules: Record<string, unknown>
  supported_assets: string[]
  supported_timeframes: string[]
  risk_configuration: Record<string, number>
  known_limitations: string[]
  backtest_report: Record<string, unknown>
  report_provenance: string
  report_sha256: string
  source_report_id?: string | null
  reproducibility_status?: string
  verification_status?: string
  version: number
  favorite_count: number
  is_favorite: boolean
  is_owner: boolean
  version_history?: { version: number; created_at: string | null; snapshot: Record<string, unknown> }[]
}

function CommunityLibraryScreen() {
  const [items, setItems] = useState<CommunityStrategy[]>([])
  const listRequestId = useRef(0)
  const [listLoading, setListLoading] = useState(false)
  const [listFailed, setListFailed] = useState(false)
  const [query, setQuery] = useState('')
  const [strategyKey, setStrategyKey] = useState('')
  const [assetFilter, setAssetFilter] = useState('')
  const [timeframeFilter, setTimeframeFilter] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showPublish, setShowPublish] = useState(false)
  const [showFavorites, setShowFavorites] = useState(false)
  const [sort, setSort] = useState('recent')
  const [selected, setSelected] = useState<CommunityStrategy | null>(null)
  const detailRequestId = useRef(0)
  const [busy, setBusy] = useState(false)
  const publishLock = useRef(false)
  const [notice, setNotice] = useState('')
  const [pendingItemActions, setPendingItemActions] = useState<Set<string>>(() => new Set())
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [key, setKey] = useState('momentum')
  const [assets, setAssets] = useState('BTCUSDT, ETHUSDT')
  const [timeframes, setTimeframes] = useState('15m, 1h')
  const [rules, setRules] = useState('{"entry":"Describe the entry rule","exit":"Describe the exit rule"}')
  const [risk, setRisk] = useState('{"risk_per_trade_pct":1,"max_position_pct":10}')
  const [limitations, setLimitations] = useState('Results are user-submitted and not a forecast.')
  const [report, setReport] = useState('{"total_trades":0,"sample_period":""}')
  const [sourceReportId, setSourceReportId] = useState('')

  const load = useCallback(async () => {
    const requestId = ++listRequestId.current
    const normalizedAsset = assetFilter.trim().toUpperCase()
    const normalizedTimeframe = timeframeFilter.trim()
    const validTimeframes = ['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1d','1w']
    if (normalizedAsset && !/^[A-Z0-9]{2,20}$/.test(normalizedAsset)) {
      setNotice('Asset filter must be a valid market symbol, such as BTCUSDT.')
      return
    }
    if (normalizedTimeframe && !validTimeframes.includes(normalizedTimeframe)) {
      setNotice('Choose a supported timeframe: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, 1d, or 1w.')
      return
    }
    if (!['recent','updated','name'].includes(sort)) {
      setNotice('Unsupported sort order. Please select a valid option.')
      return
    }
    const params = new URLSearchParams({ q: query.trim(), sort, limit: '50' })
    if (strategyKey) params.set('strategy_key', strategyKey)
    if (normalizedAsset) params.set('asset', normalizedAsset)
    if (normalizedTimeframe) params.set('timeframe', normalizedTimeframe)
    setListFailed(false)
    setListLoading(true)
    try {
      const result = await requestJson<{ strategies?: CommunityStrategy[] }>(showFavorites ? '/community/favorites' : `/community/strategies?${params.toString()}`)
      if (requestId !== listRequestId.current) return
      if (!result || !Array.isArray(result.strategies)) {
        setListFailed(true)
        setNotice('Community library returned an invalid response. Please refresh and try again.')
        return
      }
      setItems(result.strategies.filter(item => item && typeof item.public_id === 'string' && typeof item.name === 'string'))
      setNotice('')
    } catch (error) {
      if (requestId !== listRequestId.current) return
      setListFailed(true)
      setNotice(error instanceof Error ? error.message : 'Unable to load community strategies.')
    } finally {
      if (requestId === listRequestId.current) setListLoading(false)
    }
  }, [assetFilter, timeframeFilter, sort, query, strategyKey, showFavorites])
  useEffect(() => {
    const timer = window.setTimeout(() => { void load() }, 250)
    return () => {
      window.clearTimeout(timer)
      listRequestId.current += 1
    }
  }, [load])

  const publish = async (event: FormEvent) => {
    event.preventDefault()
    if (publishLock.current) return
    publishLock.current = true
    setBusy(true)
    setNotice('')
    try {
      const parsedRules: unknown = JSON.parse(rules)
      const parsedRisk: unknown = JSON.parse(risk)
      const parsedReport: unknown = JSON.parse(report)
      const supportedAssets = assets.split(',').map(value => value.trim().toUpperCase()).filter(Boolean)
      const supportedTimeframes = timeframes.split(',').map(value => value.trim()).filter(Boolean)
      const validTimeframes = ['1m','3m','5m','15m','30m','1h','2h','4h','6h','12h','1d','1w']
      if (name.trim().length < 2 || name.trim().length > 120) throw new Error('Strategy name must be between 2 and 120 characters.')
      if (description.length > 2000) throw new Error('Description must be 2,000 characters or fewer.')
      if (!supportedAssets.length || supportedAssets.some(value => !/^[A-Z0-9]{2,20}$/.test(value))) throw new Error('Enter valid comma-separated market symbols.')
      if (!supportedTimeframes.length || supportedTimeframes.some(value => !validTimeframes.includes(value))) throw new Error('Enter supported comma-separated timeframes.')
      if (new Set(supportedAssets).size !== supportedAssets.length || new Set(supportedTimeframes).size !== supportedTimeframes.length) throw new Error('Remove duplicate assets or timeframes.')
      if (!parsedRules || typeof parsedRules !== 'object' || Array.isArray(parsedRules)) throw new Error('Rules JSON must be an object.')
      if (!parsedRisk || typeof parsedRisk !== 'object' || Array.isArray(parsedRisk)) throw new Error('Risk configuration JSON must be an object.')
      if (!parsedReport || typeof parsedReport !== 'object' || Array.isArray(parsedReport)) throw new Error('Backtest report JSON must be an object.')
      const riskConfig = parsedRisk as Record<string, unknown>
      for (const field of ['risk_per_trade_pct','max_position_pct']) {
        const value = Number(riskConfig[field])
        if (!Number.isFinite(value) || value <= 0 || value > 100) throw new Error(`${field} must be greater than 0 and at most 100.`)
      }
      const payload = {
        name: name.trim(), description: description.trim(), strategy_key: key,
        supported_assets: supportedAssets,
        supported_timeframes: supportedTimeframes,
        rules: parsedRules, risk_configuration: parsedRisk,
        known_limitations: limitations.split('\n').map(value => value.trim()).filter(Boolean),
        backtest_report: parsedReport,
        ...(sourceReportId.trim() ? { source_report_id: sourceReportId.trim() } : {}),
      }
      await mutateJson(editingId ? `/community/strategies/${editingId}` : '/community/strategies', editingId ? 'PUT' : 'POST', payload)
      setNotice(editingId ? 'Published strategy version updated.' : 'Strategy published. Shared performance is labelled user-submitted.')
      setEditingId(null)
      setName('')
      setShowPublish(false)
      await load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to publish strategy.')
    } finally {
      publishLock.current = false
      setBusy(false)
    }
  }

  const openDetails = async (item: CommunityStrategy) => {
    const requestId = ++detailRequestId.current
    try {
      const detail = await requestJson<CommunityStrategy>(`/community/strategies/${item.public_id}`)
      if (requestId !== detailRequestId.current) return
      const isRecord = (value: unknown): value is Record<string, unknown> => Boolean(value && typeof value === 'object' && !Array.isArray(value))
      const history = detail?.version_history
      const validHistory = history == null || (Array.isArray(history) && history.every(version =>
        version && Number.isInteger(version.version) && version.version > 0 &&
        (version.created_at == null || typeof version.created_at === 'string') &&
        isRecord(version.snapshot) &&
        (version.snapshot.name == null || typeof version.snapshot.name === 'string')))
      if (!detail || detail.public_id !== item.public_id || typeof detail.name !== 'string' ||
          typeof detail.description !== 'string' ||
          !Array.isArray(detail.supported_assets) || !detail.supported_assets.every(value => typeof value === 'string') ||
          !Array.isArray(detail.supported_timeframes) || !detail.supported_timeframes.every(value => typeof value === 'string') ||
          !Array.isArray(detail.known_limitations) || !detail.known_limitations.every(value => typeof value === 'string') ||
          !isRecord(detail.backtest_report) || !isRecord(detail.rules) || !isRecord(detail.risk_configuration) ||
          typeof detail.report_provenance !== 'string' || typeof detail.report_sha256 !== 'string' ||
          !validHistory) {
        setNotice('Strategy details or version history are incomplete or invalid. The details panel was not opened.')
        return
      }
      setSelected({ ...detail, version_history: history ?? [] })
    } catch (error) {
      if (requestId !== detailRequestId.current) return
      setNotice(error instanceof Error ? error.message : 'Unable to load strategy details.')
    }
  }

  const editStrategy = (item: CommunityStrategy) => {
    if (busy) { setNotice('Wait for the current publish operation to finish before editing.'); return }
    setEditingId(item.public_id)
    setShowPublish(true)
    setName(item.name)
    setDescription(item.description)
    setKey(item.strategy_key)
    setAssets(item.supported_assets.join(', '))
    setTimeframes(item.supported_timeframes.join(', '))
    setRules(JSON.stringify(item.rules, null, 2))
    setRisk(JSON.stringify(item.risk_configuration, null, 2))
    setLimitations(item.known_limitations.join('\n'))
    setReport(JSON.stringify(item.backtest_report, null, 2))
    setSourceReportId(item.source_report_id ?? '')
    setNotice(`Editing your published strategy. Saving creates version ${item.version + 1}.`)
  }

  const beginItemAction = (publicId: string) => {
    if (pendingItemActions.has(publicId)) return false
    setPendingItemActions(current => new Set(current).add(publicId))
    return true
  }
  const finishItemAction = (publicId: string) => {
    setPendingItemActions(current => {
      const next = new Set(current)
      next.delete(publicId)
      return next
    })
  }

  const toggleFavorite = async (item: CommunityStrategy) => {
    if (!beginItemAction(item.public_id)) return
    const nextFavorite = !item.is_favorite
    try {
      await mutateJson(`/community/strategies/${item.public_id}/favorite`, 'POST', { favorite: nextFavorite })
      setItems(current => current.map(entry => entry.public_id === item.public_id
        ? { ...entry, is_favorite: nextFavorite, favorite_count: Math.max(0, entry.favorite_count + (nextFavorite ? 1 : -1)) }
        : entry))
      setSelected(current => current?.public_id === item.public_id
        ? { ...current, is_favorite: nextFavorite, favorite_count: Math.max(0, current.favorite_count + (nextFavorite ? 1 : -1)) }
        : current)
      setNotice(nextFavorite ? 'Strategy saved to favorites.' : 'Strategy removed from favorites.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update favorite.')
    } finally {
      finishItemAction(item.public_id)
    }
  }

  const reportItem = async (item: CommunityStrategy) => {
    if (!beginItemAction(item.public_id)) return
    try {
      await mutateJson(`/community/strategies/${item.public_id}/report`, 'POST', { reason: 'misleading_results', details: 'Please review this strategy listing.' })
      setNotice('Report submitted for review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to report listing.')
    } finally {
      finishItemAction(item.public_id)
    }
  }

  return <div className="screen-stack community-screen">
    <ScreenHeader title="Community Strategy Library" description="Browse and share strategy research · simulator-only · no live execution" />
    <div className="community-safety-strip">
      <span className="community-safety-mark">PAPER / RESEARCH</span>
      <p>Listings are shared only with clients connected to this backend. Desktop local mode keeps its own library; it does not automatically sync to the hosted community.</p>
    </div>
    <div className="community-index-strip" aria-label="Community library summary">
      <div><span>RESULTS LOADED</span><strong>{items.length.toString().padStart(2, '0')}</strong></div>
      <div><span>SAVED IN VIEW</span><strong>{items.filter(item => item.is_favorite).length.toString().padStart(2, '0')}</strong></div>
      <div className="community-mode-indicator"><span>EXECUTION MODE</span><strong>SIMULATOR ONLY</strong></div>
      <button className="community-publish-toggle" type="button" aria-expanded={showPublish} onClick={() => setShowPublish(value => !value)}>
        <span aria-hidden="true">{showPublish ? '−' : '+'}</span>{showPublish ? 'Close publisher' : 'Publish research'}
      </button>
    </div>
    <section className="workspace-panel community-catalog">
      <div className="community-catalog-heading">
        <div><span className="community-kicker">{showFavorites ? 'PERSONAL SAVED SET' : 'SHARED RESEARCH INDEX'}</span><h2>{showFavorites ? 'Saved strategies' : 'Strategy catalog'}</h2></div>
        <span className="community-result-count">{listLoading ? 'UPDATING…' : `${items.length} ${items.length === 1 ? 'ENTRY' : 'ENTRIES'}`}</span>
      </div>
      <div className="community-filter-grid">
        <input className="workspace-search" aria-label="Search strategies" placeholder="Search strategy name or description" value={query} onChange={event => setQuery(event.target.value)} />
        <select className="workspace-search" aria-label="Filter strategy type" value={strategyKey} onChange={event => setStrategyKey(event.target.value)}>
          <option value="">All strategy types</option>
          {['momentum','breakout','trend_following','mean_reversion','reversal'].map(value => <option key={value} value={value}>{value.replaceAll('_',' ')}</option>)}
        </select>
        <button className="table-action community-saved-toggle" aria-pressed={showFavorites} onClick={() => setShowFavorites(value => !value)}>{showFavorites ? 'All strategies' : 'Saved strategies'}</button>
        <input className="workspace-search" aria-label="Filter by asset" placeholder="Asset (BTCUSDT)" value={assetFilter} onChange={event => setAssetFilter(event.target.value)} />
        <input className="workspace-search" aria-label="Filter by timeframe" placeholder="Timeframe (15m)" value={timeframeFilter} onChange={event => setTimeframeFilter(event.target.value)} />
        <select className="workspace-search" aria-label="Sort strategies" value={sort} onChange={event => setSort(event.target.value)}>
          <option value="recent">Recently published</option><option value="updated">Recently updated</option><option value="name">Name</option>
        </select>
      </div>
      {notice && <p className="workspace-note" role="status">{notice}</p>}
      {listLoading && <p className="workspace-note" role="status">Loading community strategies…</p>}
      <div className="workspace-summary-grid community-summary-grid">
        {items.map(item => <article className="workspace-panel community-strategy" key={item.public_id}>
          <div className="community-strategy-meta">
            <span>{item.strategy_key.replaceAll('_',' ')}</span>
            <span>VERSION {item.version}</span>
            <span className="community-provenance">{item.report_provenance.replaceAll('_',' ')}</span>
          </div>
          <h3>{item.name}</h3>
          <p className="community-strategy-description">{item.description || 'No description supplied.'}</p>
          <div className="community-tags" aria-label="Supported markets and timeframes">
            {item.supported_assets.map(asset => <span key={asset}>{asset}</span>)}
            {item.supported_timeframes.map(timeframe => <span key={timeframe}>{timeframe}</span>)}
          </div>
          <div className="community-report-grid" aria-label="Submitted backtest metrics">
            <div><span>TRADES</span><strong>{String(item.backtest_report?.total_trades ?? '—')}</strong></div>
            <div><span>WIN RATE</span><strong>{String(item.backtest_report?.win_rate_pct ?? '—')}%</strong></div>
            <div><span>NET RETURN</span><strong>{String(item.backtest_report?.net_return_pct ?? '—')}%</strong></div>
            <div><span>DRAWDOWN</span><strong>{String(item.backtest_report?.max_drawdown_pct ?? '—')}%</strong></div>
          </div>
          <p className="community-user-submitted">USER-SUBMITTED / NOT INDEPENDENTLY VERIFIED</p>
          <div className="workspace-actions">
            <button className="table-action" onClick={() => void openDetails(item)}>Inspect</button>
            {item.is_owner && <button className="table-action" onClick={() => editStrategy(item)}>Edit / new version</button>}
            <button className="table-action" disabled={pendingItemActions.has(item.public_id)} aria-pressed={item.is_favorite} onClick={() => void toggleFavorite(item)}>{pendingItemActions.has(item.public_id) ? 'Updating…' : item.is_favorite ? '★ Saved' : '☆ Save'} · {item.favorite_count}</button>
            <button className="table-action" disabled={pendingItemActions.has(item.public_id)} onClick={() => void reportItem(item)}>{pendingItemActions.has(item.public_id) ? 'Submitting…' : 'Report'}</button>
          </div>
        </article>)}
      </div>
      {!listLoading && !listFailed && !items.length && <EmptyState text={showFavorites ? 'No saved strategies yet. Save a listing to keep it here.' : 'No public strategies found. Try another filter, or publish your research.'} />}
    </section>
    {selected && <section className="workspace-panel community-detail">
      <div className="community-catalog-heading">
        <div><span className="community-kicker">LISTING INSPECTION / VERSION {selected.version}</span><h2>{selected.name}</h2></div>
        <button className="table-action" onClick={() => { detailRequestId.current += 1; setSelected(null) }}>Close inspection</button>
      </div>
      <p>{selected.description}</p>
      <p className="workspace-note">Shared report: {selected.report_provenance.replaceAll('_',' ')} · SHA-256 {selected.report_sha256 || 'not available'}. Reproducibility: {selected.reproducibility_status ?? 'NOT_REPLAYED'} · Verification: {selected.verification_status ?? 'NOT_VERIFIED'}. The digest confirms stored content integrity only; locally generated reports have not been independently replayed or verified.</p>
      <div className="community-inspection-grid">
        <details><summary>Submitted backtest summary</summary><pre className="workspace-code">{JSON.stringify(selected.backtest_report, null, 2)}</pre></details>
        <details><summary>Strategy rules</summary><pre className="workspace-code">{JSON.stringify(selected.rules, null, 2)}</pre></details>
        <details><summary>Risk configuration</summary><pre className="workspace-code">{JSON.stringify(selected.risk_configuration, null, 2)}</pre></details>
        <details><summary>Known limitations</summary><ul>{selected.known_limitations.map((item, i) => <li key={i}>{item}</li>)}</ul></details>
        <details><summary>Version history ({selected.version_history?.length ?? 0})</summary><ol>{(selected.version_history ?? []).map(version => <li key={version.version}>v{version.version} · {version.created_at ? new Date(version.created_at).toLocaleString() : 'timestamp unavailable'} · {String(version.snapshot.name ?? selected.name)}</li>)}</ol></details>
      </div>
      {selected.is_owner && <button className="table-action" onClick={() => editStrategy(selected)}>Edit / publish next version</button>}
    </section>}
    {showPublish && <section className="workspace-panel community-publisher">
      <div className="community-catalog-heading">
        <div><span className="community-kicker">{editingId ? 'VERSION WORKFLOW' : 'CONTRIBUTOR WORKFLOW'}</span><h2>{editingId ? 'Update published strategy' : 'Publish a strategy'}</h2></div>
        {editingId && <button className="table-action" type="button" onClick={() => { if (busy) return; setEditingId(null); setName(''); setShowPublish(false); setNotice('Editing cancelled.') }}>Cancel version update</button>}
      </div>
      <p className="workspace-note">Only the fields below are published. Account balances, credentials, private trades, and personal settings are not sent. Backtest metrics are marked user-submitted, not verified.</p>
      <form className="workspace-form" onSubmit={publish}>
        <label>Strategy name<input className="workspace-search" required minLength={2} maxLength={120} value={name} onChange={event => setName(event.target.value)} /></label>
        <label>Description<textarea className="workspace-search" maxLength={2000} value={description} onChange={event => setDescription(event.target.value)} /></label>
        <label>Strategy type<select className="workspace-search" value={key} onChange={event => setKey(event.target.value)}>{['momentum','breakout','trend_following','mean_reversion','reversal'].map(value => <option key={value} value={value}>{value}</option>)}</select></label>
        <label>Supported assets (comma separated)<input className="workspace-search" value={assets} onChange={event => setAssets(event.target.value)} /></label>
        <label>Supported timeframes (comma separated)<input className="workspace-search" value={timeframes} onChange={event => setTimeframes(event.target.value)} /></label>
        <label>Strategy rules (JSON)<textarea className="workspace-search" rows={4} required value={rules} onChange={event => setRules(event.target.value)} /></label>
        <label>Risk configuration (JSON)<textarea className="workspace-search" rows={3} value={risk} onChange={event => setRisk(event.target.value)} /></label>
        <label>Known limitations (one per line)<textarea className="workspace-search" rows={3} value={limitations} onChange={event => setLimitations(event.target.value)} /></label>
        <label>Local Strategy Lab report ID (optional)<input className="workspace-search" maxLength={64} value={sourceReportId} onChange={event => setSourceReportId(event.target.value)} placeholder="Paste a saved report ID to use its generated metrics" /></label>
        <label>Backtest summary (JSON, user-submitted unless a local report ID is supplied)<textarea className="workspace-search" rows={3} value={report} onChange={event => setReport(event.target.value)} /></label>
        <button className="primary-action" type="submit" disabled={busy}>{busy ? 'Publishing…' : editingId ? 'Save new strategy version' : 'Publish to public library'}</button>
      </form>
    </section>}
  </div>
}

export function DashboardScreen(props: Props) {
  const { screen, data } = props
  return (
    <section className={`workspace-screen workspace-${screen.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} aria-label={`${screen} screen`}>
      {screen === 'Markets' && <MarketScreen data={data} onSelectMarket={props.onSelectMarket} />}
      {screen === 'AI Signals' && <SignalsScreen signals={data.signals} onSelectMarket={props.onSelectMarket} />}
      {screen === 'Market Analysis' && <AnalysisScreen symbol={props.symbol} marketType={props.marketType} candles={data.analysisCandles} volumeAnalytics={data.volumeAnalytics} />}
      {screen === 'Portfolio' && <PortfolioScreen portfolio={data.portfolio} positions={data.positions} trades={data.trades} stats={data.tradeStats} onPositionAction={props.onPositionAction} />}
      {screen === 'Positions' && <PositionsScreen positions={data.positions} openOrders={data.openOrders} onPositionAction={props.onPositionAction} onManualTrade={props.onManualTrade} onCancelOrder={props.onCancelOrder} />}
      {screen === 'Trade History' && <TradeHistoryScreen trades={data.trades} stats={data.tradeStats} />}
      {screen === 'Intelligence' && <IntelligenceScreen data={data} loadState={props.intelligenceLoadState} />}
      {screen === 'Learning' && <LearningScreen data={data} />}
      {screen === 'Autonomous' && <AutonomousScreen />}
      {screen === 'Community Library' && <CommunityLibraryScreen />}
      {screen === 'Strategy Lab' && <StrategyLabScreen onRun={props.onStrategyLabRun} onCompare={props.onStrategyLabCompare} data={data} preferences={props.preferences} screen={screen} symbol={props.symbol} marketType={props.marketType} onWorkspaceLoad={props.onWorkspaceLoad} />}
      {screen === 'Risk Management' && <RiskScreen risk={data.risk} portfolio={data.portfolio} alerts={data.riskAlerts} />}
      {screen === 'Activity' && <ActivityScreen events={data.events} loadState={props.activityLoadState} />}
      {screen === 'Diagnostics' && <DiagnosticsScreen data={data} activityLoadState={props.activityLoadState} diagnostics={props.diagnostics} />}
      {screen === 'Settings' && <SettingsScreen settings={data.settings} preferences={props.preferences} onPreferencesChange={props.onPreferencesChange} onSettingsSave={props.onSettingsSave} />}
    </section>
  )
}

function AutonomousScreen() {
  const [status, setStatus] = useState<AutonomousStatus | null>(null)
  const [decisions, setDecisions] = useState<Record<string, any>[]>([])
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const refresh = async () => {
    const [next, recent] = await Promise.all([
      requestJson<AutonomousStatus>('/autonomous/status'),
      requestJson<{ decisions?: Record<string, any>[] }>('/autonomous/decisions?limit=20'),
    ])
    if (next) setStatus(next)
    if (recent?.decisions) setDecisions(recent.decisions)
  }
  useEffect(() => {
    let active = true
    const load = async () => { if (active) try { await refresh() } catch (error) { if (active) setMessage(error instanceof Error ? error.message : 'Backend status unavailable.') } }
    void load()
    const timer = window.setInterval(() => void load(), 5000)
    return () => { active = false; window.clearInterval(timer) }
  }, [])
  const control = async (enabled: boolean) => {
    setBusy(true); setMessage('')
    try {
      await mutateJson('/autonomous/control', 'POST', { enabled })
      await refresh()
      setMessage(enabled ? 'Autonomous entries resumed.' : 'New entries paused. Open positions remain monitored.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Control request failed.') }
    finally { setBusy(false) }
  }
  const testTelegram = async () => {
    setBusy(true); setMessage('')
    try { await mutateJson('/telegram/test', 'POST'); setMessage('Telegram test message delivered.') }
    catch (error) { setMessage(error instanceof Error ? error.message : 'Telegram test failed.') }
    finally { setBusy(false); void refresh() }
  }
  return <div className="autonomous-screen">
    <ScreenHeader title="Autonomous paper engine" description="Live backend status, decisions, entry controls, and monitoring. All execution uses the simulated paper account." />
    <div className="workspace-summary autonomous-status-deck">
      <SummaryCard label="MODE" value={status?.mode ?? 'Checking'} detail="Real-money execution is disabled" />
      <SummaryCard label="ENGINE" value={status?.running ? 'RUNNING' : 'STOPPED'} />
      <SummaryCard label="NEW ENTRIES" value={status?.enabled ? 'ENABLED' : 'PAUSED'} detail={status?.entry_ready ? 'Readiness checks passed' : (status?.readiness_reasons ?? ['Loading readiness']).join(', ')} />
      <SummaryCard label="MODEL" value={status?.model_available ? status.model_version ?? 'ACTIVE' : 'UNAVAILABLE'} />
      <SummaryCard label="OPEN POSITIONS" value={String(status?.open_positions ?? '—')} />
      <SummaryCard label="LEARNING" value={status?.learning?.state ?? '—'} detail={status?.learning?.last_cycle_status} />
      <SummaryCard label="TELEGRAM" value={status?.telegram?.connected ? 'CONNECTED' : status?.telegram?.configured ? 'NOT CONNECTED' : 'NOT CONFIGURED'} />
    </div>
    <section className="autonomous-controls" aria-label="Autonomous engine controls">
      <header><span>CONTROL ROOM</span><strong>Entry execution</strong><small>{status?.strategies?.length ?? 0} STRATEGIES · {status?.open_orders ?? 0} PENDING</small></header>
      <div className="workspace-actions">
        {status?.enabled ? <button className="table-action" disabled={busy} onClick={() => void control(false)}>Pause new entries</button> : <button className="primary-action" disabled={busy || !status?.entry_ready} title={!status?.entry_ready ? (status?.readiness_reasons ?? []).join(', ') : undefined} onClick={() => void control(true)}>Resume entries</button>}
        <button className="table-action" disabled={busy || !status?.telegram?.enabled} onClick={() => void testTelegram()}>Send Telegram test</button>
      </div>
      {message && <p role="status" className="settings-status">{message}</p>}
    </section>
    <section className="autonomous-plan">
      <header><span>01 / LATEST PLAN</span><strong>Decision snapshot</strong></header>
      {status?.last_decision ? <DetailCard label={`${status.last_decision.symbol ?? '—'} · ${status.last_decision.status ?? '—'}`} value={`${status.last_decision.strategy ?? '—'} ${status.last_decision.strategy_direction ?? ''} · ${status.last_decision.reason ?? ''}`} /> : <EmptyState text="No autonomous decisions recorded. The engine records validated signals, rejections, and executions as they occur." />}
    </section>
    <section className="autonomous-decisions">
      <header><span>02 / AUDIT TRAIL</span><strong>Recent decisions</strong><small>{decisions.length} RECORDS</small></header>
      <div className="autonomous-table-wrap">
        <Table minWidth={760}><TableHead labels={['TIME','ASSET','STRATEGY','DIRECTION','RESULT','REASON']} />{decisions.length ? decisions.map((item, index) => <tr key={`${item.event_id ?? item.signal_id ?? 'decision'}-${index}`}><td>{timestamp(item.timestamp ?? item.decision_time)}</td><td className="table-primary">{item.symbol ?? '—'} {item.market ?? ''}</td><td>{item.strategy ?? '—'}</td><td>{item.strategy_direction ?? '—'}</td><td>{item.status ?? '—'}</td><td>{item.reason ?? '—'}</td></tr>) : <tr><td colSpan={6}>No decisions have been persisted yet.</td></tr>}</Table>
      </div>
    </section>
  </div>
}


function StrategyLabScreen({ onRun, onCompare, data, preferences, screen, symbol: dashboardSymbol, marketType, onWorkspaceLoad }: {
  onRun: Props['onStrategyLabRun']; onCompare: Props['onStrategyLabCompare'];
  data: WorkspaceData; preferences: DashboardPreferences; screen: ScreenName;
  symbol: string; marketType: 'SPOT' | 'FUTURES'; onWorkspaceLoad: Props['onWorkspaceLoad'];
}) {
  const [dna, setDna] = useState<any>(null)
  const [dnaError, setDnaError] = useState('')
  const localDateValue = (date: Date) => {
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return date.getFullYear() + '-' + month + '-' + day
  }
  const [start, setStart] = useState(() => localDateValue(new Date(Date.now() - 60 * 86400000)))
  const [end, setEnd] = useState(() => localDateValue(new Date()))
  const [strategy, setStrategy] = useState('momentum')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [market, setMarket] = useState<'SPOT' | 'FUTURES'>('SPOT')
  const [timeframe, setTimeframe] = useState('1h')
  const [capital, setCapital] = useState('1000')
  const [risk, setRisk] = useState('1')
  const [mode, setMode] = useState('risk_pct')
  const [notional, setNotional] = useState('100')
  const [maxPosition, setMaxPosition] = useState('50')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [result, setResult] = useState<any>(null)
  const [selectedTrade, setSelectedTrade] = useState<any>(null)
  const [comparison, setComparison] = useState<any>(null)
  const [minScore, setMinScore] = useState('0')
  const [feeRate, setFeeRate] = useState('')
  const [slippage, setSlippage] = useState('')
  const [spread, setSpread] = useState('')
  const [funding, setFunding] = useState('')
  const [savedStrategies, setSavedStrategies] = useState<any[]>([])
  const [savedReports, setSavedReports] = useState<any[]>([])
  const [savedWorkspaces, setSavedWorkspaces] = useState<any[]>([])
  const [strategyName, setStrategyName] = useState('')
  const [chosenStrategyId, setChosenStrategyId] = useState('')
  const [chosenReportId, setChosenReportId] = useState('')
  const [chosenWorkspaceId, setChosenWorkspaceId] = useState('')
  const [loadedReport, setLoadedReport] = useState<any>(null)
  const [loadedWorkspace, setLoadedWorkspace] = useState<any>(null)
  const [persistenceMessage, setPersistenceMessage] = useState('')
  const reloadSaved = useCallback(async () => {
    try {
      const [strategies, reports, workspaces] = await Promise.all([
        requestJson<{ strategies?: any[] }>('/research/strategies'),
        requestJson<{ reports?: any[] }>('/research/reports'),
        requestJson<{ workspaces?: any[] }>('/research/workspaces'),
      ])
      if (!strategies || !reports || !workspaces || !Array.isArray(strategies.strategies) || !Array.isArray(reports.reports) || !Array.isArray(workspaces.workspaces)) {
        setPersistenceMessage('Saved research response was incomplete or invalid. Existing selections were kept.')
        return false
      }
      setSavedStrategies(strategies.strategies)
      setSavedReports(reports.reports)
      setSavedWorkspaces(workspaces.workspaces)
      return true
    } catch (reason) {
      setPersistenceMessage(reason instanceof Error ? reason.message : 'Saved research could not be loaded.')
      return false
    }
  }, [])
  useEffect(() => {
    const initialLoad = window.setTimeout(() => { void reloadSaved() }, 0)
    return () => window.clearTimeout(initialLoad)
  }, [reloadSaved])
  useEffect(() => {
    let active = true
    requestJson<any>('/learning/strategy-dna').then(value => { if (active) setDna(value) }).catch(error => { if (active) setDnaError(error instanceof Error ? error.message : 'Strategy DNA unavailable') })
    return () => { active = false }
  }, [])
  const saveCurrentStrategy = async () => {
    const validationError = validateBacktestInputs()
    if (validationError) { setPersistenceMessage(validationError); return }
    if (strategyName.trim().length > 120) { setPersistenceMessage('Strategy name must be 120 characters or fewer.'); return }
    try {
      const saved = await mutateJson<any>('/research/strategies', 'POST', {
        name: strategyName.trim() || strategy,
        strategy_key: strategy,
        description: 'Saved from Strategy Lab',
        tags: ['strategy-lab'],
        definition: {
          symbol: symbol.toUpperCase(), market, timeframe, sizing_mode: mode,
          initial_capital: Number(capital), risk_per_trade_pct: Number(risk),
          fixed_notional: Number(notional), max_position_pct: Number(maxPosition),
          strategy_parameters: { min_score: Number(minScore) },
          fee_rate: feeRate === '' ? null : Number(feeRate),
          slippage_bps: slippage === '' ? null : Number(slippage),
          spread_bps: spread === '' ? null : Number(spread),
          funding_rate: funding === '' ? null : Number(funding),
        },
      })
      setChosenStrategyId(saved.strategy_id)
      setPersistenceMessage('Strategy saved to the database.')
      await reloadSaved()
    } catch (reason) {
      setPersistenceMessage(reason instanceof Error ? reason.message : String(reason))
    }
  }
  const loadChosenStrategy = () => {
    const saved = savedStrategies.find(item => item.strategy_id === chosenStrategyId)
    if (!saved) { setPersistenceMessage('Choose a saved strategy first.'); return }
    const allowedStrategies = ['momentum','breakout','trend_following','mean_reversion','reversal']
    const definition = saved.definition
    if (!allowedStrategies.includes(saved.strategy_key) || !definition || typeof definition !== 'object' || Array.isArray(definition)) {
      setPersistenceMessage('This saved strategy has an unsupported key or invalid definition. Nothing was loaded.')
      return
    }
    if (typeof definition.symbol !== 'string' || !/^[A-Za-z0-9]{2,20}$/.test(definition.symbol) ||
        !['SPOT','FUTURES'].includes(definition.market) ||
        !['1m','3m','5m','15m','30m','1h','4h','1d','1w'].includes(definition.timeframe) ||
        !['risk_pct','fixed_notional'].includes(definition.sizing_mode)) {
      setPersistenceMessage('Saved strategy contains invalid market, symbol, timeframe, or sizing settings. Nothing was loaded.')
      return
    }
    const requiredNumbers = [definition.initial_capital, definition.risk_per_trade_pct, definition.fixed_notional, definition.max_position_pct]
    if (requiredNumbers.some(value => value == null || !Number.isFinite(Number(value)) || Number(value) <= 0) ||
        Number(definition.risk_per_trade_pct) > 100 || Number(definition.max_position_pct) > 100) {
      setPersistenceMessage('Saved strategy contains invalid numeric settings. Nothing was loaded.')
      return
    }
    if (!Number.isFinite(Number(definition.strategy_parameters?.min_score)) || Number(definition.strategy_parameters?.min_score) < 0) {
      setPersistenceMessage('Saved strategy contains an invalid minimum score. Nothing was loaded.')
      return
    }
    const optionalNumbers = [definition.fee_rate, definition.slippage_bps, definition.spread_bps, definition.funding_rate]
    if (optionalNumbers.some(value => value != null && !Number.isFinite(Number(value)))) {
      setPersistenceMessage('Saved strategy contains invalid optional cost assumptions. Nothing was loaded.')
      return
    }
    setStrategy(saved.strategy_key)
    setSymbol(definition.symbol)
    setMarket(definition.market)
    setTimeframe(definition.timeframe)
    setMode(definition.sizing_mode)
    setCapital(String(definition.initial_capital))
    setRisk(String(definition.risk_per_trade_pct))
    setNotional(String(definition.fixed_notional))
    setMaxPosition(String(definition.max_position_pct))
    setMinScore(String(definition.strategy_parameters.min_score))
    setFeeRate(definition.fee_rate == null ? '' : String(definition.fee_rate))
    setSlippage(definition.slippage_bps == null ? '' : String(definition.slippage_bps))
    setSpread(definition.spread_bps == null ? '' : String(definition.spread_bps))
    setFunding(definition.funding_rate == null ? '' : String(definition.funding_rate))
    setPersistenceMessage('Saved strategy configuration loaded into the form.')
  }
  const loadChosenReport = async () => {
    if (!chosenReportId) {
      setPersistenceMessage('Choose a saved report first.')
      return
    }
    try {
      const report = await requestJson<any>(`/research/reports/${encodeURIComponent(chosenReportId)}`)
      if (!report) {
        setPersistenceMessage('Unable to open this report. Check the backend connection and try again.')
        return
      }
      if (typeof report !== 'object' || report.report_id !== chosenReportId || !report.backtest_report || typeof report.backtest_report !== 'object' || Array.isArray(report.backtest_report)) {
        setPersistenceMessage('The saved report response is invalid or incomplete. The report was not opened.')
        return
      }
      setLoadedReport(report)
      setPersistenceMessage('Saved report opened.')
    } catch (reason) {
      setPersistenceMessage(reason instanceof Error ? reason.message : String(reason))
    }
  }
  const saveWorkspaceSnapshot = async () => {
    try {
      const saved = await mutateJson<any>('/research/workspaces', 'POST', {
        name: `Workspace ${new Date().toLocaleString()}`,
        schema_version: 1,
        payload: {
          screen, symbol: dashboardSymbol, marketType, preferences,
          dashboardData: data,
          strategyLab: { strategy, symbol, market, timeframe, start, end, capital, risk, mode, notional, maxPosition, minScore, feeRate, slippage, spread, funding, result, comparison },
        },
      })
      setChosenWorkspaceId(saved.workspace_id)
      setPersistenceMessage('Workspace snapshot saved.')
      await reloadSaved()
    } catch (reason) {
      setPersistenceMessage(reason instanceof Error ? reason.message : String(reason))
    }
  }
  const loadChosenWorkspace = async () => {
    if (!chosenWorkspaceId) {
      setPersistenceMessage('Choose a saved workspace first.')
      return
    }
    try {
      const workspace = await requestJson<any>(`/research/workspaces/${encodeURIComponent(chosenWorkspaceId)}`)
      if (!workspace) {
        setPersistenceMessage('Unable to restore this workspace. Check the backend connection and try again.')
        return
      }
      if (typeof workspace !== 'object' || workspace.schema_version !== 1 || !workspace.payload || typeof workspace.payload !== 'object') {
        setPersistenceMessage('Unsupported workspace schema or invalid payload. Nothing was restored.')
        return
      }
      const savedLab = workspace.payload.strategyLab
      if (savedLab != null && (typeof savedLab !== 'object' || Array.isArray(savedLab))) {
        setPersistenceMessage('Invalid Strategy Lab workspace data. Nothing was restored.')
        return
      }
      if (savedLab && typeof savedLab === 'object' && savedLab.start != null && savedLab.end != null) {
        const startTime = Date.parse(String(savedLab.start) + 'T00:00:00Z')
        const endTime = Date.parse(String(savedLab.end) + 'T00:00:00Z')
        if (!Number.isFinite(startTime) || !Number.isFinite(endTime) || startTime >= endTime) {
          setPersistenceMessage('Invalid saved backtest date range. Nothing was restored.')
          return
        }
      }
      setLoadedWorkspace(workspace)
      onWorkspaceLoad(workspace)
      if (savedLab && typeof savedLab === 'object') {
        if (typeof savedLab.strategy === 'string') setStrategy(savedLab.strategy)
        if (typeof savedLab.symbol === 'string') setSymbol(savedLab.symbol)
        if (savedLab.market === 'SPOT' || savedLab.market === 'FUTURES') setMarket(savedLab.market)
        if (typeof savedLab.timeframe === 'string') setTimeframe(savedLab.timeframe)
        for (const [key, setter] of [
          ['start', setStart], ['end', setEnd], ['capital', setCapital], ['risk', setRisk],
          ['mode', setMode], ['notional', setNotional], ['maxPosition', setMaxPosition],
          ['minScore', setMinScore], ['feeRate', setFeeRate], ['slippage', setSlippage],
          ['spread', setSpread], ['funding', setFunding],
        ] as const) {
          if (savedLab[key] != null) setter(String(savedLab[key]))
        }
        if (savedLab.result) setResult(savedLab.result)
        if (savedLab.comparison) setComparison(savedLab.comparison)
      }
      setPersistenceMessage('Workspace snapshot loaded into the dashboard.')
    } catch (reason) {
      setPersistenceMessage(reason instanceof Error ? reason.message : String(reason))
    }
  }
  const validateBacktestInputs = () => {
    const startTime = Date.parse(start + 'T00:00:00Z')
    const endTime = Date.parse(end + 'T00:00:00Z')
    if (!/^[A-Z0-9]{2,30}$/.test(symbol.trim().toUpperCase())) return 'Enter a valid market symbol using letters and numbers.'
    if (!Number.isFinite(startTime) || !Number.isFinite(endTime)) return 'Choose valid start and end dates.'
    if (startTime >= endTime) return 'The start date must be earlier than the end date.'
    const values = [capital, risk, notional, maxPosition]
    if (values.some(value => value.trim() === '' || !Number.isFinite(Number(value)) || Number(value) <= 0)) return 'Capital, risk, notional, and position limit must be valid positive numbers.'
    if (Number(risk) > 100 || Number(maxPosition) > 100) return 'Risk and maximum position percentages cannot exceed 100%.'
    if (minScore.trim() === '' || !Number.isFinite(Number(minScore)) || Number(minScore) < 0) return 'Minimum strategy score must be a non-negative number.'
    const optionalValues = [feeRate, slippage, spread]
    if (optionalValues.some(value => value !== '' && (!Number.isFinite(Number(value)) || Number(value) < 0))) return 'Fee, slippage, and spread must be non-negative numbers.'
    if (funding !== '' && (!Number.isFinite(Number(funding)) || Number(funding) < -100 || Number(funding) > 100)) return 'Funding rate must be between -100 and 100.'
    return ''
  }
  const run = async (event: FormEvent) => {
    event.preventDefault()
    if (busy) return
    const validationError = validateBacktestInputs()
    if (validationError) { setError(validationError); return }
    setBusy(true); setError(''); setResult(null); setSelectedTrade(null)
    try {
      const data = await onRun({
        strategy, symbol: symbol.toUpperCase(), market, timeframe,
        start_date: new Date(start + 'T00:00:00Z').toISOString(),
        end_date: new Date(end + 'T23:59:59Z').toISOString(),
        initial_capital: Number(capital), sizing_mode: mode,
        risk_per_trade_pct: Number(risk), fixed_notional: Number(notional),
        max_position_pct: Number(maxPosition), strategy_parameters: { min_score: Number(minScore) },
        fee_rate: feeRate === '' ? undefined : Number(feeRate),
        slippage_bps: slippage === '' ? undefined : Number(slippage),
        spread_bps: spread === '' ? undefined : Number(spread),
        funding_rate: funding === '' ? undefined : Number(funding),
      })
      setResult(data)
      await reloadSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }
  const compare = async () => {
    if (busy) return
    const validationError = validateBacktestInputs()
    if (validationError) { setError(validationError); return }
    setBusy(true); setError(''); setComparison(null)
    try {
      const compared = await onCompare({
        symbol: symbol.toUpperCase(), market, timeframe,
        start_date: new Date(start + 'T00:00:00Z').toISOString(),
        end_date: new Date(end + 'T23:59:59Z').toISOString(),
        initial_capital: Number(capital), sizing_mode: mode,
        risk_per_trade_pct: Number(risk), fixed_notional: Number(notional),
        max_position_pct: Number(maxPosition), strategy_parameters: { min_score: Number(minScore) },
        fee_rate: feeRate === '' ? undefined : Number(feeRate),
        slippage_bps: slippage === '' ? undefined : Number(slippage),
        spread_bps: spread === '' ? undefined : Number(spread),
        funding_rate: funding === '' ? undefined : Number(funding),
      })
      setComparison(compared)
      await reloadSaved()
    } catch (reason) { setError(reason instanceof Error ? reason.message : String(reason)) }
    finally { setBusy(false) }
  }
  const metrics = result?.metrics
  const curve = result?.equity_curve ?? []
  const curveValues = curve.map((point: { equity: number }) => point.equity).filter((value: number) => Number.isFinite(value))
  const curveMin = curveValues.length ? Math.min(...curveValues) : 0
  const curveMax = curveValues.length ? Math.max(...curveValues) : 1
  const curvePoints = curve.map((point: { equity: number }, index: number) => {
    const x = 8 + (index / Math.max(1, curve.length - 1)) * 584
    const y = 8 + ((curveMax - point.equity) / Math.max(1e-9, curveMax - curveMin)) * 164
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
  const primaryMetrics = [
    ['Net return', metrics?.net_return_pct == null ? '—' : pct(metrics.net_return_pct)],
    ['Max drawdown', pct(metrics?.max_drawdown_pct)],
    ['Win rate', pct(metrics?.win_rate_pct)],
    ['Profit factor', metrics?.profit_factor ?? '—'],
    ['Sharpe', metrics?.sharpe_ratio == null ? '—' : num(metrics.sharpe_ratio)?.toFixed(2) ?? '—'],
    ['Trades', String(metrics?.trade_count ?? 0)],
  ]
  const additionalMetrics = [
    ['Gross return', metrics?.gross_return_pct == null ? '—' : pct(metrics.gross_return_pct)],
    ['Exposure', pct(metrics?.exposure_pct)],
    ['Buy & hold', metrics?.benchmark_buy_hold_return_pct == null ? '—' : pct(metrics.benchmark_buy_hold_return_pct)],
    ['Average winner', money(num(metrics?.average_winning_trade))],
    ['Average loser', money(num(metrics?.average_losing_trade))],
    ['Average reward / risk', metrics?.average_reward_risk == null ? '—' : `${num(metrics.average_reward_risk)?.toFixed(2) ?? '—'}R`],
  ]
  return (
    <div className="workspace-content strategy-lab">
      <ScreenHeader title="Strategy Lab" description="Historical research · simulated execution · paper-trading compatible" />
      <div className="strategy-command-strip" aria-label="Current research configuration">
        <div><span>MODE</span><strong>HISTORICAL / PAPER</strong></div>
        <div><span>STRATEGY</span><strong>{strategy.replaceAll('_', ' ')}</strong></div>
        <div><span>MARKET</span><strong>{symbol.toUpperCase()} · {market}</strong></div>
        <div><span>WINDOW</span><strong>{start} → {end}</strong></div>
      </div>
      <section className="workspace-panel strategy-dna-panel">
        <div className="strategy-panel-heading">
          <div><span className="strategy-kicker">OBSERVED BEHAVIOR / NOT A FORECAST</span><h2>Strategy DNA</h2></div>
          <span className="strategy-panel-meta">{dna?.profiles?.length ?? '—'} PROFILES</span>
        </div>
        <p className="workspace-note">Profiles compare saved backtests with closed paper trades; they describe observed behavior and do not predict future profitability.</p>
        {dnaError && <div role="status" className="workspace-note">Strategy DNA unavailable: {dnaError}</div>}
        {!dna && !dnaError && <p className="workspace-note">Loading historical and paper-trading records…</p>}
        {dna?.profiles?.map((profile: any) => <details key={profile.strategy}>
          <summary>{profile.strategy_type} · {profile.behavioral_differences?.status ?? 'Not evaluated'} · {profile.sample_size?.historical_trades ?? 0} historical / {profile.sample_size?.current_paper_trades ?? 0} paper trades</summary>
          <div className="workspace-summary-grid">
            <SummaryCard label="HISTORICAL WIN RATE" value={profile.historical_behavior?.win_rate_pct == null ? '—' : pct(profile.historical_behavior.win_rate_pct)} />
            <SummaryCard label="PAPER WIN RATE" value={profile.current_paper_behavior?.win_rate_pct == null ? '—' : pct(profile.current_paper_behavior.win_rate_pct)} />
            <SummaryCard label="HISTORICAL DD" value={profile.historical_behavior?.max_drawdown_pct == null ? '—' : pct(profile.historical_behavior.max_drawdown_pct)} />
            <SummaryCard label="PAPER DD" value={profile.current_paper_behavior?.max_drawdown_pct == null ? '—' : pct(profile.current_paper_behavior.max_drawdown_pct)} />
          </div>
          <p className="workspace-note">Timeframes: {profile.supported_timeframes?.join(', ')} · Entry: {profile.entry_conditions} · Exit: {profile.exit_conditions}</p>
          {profile.behavioral_differences?.reasons?.map((reason: string, index: number) => <p key={index} className="workspace-note">{reason}</p>)}
          {profile.behavioral_differences?.reason && <p className="workspace-note">{profile.behavioral_differences.reason}</p>}
          <p className="workspace-note">Known limitations: {profile.known_limitations?.join(' · ')} · Last evaluated: {profile.last_evaluated_at ?? 'Not evaluated'}</p>
        </details>)}
      </section>
      <form className="workspace-form backtest-form" onSubmit={run}>
        <div className="strategy-panel-heading">
          <div><span className="strategy-kicker">RESEARCH CONFIGURATION</span><h2>Build a backtest</h2></div>
          <span className="strategy-panel-meta">NO LIVE ORDERS</span>
        </div>
        <div className="strategy-primary-grid">
          <label>Strategy<select value={strategy} onChange={e => setStrategy(e.target.value)}>{['momentum','breakout','trend_following','mean_reversion','reversal'].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Asset<input value={symbol} onChange={e => setSymbol(e.target.value)} maxLength={20} required /></label>
          <label>Market<select value={market} onChange={e => setMarket(e.target.value as 'SPOT'|'FUTURES')}><option>SPOT</option><option>FUTURES</option></select></label>
          <label>Timeframe<select value={timeframe} onChange={e => setTimeframe(e.target.value)}>{['1m','3m','5m','15m','30m','1h','4h','1d','1w'].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Start date<input type="date" value={start} onChange={e => setStart(e.target.value)} required /></label>
          <label>End date<input type="date" value={end} onChange={e => setEnd(e.target.value)} required /></label>
          <label>Starting capital<input type="number" min="1" step="any" value={capital} onChange={e => setCapital(e.target.value)} required /></label>
          <label>Position sizing<select value={mode} onChange={e => setMode(e.target.value)}><option value="risk_pct">Risk % per trade</option><option value="fixed_notional">Fixed notional</option></select></label>
        </div>
        <details className="strategy-advanced">
          <summary>Position limits &amp; execution costs <span>Risk · sizing · fees · slippage · funding</span></summary>
          <div className="strategy-advanced-grid">
            <label>Risk per trade (%)<input type="number" min="0.01" max="100" step="any" value={risk} onChange={e => setRisk(e.target.value)} /></label>
            <label>Fixed notional<input type="number" min="0.01" step="any" value={notional} onChange={e => setNotional(e.target.value)} /></label>
            <label>Max position (% equity)<input type="number" min="0.01" max="100" step="any" value={maxPosition} onChange={e => setMaxPosition(e.target.value)} /></label>
            <label>Minimum strategy score<input type="number" min="0" step="any" value={minScore} onChange={e => setMinScore(e.target.value)} /></label>
            <label>Fee rate (optional)<input type="number" min="0" step="any" placeholder="Use market default" value={feeRate} onChange={e => setFeeRate(e.target.value)} /></label>
            <label>Slippage (bps)<input type="number" min="0" step="any" placeholder="Use market default" value={slippage} onChange={e => setSlippage(e.target.value)} /></label>
            <label>Spread (bps)<input type="number" min="0" step="any" placeholder="Use market default" value={spread} onChange={e => setSpread(e.target.value)} /></label>
            <label>Funding rate per 8h (optional)<input type="number" step="any" placeholder="Futures assumption only" value={funding} onChange={e => setFunding(e.target.value)} /></label>
          </div>
        </details>
        <div className="strategy-run-actions">
          <button className="primary-action" type="submit" disabled={busy}>{busy ? 'Running backtest…' : 'Run historical backtest'}</button>
          <button className="table-action" type="button" disabled={busy} onClick={() => void compare()}>Compare all strategies</button>
          <span>Historical data · simulated fills · no live execution</span>
        </div>
      </form>
      {error && <div role="alert" className="workspace-error">{error}</div>}
      {result?.status === 'insufficient_data' && <EmptyState text={`Insufficient historical candles. Available: ${result.available_candles}; required: ${result.required_candles}. Try a wider range or another timeframe.`} />}
      {comparison?.results && <section><h2>Strategy comparison · same conditions</h2><div className="workspace-summary-grid">{comparison.results.map((item: any) => <SummaryCard key={item.strategy} label={item.strategy} value={item.metrics ? pct(item.metrics.net_return_pct) : item.status} detail={item.metrics ? `DD ${pct(item.metrics.max_drawdown_pct)} · ${item.metrics.trade_count} trades` : 'Insufficient history'} />)}</div></section>}
      {metrics && <>
        <section className="strategy-results">
          <div className="strategy-panel-heading"><div><span className="strategy-kicker">SIMULATED PERFORMANCE</span><h2>Backtest results</h2></div><span className="strategy-panel-meta">{result.trades?.length ?? 0} CLOSED TRADES</span></div>
          <div className="strategy-result-primary">{primaryMetrics.map(([label, value]) => <SummaryCard key={label} label={label} value={String(value)} />)}</div>
          <details className="strategy-extra-metrics">
            <summary>Additional metrics <span>Gross return · exposure · benchmark · average trade</span></summary>
            <div className="strategy-result-secondary">{additionalMetrics.map(([label, value]) => <SummaryCard key={label} label={label} value={String(value)} />)}</div>
          </details>
            <p className="workspace-note">Execution assumptions: next-bar open entry, conservative stop-first intrabar exit, taker fees, spread and slippage. Funding is omitted unless a rate is explicitly supplied. Research results do not guarantee future performance.</p>
            <section className="workspace-panel strategy-equity-panel"><h2>Equity curve</h2><svg viewBox="0 0 600 180" role="img" aria-label="Backtest marked-to-market equity curve" className="strategy-equity-chart"><polyline points={curvePoints} fill="none" stroke="currentColor" strokeWidth="2" /></svg><p className="workspace-note">Execution costs · fees {money(num(metrics.costs?.fees))} · spread {money(num(metrics.costs?.spread))} · slippage {money(num(metrics.costs?.slippage))} · funding {money(num(metrics.costs?.funding))}</p></section>
            <details className="strategy-trades">
              <summary>Trade ledger ({result.trades?.length ?? 0}) <span>Open the ledger to inspect fills and exit reasons</span></summary>
              <Table>
                <TableHead labels={['Trade','Side','Entry','Exit','Net P&L','Exit reason']} />
                <tbody>{(result.trades ?? []).map((trade: any) => <tr key={trade.trade_id} onClick={() => setSelectedTrade(trade)}><td>{trade.trade_id}</td><td>{trade.side}</td><td>{price(num(trade.entry_fill))}</td><td>{price(num(trade.exit_fill))}</td><td>{money(num(trade.net_pnl))}</td><td>{trade.close_reason}</td></tr>)}</tbody>
              </Table>
              {selectedTrade && <DetailCard label="Selected trade details" value={JSON.stringify(selectedTrade, null, 2)} />}
            </details>
            <details><summary>Equity curve data ({result.equity_curve?.length ?? 0} points)</summary><pre>{JSON.stringify(result.equity_curve, null, 2)}</pre></details>
        </section>
      </>}
      <details className="workspace-panel persistence-panel strategy-persistence">
        <summary className="strategy-persistence-heading">
            <span><small className="strategy-kicker">LOCAL DATABASE</small><strong>Saved research &amp; workspaces</strong></span>
            <span className="strategy-panel-meta">{savedStrategies.length} STRATEGIES · {savedReports.length} REPORTS · {savedWorkspaces.length} WORKSPACES</span>
        </summary>
        <div className="strategy-persistence-content">
            <div className="workspace-form-grid">
              <label>Strategy name<input value={strategyName} onChange={event => setStrategyName(event.target.value)} placeholder={strategy} maxLength={120} /></label>
              <button className="table-action" type="button" onClick={() => void saveCurrentStrategy()}>Save strategy definition</button>
              <label>Saved strategy<select value={chosenStrategyId} onChange={event => setChosenStrategyId(event.target.value)}><option value="">Choose saved strategy</option>{savedStrategies.map(item => <option key={item.strategy_id} value={item.strategy_id}>{item.name} · {item.strategy_key} v{item.version}</option>)}</select></label>
              <button className="table-action" type="button" disabled={!chosenStrategyId} onClick={loadChosenStrategy}>Load strategy</button>
              <label>Saved backtest report<select value={chosenReportId} onChange={event => setChosenReportId(event.target.value)}><option value="">Choose report</option>{savedReports.map(item => <option key={item.report_id} value={item.report_id}>{item.symbol} · {item.strategy_name} · {timestamp(item.created_at)}</option>)}</select></label>
              <button className="table-action" type="button" disabled={!chosenReportId} onClick={() => void loadChosenReport()}>Open report</button>
              <button className="table-action" type="button" onClick={() => void saveWorkspaceSnapshot()}>Save workspace snapshot</button>
              <label>Saved workspace<select value={chosenWorkspaceId} onChange={event => setChosenWorkspaceId(event.target.value)}><option value="">Choose workspace</option>{savedWorkspaces.map(item => <option key={item.workspace_id} value={item.workspace_id}>{item.name} · {timestamp(item.updated_at)}</option>)}</select></label>
              <button className="table-action" type="button" disabled={!chosenWorkspaceId} onClick={() => void loadChosenWorkspace()}>Restore workspace</button>
            </div>
            {persistenceMessage && <p role="status" className="workspace-note">{persistenceMessage}</p>}
            {loadedReport && <details open><summary>Saved report · {loadedReport.report_id}</summary><pre>{JSON.stringify(loadedReport, null, 2)}</pre></details>}
            {loadedWorkspace && <details><summary>Restored workspace data</summary><pre>{JSON.stringify({name: loadedWorkspace.name, updated_at: loadedWorkspace.updated_at, schema_version: loadedWorkspace.schema_version, payload: loadedWorkspace.payload}, null, 2)}</pre></details>}
        </div>
      </details>
    </div>
  )
}
