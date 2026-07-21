import { isTransientPollError } from "../../components/canvas/taskNetworkError"

export const GATEWAY_BACKOFF_BASE_MS = 2000
export const GATEWAY_BACKOFF_MAX_MS = 8000
export const GATEWAY_MAX_ATTEMPTS = 5

export function getGatewayBackoffMs(attempt) {
  const exp = Math.min(Math.max(attempt, 0), 3)
  return Math.min(GATEWAY_BACKOFF_MAX_MS, GATEWAY_BACKOFF_BASE_MS * (2 ** exp))
}

/**
 * 轮询期瞬态网络/网关错误退避（502/503/504、连接失败等）。
 * 连续失败超过 GATEWAY_MAX_ATTEMPTS 后返回 false，由调用方 failTask。
 */
export function createGatewayPollRetryState() {
  let attempt = 0
  let pausedUntil = 0

  return {
    get paused() {
      return Date.now() < pausedUntil
    },
    get attempt() {
      return attempt
    },
    shouldRetry(err) {
      if (!isTransientPollError(err)) return false
      if (attempt >= GATEWAY_MAX_ATTEMPTS) return false
      const waitMs = getGatewayBackoffMs(attempt)
      attempt += 1
      pausedUntil = Date.now() + waitMs
      console.warn(
        `[poll-retry] transient error, attempt ${attempt}/${GATEWAY_MAX_ATTEMPTS}, wait ${waitMs}ms`,
      )
      return true
    },
    exhausted() {
      return attempt >= GATEWAY_MAX_ATTEMPTS
    },
    reset() {
      attempt = 0
      pausedUntil = 0
    },
  }
}
