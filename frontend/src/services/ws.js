import { API_BASE } from "./api"

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
  }

  connect() {
    const token = localStorage.getItem("access_token")
    if (!token) return
    this.shouldConnect = true
    if (this.ws?.readyState === WebSocket.OPEN) return
    if (this.ws?.readyState === WebSocket.CONNECTING) return

    const wsBase = API_BASE.replace(/^http/, "ws")
    this.ws = new WebSocket(
      `${wsBase}/ws?clientId=${encodeURIComponent(this.clientId)}&token=${encodeURIComponent(token)}`
    )

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.listeners.forEach((fn) => fn(data))
      } catch {
        /* ignore parse errors */
      }
    }

    this.ws.onclose = () => {
      this.ws = null
      if (this.shouldConnect) {
        this.reconnectTimer = setTimeout(() => this.connect(), 3000)
      }
    }

    this.ws.onerror = () => {
      this.ws?.close()
    }
  }

  addListener(fn) {
    this.listeners.add(fn)
    return () => this.listeners.delete(fn)
  }

  disconnect() {
    this.shouldConnect = false
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    if (this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
  }

  getClientId() {
    return this.clientId
  }
}

export const wsManager = new WebSocketManager()
