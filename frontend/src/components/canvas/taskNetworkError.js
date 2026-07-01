import { getT } from "../../utils/locale"

/** axios / fetch 网络层错误（后端不可达等） */
export function isNetworkError(err) {
  if (!err) return false
  const code = err.code || err.cause?.code
  if (code === "ERR_NETWORK" || code === "ECONNREFUSED" || code === "ENOTFOUND") {
    return true
  }
  const msg = String(err.message || "")
  if (
    msg.includes("Network Error")
    || msg.includes("Failed to fetch")
    || msg.includes("ECONNREFUSED")
  ) {
    return true
  }
  return !err.response && Boolean(err.request)
}

export function networkErrorMessage() {
  return getT()("canvas.error.noBackend")
}

export function comfyUnavailableMessage() {
  return getT()("canvas.error.comfyDown")
}

/** 从轮询接口响应或 axios 错误中解析用户可见文案 */
export function parseGenerationError(err, task) {
  if (task?.status === "failed" && task.error) {
    return String(task.error)
  }
  if (err) {
    if (isNetworkError(err)) {
      return networkErrorMessage()
    }
    const detail = err.response?.data?.detail
    if (typeof detail === "string" && detail.trim()) {
      return detail
    }
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || d).filter(Boolean).join("; ")
    }
    const status = err.response?.status
    if (status === 502 || status === 503) {
      return comfyUnavailableMessage()
    }
  }
  return getT()("canvas.error.genRetry")
}
