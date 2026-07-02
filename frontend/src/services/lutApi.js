import api from "./api"

export async function fetchLutConfig(projectId, scriptTableNodeId) {
  const res = await api.get(`/api/projects/${projectId}/lut`, {
    params: { script_table_node_id: scriptTableNodeId },
  })
  return res.data
}

export async function updateLutPreset(projectId, scriptTableNodeId, lutPreset) {
  const res = await api.put(`/api/projects/${projectId}/lut`, {
    script_table_node_id: scriptTableNodeId,
    lut_preset: lutPreset,
    clear_custom: true,
  })
  return res.data
}

export async function uploadLutCube(projectId, scriptTableNodeId, file) {
  const form = new FormData()
  form.append("file", file)
  const res = await api.post(
    `/api/lut/upload?project_id=${encodeURIComponent(projectId)}&script_table_node_id=${encodeURIComponent(scriptTableNodeId)}`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  )
  return res.data
}

export async function applyLutToAll(projectId, scriptTableNodeId) {
  const res = await api.post(`/api/projects/${projectId}/lut/apply-all`, {
    script_table_node_id: scriptTableNodeId,
  })
  return res.data
}

export async function submitVideoLutTask({
  projectId,
  scriptTableNodeId,
  videoUrl,
  nodeId,
  teamId,
}) {
  const res = await api.post("/api/tasks/video-lut", {
    project_id: projectId,
    script_table_node_id: scriptTableNodeId,
    video_url: videoUrl,
    node_id: nodeId,
    team_id: teamId,
  })
  return res.data
}

export const LUT_PRESET_IDS = [
  "cool_teal",
  "warm_orange_film",
  "natural_realistic",
  "high_contrast_commercial",
  "vintage_fade",
  "none",
]

export function isLutActive(data) {
  const preset = data?.lutPreset
  const custom = data?.lutCustomUrl
  if (custom) return true
  return preset && preset !== "none"
}
