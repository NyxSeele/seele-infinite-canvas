import { ensureMediaUrl } from "../mediaTicket"

const AVATAR_KEY = "canvas-user-avatar-url"
export const AVATAR_CHANGED_EVENT = "canvas-avatar-changed"

/** 读取持久化路径（无 mt），展示时请配合 ensureMediaUrl */
export function readUserAvatarRaw() {
  try {
    return localStorage.getItem(AVATAR_KEY) || ""
  } catch {
    return ""
  }
}

export function readUserAvatar() {
  const raw = readUserAvatarRaw()
  if (!raw) return ""
  if (raw.startsWith("data:") || raw.startsWith("blob:")) return raw
  return ensureMediaUrl(raw)
}

export function writeUserAvatar(url) {
  try {
    const stored = url && !url.startsWith("data:") && !url.startsWith("blob:")
      ? url.split("?")[0]
      : url
    if (stored) localStorage.setItem(AVATAR_KEY, stored)
    else localStorage.removeItem(AVATAR_KEY)
    window.dispatchEvent(new CustomEvent(AVATAR_CHANGED_EVENT, { detail: stored || "" }))
  } catch {
    /* ignore */
  }
}
