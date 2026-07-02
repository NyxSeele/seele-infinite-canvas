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
  if (typeof err === "string" && err.trim()) {
    return mapEnhanceError(err)
  }
  if (task?.status === "failed" && task.error) {
    return mapEnhanceError(String(task.error))
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
    const status = err.response?.status
    if (status === 502 || status === 503) {
      return comfyUnavailableMessage()
    }
  }
  return getT()("canvas.error.genRetry")
}

/** 画质增强 / Comfy 错误文案映射 */
export function mapEnhanceError(detail) {
  const raw = String(detail || "").trim()
  if (!raw) return getT()("canvas.error.genRetry")
  const lower = raw.toLowerCase()
  const t = getT()
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
    return t("canvas.video.enhanceModelMissing", { detail: raw })
  }
  if (lower.includes("vhs") || lower.includes("video helper suite")) {
    return t("canvas.video.enhancePluginMissing")
  }
  return raw
}
