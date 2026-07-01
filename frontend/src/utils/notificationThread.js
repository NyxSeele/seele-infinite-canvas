import { fetchNotifications, markNotificationsRead } from "../services/notificationsApi"

/** 同一张卡片上的评论线程（按 project + node 聚合） */
export function notificationThreadKey(payload) {
  if (!payload?.project_id || !payload?.node_id) return null
  return `${payload.project_id}:${payload.node_id}`
}

export function collectThreadNotifications(items, item) {
  const key = notificationThreadKey(item?.payload)
  if (!key) return item ? [item] : []
  return (items || []).filter((i) => notificationThreadKey(i.payload) === key)
}

export function applyReadToItems(items, readIds) {
  const idSet = new Set(readIds)
  return (items || []).map((i) => (idSet.has(i.id) ? { ...i, is_read: true } : i))
}

export async function markThreadNotificationsRead(items, item) {
  const related = collectThreadNotifications(items, item)
  const unread = related.filter((i) => !i.is_read)
  const ids = unread.map((i) => i.id)
  const commentIds = [
    ...new Set(unread.map((i) => i.payload?.comment_id).filter(Boolean)),
  ]
  if (ids.length) {
    await markNotificationsRead({ notificationIds: ids })
  }
  return { ids, commentIds, related }
}

export async function markNodeMentionNotificationsRead(projectId, nodeId, items = null) {
  const list = items || (await fetchNotifications({ limit: 100 }))?.notifications || []
  const unread = list.filter(
    (n) => !n.is_read
      && n.payload?.project_id === projectId
      && n.payload?.node_id === nodeId
  )
  const ids = unread.map((n) => n.id)
  const commentIds = [
    ...new Set(unread.map((n) => n.payload?.comment_id).filter(Boolean)),
  ]
  if (ids.length) {
    await markNotificationsRead({ notificationIds: ids })
  }
  return { ids, commentIds, unreadCount: unread.length }
}
