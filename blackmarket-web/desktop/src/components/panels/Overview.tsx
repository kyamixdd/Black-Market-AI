import { useEffect } from 'react';
import PortfolioPanel from './PortfolioPanel';
import RiskPanel from './RiskPanel';
import HeatmapPanel from './HeatmapPanel';
import MarketBreadthPanel from './MarketBreadthPanel';
import VolumePanel from './VolumePanel';
import LongShortPanel from './LongShortPanel';

export const OverviewPanel: React.FC = () => {
  useEffect(() => {
    fetch('/api/markets')
      .then(r => r.json())
      .then(data => {
        const symbols = data.markets.map((m: any) => ({
          symbol: m.symbol,
          market: m.market,
          price: m.price,
          change: m.price_change_24h,
        }));
        console.log('Markets loaded:', symbols.length);
      });
    fetch('/api/portfolio/balance')
      .then(r => r.json())
      .then(data => console.log('Portfolio loaded:', data));
  }, []);

  return (
    <div className="h-full bg-[#141516] rounded-lg p-4 overflow-y-auto">
      <div className="flex items-baseline justify-between mb-4">
        <div>
          <h2 className="text-xl font-semibold text-white">Overview</h2>
          <span className="text-sm text-muted">Live market data</span>
        </div>
        <button className="btn-ghost text-sm" onClick={() => window.open('/settings', '_blank')}>
          Settings
        </button>
      </div>

      <div className="grid gap-4">
        {/* Left Column: Portfolio + Risk */}
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 h-[300px]">
          <div className="panel h-100">
            <PortfolioPanel />
          </div>
          <div className="panel h-100">
            <RiskPanel />
          </div>
        </div>

        {/* Right Column: Heatmap + Breadth */}
        <div className="grid grid-cols-2 gap-4 h-[250px]">
          <HeatmapPanel />
          <MarketBreadthPanel />
        </div>

        <div className="panel" style={{ height: '200px' }}>
          <VolumePanel />
        </div>
      </div>

      {/* Bottom row: Long/Short */}
      <div className="mt-4 flex gap-4">
        <div className="panel flex-1">
          <LongShortPanel />
        </div>
      </div>
    </div>
  );
};