function storageKey(projectId) {
  return `canvas-comment-seen:${projectId}`
}

function isFromOthers(msg, currentUserId) {
  if (currentUserId == null) return true
  return Number(msg.author_id) !== Number(currentUserId)
}

function messagesAfterSeen(messages, seen) {
  if (!seen?.lastMessageId) return messages
  const idx = messages.findIndex((m) => m.id === seen.lastMessageId)
  if (idx < 0) return messages
  return messages.slice(idx + 1)
}

function messageMentionsUser(msg, currentUserId) {
  if (!currentUserId || !msg) return false
  const ids = msg.mentioned_user_ids || []
  return ids.some((id) => Number(id) === Number(currentUserId))
}

export function getCommentSeenState(projectId) {
  if (!projectId) return {}
  try {
    const raw = localStorage.getItem(storageKey(projectId))
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

export function markNodeCommentsSeen(projectId, nodeId, thread) {
  if (!projectId || !nodeId) return
  const messages = thread?.messages || []
  const last = messages[messages.length - 1]
  const state = getCommentSeenState(projectId)
  const prev = state[nodeId] || {}
  state[nodeId] = {
    ...prev,
    lastMessageId: last?.id || null,
    count: messages.length,
    at: Date.now(),
  }
  try {
    localStorage.setItem(storageKey(projectId), JSON.stringify(state))
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent("canvas-comment-read-changed", { detail: { projectId } }))
}

export function markMentionsSeen(projectId, nodeId, messageIds) {
  if (!projectId || !nodeId || !messageIds?.length) return
  const state = getCommentSeenState(projectId)
  const prev = state[nodeId] || {}
  const seenMentionIds = [...new Set([...(prev.seenMentionIds || []), ...messageIds])]
  state[nodeId] = { ...prev, seenMentionIds }
  try {
    localStorage.setItem(storageKey(projectId), JSON.stringify(state))
  } catch {
    /* ignore */
  }
}

/** 红点：自上次打开后，他人发了新消息 */
export function isNodeCommentUnread(projectId, nodeId, thread, currentUserId) {
  const messages = thread?.messages || []
  if (!projectId || !nodeId || !messages.length) return false
  const seen = getCommentSeenState(projectId)[nodeId]
  const newMsgs = messagesAfterSeen(messages, seen)
  if (!seen) {
    return messages.some((m) => isFromOthers(m, currentUserId))
  }
  return newMsgs.some((m) => isFromOthers(m, currentUserId))
}

/** 高光：@ 当前用户且尚未看过的高亮消息 id */
export function getMentionHighlightIds(projectId, nodeId, thread, currentUserId) {
  if (!projectId || !nodeId || !currentUserId) return []
  const messages = thread?.messages || []
  if (!messages.length) return []
  const seenMentionIds = new Set(getCommentSeenState(projectId)[nodeId]?.seenMentionIds || [])
  return messages
    .filter((m) => messageMentionsUser(m, currentUserId) && !seenMentionIds.has(m.id))
    .map((m) => m.id)
}

export function countUnreadCommentNodes(projectId, threadsByNode, currentUserId) {
  if (!projectId || !threadsByNode) return 0
  return Object.entries(threadsByNode).filter(([nodeId, thread]) => (
    isNodeCommentUnread(projectId, nodeId, thread, currentUserId)
  )).length
}
