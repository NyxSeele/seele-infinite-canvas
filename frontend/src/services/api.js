import axios from "axios"

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")

const api = axios.create({ baseURL: API_BASE })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token")
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error) => {
    if (error.response?.status === 401) {
      const token = localStorage.getItem("access_token")
      console.warn(
        "request 401:",
        error.config?.baseURL || "",
        error.config?.url || "",
        "token:",
        token ? `${token.slice(0, 12)}…` : "(missing)"
      )
    }
    const original = error.config
    if (
      error.response?.status === 401 &&
      original &&
      !original._retry &&
      !original.url?.includes("/api/auth/login") &&
      !original.url?.includes("/api/auth/register")
    ) {
      original._retry = true
      const refresh = localStorage.getItem("refresh_token")
      if (refresh) {
        try {
          const { data } = await axios.post(`${API_BASE}/api/auth/refresh`, {
            refresh_token: refresh,
          })
          localStorage.setItem("access_token", data.access_token)
          original.headers.Authorization = `Bearer ${data.access_token}`
          return api(original)
        } catch {
          localStorage.removeItem("access_token")
          localStorage.removeItem("refresh_token")
          window.location.href = "/login"
        }
      } else {
        window.location.href = "/login"
      }
    }
    return Promise.reject(error)
  }
)

export default api
