/**
 * 安全关闭 WebSocket，避免在 CONNECTING 阶段直接 close 触发
 * "WebSocket is closed before the connection is established"。
 */
export function safeCloseWebSocket(ws) {
  if (!ws) return

  const state = ws.readyState
  if (state === WebSocket.CLOSED || state === WebSocket.CLOSING) return

  ws.onmessage = null
  ws.onerror = null

  if (state === WebSocket.CONNECTING) {
    ws.onopen = () => {
      try {
        ws.close(1000, "cancelled")
      } catch {
        /* ignore */
      }
    }
    ws.onclose = null
    return
  }

  ws.onopen = null
  ws.onclose = null
  try {
    ws.close(1000, "closed")
  } catch {
    /* ignore */
  }
}
