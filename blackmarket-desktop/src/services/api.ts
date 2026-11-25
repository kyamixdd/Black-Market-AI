// API service for communicating with the BlackMarket AI backend.
import axios, { AxiosInstance, AxiosError, InternalAxiosRequestConfig } from 'axios';
import { backendBaseUrl, isDesktopRuntime } from './backendClient.js';
import { getApiAuthorization } from './localAuth';
import { recordDiagnostic, recommendDiagnosticFix } from './diagnosticLogger';

const apiRequestStarts = new WeakMap<object, number>();

const API_BASE_URL = backendBaseUrl();

export type IntelligenceMode = 'balanced' | 'fast' | 'research' | 'conservative';
export type IntelligenceResponseDetail = 'brief' | 'normal' | 'detailed';

export interface IntelligenceConfig {
  mode: IntelligenceMode;
  max_tool_calls: number;
  memory_enabled: boolean;
  feedback_enabled: boolean;
  provider_enabled: boolean;
  response_detail: IntelligenceResponseDetail;
}

export type IntelligenceConfigUpdate = Partial<IntelligenceConfig> & { mode: IntelligenceMode };

class ApiService {
  private client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: API_BASE_URL,
      timeout: 10000,
      headers: { 'Content-Type': 'application/json' },
    });

    this.client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      const requestId = crypto.randomUUID()
      config.headers.set('X-Request-ID', requestId)
      apiRequestStarts.set(config, performance.now())
      recordDiagnostic('DEBUG', 'api.axios.request.started', { feature: 'api-client', function: 'axios.request', trace_id: requestId, detail: `${config.method?.toUpperCase() ?? 'GET'} ${(config.url ?? '').split('?')[0]}` })
      const authorization = getApiAuthorization()
      if (authorization) config.headers.set('Authorization', authorization.Authorization)
      return config
    })

    this.client.interceptors.response.use(
      (response) => {
        const config = response.config
        const started = apiRequestStarts.get(config) ?? performance.now()
        const requestId = String(config.headers?.['X-Request-ID'] ?? '')
        recordDiagnostic('INFO', 'api.axios.request.completed', { feature: 'api-client', function: 'axios.response', trace_id: requestId, duration_ms: Math.round(performance.now() - started), detail: `${response.config.method?.toUpperCase() ?? 'GET'} ${(response.config.url ?? '').split('?')[0]} · HTTP ${response.status}` })
        return response.data
      },
      (error: AxiosError) => {
        const message = error.response?.data?.detail || error.message || 'Unknown error';
        const config = error.config
        const started = config ? apiRequestStarts.get(config) ?? performance.now() : performance.now()
        const requestId = String(config?.headers?.['X-Request-ID'] ?? '')
        recordDiagnostic('ERROR', 'api.axios.request.failed', { feature: 'api-client', function: 'axios.response', trace_id: requestId, duration_ms: Math.round(performance.now() - started), detail: `${config?.method?.toUpperCase() ?? 'GET'} ${(config?.url ?? '').split('?')[0]} · HTTP ${error.response?.status ?? 'network'} · ${String(message)}`, ...recommendDiagnosticFix(message) })
        return Promise.reject(new Error(message));
      }
    );
  }

  async getMarkets() { return this.client.get('/markets'); }
  async getMarketSymbols() { return this.client.get('/markets/symbols'); }
  async getMarket(symbol: string, market: string = 'SPOT') { return this.client.get(`/markets/${symbol}`, { params: { market } }); }
  async getCandles(symbol: string, market: string = 'SPOT', timeframe: string = '1h', limit = 200) { return this.client.get(`/markets/${symbol}/candles`, { params: { market, timeframe, limit } }); }
  async getHeatmap() { return this.client.get('/markets/heatmap'); }
  async getBreadth() { return this.client.get('/markets/breadth'); }
  async getVolume() { return this.client.get('/markets/volume'); }
  async getLongShort() { return this.client.get('/markets/long-short'); }
  async getSignals(market?: string, strategy?: string) {
    const params: Record<string, string> = {};
    if (market) params.market = market;
    if (strategy) params.strategy = strategy;
    return this.client.get('/signals', { params });
  }
  async getSignalStats() { return this.client.get('/signals/stats'); }
  async getPortfolioBalance() { return this.client.get('/portfolio/balance'); }
  async getPortfolioSummary() { return this.client.get('/portfolio/summary'); }
  async getPositions() { return this.client.get('/positions'); }
  async getPosition(positionId: string) { return this.client.get(`/positions/${positionId}`); }
  async getTrades(limit = 100) { return this.client.get('/trades', { params: { limit } }); }
  async getTradeStats() { return this.client.get('/trades/stats'); }
  async getStrategyMetrics() { return this.client.get('/intelligence/strategies'); }
  async getStrategyWeights() { return this.client.get('/intelligence/weights'); }
  async getLearningStatus() { return this.client.get('/learning/status'); }
  async getPredictions(limit = 100) { return this.client.get('/learning/predictions', { params: { limit } }); }
  async getModels() { return this.client.get('/learning/models'); }
  async getRiskStatus() { return this.client.get('/risk/status'); }
  async getRiskAlerts() { return this.client.get('/risk/alerts'); }
  async getActivity(limit = 100) { return this.client.get('/activity', { params: { limit } }); }
  async getSettings() { return this.client.get('/settings'); }
  async updateSettings(settings: Record<string, any>) { return this.client.post('/settings', settings); }

  async getIntelligenceConfig(): Promise<IntelligenceConfig> {
    return this.client.get('/settings/intelligence');
  }

  async updateIntelligenceConfig(config: IntelligenceConfigUpdate): Promise<IntelligenceConfig> {
    return this.client.put('/settings/intelligence', config);
  }

  async getHealth() {
    const healthUrl = isDesktopRuntime() ? 'http://127.0.0.1:8765/health' : '/api/health';
    const response = await axios.get(healthUrl, { timeout: 10000 });
    return response.data;
  }
  async getSystemStatus() { return this.client.get('/system/status'); }
}

export const api = new ApiService();
