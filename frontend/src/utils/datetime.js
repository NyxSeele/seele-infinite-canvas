/** 将服务端时间统一解析为 UTC 毫秒 */
export function parseServerTimestamp(raw) {
  if (raw == null || raw === "") return null
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw < 1e12 ? Math.round(raw * 1000) : Math.round(raw)
  }
  const n = Number(raw)
  if (Number.isFinite(n) && n > 0) {
    return n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  }
  const s = String(raw).trim()
  const normalized = /[zZ]|[+-]\d{2}:\d{2}$/.test(s) ? s : `${s}Z`
  const ms = Date.parse(normalized)
  return Number.isFinite(ms) ? ms : null
}

/** @deprecated 使用 parseServerTimestamp */
export function parseUpdatedAt(iso) {
  return parseServerTimestamp(iso)
}

export function formatProjectDate(iso, neverEditedLabel = "尚未编辑") {
  const ts = parseServerTimestamp(iso)
  if (!ts) return neverEditedLabel
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, "0")
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** 项目活动时间：相对时间（分钟 / 小时 / 天 / 周 / 日期） */
export function formatProjectActivityTime(iso, labels = {}) {
  const {
    neverEdited = "尚未编辑",
    justNow = "刚刚",
    minutesAgo = (n) => `${n} 分钟前`,
    hoursAgo = (n) => `${n} 小时前`,
    daysAgo = (n) => `${n} 天前`,
    weeksAgo = (n) => `${n} 周前`,
  } = labels

  const ts = parseServerTimestamp(iso)
  if (!ts) return neverEdited

  const d = new Date(ts)
  const diff = Date.now() - ts
  const pad = (n) => String(n).padStart(2, "0")

  if (diff < 60_000) return justNow

  const minutes = Math.floor(diff / 60_000)
  if (minutes < 60) return minutesAgo(minutes)

  const hours = Math.floor(minutes / 60)
  if (hours < 24) return hoursAgo(hours)

  const days = Math.floor(hours / 24)
  if (days < 7) return daysAgo(days)

  const weeks = Math.floor(days / 7)
  if (days < 30) return weeksAgo(weeks)

  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}
