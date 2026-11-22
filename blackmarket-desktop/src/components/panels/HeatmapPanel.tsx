// Market heatmap panel.
import { useEffect, useState } from 'react';

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

export const HeatmapPanel: React.FC = () => {
  const [heatmap, setHeatmap] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/markets/heatmap');
      if (!response.ok) throw new Error(`Heatmap API returned HTTP ${response.status}`);
      const data = await response.json();
      setHeatmap(data.heatmap || []);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Market heatmap unavailable');
      console.error('Failed to load heatmap', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
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
      <div className="panel h-80 flex items-center justify-center">
        <div className="spinner"></div>
      </div>
    );
  }

  return (
    <div className="panel h-full">
      <div className="panel-header">Market Heatmap</div>
      <div className="p-2">
        {error && <p className="text-xs text-amber-400 mb-2">Refresh failed: {error}</p>}
        <div className="grid grid-cols-7 gap-1">
          {heatmap.slice(0, 35).map((item: any) => (
            <div
              key={item.symbol}
              className={`rounded px-2 py-1.5 text-center text-xs font-mono transition-colors ${getColor(item.price_change_24h)}`}
              style={{ border: '1px solid #303235' }}
              title={`${item.symbol}: ${item.price_change_24h >= 0 ? '+' : ''}${item.price_change_24h.toFixed(2)}% | ${(item.volume_24h / 1e6).toFixed(1)}M vol | ${item.regime}`}
            >
              <div className="font-mono text-xs font-medium truncate">{item.symbol.replace('USDT', '')}</div>
              <div className={`text-[10px] font-mono ${item.price_change_24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
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