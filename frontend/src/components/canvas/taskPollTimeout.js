/** 任务轮询 / 进度停滞超时（毫秒），默认 10 分钟 */
export const TASK_POLL_TIMEOUT_MS = 600 * 1000

/** 进度超过该时长未变化则判定超时（毫秒） */
export const PROGRESS_STALE_MS = TASK_POLL_TIMEOUT_MS

/** 后端任务已结束，前端应停止轮询且不得因本地计时器重新提交 */
export function isTerminalTaskStatus(status) {
  return status === "completed" || status === "failed"
}

/**
 * 基于「进度值是否变化」的超时守卫（非任务创建时间）。
 * - progress 变化 => 刷新计时，不超时
 * - progress 长期不变 => 超时
 * - 从未收到过 progress => 超过阈值后超时（非无限等待）
 */
export function createStaleProgressGuard(onStale, threshold = PROGRESS_STALE_MS) {
  let lastProgress = null
  let lastChangeAt = 0
  let startedAt = 0
  let timerId = null

  const schedule = () => {
    clearTimeout(timerId)
    timerId = setTimeout(() => {
      const now = Date.now()
      if (lastProgress === null) {
        if (now - startedAt >= threshold) {
          onStale({
            lastProgress: null,
            lastChangeAt: startedAt,
            elapsed: now - startedAt,
            threshold,
            reason: "no_progress_yet",
          })
        } else {
          schedule()
        }
        return
      }
      const elapsed = now - lastChangeAt
      if (elapsed >= threshold) {
        onStale({ lastProgress, lastChangeAt, elapsed, threshold, reason: "stale" })
      } else {
        schedule()
      }
    }, Math.min(threshold, 5000))
  }

  return {
    bump(progress) {
      const p = Number(progress) || 0
      if (lastProgress === null || p !== lastProgress) {
        lastProgress = p
        lastChangeAt = Date.now()
        schedule()
      }
    },
    /** 轮询仍活跃但 ComfyUI 未推送进度时，避免误判超时 */
    touch() {
      if (lastProgress === null) lastProgress = 0
      lastChangeAt = Date.now()
      schedule()
    },
    start() {
      startedAt = Date.now()
      lastProgress = null
      lastChangeAt = startedAt
      schedule()
    },
    stop() {
      clearTimeout(timerId)
      timerId = null
      lastProgress = null
    },
    getDebugState() {
      return {
        lastProgress,
        lastProgressAt: lastChangeAt || null,
        elapsed: lastChangeAt ? Date.now() - lastChangeAt : 0,
        timeoutThreshold: threshold,
      }
    },
  }
}
