import api from "./api"

export async function fetchUserAssets({ kind = null, teamId = null } = {}) {
  const params = {}
  if (kind) params.kind = kind
  if (teamId) params.team_id = teamId
  const res = await api.get("/api/assets", { params })
  return res.data || []
}

export async function createUserAsset(payload) {
  const res = await api.post("/api/assets", payload)
  return res.data
}

export async function uploadUserAsset({
  file,
  name,
  kind,
  note,
  source_canvas_id,
  source_canvas_name,
  source_node_id,
  team_id,
}) {
  const form = new FormData()
  form.append("file", file)
  form.append("name", name)
  form.append("kind", kind || "image")
  if (note) form.append("note", note)
  if (source_canvas_id) form.append("source_canvas_id", source_canvas_id)
  if (source_canvas_name) form.append("source_canvas_name", source_canvas_name)
  if (source_node_id) form.append("source_node_id", source_node_id)
  if (team_id) form.append("team_id", team_id)
  const res = await api.post("/api/assets/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return res.data
}

export async function updateUserAsset(id, payload) {
  const res = await api.patch(`/api/assets/${id}`, payload)
  return res.data
}

export async function deleteUserAsset(id) {
  await api.delete(`/api/assets/${id}`)
}
