import api from "./api"

export async function fetchProfile() {
  const res = await api.get("/api/auth/me")
  return res.data
}

export async function updateProfile(payload) {
  const res = await api.patch("/api/auth/profile", payload)
  return res.data
}
