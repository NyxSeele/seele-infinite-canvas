/** 生成失败是否允许一键重试 */

const CONTENT_POLICY_PATTERNS = [
  /内容.*拦截/i,
  /敏感/i,
  /违规/i,
  /policy/i,
  /content.?filter/i,
  /审核/i,
  /blocked/i,
  /safety/i,
]

const CONFIG_PATTERNS = [
  /请选择.*模型/i,
  /select.*model/i,
  /空.*prompt/i,
  /empty.*prompt/i,
  /fill.*desc/i,
  /填写/i,
]

export function classifyGenerationError(errorText, httpStatus) {
  const msg = String(errorText || "").trim()
  if (!msg && !httpStatus) {
    return { kind: "unknown", retryable: true, reason: "" }
  }
  if (httpStatus === 400 && CONFIG_PATTERNS.some((p) => p.test(msg))) {
    return { kind: "config", retryable: false, reason: msg }
  }
  if (CONTENT_POLICY_PATTERNS.some((p) => p.test(msg))) {
    return {
      kind: "content_policy",
      retryable: false,
      reason: msg || "内容可能被拦截，请先修改提示词后再试",
    }
  }
  if (/timeout|超时|timed out/i.test(msg)) {
    return { kind: "timeout", retryable: true, reason: msg }
  }
  if (/ERR_NETWORK|network|无法连接|no backend|502|503|comfy/i.test(msg)) {
    return { kind: "network", retryable: true, reason: msg }
  }
  return { kind: "provider", retryable: true, reason: msg }
}

export function getRetryPolicy(errorText, httpStatus) {
  return classifyGenerationError(errorText, httpStatus)
}
