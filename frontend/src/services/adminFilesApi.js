import api from "./api"

export async function listAdminFiles(params = {}) {
  const res = await api.get("/api/admin/files", { params })
  return res.data
}

export async function getAdminFileStats() {
  const res = await api.get("/api/admin/files/stats")
  return res.data
}

export async function downloadAdminFile(file) {
  const fileId = file?.id
  if (!fileId) throw new Error("缺少文件 ID")
  const res = await api.get(`/api/admin/files/${encodeURIComponent(fileId)}/download`, {
    responseType: "blob",
  })
  return res.data
}
