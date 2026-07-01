import { outlineSceneMetaEntries } from "./outlineSceneMeta"

export function outlineToExportText({ title = "", scenes = [] } = {}) {
  const lines = []
  if (title?.trim()) lines.push(title.trim(), "")
  for (const scene of scenes || []) {
    const heading = (scene.title || "").trim()
    if (heading) lines.push(`## ${heading}`)
    for (const entry of outlineSceneMetaEntries(scene)) {
      if (entry.value) lines.push(`${entry.label}：${entry.value}`)
    }
    const body = (scene.content || "").trim()
    if (body) lines.push(body)
    lines.push("")
  }
  return lines.join("\n").trim()
}

export function scriptTableToExportText({ rows = [], segments = [] } = {}) {
  const lines = []
  const segById = new Map((segments || []).map((s) => [s.id, s]))
  let lastSegId = null

  for (const row of rows || []) {
    const segId = row.segmentId
    if (segId && segId !== lastSegId) {
      const seg = segById.get(segId)
      if (seg?.title?.trim()) {
        lines.push(`# ${seg.title.trim()}`, "")
      }
      lastSegId = segId
    }
    const n = row.shotNumber ?? ""
    const dur = row.duration ?? ""
    const prompt = (row.prompt || row.description || "").trim()
    lines.push(`镜头 ${n}（${dur}s）`)
    if (prompt) lines.push(prompt)
    const pkg = row.compiledPromptPackage?.fullText || row.compiledPromptPackage?.apiDescription
    if (pkg?.trim() && pkg.trim() !== prompt) lines.push(pkg.trim())
    lines.push("")
  }
  return lines.join("\n").trim()
}
