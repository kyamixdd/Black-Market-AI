import { useEffect, useMemo, useState } from 'react'
import type { FormEvent } from 'react'
import { mutateJson, requestJson } from '../services/backendClient'
import { DataTable as Table, DetailCard, EmptyState, ScreenHeader, SummaryCard, TableHead } from '../components/ui/TerminalPrimitives'

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
  | 'Strategy Lab'
  | 'Community Library'
  | 'Risk Management'
  | 'Activity'
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

type Props = {
  screen: ScreenName
  symbol: string
  marketType: 'SPOT' | 'FUTURES'
  data: WorkspaceData
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
    <>
      <ScreenHeader title="Positions" description="Open simulated exposure across separate Spot and Futures paper accounts" />
      <section className="workspace-inspector" aria-label="Manual paper trade">
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
      <section className="workspace-inspector" aria-label="Open limit orders">
        <div className="workspace-inspector-heading"><strong>OPEN LIMIT ORDERS</strong><span>{openOrders.length} pending</span></div>
        {openOrders.length ? <Table minWidth={720}>
          <TableHead labels={['ORDER ID', 'ASSET', 'MARKET', 'SIDE', 'LIMIT PRICE', 'QUANTITY', 'STATUS', 'ACTION']} />
          {openOrders.map((order) => <tr key={order.order_id}>
            <td>{order.order_id ?? '—'}</td><td className="table-primary">{order.symbol ?? '—'}</td><td>{order.market ?? '—'}</td><td>{order.side ?? '—'}</td><td>{price(num(order.entry_price))}</td><td>{num(order.amount)?.toPrecision(6) ?? '—'}</td><td>{order.status ?? '—'}</td>
            <td><button className="table-action" disabled={!order.order_id || order.status !== 'OPEN'} onClick={async () => {
              if (!order.order_id || !window.confirm(`Cancel paper limit order ${order.order_id}?`)) return
              try { await onCancelOrder(order.order_id) } catch (error) { window.alert(error instanceof Error ? error.message : 'Cancellation failed.') }
            }}>Cancel order</button></td>
          </tr>)}
        </Table> : <EmptyState text="No open paper limit orders." />}
      </section>
      <div className="workspace-summary"><SummaryCard label="OPEN POSITIONS" value={String(positions.length)} /><SummaryCard label="SPOT" value={String(positions.filter((position) => position.market === 'SPOT').length)} /><SummaryCard label="FUTURES" value={String(positions.filter((position) => position.market === 'FUTURES').length)} /><SummaryCard label="UNREALIZED P&L" value={money(positions.reduce((total, position) => total + (position.unrealized_pnl ?? 0), 0))} /></div>
      {positions.length ? <Table minWidth={1200}>
        <TableHead labels={['POSITION', 'ASSET', 'ACCOUNT', 'SIDE', 'ENTRY PRICE', 'CURRENT PRICE', 'AMOUNT', 'LEVERAGE', 'UNREALIZED P&L', 'STOP LOSS', 'TAKE PROFIT', 'LIQ. PRICE', 'MARGIN RATIO', 'OPENED', 'ACTION']} />
        {positions.map((position, index) => <tr key={position.position_id ?? index}>
          <td>{position.position_id ?? '—'}</td><td className="table-primary">{position.symbol ?? '—'}</td><td>{position.market ?? '—'}</td><td>{position.side ?? '—'}</td>
          <td>{price(num(position.entry_price))}</td><td>{price(num(position.current_price))}</td><td>{num(position.amount)?.toPrecision(6) ?? '—'}</td><td>{position.leverage ?? '—'}x</td>
          <td className={(position.unrealized_pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(position.unrealized_pnl))}</td>
          <td>{price(num(position.stop_loss ?? undefined))}</td><td>{price(num(position.take_profit ?? undefined))}</td><td>{price(num(position.liquidation_price ?? undefined))}</td>
          <td>{position.margin_ratio == null ? '—' : `${(position.margin_ratio * 100).toFixed(2)}%`}</td><td>{timestamp(position.opened_at)}</td>
          <td><button className="table-action" onClick={() => setSelectedPosition(position)}>Inspect</button></td>
        </tr>)}
      </Table> : <EmptyState text="No open positions in the paper simulator." />}
      {selectedPosition && <PositionInspector position={selectedPosition} onClose={() => setSelectedPosition(null)} onPositionAction={onPositionAction} />}
    </>
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
      {filteredTrades.length ? <Table minWidth={1150}>
        <TableHead labels={['POSITION ID', 'ASSET', 'ACCOUNT', 'SIDE', 'ENTRY', 'EXIT', 'AMOUNT', 'LEVERAGE', 'NET P&L', 'P&L %', 'FEES', 'STRATEGY', 'EXIT REASON', 'OPENED', 'CLOSED']} />
        {filteredTrades.map((trade, index) => <tr key={trade.position_id ?? index}>
          <td>{trade.position_id ?? '—'}</td><td className="table-primary">{trade.symbol ?? '—'}</td><td>{trade.market ?? '—'}</td><td>{trade.side ?? '—'}</td>
          <td>{price(num(trade.entry_price))}</td><td>{price(num(trade.exit_price))}</td><td>{num(trade.amount)?.toPrecision(6) ?? '—'}</td><td>{trade.leverage ?? '—'}x</td>
          <td className={(trade.pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(trade.pnl))}</td><td>{pct(num(trade.pnl_pct))}</td><td>{money(num(trade.fee))}</td>
          <td>{trade.strategy ?? '—'}</td><td>{trade.close_reason ?? '—'}</td><td>{timestamp(trade.opened_at)}</td><td>{timestamp(trade.closed_at)}</td>
        </tr>)}
      </Table> : <EmptyState text="No persisted closed trades are available." />}
      <div className="workspace-note">Performance metrics are based on recorded paper trades only; no historical performance is estimated or fabricated.</div>
    </>
  )
}

