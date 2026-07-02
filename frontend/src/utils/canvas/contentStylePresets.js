/** 项目级内容风格（与行级画风 qualityPreset 正交） */
export const DEFAULT_CONTENT_STYLE = "photorealistic_cinema"

export const CONTENT_STYLE_OPTIONS = [
  { id: "photorealistic_cinema", name: "写实电影" },
  { id: "generic", name: "通用" },
]

export function normalizeContentStyle(value) {
  if (value === "generic") return "generic"
  return DEFAULT_CONTENT_STYLE
}

export function findScriptTableNode(nodes) {
  if (!Array.isArray(nodes)) return null
  return nodes.find((n) => n.type === "script-table") || null
}

export function getProjectContentStyle(nodes) {
  const st = findScriptTableNode(nodes)
  return normalizeContentStyle(st?.data?.contentStyle)
}

export function getScriptTableContentStyle(data) {
  return normalizeContentStyle(data?.contentStyle)
}
