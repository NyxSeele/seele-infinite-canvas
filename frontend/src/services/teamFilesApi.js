import api from "./api"
import {
  getUploadCapabilities,
  mediaClientFor,
  shouldUseMediaBase,
} from "./mediaApi"

/** Use server proxy for files larger than this (bytes). */
export const TEAM_FILE_SERVER_UPLOAD_THRESHOLD = 32 * 1024 * 1024

/** Direct PUT timeout for small files (ms). */
export const TEAM_FILE_PRESIGN_TIMEOUT_MS = 10 * 60 * 1000

export async function listTeamFiles({ q, limit = 200, offset = 0 } = {}) {
  const res = await api.get("/api/r2/files", {
    params: {
      ...(q ? { q } : {}),
      limit,
      offset,
    },
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

export async function uploadTeamFileViaServer(
  file,
  { description, teamId, onProgress } = {},
) {
  const client = await mediaClientFor("team")
  const form = new FormData()
  form.append("file", file)
  if (description) form.append("description", description)
  if (teamId) form.append("team_id", teamId)
  const res = await client.post("/api/r2/upload", form, {
    headers: { "Content-Type": "multipart/form-data" },
    timeout: 0,
    onUploadProgress: (evt) => {
      if (!evt.total || typeof onProgress !== "function") return
      onProgress(Math.round((evt.loaded / evt.total) * 100))
    },
  })
  return res.data
}

/** Rehost /api/view|/api/uploads studio videos into team file space. */
export async function importTeamVideoFromUrl(source_url, { description, teamId } = {}) {
  const res = await api.post("/api/r2/import-video", {
    source_url,
    description: description || null,
    team_id: teamId || null,
  })
  return res.data
}

export async function getTeamFileDownloadUrl(fileId) {
  const res = await api.get(`/api/r2/files/${fileId}/download`)
  return res.data
}

function triggerBlobDownload(blob, filename) {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement("a")
  anchor.href = url
  anchor.download = filename || "download"
  anchor.rel = "noopener"
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

export async function downloadTeamFile(file, { onProgress } = {}) {
  const fileId = file?.id
  if (!fileId) throw new Error("缺少文件 ID")

  if (file?.storage_backend === "local") {
    const client = await mediaClientFor("team")
    const res = await client.get(`/api/r2/files/${fileId}/download`, {
      responseType: "blob",
      timeout: 0,
      onDownloadProgress: (evt) => {
        if (!evt.total || typeof onProgress !== "function") return
        onProgress(Math.round((evt.loaded / evt.total) * 100))
      },
    })
    triggerBlobDownload(res.data, file.filename)
    return { ok: true }
  }

  const data = await getTeamFileDownloadUrl(fileId)
  if (data?.download_url) {
    window.open(data.download_url, "_blank", "noopener,noreferrer")
    return data
  }
  throw new Error("未返回下载地址")
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
export function uploadToPresignedUrl(
  uploadUrl,
  file,
  contentType,
  onProgress,
  timeoutMs = TEAM_FILE_PRESIGN_TIMEOUT_MS,
) {
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
    xhr.ontimeout = () => reject(new Error("直传 R2 超时，将尝试通过服务器上传"))
    xhr.send(file)
  })
}

/**
 * Smart upload: local backend → AutoDL server upload; else R2 presign with server fallback.
 */
export async function uploadTeamFile(file, { description, teamId, onProgress } = {}) {
  await getUploadCapabilities()
  const contentType = file.type || "application/octet-stream"
  const desc = description?.trim() || null

  if (shouldUseMediaBase("team")) {
    return uploadTeamFileViaServer(file, {
      description: desc,
      teamId,
      onProgress,
    })
  }

  try {
    const presign = await presignTeamFileUpload({
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
      description: desc,
    })
    await uploadToPresignedUrl(
      presign.upload_url,
      file,
      presign.content_type || contentType,
      onProgress,
    )
    return registerTeamFile({
      key: presign.key,
      filename: file.name,
      content_type: contentType,
      size_bytes: file.size,
      description: desc,
    })
  } catch (err) {
    if (typeof onProgress === "function") onProgress(0)
    return uploadTeamFileViaServer(file, { description: desc, teamId, onProgress })
  }
}
