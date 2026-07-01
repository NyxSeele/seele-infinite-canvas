import { ensureMediaUrl } from "../mediaTicket"
import { readUserAvatarRaw } from "./userAvatar"

const PREFS_KEY = "canvas-user-profile-prefs"

export function readDisplayName(fallbackUsername = "") {
  try {
    const prefs = JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
    return (prefs.displayName || "").trim() || fallbackUsername || ""
  } catch {
    return fallbackUsername || ""
  }
}

export function resolveCommentAuthorName(msg, currentUserId, fallbackUsername = "") {
  if (!msg) return fallbackUsername
  if (currentUserId != null && Number(msg.author_id) === Number(currentUserId)) {
    return readDisplayName(fallbackUsername) || msg.author_name || fallbackUsername
  }
  return msg.author_name || fallbackUsername
}

export function resolveCommentAvatar(msg, currentUserId) {
  if (!msg) return ""
  if (currentUserId != null && Number(msg.author_id) === Number(currentUserId)) {
    const mine = readUserAvatarRaw()
    if (mine) {
      if (mine.startsWith("data:") || mine.startsWith("blob:")) return mine
      return ensureMediaUrl(mine)
    }
  }
  const raw = msg?.author_avatar_url || ""
  if (!raw) return ""
  if (raw.startsWith("data:") || raw.startsWith("blob:")) return raw
  return ensureMediaUrl(raw)
}

export function personLabel(who, fallback = "") {
  if (!who) return fallback
  return (who.display_name || who.username || fallback).trim()
}
