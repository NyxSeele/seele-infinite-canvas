import api from "./api"

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
  const res = await api.post("/api/import/document/parse", {
    project_id: projectId,
    import_session_id: importSessionId,
    sheet_names: sheetNames,
  })
  return res.data
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
  const res = await api.post("/api/import/document/group-suggest", body)
  return res.data
}

export async function applyImportDocument(payload) {
  const res = await api.post("/api/import/document/apply", payload)
  return res.data
}
