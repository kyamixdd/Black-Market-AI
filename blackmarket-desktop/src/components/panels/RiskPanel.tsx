// Risk analytics panel with circular risk visualization.
import { useEffect, useState } from 'react';

interface RiskData {
  current_exposure_pct: number;
  used_risk_capacity_pct: number;
  available_risk_capacity_pct: number;
  open_trade_risk_pct: number;
  daily_loss_capacity_pct: number;
  risk_manager_status: string;
  max_spot_positions: number;
  max_futures_positions: number;
  max_leverage: number;
  risk_per_trade_pct: number;
  max_daily_loss_pct: number;
  max_total_open_pct: number;
}

export const RiskPanel: React.FC = () => {
  const [data, setData] = useState<RiskData | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchData = async () => {
    try {
      const response = await fetch('/api/risk/status');
      const data = await response.json();
      setData(data);
    } catch (e) {
      console.error('Failed to load risk data', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, []);

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'NORMAL': return 'text-gray-200';
      case 'WARNING': return 'text-gray-200';
      case 'CRITICAL': return 'text-gray-200';
      default: return 'text-gray-400';
    }
  };

  const getStatusDot = (status: string) => {
    switch (status) {
      case 'NORMAL': return 'bg-gray-200';
      case 'WARNING': return 'bg-gray-200';
      case 'CRITICAL': return 'bg-gray-200';
      default: return 'bg-gray-400';
    }
  };

  if (loading) {
    return (
      <div className="panel h-80 flex items-center justify-center">
        <div className="spinner"></div>
      </div>
    );
  }

  if (!data) return null;

  const exposureDegrees = (data.current_exposure_pct / 100) * 360;
  const riskCapacityDegrees = (data.used_risk_capacity_pct / 100) * 360;

  return (
    <div className="panel h-full">
      <div className="panel-header">Risk Analytics</div>
      <div className="p-4 space-y-4">
        {/* Circular Risk Visualization */}
        <div className="flex items-center justify-center">
          <div className="relative w-48 h-48">
            {/* Background circle */}
            <svg className="w-48 h-48 transform -rotate-90">
              <circle
                cx="96"
                cy="96"
                r="80"
                fill="none"
                stroke="#303235"
                strokeWidth="8"
              />
              {/* Exposure arc */}
              <circle
                cx="96"
                cy="96"
                r="80"
                fill="none"
                stroke="#bfc3c5"
                strokeWidth="8"
                strokeDasharray={`${(data.current_exposure_pct / 100) * 502.65} 502.65`}
                strokeLinecap="round"
                strokeDashoffset="0"
                style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
              />
              {/* Risk capacity arc */}
              <circle
                cx="96"
                cy="96"
                r="68"
                fill="none"
                stroke="#858a8f"
                strokeWidth="6"
                strokeDasharray={`${(data.used_risk_capacity_pct / 100) * 427.26} 427.26`}
                strokeLinecap="round"
                strokeDashoffset="0"
                style={{ transform: 'rotate(-90deg)', transformOrigin: 'center' }}
              />
            </svg>
            <div className="absolute inset-0 flex flex-col items-center justify-center">
              <span className="text-xs text-muted">Exposure</span>
              <span className="text-2xl font-mono font-bold">{data.current_exposure_pct.toFixed(1)}%</span>
              <span className="text-xs text-muted mt-1">of 100% limit</span>
            </div>
          </div>
        </div>

        {/* Risk Metrics Grid */}
        <div className="grid grid-cols-2 gap-3">
          <div className="metric-card">
            <div className="metric-label">Exposure</div>
            <div className="metric-value text-xl">{data.current_exposure_pct.toFixed(1)}%</div>
            <div className="text-xs text-muted mt-1">of 100% max</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Risk Capacity Used</div>
            <div className="metric-value text-xl">{data.used_risk_capacity_pct.toFixed(1)}%</div>
            <div className="text-xs text-muted mt-1">of 100% max</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Daily Loss Capacity</div>
            <div className="metric-value text-xl">{data.daily_loss_capacity_pct.toFixed(1)}%</div>
            <div className="text-xs text-muted mt-1">of 2% daily limit</div>
          </div>
          <div className="metric-card">
            <div className="metric-label">Risk Manager Status</div>
            <div className="flex items-center gap-2 mt-1">
              <span className={`status-dot ${getStatusDot(data.risk_manager_status)}`}></span>
              <span className={`font-mono ${getStatusColor(data.risk_manager_status)}`}>
                {data.risk_manager_status}
              </span>
            </div>
          </div>
        </div>

        {/* Position Limits */}
        <div className="pt-2 border-t border-gray-700">
          <div className="text-xs text-muted mb-2">Position Limits</div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="metric-card py-2">
              <div className="text-xs text-muted">Max Spot</div>
              <div className="font-mono text-lg">{data.max_spot_positions}</div>
            </div>
            <div className="metric-card py-2">
              <div className="text-xs text-muted">Max Futures</div>
              <div className="font-mono text-lg">{data.max_futures_positions}</div>
            </div>
            <div className="metric-card py-2">
              <div className="text-xs text-muted">Max Leverage</div>
              <div className="font-mono text-lg">{data.max_leverage}x</div>
            </div>
          </div>
        </div>

        {/* Risk Limits */}
        <div className="pt-2 border-t border-gray-700">
          <div className="text-xs text-muted mb-2">Risk Parameters</div>
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="metric-card py-2">
              <div className="text-xs text-muted">Per Trade</div>
              <div className="font-mono text-lg">{data.risk_per_trade_pct}%</div>
            </div>
            <div className="metric-card py-2">
              <div className="text-xs text-muted">Daily Loss</div>
              <div className="font-mono text-lg">{data.max_daily_loss_pct}%</div>
            </div>
            <div className="metric-card py-2">
              <div className="text-xs text-muted">Total Open</div>
              <div className="font-mono text-lg">{data.max_total_open_pct}%</div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

function getStatusColor(status: string): string {
  switch (status) {
    case 'NORMAL': return 'text-green-400';
    case 'WARNING': return 'text-yellow-400';
    case 'CRITICAL': return 'text-red-400';
    default: return 'text-gray-400';
  }
}

function getStatusDot(status: string): string {
  switch (status) {
    case 'NORMAL': return 'bg-green-400';
    case 'WARNING': return 'bg-yellow-400';
    case 'CRITICAL': return 'bg-red-400';
    default: return 'bg-gray-400';
  }
}

export default RiskPanel;
