/** 节点 data.meta 最后编辑信息 */
export function stampEditMeta(patch, user) {
  if (!user) return patch
  const username = user.username || String(user.id)
  const now = new Date().toISOString()
  const prevMeta = patch?.meta && typeof patch.meta === "object" ? patch.meta : {}
  return {
    ...patch,
    meta: {
      ...prevMeta,
      lastEditedBy: username,
      lastEditedAt: now,
    },
  }
}

export function formatNodeEditMeta(meta) {
  if (!meta?.lastEditedAt) return null
  const by = meta.lastEditedBy || "未知"
  let timeStr = meta.lastEditedAt
  try {
    timeStr = new Date(meta.lastEditedAt).toLocaleString("zh-CN", {
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    /* keep raw */
  }
  return `${by} · ${timeStr}`
}
