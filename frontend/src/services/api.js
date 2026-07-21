import axios from "axios"
import { canvasWsManager } from "./canvasWs"
import { wsManager } from "./ws"

export const API_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "")

const AUTH_SKIP_REFRESH_PATHS = [
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/refresh",
  "/api/auth/logout",
]

let refreshPromise = null
let redirectingToLogin = false

/** token refresh 成功后重连任务/画布 WebSocket */
export function reconnectWebSocketsAfterAuthRefresh() {
  wsManager.reconnect()
  canvasWsManager.reconnect()
}

function shouldSkipAuthRefresh(url) {
  if (!url) return false
  return AUTH_SKIP_REFRESH_PATHS.some((path) => url.includes(path))
}

function redirectToLogin() {
  if (redirectingToLogin) return
  redirectingToLogin = true
  localStorage.removeItem("access_token")
  localStorage.removeItem("refresh_token")
  window.location.href = "/login"
}

/**
 * Single-flight refresh: concurrent 401s share one POST /api/auth/refresh.
 * @returns {Promise<string>} new access token
 */
export function refreshAccessToken() {
  if (!refreshPromise) {
    refreshPromise = (async () => {
      const refresh = localStorage.getItem("refresh_token")
      if (!refresh) {
        redirectToLogin()
        throw new Error("missing refresh token")
      }
      const { data } = await axios.post(`${API_BASE}/api/auth/refresh`, {
        refresh_token: refresh,
      })
      localStorage.setItem("access_token", data.access_token)
      reconnectWebSocketsAfterAuthRefresh()
      return data.access_token
    })().catch((err) => {
      redirectToLogin()
      throw err
    }).finally(() => {
      refreshPromise = null
    })
  }
  return refreshPromise
}

/** 生产环境 API_BASE 为空时，回退到当前页面的 ws/wss 源 */
export function getWsBase() {
  if (API_BASE && /^https?:\/\//i.test(API_BASE)) {
    return API_BASE.replace(/^http/i, "ws")
  }
  if (typeof window !== "undefined" && window.location?.host) {
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:"
    return `${proto}//${window.location.host}`
  }
  return "ws://127.0.0.1:7788"
}

const api = axios.create({
  baseURL: API_BASE,
  timeout: 20_000,
})

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
      !shouldSkipAuthRefresh(original.url)
    ) {
      original._retry = true
      try {
        const accessToken = await refreshAccessToken()
        original.headers.Authorization = `Bearer ${accessToken}`
        return api(original)
      } catch {
        return Promise.reject(error)
      }
    }
    return Promise.reject(error)
  }
)

export default api
