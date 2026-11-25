// Market breadth panel: cached eligible listings, separated by market.
import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';

interface MarketBreadth {
  advancing: number;
  declining: number;
  neutral: number;
  sample_size: number;
  advance_pct: number | null;
  decline_pct: number | null;
  neutral_pct: number | null;
  advance_decline_ratio: number | null;
  total_quote_volume_24h: number | null;
  status: string;
}
interface BreadthData {
  markets: Record<string, MarketBreadth>;
  sample_size: number;
  scope: string;
  total_quote_volume_24h: number | null;
  avg_spread_bps: number | null;
  avg_orderbook_imbalance: number | null;
  spread_status?: string;
  orderbook_status?: string;
}

const money = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value) ? 'Unavailable'
    : value >= 1e9 ? `$${(value / 1e9).toFixed(2)}B`
      : value >= 1e6 ? `$${(value / 1e6).toFixed(2)}M`
        : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export const MarketBreadthPanel: React.FC = () => {
  const [data, setData] = useState<BreadthData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const mounted = useRef(false);

  const fetchData = async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const payload = await api.getBreadth() as BreadthData;
      if (!payload || typeof payload !== 'object' || !payload.markets || typeof payload.markets !== 'object') {
        throw new Error('Breadth service returned invalid data');
      }
      if (mounted.current) {
        setData(payload);
        setError(null);
      }
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : 'Breadth data unavailable');
    } finally {
      requestInFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    const initialFetch = window.setTimeout(() => { void fetchData(); }, 0);
    const interval = setInterval(() => void fetchData(), 30000);
    return () => {
      mounted.current = false;
      clearTimeout(initialFetch);
      clearInterval(interval);
    };
  }, []);

  if (loading) return <div className="panel h-64 flex items-center justify-center"><div className="spinner" /></div>;
  if (!data) return <div className="panel p-3 sm:p-4 min-w-0"><div className="panel-header">Market Breadth</div><p className="text-sm text-muted my-3" role={error ? 'alert' : 'status'}>{error || 'Market breadth unavailable'}</p><button type="button" className="btn-ghost text-sm" onClick={() => { setLoading(true); void fetchData(); }}>Retry</button></div>;

  const renderMarket = (name: string, item?: MarketBreadth) => {
    if (!item || item.status !== 'READY') return <div className="metric-card"><div className="metric-label">{name}</div><div className="metric-value">Unavailable</div><div className="text-xs text-muted">No valid ticker sample</div></div>;
    const total = item.sample_size;
    return <div className="metric-card space-y-2">
      <div className="metric-label">{name} · {total} listings</div>
      <div className="flex justify-between text-xs"><span className="text-green-400">Adv {item.advancing}</span><span className="text-gray-400">Flat {item.neutral}</span><span className="text-red-400">Dec {item.declining}</span></div>
      <div className="h-3 rounded overflow-hidden bg-gray-800 flex">
        <div className="h-full bg-green-500" style={{ width: `${Math.min(100, Math.max(0, item.advance_pct ?? 0))}%` }} />
        <div className="h-full bg-gray-500" style={{ width: `${Math.min(100, Math.max(0, item.neutral_pct ?? 0))}%` }} />
        <div className="h-full bg-red-500" style={{ width: `${Math.min(100, Math.max(0, item.decline_pct ?? 0))}%` }} />
      </div>
      <div className="text-xs text-muted">24h quote volume: {money(item.total_quote_volume_24h)}</div>
    </div>;
  };

  return <div className="panel h-full min-w-0">
    <div className="panel-header">Market Breadth</div>
    <div className="p-3 sm:p-4 space-y-3 min-w-0">
      <p className="text-xs text-muted">{data.scope}. This is ticker breadth, not order-book depth.</p>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {renderMarket('Spot', data.markets?.SPOT)}
        {renderMarket('USDⓈ-M Futures', data.markets?.FUTURES)}
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 border-t border-gray-700 min-w-0">
        <div className="metric-card"><div className="metric-label">Sampled listings</div><div className="metric-value">{data.sample_size}</div></div>
        <div className="metric-card"><div className="metric-label">Combined quote volume</div><div className="metric-value text-lg">{money(data.total_quote_volume_24h)}</div><div className="text-xs text-muted">Spot + Futures listing totals</div></div>
        <div className="metric-card"><div className="metric-label">Average spread</div><div className="metric-value">{data.avg_spread_bps == null ? 'Unavailable' : `${data.avg_spread_bps.toFixed(1)} bps`}</div><div className="text-xs text-muted">{data.spread_status}</div></div>
        <div className="metric-card"><div className="metric-label">Order-book imbalance</div><div className="metric-value">{data.avg_orderbook_imbalance == null ? 'Unavailable' : data.avg_orderbook_imbalance.toFixed(3)}</div><div className="text-xs text-muted">{data.orderbook_status}</div></div>
      </div>
      {error && <p className="text-xs text-amber-400">Last refresh failed: {error}</p>}
    </div>
  </div>;
};

export default MarketBreadthPanel;
