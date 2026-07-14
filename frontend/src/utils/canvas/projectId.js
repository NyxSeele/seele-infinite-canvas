/** 是否为真实画布项目 ID（排除占位符 default / 空值） */
export function isRealProjectId(id) {
  if (id == null) return false
  const s = String(id).trim()
  if (!s || s === "default") return false
  return true
}
