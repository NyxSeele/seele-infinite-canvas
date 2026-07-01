import { API_BASE } from "../services/api"
import { appendMediaTicket, ensureMediaUrl } from "./mediaTicket"

/** 将 ComfyUI 输出项或 /api/view 路径拼成可播放 URL（含 subfolder + mt） */
export function buildMediaViewUrl(file) {
  if (!file) return ""
  let url = ""
  if (typeof file === "string") {
    const s = file.trim()
    if (!s) return ""
    if (s.startsWith("http://") || s.startsWith("https://")) url = s
    else if (s.startsWith("/api/view") || s.startsWith("/api/uploads")) {
      url = `${API_BASE}${s.startsWith("/") ? s : `/${s}`}`
    } else {
      const params = new URLSearchParams({ filename: s, type: "output" })
      url = `${API_BASE}/api/view?${params}`
    }
  } else {
    const filename = file.filename || ""
    if (!filename) return ""
    const type = file.type || "output"
    const subfolder = file.subfolder || ""
    const params = new URLSearchParams({ filename, type })
    if (subfolder) params.set("subfolder", subfolder)
    url = `${API_BASE}/api/view?${params}`
  }
  return ensureMediaUrl(url)
}

export function resolveTaskResultUrl(result) {
  if (!result) return ""
  const raw = String(result).trim()
  if (!raw) return ""
  if (raw.startsWith("http://") || raw.startsWith("https://")) {
    return ensureMediaUrl(raw)
  }
  if (raw.startsWith("/api/view") || raw.startsWith("/api/uploads")) {
    return ensureMediaUrl(`${API_BASE}${raw.startsWith("/") ? raw : `/${raw}`}`)
  }
  return ensureMediaUrl(`${API_BASE}${raw.startsWith("/") ? raw : `/${raw}`}`)
}
