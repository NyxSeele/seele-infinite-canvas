/**
 * Ensure R2 / public media URLs with non-ASCII path segments are percent-encoded
 * so browsers can Range-request (avoids Cloudflare 400 on raw CJK filenames).
 */
export function encodePublicMediaUrl(url) {
  if (!url || typeof url !== "string") return url
  const raw = url.trim()
  if (!raw) return raw
  try {
    const u = new URL(raw, typeof window !== "undefined" ? window.location.origin : "http://local")
    const parts = u.pathname.split("/").map((seg) => {
      if (!seg) return seg
      try {
        return encodeURIComponent(decodeURIComponent(seg))
      } catch {
        return encodeURIComponent(seg)
      }
    })
    u.pathname = parts.join("/")
    return u.toString()
  } catch {
    try {
      return encodeURI(raw)
    } catch {
      return raw
    }
  }
}
