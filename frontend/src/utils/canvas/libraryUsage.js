/** 人物/场景库使用频次：分配镜头时更新 */

export function touchLibraryEntry(entry) {
  if (!entry) return entry
  return {
    ...entry,
    lastUsedAt: Date.now(),
    useCount: (Number(entry.useCount) || 0) + 1,
  }
}

export function touchLibraryById(library, id) {
  if (!id || !Array.isArray(library)) return library
  return library.map((item) => (item.id === id ? touchLibraryEntry(item) : item))
}

export function sortLibraryEntries(list, sortMode = "default") {
  const entries = [...(list || [])]
  if (sortMode !== "recent") return entries
  return entries.sort((a, b) => {
    const ta = Number(a.lastUsedAt) || 0
    const tb = Number(b.lastUsedAt) || 0
    if (tb !== ta) return tb - ta
    return (Number(b.useCount) || 0) - (Number(a.useCount) || 0)
  })
}

export function isRecentlyUsed(entry, withinMs = 7 * 24 * 60 * 60 * 1000) {
  const ts = Number(entry?.lastUsedAt) || 0
  if (!ts) return false
  return Date.now() - ts <= withinMs
}
