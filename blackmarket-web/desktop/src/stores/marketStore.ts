// Market data store using Zustand.
import { create } from 'zustand';

interface MarketState {
  // Market data
  markets: Record<string, any>;
  symbols: any[];
  selectedSymbol: string | null;
  selectedMarket: 'SPOT' | 'FUTURES';
  selectedTimeframe: string;

  // Chart data
  candles: Record<string, any[]>;
  currentPrice: number | null;

  // Analytics
  heatmap: any[];
  breadth: any;
  volumeStats: any;
  longShortStats: any;

  // Loading states
  loading: boolean;
  error: string | null;

  // Actions
  setMarkets: (markets: any[]) => void;
  setSymbols: (symbols: any[]) => void;
  setSelectedSymbol: (symbol: string | null, market?: 'SPOT' | 'FUTURES') => void;
  setSelectedMarket: (market: 'SPOT' | 'FUTURES') => void;
  setSelectedTimeframe: (timeframe: string) => void;
  setCandles: (key: string, candles: any[]) => void;
  setCurrentPrice: (price: number | null) => void;
  setHeatmap: (heatmap: any[]) => void;
  setBreadth: (breadth: any) => void;
  setVolumeStats: (stats: any) => void;
  setLongShortStats: (stats: any) => void;
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
}

export const useMarketStore = create<MarketState>((set, get) => ({
  // Initial state
  markets: {},
  symbols: [],
  selectedSymbol: 'BTCUSDT',
  selectedMarket: 'SPOT',
  selectedTimeframe: '1h',
  candles: {},
  currentPrice: null,
  heatmap: [],
  breadth: null,
  volumeStats: null,
  longShortStats: null,
  loading: false,
  error: null,

  // Actions
  setMarkets: (markets) => set({ markets }),
  setSymbols: (symbols) => set({ symbols }),
  setSelectedSymbol: (symbol, market = 'SPOT') => set({ selectedSymbol: symbol, selectedMarket: market }),
  setSelectedMarket: (market) => set({ selectedMarket: market }),
  setSelectedTimeframe: (timeframe) => set({ selectedTimeframe: timeframe }),
  setCandles: (key, candles) => set((state) => ({ candles: { ...state.candles, [key]: candles } })),
  setCurrentPrice: (price) => set({ currentPrice: price }),
  setHeatmap: (heatmap) => set({ heatmap }),
  setBreadth: (breadth) => set({ breadth }),
  setVolumeStats: (stats) => set({ volumeStats: stats }),
  setLongShortStats: (stats) => set({ longShortStats: stats }),
  setLoading: (loading) => set({ loading }),
  setError: (error) => set({ error }),
}));