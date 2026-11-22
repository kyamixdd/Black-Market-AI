// Risk analytics panel with circular risk visualization.
import { useEffect, useRef, useState } from 'react';
import { api } from '../../services/api';

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
  max_position_size_pct: number;
  max_asset_exposure_pct: number;
}

export const RiskPanel: React.FC = () => {
  const [data, setData] = useState<RiskData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const mounted = useRef(false);

  const fetchData = async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const payload = await api.getRiskStatus() as RiskData;
      if (!payload || typeof payload !== 'object'
        || !Number.isFinite(payload.current_exposure_pct)
        || !Number.isFinite(payload.used_risk_capacity_pct)
        || !Number.isFinite(payload.daily_loss_capacity_pct)
        || typeof payload.risk_manager_status !== 'string') {
        throw new Error('Risk service returned invalid data');
      }
      if (mounted.current) {
        setData(payload);
        setError(null);
      }
    } catch (e) {
      if (mounted.current) setError(e instanceof Error ? e.message : 'Risk data unavailable');
    } finally {
      requestInFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  };

  useEffect(() => {
    mounted.current = true;
    void fetchData();
    const interval = setInterval(() => void fetchData(), 10000);
    return () => {
      mounted.current = false;
      clearInterval(interval);
    };
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
      <div className="panel h-80 flex items-center justify-center" role="status" aria-label="Loading risk analytics">
        <div className="spinner" />
      </div>
    );
  }

  if (!data) {
    return (
      <div className="panel p-3 sm:p-4 min-w-0">
        <div className="panel-header">Risk Analytics</div>
        <p className="text-sm text-muted my-3" role={error ? 'alert' : 'status'}>
          {error || 'Risk data unavailable'}
        </p>
        <button type="button" className="btn-ghost text-sm" onClick={() => { setLoading(true); void fetchData(); }}>
          Retry
        </button>
      </div>
    );
  }

  const clampPercent = (value: number) => Math.min(100, Math.max(0, Number.isFinite(value) ? value : 0));
  const exposureDegrees = (clampPercent(data.current_exposure_pct) / 100) * 360;
  const riskCapacityDegrees = (clampPercent(data.used_risk_capacity_pct) / 100) * 360;

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
