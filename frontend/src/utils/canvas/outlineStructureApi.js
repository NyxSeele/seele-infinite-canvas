import { flushSync } from "react-dom"
import api from "../../services/api"
import { formatScreenplayParagraphs } from "./textFormat"
import { normalizeOutlineScene } from "./outlineSceneMeta"

export const OUTLINE_API_TIMEOUT_MS = 120000
/** 超过 API 超时仍未结束，视为僵死 loading，允许重试 */
export const OUTLINE_LOADING_STALE_MS = OUTLINE_API_TIMEOUT_MS + 15000

export function isOutlineLoadingStale(node) {
  if (node?.type !== "outline" || !node.data?.loading) return false
  const started = node.data?.outlineLoadingStartedAt
  if (!started) return true
  return Date.now() - started > OUTLINE_LOADING_STALE_MS
}

export function outlineLoadingPatch(extra = {}) {
  return {
    ...extra,
    loading: true,
    outlineLoadingStartedAt: Date.now(),
    error: null,
  }
}

export async function postOutlineStructure(payload) {
  const controller = new AbortController()
  const timer = window.setTimeout(() => controller.abort(), OUTLINE_API_TIMEOUT_MS)
  try {
    return await api.post("/api/screenplay/structure-from-text", payload, {
      signal: controller.signal,
      timeout: OUTLINE_API_TIMEOUT_MS,
    })
  } catch (err) {
    if (
      err.code === "ECONNABORTED"
      || err.name === "CanceledError"
      || err.name === "AbortError"
    ) {
      throw new Error("大纲生成超时，请稍后重试")
    }
    throw err
  } finally {
    window.clearTimeout(timer)
  }
}

function formatOutlineScenes(scenes) {
  if (!Array.isArray(scenes)) return []
  return scenes.map((s) => {
    const scene = normalizeOutlineScene(s)
    return {
      ...scene,
      content: formatScreenplayParagraphs(scene.content || ""),
    }
  })
}

function formatOutlineVersions(versions) {
  if (!Array.isArray(versions)) return []
  return versions.map((v) => ({
    ...v,
    scenes: formatOutlineScenes(v.scenes),
  }))
}

/** 解析 structure-from-text 响应为 outline 节点 data 字段 */
export function parseOutlineStructureResponse(res, { sourceIdea, targetVideoDurationSec } = {}) {
  const rawVersions =
    Array.isArray(res.data?.versions) && res.data.versions.length > 0
      ? res.data.versions
      : [
          {
            title: res.data?.title || "",
            scenes: Array.isArray(res.data?.scenes) ? res.data.scenes : [],
          },
        ]
  const versions = formatOutlineVersions(rawVersions)
  const first = versions[0] || { title: "", scenes: [] }
  const title = first.title || res.data?.title || ""
  const scenes = formatOutlineScenes(first.scenes)
  return {
    loading: false,
    outlineLoadingStartedAt: undefined,
    title,
    scenes,
    versions,
    selectedVersionIndex: 0,
    error: null,
    truncated: res.data?.truncated === true,
    targetVideoDurationSec:
      res.data?.target_video_duration_sec ?? targetVideoDurationSec ?? null,
    sourceIdea: sourceIdea || "",
  }
}

/**
 * 将大纲 API 结果写入画布节点；优先 preferredOutlineId，否则按边 / linkedSourceId 查找。
 * @returns {{ ok: boolean, nodeIds?: string[], error?: string }}
 */
export function applyOutlineStructureToNodes(
  setNodes,
  { preferredOutlineId, responseId, outlineNodeId, outlineFields }
) {
  const targetOutlineId = outlineNodeId || preferredOutlineId
  if (!targetOutlineId) {
    return { ok: false, error: "大纲节点未找到，请刷新后重试" }
  }

  let applied = false
  flushSync(() => {
    setNodes((ns) => {
      const hasTarget = ns.some(
        (n) => n.id === targetOutlineId && n.type === "outline"
      )
      if (!hasTarget) return ns

      applied = true
      return ns.map((n) => {
        if (n.id === targetOutlineId && n.type === "outline") {
          return {
            ...n,
            data: {
              ...n.data,
              ...outlineFields,
            },
          }
        }
        if (responseId && n.id === responseId) {
          return {
            ...n,
            data: {
              ...n.data,
              outlineSynced: true,
              outlineNodeId: targetOutlineId,
            },
          }
        }
        return n
      })
    })
  })

  if (!applied) {
    return { ok: false, error: "大纲节点未找到，请刷新后重试" }
  }
  return { ok: true, nodeIds: [targetOutlineId] }
}
