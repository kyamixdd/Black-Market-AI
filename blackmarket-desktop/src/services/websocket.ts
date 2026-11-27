import { getApiToken } from './localAuth.js'
import { backendEventStreamUrl, backendWebSocketUrl, isDesktopRuntime } from './backendClient.js'
import { recordFrontendDiagnostic } from './frontendDiagnostics.ts'

type EventCallback = (data: unknown) => void

type ConnectionState = 'connecting' | 'connected' | 'disconnected' | 'reconnecting'
export type WebSocketChannel =
  | 'market_updates'
  | 'price_updates'
  | 'signal_updates'
  | 'portfolio_updates'
  | 'position_updates'
  | 'risk_updates'
  | 'system_events'
  | 'learning_updates'

interface WebSocketMessage {
  type: string
  channel?: string
  event?: unknown
  channels?: string[]
  detail?: string
}

export class WebSocketService {
  private ws: WebSocket | null = null
  private eventSource: EventSource | null = null
  private readonly url: string
  private reconnectAttempts = 0
  private reconnectDelay = 1000
  private maxReconnectDelay = 30000
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private subscriptions = new Map<string, Set<EventCallback>>()
  private listeners = new Map<string, Set<EventCallback>>()
  private state: ConnectionState = 'disconnected'
  private pingInterval: ReturnType<typeof setInterval> | null = null
  private manuallyDisconnected = false

  constructor() {
    this.url = backendWebSocketUrl()
  }

  get connectionState(): ConnectionState {
    return this.state
  }

  on(eventName: string, callback: EventCallback): () => void {
    const callbacks = this.listeners.get(eventName) ?? new Set<EventCallback>()
    callbacks.add(callback)
    this.listeners.set(eventName, callbacks)
    return () => {
      callbacks.delete(callback)
      if (callbacks.size === 0) this.listeners.delete(eventName)
    }
  }

  private emit(eventName: string, data?: unknown) {
    this.listeners.get(eventName)?.forEach((callback) => callback(data))
  }

  private setState(state: ConnectionState) {
    if (this.state !== state) {
      const previous = this.state
      this.state = state
      recordFrontendDiagnostic({
        level: state === 'connected' ? 'INFO' : state === 'disconnected' ? 'WARNING' : 'INFO',
        event: 'frontend_realtime_state_changed',
        operation: 'realtime.connection_state',
        status: state === 'connected' ? 'SUCCESS' : state === 'disconnected' ? 'WARNING' : 'SUCCESS',
        detail: `${previous} -> ${state}; transport=${isDesktopRuntime() ? 'websocket' : 'sse'}`,
        recommendation: state === 'disconnected' ? 'Check backend readiness and event-stream logs; automatic reconnect remains enabled.' : undefined,
      })
      this.emit('stateChange', state)
    }
  }

