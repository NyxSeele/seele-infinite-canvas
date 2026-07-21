export const RATE_LIMIT_BACKOFF_BASE_MS = 5000
export const RATE_LIMIT_BACKOFF_MAX_MS = 60000

export function isRateLimitError(err) {
  if (!err) return false
  const status = err.response?.status ?? err.status
  return status === 429
}

export function getRateLimitBackoffMs(attempt) {
  const exp = Math.min(Math.max(attempt, 0), 4)
  return Math.min(RATE_LIMIT_BACKOFF_MAX_MS, RATE_LIMIT_BACKOFF_BASE_MS * (2 ** exp))
}

export function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

export function createRateLimitBackoffState() {
  let attempt = 0
  let pausedUntil = 0

  return {
    get paused() {
      return Date.now() < pausedUntil
    },
    apply(err) {
      if (!isRateLimitError(err)) return false
      const waitMs = getRateLimitBackoffMs(attempt)
      attempt += 1
      pausedUntil = Date.now() + waitMs
      console.warn(`[rate-limit] 429 received, backing off ${waitMs}ms`)
      return true
    },
    async applyAndWait(err) {
      if (!this.apply(err)) return false
      const waitMs = pausedUntil - Date.now()
      if (waitMs > 0) await sleep(waitMs)
      return true
    },
    reset() {
      attempt = 0
      pausedUntil = 0
    },
  }
}
