import { API_BASE } from "./api"

export const AGENT_REQUEST_TIMEOUT_MS = 180000
export const AGENT_SSE_IDLE_TIMEOUT_MS = 30000

export class AgentQuotaError extends Error {
  constructor(message) {
    super(message)
    this.name = "AgentQuotaError"
  }
}

function authHeaders() {
  const headers = { "Content-Type": "application/json" }
  const token = localStorage.getItem("access_token")
  if (token) headers.Authorization = `Bearer ${token}`
  return headers
}

export async function loadAgentConversation(projectId) {
  const response = await fetch(`${API_BASE}/api/agent/conversation/${projectId}`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    throw new Error(`加载对话失败 (${response.status})`)
  }
  return response.json()
}

export async function saveAgentConversation(projectId, messages) {
  const response = await fetch(`${API_BASE}/api/agent/conversation/${projectId}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify({ messages }),
  })
  if (!response.ok) {
    throw new Error(`保存对话失败 (${response.status})`)
  }
  return response.json()
}

export async function listAgentChatHistoryApi(projectId) {
  const response = await fetch(`${API_BASE}/api/agent/chat-history/${projectId}`, {
    headers: authHeaders(),
  })
  if (!response.ok) {
    throw new Error(`加载聊天历史失败 (${response.status})`)
  }
  const data = await response.json()
  return Array.isArray(data?.entries) ? data.entries : []
}

export async function saveAgentChatHistoryApi(projectId, messages, { id, title } = {}) {
  const response = await fetch(`${API_BASE}/api/agent/chat-history/${projectId}`, {
    method: "PUT",
    headers: authHeaders(),
    body: JSON.stringify({ messages, id, title }),
  })
  if (!response.ok) {
    throw new Error(`保存聊天历史失败 (${response.status})`)
  }
  return response.json()
}

export async function deleteAgentChatHistoryApi(projectId, entryId) {
  const response = await fetch(
    `${API_BASE}/api/agent/chat-history/${projectId}/${encodeURIComponent(entryId)}`,
    { method: "DELETE", headers: authHeaders() }
  )
  if (!response.ok) {
    throw new Error(`删除聊天历史失败 (${response.status})`)
  }
  return response.json()
}

export async function generateAgentChatTitleApi(messages) {
  const response = await fetch(`${API_BASE}/api/agent/chat-title`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ messages }),
  })
  if (!response.ok) {
    throw new Error(`生成标题失败 (${response.status})`)
  }
  const data = await response.json()
  return (data?.title || "").trim()
}

export async function runAgentStream(body, { signal } = {}) {
  const response = await fetch(`${API_BASE}/api/agent/run`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(body),
    signal,
  })

  if (response.status === 402) {
    let message = "配额不足，请升级"
    try {
      const data = await response.json()
      message = data.detail || message
    } catch {
      /* ignore */
    }
    throw new AgentQuotaError(message)
  }

  if (!response.ok) {
    const text = await response.text().catch(() => "")
    throw new Error(text || `Agent 请求失败 (${response.status})`)
  }

  return response
}
