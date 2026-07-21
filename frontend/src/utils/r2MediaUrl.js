/** Cloudflare R2 canvas image URLs + local uploads via AutoDL public base. */

import { getMediaPublicBase, getUploadCapabilities } from "../services/mediaApi"

const CANVAS_KEY_PREFIX = "/canvas/"

let _r2PublicBase = ""

export function setR2PublicBase(base) {
  const trimmed = (base || "").trim().replace(/\/$/, "")
  if (trimmed) _r2PublicBase = trimmed
}

export function getR2PublicBase() {
  return _r2PublicBase
}

/** Learn R2 public origin from a full object URL (e.g. after register-image). */
export function rememberR2PublicBaseFromUrl(url) {
  if (!url || typeof url !== "string") return
  const raw = url.trim().split("?")[0]
  if (!raw.startsWith("http")) return
  try {
    const parsed = new URL(raw)
    if (parsed.hostname.endsWith(".r2.dev") || parsed.pathname.startsWith(CANVAS_KEY_PREFIX)) {
      setR2PublicBase(parsed.origin)
    }
  } catch {
    /* ignore */
  }
}

export function isCanvasR2KeyPath(path) {
  if (!path || typeof path !== "string") return false
  const bare = path.trim().split("?")[0]
  return bare.startsWith(CANVAS_KEY_PREFIX) || bare.startsWith("canvas/")
}

export function isR2PublicMediaUrl(url) {
  if (!url || typeof url !== "string") return false
  const raw = url.trim().split("?")[0]
  if (!raw.startsWith("http")) return false
  try {
    const parsed = new URL(raw)
    if (parsed.hostname.endsWith(".r2.dev")) return true
    if (_r2PublicBase && parsed.origin === _r2PublicBase) return true
    return parsed.pathname.startsWith(CANVAS_KEY_PREFIX)
  } catch {
    return false
  }
}


function encodeKeySegments(key) {
  return key
    .replace(/^\//, "")
    .split("/")
    .filter(Boolean)
    .map((seg) => {
      try {
        return encodeURIComponent(decodeURIComponent(seg))
      } catch {
        return encodeURIComponent(seg)
      }
    })
    .join("/")
}

export function r2PublicUrlForKey(key) {
  const base = _r2PublicBase
  if (!base || !key) return null
  const encoded = encodeKeySegments(key)
  return encoded ? `${base}/${encoded}` : null
}

/** Complete /api/uploads/ or /api/view path with MEDIA_PUBLIC_BASE when configured. */
export function applyMediaPublicBase(urlOrPath) {
  if (!urlOrPath || typeof urlOrPath !== "string") return urlOrPath
  const trimmed = urlOrPath.trim()
  if (!trimmed || trimmed.startsWith("data:") || trimmed.startsWith("blob:")) return urlOrPath

  const mediaBase = getMediaPublicBase()
  if (!mediaBase) return urlOrPath

  const needsProxy = trimmed.includes("/api/uploads") || trimmed.includes("/api/view")
  if (!needsProxy) return urlOrPath

  if (trimmed.startsWith("http")) {
    try {
      const parsed = new URL(trimmed)
      const p = parsed.pathname
      if (p.startsWith("/api/uploads/") || p === "/api/view" || p.endsWith("/api/view")) {
        return `${mediaBase}${p}${parsed.search}`
      }
    } catch {
      return urlOrPath
    }
    return urlOrPath
  }

  const path = trimmed.startsWith("/") ? trimmed : `/${trimmed}`
  if (path.startsWith("/uploads/") && !path.startsWith("/api/uploads/")) {
    return `${mediaBase}${path.replace(/^\/uploads\//, "/api/uploads/")}`
  }
  if (path.startsWith("/api/uploads/") || path.startsWith("/api/view")) {
    return `${mediaBase}${path}`
  }
  return urlOrPath
}

/**
 * Resolve bare /canvas/... paths or normalize full R2 URLs for display/API.
 * Returns the original value when R2 base is unknown.
 */
export function resolveCanvasR2MediaUrl(url) {
  if (!url || typeof url !== "string") return url
  const s = url.trim()
  if (!s || s.startsWith("data:") || s.startsWith("blob:")) return url

  rememberR2PublicBaseFromUrl(s)

  if (isR2PublicMediaUrl(s)) {
    try {
      const parsed = new URL(s.split("?")[0])
      const key = parsed.pathname.replace(/^\//, "")
      const rebuilt = r2PublicUrlForKey(key) || s.split("?")[0]
      const query = s.includes("?") ? s.slice(s.indexOf("?")) : ""
      return `${rebuilt}${query}`
    } catch {
      return s
    }
  }

  if (isCanvasR2KeyPath(s)) {
    const [pathPart, queryPart = ""] = s.split("?", 2)
    const key = pathPart.replace(/^\//, "")
    const full = r2PublicUrlForKey(key)
    if (full) return queryPart ? `${full}?${queryPart}` : full
  }

  return applyMediaPublicBase(s)
}

export async function fetchR2PublicBase(api) {
  if (_r2PublicBase) return _r2PublicBase
  try {
    const caps = await getUploadCapabilities()
    const base = caps?.r2_public_url || caps?.review?.r2_public_url
    if (base) setR2PublicBase(base)
  } catch {
    /* ignore */
  }
  if (!_r2PublicBase && api) {
    try {
      const res = await api.get("/api/upload/capabilities")
      const base = res.data?.r2_public_url
      if (base) setR2PublicBase(base)
    } catch {
      /* ignore — uploads may still learn base from register-image */
    }
  }
  return _r2PublicBase
}
