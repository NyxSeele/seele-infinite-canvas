import { useCallback, useEffect, useRef, useState } from "react"
import {
  fetchCanvasPresence,
  leaveCanvasPresence,
  pingCanvasPresence,
} from "../../services/canvasApi"
import { canvasWsManager } from "../../services/canvasWs"
import { readDisplayName } from "../../utils/canvas/commentUserDisplay"
import { AVATAR_CHANGED_EVENT } from "../../utils/canvas/userAvatar"

const PING_MS = 3000
const HTTP_POLL_MS = 3000

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
  const [avatarTick, setAvatarTick] = useState(0)
  const isEditorRef = useRef(isEditor)
  const usernameRef = useRef(username)

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
    const onAvatar = () => setAvatarTick((n) => n + 1)
    window.addEventListener(AVATAR_CHANGED_EVENT, onAvatar)
    return () => window.removeEventListener(AVATAR_CHANGED_EVENT, onAvatar)
  }, [])

  useEffect(() => {
    if (!enabled || !projectId) {
      setMembers([])
      return undefined
    }

    let cancelled = false

    const buildPayload = () => ({
      is_editor: isEditorRef.current,
      username: usernameRef.current,
      display_name: readDisplayName(usernameRef.current),
    })

    const sendPing = async () => {
      void avatarTick
      const payload = buildPayload()
      canvasWsManager.sendPresence(payload)
      try {
        const list = await pingCanvasPresence(projectId, payload)
        if (!cancelled) applyMembers(list)
      } catch (err) {
        console.warn("[presence] ping failed", err?.response?.status || err?.message)
      }
    }

    const pollHttp = async () => {
      try {
        const list = await fetchCanvasPresence(projectId)
        if (!cancelled) applyMembers(list)
      } catch (err) {
        console.warn("[presence] poll failed", err?.response?.status || err?.message)
      }
    }

    const refreshNow = () => {
      if (cancelled) return
      void sendPing()
      void pollHttp()
    }

    const off = canvasWsManager.addListener((msg) => {
      if (msg?.type === "presence_changed" && msg.project_id === projectId) {
        applyMembers(msg.members)
      }
    })

    const onVisible = () => {
      if (document.visibilityState === "visible") refreshNow()
    }
    document.addEventListener("visibilitychange", onVisible)

    refreshNow()
    const pingTimer = window.setInterval(sendPing, PING_MS)
    const httpTimer = window.setInterval(pollHttp, HTTP_POLL_MS)

    return () => {
      cancelled = true
      off()
      document.removeEventListener("visibilitychange", onVisible)
      window.clearInterval(pingTimer)
      window.clearInterval(httpTimer)
      void leaveCanvasPresence(projectId).catch(() => {})
    }
  }, [enabled, projectId, isEditor, username, applyMembers, avatarTick])

  return { members, count: members.length }
}
