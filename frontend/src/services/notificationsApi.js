import api from "./api"

export async function fetchNotifications({ limit = 50, offset = 0 } = {}) {
  const res = await api.get("/api/notifications", { params: { limit, offset } })
  return res.data
}

export async function markNotificationsRead({ notificationIds = [], markAll = false } = {}) {
  const res = await api.post("/api/notifications/mark-read", {
    notification_ids: notificationIds,
    mark_all: markAll,
  })
  return res.data
}
