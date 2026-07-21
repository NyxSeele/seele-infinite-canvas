import api from "../../services/api"
import { encodePublicMediaUrl } from "../encodePublicMediaUrl"
import { ensureMediaUrl, refreshMediaTicket, toRelativeMediaUrl } from "../mediaTicket"

const AVATAR_KEY = "canvas-user-avatar-url"
export const AVATAR_CHANGED_EVENT = "canvas-avatar-changed"

let avatarReloadPromise = null

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
  if (raw.startsWith("http://") || raw.startsWith("https://")) return raw
  return ensureMediaUrl(raw)
}

export function writeUserAvatar(url) {
  try {
    let stored = url || ""
    if (stored && !stored.startsWith("data:") && !stored.startsWith("blob:")) {
      if (stored.includes("/api/uploads/")) {
        stored = toRelativeMediaUrl(stored).split("?")[0]
      } else if (stored.startsWith("http")) {
        stored = encodePublicMediaUrl(stored).split("?")[0]
      }
    }
    if (stored) localStorage.setItem(AVATAR_KEY, stored)
    else localStorage.removeItem(AVATAR_KEY)
    window.dispatchEvent(new CustomEvent(AVATAR_CHANGED_EVENT, { detail: stored || "" }))
  } catch {
    /* ignore */
  }
}

/** 头像加载失败时刷新媒体票据并重读展示 URL */
export async function reloadUserAvatarMedia() {
  if (!avatarReloadPromise) {
    avatarReloadPromise = refreshMediaTicket(api)
      .then(() => {
        window.dispatchEvent(new CustomEvent(AVATAR_CHANGED_EVENT))
        return readUserAvatar()
      })
      .catch(() => readUserAvatar())
      .finally(() => {
        avatarReloadPromise = null
      })
  }
  return avatarReloadPromise
}

export function avatarBackgroundStyle(url) {
  if (!url) return undefined
  const safe = String(url).replace(/"/g, '\\"')
  return { backgroundImage: `url("${safe}")` }
}
