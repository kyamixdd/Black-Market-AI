// Risk analytics panel with a compact, source-backed risk visualization.
import { useCallback, useEffect, useRef, useState } from 'react';
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

const percent = (value: number | null | undefined) =>
  Number.isFinite(value) ? `${(value as number).toFixed(2)}%` : '—';

const boundedPercent = (value: number | null | undefined) =>
  Math.min(100, Math.max(0, Number.isFinite(value) ? value as number : 0));

const statusLabel = (status: string) => status.replace(/_/g, ' ').toLowerCase();

export const RiskPanel: React.FC = () => {
  const [data, setData] = useState<RiskData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const requestInFlight = useRef(false);
  const mounted = useRef(false);

  const fetchData = useCallback(async () => {
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
    } catch (cause) {
      if (mounted.current) {
        setError(cause instanceof Error ? cause.message : 'Risk data unavailable');
      }
    } finally {
      requestInFlight.current = false;
      if (mounted.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void fetchData();
    const interval = window.setInterval(() => void fetchData(), 10_000);
    return () => {
      mounted.current = false;
      window.clearInterval(interval);
    };
  }, [fetchData]);

  if (loading && !data) {
    return (
      <section className="panel risk-panel" aria-label="Risk analytics">
        <div className="panel-heading"><h2>Risk analytics</h2></div>
        <div className="workspace-empty" role="status">Loading risk data…</div>
      </section>
    );
  }

  if (!data) {
    return (
      <section className="panel risk-panel" aria-label="Risk analytics">
        <div className="panel-heading"><h2>Risk analytics</h2></div>
        <div className="workspace-empty" role="alert">{error || 'Risk data unavailable'}</div>
        <div className="risk-foot">
          <button type="button" className="table-action" onClick={() => { setLoading(true); void fetchData(); }}>
            Retry
          </button>
        </div>
      </section>
    );
  }

  const exposure = boundedPercent(data.current_exposure_pct);
  const usedCapacity = boundedPercent(data.used_risk_capacity_pct);
  const status = data.risk_manager_status.toUpperCase();
  const statusTone = status === 'NORMAL' ? 'positive' : status === 'CRITICAL' ? 'negative' : '';

  return (
    <section className="panel risk-panel" aria-label="Risk analytics">
      <div className="panel-heading">
        <h2>Risk analytics</h2>
        <span className={`risk-status ${statusTone}`} role="status">{statusLabel(status)}</span>
      </div>
      <div className="risk-content">
        <div
          className="risk-dial"
          aria-label={`Risk capacity used ${percent(data.used_risk_capacity_pct)}`}
          style={{ background: `conic-gradient(var(--text-secondary) ${usedCapacity}%, var(--border-subtle) 0)` }}
        >
          <div>
            <strong className="risk-digit">{percent(data.current_exposure_pct)}</strong>
            <span className="risk-caption">Exposure</span>
          </div>
        </div>
        <div className="risk-stats">
          <div className="risk-stat"><span>Capacity used</span><b>{percent(data.used_risk_capacity_pct)}</b></div>
          <div className="risk-stat"><span>Capacity available</span><b>{percent(data.available_risk_capacity_pct)}</b></div>
          <div className="risk-stat"><span>Open trade risk</span><b>{percent(data.open_trade_risk_pct)}</b></div>
          <div className="risk-stat"><span>Daily loss capacity</span><b>{percent(data.daily_loss_capacity_pct)}</b></div>
        </div>
      </div>
      <div className="risk-foot">
        <span>Risk / trade <b>{percent(data.risk_per_trade_pct)}</b></span>
        <span>Max leverage <b>{Number.isFinite(data.max_leverage) ? `${data.max_leverage}×` : '—'}</b></span>
      </div>
      <div className="risk-foot">
        <span>Spot positions <b>{Number.isFinite(data.max_spot_positions) ? data.max_spot_positions : '—'}</b></span>
        <span>Futures <b>{Number.isFinite(data.max_futures_positions) ? data.max_futures_positions : '—'}</b></span>
      </div>
      <div className="risk-foot">
        <span>Max daily loss <b>{percent(data.max_daily_loss_pct)}</b></span>
        <span>Total open <b>{percent(data.max_total_open_pct)}</b></span>
      </div>
      <div className="risk-foot">
        <span>Position cap <b>{percent(data.max_position_size_pct)}</b></span>
        <span>Asset cap <b>{percent(data.max_asset_exposure_pct)}</b></span>
      </div>
    </section>
  );
};

export default RiskPanel;
