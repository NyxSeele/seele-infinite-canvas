import { useCallback, useEffect, useState } from "react"
import { useAuth } from "../contexts/AuthContext"
import { fetchNotifications } from "../services/notificationsApi"
import { canvasWsManager } from "../services/canvasWs"

export const NOTIFICATION_UNREAD_EVENT = "notifications-unread-changed"

export function emitNotificationUnread(count) {
  window.dispatchEvent(new CustomEvent(NOTIFICATION_UNREAD_EVENT, { detail: { count } }))
}

export function useNotificationUnread({ listenCanvasWs = false } = {}) {
  const { user } = useAuth()
  const [unread, setUnread] = useState(0)

  const refresh = useCallback(async () => {
    if (!user) {
      setUnread(0)
      return 0
    }
    try {
      const data = await fetchNotifications({ limit: 1 })
      const count = data?.unread_count ?? 0
      setUnread(count)
      emitNotificationUnread(count)
      return count
    } catch {
      return 0
    }
  }, [user])

  useEffect(() => {
    refresh()
  }, [user]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const onEvent = (e) => {
      if (typeof e.detail?.count === "number") setUnread(e.detail.count)
    }
    window.addEventListener(NOTIFICATION_UNREAD_EVENT, onEvent)
    return () => window.removeEventListener(NOTIFICATION_UNREAD_EVENT, onEvent)
  }, [])

  useEffect(() => {
    if (!listenCanvasWs || !user?.id) return undefined
    const off = canvasWsManager.addListener((msg) => {
      if (msg?.type !== "comment_mention") return
      if (Number(msg.recipient_user_id) !== Number(user.id)) return
      setUnread((prev) => {
        const next = prev + 1
        emitNotificationUnread(next)
        return next
      })
    })
    return off
  }, [listenCanvasWs, user?.id])

  return { unread, refresh, setUnread }
}
