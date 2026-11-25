import { recordDiagnostic } from './diagnosticLogger.ts'
import { getApiToken } from './localAuth.js'
import { backendEventStreamUrl, backendWebSocketUrl, isDesktopRuntime } from './backendClient.js'

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
      recordDiagnostic(state === 'disconnected' ? 'WARNING' : 'INFO', 'realtime.connection.state', {
        feature: 'realtime', function: 'setState', detail: `${previous} → ${state}`,
      })
      this.emit('stateChange', state)
    }
  }

  connect(): Promise<void> {
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
          this.emit('connected')
          if (!settled) { settled = true; resolve() }
        }
        source.onmessage = (message) => {
          try {
            const event: unknown = JSON.parse(message.data)
            if (typeof event !== 'object' || event === null || !('event_type' in event)) return
            const eventType = String(event.event_type)
            recordDiagnostic('DEBUG', 'realtime.sse.event', {
              feature: 'realtime', function: 'onmessage',
              detail: `${eventType} · ${String((event as { source?: unknown }).source ?? 'unknown source')}`,
            })
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
          recordDiagnostic('ERROR', 'realtime.sse.error', { feature: 'realtime', function: 'onerror', detail: 'Authenticated desktop event stream encountered a connection error' })
          this.setState('reconnecting')
          this.emit('error', 'The authenticated website event stream disconnected.')
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
          recordDiagnostic('INFO', 'realtime.websocket.open', { feature: 'realtime', function: 'onopen', detail: 'Socket opened; sending authentication handshake' })
          this.send({ type: 'authenticate', token })
        }

        socket.onclose = (event) => {
          if (this.ws !== socket) return
          recordDiagnostic('WARNING', 'realtime.websocket.close', { feature: 'realtime', function: 'onclose', detail: `code=${event.code} clean=${event.wasClean}` })
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
          recordDiagnostic('ERROR', 'realtime.websocket.error', { feature: 'realtime', function: 'onerror', detail: 'WebSocket transport error' })
          this.emit('error', error)
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
            recordDiagnostic(message.type === 'error' ? 'ERROR' : 'DEBUG', 'realtime.websocket.message', {
              feature: 'realtime', function: 'onmessage',
              detail: `${message.type}${message.channel ? ` · channel=${message.channel}` : ''}${message.detail ? ` · ${message.detail}` : ''}`,
            })
            if (message.type === 'authenticated') {
              this.setState('connected')
              this.reconnectAttempts = 0
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
          }
        }
      } catch (error) {
        this.setState('disconnected')
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
    recordDiagnostic('WARNING', 'realtime.reconnect.scheduled', {
      feature: 'realtime', function: 'scheduleReconnect', detail: `attempt=${this.reconnectAttempts} delay_ms=${delay}`,
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
    const data = message as { type?: string; channels?: string[] }
    recordDiagnostic('DEBUG', 'realtime.websocket.send', {
      feature: 'realtime', function: 'send',
      detail: `${data.type ?? 'message'}${data.channels ? ` · ${data.channels.join(',')}` : ''} · ${this.ws?.readyState === WebSocket.OPEN ? 'sent' : 'socket-not-open'}`,
    })
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
