// Portfolio panel component.
import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';

interface PortfolioData {
  spot_balance: number;
  futures_balance: number;
  total_balance: number;
  spot_pnl: number;
  futures_pnl: number;
  total_pnl: number;
  spot_return_pct: number;
  futures_return_pct: number;
  total_return_pct: number;
}

const formatAmount = (value: number) =>
  Number.isFinite(value)
    ? value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : 'Unavailable';

const formatSigned = (value: number) =>
  Number.isFinite(value) ? `${value >= 0 ? '+' : ''}${value.toFixed(2)}` : 'Unavailable';

const pnlClass = (value: number) =>
  Number.isFinite(value) ? (value >= 0 ? 'text-green-400' : 'text-red-400') : 'text-muted';

export const PortfolioPanel: React.FC = () => {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const mounted = useRef(true);

  const fetchData = async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      // Use the shared authenticated API client. Relative fetch('/api/...') can
      // target the frontend origin rather than the local backend in desktop.
      const response = await api.getPortfolioBalance() as PortfolioData;
      if (!response || typeof response !== 'object') {
        throw new Error('Portfolio service returned an invalid response');
      }
      if (mounted.current) {
        setData(response);
        setError(null);
      }
    } catch (e) {
      if (mounted.current) {
        setError(e instanceof Error ? e.message : 'Portfolio data unavailable');
      }
    } finally {
      requestInFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    void fetchData();
    const interval = setInterval(() => void fetchData(), 5000);
    return () => {
      mounted.current = false;
      clearInterval(interval);
    };
  }, []);

  if (loading) {
    return (
      <div className="panel h-64 flex items-center justify-center" role="status" aria-label="Loading portfolio">
        <div className="spinner" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="panel h-64 flex flex-col items-center justify-center gap-3 p-4">
        <div className="panel-header w-full">Portfolio</div>
        <p className="text-sm text-red-400 text-center" role="alert">{error || 'Portfolio data unavailable'}</p>
        <button type="button" className="btn-ghost text-sm" onClick={() => { setLoading(true); void fetchData(); }}>
          Retry
        </button>
      </div>
    );
  }

  return (
    <div className="panel h-full min-w-0">
      <div className="panel-header">Portfolio</div>
      <div className="p-3 sm:p-4 space-y-3">
        {error && <p className="text-xs text-amber-400" role="status">Refresh failed: {error}. Showing last successful data.</p>}
        <div className="metric-card min-w-0">
          <div className="metric-label">Total Equity</div>
          <div className="metric-value text-xl sm:text-2xl tabular-nums break-words">${formatAmount(data.total_balance)} USDT</div>
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 mt-2 min-w-0">
            <span className="metric-label text-sm">24h P&amp;L:</span>
            <span className={`font-mono text-xs sm:text-sm tabular-nums ${pnlClass(data.total_pnl)}`}>
              {formatSigned(data.total_pnl)} USDT ({formatSigned(data.total_return_pct)}%)
            </span>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 min-w-0">
          <div className="metric-card min-w-0">
            <div className="metric-label">Spot Balance</div>
            <div className="metric-value mt-2 text-base sm:text-lg tabular-nums break-words">${formatAmount(data.spot_balance)} USDT</div>
            <div className="flex flex-wrap items-center gap-x-1 mt-2 text-xs sm:text-sm">
              <span className="text-muted">P&amp;L:</span>
              <span className={`font-mono tabular-nums ${pnlClass(data.spot_pnl)}`}>
                {formatSigned(data.spot_pnl)} ({formatSigned(data.spot_return_pct)}%)
              </span>
            </div>
          </div>

          <div className="metric-card min-w-0">
            <div className="metric-label">Futures Balance</div>
            <div className="metric-value mt-2 text-base sm:text-lg tabular-nums break-words">${formatAmount(data.futures_balance)} USDT</div>
            <div className="flex flex-wrap items-center gap-x-1 mt-2 text-xs sm:text-sm">
              <span className="text-muted">P&amp;L:</span>
              <span className={`font-mono tabular-nums ${pnlClass(data.futures_pnl)}`}>
                {formatSigned(data.futures_pnl)} ({formatSigned(data.futures_return_pct)}%)
              </span>
            </div>
          </div>
        </div>

        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-700 min-w-0">
          <div className="text-center min-w-0">
            <div className="text-xs text-muted">Total P&amp;L</div>
            <div className={`font-mono text-xs sm:text-sm tabular-nums break-words ${pnlClass(data.total_pnl)}`}>
              {formatSigned(data.total_pnl)} USDT
            </div>
          </div>
          <div className="text-center border-x border-gray-700 min-w-0">
            <div className="text-xs text-muted">Win Rate</div>
            <div className="font-mono text-muted">Unavailable</div>
          </div>
          <div className="text-center min-w-0">
            <div className="text-xs text-muted">Max DD</div>
            <div className="font-mono text-muted">Unavailable</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioPanel;
