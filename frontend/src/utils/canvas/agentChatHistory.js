import {
  deleteAgentChatHistoryApi,
  generateAgentChatTitleApi,
  listAgentChatHistoryApi,
  loadAgentConversation,
  saveAgentChatHistoryApi,
  saveAgentConversation,
} from "../../services/agentApi"
import {
  activeChatArchiveId,
  readLocalConversation,
  writeLocalConversation,
} from "./agentConversationStorage"

const HISTORY_KEY_PREFIX = "agent-chat-history-"
const MAX_ENTRIES = 30
const titleGenerationInflight = new Set()

function storageKey(projectId) {
  return `${HISTORY_KEY_PREFIX}${projectId}`
}

function readLocalList(projectId) {
  if (!projectId) return []
  try {
    const raw = localStorage.getItem(storageKey(projectId))
    const parsed = raw ? JSON.parse(raw) : []
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function writeLocalList(projectId, list) {
  if (!projectId) return
  localStorage.setItem(storageKey(projectId), JSON.stringify(list.slice(0, MAX_ENTRIES)))
}

function titleFromMessages(messages) {
  const firstUser = (messages || []).find((m) => m.role === "user")
  const text = (firstUser?.content || "").trim()
  if (!text) return "未命名对话"
  return text.length > 28 ? `${text.slice(0, 28)}…` : text
}

function parseUpdatedAt(entry) {
  if (entry?.updatedAt != null && Number.isFinite(entry.updatedAt)) {
    return entry.updatedAt
  }
  if (entry?.updated_at) {
    const parsed = Date.parse(entry.updated_at)
    if (Number.isFinite(parsed)) return parsed
  }
  return null
}

function normalizeEntry(entry) {
  if (!entry) return null
  const parsedAt = parseUpdatedAt(entry)
  return {
    id: entry.id,
    projectId: entry.project_id || entry.projectId,
    title: entry.title || titleFromMessages(entry.messages),
    messages: Array.isArray(entry.messages) ? entry.messages : [],
    updatedAt: parsedAt ?? Date.now(),
  }
}

function sortEntries(list) {
  return [...list].sort((a, b) => (b.updatedAt || 0) - (a.updatedAt || 0))
}

async function migrateLocalToServer(projectId) {
  const local = readLocalList(projectId)
  if (local.length === 0) return
  const token = localStorage.getItem("access_token")
  if (!token) return
  try {
    const remote = await listAgentChatHistoryApi(projectId)
    if (remote.length > 0) return
    for (const item of local.slice(0, MAX_ENTRIES)) {
      if (!item?.messages?.length) continue
      await saveAgentChatHistoryApi(projectId, item.messages, {
        id: item.id,
        title: item.title,
      })
    }
    writeLocalList(projectId, [])
  } catch {
    /* 离线或后端未迁移时保留本地 */
  }
}

export async function listAgentChatHistory(projectId) {
  if (!projectId) return []
  const token = localStorage.getItem("access_token")
  let remote = []
  if (token) {
    try {
      await migrateLocalToServer(projectId)
      remote = await listAgentChatHistoryApi(projectId)
    } catch {
      remote = []
    }
  }

  const normalized = sortEntries(remote.map(normalizeEntry).filter(Boolean))

  if (token) {
    try {
      const conv = await loadAgentConversation(projectId)
      const msgs = Array.isArray(conv?.messages) ? conv.messages : []
      if (msgs.length > 0) {
        const activeId = activeChatArchiveId(projectId)
        const existingActive = normalized.find((e) => e.id === activeId)
        const localActive = readLocalList(projectId).find((e) => e.id === activeId)
        const activeUpdatedAt = existingActive?.updatedAt
          ?? parseUpdatedAt(localActive)
          ?? parseUpdatedAt(conv)
          ?? Date.now()
        const withoutActive = normalized.filter((e) => e.id !== activeId)
        const activeEntry = normalizeEntry({
          id: activeId,
          project_id: projectId,
          title: existingActive?.title || localActive?.title || titleFromMessages(msgs),
          messages: msgs,
          updatedAt: activeUpdatedAt,
        })
        return sortEntries([activeEntry, ...withoutActive])
      }
    } catch {
      /* 合并当前会话失败时仍返回归档列表 */
    }
  }

  if (normalized.length > 0) return normalized

  const localConv = readLocalConversation(projectId)
  if (localConv.length > 0) {
    return sortEntries([
      normalizeEntry({
        id: activeChatArchiveId(projectId),
        project_id: projectId,
        title: titleFromMessages(localConv),
        messages: localConv,
        updatedAt: Date.now(),
      }),
      ...readLocalList(projectId).map(normalizeEntry).filter(Boolean),
    ])
  }

  if (!token) {
    return sortEntries(readLocalList(projectId).map(normalizeEntry).filter(Boolean))
  }
  return normalized
}

async function maybeGenerateAiTitle(projectId, entryId, messages, fallbackTitle) {
  const token = localStorage.getItem("access_token")
  if (!token || !projectId || !entryId || !messages?.length) return

  const inflightKey = `${projectId}:${entryId}`
  if (titleGenerationInflight.has(inflightKey)) return
  titleGenerationInflight.add(inflightKey)

  try {
    const aiTitle = await generateAgentChatTitleApi(messages)
    if (!aiTitle || aiTitle === fallbackTitle) return
    await saveAgentChatHistoryApi(projectId, messages, {
      id: entryId,
      title: aiTitle,
    })
    const list = readLocalList(projectId)
    const idx = list.findIndex((e) => e.id === entryId)
    if (idx >= 0) {
      list[idx] = { ...list[idx], title: aiTitle }
      writeLocalList(projectId, list)
    }
    window.dispatchEvent(new CustomEvent("agent-chat-title-updated", {
      detail: { projectId, entryId },
    }))
  } catch {
    /* 标题生成失败时保留 fallback */
  } finally {
    titleGenerationInflight.delete(inflightKey)
  }
}

export async function syncAgentSession(projectId, messages) {
  if (!projectId || !Array.isArray(messages) || messages.length === 0) return

  writeLocalConversation(projectId, messages)

  const token = localStorage.getItem("access_token")
  if (!token) {
    await saveAgentChatHistory(projectId, messages, {
      id: activeChatArchiveId(projectId),
    })
    return
  }

  try {
    await saveAgentConversation(projectId, messages)
  } catch (err) {
    console.warn("[agent] save conversation failed:", err)
  }

  try {
    await saveAgentChatHistory(projectId, messages, {
      id: activeChatArchiveId(projectId),
    })
  } catch (err) {
    console.warn("[agent] sync chat history failed:", err)
  }
}

export async function loadAgentSession(projectId) {
  if (!projectId) return []
  const token = localStorage.getItem("access_token")
  if (token) {
    try {
      const data = await loadAgentConversation(projectId)
      if (Array.isArray(data?.messages) && data.messages.length > 0) {
        writeLocalConversation(projectId, data.messages)
        return data.messages
      }
    } catch (err) {
      console.warn("[agent] load conversation failed:", err)
    }
  }
  return readLocalConversation(projectId)
}

export async function clearAgentSession(projectId) {
  if (!projectId) return
  writeLocalConversation(projectId, [])
  const token = localStorage.getItem("access_token")
  if (token) {
    try {
      await saveAgentConversation(projectId, [])
    } catch {
      /* ignore */
    }
  }
}

export async function saveAgentChatHistory(projectId, messages, { id, title } = {}) {
  if (!projectId || !Array.isArray(messages) || messages.length === 0) return null
  const entryId = id || `chat_${Date.now()}`
  const fallbackTitle = titleFromMessages(messages)
  const list = readLocalList(projectId)
  const existing = list.find((e) => e.id === entryId)
  const isNew = !existing
  const next = normalizeEntry({
    id: entryId,
    project_id: projectId,
    title: title || existing?.title || fallbackTitle,
    messages,
    updatedAt: Date.now(),
  })

  const token = localStorage.getItem("access_token")
  if (token) {
    try {
      const saved = await saveAgentChatHistoryApi(projectId, messages, {
        id: entryId,
        title: next.title,
      })
      const normalized = normalizeEntry(saved) || next
      if (isNew || next.title === fallbackTitle) {
        void maybeGenerateAiTitle(projectId, entryId, messages, fallbackTitle)
      }
      return normalized
    } catch {
      /* fallback local */
    }
  }

  const idx = list.findIndex((e) => e.id === entryId)
  if (idx >= 0) list[idx] = next
  else list.unshift(next)
  writeLocalList(projectId, list)
  if (isNew || next.title === fallbackTitle) {
    void maybeGenerateAiTitle(projectId, entryId, messages, fallbackTitle)
  }
  return next
}

export async function deleteAgentChatHistory(projectId, entryId) {
  const token = localStorage.getItem("access_token")
  if (token) {
    try {
      await deleteAgentChatHistoryApi(projectId, entryId)
      return
    } catch {
      /* fallback local */
    }
  }
  const list = readLocalList(projectId).filter((e) => e.id !== entryId)
  writeLocalList(projectId, list)
}
