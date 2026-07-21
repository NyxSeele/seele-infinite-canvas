import { normalizeOutlineScene } from "./outlineSceneMeta"
import { normalizeScriptRow } from "./scriptTableKeyframes"
import { withDefaultQualityPreset } from "./scriptQualityPresets"
import { makeEmptyScriptRow } from "./scriptTableRowFactory"
import { normalizeClarityLabel } from "./aspectRatioLayout"
import {
  defaultVidAudioForModel,
  I2AV_ONLY,
  I2V_ONLY,
} from "./videoModelCompat"
import { pickDefaultModel } from "./modelCatalog"

export const AGENT_OUTLINE_WIDTH = 540
export const AGENT_SCRIPT_TABLE_WIDTH = 1120

function normalizeAgentClarity(value) {
  return normalizeClarityLabel(value, "720P")
}

function normalizeAgentOutlineScenes(scenes, fallbackContent = "") {
  if (Array.isArray(scenes) && scenes.length > 0) {
    return scenes.map((raw, i) => {
      const scene = normalizeOutlineScene(
        typeof raw === "string" ? { content: raw } : raw
      )
      return {
        ...scene,
        id: scene.id || `scene-${i}`,
        content: scene.content || "",
      }
    })
  }
  if (fallbackContent.trim()) {
    return [{ id: "scene-0", content: fallbackContent.trim() }]
  }
  return [{ id: "scene-0", content: "" }]
}

function normalizeAgentScriptRows(rows) {
  if (!Array.isArray(rows) || rows.length === 0) {
    return [makeEmptyScriptRow(1)]
  }
  return rows.map((raw, i) => {
    const shotNumber = raw?.shotNumber ?? i + 1
    const duration = raw?.duration ?? 8
    return normalizeScriptRow(
      withDefaultQualityPreset({
        ...makeEmptyScriptRow(shotNumber),
        ...raw,
        shotNumber,
        duration,
      })
    )
  })
}

function agentVideoNeedsReferenceImage(modelId) {
  const id = String(modelId || "")
  return I2AV_ONLY.has(id) || I2V_ONLY.has(id)
}

function agentVideoHasReferenceImage(data) {
  const freeRefs = Array.isArray(data.freeRefs) ? data.freeRefs : []
  if (freeRefs.some((r) => r?.imageUrl)) return true
  const kf = data.keyframes
  if (kf?.first?.imageUrl || kf?.last?.imageUrl) return true
  if (data.referenceImage || data.referenceImageUrl) return true
  return false
}

function buildAgentVideoReferenceFields(data, referenceMode) {
  const patch = {}
  if (Array.isArray(data.freeRefs) && data.freeRefs.length > 0) {
    patch.freeRefs = data.freeRefs
  }
  if (data.keyframes && (data.keyframes.first || data.keyframes.last)) {
    patch.keyframes = data.keyframes
  }
  const refUrl = data.referenceImage || data.referenceImageUrl
  if (refUrl && !patch.freeRefs?.length && !patch.keyframes?.first?.imageUrl) {
    if (referenceMode === "freeref") {
      patch.freeRefs = [{ imageUrl: refUrl, imageId: refUrl, label: "参考" }]
    } else {
      patch.keyframes = {
        first: { imageUrl: refUrl, enabled: true },
        last: data.keyframes?.last || null,
      }
      patch.referenceMode = "keyframe"
    }
  }
  return patch
}

/**
 * 将 Agent create_node action 转为节点初始 data。
 * 返回 { __agentError } 表示应跳过并提示用户。
 */
export function buildAgentCreateNodeData(action, z) {
  const data = action.data || {}

  if (action.node_type === "image") {
    const imageModels = action._imageModels || []
    const prompt = (data.prompt || data.content || "").trim()
    const modelId = data.modelId || pickDefaultModel(imageModels, { category: "image" }) || imageModels[0]?.id
    if (!prompt) {
      return { __agentError: "图像节点缺少 prompt，已跳过" }
    }
    if (!modelId) {
      return { __agentError: "未配置可用的图像模型，无法创建图像节点" }
    }
    return {
      label: data.label || "Image",
      prompt,
      modelId,
      status: "input",
      imgQuality: normalizeAgentClarity(data.quality || data.imgQuality || "720P"),
      imgResolution: normalizeAgentClarity(data.quality || data.imgResolution || data.imgQuality || "720P"),
      imgRatio: data.ratio || "1:1",
      count: 1,
      expectedCount: 1,
      pendingTrigger: Date.now(),
      agentCreated: true,
      zIndex: z,
    }
  }

  if (action.node_type === "video") {
    const videoModels = action._videoModels || []
    const prompt = (data.prompt || data.content || "").trim()
    const referenceMode = data.referenceMode
      || (agentVideoNeedsReferenceImage(data.modelId || data.video_model_id) ? "freeref" : "t2v")
    const refFields = buildAgentVideoReferenceFields(data, referenceMode)
    const resolvedReferenceMode = refFields.referenceMode || referenceMode
    const vidMode = data.vidMode
      || (resolvedReferenceMode === "freeref"
        ? "参考"
        : resolvedReferenceMode === "t2v"
          ? "文生"
          : "首尾帧")
    const modelId = data.modelId || data.video_model_id
      || pickDefaultModel(videoModels, { category: "video", vidMode })
      || videoModels[0]?.id
    if (!prompt) {
      return { __agentError: "视频节点缺少 prompt，已跳过" }
    }
    if (!modelId) {
      return { __agentError: "未配置可用的视频模型，无法创建视频节点" }
    }
    const duration = data.duration || data.vidDuration || "5s"
    const needsRefImage = agentVideoNeedsReferenceImage(modelId)
    const hasRefImage = agentVideoHasReferenceImage(data)

    const nodeData = {
      label: data.label || "Video",
      prompt,
      modelId,
      status: "input",
      vidDuration: typeof duration === "number" ? `${duration}s` : duration,
      vidRatio: data.ratio || data.vidRatio || "16:9",
      vidQuality: normalizeAgentClarity(data.quality || data.vidQuality || "720P"),
      referenceMode: resolvedReferenceMode,
      panelMode: data.panelMode || resolvedReferenceMode,
      vidMode,
      vidAudio: data.vidAudio || defaultVidAudioForModel(modelId),
      cameraMove: data.cameraMove || "auto",
      shotScale: data.shotScale || "auto",
      samplingProfile: data.samplingProfile || "fast",
      agentCreated: true,
      zIndex: z,
      ...refFields,
    }

    if (!needsRefImage || hasRefImage || refFields.freeRefs?.length || refFields.keyframes?.first?.imageUrl) {
      nodeData.pendingTrigger = Date.now()
    }

    return nodeData
  }

  if (action.node_type === "outline") {
    const title = data.title || data.label || "大纲"
    const scenes = normalizeAgentOutlineScenes(data.scenes, data.content)
    return {
      title,
      label: title,
      scenes,
      versions: [],
      selectedVersionIndex: 0,
      zIndex: z,
    }
  }

  if (action.node_type === "script_table") {
    const label = data.label || "分镜表"
    return {
      label,
      rows: normalizeAgentScriptRows(data.rows),
      globalStyle: data.globalStyle || "",
      themeContext: data.themeContext || "",
      continuityMode: data.continuityMode !== false,
      visualContinuity: data.visualContinuity === true,
      zIndex: z,
    }
  }

  return {
    content: data.content || "",
    label: data.label || "Text",
    status: "completed",
    zIndex: z,
  }
}
