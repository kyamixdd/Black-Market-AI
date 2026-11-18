// API service for communicating with the BlackMarket AI backend.
import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { getApiAuthorization } from './localAuth';

const API_BASE_URL = 'http://127.0.0.1:8765';

class ApiService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: `${API_BASE_URL}/api`,
      timeout: 10000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      const authorization = getApiAuthorization()
      if (authorization) config.headers.set('Authorization', authorization.Authorization)
      return config
    })

    this.client.interceptors.response.use(
      (response) => response.data,
      (error: AxiosError) => {
        const message = error.response?.data?.detail || error.message || 'Unknown error';
        return Promise.reject(new Error(message));
      }
    );
  }

  // Markets
  async getMarkets() {
    return this.client.get('/markets');
  }

  async getMarketSymbols() {
    return this.client.get('/markets/symbols');
  }

  async getMarket(symbol: string, market: string = 'SPOT') {
    return this.client.get(`/markets/${symbol}`, { params: { market } });
  }

  async getCandles(symbol: string, market: string = 'SPOT', timeframe: string = '1h', limit = 200) {
    return this.client.get(`/markets/${symbol}/candles`, { params: { market, timeframe, limit } });
  }

  async getHeatmap() {
    return this.client.get('/markets/heatmap');
  }

  async getBreadth() {
    return this.client.get('/markets/breadth');
  }

  async getVolume() {
    return this.client.get('/markets/volume');
  }

  async getLongShort() {
    return this.client.get('/markets/long-short');
  }

  // Signals
  async getSignals(market?: string, strategy?: string) {
    const params: Record<string, string> = {};
    if (market) params.market = market;
    if (strategy) params.strategy = strategy;
    return this.client.get('/signals', { params });
  }

  async getSignalStats() {
    return this.client.get('/signals/stats');
  }

  // Portfolio
  async getPortfolioBalance() {
    return this.client.get('/portfolio/balance');
  }

  async getPortfolioSummary() {
    return this.client.get('/portfolio/summary');
  }

  // Positions
  async getPositions() {
    return this.client.get('/positions');
  }

  async getPosition(positionId: string) {
    return this.client.get(`/positions/${positionId}`);
  }

  // Trades
  async getTrades(limit = 100) {
    return this.client.get('/trades', { params: { limit } });
  }

  async getTradeStats() {
    return this.client.get('/trades/stats');
  }

  // Intelligence
  async getStrategyMetrics() {
    return this.client.get('/intelligence/strategies');
  }

  async getStrategyWeights() {
    return this.client.get('/intelligence/weights');
  }

  // Learning
  async getLearningStatus() {
    return this.client.get('/learning/status');
  }

  async getPredictions(limit = 100) {
    return this.client.get('/learning/predictions', { params: { limit } });
  }

  async getModels() {
    return this.client.get('/learning/models');
  }

  // Risk
  async getRiskStatus() {
    return this.client.get('/risk/status');
  }

  async getRiskAlerts() {
    return this.client.get('/risk/alerts');
  }

  // Activity
  async getActivity(limit = 100) {
    return this.client.get('/activity', { params: { limit } });
  }

  // Settings
  async getSettings() {
    return this.client.get('/settings');
  }

  async updateSettings(settings: Record<string, any>) {
    return this.client.post('/settings', settings);
  }

  // Health
  async getHealth() {
    const response = await axios.get(`${API_BASE_URL}/health`, { timeout: 10000 });
    return response.data;
  }

  async getSystemStatus() {
    return this.client.get('/system/status');
  }
}

export const api = new ApiService();