// Market heatmap panel.
import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';

interface HeatmapItem {
  symbol: string;
  market: string;
  price_change_24h: number;
  volume_24h: number;
  price: number;
  regime: string;
  relative_strength_pct?: number | null;
  volatility_24h_pct?: number | null;
  atr_24h_pct?: number | null;
  data_freshness?: string;
}

const isHeatmapItem = (value: unknown): value is HeatmapItem => {
  if (!value || typeof value !== 'object') return false;
  const item = value as Record<string, unknown>;
  return typeof item.symbol === 'string'
    && typeof item.market === 'string'
    && typeof item.price_change_24h === 'number' && Number.isFinite(item.price_change_24h)
    && typeof item.volume_24h === 'number' && Number.isFinite(item.volume_24h)
    && typeof item.price === 'number' && Number.isFinite(item.price)
    && typeof item.regime === 'string';
};

export const HeatmapPanel: React.FC = () => {
  const [heatmap, setHeatmap] = useState<HeatmapItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const mounted = useRef(false);

  const fetchData = async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const payload = await api.getHeatmap() as { heatmap?: unknown };
      if (!payload || !Array.isArray(payload.heatmap)) {
        throw new Error('Heatmap service returned an invalid response');
      }
      const validItems = payload.heatmap.filter(isHeatmapItem);
      if (mounted.current) {
        setHeatmap(validItems);
        setError(null);
      }
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Market heatmap unavailable');
      }
    } finally {
      requestInFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    void fetchData();
    const interval = setInterval(() => void fetchData(), 30000);
    return () => {
      mounted.current = false;
      clearInterval(interval);
    };
  }, []);

  const getColor = (change: number) => {
    if (change > 2) return 'bg-green-500/30';
    if (change > 0) return 'bg-green-500/15';
    if (change < -2) return 'bg-red-500/30';
    if (change < 0) return 'bg-red-500/15';
    return 'bg-gray-700/30';
  };

  const getTextColor = (change: number) => {
    if (change > 0) return 'text-green-400';
    if (change < 0) return 'text-red-400';
    return 'text-gray-400';
  };

  if (loading) {
    return (
      <div className="panel h-80 flex items-center justify-center" role="status" aria-label="Loading market heatmap">
        <div className="spinner" />
      </div>
    );
  }

  if (heatmap.length === 0) {
    return (
      <div className="panel h-full min-w-0 p-3">
        <div className="panel-header">Market Heatmap</div>
        <p className="text-sm text-muted my-3" role={error ? 'alert' : 'status'}>
          {error || 'No heatmap market data is currently available.'}
        </p>
        <button type="button" className="btn-ghost text-sm" onClick={() => { setLoading(true); void fetchData(); }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="panel h-full min-w-0">
      <div className="panel-header">Market Heatmap</div>
      <div className="p-2 min-w-0">
        {error && <p className="text-xs text-amber-400 mb-2" role="status">Refresh failed: {error}. Showing last successful data.</p>}
        <div className="grid grid-cols-4 sm:grid-cols-7 gap-1">
          {heatmap.slice(0, 35).map((item) => (
            <div
              key={`${item.market}:${item.symbol}`}
              className={`min-w-0 rounded px-1 sm:px-2 py-1.5 text-center text-xs font-mono transition-colors ${getColor(item.price_change_24h)}`}
              style={{ border: '1px solid #303235' }}
              title={`${item.symbol}: ${item.price_change_24h >= 0 ? '+' : ''}${item.price_change_24h.toFixed(2)}% | ${(item.volume_24h / 1e6).toFixed(1)}M vol | ${item.regime}`}
            >
              <div className="font-mono text-xs font-medium truncate">{item.symbol.replace('USDT', '')}</div>
              <div className={`text-[10px] font-mono tabular-nums ${getTextColor(item.price_change_24h)}`}>
                {item.price_change_24h >= 0 ? '+' : ''}{item.price_change_24h.toFixed(2)}%
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

export default HeatmapPanel;
