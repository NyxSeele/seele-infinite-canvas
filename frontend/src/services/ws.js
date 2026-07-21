import { getWsBase } from "./api"
import { safeCloseWebSocket } from "../utils/wsSafeClose"

class WebSocketManager {
  constructor() {
    this.ws = null
    this.clientId =
      typeof crypto !== "undefined" && crypto.randomUUID
        ? crypto.randomUUID()
        : `client-${Date.now()}`
    this.listeners = new Set()
    this.reconnectTimer = null
    this.shouldConnect = false
    this.connectGeneration = 0
  }

  _dropSocket() {
    if (!this.ws) return
    safeCloseWebSocket(this.ws)
    this.ws = null
  }

  connect() {
    const token = localStorage.getItem("access_token")
    if (!token) return
    this.shouldConnect = true
    if (this.ws?.readyState === WebSocket.OPEN) return
    if (this.ws?.readyState === WebSocket.CONNECTING) return

    this._dropSocket()
    const generation = ++this.connectGeneration
    const wsBase = getWsBase()
    const url = `${wsBase}/ws?clientId=${encodeURIComponent(this.clientId)}&token=${encodeURIComponent(token)}`
    let ws
    try {
      ws = new WebSocket(url)
    } catch (err) {
      console.warn("task WebSocket connect failed", err)
      return
    }
    this.ws = ws

    ws.onmessage = (event) => {
      if (generation !== this.connectGeneration || this.ws !== ws) return
      try {
        const data = JSON.parse(event.data)
        this.listeners.forEach((fn) => fn(data))
      } catch {
        /* ignore parse errors */
      }
    }

    ws.onclose = () => {
      if (this.ws === ws) this.ws = null
      if (generation !== this.connectGeneration) return
      if (this.shouldConnect) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000)
      }
    }

    ws.onerror = () => {
      if (generation !== this.connectGeneration || this.ws !== ws) return
      safeCloseWebSocket(ws)
    }
  }

  addListener(fn) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  disconnect() {
    this.shouldConnect = false
    this.connectGeneration += 1
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this._dropSocket()
  }

  /** token 刷新后强制用新 token 重连 */
  reconnect() {
    const keep = this.shouldConnect
    this.connectGeneration += 1
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this._dropSocket()
    if (keep) {
      this.shouldConnect = true
      this.connect()
    }
  }

  getClientId() {
    return this.clientId
  }
}

export const wsManager = new WebSocketManager()
