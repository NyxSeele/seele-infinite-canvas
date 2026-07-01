import { stripMediaTicket } from "../mediaTicket"

function normImageUrl(url) {
  if (!url) return ""
  return stripMediaTicket(url) || String(url)
}

export function makeSceneRefId() {
  return `scene-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function normalizeSceneLibraryEntry(item) {
  if (!item || !String(item.name || "").trim()) return null
  const imageUrl = item.imageUrl || null
  return {
    id: item.id || makeSceneRefId(),
    name: String(item.name).trim(),
    type: "scene",
    imageUrl,
    description: item.description ? String(item.description).trim() : "",
    pendingImage: !imageUrl,
    lastUsedAt: item.lastUsedAt != null ? Number(item.lastUsedAt) : null,
    useCount: Number(item.useCount) || 0,
    ...(item.globalAssetId ? { globalAssetId: item.globalAssetId } : {}),
  }
}

export function normalizeSceneLibrary(list, { requireImage = true } = {}) {
  const entries = (Array.isArray(list) ? list : [])
    .map(normalizeSceneLibraryEntry)
    .filter(Boolean)
  return requireImage ? entries.filter((e) => e.imageUrl) : entries
}

export function buildSceneThemeContext(sceneLibrary = []) {
  const list = normalizeSceneLibrary(sceneLibrary, { requireImage: false })
  if (!list.length) return ""
  return list
    .map((item) => {
      const desc = item.description ? `，${item.description}` : ""
      const visual = item.imageUrl
        ? "保持与场景参考图一致的空间与氛围"
        : "（待配图，以文字描述为准）"
      return `场景「${item.name}」${desc}：${visual}`
    })
    .join("；")
}

export { normImageUrl as sceneNormImageUrl }
