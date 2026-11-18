// Portfolio panel component.
import { useEffect, useState } from 'react';
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

export const PortfolioPanel: React.FC = () => {
  const [data, setData] = useState<PortfolioData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/portfolio/balance');
      const data = await response.json();
      setData(data);
    } catch (e) {
      setError('Failed to load portfolio');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000);
    return () => clearInterval(interval);
  }, []);

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: 'USDT',
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    }).format(value);
  };

  const formatPct = (value: number) => {
    const color = value >= 0 ? 'text-green-400' : 'text-red-400';
    const prefix = value >= 0 ? '+' : '';
    return (
      <span className={`font-mono ${value >= 0 ? 'text-green-400' : 'text-red-400'}`}>
        {prefix}{value.toFixed(2)}%
      </span>
    );
  };

  if (loading) {
    return (
      <div className="panel h-64 flex items-center justify-center">
        <div className="spinner"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="panel h-64 flex items-center justify-center text-red-400">
        {error}
      </div>
    );
  }

  if (!data) return null;

  return (
    <div className="panel h-full">
      <div className="panel-header">Portfolio</div>
      <div className="p-4 space-y-4">
        {/* Total Balance */}
        <div className="metric-card">
          <div className="metric-label">Total Equity</div>
          <div className="metric-value text-2xl">${data.total_balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT</div>
          <div className="flex items-center gap-2 mt-2">
            <span className="metric-label text-sm">24h P&L:</span>
            <span className={`font-mono ${data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.total_pnl >= 0 ? '+' : ''}{data.total_pnl.toFixed(2)} USDT ({data.total_return_pct >= 0 ? '+' : ''}{data.total_return_pct.toFixed(2)}%)
            </span>
          </div>
        </div>

        {/* Spot & Futures Balances */}
        <div className="grid grid-cols-2 gap-3">
          <div className="metric-card">
            <div className="flex items-center justify-between">
              <span className="metric-label">Spot</span>
              <span className="status-indicator">
                <span className="status-dot healthy"></span>
                <span>Active</span>
              </span>
            </div>
            <div className="metric-value mt-2">${data.spot_balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT</div>
            <div className="flex items-center justify-between mt-2 text-sm">
              <span className="text-muted">P&L:</span>
              <span className={`font-mono ${data.spot_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.spot_pnl >= 0 ? '+' : ''}{data.spot_pnl.toFixed(2)} USDT ({data.spot_return_pct >= 0 ? '+' : ''}{data.spot_return_pct.toFixed(2)}%)
              </span>
            </div>
          </div>

          <div className="metric-card">
            <div className="flex items-center justify-between">
              <span className="metric-label">Futures</span>
              <span className="status-indicator">
                <span className="status-dot healthy"></span>
                <span>Active</span>
              </span>
            </div>
            <div className="metric-value mt-2">${data.futures_balance.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} USDT</div>
            <div className="flex items-center justify-between mt-2 text-sm">
              <span className="text-muted">P&L:</span>
              <span className={`font-mono ${data.futures_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                {data.futures_pnl >= 0 ? '+' : ''}{data.futures_pnl.toFixed(2)} USDT ({data.futures_return_pct >= 0 ? '+' : ''}{data.futures_return_pct.toFixed(2)}%)
              </span>
            </div>
          </div>
        </div>

        {/* Quick Stats */}
        <div className="grid grid-cols-3 gap-2 pt-2 border-t border-gray-700">
          <div className="text-center">
            <div className="text-xs text-muted">Total P&L</div>
            <div className={`font-mono ${data.total_pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
              {data.total_pnl >= 0 ? '+' : ''}{data.total_pnl.toFixed(2)} USDT
            </div>
          </div>
          <div className="text-center border-x border-gray-700">
            <div className="text-xs text-muted">Win Rate</div>
            <div className="font-mono text-yellow-400">—</div>
          </div>
          <div className="text-center">
            <div className="text-xs text-muted">Max DD</div>
            <div className="font-mono text-red-400">—</div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PortfolioPanel;