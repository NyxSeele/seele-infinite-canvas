import { API_BASE } from "../services/api"

const TICKET_KEY = "media_ticket"
const TICKET_EXP_KEY = "media_ticket_exp"

export function getMediaTicket() {
  const ticket = localStorage.getItem(TICKET_KEY)
  const exp = Number(localStorage.getItem(TICKET_EXP_KEY) || 0)
  if (!ticket) return ""
  if (exp && Date.now() / 1000 > exp - 60) return ""
  return ticket
}

export function setMediaTicket(ticket, expiresAt) {
  if (!ticket) {
    localStorage.removeItem(TICKET_KEY)
    localStorage.removeItem(TICKET_EXP_KEY)
    return
  }
  localStorage.setItem(TICKET_KEY, ticket)
  if (expiresAt) {
    localStorage.setItem(TICKET_EXP_KEY, String(expiresAt))
  }
}

export async function refreshMediaTicket(api) {
  const res = await api.get("/api/media/ticket")
  setMediaTicket(res.data.media_ticket, res.data.expires_at)
  return res.data.media_ticket
}

export function appendMediaTicket(url) {
  if (!url || typeof url !== "string") return url
  if (url.includes("mt=")) return url
  const ticket = getMediaTicket()
  if (!ticket) return url
  const sep = url.includes("?") ? "&" : "?"
  return `${url}${sep}mt=${encodeURIComponent(ticket)}`
}

export function stripMediaTicket(url) {
  if (!url || typeof url !== "string") return url
  const s = url.trim()
  if (s.startsWith("data:") || s.startsWith("blob:")) return s
  try {
    const absolute = url.startsWith("http")
      ? url
      : `${API_BASE}${url.startsWith("/") ? url : `/${url}`}`
    const parsed = new URL(absolute)
    parsed.searchParams.delete("mt")
    if (url.startsWith("http")) return parsed.toString()
    return `${parsed.pathname}${parsed.search}`
  } catch {
    return url.replace(/([?&])mt=[^&]*(?=&|$)/g, "$1").replace(/[?&]$/, "")
  }
}

/** API 提交用：相对 /api/view|/api/uploads 路径（无 mt、无 host） */
export function toRelativeMediaUrl(url) {
  if (!url || typeof url !== "string") return url
  const stripped = stripMediaTicket(url.trim())
  if (!stripped) return stripped
  if (stripped.startsWith("data:") || stripped.startsWith("blob:")) return stripped
  if (stripped.startsWith("http://") || stripped.startsWith("https://")) {
    try {
      const parsed = new URL(stripped)
      return `${parsed.pathname}${parsed.search}`
    } catch {
      return stripped
    }
  }
  return stripped.startsWith("/") ? stripped : `/${stripped}`
}

export function ensureMediaUrl(url) {
  if (!url) return url
  if (typeof url !== "string") return url
  const s = url.trim()
  if (!s) return s
  // base64 或 blob URL 不走媒体代理，避免被拼成相对路径触发错误 GET
  if (s.startsWith("data:") || s.startsWith("blob:")) return s
  if (!s.includes("/api/view") && !s.includes("/api/uploads")) return s
  const absolute = s.startsWith("http")
    ? stripMediaTicket(s)
    : `${API_BASE}${stripMediaTicket(s.startsWith("/") ? s : `/${s}`)}`
  return appendMediaTicket(absolute)
}

export function clearMediaTicket() {
  localStorage.removeItem(TICKET_KEY)
  localStorage.removeItem(TICKET_EXP_KEY)
}

export function hydrateNodeMediaFields(data) {
  if (!data || typeof data !== "object") return data
  const next = { ...data }
  const scalarKeys = [
    "uploadedImage",
    "imageUrl",
    "referenceImage",
    "referenceImageUrl",
    "videoUrl",
    "resultUrl",
  ]
  for (const key of scalarKeys) {
    if (next[key]) next[key] = ensureMediaUrl(next[key])
  }
  if (Array.isArray(next.results)) {
    next.results = next.results.map((u) => ensureMediaUrl(u))
  }
  if (Array.isArray(next.referenceImages)) {
    next.referenceImages = next.referenceImages.map((r) =>
      r?.imageUrl ? { ...r, imageUrl: ensureMediaUrl(r.imageUrl) } : r
    )
  }
  if (next.referenceRef?.imageUrl) {
    next.referenceRef = {
      ...next.referenceRef,
      imageUrl: ensureMediaUrl(next.referenceRef.imageUrl),
    }
  }
  if (next.keyframes) {
    const kf = { ...next.keyframes }
    for (const slot of ["first", "last"]) {
      if (kf[slot]?.imageUrl) {
        kf[slot] = { ...kf[slot], imageUrl: ensureMediaUrl(kf[slot].imageUrl) }
      }
    }
    next.keyframes = kf
  }
  if (Array.isArray(next.freeRefs)) {
    next.freeRefs = next.freeRefs.map((r) =>
      r?.imageUrl ? { ...r, imageUrl: ensureMediaUrl(r.imageUrl) } : r
    )
  }
  return next
}
