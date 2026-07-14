import api from "./api"
import { pollTaskUntilDone } from "../utils/canvas/outlineStructureApi"

/** 上传入队应很快；分析走轮询 */
const STYLE_REF_UPLOAD_TIMEOUT_MS = 30000

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
  if (submitData?.style_reference) return submitData.style_reference
  const taskId = submitData?.task_id
  if (!taskId) throw new Error("未返回 task_id")
  const task = await pollTaskUntilDone(taskId, {
    timeoutMessage: "风格分析超时，请稍后重试",
  })
  return task.result || null
}

export async function uploadStyleReference(target, file) {
  const form = new FormData()
  form.append("file", file)
  if (target.kind === "shot") {
    const res = await api.post(
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
  const res = await api.post(
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
    return res.data?.style_reference ?? null
  }
  const res = await api.put(
    `/api/video-nodes/${target.nodeId}/style-reference`,
    body,
    nodeParams(target.projectId)
  )
  return res.data?.style_reference ?? null
}

export async function deleteStyleReference(target) {
  if (target.kind === "shot") {
    await api.delete(`/api/shots/${target.rowId}/style-reference`, shotQuery(target))
    return
  }
  await api.delete(
    `/api/video-nodes/${target.nodeId}/style-reference`,
    nodeParams(target.projectId)
  )
}
