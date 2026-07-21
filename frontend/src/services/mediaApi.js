import axios from "axios"
import api, { refreshAccessToken } from "./api"

const ENV_MEDIA_BASE = (import.meta.env.VITE_MEDIA_PUBLIC_BASE_URL ?? "").replace(/\/$/, "")

const AUTH_SKIP_REFRESH_PATHS = [
  "/api/auth/login",
  "/api/auth/register",
  "/api/auth/refresh",
  "/api/auth/logout",
]

let _capabilities = null
let _capabilitiesPromise = null
let _mediaApi = null

function shouldSkipAuthRefresh(url) {
  if (!url) return false
  return AUTH_SKIP_REFRESH_PATHS.some((path) => url.includes(path))
}

function attachAuthRefreshInterceptor(client) {
  client.interceptors.response.use(
    (res) => res,
    async (error) => {
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
          return client(original)
        } catch {
          return Promise.reject(error)
        }
      }
      return Promise.reject(error)
    }
  )
}

async function fetchCapabilities() {
  if (_capabilities) return _capabilities
  if (!_capabilitiesPromise) {
    _capabilitiesPromise = api
      .get("/api/upload/capabilities")
      .then((res) => {
        _capabilities = res.data || {}
        return _capabilities
      })
      .catch(() => {
        _capabilities = {}
        return _capabilities
      })
      .finally(() => {
        _capabilitiesPromise = null
      })
  }
  return _capabilitiesPromise
}

export async function getUploadCapabilities(force = false) {
  if (force) {
    _capabilities = null
  }
  return fetchCapabilities()
}

export function getMediaPublicBase() {
  const fromCaps = (_capabilities?.media_public_base || "").replace(/\/$/, "")
  return fromCaps || ENV_MEDIA_BASE || ""
}

export function shouldUseMediaBase(feature) {
  if (feature !== "canvas" && feature !== "team") return false
  const backend = _capabilities?.[feature]?.backend
  return backend === "local" && Boolean(getMediaPublicBase())
}

export async function ensureMediaApi() {
  await fetchCapabilities()
  const base = getMediaPublicBase()
  if (!base) return api
  if (!_mediaApi || _mediaApi.defaults.baseURL !== base) {
    _mediaApi = axios.create({ baseURL: base })
    _mediaApi.interceptors.request.use((config) => {
      const token = localStorage.getItem("access_token")
      if (token) {
        config.headers.Authorization = `Bearer ${token}`
      }
      return config
    })
    attachAuthRefreshInterceptor(_mediaApi)
  }
  return _mediaApi
}

/** Prefer AutoDL public base for large canvas/team transfers when configured. */
export async function mediaClientFor(feature) {
  await fetchCapabilities()
  return shouldUseMediaBase(feature) ? ensureMediaApi() : api
}

export default ensureMediaApi
