/** 将 FastAPI detail（字符串 / 校验错误数组 / 对象）转为可展示文案 */
export function formatApiError(detail, fallback = "操作失败") {
  if (!detail) return fallback
  if (typeof detail === "string") return detail
  if (Array.isArray(detail)) {
    const text = detail
      .map((d) => (d && typeof d === "object" ? d.msg || JSON.stringify(d) : String(d)))
      .filter(Boolean)
      .join("；")
    return text || fallback
  }
  if (typeof detail === "object" && detail.msg) return detail.msg
  return fallback
}
