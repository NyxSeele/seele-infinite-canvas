const CONVERSATION_KEY_PREFIX = "agent-conversation-"

export function activeChatArchiveId(projectId) {
  return `active_${projectId}`
}

function storageKey(projectId) {
  return `${CONVERSATION_KEY_PREFIX}${projectId}`
}

export function readLocalConversation(projectId) {
  if (!projectId) return []
  try {
    const raw = localStorage.getItem(storageKey(projectId))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

export function writeLocalConversation(projectId, messages) {
  if (!projectId) return
  try {
    if (!Array.isArray(messages) || messages.length === 0) {
      localStorage.removeItem(storageKey(projectId))
      return
    }
    localStorage.setItem(storageKey(projectId), JSON.stringify(messages))
  } catch {
    /* quota */
  }
}
