// Long/Short analytics panel for Futures.
import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';

interface LongShortData {
  long_short_ratio: number;
  open_interest: number;
  funding_rate: number;
  long_volume: number;
  short_volume: number;
}

const isValidData = (value: unknown): value is LongShortData => {
  if (!value || typeof value !== 'object') return false;
  const data = value as Record<string, unknown>;
  return ['long_short_ratio', 'open_interest', 'funding_rate', 'long_volume', 'short_volume']
    .every((key) => typeof data[key] === 'number' && Number.isFinite(data[key]));
};

const formatValue = (value: number, digits = 2) =>
  Number.isFinite(value) ? value.toFixed(digits) : 'Unavailable';

export const LongShortPanel: React.FC = () => {
  const [data, setData] = useState<LongShortData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const mounted = useRef(false);

  const fetchData = async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const payload = await api.getLongShort();
      if (!isValidData(payload)) throw new Error('Long/short service returned invalid data');
      if (mounted.current) {
        setData(payload);
        setError(null);
      }
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Long/short data unavailable');
      }
    } finally {
      requestInFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    void fetchData();
    const interval = setInterval(() => void fetchData(), 60000);
    return () => {
      mounted.current = false;
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className="panel h-64 flex items-center justify-center" role="status" aria-label="Loading long/short analytics">
        <div className="spinner" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="panel p-4">
        <div className="panel-header">Long/Short Analytics (Futures)</div>
        <p className="text-sm text-muted my-3" role="alert">{error || 'Long/short data unavailable'}</p>
        <button type="button" className="btn-ghost text-sm" onClick={() => { setLoading(true); void fetchData(); }}>
          Retry
        </button>
      </div>
    );
  }

  const ratio = data.long_short_ratio;
  const isInfinite = !Number.isFinite(ratio);
  const longPct = Math.min(100, Math.max(0, data.long_volume));
  const shortPct = Math.min(100, Math.max(0, data.short_volume));

  return (
    <div className="panel h-full min-w-0">
      <div className="panel-header">Long/Short Analytics (Futures)</div>
      <div className="p-3 sm:p-4 space-y-4 min-w-0">
        {error && <p className="text-xs text-amber-400" role="status">Refresh failed: {error}. Showing last successful data.</p>}
        <div className="metric-card p-3 sm:p-4 text-center min-w-0">
          <div className="text-xs text-muted mb-2">Long/Short Ratio</div>
          <div className="text-3xl sm:text-4xl font-mono font-bold tabular-nums">{isInfinite ? '∞' : formatValue(ratio)}</div>
          <div className="text-xs text-muted mt-1 break-words">
            {data.long_volume > 0 || data.short_volume > 0
              ? <>Long: {formatValue(data.long_volume, 1)}% | Short: {formatValue(data.short_volume, 1)}%</>
              : 'No position data'}
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 min-w-0">
          <div className="metric-card min-w-0">
            <div className="metric-label">Open Interest</div>
            <div className="metric-value text-lg sm:text-xl tabular-nums break-words">
              {Number.isFinite(data.open_interest) ? `$${(data.open_interest / 1e9).toFixed(2)}B` : 'Unavailable'}
            </div>
          </div>
          <div className="metric-card min-w-0">
            <div className="metric-label">Funding Rate (8h)</div>
            <div className={`metric-value text-lg sm:text-xl tabular-nums break-words ${data.funding_rate >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.funding_rate >= 0 ? '+' : ''}{formatValue(data.funding_rate * 100, 4)}%
            </div>
            <div className="text-xs text-muted mt-1">per 8 hours</div>
          </div>
        </div>

        <div className="pt-2 border-t border-gray-700 min-w-0">
          <div className="text-xs text-muted mb-2">Long vs Short Volume</div>
          <div className="space-y-3">
            <div>
              <div className="flex flex-wrap justify-between gap-1 text-xs mb-1">
                <span className="text-green-400">Long Volume</span>
                <span className="text-green-400 font-mono tabular-nums">{formatValue(data.long_volume, 1)}%</span>
              </div>
              <div className="h-2 bg-gray-800 rounded overflow-hidden">
                <div className="h-full bg-green-500 transition-all duration-300" style={{ width: `${longPct}%` }} />
              </div>
            </div>
            <div>
              <div className="flex flex-wrap justify-between gap-1 text-xs mb-1">
                <span className="text-red-400">Short Volume</span>
                <span className="text-red-400 font-mono tabular-nums">{formatValue(data.short_volume, 1)}%</span>
              </div>
              <div className="h-2 bg-gray-800 rounded overflow-hidden">
                <div className="h-full bg-red-500 transition-all duration-300" style={{ width: `${shortPct}%` }} />
              </div>
            </div>
          </div>

          <div className="pt-3 mt-3 border-t border-gray-700">
            <div className="text-xs text-muted">
              {!Number.isFinite(ratio) ? 'Position ratio unavailable'
                : ratio > 1.5 ? 'Strongly bullish bias - Longs dominate'
                  : ratio > 1.1 ? 'Moderately bullish - More longs than shorts'
                    : ratio > 0.9 ? 'Balanced - Near equal long/short'
                      : ratio > 0.5 ? 'Moderately bearish - More shorts than longs'
                        : 'Strongly bearish bias - Shorts dominate'}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LongShortPanel;
