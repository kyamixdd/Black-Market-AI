import { getApiToken } from './localAuth'

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

class WebSocketService {
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
    this.url = 'ws://127.0.0.1:8765/ws'
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
      this.state = state
      this.emit('stateChange', state)
    }
  }

  connect(): Promise<void> {
    if (typeof window !== 'undefined' && !('__TAURI_INTERNALS__' in window)) {
      if (this.eventSource?.readyState === EventSource.OPEN || this.eventSource?.readyState === EventSource.CONNECTING) return Promise.resolve()
      this.manuallyDisconnected = false
      this.setState(this.reconnectAttempts ? 'reconnecting' : 'connecting')
      return new Promise((resolve, reject) => {
        const source = new EventSource('/api/backend/events/stream')
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
            for (const [channel, callbacks] of this.subscriptions) {
              callbacks.forEach((callback) => callback(event))
              this.emit(channel, event)
            }
            this.emit('event', event)
          } catch (error) { this.emit('error', error) }
        }
        source.onerror = () => {
          if (this.eventSource !== source) return
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
