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

/** 网关瞬态错误（后端重启、反代断连等） */
export function isTransientGatewayError(err) {
  if (!err) return false
  const status = err.response?.status ?? err.status
  return status === 502 || status === 503 || status === 504
}

/** 轮询可自动重试的瞬态错误 */
export function isTransientPollError(err) {
  return isNetworkError(err) || isTransientGatewayError(err)
}

export function networkErrorMessage() {
  return getT()("canvas.error.noBackend")
}

export function comfyUnavailableMessage() {
  return getT()("canvas.error.comfyDown")
}

function coerceErrorText(value) {
  if (value == null) return ""
  if (typeof value === "string") return value.trim()
  if (typeof value === "object") {
    const msg =
      value.exception_message
      || value.message
      || value.detail
      || value.error
    if (typeof msg === "string" && msg.trim()) {
      const excType = value.exception_type ? `${value.exception_type}: ` : ""
      return `${excType}${msg}`.trim()
    }
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }
  return String(value).trim()
}

/** 从轮询接口响应或 axios 错误中解析用户可见文案 */
export function parseGenerationError(err, task) {
  if (typeof err === "string" && err.trim()) {
    return mapEnhanceError(err)
  }
  if (task?.status === "failed" && task.error) {
    return mapEnhanceError(coerceErrorText(task.error))
  }
  if (err) {
    if (isNetworkError(err)) {
      return networkErrorMessage()
    }
    const detail = err.response?.data?.detail
    if (typeof detail === "string" && detail.trim()) {
      return mapEnhanceError(detail)
    }
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || d).filter(Boolean).join("; ")
    }
    if (detail && typeof detail === "object") {
      return mapEnhanceError(coerceErrorText(detail))
    }
    const status = err.response?.status
    if (status === 502 || status === 503) {
      return comfyUnavailableMessage()
    }
    if (err.message) {
      return mapEnhanceError(String(err.message))
    }
  }
  return getT()("canvas.error.genRetry")
}

/** 画质增强 / Comfy 错误文案映射 */
export function mapEnhanceError(detail) {
  const raw = coerceErrorText(detail)
  if (!raw) return getT()("canvas.error.genRetry")
  const lower = raw.toLowerCase()
  const t = getT()
  if (
    lower.includes("out of memory")
    || lower.includes("outofmemory")
    || lower.includes("cuda oom")
    || lower.includes("allocation on device")
    || raw.includes("显存不足")
  ) {
    return t("canvas.error.oom")
  }
  if (raw.includes("非法上传路径") || raw.includes("视频源无效")) {
    return t("canvas.video.enhanceInvalidSource")
  }
  if (raw.includes("不支持画质增强")) {
    return t("canvas.video.enhanceUnavailable")
  }
  if (
    lower.includes("not found")
    || lower.includes("does not exist")
    || raw.includes("缺少画质增强模型")
    || raw.includes("缺少所需模型")
    || lower.includes("seedvr")
    || lower.includes("realesrgan")
  ) {
    return t("canvas.video.enhanceModelMissing", { detail: raw.slice(0, 180) })
  }
  if (lower.includes("vhs") || lower.includes("video helper suite")) {
    return t("canvas.video.enhancePluginMissing")
  }
  if (raw.length > 240) return `${raw.slice(0, 240).trimEnd()}…`
  return raw
}
