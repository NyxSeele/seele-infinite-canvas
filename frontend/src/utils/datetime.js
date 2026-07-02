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
