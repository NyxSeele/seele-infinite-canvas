import { useCallback, useEffect, useRef, useState } from "react"
import {
  fetchCanvasPresence,
  leaveCanvasPresence,
  pingCanvasPresence,
} from "../../services/canvasApi"
import { canvasWsManager } from "../../services/canvasWs"
import { readDisplayName } from "../../utils/canvas/commentUserDisplay"
import { AVATAR_CHANGED_EVENT } from "../../utils/canvas/userAvatar"
import { createRateLimitBackoffState } from "../../utils/canvas/rateLimitBackoff"

const PING_MS = 10000
/** HTTP 兜底拉取；有 WS presence_changed 时不必与 ping 同频 */
const HTTP_POLL_MS = 30000

function normalizeMembers(list) {
  if (!Array.isArray(list)) return []
  const seen = new Set()
  const out = []
  for (const raw of list) {
    if (!raw) continue
    const userId = raw.user_id ?? raw.userId
    if (userId == null || seen.has(userId)) continue
    seen.add(userId)
    out.push({
      ...raw,
      user_id: userId,
      username: raw.username || raw.display_name || "",
      display_name: raw.display_name || raw.username || "",
    })
  }
  return out
}

export function useCanvasPresence(projectId, { enabled = true, isEditor = false, username = "" } = {}) {
  const [members, setMembers] = useState([])
  const isEditorRef = useRef(isEditor)
  const usernameRef = useRef(username)
  const sendPingRef = useRef(null)

  useEffect(() => {
    isEditorRef.current = isEditor
  }, [isEditor])

  useEffect(() => {
    usernameRef.current = username
  }, [username])

  const applyMembers = useCallback((list) => {
    setMembers(normalizeMembers(list))
  }, [])

  useEffect(() => {
    const onAvatar = () => {
      // 头像变更只刷新一次 ping payload，勿重建整套 interval
      void sendPingRef.current?.()
    }
    window.addEventListener(AVATAR_CHANGED_EVENT, onAvatar)
    return () => window.removeEventListener(AVATAR_CHANGED_EVENT, onAvatar)
  }, [])

  useEffect(() => {
    if (!enabled || !projectId) {
      setMembers([])
      sendPingRef.current = null
      return undefined
    }

    let cancelled = false
    const rateLimit = createRateLimitBackoffState()

    const buildPayload = () => ({
      is_editor: isEditorRef.current,
      username: usernameRef.current,
      display_name: readDisplayName(usernameRef.current),
    })

    const sendPing = async () => {
      if (rateLimit.paused) return
      const payload = buildPayload()
      canvasWsManager.sendPresence(payload)
      try {
        const list = await pingCanvasPresence(projectId, payload)
        if (!cancelled) {
          rateLimit.reset()
          applyMembers(list)
        }
      } catch (err) {
        if (rateLimit.apply(err)) return
        console.warn("[presence] ping failed", err?.response?.status || err?.message)
      }
    }
    sendPingRef.current = sendPing

    const pollHttp = async () => {
      if (rateLimit.paused) return
      try {
        const list = await fetchCanvasPresence(projectId)
        if (!cancelled) {
          rateLimit.reset()
          applyMembers(list)
        }
      } catch (err) {
        if (rateLimit.apply(err)) return
        console.warn("[presence] poll failed", err?.response?.status || err?.message)
      }
    }

    const refreshNow = () => {
      if (cancelled) return
      void sendPing()
    }

    const off = canvasWsManager.addListener((msg) => {
      if (msg?.type === "presence_changed" && msg.project_id === projectId) {
        applyMembers(msg.members)
      }
    })

    const onVisible = () => {
      if (document.visibilityState === "visible") {
        refreshNow()
        void pollHttp()
      }
    }
    document.addEventListener("visibilitychange", onVisible)

    refreshNow()
    void pollHttp()
    const pingTimer = window.setInterval(sendPing, PING_MS)
    const httpTimer = window.setInterval(pollHttp, HTTP_POLL_MS)

    return () => {
      cancelled = true
      sendPingRef.current = null
      off()
      document.removeEventListener("visibilitychange", onVisible)
      window.clearInterval(pingTimer)
      window.clearInterval(httpTimer)
      void leaveCanvasPresence(projectId).catch(() => {})
    }
  }, [enabled, projectId, applyMembers])

  return { members, count: members.length }
}
