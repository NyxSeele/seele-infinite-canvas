import api from "./api"

export async function fetchTaskRecords({ teamId = null, limit = 80 } = {}) {
  const params = { limit }
  if (teamId) params.team_id = teamId
  const res = await api.get("/api/tasks/records", { params })
  return res.data?.records ?? []
}

export async function submitTaskRating(taskId, { rating, tags = [], comment } = {}) {
  const res = await api.post(`/api/tasks/${taskId}/rating`, {
    rating,
    tags,
    comment,
  })
  return res.data
}
