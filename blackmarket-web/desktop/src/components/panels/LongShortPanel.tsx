// Long/Short analytics panel for Futures.
import { useEffect, useState } from 'react';

interface LongShortData {
  long_short_ratio: number;
  open_interest: number;
  funding_rate: number;
  long_volume: number;
  short_volume: number;
}

export const LongShortPanel: React.FC = () => {
  const [data, setData] = useState<LongShortData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/markets/long-short');
      const data = await response.json();
      setData(data);
    } catch (e) {
      console.error('Failed to load long/short data', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 60000);
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

  const ratio = data.long_short_ratio;
  const isInfinite = !isFinite(ratio);

  return (
    <div className="panel h-full">
      <div className="panel-header">Long/Short Analytics (Futures)</div>
      <div className="p-4 space-y-4">
        {/* Main Ratio */}
        <div className="metric-card p-4 text-center">
          <div className="text-xs text-muted mb-2">Long/Short Ratio</div>
          <div className="text-4xl font-mono font-bold">
            {isInfinite ? '∞' : ratio.toFixed(2)}
          </div>
          <div className="text-xs text-muted mt-1">
            {data.long_volume > 0 || data.short_volume > 0 ? (
              <>
                Long: {data.long_volume.toFixed(1)}% | Short: {data.short_volume.toFixed(1)}%
              </>
            ) : 'No position data'}
          </div>
        </div>

        {/* Key Metrics */}
        <div className="grid grid-cols-2 gap-3">
          <div className="metric-card">
            <div className="metric-label">Open Interest</div>
            <div className="metric-value text-xl">${(data.open_interest / 1e9).toFixed(2)}B</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Funding Rate (8h)</div>
            <div className={`metric-value text-xl ${data.funding_rate >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.funding_rate >= 0 ? '+' : ''}{(data.funding_rate * 100).toFixed(4)}%
            </div>
            <div className="text-xs text-muted mt-1">per 8 hours</div>
          </div>
        </div>

        {/* Long/Short Volume Breakdown */}
        <div className="pt-2 border-t border-gray-700">
          <div className="text-xs text-muted mb-2">Long vs Short Volume</div>
          <div className="space-y-2">
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-green-400">Long Volume</span>
                <span className="text-green-400 font-mono">{data.long_volume.toFixed(1)}%</span>
              </div>
              <div className="h-2 bg-gray-800 rounded overflow-hidden">
                <div
                  className="h-full bg-green-500 transition-all duration-300"
                  style={{ width: `${data.long_volume}%` }}
                />
              </div>
            </div>
            <div>
              <div className="flex justify-between text-xs mb-1">
                <span className="text-red-400">Short Volume</span>
                <span className="text-red-400 font-mono">{data.short_volume.toFixed(1)}%</span>
              </div>
              <div className="h-2 bg-gray-800 rounded overflow-hidden">
                <div
                  className="h-full bg-red-500 transition-all duration-300"
                  style={{ width: `${data.short_volume}%` }}
                />
              </div>
            </div>
          </div>

          {/* Interpretation */}
          <div className="pt-2 border-t border-gray-700">
            <div className="text-xs text-muted">
              {ratio > 1.5 ? (
                'Strongly bullish bias - Longs dominate'
              ) : ratio > 1.1 ? (
                'Moderately bullish - More longs than shorts'
              ) : ratio > 0.9 ? (
                'Balanced - Near equal long/short'
              ) : ratio > 0.5 ? (
                'Moderately bearish - More shorts than longs'
              ) : (
                'Strongly bearish bias - Shorts dominate'
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LongShortPanel;