  connect(): Promise<void> {
    recordFrontendDiagnostic({
      level: 'INFO',
      event: 'frontend_realtime_connect_started',
      operation: 'realtime.connect',
      status: 'SUCCESS',
      endpoint: isDesktopRuntime() ? this.url : backendEventStreamUrl(),
      detail: `transport=${isDesktopRuntime() ? 'authenticated_websocket' : 'authenticated_sse'}`,
    })
    if (!isDesktopRuntime()) {
      if (this.eventSource?.readyState === EventSource.OPEN || this.eventSource?.readyState === EventSource.CONNECTING) return Promise.resolve()
      this.manuallyDisconnected = false
      this.setState(this.reconnectAttempts ? 'reconnecting' : 'connecting')
      return new Promise((resolve, reject) => {
        const source = new EventSource(backendEventStreamUrl())
        this.eventSource = source
        let settled = false
        source.onopen = () => {
          if (this.eventSource !== source) return
          this.reconnectAttempts = 0
          this.setState('connected')
          recordFrontendDiagnostic({
            level: 'INFO',
            event: 'frontend_realtime_connected',
            operation: 'realtime.connect_sse',
            status: 'SUCCESS',
            endpoint: backendEventStreamUrl(),
          })
          this.emit('connected')
          if (!settled) { settled = true; resolve() }
        }
        source.onmessage = (message) => {
          try {
            const event: unknown = JSON.parse(message.data)
            if (typeof event !== 'object' || event === null || !('event_type' in event)) return
            const eventType = String(event.event_type)
            const channels: Record<string, WebSocketChannel[]> = {
              MARKET_DATA: ['price_updates'],
              MARKET_SNAPSHOT: ['market_updates'],
              SIGNAL_PROPOSED: ['signal_updates'],
              SIGNAL_VALIDATED: ['signal_updates'],
              SIGNAL_REJECTED: ['signal_updates', 'system_events'],
              SIGNAL_EXPIRED: ['signal_updates'],
              PREDICTION: ['learning_updates'],
              TRADE_EXECUTED: ['portfolio_updates', 'position_updates'],
              TRADE_PARTIALLY_FILLED: ['portfolio_updates', 'position_updates'],
              TRADE_CLOSED: ['portfolio_updates', 'position_updates'],
              TRADE_CANCELLED: ['portfolio_updates', 'system_events'],
              TRADE_REJECTED: ['portfolio_updates', 'system_events'],
              POSITION_OPENED: ['position_updates', 'portfolio_updates'],
              POSITION_CLOSED: ['position_updates', 'portfolio_updates'],
              ORDER_PLACED: ['portfolio_updates'],
              ORDER_FILLED: ['portfolio_updates', 'position_updates'],
              LEARNING_UPDATE: ['learning_updates'],
              MODEL_TRAINED: ['learning_updates'],
              MODEL_PROMOTED: ['learning_updates'],
              MODEL_ROLLED_BACK: ['learning_updates'],
              RISK_ALERT: ['risk_updates', 'system_events'],
              SYSTEM_HEALTH: ['system_events'],
              NOTIFICATION: ['system_events'],
            }
            for (const channel of channels[eventType] ?? []) {
              this.subscriptions.get(channel)?.forEach((callback) => callback(event))
              this.emit(channel, event)
            }
            this.emit('event', event)
          } catch (error) { this.emit('error', error) }
        }
        source.onerror = () => {
          if (this.eventSource !== source) return
          this.setState('reconnecting')
          this.emit('error', 'The authenticated website event stream disconnected.')
          recordFrontendDiagnostic({
            level: 'ERROR',
            event: 'frontend_realtime_connection_failed',
            operation: 'realtime.connect_sse',
            status: 'FAILURE',
            endpoint: backendEventStreamUrl(),
            recommendation: 'Verify the hosted backend event-stream proxy and service health; the client will reconnect automatically.',
          })
          if (!settled) { settled = true; reject(new Error('Website event stream unavailable')) }
          source.close()
          this.eventSource = null
          if (!this.manuallyDisconnected) this.scheduleReconnect()
        }
      })
    }
    if (this.ws?.readyState === WebSocket.OPEN || this.ws?.readyState === WebSocket.CONNECTING) {
      return Promise.resolve()
    }

    this.manuallyDisconnected = false
    this.setState(this.reconnectAttempts ? 'reconnecting' : 'connecting')
    const token = getApiToken()
    if (!token) {
      this.setState('disconnected')
      recordFrontendDiagnostic({
        level: 'ERROR',
        event: 'frontend_realtime_authentication_missing',
        operation: 'realtime.authenticate',
        status: 'FAILURE',
        recommendation: 'Wait for the Tauri supervisor to provide the current per-launch API token, then retry.',
      })
      if (!this.manuallyDisconnected) this.scheduleReconnect()
      return Promise.reject(new Error('The authenticated desktop API session is unavailable.'))
    }

    return new Promise((resolve, reject) => {
      let settled = false
      try {
        const socket = new WebSocket(this.url)
        this.ws = socket

        socket.onopen = () => {
          if (this.ws !== socket) return
          this.send({ type: 'authenticate', token })
        }

        socket.onclose = () => {
          if (this.ws !== socket) return
          this.ws = null
          this.stopPing()
          this.setState('disconnected')
          this.emit('disconnected')
          if (!settled) {
            settled = true
            reject(new Error('WebSocket connection closed before opening'))
          }
          if (!this.manuallyDisconnected) this.scheduleReconnect()
        }

        socket.onerror = (error) => {
          this.emit('error', error)
          recordFrontendDiagnostic({
            level: 'ERROR',
            event: 'frontend_realtime_connection_failed',
            operation: 'realtime.connect_websocket',
            status: 'FAILURE',
            endpoint: this.url,
            recommendation: 'Check backend WebSocket readiness and local API authentication; reconnect is attempted automatically.',
          })
          if (!settled) {
            settled = true
            reject(new Error('WebSocket connection failed'))
          }
        }

        socket.onmessage = (event) => {
          try {
            const parsed: unknown = JSON.parse(String(event.data))
            if (typeof parsed !== 'object' || parsed === null) return
            const message = parsed as WebSocketMessage
            if (message.type === 'authenticated') {
              this.setState('connected')
              this.reconnectAttempts = 0
              recordFrontendDiagnostic({
                level: 'INFO',
                event: 'frontend_realtime_connected',
                operation: 'realtime.authenticate',
                status: 'SUCCESS',
                endpoint: this.url,
              })
              this.startPing()
              this.send({ type: 'subscribe', channels: [...this.subscriptions.keys()] })
              this.emit('connected')
              if (!settled) {
                settled = true
                resolve()
              }
              return
            }
            this.handleMessage(message)
          } catch (error) {
            this.emit('error', error)
            recordFrontendDiagnostic({
              level: 'ERROR',
              event: 'frontend_realtime_connection_failed',
              operation: 'realtime.connect_websocket',
              status: 'FAILURE',
              endpoint: this.url,
              recommendation: 'Check the authenticated backend WebSocket endpoint and backend stream diagnostics.',
            })
          }
        }
      } catch (error) {
        this.setState('disconnected')
        recordFrontendDiagnostic({
          level: 'ERROR',
          event: 'frontend_realtime_connection_failed',
          operation: 'realtime.create_websocket',
          status: 'FAILURE',
          endpoint: this.url,
          detail: error instanceof Error ? error.message : 'Unable to create the WebSocket connection.',
          recommendation: 'Verify the desktop runtime and backend WebSocket endpoint, then retry.',
        })
        if (!this.manuallyDisconnected) this.scheduleReconnect()
        reject(error)
      }
    })
  }

