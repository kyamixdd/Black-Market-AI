import { Children, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

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

export type WorkspaceData = {
  markets: WorkspaceMarket[]
  signals: WorkspaceSignal[]
  portfolio: WorkspacePortfolio | null
  positions: WorkspacePosition[]
  trades: WorkspaceTrade[]
  tradeStats: WorkspaceTradeStats | null
  strategies: WorkspaceStrategy[]
  strategyWeights: Record<string, unknown>
  predictions: WorkspacePrediction[]
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

function ScreenHeader({ title, description, actions }: { title: string; description: string; actions?: ReactNode }) {
  return (
    <div className="workspace-header">
      <div><h1>{title}</h1><p>{description}</p></div>
      {actions && <div className="workspace-actions">{actions}</div>}
    </div>
  )
}

function SummaryCard({ label, value, detail, tone }: { label: string; value: string; detail?: string; tone?: string }) {
  return <div className="workspace-summary-card"><span>{label}</span><strong className={tone}>{value}</strong>{detail && <small>{detail}</small>}</div>
}

function EmptyState({ text }: { text: string }) {
  return <div className="workspace-empty">{text}</div>
}

function DetailCard({ label, value }: { label: string; value: string }) {
  return <div className="workspace-detail"><span>{label}</span><b>{value}</b></div>
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
}: {
  position: WorkspacePosition
  onClose: () => void
}) {
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
    </section>
  )
}

function Table({ children, minWidth = 720 }: { children: ReactNode; minWidth?: number }) {
  const [header, ...rows] = Children.toArray(children)
  return <div className="workspace-table-wrap"><table style={{ minWidth }}><thead>{header}</thead><tbody>{rows}</tbody></table></div>
}

function TableHead({ labels }: { labels: string[] }) {
  return <tr>{labels.map((label) => <th key={label}>{label}</th>)}</tr>
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
          <TableHead labels={['SYMBOL', 'MARKET', 'LAST PRICE', '24H CHANGE', '24H QUOTE VOL', 'SPREAD', 'BOOK IMBALANCE', 'REGIME', 'ACTION']} />
          {markets.slice(0, 1000).map((market, index) => (
            <tr key={`${market.market}-${market.symbol}-${index}`}>
              <td className="table-primary">{market.symbol ?? '—'}</td><td>{market.market ?? '—'}</td>
              <td>{price(num(market.price))}</td>
              <td className={(market.price_change_24h ?? 0) >= 0 ? 'positive' : 'negative'}>{pct(num(market.price_change_24h))}</td>
              <td>{compact(num(market.volume_24h))}</td>
              <td>{market.bid_ask_spread == null ? '—' : `${market.bid_ask_spread.toFixed(2)} bps`}</td>
              <td>{market.orderbook_imbalance == null ? '—' : market.orderbook_imbalance.toFixed(3)}</td>
              <td>{market.regime ?? '—'}</td>
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

function AnalysisScreen({ symbol, marketType, candles }: { symbol: string; marketType: string; candles: WorkspaceData['analysisCandles'] }) {
  return (
    <>
      <ScreenHeader title="Market Analysis" description={`${symbol} · ${marketType} · technical readings computed from loaded Binance public candles across configured intervals`} />
      <div className="workspace-summary"><SummaryCard label="SYMBOL" value={symbol} /><SummaryCard label="MARKET" value={marketType} /><SummaryCard label="TIMEFRAMES" value="9" detail="1m → 1w" /><SummaryCard label="ANALYSIS" value="DESCRIPTIVE" detail="Not a forecast" /></div>
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

function PortfolioScreen({ portfolio, positions, trades, stats }: { portfolio: WorkspacePortfolio | null; positions: WorkspacePosition[]; trades: WorkspaceTrade[]; stats: WorkspaceTradeStats | null }) {
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
      {selectedPosition && <PositionInspector position={selectedPosition} onClose={() => setSelectedPosition(null)} />}
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

function PositionsScreen({ positions }: { positions: WorkspacePosition[] }) {
  const [selectedPosition, setSelectedPosition] = useState<WorkspacePosition | null>(null)
  return (
    <>
      <ScreenHeader title="Positions" description="Open simulated exposure across separate Spot and Futures paper accounts" />
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
      {selectedPosition && <PositionInspector position={selectedPosition} onClose={() => setSelectedPosition(null)} />}
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

function LearningScreen({ data }: { data: WorkspaceData }) {
  const promotions = data.events.filter((event) => ['MODEL_PROMOTED', 'MODEL_ROLLED_BACK', 'MODEL_TRAINED'].includes(event.event_type ?? ''))
  return (
    <>
      <ScreenHeader title="Learning" description="Local model status, predictions, outcomes, and persisted promotion or rollback events" />
      <div className="workspace-summary"><SummaryCard label="MODEL STATUS" value={data.learning?.model_status ?? 'Unavailable'} /><SummaryCard label="ACTIVE VERSION" value={data.learning?.version ?? '—'} /><SummaryCard label="PREDICTIONS" value={String(data.learning?.predictions_total ?? '—')} /><SummaryCard label="RESOLVED" value={String(data.learning?.predictions_resolved ?? '—')} /><SummaryCard label="MEASURED ACCURACY" value={data.learning?.accuracy == null ? '—' : `${data.learning.accuracy.toFixed(2)}%`} detail="Resolved outcomes only" /></div>
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
}: {
  settings: WorkspaceSettings | null
  preferences: DashboardPreferences
  onPreferencesChange: (preferences: DashboardPreferences) => void
}) {
  const updatePreference = (key: keyof DashboardPreferences) => onPreferencesChange({ ...preferences, [key]: !preferences[key] })
  return (
    <>
      <ScreenHeader title="Settings" description="Dashboard preferences are stored locally. Engine configuration is reported read-only; edits require changing local configuration and restarting." />
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
      <h2 className="workspace-section-title">Engine configuration · read-only</h2>
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
      <div className="workspace-note">Risk controls and notification credentials are not editable in this dashboard. Configure Telegram secrets only through the private local environment file. Binance public market data requires no API credentials; real trading is disabled.</div>
    </>
  )
}

export function DashboardScreen(props: Props) {
  const { screen, data } = props
  return (
    <section className={`workspace-screen workspace-${screen.toLowerCase().replace(/[^a-z0-9]+/g, '-')}`} aria-label={`${screen} screen`}>
      {screen === 'Markets' && <MarketScreen data={data} onSelectMarket={props.onSelectMarket} />}
      {screen === 'AI Signals' && <SignalsScreen signals={data.signals} onSelectMarket={props.onSelectMarket} />}
      {screen === 'Market Analysis' && <AnalysisScreen symbol={props.symbol} marketType={props.marketType} candles={data.analysisCandles} />}
      {screen === 'Portfolio' && <PortfolioScreen portfolio={data.portfolio} positions={data.positions} trades={data.trades} stats={data.tradeStats} />}
      {screen === 'Positions' && <PositionsScreen positions={data.positions} />}
      {screen === 'Trade History' && <TradeHistoryScreen trades={data.trades} stats={data.tradeStats} />}
      {screen === 'Intelligence' && <IntelligenceScreen data={data} />}
      {screen === 'Learning' && <LearningScreen data={data} />}
      {screen === 'Risk Management' && <RiskScreen risk={data.risk} portfolio={data.portfolio} alerts={data.riskAlerts} />}
      {screen === 'Activity' && <ActivityScreen events={data.events} />}
      {screen === 'Settings' && <SettingsScreen settings={data.settings} preferences={props.preferences} onPreferencesChange={props.onPreferencesChange} />}
    </section>
  )
}
