import { PROGRESS_STALE_MS } from "./taskPollTimeout"
import { isCanvasDebugEnabled } from "../../utils/canvas/canvasDebug"

/** 与后端 comfyui_progress._RUNNING_CAP 一致：运行中最高 95，100 仅留给真正完成 */
export const RUNNING_PROGRESS_CAP = 95

/**
 * 运行中进度封顶；仅 isComplete 时允许 100。
 * @param {number|string|null|undefined} raw
 * @param {{ isComplete?: boolean }} [opts]
 */
export function capRunningProgress(raw, { isComplete = false } = {}) {
  const n = normalizeProgressPercent(raw)
  if (n == null) return null
  if (isComplete) return n
  return Math.min(RUNNING_PROGRESS_CAP, n)
}

/** 将后端 progress 统一为 0~100 整数；null 表示无有效值 */
export function normalizeProgressPercent(raw) {
  if (raw == null || raw === "") return null
  const n = Number(raw)
  if (Number.isNaN(n)) return null
  if (n > 0 && n <= 1) return Math.min(100, Math.max(0, Math.round(n * 100)))
  return Math.min(100, Math.max(0, Math.round(n)))
}

/**
 * 合并进度：默认只升不降，避免双采样器 / 轮询乱序造成 0↔50↔100 回跳。
 * allowDecrease=true 用于新任务重置。
 */
export function mergeMonotonicProgress(prev, next, { allowDecrease = false } = {}) {
  const p = normalizeProgressPercent(prev) ?? 0
  const n = normalizeProgressPercent(next)
  if (n == null) return p
  if (allowDecrease) return n
  return Math.max(p, n)
}

export function logVideoPollDebug(fields) {
  if (!isCanvasDebugEnabled()) return
  console.log("[video-poll]", {
    timeoutThreshold: PROGRESS_STALE_MS,
    ...fields,
  })
}

/** 任务是否已进入真实生成（running 或已有进度） */
export function taskHasGenerationStarted(task, progressPct) {
  if (task?.status === "running") return true
  const fromArg = normalizeProgressPercent(progressPct)
  if (fromArg != null && fromArg > 0) return true
  const fromTask = normalizeProgressPercent(task?.progress)
  return fromTask != null && fromTask > 0
}

/**
 * 媒体任务在 Comfy 入队前（L3/提交阶段）：无 comfy_prompt_id 且仍为 pending/processing。
 */
export function isMediaTaskPreparing(task) {
  if (!task || task.comfy_prompt_id) return false
  if (task.stage === "preparing" || task.message === "preparing") return true
  const status = task?.status
  if (status !== "pending" && status !== "processing") return false
  const pct = normalizeProgressPercent(task?.progress)
  return pct == null || pct === 0
}

/**
 * 视频卡片「排队中 / 准备中」判定。
 * 仅 Comfy 已入队且 stage/message 为 queued 时显示排队；无 comfy_prompt_id 时为准备中。
 * hasStarted 为 true 后不再回退到排队/准备文案。
 */
export function resolveVideoGenerationPhase(task, { hasStarted = false } = {}) {
  if (hasStarted) {
    return { isQueued: false, isPreparing: false }
  }
  const status = task?.status
  const explicitlyQueued =
    status === "pending"
    && (task?.stage === "queued" || task?.message === "queued")

  if (isMediaTaskPreparing(task)) {
    return { isQueued: false, isPreparing: true }
  }
  return {
    isQueued: explicitlyQueued,
    isPreparing: false,
  }
}
