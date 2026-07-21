import { useCallback, useEffect, useRef, useState } from "react"
import {
  acquireCanvasSession,
  heartbeatCanvasSession,
  joinCanvasSession,
  releaseCanvasSession,
} from "../../services/canvasApi"
import { canvasWsManager } from "../../services/canvasWs"
import { isNetworkError } from "../../components/canvas/taskNetworkError"
import { createRateLimitBackoffState } from "../../utils/canvas/rateLimitBackoff"
import { useAuth } from "../../contexts/AuthContext"
import { getT } from "../../utils/locale"
import { readDisplayName } from "../../utils/canvas/commentUserDisplay"

function personLabel(who) {
  if (!who) return getT()("canvas.session.otherUser")
  return who.display_name || who.username || getT()("canvas.session.otherUser")
}

const HEARTBEAT_MS = 25000
const HEARTBEAT_NETWORK_FAIL_MAX = 2
const VIEWER_LOCK_POLL_MS = 12000
const EDIT_REQUEST_TIMEOUT_MS = 30000

/**
 * 画布协作：join 不抢锁；仅编辑者 acquire + heartbeat。
 * 查看者可主动请求编辑权；编辑者退出后查看者自动接权。
 */
export function useCanvasSession(projectId, { enabled = true, onRemoteUpdate = null } = {}) {
  const { user } = useAuth()
  const sessionIdRef = useRef(null)
  const onRemoteUpdateRef = useRef(onRemoteUpdate)
  const isEditorRef = useRef(false)
  const lockHolderRef = useRef(null)
  const heartbeatTimerRef = useRef(null)
  const editRequestTimerRef = useRef(null)
  const heartbeatFailRef = useRef(0)
  const heartbeatRateLimitRef = useRef(createRateLimitBackoffState())
  const [isEditor, setIsEditor] = useState(false)
  const [lockHolder, setLockHolder] = useState(null)
  const [kickedNotice, setKickedNotice] = useState(null)
  const [remoteSyncNotice, setRemoteSyncNotice] = useState(null)
  const [editorPromotedNotice, setEditorPromotedNotice] = useState(null)
  const [sessionReady, setSessionReady] = useState(false)
  const [incomingEditRequest, setIncomingEditRequest] = useState(null)
  const [editRequestPending, setEditRequestPending] = useState(false)
  const [editRequestNotice, setEditRequestNotice] = useState(null)

  useEffect(() => {
    onRemoteUpdateRef.current = onRemoteUpdate
  }, [onRemoteUpdate])

  useEffect(() => {
    isEditorRef.current = isEditor
  }, [isEditor])

  useEffect(() => {
    lockHolderRef.current = lockHolder
  }, [lockHolder])

  const clearEditRequestTimer = useCallback(() => {
    if (editRequestTimerRef.current) {
      clearTimeout(editRequestTimerRef.current)
      editRequestTimerRef.current = null
    }
  }, [])

  const release = useCallback(async () => {
    const sid = sessionIdRef.current
    if (!projectId || !sid) return
    sessionIdRef.current = null
    try {
      await releaseCanvasSession(projectId, sid)
    } catch {
      /* ignore */
    }
  }, [projectId])

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current)
      heartbeatTimerRef.current = null
    }
  }, [])

  const applyEditorState = useCallback((acquireRes) => {
    sessionIdRef.current = acquireRes.session_id
    setLockHolder(acquireRes.lock || null)
    setIsEditor(true)
    setKickedNotice(null)
    setIncomingEditRequest(null)
    setEditRequestPending(false)
    clearEditRequestTimer()
  }, [clearEditRequestTimer])

  const applyViewerState = useCallback((lock) => {
    sessionIdRef.current = null
    setLockHolder(lock || null)
    setIsEditor(false)
  }, [])

  const startHeartbeat = useCallback(() => {
    stopHeartbeat()
    heartbeatFailRef.current = 0
    heartbeatRateLimitRef.current.reset()
    heartbeatTimerRef.current = setInterval(async () => {
      const sid = sessionIdRef.current
      if (!sid || !projectId) return
      if (heartbeatRateLimitRef.current.paused) return
      try {
        await heartbeatCanvasSession(projectId, sid)
        heartbeatFailRef.current = 0
        heartbeatRateLimitRef.current.reset()
      } catch (err) {
        if (isNetworkError(err) || heartbeatRateLimitRef.current.apply(err)) {
          heartbeatFailRef.current += 1
          if (heartbeatFailRef.current < HEARTBEAT_NETWORK_FAIL_MAX) return
        }
        setIsEditor(false)
        sessionIdRef.current = null
        heartbeatFailRef.current = 0
        heartbeatRateLimitRef.current.reset()
        setKickedNotice(getT()("canvas.session.expired"))
      }
    }, HEARTBEAT_MS)
  }, [projectId, stopHeartbeat])

  const tryAcquireAsEditor = useCallback(
    async (releasedBy, { showNotice = true } = {}) => {
      if (!enabled || !projectId || !user || isEditorRef.current) return false
      try {
        const join = await joinCanvasSession(projectId)
        const lock = join.lock || null
        const lockUserId = lock ? Number(lock.user_id) : null
        const myId = Number(user.id)
        if (lockUserId != null && lockUserId !== myId) {
          setLockHolder(lock)
          return false
        }
        const res = await acquireCanvasSession(projectId, {
          display_name: readDisplayName(user?.username),
        })
        const afterJoin = await joinCanvasSession(projectId)
        const afterLock = afterJoin.lock || null
        if (afterLock && Number(afterLock.user_id) !== myId) {
          applyViewerState(afterLock)
          return false
        }
        applyEditorState(res)
        startHeartbeat()
        if (showNotice) {
          const who = personLabel(releasedBy || lockHolderRef.current)
          setEditorPromotedNotice(getT()("canvas.session.editorPromoted", { who }))
        }
        return true
      } catch (err) {
        console.warn("auto acquire editor failed", err)
        return false
      }
    },
    [enabled, projectId, user, applyEditorState, applyViewerState, startHeartbeat]
  )

  const requestEditPermission = useCallback(() => {
    if (!enabled || !projectId || !user || isEditorRef.current || editRequestPending) return false
    const sent = canvasWsManager.send({ type: "edit_request" })
    if (!sent) {
      setEditRequestNotice(getT()("canvas.session.editRequestFailed"))
      return false
    }
    setEditRequestPending(true)
    setEditRequestNotice(null)
    clearEditRequestTimer()
    editRequestTimerRef.current = setTimeout(() => {
      setEditRequestPending(false)
      setEditRequestNotice(getT()("canvas.session.editRequestTimeout"))
      editRequestTimerRef.current = null
    }, EDIT_REQUEST_TIMEOUT_MS)
    return true
  }, [enabled, projectId, user, editRequestPending, clearEditRequestTimer])

  const respondEditRequest = useCallback(
    (approved) => {
      const req = incomingEditRequest
      const sid = sessionIdRef.current
      if (!req?.request_id || !sid) return false
      const sent = canvasWsManager.send({
        type: "edit_request_response",
        request_id: req.request_id,
        approved: !!approved,
        session_id: sid,
      })
      if (sent) setIncomingEditRequest(null)
      return sent
    },
    [incomingEditRequest]
  )

  useEffect(() => {
    if (!enabled || !projectId || !user) {
      setIsEditor(false)
      setLockHolder(null)
      setSessionReady(false)
      stopHeartbeat()
      clearEditRequestTimer()
      return undefined
    }

    let cancelled = false
    let lockPollTimer = null

    const init = async () => {
      try {
        const join = await joinCanvasSession(projectId)
        if (cancelled) return

        const lock = join.lock || null
        const lockUserId = lock ? Number(lock.user_id) : null
        const isMine = lockUserId != null && lockUserId === Number(user.id)

        if (!lock || isMine) {
          const res = await acquireCanvasSession(projectId, {
            display_name: readDisplayName(user?.username),
          })
          if (cancelled) return
          applyEditorState(res)
          startHeartbeat()
        } else {
          applyViewerState(lock)
        }
      } catch (err) {
        console.warn("join canvas session failed", err)
        if (!cancelled) {
          applyViewerState(null)
        }
      } finally {
        if (!cancelled) setSessionReady(true)
      }
    }

    init()
    canvasWsManager.connect(projectId)

    lockPollTimer = setInterval(async () => {
      if (cancelled || isEditorRef.current) return
      try {
        const join = await joinCanvasSession(projectId)
        if (cancelled || isEditorRef.current) return
        const lock = join.lock || null
        if (!lock && lockHolderRef.current) {
          const prev = lockHolderRef.current
          setLockHolder(null)
          await tryAcquireAsEditor(prev)
        } else if (lock) {
          setLockHolder(lock)
        }
      } catch {
        /* ignore poll errors */
      }
    }, VIEWER_LOCK_POLL_MS)

    const offWs = canvasWsManager.addListener((msg) => {
      const myId = Number(user.id)

      if (msg?.type === "session_kicked") {
        const mySid = sessionIdRef.current
        const kickedSid = msg?.kicked?.session_id
        if (mySid && kickedSid && mySid === kickedSid) {
          sessionIdRef.current = null
          setIsEditor(false)
          setLockHolder(msg?.by || null)
          const by = personLabel(msg?.by)
          setKickedNotice(getT()("canvas.session.takenOver", { by }))
        }
        return
      }
      if (msg?.type === "session_released") {
        if (isEditorRef.current) return
        void tryAcquireAsEditor(msg?.released_by || null)
        return
      }
      if (msg?.type === "canvas_updated" && msg?.project_id === projectId) {
        if (isEditorRef.current) return
        const by = personLabel(msg?.by)
        onRemoteUpdateRef.current?.(msg)
        setRemoteSyncNotice(getT()("canvas.session.collaboratorUpdated", { by }))
        return
      }
      if (msg?.type === "edit_request" && isEditorRef.current) {
        setIncomingEditRequest(msg)
        return
      }
      if (msg?.type === "edit_request_response") {
        const requesterId = Number(msg?.requester?.user_id)
        if (requesterId !== myId) {
          if (msg?.status === "approved" && msg?.lock) {
            setLockHolder(msg.lock)
          }
          return
        }
        clearEditRequestTimer()
        setEditRequestPending(false)
        if (msg.status === "approved" && msg.session_id && msg.lock) {
          applyEditorState({ session_id: msg.session_id, lock: msg.lock })
          startHeartbeat()
          setEditRequestNotice(getT()("canvas.session.editRequestApproved"))
        } else if (msg.status === "denied") {
          setEditRequestNotice(getT()("canvas.session.editRequestDenied"))
        } else if (msg.status === "timeout") {
          setEditRequestNotice(getT()("canvas.session.editRequestTimeout"))
        } else if (msg.status === "error") {
          setEditRequestNotice(msg.message || getT()("canvas.session.editRequestFailed"))
        }
      }
    })

    return () => {
      cancelled = true
      stopHeartbeat()
      clearEditRequestTimer()
      clearInterval(lockPollTimer)
      offWs()
      release()
      canvasWsManager.disconnect()
      setSessionReady(false)
      setIncomingEditRequest(null)
      setEditRequestPending(false)
    }
  }, [
    enabled,
    projectId,
    user,
    release,
    applyEditorState,
    applyViewerState,
    startHeartbeat,
    stopHeartbeat,
    tryAcquireAsEditor,
    clearEditRequestTimer,
  ])

  useEffect(() => {
    if (!projectId) {
      canvasWsManager.disconnect()
    }
  }, [projectId])

  const clearKickedNotice = useCallback(() => setKickedNotice(null), [])
  const clearRemoteSyncNotice = useCallback(() => setRemoteSyncNotice(null), [])
  const clearEditorPromotedNotice = useCallback(() => setEditorPromotedNotice(null), [])
  const clearEditRequestNotice = useCallback(() => setEditRequestNotice(null), [])

  return {
    sessionId: sessionIdRef.current,
    getSessionId: () => sessionIdRef.current,
    isEditor,
    sessionReady,
    lockHolder,
    kickedNotice,
    remoteSyncNotice,
    editorPromotedNotice,
    incomingEditRequest,
    editRequestPending,
    editRequestNotice,
    clearKickedNotice,
    clearRemoteSyncNotice,
    clearEditorPromotedNotice,
    clearEditRequestNotice,
    requestEditPermission,
    respondEditRequest,
    release,
  }
}
