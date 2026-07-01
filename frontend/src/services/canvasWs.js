import { API_BASE } from "./api"

class CanvasWsManager {
  constructor() {
    this.ws = null
    this.projectId = null
    this.listeners = new Set()
    this.reconnectTimer = null
    this.shouldConnect = false
    this.lastPresence = null
    this.lastPresenceEvent = null
  }

  connect(projectId) {
    const token = localStorage.getItem("access_token")
    if (!token || !projectId) return
    this.shouldConnect = true
    if (this.projectId && this.projectId !== projectId && this.ws) {
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
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

    const wsBase = API_BASE.replace(/^http/, "ws")
    this.ws = new WebSocket(
      `${wsBase}/ws/canvas/${encodeURIComponent(projectId)}?token=${encodeURIComponent(token)}`
    )

    this.ws.onopen = () => {
      if (this.lastPresence) {
        this.sendPresence(this.lastPresence)
      }
    }

    this.ws.onmessage = (event) => {
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

    this.ws.onclose = () => {
      this.ws = null
      if (this.shouldConnect && this.projectId) {
        this.reconnectTimer = setTimeout(() => this.connect(this.projectId), 3000)
      }
    }

    this.ws.onerror = () => {
      this.ws?.close()
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
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = null
    if (this.ws) {
      this.sendPresenceLeave()
      this.ws.onclose = null
      this.ws.close()
      this.ws = null
    }
    this.projectId = null
    this.lastPresenceEvent = null
  }
}

export const canvasWsManager = new CanvasWsManager()
