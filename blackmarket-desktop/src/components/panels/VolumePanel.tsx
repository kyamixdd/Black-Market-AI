// Volume analysis panel.
import { useEffect, useState } from 'react';

interface VolumeData {
  buy_volume: number;
  sell_volume: number;
  total_volume: number;
  volume_change_24h: number;
  buy_volume_7d_avg: number | null;
  sell_volume_7d_avg: number | null;
}

export const VolumePanel: React.FC = () => {
  const [data, setData] = useState<VolumeData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/markets/volume');
      const data = await response.json();
      setData(data);
    } catch (e) {
      console.error('Failed to load volume data', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, []);

  if (loading) {
    return (
      <div className="panel h-64 flex items-center justify-center">
        <div className="spinner"></div>
      </div>
    );
  }

  if (!data) return null;

  const totalVol = data.total_volume;
  const buyPct = totalVol > 0 ? ((data.buy_volume / totalVol) * 100).toFixed(1) : '0.0';
  const sellPct = totalVol > 0 ? ((data.sell_volume / totalVol) * 100).toFixed(1) : '0.0';

  return (
    <div className="panel h-full">
      <div className="panel-header">Volume Analysis</div>
      <div className="p-4 space-y-4">
        {/* Buy/Sell Volume Bars */}
        <div className="space-y-2">
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-green-400">Buy Volume</span>
              <span className="text-green-400 font-mono">{buyPct}%</span>
            </div>
            <div className="h-3 bg-gray-800 rounded overflow-hidden">
              <div
                className="h-full bg-green-500 transition-all duration-300"
                style={{ width: `${parseFloat(buyPct)}%` }}
              />
            </div>
          </div>
          <div>
            <div className="flex justify-between text-xs mb-1">
              <span className="text-red-400">Sell Volume</span>
              <span className="text-red-400 font-mono">{sellPct}%</span>
            </div>
            <div className="h-3 bg-gray-800 rounded overflow-hidden">
              <div
                className="h-full bg-red-500 transition-all duration-300"
                style={{ width: `${sellPct}%` }}
              />
            </div>
          </div>
        </div>

        {/* Volume Stats */}
        <div className="grid grid-cols-3 gap-3 pt-2 border-t border-gray-700">
          <div className="metric-card">
            <div className="metric-label">Total Volume (24h)</div>
            <div className="metric-value text-xl">${(data.total_volume / 1e9).toFixed(2)}B</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">24h Change</div>
            <div className={`metric-value text-xl ${data.volume_change_24h >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.volume_change_24h >= 0 ? '+' : ''}{data.volume_change_24h.toFixed(2)}%
            </div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Buy/Sell Ratio</div>
            <div className="metric-value text-xl">
              {data.sell_volume > 0 ? (data.buy_volume / data.sell_volume).toFixed(2) : '∞'}
            </div>
          </div>
        </div>

        {/* 7-day Averages */}
        {data.buy_volume_7d_avg && data.sell_volume_7d_avg && (
          <div className="pt-2 border-t border-gray-700">
            <div className="text-xs text-muted mb-2">7-Day Averages</div>
            <div className="grid grid-cols-2 gap-3">
              <div className="metric-card">
                <div className="metric-label">Avg Buy Volume</div>
                <div className="metric-value text-green-400">${(data.buy_volume_7d_avg! / 1e9).toFixed(2)}B</div>
              </div>
              <div className="metric-card">
                <div className="metric-label">Avg Sell Volume</div>
                <div className="metric-value text-red-400">${(data.sell_volume_7d_avg! / 1e9).toFixed(2)}B</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default VolumePanel;