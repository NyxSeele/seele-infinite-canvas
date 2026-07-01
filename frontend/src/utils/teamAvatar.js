const AVATAR_KEY = "ai_studio_team_avatars"

function readMap() {
  try {
    return JSON.parse(localStorage.getItem(AVATAR_KEY) || "{}")
  } catch {
    return {}
  }
}

function writeMap(map) {
  try {
    localStorage.setItem(AVATAR_KEY, JSON.stringify(map))
    window.dispatchEvent(new CustomEvent("team-avatar-changed"))
  } catch {
    /* ignore */
  }
}

export function readTeamAvatar(teamId) {
  if (!teamId) return ""
  return readMap()[teamId] || ""
}

export function writeTeamAvatar(teamId, dataUrl) {
  if (!teamId) return
  const map = readMap()
  if (dataUrl) map[teamId] = dataUrl
  else delete map[teamId]
  writeMap(map)
}

export function teamInitial(name, fallback = "T") {
  const ch = String(name || fallback).trim()[0]
  return (ch || fallback).toUpperCase()
}
