import api from "./api"
import { pollTaskUntilDone } from "../utils/canvas/outlineStructureApi"

export async function scanImportDocument({ projectId, file }) {
  const form = new FormData()
  form.append("project_id", projectId)
  form.append("file", file)
  const res = await api.post("/api/import/document/scan", form, {
    headers: { "Content-Type": "multipart/form-data" },
  })
  return res.data
}

export async function parseImportSheets({ projectId, importSessionId, sheetNames }) {
  const submit = await api.post(
    "/api/import/document/parse",
    {
      project_id: projectId,
      import_session_id: importSessionId,
      sheet_names: sheetNames,
    },
    { timeout: 30000 }
  )
  const taskId = submit.data?.task_id
  if (!taskId) {
    // 兼容旧同步响应
    return submit.data
  }
  const task = await pollTaskUntilDone(taskId, {
    timeoutMessage: "文档解析超时，请稍后重试",
  })
  return task.result || {}
}

export async function suggestImportGroups({
  projectId,
  importSessionId,
  sheetName,
  mode = "rule",
  targetDuration = 10,
}) {
  const body = {
    project_id: projectId,
    import_session_id: importSessionId,
    sheet_name: sheetName,
    mode,
  }
  if (mode === "rule") {
    body.target_duration = targetDuration
  }
  const submit = await api.post("/api/import/document/group-suggest", body, {
    timeout: 30000,
  })
  const taskId = submit.data?.task_id
  if (!taskId) {
    return submit.data
  }
  const task = await pollTaskUntilDone(taskId, {
    timeoutMessage: "分组建议超时，请稍后重试",
  })
  return task.result || {}
}

export async function applyImportDocument(payload) {
  const res = await api.post("/api/import/document/apply", payload)
  return res.data
}