  private startPing() {
    this.stopPing()
    this.pingInterval = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) this.send({ type: 'ping' })
    }, 30000)
  }

  private stopPing() {
    if (this.pingInterval) {
      clearInterval(this.pingInterval)
      this.pingInterval = null
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer)
    const delay = Math.min(
      this.reconnectDelay * 2 ** this.reconnectAttempts,
      this.maxReconnectDelay,
    )
    this.reconnectAttempts += 1
    recordFrontendDiagnostic({
      level: 'WARNING',
      event: 'frontend_realtime_reconnect_scheduled',
      operation: 'realtime.schedule_reconnect',
      status: 'WARNING',
      duration_ms: delay,
      detail: `attempt=${this.reconnectAttempts}; maximum_delay_ms=${this.maxReconnectDelay}`,
    })
    this.setState('reconnecting')
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      void this.connect().catch((error: unknown) => this.emit('error', error))
    }, delay)
  }

  private handleMessage(message: WebSocketMessage) {
    if (message.type === 'pong' || message.type === 'subscribed' || message.type === 'unsubscribed') {
      this.emit(message.type, message)
      return
    }
    if (message.type === 'event' && message.channel) {
      this.subscriptions.get(message.channel)?.forEach((callback) => callback(message.event))
      this.emit(message.channel, message.event)
      this.emit('event', message.event)
    } else if (message.type === 'error') {
      this.emit('error', message.detail ?? 'The backend rejected a WebSocket message.')
    }
  }

  subscribe(channel: WebSocketChannel, callback: EventCallback): () => void {
    const callbacks = this.subscriptions.get(channel) ?? new Set<EventCallback>()
    callbacks.add(callback)
    this.subscriptions.set(channel, callbacks)
    if (callbacks.size === 1) this.send({ type: 'subscribe', channels: [channel] })
    return () => this.unsubscribe(channel, callback)
  }

  private unsubscribe(channel: string, callback: EventCallback) {
    const callbacks = this.subscriptions.get(channel)
    if (!callbacks) return
    callbacks.delete(callback)
    if (callbacks.size === 0) {
      this.subscriptions.delete(channel)
      this.send({ type: 'unsubscribe', channels: [channel] })
    }
  }

  private send(message: object) {
    if (this.ws?.readyState === WebSocket.OPEN) this.ws.send(JSON.stringify(message))
  }

  disconnect() {
    this.manuallyDisconnected = true
    this.eventSource?.close()
    this.eventSource = null
    this.stopPing()
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    const socket = this.ws
    this.ws = null
    socket?.close()
    this.setState('disconnected')
    this.subscriptions.clear()
  }

  destroy() {
    this.disconnect()
    this.listeners.clear()
  }
}

let wsInstance: WebSocketService | null = null

export function getWebSocket(): WebSocketService {
  if (!wsInstance) wsInstance = new WebSocketService()
  return wsInstance
}

export function destroyWebSocket() {
  wsInstance?.destroy()
  wsInstance = null
}
