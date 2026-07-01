import { useCallback, useEffect, useRef, useState } from "react"
import {
  createCanvasComment,
  deleteCanvasCommentMessage,
  listCanvasComments,
  replyCanvasComment,
  updateCanvasCommentMessage,
} from "../../services/canvasApi"
import { canvasWsManager } from "../../services/canvasWs"

export function useCanvasComments(projectId, { enabled = true, userId = null } = {}) {
  const [threadsByNode, setThreadsByNode] = useState({})
  const [loading, setLoading] = useState(false)
  const threadsRef = useRef({})

  const applyThreads = useCallback((threads) => {
    const map = {}
    ;(threads || []).forEach((t) => {
      if (t?.node_id) map[t.node_id] = t
    })
    threadsRef.current = map
    setThreadsByNode(map)
  }, [])

  const refresh = useCallback(async () => {
    if (!projectId || !enabled) return
    setLoading(true)
    try {
      const threads = await listCanvasComments(projectId)
      applyThreads(threads)
    } catch (err) {
      console.warn("load comments failed", err)
    } finally {
      setLoading(false)
    }
  }, [projectId, enabled, applyThreads])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (!enabled || !projectId) return undefined
    const off = canvasWsManager.addListener((msg) => {
      if (msg?.project_id && msg.project_id !== projectId) return
      if (msg?.type === "comment_updated" && msg?.thread) {
        const t = msg.thread
        const missingAvatar = (t.messages || []).some(
          (m) => m?.author_id != null && !m?.author_avatar_url
        )
        if (missingAvatar) {
          refresh()
          return
        }
        setThreadsByNode((prev) => {
          const next = { ...prev, [t.node_id]: t }
          threadsRef.current = next
          return next
        })
      }
      if (msg?.type === "comment_deleted" && msg?.node_id) {
        setThreadsByNode((prev) => {
          const next = { ...prev }
          delete next[msg.node_id]
          threadsRef.current = next
          return next
        })
      }
    })
    return off
  }, [enabled, projectId, refresh])

  const getThread = useCallback((nodeId) => threadsByNode[nodeId] || null, [threadsByNode])

  const upsertThread = useCallback((thread) => {
    if (!thread?.node_id) return
    setThreadsByNode((prev) => {
      const next = { ...prev, [thread.node_id]: thread }
      threadsRef.current = next
      return next
    })
  }, [])

  const postComment = useCallback(
    async (nodeId, body, displayName, mentionedUserIds = []) => {
      if (!projectId) return null
      const existing = threadsRef.current[nodeId]
      const thread = existing?.id
        ? await replyCanvasComment(
          projectId,
          existing.id,
          body,
          displayName,
          mentionedUserIds
        )
        : await createCanvasComment(projectId, {
          node_id: nodeId,
          body,
          display_name: displayName,
          mentioned_user_ids: mentionedUserIds,
        })
      upsertThread(thread)
      return thread
    },
    [projectId, upsertThread]
  )

  const postReply = useCallback(
    async (threadId, body, displayName) => {
      const thread = await replyCanvasComment(projectId, threadId, body, displayName)
      upsertThread(thread)
      return thread
    },
    [projectId, upsertThread]
  )

  const editMessage = useCallback(
    async (messageId, body) => {
      const thread = await updateCanvasCommentMessage(projectId, messageId, body)
      upsertThread(thread)
      return thread
    },
    [projectId, upsertThread]
  )

  const removeMessage = useCallback(
    async (messageId) => {
      const res = await deleteCanvasCommentMessage(projectId, messageId)
      if (res?.deleted) {
        const nodeId = res.node_id || Object.keys(threadsRef.current).find((nid) =>
          threadsRef.current[nid]?.messages?.some((m) => m.id === messageId)
        )
        if (nodeId) {
          setThreadsByNode((prev) => {
            const next = { ...prev }
            delete next[nodeId]
            threadsRef.current = next
            return next
          })
        }
      } else if (res?.thread) {
        upsertThread(res.thread)
      }
      return res
    },
    [projectId, upsertThread]
  )

  const commentCount = useCallback(
    (nodeId) => threadsByNode[nodeId]?.messages?.length || 0,
    [threadsByNode]
  )

  return {
    threadsByNode,
    loading,
    refresh,
    getThread,
    postComment,
    postReply,
    editMessage,
    removeMessage,
    commentCount,
    userId,
  }
}
