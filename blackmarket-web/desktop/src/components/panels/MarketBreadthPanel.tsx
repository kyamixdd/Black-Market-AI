// Market breadth panel.
import { useEffect, useState } from 'react';

interface BreadthData {
  advancing: number;
  declining: number;
  neutral: number;
  total_volume: number;
  avg_spread_bps: number;
  avg_orderbook_imbalance: number;
}

export const MarketBreadthPanel: React.FC = () => {
  const [data, setData] = useState<BreadthData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/markets/breadth');
      const data = await response.json();
      setData(data);
    } catch (e) {
      console.error('Failed to load breadth data', e);
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

  const total = data.advancing + data.declining + data.neutral;
  const advancePct = total > 0 ? (data.advancing / total * 100).toFixed(1) : '0.0';
  const declinePct = total > 0 ? (data.declining / total * 100).toFixed(1) : '0.0';

  return (
    <div className="panel h-full">
      <div className="panel-header">Market Breadth</div>
      <div className="p-4 space-y-4">
        {/* Summary Cards */}
        <div className="grid grid-cols-3 gap-3">
          <div className="metric-card">
            <div className="metric-label">Advancing</div>
            <div className="metric-value text-green-400">{data.advancing}</div>
            <div className="text-xs text-muted mt-1">{advancePct}% of markets</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Declining</div>
            <div className="metric-value text-red-400">{data.declining}</div>
            <div className="text-xs text-muted mt-1">{declinePct}% of markets</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Neutral</div>
            <div className="metric-value text-gray-400">{data.neutral}</div>
            <div className="text-xs text-muted mt-1">{total > 0 ? ((data.neutral / total) * 100).toFixed(1) : '0.0'}% of markets</div>
          </div>
        </div>

        {/* Volume & Spread */}
        <div className="grid grid-cols-3 gap-3 pt-2 border-t border-gray-700">
          <div className="metric-card">
            <div className="metric-label">Total Volume (24h)</div>
            <div className="metric-value text-xl">${(data.total_volume / 1e9).toFixed(2)}B</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Avg Spread</div>
            <div className="metric-value text-xl">{data.avg_spread_bps.toFixed(1)} bps</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Orderbook Imbalance</div>
            <div className="metric-value text-xl">{data.avg_orderbook_imbalance.toFixed(3)}</div>
          </div>
        </div>

        {/* Advance/Decline Visual */}
        <div className="pt-2 border-t border-gray-700">
          <div className="text-xs text-muted mb-2">Advance/Decline Ratio</div>
          <div className="h-4 rounded overflow-hidden bg-gray-800">
            <div
              className="h-full bg-green-500 transition-all duration-300"
              style={{ width: `${(data.advancing / (total || 1)) * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-xs text-muted mt-1">
            <span>Advancing: {data.advancing}</span>
            <span>Neutral: {data.neutral}</span>
            <span>Declining: {data.declining}</span>
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketBreadthPanel;