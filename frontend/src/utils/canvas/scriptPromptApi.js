import api from "../../services/api"
import { pollTaskUntilDone } from "./outlineStructureApi"
import { redistributeKeyframeTimes } from "./scriptTableKeyframes"
import { buildShotPromptPackage } from "./scriptPromptPackage"

export function rowToExpandPayload(row, castLibrary = [], sceneLibrary = []) {
  const rowNorm = redistributeKeyframeTimes(row)
  return {
    row: {
      shot_number: rowNorm.shotNumber ?? 1,
      duration: Number(rowNorm.duration) || 8,
      prompt: rowNorm.prompt || rowNorm.description || "",
      sound_note: rowNorm.soundNote || "",
      atmosphere_note: rowNorm.atmosphereNote || "",
      camera: rowNorm.camera || "",
      movement: rowNorm.movement || "",
      lighting: rowNorm.lighting || "",
      composition: rowNorm.composition || "",
      color_grade: rowNorm.colorGrade || "",
      lens: rowNorm.lens || "",
      performance: rowNorm.performance || "",
      sound_design: rowNorm.soundDesign || "",
      location_id: rowNorm.locationId || rowNorm.location_id || null,
      keyframes: (rowNorm.keyframes || []).map((kf) => ({
        id: kf.id,
        label: kf.label || "",
        time_start: Number(kf.timeStart) || 0,
        time_end: Number(kf.timeEnd) || 0,
        prompt: kf.prompt || kf.description || "",
        /** @deprecated 节拍格构图参考已下线；序列化旧值仅供历史 expand API 兼容 */
        reference_image: kf.referenceImage || null,
      })),
    },
    cast_library: (castLibrary || [])
      .filter((c) => c.type !== "scene")
      .map((c) => ({
        name: c.name,
        type: "character",
      })),
    scene_library: (sceneLibrary || []).map((s) => ({
      id: s.id,
      name: s.name,
      type: "scene",
    })),
  }
}

export function buildLocalPromptPackage(row, castLibrary, keyframeId = null, sceneLibrary = [], styleReference = null) {
  return buildShotPromptPackage(row, castLibrary, { keyframeId, sceneLibrary, styleReference })
}

async function postPromptLlmOrSync(url, payload) {
  const submit = await api.post(url, payload, { timeout: 30000 })
  const taskId = submit.data?.task_id
  if (!taskId) {
    return submit.data
  }
  const task = await pollTaskUntilDone(taskId)
  return task.result || {}
}

export async function expandShotPromptPackage(row, castLibrary, options = {}) {
  const { keyframeId = null, useLlm = true, sceneLibrary = [] } = options
  const payload = rowToExpandPayload(row, castLibrary, sceneLibrary)
  if (keyframeId) payload.keyframe_id = keyframeId
  payload.use_llm = useLlm

  try {
    const data = await postPromptLlmOrSync("/api/prompt/expand-shot-package", payload)
    return normalizePromptPackage(data)
  } catch {
    return buildLocalPromptPackage(row, castLibrary, keyframeId, sceneLibrary)
  }
}

export async function splitShotBeats(row, castLibrary, options = {}) {
  const { useLlm = true, sceneLibrary = [] } = options
  const payload = rowToExpandPayload(row, castLibrary, sceneLibrary)
  payload.use_llm = useLlm
  try {
    return await postPromptLlmOrSync("/api/prompt/split-shot-beats", payload)
  } catch {
    return null
  }
}

export function normalizePromptPackage(data) {
  if (!data) return null
  return {
    basic: data.basic || "",
    atmosphere: data.atmosphere || "",
    frames: data.frames || "",
    fullText: data.full_text || data.fullText || "",
    apiDescription: data.api_description || data.apiDescription || "",
    source: data.source || "rule",
  }
}
