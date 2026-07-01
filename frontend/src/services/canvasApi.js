import api from "./api"

export async function listCanvasProjects({ teamId = null } = {}) {
  const params = {}
  if (teamId) params.team_id = teamId
  const res = await api.get("/api/canvas/projects", { params })
  return res.data?.projects ?? []
}

export async function createCanvasProject({
  name = "未命名画布",
  canvas_data = null,
  team_id = null,
} = {}) {
  const body = {
    name,
    canvas_data: canvas_data ?? { nodes: [], edges: [] },
  }
  if (team_id) body.team_id = team_id
  const res = await api.post("/api/canvas/projects", body)
  return res.data
}

export async function loadCanvasProject(projectId) {
  const res = await api.get(`/api/canvas/projects/${projectId}`)
  return res.data
}

export async function fetchCanvasPresence(projectId) {
  const res = await api.get(`/api/canvas/projects/${projectId}/presence`)
  return res.data?.members ?? []
}

export async function pingCanvasPresence(
  projectId,
  { is_editor = false, username = "", display_name = "", avatar_url = "" } = {}
) {
  const res = await api.post(`/api/canvas/projects/${projectId}/presence/ping`, {
    is_editor,
    username,
    display_name,
    avatar_url,
  })
  return res.data?.members ?? []
}

export async function leaveCanvasPresence(projectId) {
  if (!projectId) return []
  const res = await api.post(`/api/canvas/projects/${projectId}/presence/leave`)
  return res.data?.members ?? []
}

export async function saveCanvasProject(
  projectId,
  { canvas_data, name, version, session_id, display_name } = {}
) {
  const body = {}
  if (canvas_data !== undefined) body.canvas_data = canvas_data
  if (name !== undefined) body.name = name
  if (version !== undefined) body.version = version
  const params = {}
  if (session_id) params.session_id = session_id
  if (display_name) params.display_name = display_name
  const res = await api.put(`/api/canvas/projects/${projectId}`, body, { params })
  return res.data
}

export async function deleteCanvasProject(projectId) {
  const res = await api.delete(`/api/canvas/projects/${projectId}`)
  return res.data
}

export async function migrateCanvasProjectToTeam(projectId, teamId) {
  const res = await api.post(`/api/canvas/projects/${projectId}/migrate-to-team`, {
    team_id: teamId,
  })
  return res.data
}

export async function joinCanvasSession(projectId) {
  const res = await api.post(`/api/canvas/projects/${projectId}/session/join`)
  return res.data
}

export async function acquireCanvasSession(projectId, { display_name } = {}) {
  const body = display_name ? { display_name } : {}
  const res = await api.post(`/api/canvas/projects/${projectId}/session`, body)
  return res.data
}

export async function listCanvasComments(projectId) {
  const res = await api.get(`/api/canvas/projects/${projectId}/comments`)
  return res.data?.threads ?? []
}

export async function createCanvasComment(projectId, { node_id, body, display_name, mentioned_user_ids }) {
  const res = await api.post(`/api/canvas/projects/${projectId}/comments`, {
    node_id,
    body,
    display_name,
    mentioned_user_ids: mentioned_user_ids || [],
  })
  return res.data?.thread
}

export async function replyCanvasComment(projectId, threadId, body, display_name, mentioned_user_ids) {
  const res = await api.post(
    `/api/canvas/projects/${projectId}/comments/${threadId}/replies`,
    { body, display_name, mentioned_user_ids: mentioned_user_ids || [] }
  )
  return res.data?.thread
}

export async function updateCanvasCommentMessage(projectId, messageId, body) {
  const res = await api.put(
    `/api/canvas/projects/${projectId}/comments/messages/${messageId}`,
    { body }
  )
  return res.data?.thread
}

export async function deleteCanvasCommentMessage(projectId, messageId) {
  const res = await api.delete(
    `/api/canvas/projects/${projectId}/comments/messages/${messageId}`
  )
  return res.data
}

export async function heartbeatCanvasSession(projectId, sessionId) {
  const res = await api.post(`/api/canvas/projects/${projectId}/session/heartbeat`, {
    session_id: sessionId,
  })
  return res.data
}

export async function releaseCanvasSession(projectId, sessionId) {
  const res = await api.delete(`/api/canvas/projects/${projectId}/session`, {
    params: { session_id: sessionId },
  })
  return res.data
}

export async function shareCanvas(payload) {
  const res = await api.post("/api/canvas/share", payload)
  return res.data
}

export async function loadCanvasShare(token) {
  const res = await api.get(`/api/canvas/share/${token}`)
  return res.data
}
