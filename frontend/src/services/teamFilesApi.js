import api from "./api"

export async function listTeamFiles({ q } = {}) {
  const res = await api.get("/api/r2/files", {
    params: q ? { q } : undefined,
  })
  return res.data
}

export async function presignTeamFileUpload({
  filename,
  content_type,
  size_bytes,
  description,
}) {
  const res = await api.post("/api/r2/presign-upload", {
    filename,
    content_type,
    size_bytes,
    description: description || null,
  })
  return res.data
}

export async function registerTeamFile(payload) {
  const res = await api.post("/api/r2/files", payload)
  return res.data
}

export async function getTeamFileDownloadUrl(fileId) {
  const res = await api.get(`/api/r2/files/${fileId}/download`)
  return res.data
}

export async function deleteTeamFile(fileId) {
  const res = await api.delete(`/api/r2/files/${fileId}`)
  return res.data
}

export async function addTeamFileToAssets(fileId, { target, team_id }) {
  const res = await api.post(`/api/r2/files/${fileId}/add-to-assets`, {
    target,
    team_id: team_id || null,
  })
  return res.data
}

/** PUT file directly to R2 via presigned URL (browser → R2). */
export function uploadToPresignedUrl(uploadUrl, file, contentType, onProgress, timeoutMs = 180_000) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest()
    xhr.open("PUT", uploadUrl)
    xhr.timeout = timeoutMs
    xhr.setRequestHeader("Content-Type", contentType || file.type || "application/octet-stream")
    xhr.upload.onprogress = (evt) => {
      if (!evt.lengthComputable || typeof onProgress !== "function") return
      onProgress(Math.round((evt.loaded / evt.total) * 100))
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) resolve()
      else reject(new Error(`上传失败 HTTP ${xhr.status}`))
    }
    xhr.onerror = () => reject(new Error("直传 R2 网络错误，请检查网络后重试"))
    xhr.ontimeout = () => reject(new Error("直传 R2 超时，请换较小图片或稍后重试"))
    xhr.send(file)
  })
}
