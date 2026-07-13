import { flushSync } from "react-dom"
import api from "../../services/api"
import { formatScreenplayParagraphs } from "./textFormat"
import { normalizeOutlineScene } from "./outlineSceneMeta"
import { TASK_POLL_TIMEOUT_MS } from "../../components/canvas/taskPollTimeout"

const TASK_POLL_INTERVAL_MS = 2000

/** 单次提交超时（入队应很快）；总等待走轮询超时 */
export const OUTLINE_API_TIMEOUT_MS = TASK_POLL_TIMEOUT_MS
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

function sleep(ms) {
  return new Promise((resolve) => window.setTimeout(resolve, ms))
}

/**
 * 轮询 GET /api/tasks/{id} 直至终态。
 * @returns {Promise<object>} completed task payload (result already parsed for JSON async jobs)
 */
export async function pollTaskUntilDone(
  taskId,
  {
    intervalMs = TASK_POLL_INTERVAL_MS,
    timeoutMs = TASK_POLL_TIMEOUT_MS,
    timeoutMessage = "任务超时，请稍后重试",
  } = {}
) {
  const started = Date.now()
  while (Date.now() - started < timeoutMs) {
    const res = await api.get(`/api/tasks/${taskId}`, { timeout: 30000 })
    const task = res.data
    if (task?.status === "completed") return task
    if (task?.status === "failed" || task?.status === "cancelled") {
      throw new Error(task?.error || "任务失败")
    }
    await sleep(intervalMs)
  }
  throw new Error(timeoutMessage)
}

/**
 * 提交 structure-from-text（异步）并轮询结果。
 * 返回形态兼容旧同步接口：{ data: structureResult }
 */
export async function postOutlineStructure(payload) {
  try {
    const submit = await api.post("/api/screenplay/structure-from-text", payload, {
      timeout: 30000,
    })
    const taskId = submit.data?.task_id
    if (!taskId) {
      // 兼容偶发同步响应
      if (submit.data?.scenes || submit.data?.versions) return submit
      throw new Error("未返回 task_id")
    }
    const task = await pollTaskUntilDone(taskId, {
      timeoutMessage: "大纲生成超时，请稍后重试",
    })
    return { data: task.result || {} }
  } catch (err) {
    if (
      err.code === "ECONNABORTED"
      || err.name === "CanceledError"
      || err.name === "AbortError"
    ) {
      throw new Error("大纲生成超时，请稍后重试")
    }
    throw err
  }
}

/**
 * 提交 generate-shots（异步）并轮询结果。
 * 返回形态兼容旧同步接口：{ data: shotsResult }
 */
export async function postGenerateShots(payload) {
  const submit = await api.post("/api/screenplay/generate-shots", payload, {
    timeout: 30000,
  })
  const taskId = submit.data?.task_id
  if (!taskId) {
    if (Array.isArray(submit.data?.segments)) return submit
    throw new Error("未返回 task_id")
  }
  const task = await pollTaskUntilDone(taskId, {
    timeoutMessage: "分镜生成超时，请稍后重试",
  })
  return { data: task.result || {} }
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
