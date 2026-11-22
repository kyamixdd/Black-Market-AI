// Volume analysis panel: distinguish sampled trade flow from full-day ticker volume.
import { useEffect, useState } from 'react';

interface VolumeData {
  buy_volume: number;
  sell_volume: number;
  total_volume: number | null;
  volume_change_24h: number | null;
  average_daily_quote_volume_7d: number | null;
  volume_change_vs_7d_avg_pct: number | null;
  comparison_period?: string;
  flow_sample_size?: number;
  flow_sample_scope?: string;
  flow_last_trade_time?: string | null;
  data_freshness?: string;
}

const money = (value: number | null | undefined) =>
  value == null || !Number.isFinite(value)
    ? 'Unavailable'
    : value >= 1e9 ? `$${(value / 1e9).toFixed(2)}B`
      : value >= 1e6 ? `$${(value / 1e6).toFixed(2)}M`
        : `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;

export const VolumePanel: React.FC = () => {
  const [data, setData] = useState<VolumeData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/markets/volume');
      if (!response.ok) throw new Error(`Volume API returned HTTP ${response.status}`);
      const payload: VolumeData = await response.json();
      setData(payload);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Volume data unavailable');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void fetchData();
    const interval = setInterval(() => void fetchData(), 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) return <div className="panel h-64 flex items-center justify-center"><div className="spinner" /></div>;
  if (!data) return <div className="panel p-4"><div className="panel-header">Volume Analysis</div><p className="text-sm text-muted">{error || 'Volume data unavailable'}. Retry after the market-data service reconnects.</p></div>;

  const sampledTotal = Math.max(0, data.buy_volume) + Math.max(0, data.sell_volume);
  const buyPct = sampledTotal > 0 ? data.buy_volume / sampledTotal * 100 : 0;
  const sellPct = sampledTotal > 0 ? data.sell_volume / sampledTotal * 100 : 0;
  const volumeChange = data.volume_change_vs_7d_avg_pct;

  return (
    <div className="panel h-full">
      <div className="panel-header">Volume & Trade Flow</div>
      <div className="p-4 space-y-4">
        <p className="text-xs text-muted">
          Aggressor-side quote value from {data.flow_sample_scope || 'a limited aggregate-trade sample'}.
          This is not a complete 24-hour buy/sell volume profile.
        </p>
        <div className="space-y-2">
          <div className="flex justify-between text-xs"><span className="text-green-400">Sampled buyer-initiated</span><span>{money(data.buy_volume)} · {buyPct.toFixed(1)}%</span></div>
          <div className="h-3 bg-gray-800 rounded overflow-hidden"><div className="h-full bg-green-500" style={{ width: `${buyPct}%` }} /></div>
          <div className="flex justify-between text-xs"><span className="text-red-400">Sampled seller-initiated</span><span>{money(data.sell_volume)} · {sellPct.toFixed(1)}%</span></div>
          <div className="h-3 bg-gray-800 rounded overflow-hidden"><div className="h-full bg-red-500" style={{ width: `${sellPct}%` }} /></div>
        </div>
        <div className="grid grid-cols-2 gap-3 pt-2 border-t border-gray-700">
          <div className="metric-card"><div className="metric-label">Rolling 24h Quote Volume</div><div className="metric-value text-lg">{money(data.total_volume)}</div><div className="text-xs text-muted">Exchange ticker</div></div>
          <div className="metric-card"><div className="metric-label">vs 7 Completed Daily Bars</div><div className="metric-value text-lg">{volumeChange == null || !Number.isFinite(volumeChange) ? 'Unavailable' : `${volumeChange >= 0 ? '+' : ''}${volumeChange.toFixed(2)}%`}</div><div className="text-xs text-muted">Current rolling 24h vs daily quote-volume mean</div></div>
          <div className="metric-card"><div className="metric-label">Sample Size</div><div className="metric-value text-lg">{data.flow_sample_size ?? 'Unavailable'}</div><div className="text-xs text-muted">Aggregate trades</div></div>
          <div className="metric-card"><div className="metric-label">Sample Buy/Sell Ratio</div><div className="metric-value text-lg">{data.sell_volume > 0 ? (data.buy_volume / data.sell_volume).toFixed(2) : 'Unavailable'}</div><div className="text-xs text-muted">Sample only</div></div>
        </div>
        {error && <p className="text-xs text-amber-400">Last refresh failed: {error}</p>}
      </div>
    </div>
  );
};

export default VolumePanel;
