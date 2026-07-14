import axios from "axios"
import { API_BASE } from "./api"

/** Public review APIs — never redirect to /login on 401. */
const publicApi = axios.create({ baseURL: API_BASE })

export async function listPublicReviewVideos() {
  const res = await publicApi.get("/api/review/public/videos")
  return res.data || []
}

export async function getPublicReviewVideo(id) {
  const res = await publicApi.get(`/api/review/public/videos/${id}`)
  return res.data
}

export async function postPublicReviewComment(id, payload) {
  const res = await publicApi.post(`/api/review/public/videos/${id}/comment`, payload)
  return res.data
}
