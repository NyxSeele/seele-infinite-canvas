/** text-response 必须整卡可拖，清除历史遗留的 dragHandle */
import { normalizeBeatCardData } from "./scriptBeatCard"

export function normalizeTextResponseNode(n) {
  if (n.type !== "text-response") return n
  const { dragHandle: _dh, ...rest } = n
  const data = { ...(rest.data || {}) }
  // 勿在刷新后再次自动整理大纲（仅任务完成当次有效）
  data.outlineAutoPending = false
  return { ...rest, data, draggable: rest.draggable !== false }
}

/** outline 节点清除 dragHandle，避免只能拖把手区域（保留 loading / generatingShots） */
export function stripOutlineDragHandle(n) {
  if (n.type !== "outline") return n
  const { dragHandle: _dh, ...rest } = n
  return { ...rest, draggable: rest.draggable !== false }
}

/** 持久化/刷新后清理 outline 上的进行中态，避免僵死 loading */
export function normalizeOutlineNode(n) {
  if (n.type !== "outline") return n
  const stripped = stripOutlineDragHandle(n)
  const data = { ...(stripped.data || {}) }
  data.loading = false
  data.generatingShots = false
  return { ...stripped, data }
}

export function normalizeShotScriptNode(n) {
  if (n.type !== "shot-script") return n
  const { dragHandle: _dh, ...rest } = n
  return { ...rest, draggable: rest.draggable !== false }
}

export function normalizeBeatCardNode(n) {
  if (n.type !== "script-beat-card") return n
  const { dragHandle: _dh, ...rest } = n
  return {
    ...rest,
    draggable: rest.draggable !== false,
    data: normalizeBeatCardData(rest.data || {}),
  }
}

export function normalizeCanvasNode(n) {
  return normalizeBeatCardNode(
    normalizeShotScriptNode(stripOutlineDragHandle(normalizeTextResponseNode(n)))
  )
}
