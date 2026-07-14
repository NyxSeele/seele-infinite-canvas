import api from "./api"

export async function createExportJob({ projectId, scriptTableNodeId }) {
  const res = await api.post("/api/exports", {
    project_id: projectId,
    script_table_node_id: scriptTableNodeId,
  })
  return res.data
}

export async function getExportJob(exportId) {
  const res = await api.get(`/api/exports/${exportId}`)
  return res.data
}

export function getExportDownloadUrl(exportId, accessToken = null) {
  const base = `/api/exports/${exportId}/download`
  if (!accessToken) return base
  const q = new URLSearchParams({ access_token: accessToken })
  return `${base}?${q.toString()}`
}
