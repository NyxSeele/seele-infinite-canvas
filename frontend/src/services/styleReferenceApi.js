import api from "./api"
import { mediaClientFor } from "./mediaApi"
import { pollTaskUntilDone } from "../utils/canvas/outlineStructureApi"
import { useCanvasStore } from "../stores"

/** 大视频上传走 AutoDL；分析仍轮询 */
const STYLE_REF_UPLOAD_TIMEOUT_MS = 120_000

function syncCanvasVersion(payload) {
  if (payload?.version != null) {
    useCanvasStore.getState().setProjectVersion(payload.version)
  }
}

function unwrapStyleRefPayload(payload) {
  if (!payload || typeof payload !== "object") return null
  if (payload.style_reference != null) {
    syncCanvasVersion(payload)
    return payload.style_reference
  }
  // 兼容旧任务结果：result 直接是 style_reference 对象
  if (
    payload.color_tone != null
    || payload.style_keywords != null
    || payload.display_summary != null
  ) {
    return payload
  }
  return null
}

function shotQuery({ projectId, scriptTableNodeId }) {
  return {
    params: {
      project_id: projectId,
      script_table_node_id: scriptTableNodeId,
    },
  }
}

function nodeParams(projectId) {
  return { params: { project_id: projectId } }
}

export function resolveStyleReferenceTarget({ projectId, nodeId, scriptTableRef }) {
  if (scriptTableRef?.nodeId && scriptTableRef?.rowId) {
    return {
      kind: "shot",
      projectId,
      scriptTableNodeId: scriptTableRef.nodeId,
      rowId: scriptTableRef.rowId,
      nodeId,
    }
  }
  return { kind: "node", projectId, nodeId }
}

export async function fetchStyleReference(target) {
  if (target.kind === "shot") {
    const res = await api.get(
      `/api/shots/${target.rowId}/style-reference`,
      shotQuery(target)
    )
    return res.data?.style_reference ?? null
  }
  const res = await api.get(
    `/api/video-nodes/${target.nodeId}/style-reference`,
    nodeParams(target.projectId)
  )
  return res.data?.style_reference ?? null
}

async function waitStyleRefResult(submitData) {
  const direct = unwrapStyleRefPayload(submitData)
  if (direct) return direct
  const taskId = submitData?.task_id
  if (!taskId) throw new Error("未返回 task_id")
  const task = await pollTaskUntilDone(taskId, {
    timeoutMessage: "风格分析超时，请稍后重试",
  })
  return unwrapStyleRefPayload(task.result)
}

export async function uploadStyleReference(target, file) {
  const client = await mediaClientFor("canvas")
  const form = new FormData()
  form.append("file", file)
  if (target.kind === "shot") {
    const res = await client.post(
      `/api/shots/${target.rowId}/style-reference`,
      form,
      {
        ...shotQuery(target),
        timeout: STYLE_REF_UPLOAD_TIMEOUT_MS,
        headers: { "Content-Type": "multipart/form-data" },
      }
    )
    return waitStyleRefResult(res.data)
  }
  const res = await client.post(
    `/api/video-nodes/${target.nodeId}/style-reference`,
    form,
    {
      ...nodeParams(target.projectId),
      timeout: STYLE_REF_UPLOAD_TIMEOUT_MS,
      headers: { "Content-Type": "multipart/form-data" },
    }
  )
  return waitStyleRefResult(res.data)
}

export async function updateStyleReference(target, body) {
  if (target.kind === "shot") {
    const res = await api.put(
      `/api/shots/${target.rowId}/style-reference`,
      body,
      shotQuery(target)
    )
    syncCanvasVersion(res.data)
    return res.data?.style_reference ?? null
  }
  const res = await api.put(
    `/api/video-nodes/${target.nodeId}/style-reference`,
    body,
    nodeParams(target.projectId)
  )
  syncCanvasVersion(res.data)
  return res.data?.style_reference ?? null
}

export async function deleteStyleReference(target) {
  if (target.kind === "shot") {
    const res = await api.delete(
      `/api/shots/${target.rowId}/style-reference`,
      shotQuery(target)
    )
    syncCanvasVersion(res.data)
    return
  }
  const res = await api.delete(
    `/api/video-nodes/${target.nodeId}/style-reference`,
    nodeParams(target.projectId)
  )
  syncCanvasVersion(res.data)
}
