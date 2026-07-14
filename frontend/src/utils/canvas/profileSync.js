import { updateProfile } from "../../services/profileApi"
import { uploadImageFile, dataUrlToFile } from "../../services/uploadImage"
import { ensureMediaUrl, toRelativeMediaUrl } from "../mediaTicket"
import { writeUserAvatar } from "./userAvatar"

export function resolveProfileAvatarUrl(raw) {
  if (!raw) return ""
  if (raw.startsWith("data:") || raw.startsWith("blob:")) return raw
  return ensureMediaUrl(raw)
}

const PREFS_KEY = "canvas-user-profile-prefs"
const LEGACY_AVATAR_KEY = "canvas-user-avatar-url"
const MIGRATION_PREFIX = "profile-server-migrated:"

function readPrefs() {
  try {
    return JSON.parse(localStorage.getItem(PREFS_KEY) || "{}")
  } catch {
    return {}
  }
}

function writePrefs(prefs) {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify(prefs))
    window.dispatchEvent(new CustomEvent("canvas-prefs-changed"))
  } catch {
    /* ignore */
  }
}

export function getUserDisplayName(user, fallback = "创作者") {
  const prefs = readPrefs()
  const name = (user?.display_name || prefs.displayName || user?.username || "").trim()
  return name || fallback
}

function migrationKey(userId) {
  return `${MIGRATION_PREFIX}${userId}`
}

export function applyServerProfileToCache(user, { notify = true } = {}) {
  if (!user) return
  const prefs = readPrefs()
  if (user.display_name) {
    prefs.displayName = user.display_name
  }
  if (user.bio != null) {
    prefs.bio = user.bio
  }
  writePrefs(prefs)
  const storedAvatar = user.avatar_url ? toRelativeMediaUrl(user.avatar_url) : ""
  if (notify) {
    writeUserAvatar(storedAvatar)
  } else {
    try {
      if (storedAvatar) localStorage.setItem(LEGACY_AVATAR_KEY, storedAvatar)
      else localStorage.removeItem(LEGACY_AVATAR_KEY)
    } catch {
      /* ignore */
    }
  }
}

export async function persistAvatarForProfile(avatarUrl) {
  if (!avatarUrl) return ""
  const trimmed = avatarUrl.trim()
  if (!trimmed) return ""
  if (trimmed.startsWith("data:") || trimmed.startsWith("blob:")) {
    const file = await dataUrlToFile(trimmed)
    const uploaded = await uploadImageFile(file)
    return toRelativeMediaUrl(uploaded)
  }
  if (trimmed.startsWith("http")) {
    return toRelativeMediaUrl(trimmed)
  }
  return toRelativeMediaUrl(trimmed)
}

export async function saveProfileToServer({ displayName, bio, avatarUrl, removeAvatar = false }) {
  const payload = {}
  if (displayName != null) {
    payload.display_name = displayName.trim()
  }
  if (bio != null) {
    payload.bio = bio.trim()
  }
  if (removeAvatar) {
    payload.avatar_url = ""
  } else if (avatarUrl) {
    const path = await persistAvatarForProfile(avatarUrl)
    if (path) payload.avatar_url = path
  }
  const updated = await updateProfile(payload)
  return updated
}

/**
 * 将本机 localStorage 资料静默迁移到服务端（每用户每浏览器一次）。
 */
export async function migrateLocalProfileIfNeeded(user) {
  if (!user?.id) return user
  const key = migrationKey(user.id)
  if (localStorage.getItem(key)) {
    applyServerProfileToCache(user)
    return user
  }

  const prefs = readPrefs()
  const legacyAvatar = localStorage.getItem(LEGACY_AVATAR_KEY) || ""
  const payload = {}
  let needsUpload = false

  if (!user.avatar_url && legacyAvatar) {
    if (legacyAvatar.startsWith("data:") || legacyAvatar.startsWith("blob:")) {
      needsUpload = true
    } else if (legacyAvatar.includes("/api/uploads/")) {
      payload.avatar_url = toRelativeMediaUrl(legacyAvatar)
    }
  }

  const localName = (prefs.displayName || "").trim()
  if (!user.display_name && localName) {
    payload.display_name = localName
  }

  const localBio = (prefs.bio || "").trim()
  if (!user.bio && localBio) {
    payload.bio = localBio
  }

  try {
    if (needsUpload) {
      const path = await persistAvatarForProfile(legacyAvatar)
      if (path) payload.avatar_url = path
    }
    if (Object.keys(payload).length > 0) {
      const updated = await updateProfile(payload)
      localStorage.setItem(key, "1")
      applyServerProfileToCache(updated)
      return updated
    }
    localStorage.setItem(key, "1")
    applyServerProfileToCache(user)
    return user
  } catch (err) {
    console.warn("[profile] silent migration failed", err?.response?.status || err?.message)
    applyServerProfileToCache(user)
    return user
  }
}
