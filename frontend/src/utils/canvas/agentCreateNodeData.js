import { normalizeOutlineScene } from "./outlineSceneMeta"
import { normalizeScriptRow } from "./scriptTableKeyframes"
import { withDefaultQualityPreset } from "./scriptQualityPresets"
import { makeEmptyScriptRow } from "../../components/canvas/ScriptTableNode"

export const AGENT_OUTLINE_WIDTH = 540
export const AGENT_SCRIPT_TABLE_WIDTH = 1120

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

/**
 * 将 Agent create_node action 转为节点初始 data。
 * 返回 { __agentError } 表示应跳过并提示用户。
 */
export function buildAgentCreateNodeData(action, z) {
  const data = action.data || {}

  if (action.node_type === "image") {
    const imageModels = action._imageModels || []
    const prompt = (data.prompt || data.content || "").trim()
    const modelId = data.modelId || imageModels[0]?.id
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
      status: "idle",
      imgQuality: data.quality || "2K",
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
    const modelId = data.modelId || data.video_model_id || videoModels[0]?.id
    if (!prompt) {
      return { __agentError: "视频节点缺少 prompt，已跳过" }
    }
    if (!modelId) {
      return { __agentError: "未配置可用的视频模型，无法创建视频节点" }
    }
    const duration = data.duration || data.vidDuration || "5s"
    return {
      label: data.label || "Video",
      prompt,
      modelId,
      status: "input",
      vidDuration: typeof duration === "number" ? `${duration}s` : duration,
      vidRatio: data.ratio || data.vidRatio || "16:9",
      vidQuality: data.quality || data.vidQuality || "720P",
      referenceMode: data.referenceMode || "freeref",
      cameraMove: data.cameraMove || "auto",
      shotScale: data.shotScale || "auto",
      samplingProfile: data.samplingProfile || "fast",
      pendingTrigger: Date.now(),
      agentCreated: true,
      zIndex: z,
    }
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
