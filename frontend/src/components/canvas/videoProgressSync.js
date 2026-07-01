import { PROGRESS_STALE_MS } from "./taskPollTimeout"

/** 将后端 progress 统一为 0~100 整数；null 表示无有效值 */
export function normalizeProgressPercent(raw) {
  if (raw == null || raw === "") return null
  const n = Number(raw)
  if (Number.isNaN(n)) return null
  if (n > 0 && n <= 1) return Math.min(100, Math.max(0, Math.round(n * 100)))
  return Math.min(100, Math.max(0, Math.round(n)))
}

export function logVideoPollDebug(fields) {
  console.log("[video-poll]", {
    timeoutThreshold: PROGRESS_STALE_MS,
    ...fields,
  })
}
