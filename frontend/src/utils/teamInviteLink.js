const LINK_KEY = "ai_studio_team_invite_links"

function readMap() {
  try {
    return JSON.parse(localStorage.getItem(LINK_KEY) || "{}")
  } catch {
    return {}
  }
}

function writeMap(map) {
  try {
    localStorage.setItem(LINK_KEY, JSON.stringify(map))
  } catch {
    /* ignore */
  }
}

function randomToken() {
  return Array.from(crypto.getRandomValues(new Uint8Array(8)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("")
}

const DEFAULT_SETTINGS = {
  expiryDays: 7,
  maxUses: 0,
  quotaType: "unlimited",
  periodicCycle: "monthly",
  periodicAmount: 20000,
  fixedAmount: 20000,
}

export function getInviteSettings(teamId) {
  const row = readMap()[teamId]
  return { ...DEFAULT_SETTINGS, ...(row?.settings || {}) }
}

export function getOrCreateInviteLink(teamId, settings = null) {
  if (!teamId) return { url: "", token: "" }
  const map = readMap()
  const prev = map[teamId]
  const mergedSettings = { ...DEFAULT_SETTINGS, ...(settings || prev?.settings || {}) }
  const token = settings ? randomToken() : prev?.token || randomToken()
  map[teamId] = {
    token,
    settings: mergedSettings,
    createdAt: Date.now(),
  }
  writeMap(map)
  const url = `${window.location.origin}/join-team?token=${token}`
  return { url, token, settings: mergedSettings }
}

export function inviteExpiryLabel(days) {
  if (days === 0) return "永不过期"
  if (days === 1) return "1 天"
  if (days === 7) return "7 天"
  if (days === 30) return "30 天"
  return `${days} 天`
}

export function inviteUsesLabel(maxUses) {
  if (!maxUses || maxUses < 0) return "无限制"
  return `${maxUses} 次`
}
