import { getWsBase } from "./api"
import { safeCloseWebSocket } from "../utils/wsSafeClose"

class CanvasWsManager {
  constructor() {
    this.ws = null
    this.projectId = null
    this.listeners = new Set()
    this.reconnectTimer = null
    this.shouldConnect = false
    this.connectGeneration = 0
    this.lastPresence = null
    this.lastPresenceEvent = null
  }

  _dropSocket() {
    if (!this.ws) return
    safeCloseWebSocket(this.ws)
    this.ws = null
  }

  connect(projectId) {
    const token = localStorage.getItem("access_token")
    if (!token || !projectId) return
    this.shouldConnect = true
    if (this.projectId && this.projectId !== projectId && this.ws) {
      this._dropSocket()
      this.lastPresenceEvent = null
    }
    this.projectId = projectId
    if (
      this.ws?.readyState === WebSocket.OPEN
      && this.projectId === projectId
    ) {
      return
    }
    if (this.ws?.readyState === WebSocket.CONNECTING && this.projectId === projectId) {
      return
    }

    this._dropSocket()
    const generation = ++this.connectGeneration
    const wsBase = getWsBase()
    const url = `${wsBase}/ws/canvas/${encodeURIComponent(projectId)}?token=${encodeURIComponent(token)}`
    let ws
    try {
      ws = new WebSocket(url)
    } catch (err) {
      console.warn("canvas WebSocket connect failed", err)
      return
    }
    this.ws = ws

    ws.onopen = () => {
      if (generation !== this.connectGeneration || this.ws !== ws) return
      if (this.lastPresence) {
        this.sendPresence(this.lastPresence)
      }
    }

    ws.onmessage = (event) => {
      if (generation !== this.connectGeneration || this.ws !== ws) return
      try {
        const data = JSON.parse(event.data)
        if (data?.type === "presence_changed") {
          this.lastPresenceEvent = data
        }
        this.listeners.forEach((fn) => fn(data))
      } catch {
        /* ignore */
      }
    }

    ws.onclose = () => {
      if (this.ws === ws) this.ws = null
      if (generation !== this.connectGeneration) return
      if (this.shouldConnect && this.projectId) {
        this.reconnectTimer = setTimeout(() => this.connect(this.projectId), 3000)
      }
    }

    ws.onerror = () => {
      if (generation !== this.connectGeneration || this.ws !== ws) return
      safeCloseWebSocket(ws)
    }
  }

  addListener(fn) {
    this.listeners.add(fn)
    if (this.lastPresenceEvent) {
      try {
        fn(this.lastPresenceEvent)
      } catch {
        /* ignore */
      }
    }
    return () => this.listeners.delete(fn)
  }

  sendPresence({ is_editor = false, username = "", display_name = "" } = {}) {
    this.lastPresence = { is_editor, username, display_name }
    if (this.ws?.readyState !== WebSocket.OPEN) return
    try {
      this.ws.send(JSON.stringify({
        type: "presence_ping",
        is_editor,
        username,
        display_name,
      }))
    } catch {
      /* ignore */
    }
  }

  sendPresenceLeave() {
    this.lastPresence = null
    if (this.ws?.readyState !== WebSocket.OPEN) return
    try {
      this.ws.send(JSON.stringify({ type: "presence_leave" }))
    } catch {
      /* ignore */
    }
  }

  send(payload) {
    if (this.ws?.readyState !== WebSocket.OPEN) return false
    try {
      this.ws.send(JSON.stringify(payload))
      return true
    } catch {
      return false
    }
  }

  disconnect() {
    this.shouldConnect = false
    this.connectGeneration += 1
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.sendPresenceLeave()
    }
    this._dropSocket()
    this.projectId = null
    this.lastPresenceEvent = null
  }

  /** token 刷新后强制用新 token 重连（保留 projectId） */
  reconnect() {
    const keep = this.shouldConnect
    const pid = this.projectId
    this.connectGeneration += 1
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    this._dropSocket()
    if (keep && pid) {
      this.shouldConnect = true
      this.projectId = pid
      this.connect(pid)
    }
  }
}

export const canvasWsManager = new CanvasWsManager()
