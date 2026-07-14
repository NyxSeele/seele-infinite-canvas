/**
 * 视频模式与模型兼容（对齐后端 workflow_route）：
 * - 文生 → text2video
 * - 全能参考（vidMode「参考」/ freeref）→ image2video（单图 I2V）
 * - 首尾帧 → flf2v / fun_inpaint / 单帧 image2video
 */

/** 可走 text2video 的模型 */
export const T2V_MODELS = new Set([
  "wan-2.6",
  "ltx-video",
  "ltx2-fp4",
  "hunyuan-video",
  "hunyuan-video-1.5",
])

/** 可走 image2video 的模型（全能参考 = 图生视频） */
export const I2V_MODELS = new Set([
  "wan-i2v",
  "ltx2-fp4",
])

/** 可走首尾帧（FLF2V / Fun Inpaint）的模型 */
export const KEYFRAME_MODELS = new Set([
  "wan-i2v",
  "wan-fun-inpaint",
])

/** 仅文生、不能图生/全能参考（兼容旧引用） */
export const T2V_ONLY = new Set(
  [...T2V_MODELS].filter((id) => !I2V_MODELS.has(id)),
)

/** 支持图生但不支持首尾帧 FLF2V（兼容旧引用） */
export const NO_FLF2V = new Set(
  [...I2V_MODELS].filter((id) => !KEYFRAME_MODELS.has(id)),
)

/** 图生专用权重，不能文生 */
export const I2V_ONLY = new Set(
  [...I2V_MODELS].filter((id) => !T2V_MODELS.has(id)),
)

const PREFER_T2V = ["wan-2.6", "ltx2-fp4", "hunyuan-video-1.5", "hunyuan-video", "ltx-video"]
const PREFER_KEYFRAME = ["wan-i2v", "wan-fun-inpaint"]
const PREFER_I2V = ["wan-i2v", "ltx2-fp4"]

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

  if (vidMode === "文生") return T2V_MODELS.has(id)
  if (vidMode === "参考") return I2V_MODELS.has(id)
  if (vidMode === "首尾帧") return KEYFRAME_MODELS.has(id)

  return T2V_MODELS.has(id)
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
  if (vidMode === "参考") prefer = PREFER_I2V
  else if (vidMode === "文生") prefer = PREFER_T2V
  for (const id of prefer) {
    if (ids.includes(id) && isVideoModelCompatible(id, vidMode)) return id
  }
  const hit = ids.find((id) => isVideoModelCompatible(id, vidMode))
  return hit || null
}

/**
 * 纠偏模型与模式：保留用户选的模式，尽量换模型而不是偷偷改模式。
 * @returns {{ modelId: string, vidMode: string }}
 */
export function reconcileVideoModelAndMode({ modelId, vidMode, models = [] }) {
  const mode = vidMode || "首尾帧"
  const id = String(modelId || "")

  if (id === "wan-fun-inpaint" && mode !== "首尾帧") {
    return { modelId: id, vidMode: "首尾帧" }
  }

  if (id && isVideoModelCompatible(id, mode)) {
    return { modelId: id, vidMode: mode }
  }

  // 文生权重用在图生/首尾帧 → 换兼容模型
  if (id && T2V_ONLY.has(id) && (mode === "首尾帧" || mode === "参考")) {
    const next = preferredModelForMode(mode, models)
    if (next && isVideoModelCompatible(next, mode)) {
      return { modelId: next, vidMode: mode }
    }
    return { modelId: id, vidMode: "文生" }
  }

  // 图生专用权重不能文生 → 全能参考（I2V）
  if (id && I2V_ONLY.has(id) && mode === "文生") {
    return { modelId: id, vidMode: "参考" }
  }

  // LTX2 等：有 I2V 无 FLF2V，首尾帧模式下降级到图生
  if (id && NO_FLF2V.has(id) && mode === "首尾帧") {
    const next = preferredModelForMode("首尾帧", models)
    if (next && isVideoModelCompatible(next, "首尾帧")) {
      return { modelId: next, vidMode: "首尾帧" }
    }
    return { modelId: id, vidMode: "参考" }
  }

  const next = preferredModelForMode(mode, models)
  return { modelId: next || id, vidMode: mode }
}
