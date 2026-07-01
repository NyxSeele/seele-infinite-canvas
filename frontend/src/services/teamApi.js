import api from "./api"

export async function fetchMyTeams() {
  const res = await api.get("/api/teams/mine")
  return res.data
}

export async function createTeam(name) {
  const res = await api.post("/api/teams", { name })
  return res.data
}

export async function updateTeam(teamId, payload) {
  const res = await api.patch(`/api/teams/${teamId}`, payload)
  return res.data
}

export async function listTeamMembers(teamId) {
  const res = await api.get(`/api/teams/${teamId}/members`)
  return Array.isArray(res.data) ? res.data : []
}

export async function updateTeamMember(teamId, userId, payload) {
  const res = await api.patch(`/api/teams/${teamId}/members/${userId}`, payload)
  return res.data
}

export async function addTeamMember(teamId, { username, role = "editor" }) {
  const res = await api.post(`/api/teams/${teamId}/members`, { username, role })
  return res.data
}

export async function removeTeamMember(teamId, userId) {
  await api.delete(`/api/teams/${teamId}/members/${userId}`)
}

export async function leaveTeam(teamId) {
  await api.post(`/api/teams/${teamId}/leave`)
}

export async function getTeamInviteLink(teamId) {
  const res = await api.get(`/api/teams/${teamId}/invite-link`)
  return res.data
}

export async function createTeamInviteLink(teamId, settings = null) {
  const res = settings
    ? await api.post(`/api/teams/${teamId}/invite-link`, { settings })
    : await api.post(`/api/teams/${teamId}/invite-link`)
  return res.data
}

export async function previewTeamInvite(token) {
  const res = await api.get(`/api/teams/invites/${encodeURIComponent(token)}`)
  return res.data
}

export async function joinTeamByInvite(token) {
  const res = await api.post("/api/teams/join", { token })
  return res.data
}
