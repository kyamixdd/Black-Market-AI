// Main market chart component using Lightweight Charts.
import { useEffect, useRef, useState } from 'react';
import {
  createChart,
  IChartApi,
  ISeriesApi,
  CandlestickData,
  UTCTimestamp,
  WhitespaceData,
  Time,
} from 'lightweight-charts';
import { useMarketStore } from '../../stores/marketStore';

interface MarketChartProps {
  symbol?: string;
  market?: 'SPOT' | 'FUTURES';
  timeframe?: string;
  height?: number;
}

export const MarketChart: React.FC<MarketChartProps> = ({
  symbol = 'BTCUSDT',
  market = 'SPOT',
  timeframe = '1h',
  height = 500,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null);
  const [loading, setLoading] = useState(true);
  const { selectedSymbol, selectedMarket, selectedTimeframe, candles, setCandles, setCurrentPrice } = useMarketStore();

  const currentSymbol = symbol || selectedSymbol || 'BTCUSDT';
  const currentMarket = market || 'SPOT';
  const currentTimeframe = timeframe || '1h';

  useEffect(() => {
    if (!containerRef.current) return;

    // Create chart
    const chart = createChart(containerRef.current, {
      layout: {
        background: { color: '#101112' },
        textColor: '#eeeeee',
        fontFamily: 'JetBrains Mono, IBM Plex Mono, monospace',
        fontSize: 11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: '#25272a' },
        horzLines: { color: '#25272a' },
      },
      crosshair: {
        mode: 1, // CrosshairMode.Normal
        vertLine: { color: '#666a70', width: 1, style: 2 },
        horzLine: { color: '#666a70', width: 1, style: 2 },
      },
      rightPriceScale: {
        borderColor: '#303235',
        borderVisible: true,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      timeScale: {
        borderColor: '#303235',
        borderVisible: true,
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 12,
      },
      localization: {
        timeFormatter: (time: Time) => {
          const date = new Date((time as UTCTimestamp) * 1000);
          return date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false });
        },
      },
    });

    // Resize chart to container
    const resizeObserver = new ResizeObserver(() => {
      if (containerRef.current) {
        chart.resize(containerRef.current.clientWidth, height);
      }
    });
    resizeObserver.observe(containerRef.current);

    // Create main candlestick series
    const candleSeries = chart.addCandlestickSeries({
      upColor: '#a8d9c0',
      downColor: '#d99ca5',
      borderVisible: false,
      wickUpColor: '#a8d9c0',
      wickDownColor: '#d99ca5',
      priceScaleId: 'right',
    });

    // Create volume histogram series
    const volumeSeries = chart.addHistogramSeries({
      color: '#666a70',
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
      base: 0,
    });

    // Create volume price scale
    chart.priceScale('volume').applyOptions({
      borderVisible: false,
      scaleMargins: { top: 0.85, bottom: 0.05 },
      visible: false,
    });

    chartRef.current = chart;
    seriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    // Load initial data
    loadCandles();

    // Handle cleanup
    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [height]);

  const loadCandles = async () => {
    try {
      const response = await fetch(`/api/markets/${symbol}/candles?market=${market}&timeframe=${timeframe}&limit=500`);
      const data = await response.json();
      if (data.candles) {
        const formattedCandles = data.candles.map((c: any) => ({
          time: c.open_time / 1000,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }));
        seriesRef.current?.setData(formattedCandles);

        // Update volume
        const volumeData = data.candles.map((c: any) => ({
          time: c.open_time / 1000,
          value: c.volume,
          color: c.close >= c.open ? '#a8d9c0' : '#d99ca5',
        }));
        volumeSeriesRef.current?.setData(volumeData);

        // Update current price
        if (formattedCandles.length > 0) {
          const lastClose = formattedCandles[formattedCandles.length - 1].close;
          if (seriesRef.current) {
            seriesRef.current.setData(formattedCandles);
          }
        }
      }
      setLoading(false);
    } catch (e) {
      console.error('Failed to load candles:', e);
      setLoading(false);
    }
  };

  const handleCrosshairMove = (param: any) => {
    if (param.time) {
      const date = new Date((param.time as number) * 1000);
      // Could emit crosshair data for tooltip
    }
  };

  return (
    <div
      ref={containerRef}
      className="chart-container"
      style={{ width: '100%', height: `${height}px` }}
    >
      {loading && (
        <div className="flex items-center justify-center h-full">
          <div className="spinner"></div>
        </div>
      )}
    </div>
  );
};

export default MarketChart;