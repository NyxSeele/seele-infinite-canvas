/** 仅文生视频（T2V），不支持首尾帧 / 自由参考 */
export const T2V_ONLY = new Set(["wan-2.6", "ltx2-fp4", "hunyuan-video"])

const PREFER_T2V = ["wan-2.6", "ltx2-fp4", "hunyuan-video", "wan-i2v"]
const PREFER_KEYFRAME = ["wan-i2v", "wan-fun-inpaint"]
const PREFER_FREEREF = ["wan-i2v"]

export function referenceModeForVidMode(vidMode) {
  if (vidMode === "参考") return "freeref"
  if (vidMode === "文生") return "t2v"
  return "keyframe"
}

export function vidModeFromReferenceMode(referenceMode, vidModeFallback) {
  if (referenceMode === "freeref") return "参考"
  if (referenceMode === "t2v") return "文生"
  if (referenceMode === "keyframe") return "首尾帧"
  if (vidModeFallback === "参考" || vidModeFallback === "文生" || vidModeFallback === "首尾帧") {
    return vidModeFallback
  }
  return "首尾帧"
}

/**
 * 视频生成模式与模型是否兼容。
 * @param {string} modelId
 * @param {string} vidMode 「文生」|「首尾帧」|「参考」
 */
export function isVideoModelCompatible(modelId, vidMode) {
  const id = String(modelId || "")
  if (!id) return false

  if (vidMode === "首尾帧") {
    if (T2V_ONLY.has(id)) return false
    return true
  }

  if (vidMode === "参考") {
    if (T2V_ONLY.has(id)) return false
    if (id === "wan-fun-inpaint") return false
    return true
  }

  // 文生（及未知模式按文生处理）：T2V-only 与 wan-i2v 可用；fun-inpaint 需双帧
  if (id === "wan-fun-inpaint") return false
  return true
}

/**
 * 为当前模式挑选首选兼容模型。
 * @param {string} vidMode
 * @param {Array<{id?: string}>} models
 * @returns {string|null}
 */
export function preferredModelForMode(vidMode, models = []) {
  const ids = models.map((m) => m?.id).filter(Boolean)
  let prefer = PREFER_KEYFRAME
  if (vidMode === "参考") prefer = PREFER_FREEREF
  else if (vidMode === "文生") prefer = PREFER_T2V
  for (const id of prefer) {
    if (ids.includes(id) && isVideoModelCompatible(id, vidMode)) return id
  }
  const hit = ids.find((id) => isVideoModelCompatible(id, vidMode))
  return hit || null
}

/**
 * 纠偏模型与模式组合。
 * @returns {{ modelId: string, vidMode: string }}
 */
export function reconcileVideoModelAndMode({ modelId, vidMode, models = [] }) {
  let mode = vidMode || "首尾帧"
  let id = String(modelId || "")

  if (id && T2V_ONLY.has(id) && (mode === "首尾帧" || mode === "参考")) {
    return { modelId: id, vidMode: "文生" }
  }

  if (id === "wan-fun-inpaint" && mode !== "首尾帧") {
    return { modelId: id, vidMode: "首尾帧" }
  }

  if (id && isVideoModelCompatible(id, mode)) {
    return { modelId: id, vidMode: mode }
  }

  const next = preferredModelForMode(mode, models)
  return { modelId: next || id, vidMode: mode }
}
