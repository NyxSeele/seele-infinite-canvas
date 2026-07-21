import api from "./api"

export async function submitShortVideoGenerate(body) {
  const res = await api.post("/api/short-video/generate", body)
  return res.data
}

export async function fetchShortVideoTask(taskId) {
  const res = await api.get(`/api/short-video/${taskId}`)
  return res.data
}
