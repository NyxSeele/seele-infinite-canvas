import api, { API_BASE } from "./api"

export function isBlobUrl(url) {
  return typeof url === "string" && url.startsWith("blob:")
}

function isDataUrl(url) {
  return typeof url === "string" && url.startsWith("data:")
}

/** 将 data:/blob: 参考图上传为 http URL，避免 POST body 过大或 431 */
export async function resolveReferenceUrlForApi(url) {
  if (!url || typeof url !== "string") return null
  const trimmed = url.trim()
  if (!trimmed) return null
  if (trimmed.startsWith("http") && !isDataUrl(trimmed)) {
    try {
      const parsed = new URL(trimmed)
      if (parsed.pathname.startsWith("/api/uploads/") || parsed.pathname.startsWith("/uploads/")) {
        return parsed.pathname.split("?")[0]
      }
    } catch {
      /* keep original */
    }
    return trimmed
  }
  if (!isDataUrl(trimmed) && !isBlobUrl(trimmed)) return trimmed

  const res = await fetch(trimmed)
  const blob = await res.blob()
  const ext = blob.type?.includes("png") ? "png" : "jpg"
  const file = new File([blob], `ref.${ext}`, { type: blob.type || "image/jpeg" })
  return uploadImageFile(file)
}

export async function dataUrlToFile(dataUrl, filename = "avatar.jpg") {
  const res = await fetch(dataUrl)
  const blob = await res.blob()
  const ext = blob.type?.includes("png") ? "png" : "jpg"
  return new File([blob], filename.replace(/\.[^.]+$/, `.${ext}`), {
    type: blob.type || "image/jpeg",
  })
}

/** 上传图片，返回可持久化的绝对 URL（禁止 blob:） */
export async function uploadImageFile(file) {
  const formData = new FormData()
  formData.append("file", file)
  const res = await api.post("/api/upload/image", formData, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  const path = res.data?.url
  if (!path) throw new Error("上传未返回 url")
  if (path.startsWith("http")) return path
  return `${API_BASE}${path.startsWith("/") ? path : `/${path}`}`
}