function IntelligenceScreen({ data }: { data: WorkspaceData }) {
  const regimes = useMemo(() => {
    const counts = new Map<string, number>()
    for (const market of data.markets) {
      const regime = market.regime ?? 'UNKNOWN'
      counts.set(regime, (counts.get(regime) ?? 0) + 1)
    }
    return [...counts].sort((a, b) => b[1] - a[1])
  }, [data.markets])
  return (
    <>
      <ScreenHeader title="Intelligence" description="Observed market regimes and persisted strategy evaluation; decision rationale is shown only when recorded" />
      <h2 className="workspace-section-title">Observed regimes</h2>
      {regimes.length ? <div className="workspace-summary">{regimes.map(([regime, count]) => <SummaryCard key={regime} label={regime} value={String(count)} detail="ticker snapshots" />)}</div> : <EmptyState text="Market regime snapshots unavailable." />}
      <h2 className="workspace-section-title">Strategy evaluations</h2>
      {data.strategies.length ? <Table minWidth={850}>
        <TableHead labels={['STRATEGY', 'MARKET', 'SIGNALS', 'VALIDATED', 'WINS', 'LOSSES', 'WIN RATE', 'NET P&L', 'PROFIT FACTOR', 'WEIGHT']} />
        {data.strategies.map((strategy, index) => <tr key={`${strategy.market}-${strategy.strategy}-${index}`}>
          <td className="table-primary">{strategy.strategy ?? '—'}</td><td>{strategy.market ?? '—'}</td><td>{strategy.total_signals ?? '—'}</td><td>{strategy.validated_signals ?? '—'}</td>
          <td>{strategy.winning_trades ?? '—'}</td><td>{strategy.losing_trades ?? '—'}</td><td>{strategy.win_rate == null ? '—' : `${strategy.win_rate.toFixed(1)}%`}</td>
          <td className={(strategy.total_pnl ?? 0) >= 0 ? 'positive' : 'negative'}>{money(num(strategy.total_pnl))}</td><td>{strategy.profit_factor == null ? '—' : strategy.profit_factor.toFixed(2)}</td><td>{strategy.weight == null ? '—' : strategy.weight.toFixed(3)}</td>
        </tr>)}
      </Table> : <EmptyState text="No persisted strategy performance metrics are available." />}
      <h2 className="workspace-section-title">Recent decision records</h2>
      {data.signals.length ? <Table minWidth={760}>
        <TableHead labels={['TIMESTAMP', 'ASSET', 'MARKET', 'STRATEGY', 'DECISION', 'REGIME', 'RECORDED REASONS']} />
        {data.signals.slice(0, 50).map((signal, index) => <tr key={signal.signal_id ?? index}>
          <td>{timestamp(signal.created_at)}</td><td className="table-primary">{signal.symbol ?? '—'}</td><td>{signal.market ?? '—'}</td><td>{signal.strategy ?? '—'}</td>
          <td>{signal.direction ?? '—'} · {signal.status ?? '—'}</td><td>{signal.regime ?? '—'}</td><td>{signal.reasons?.length ? signal.reasons.join('; ') : 'No rationale recorded'}</td>
        </tr>)}
      </Table> : <EmptyState text="No signal decision records are available." />}
    </>
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
  return (
    <>
      <ScreenHeader title="Learning" description="Local model status, predictions, outcomes, and persisted promotion or rollback events" />
      <div className="workspace-summary"><SummaryCard label="MODEL STATUS" value={data.learning?.model_status ?? 'Unavailable'} /><SummaryCard label="LEARNING LOOP" value={data.learning?.training_state ?? '—'} detail={data.learning?.last_cycle_status ?? 'No cycle reported'} /><SummaryCard label="ACTIVE VERSION" value={data.learning?.version ?? '—'} /><SummaryCard label="BOOTSTRAP SAMPLES" value={String(data.learning?.training_samples ?? '—')} detail="Historical labeled hourly candles" /><SummaryCard label="ONLINE UPDATES" value={String(data.learning?.river_updates ?? '—')} /><SummaryCard label="PREDICTIONS" value={String(data.learning?.predictions_total ?? '—')} /><SummaryCard label="RESOLVED" value={String(data.learning?.predictions_resolved ?? '—')} /><SummaryCard label="MEASURED ACCURACY" value={data.learning?.accuracy == null ? '—' : `${data.learning.accuracy.toFixed(2)}%`} detail="Resolved outcomes only" /></div>
      <h2 className="workspace-section-title">Model performance · evaluated data only</h2>
      <div className="workspace-summary">
        <SummaryCard label="PREDICTION ACCURACY" value={metricPercent(data.performance?.accuracy_pct)} detail={`${data.performance?.prediction_count ?? 0} resolved predictions`} />
        <SummaryCard label="PRECISION · MACRO" value={metricPercent(data.performance?.precision_macro_pct)} detail="Macro average across observed classes" />
        <SummaryCard label="RECALL · MACRO" value={metricPercent(data.performance?.recall_macro_pct)} detail="Macro average across observed classes" />
        <SummaryCard label="PROFIT FACTOR" value={data.performance?.profit_factor === 'infinite' ? '∞' : metricNumber(data.performance?.profit_factor)} detail="Gross profit / gross loss" />
        <SummaryCard label="WIN RATE" value={metricPercent(data.performance?.win_rate_pct)} detail={`${data.performance?.trade_count ?? 0} closed paper trades`} />
        <SummaryCard label="MAX DRAWDOWN" value={metricPercent(data.performance?.max_drawdown_pct)} detail="Closed-trade equity sequence" />
        <SummaryCard label="SHARPE RATIO" value={metricNumber(data.performance?.sharpe_ratio)} detail="Daily realized P&L; annualized" />
        <SummaryCard label="TRADES EVALUATED" value={String(data.performance?.trade_count ?? 0)} detail="Closed paper trades only" />
      </div>
      <div className="workspace-note">Classification metrics use resolved predictions; trading metrics use closed paper trades. Sharpe uses daily realized P&L divided by initial paper equity, annualized with √365, and is unavailable with fewer than two daily observations. Missing metrics are shown as unavailable, not zero.</div>
      <h2 className="workspace-section-title">Strategy comparison · walk-forward out-of-sample</h2>
      {data.strategyComparison?.status === 'ok' ? <>
        <div className="workspace-summary">
          <SummaryCard label="ASSET / MARKET" value={`${data.strategyComparison.symbol ?? '—'} · ${data.strategyComparison.market ?? '—'}`} detail={`${data.strategyComparison.timeframe ?? '—'} · ${data.strategyComparison.candles ?? 0} candles`} />
          <SummaryCard label="WALK-FORWARD FOLDS" value={String(data.strategyComparison.walk_forward_folds ?? 0)} detail="Expanding historical windows" />
          <SummaryCard label="TEST WINDOW" value={`${timestamp(data.strategyComparison.evaluation_start_time)} → ${timestamp(data.strategyComparison.evaluation_end_time)}`} detail="Same unseen period for all strategies" />
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
        <div className="workspace-note">{data.strategyComparison.training_policy}. Costs: {data.strategyComparison.cost_policy}. No slippage or futures funding is included. Model rows remain flat until a valid out-of-sample fold prediction is available.</div>
      </> : <EmptyState text={data.strategyComparison?.status === 'insufficient_data' ? 'Not enough closed historical candles to compare strategies.' : 'Strategy comparison will appear when historical candle data is available.'} />}
      <h2 className="workspace-section-title">Model registry · candidate / champion state</h2>
      {data.models.length ? <Table minWidth={900}>
        <TableHead labels={['VERSION', 'MODEL', 'STATUS', 'ACTIVE', 'CHAMPION', 'PARENT', 'TRAINED']} />
        {data.models.map((model, index) => <tr key={model.version ?? index}><td className="table-primary">{model.version ?? '—'}</td><td>{model.model_type ?? '—'}</td><td>{model.status ?? '—'}</td><td>{model.is_active ? 'YES' : 'NO'}</td><td>{model.is_champion ? 'YES' : 'NO'}</td><td>{model.parent_version ?? '—'}</td><td>{timestamp(model.trained_at)}</td></tr>)}
      </Table> : <EmptyState text="Model registry is empty or unavailable; no candidate or champion state is inferred." />}
      <h2 className="workspace-section-title">Prediction outcomes</h2>
      {data.predictions.length ? <Table minWidth={950}>
        <TableHead labels={['CREATED', 'ASSET', 'MARKET', 'TIMEFRAME', 'HORIZON', 'MODEL', 'PREDICTION', 'CONFIDENCE SCORE', 'OUTCOME', 'RETURN', 'SIMULATED P&L', 'CORRECT']} />
        {data.predictions.map((prediction, index) => <tr key={prediction.prediction_id ?? index}>
          <td>{timestamp(prediction.created_at)}</td><td className="table-primary">{prediction.symbol ?? '—'}</td><td>{prediction.market ?? '—'}</td><td>{prediction.timeframe ?? '—'}</td><td>{prediction.horizon_minutes == null ? '—' : `${prediction.horizon_minutes}m`}</td>
          <td>{prediction.model_version ?? '—'}</td><td>{prediction.predicted_class ?? '—'}</td><td>{prediction.confidence == null ? '—' : prediction.confidence.toFixed(3)}</td>
          <td>{prediction.actual_outcome ?? 'Pending'}</td><td>{pct(num(prediction.actual_return_pct ?? undefined))}</td><td>{money(num(prediction.simulated_pnl ?? undefined))}</td><td>{prediction.is_correct == null ? 'Pending' : prediction.is_correct ? 'YES' : 'NO'}</td>
        </tr>)}
      </Table> : <EmptyState text="No prediction history is available." />}
      <h2 className="workspace-section-title">Promotion decisions</h2>
      {promotions.length ? <Table minWidth={700}><TableHead labels={['TIMESTAMP', 'EVENT', 'MODEL / VERSION', 'DETAIL']} />{promotions.map((event, index) => <tr key={event.event_id ?? index}><td>{timestamp(event.timestamp)}</td><td>{event.event_type ?? '—'}</td><td>{String(event.payload?.version ?? event.payload?.model_version ?? '—')}</td><td>{String(event.payload?.reason ?? event.payload?.message ?? 'No additional detail recorded')}</td></tr>)}</Table> : <EmptyState text="No promotion or rollback events are recorded. Experiment registry data is not exposed by the current API." />}
      <div className="workspace-note">Confidence is a score unless the associated model and calibration metadata establish otherwise. The UI does not claim exact future prices or unverified learning improvement.</div>
    </>
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

function ActivityScreen({ events }: { events: WorkspaceEvent[] }) {
  const [filter, setFilter] = useState('')
  const filtered = events.filter((event) => !filter || `${event.event_type} ${event.source} ${event.symbol}`.toLowerCase().includes(filter.toLowerCase()))
  return (
    <>
      <ScreenHeader title="Activity" description="Recent persisted system events polled from the local application event history" actions={<input className="workspace-search" value={filter} onChange={(event) => setFilter(event.target.value)} placeholder="Filter events" aria-label="Filter events" />} />
      {filtered.length ? <Table minWidth={850}><TableHead labels={['TIMESTAMP', 'EVENT', 'SOURCE', 'ASSET', 'MARKET', 'DETAIL']} />{filtered.map((event, index) => <tr key={event.event_id ?? index}>
        <td>{timestamp(event.timestamp)}</td><td className={/ERROR|FAIL|REJECT|RISK_ALERT/i.test(event.event_type ?? '') ? 'negative' : ''}>{event.event_type ?? '—'}</td><td>{event.source ?? '—'}</td><td>{event.symbol ?? '—'}</td><td>{event.market ?? '—'}</td><td>{String(event.payload?.message ?? event.payload?.reason ?? event.payload?.status ?? '—')}</td>
      </tr>)}</Table> : <EmptyState text="No system events are available in local history." />}
      <div className="workspace-note">The API exposes persisted system events, not arbitrary process logs. Application errors remain visible in local backend logs.</div>
    </>
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
  const value = (key: keyof WorkspaceSettings) => draft[key] ?? (Array.isArray(settings?.[key]) ? (settings?.[key] as string[]).join(', ') : String(settings?.[key] ?? ''))
  const updatePreference = (key: keyof DashboardPreferences) => onPreferencesChange({ ...preferences, [key]: !preferences[key] })
  return (
    <>
      <ScreenHeader title="Settings" description="Engine settings are validated, saved locally by the backend, and applied to the running scanner and risk controls." />
      <h2 className="workspace-section-title">Dashboard preferences · this device</h2>
      <div className="settings-card-list">
        {([
          ['autoScale', 'Chart auto-scale', 'Scale price to visible candle range'],
          ['crosshair', 'Chart crosshair', 'Show crosshair and axis labels'],
          ['showRiskAlerts', 'Show risk alert badge', 'Display a badge when risk events are present'],
        ] as [keyof DashboardPreferences, string, string][]).map(([key, label, detail]) => (
          <button key={key} className="settings-card" role="switch" aria-checked={preferences[key]} onClick={() => updatePreference(key)}>
            <span><b>{label}</b><small>{detail}</small></span><i className={preferences[key] ? 'switch-on' : ''} />
          </button>
        ))}
      </div>
      <h2 className="workspace-section-title">Engine configuration · persistent</h2>
      <form className="settings-card-list" onSubmit={async (event) => {
        event.preventDefault(); setSaving(true); setMessage('')
        const payload: Record<string, unknown> = {}
        const boolKeys = ['spot_enabled','futures_enabled','scan_all_eligible_symbols','telegram_enabled']
        const numberKeys = ['spot_initial_balance','futures_initial_balance','risk_per_trade_pct','risk_max_daily_loss_pct','risk_max_total_open_pct','risk_max_leverage','max_spot_positions','max_futures_positions']
        for (const key of boolKeys) if (draft[key] !== undefined) payload[key] = draft[key] === 'true'
        for (const key of numberKeys) if (draft[key] !== undefined && draft[key] !== '') payload[key] = Number(draft[key])
        if (draft.timeframes !== undefined) payload.timeframes = draft.timeframes.split(',').map((item) => item.trim()).filter(Boolean)
        try { await onSettingsSave(payload); setDraft({}); setMessage('Settings saved and applied.') }
        catch (error) { setMessage(error instanceof Error ? error.message : 'Settings could not be saved.') }
        finally { setSaving(false) }
      }}>
        <label className="settings-card"><span><b>Spot market data</b><small>Enable or pause Spot scanning</small></span><select className="workspace-select" value={value('spot_enabled')} onChange={(event) => setDraft((state) => ({ ...state, spot_enabled: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
        <label className="settings-card"><span><b>USDⓈ-M Futures</b><small>Enable or pause Futures scanning</small></span><select className="workspace-select" value={value('futures_enabled')} onChange={(event) => setDraft((state) => ({ ...state, futures_enabled: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
        <label className="settings-card"><span><b>Scan broader symbol set</b><small>Uses up to 50 high-volume eligible symbols per market</small></span><select className="workspace-select" value={value('scan_all_eligible_symbols')} onChange={(event) => setDraft((state) => ({ ...state, scan_all_eligible_symbols: event.target.value }))}><option value="true">Enabled</option><option value="false">Top 10</option></select></label>
        <label className="settings-card"><span><b>Analysis timeframes</b><small>Comma-separated Binance intervals</small></span><input className="workspace-search" value={value('timeframes')} onChange={(event) => setDraft((state) => ({ ...state, timeframes: event.target.value }))} /></label>
        {(['spot_initial_balance','futures_initial_balance','risk_per_trade_pct','risk_max_daily_loss_pct','risk_max_total_open_pct','risk_max_leverage','max_spot_positions','max_futures_positions'] as const).map((key) => <label className="settings-card" key={key}><span><b>{key.replaceAll('_',' ').toUpperCase()}</b></span><input className="workspace-search" type="number" min="0.01" step="any" value={value(key)} onChange={(event) => setDraft((state) => ({ ...state, [key]: event.target.value }))} /></label>)}
        <label className="settings-card"><span><b>Telegram notifications</b><small>Uses credentials already configured in the private environment</small></span><select className="workspace-select" value={value('telegram_enabled')} onChange={(event) => setDraft((state) => ({ ...state, telegram_enabled: event.target.value }))}><option value="true">Enabled</option><option value="false">Disabled</option></select></label>
        <button className="table-action" type="submit" disabled={saving || !Object.keys(draft).length}>{saving ? 'Saving…' : 'Save engine settings'}</button>
        {message && <span role="status">{message}</span>}
      </form>
      <div className="workspace-summary">
        <SummaryCard label="SPOT MARKET DATA" value={settings ? settings.spot_enabled ? 'ENABLED' : 'DISABLED' : 'Unavailable'} />
        <SummaryCard label="USDⓈ-M FUTURES" value={settings ? settings.futures_enabled ? 'ENABLED' : 'DISABLED' : 'Unavailable'} />
        <SummaryCard label="MARKET SCANNING" value={settings ? settings.scan_all_eligible_symbols ? 'ALL ELIGIBLE' : 'CONFIGURED SET' : 'Unavailable'} />
        <SummaryCard label="SPOT PAPER CAPITAL" value={money(num(settings?.spot_initial_balance))} />
        <SummaryCard label="FUTURES PAPER CAPITAL" value={money(num(settings?.futures_initial_balance))} />
        <SummaryCard label="TELEGRAM" value={settings ? settings.telegram_enabled ? 'ENABLED' : 'DISABLED' : 'Unavailable'} detail={settings?.telegram_enabled ? `Token ${settings.telegram_bot_token_configured ? 'configured' : 'missing'} · chat ${settings.telegram_chat_id_configured ? 'configured' : 'missing'}` : 'No credentials are exposed'} />
      </div>
      <h2 className="workspace-section-title">Risk controls · read-only</h2>
      <div className="workspace-summary">
        <SummaryCard label="RISK / TRADE" value={settings?.risk_per_trade_pct == null ? '—' : `${settings.risk_per_trade_pct}%`} />
        <SummaryCard label="MAX DAILY LOSS" value={settings?.risk_max_daily_loss_pct == null ? '—' : `${settings.risk_max_daily_loss_pct}%`} />
        <SummaryCard label="MAX OPEN RISK" value={settings?.risk_max_total_open_pct == null ? '—' : `${settings.risk_max_total_open_pct}%`} />
        <SummaryCard label="FUTURES LEVERAGE" value={settings?.risk_max_leverage == null ? '—' : `${settings.risk_max_leverage}x`} />
        <SummaryCard label="POSITION LIMITS" value={settings ? `${settings.max_spot_positions ?? '—'} Spot / ${settings.max_futures_positions ?? '—'} Futures` : '—'} />
        <SummaryCard label="TIMEFRAMES" value={settings?.timeframes?.length ? settings.timeframes.join(', ') : '—'} />
      </div>
      <div className="workspace-note">Telegram credentials remain secret and cannot be changed here. Starting balances can only be changed before the first paper trade. Real exchange trading remains disabled.</div>
    </>
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
  const [query, setQuery] = useState('')
  const [strategyKey, setStrategyKey] = useState('')
  const [assetFilter, setAssetFilter] = useState('')
  const [timeframeFilter, setTimeframeFilter] = useState('')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [showFavorites, setShowFavorites] = useState(false)
  const [sort, setSort] = useState('recent')
  const [selected, setSelected] = useState<CommunityStrategy | null>(null)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
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

  const load = async () => {
    const params = new URLSearchParams({ q: query, sort, limit: '50' })
    if (strategyKey) params.set('strategy_key', strategyKey)
    if (assetFilter) params.set('asset', assetFilter.toUpperCase())
    if (timeframeFilter) params.set('timeframe', timeframeFilter)
    const result = await requestJson<{ strategies: CommunityStrategy[] }>(showFavorites ? '/community/favorites' : `/community/strategies?${params.toString()}`)
    if (result) setItems(result.strategies ?? [])
  }
  useEffect(() => { void load() }, [query, strategyKey, assetFilter, timeframeFilter, sort, showFavorites])

  const publish = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setNotice('')
    try {
      const payload = {
        name, description, strategy_key: key,
        supported_assets: assets.split(',').map(value => value.trim()).filter(Boolean),
        supported_timeframes: timeframes.split(',').map(value => value.trim()).filter(Boolean),
        rules: JSON.parse(rules), risk_configuration: JSON.parse(risk),
        known_limitations: limitations.split('\n').map(value => value.trim()).filter(Boolean),
        backtest_report: JSON.parse(report),\n        ...(sourceReportId.trim() ? { source_report_id: sourceReportId.trim() } : {}),
      }
      await mutateJson(editingId ? `/community/strategies/${editingId}` : '/community/strategies', editingId ? 'PUT' : 'POST', payload)
      setNotice(editingId ? 'Published strategy version updated.' : 'Strategy published. Shared performance is labelled user-submitted.')
      setEditingId(null)
      setName('')
      await load()
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to publish strategy.')
    } finally {
      setBusy(false)
    }
  }

  const openDetails = async (item: CommunityStrategy) => {
    const detail = await requestJson<CommunityStrategy>(`/community/strategies/${item.public_id}`)
    if (detail) setSelected(detail)
  }

  const editStrategy = (item: CommunityStrategy) => {
    setEditingId(item.public_id)
    setName(item.name)
    setDescription(item.description)
    setKey(item.strategy_key)
    setAssets(item.supported_assets.join(', '))
    setTimeframes(item.supported_timeframes.join(', '))
    setRules(JSON.stringify(item.rules, null, 2))
    setRisk(JSON.stringify(item.risk_configuration, null, 2))
    setLimitations(item.known_limitations.join('\n'))
    setReport(JSON.stringify(item.backtest_report, null, 2))\n    setSourceReportId(item.source_report_id ?? '')
    setNotice(`Editing your published strategy. Saving creates version ${item.version + 1}.`)
  }

  const toggleFavorite = async (item: CommunityStrategy) => {
    try {
      await mutateJson(`/community/strategies/${item.public_id}/favorite`, 'POST', { favorite: !item.is_favorite })
      await load()
      if (selected?.public_id === item.public_id) setSelected({ ...selected, is_favorite: !item.is_favorite })
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to update favorite.')
    }
  }

  const reportItem = async (item: CommunityStrategy) => {
    try {
      await mutateJson(`/community/strategies/${item.public_id}/report`, 'POST', { reason: 'misleading_results', details: 'Please review this strategy listing.' })
      setNotice('Report submitted for review.')
    } catch (error) {
      setNotice(error instanceof Error ? error.message : 'Unable to report listing.')
    }
  }

  return <div className="screen-stack">
    <ScreenHeader title="Community Strategy Library" description="Browse and share strategy research · simulator-only · no live execution" />
    <p className="workspace-note">Listings are shared only with clients connected to this backend. Desktop local mode keeps its own library; it does not automatically sync to the hosted community.</p>
    <section className="workspace-panel">
      <div className="workspace-toolbar">
        <input className="workspace-search" aria-label="Search strategies" placeholder="Search strategy name or description" value={query} onChange={event => setQuery(event.target.value)} />
        <select className="workspace-search" aria-label="Filter strategy type" value={strategyKey} onChange={event => setStrategyKey(event.target.value)}>
          <option value="">All strategy types</option>
          {['momentum','breakout','trend_following','mean_reversion','reversal'].map(value => <option key={value} value={value}>{value.replaceAll('_',' ')}</option>)}
        </select>
        <button className="table-action" onClick={() => setShowFavorites(value => !value)}>{showFavorites ? 'All strategies' : 'Saved strategies'}</button>
        <input className="workspace-search" aria-label="Filter by asset" placeholder="Asset (BTCUSDT)" value={assetFilter} onChange={event => setAssetFilter(event.target.value)} />
        <input className="workspace-search" aria-label="Filter by timeframe" placeholder="Timeframe (15m)" value={timeframeFilter} onChange={event => setTimeframeFilter(event.target.value)} />
        <select className="workspace-search" aria-label="Sort strategies" value={sort} onChange={event => setSort(event.target.value)}>
          <option value="recent">Recently published</option><option value="updated">Recently updated</option><option value="name">Name</option>
        </select>
      </div>
      {notice && <p className="workspace-note" role="status">{notice}</p>}
      <div className="workspace-summary-grid">
        {items.map(item => <article className="workspace-panel" key={item.public_id}>
          <h3>{item.name}</h3>
          <p>{item.description || 'No description supplied.'}</p>
          <p className="workspace-note">{item.strategy_key.replaceAll('_',' ')} · v{item.version} · {item.supported_timeframes.join(', ')}</p>
          <p className="workspace-note">Report provenance: <b>{item.report_provenance.replaceAll('_',' ')}</b> · {String(item.backtest_report?.total_trades ?? '—')} reported trades · win rate {String(item.backtest_report?.win_rate_pct ?? '—')}% · return {String(item.backtest_report?.net_return_pct ?? '—')}% · drawdown {String(item.backtest_report?.max_drawdown_pct ?? '—')}%</p>
          <div className="workspace-actions">
            <button className="table-action" onClick={() => void openDetails(item)}>Details</button>
            {item.is_owner && <button className="table-action" onClick={() => editStrategy(item)}>Edit / new version</button>}
            <button className="table-action" onClick={() => void toggleFavorite(item)}>{item.is_favorite ? '★ Saved' : '☆ Save'} · {item.favorite_count}</button>
            <button className="table-action" onClick={() => void reportItem(item)}>Report</button>
          </div>
        </article>)}
      </div>
      {!items.length && <EmptyState text="No public strategies found. Try a different search, or publish a strategy below." />}
    </section>
    {selected && <section className="workspace-panel">
      <div className="workspace-toolbar"><h2>{selected.name} · v{selected.version}</h2><button className="table-action" onClick={() => setSelected(null)}>Close</button></div>
      <p>{selected.description}</p>
      <p className="workspace-note">Shared report: {selected.report_provenance.replaceAll('_',' ')} · SHA-256 {selected.report_sha256 || 'not available'}. Reproducibility: {selected.reproducibility_status ?? 'NOT_REPLAYED'} · Verification: {selected.verification_status ?? 'NOT_VERIFIED'}. The digest confirms stored content integrity only; locally generated reports have not been independently replayed or verified.</p>
      <h3>Submitted backtest summary</h3><pre className="workspace-code">{JSON.stringify(selected.backtest_report, null, 2)}</pre>
      <h3>Rules</h3><pre className="workspace-code">{JSON.stringify(selected.rules, null, 2)}</pre>
      <h3>Risk configuration</h3><pre className="workspace-code">{JSON.stringify(selected.risk_configuration, null, 2)}</pre>
      <h3>Known limitations</h3><ul>{selected.known_limitations.map((item, i) => <li key={i}>{item}</li>)}</ul>
      <h3>Version history</h3><ol>{(selected.version_history ?? []).map(version => <li key={version.version}>v{version.version} · {version.created_at ? new Date(version.created_at).toLocaleString() : 'timestamp unavailable'} · {String(version.snapshot.name ?? selected.name)}</li>)}</ol>
      {selected.is_owner && <button className="table-action" onClick={() => editStrategy(selected)}>Edit / publish next version</button>}
    </section>}
    <section className="workspace-panel">
      <h2>{editingId ? 'Update published strategy' : 'Publish a strategy'}</h2>
      {editingId && <button className="table-action" type="button" onClick={() => { setEditingId(null); setName(''); setNotice('Editing cancelled.') }}>Cancel version update</button>}
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
        <label>Local Strategy Lab report ID (optional)<input className="workspace-search" maxLength={64} value={sourceReportId} onChange={event => setSourceReportId(event.target.value)} placeholder="Paste a saved report ID to use its generated metrics" /></label>\n        <label>Backtest summary (JSON, user-submitted unless a local report ID is supplied)<textarea className="workspace-search" rows={3} value={report} onChange={event => setReport(event.target.value)} /></label>
        <button className="primary-action" type="submit" disabled={busy}>{busy ? 'Publishing…' : 'Publish to public library'}</button>
      </form>
    </section>
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
      {screen === 'Intelligence' && <IntelligenceScreen data={data} />}
      {screen === 'Learning' && <LearningScreen data={data} />}
      {screen === 'Community Library' && <CommunityLibraryScreen />}
      {screen === 'Strategy Lab' && <StrategyLabScreen onRun={props.onStrategyLabRun} onCompare={props.onStrategyLabCompare} data={data} preferences={props.preferences} screen={screen} symbol={props.symbol} marketType={props.marketType} onWorkspaceLoad={props.onWorkspaceLoad} />}
      {screen === 'Risk Management' && <RiskScreen risk={data.risk} portfolio={data.portfolio} alerts={data.riskAlerts} />}
      {screen === 'Activity' && <ActivityScreen events={data.events} />}
      {screen === 'Settings' && <SettingsScreen settings={data.settings} preferences={props.preferences} onPreferencesChange={props.onPreferencesChange} onSettingsSave={props.onSettingsSave} />}
    </section>
  )
}


function StrategyLabScreen({ onRun, onCompare, data, preferences, screen, symbol: dashboardSymbol, marketType, onWorkspaceLoad }: {
  onRun: Props['onStrategyLabRun']; onCompare: Props['onStrategyLabCompare'];
  data: WorkspaceData; preferences: DashboardPreferences; screen: ScreenName;
  symbol: string; marketType: 'SPOT' | 'FUTURES'; onWorkspaceLoad: Props['onWorkspaceLoad'];
}) {
  const [dna, setDna] = useState<any>(null)
  const [dnaError, setDnaError] = useState('')
  const [strategy, setStrategy] = useState('momentum')
  const [symbol, setSymbol] = useState('BTCUSDT')
  const [market, setMarket] = useState<'SPOT' | 'FUTURES'>('SPOT')
  const [timeframe, setTimeframe] = useState('1h')
  const [start, setStart] = useState('2026-09-15')
  const [end, setEnd] = useState('2026-11-21')
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
  const reloadSaved = async () => {
    const [strategies, reports, workspaces] = await Promise.all([
      requestJson<{ strategies?: any[] }>('/research/strategies'),
      requestJson<{ reports?: any[] }>('/research/reports'),
      requestJson<{ workspaces?: any[] }>('/research/workspaces'),
    ])
    setSavedStrategies(strategies?.strategies ?? [])
    setSavedReports(reports?.reports ?? [])
    setSavedWorkspaces(workspaces?.workspaces ?? [])
  }
  useEffect(() => { void reloadSaved() }, [])
  useEffect(() => {
    let active = true
    requestJson<any>('/learning/strategy-dna').then(value => { if (active) setDna(value) }).catch(error => { if (active) setDnaError(error instanceof Error ? error.message : 'Strategy DNA unavailable') })
    return () => { active = false }
  }, [])
  const saveCurrentStrategy = async () => {
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
    if (!saved) return
    const definition = saved.definition ?? {}
    setStrategy(saved.strategy_key)
    if (definition.symbol) setSymbol(String(definition.symbol))
    if (definition.market === 'SPOT' || definition.market === 'FUTURES') setMarket(definition.market)
    if (definition.timeframe) setTimeframe(String(definition.timeframe))
    if (definition.sizing_mode) setMode(String(definition.sizing_mode))
    if (definition.initial_capital != null) setCapital(String(definition.initial_capital))
    if (definition.risk_per_trade_pct != null) setRisk(String(definition.risk_per_trade_pct))
    if (definition.fixed_notional != null) setNotional(String(definition.fixed_notional))
    if (definition.max_position_pct != null) setMaxPosition(String(definition.max_position_pct))
    if (definition.strategy_parameters?.min_score != null) setMinScore(String(definition.strategy_parameters.min_score))
    if (definition.fee_rate != null) setFeeRate(String(definition.fee_rate))
    if (definition.slippage_bps != null) setSlippage(String(definition.slippage_bps))
    if (definition.spread_bps != null) setSpread(String(definition.spread_bps))
    if (definition.funding_rate != null) setFunding(String(definition.funding_rate))
    setPersistenceMessage('Saved strategy configuration loaded into the form.')
  }
  const loadChosenReport = async () => {
    if (!chosenReportId) return
    const report = await requestJson<any>(`/research/reports/${encodeURIComponent(chosenReportId)}`)
    if (report) setLoadedReport(report)
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
    if (!chosenWorkspaceId) return
    const workspace = await requestJson<any>(`/research/workspaces/${encodeURIComponent(chosenWorkspaceId)}`)
    if (workspace) {
      setLoadedWorkspace(workspace)
      onWorkspaceLoad(workspace)
      const savedLab = workspace.payload?.strategyLab
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
    }
  }
  const run = async (event: FormEvent) => {
    event.preventDefault()
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
  return (
    <div className="workspace-content strategy-lab">
      <ScreenHeader title="Strategy Lab" description="Historical research · simulated execution · paper-trading compatible" />
      <section className="workspace-panel">
        <h2>Strategy DNA · behavior monitoring</h2>
        <p className="workspace-note">Profiles are derived from saved backtests and closed paper trades. Diagnostics describe observed behavior only; they do not predict future profitability.</p>
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
      <form className="workspace-form" onSubmit={run}>
        <div className="workspace-form-grid">
          <label>Strategy<select value={strategy} onChange={e => setStrategy(e.target.value)}>{['momentum','breakout','trend_following','mean_reversion','reversal'].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Asset<input value={symbol} onChange={e => setSymbol(e.target.value)} maxLength={20} required /></label>
          <label>Market<select value={market} onChange={e => setMarket(e.target.value as 'SPOT'|'FUTURES')}><option>SPOT</option><option>FUTURES</option></select></label>
          <label>Timeframe<select value={timeframe} onChange={e => setTimeframe(e.target.value)}>{['1m','3m','5m','15m','30m','1h','4h','1d','1w'].map(v => <option key={v}>{v}</option>)}</select></label>
          <label>Start date<input type="date" value={start} onChange={e => setStart(e.target.value)} required /></label>
          <label>End date<input type="date" value={end} onChange={e => setEnd(e.target.value)} required /></label>
          <label>Starting capital<input type="number" min="1" step="any" value={capital} onChange={e => setCapital(e.target.value)} required /></label>
          <label>Position sizing<select value={mode} onChange={e => setMode(e.target.value)}><option value="risk_pct">Risk % per trade</option><option value="fixed_notional">Fixed notional</option></select></label>
          <label>Risk per trade (%)<input type="number" min="0.01" max="100" step="any" value={risk} onChange={e => setRisk(e.target.value)} /></label>
          <label>Fixed notional<input type="number" min="0.01" step="any" value={notional} onChange={e => setNotional(e.target.value)} /></label>
          <label>Max position (% equity)<input type="number" min="0.01" max="100" step="any" value={maxPosition} onChange={e => setMaxPosition(e.target.value)} /></label>
          <label>Minimum strategy score<input type="number" min="0" step="any" value={minScore} onChange={e => setMinScore(e.target.value)} /></label>
          <label>Fee rate (optional)<input type="number" min="0" step="any" placeholder="Use market default" value={feeRate} onChange={e => setFeeRate(e.target.value)} /></label>
          <label>Slippage (bps)<input type="number" min="0" step="any" placeholder="Use market default" value={slippage} onChange={e => setSlippage(e.target.value)} /></label>
          <label>Spread (bps)<input type="number" min="0" step="any" placeholder="Use market default" value={spread} onChange={e => setSpread(e.target.value)} /></label>
          <label>Funding rate per 8h (optional)<input type="number" step="any" placeholder="Futures assumption only" value={funding} onChange={e => setFunding(e.target.value)} /></label>
        </div>
        <button className="primary-action" type="submit" disabled={busy}>{busy ? 'Running backtest…' : 'Run historical backtest'}</button>
        <button className="table-action" type="button" disabled={busy} onClick={() => void compare()}>Compare all strategies</button>
      </form>
      {error && <div role="alert" className="workspace-error">{error}</div>}
      <section className="workspace-panel persistence-panel">
        <h2>Saved research & workspaces</h2>
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
      </section>
      {result?.status === 'insufficient_data' && <EmptyState text={`Insufficient historical candles. Available: ${result.available_candles}; required: ${result.required_candles}. Try a wider range or another timeframe.`} />}
      {comparison?.results && <section><h2>Strategy comparison · same conditions</h2><div className="workspace-summary-grid">{comparison.results.map((item: any) => <SummaryCard key={item.strategy} label={item.strategy} value={item.metrics ? pct(item.metrics.net_return_pct) : item.status} detail={item.metrics ? `DD ${pct(item.metrics.max_drawdown_pct)} · ${item.metrics.trade_count} trades` : 'Insufficient history'} />)}</div></section>}
      {metrics && <>
        <div className="workspace-summary-grid">
          {[
            ['Net return', metrics.net_return_pct == null ? '—' : pct(metrics.net_return_pct)],
            ['Gross return', metrics.gross_return_pct == null ? '—' : pct(metrics.gross_return_pct)],
            ['Max drawdown', pct(metrics.max_drawdown_pct)],
            ['Profit factor', metrics.profit_factor ?? '—'],
            ['Win rate', pct(metrics.win_rate_pct)],
            ['Sharpe', metrics.sharpe_ratio == null ? '—' : num(metrics.sharpe_ratio)?.toFixed(2) ?? '—'],
            ['Trades', String(metrics.trade_count ?? 0)],
            ['Exposure', pct(metrics.exposure_pct)],
            ['Buy & hold', metrics.benchmark_buy_hold_return_pct == null ? '—' : pct(metrics.benchmark_buy_hold_return_pct)],
            ['Average winner', money(num(metrics.average_winning_trade))],
            ['Average loser', money(num(metrics.average_losing_trade))],
            ['Average reward / risk', metrics.average_reward_risk == null ? '—' : `${num(metrics.average_reward_risk)?.toFixed(2) ?? '—'}R`],
          ].map(([label,value]) => <SummaryCard key={label} label={label} value={String(value)} />)}
        </div>
        <p className="workspace-note">Execution assumptions: next-bar open entry, conservative stop-first intrabar exit, taker fees, spread and slippage. Funding is omitted unless a rate is explicitly supplied. Research results do not guarantee future performance.</p>
        <section className="workspace-panel"><h2>Equity curve</h2><svg viewBox="0 0 600 180" role="img" aria-label="Backtest marked-to-market equity curve" className="strategy-equity-chart"><polyline points={curvePoints} fill="none" stroke="currentColor" strokeWidth="2" /></svg><p className="workspace-note">Costs · fees {money(num(metrics.costs?.fees))} · spread {money(num(metrics.costs?.spread))} · slippage {money(num(metrics.costs?.slippage))} · funding {money(num(metrics.costs?.funding))}</p></section>
        <Table>
          <TableHead labels={['Trade','Side','Entry','Exit','Net P&L','Exit reason']} />
          <tbody>{(result.trades ?? []).map((trade: any) => <tr key={trade.trade_id} onClick={() => setSelectedTrade(trade)}><td>{trade.trade_id}</td><td>{trade.side}</td><td>{price(num(trade.entry_fill))}</td><td>{price(num(trade.exit_fill))}</td><td>{money(num(trade.net_pnl))}</td><td>{trade.close_reason}</td></tr>)}</tbody>
        </Table>
        {selectedTrade && <DetailCard label="Selected trade details" value={JSON.stringify(selectedTrade, null, 2)} />}
        <details><summary>Equity curve data ({result.equity_curve?.length ?? 0} points)</summary><pre>{JSON.stringify(result.equity_curve, null, 2)}</pre></details>
      </>}
    </div>
  )
}
