import { isOutlineLoadingStale } from "./outlineStructureApi"

/** 检测画布链路是否有进行中的异步步骤（Agent 应等待） */
export function getCanvasPipelineBusy(nodes) {
  if (!Array.isArray(nodes)) return { busy: false }

  for (const n of nodes) {
    if (n.type === "text-response" && n.data?.status === "generating") {
      return { busy: true, reason: "剧本文本正在生成中，请稍候再点「继续」" }
    }
    if (n.type === "outline" && n.data?.loading && !isOutlineLoadingStale(n)) {
      return { busy: true, reason: "剧本大纲正在生成中，请稍候再点「继续」" }
    }
    if (n.type === "script-table" && (n.data?.loading || n.data?.generatingFromOutline)) {
      return { busy: true, reason: "分镜表正在生成中，请稍候再点「继续」" }
    }
    if (n.type === "outline" && n.data?.generatingShots) {
      return { busy: true, reason: "分镜内容正在生成中，请稍候" }
    }
    if (n.type === "script-table") {
      for (const row of n.data?.rows || []) {
        if (row.status === "generating") {
          return { busy: true, reason: "分镜图正在生成中，请稍候再点「继续」" }
        }
        if ((row.keyframes || []).some((k) => k.status === "generating")) {
          return { busy: true, reason: "分镜图正在生成中，请稍候再点「继续」" }
        }
      }
    }
    if (n.type === "image-gen" && (n.data?.status === "generating" || n.data?.status === "pending")) {
      return { busy: true, reason: "图像正在生成中，请稍候" }
    }
    if (n.type === "video-gen" && (n.data?.status === "generating" || n.data?.status === "pending")) {
      return { busy: true, reason: "视频正在生成中，请稍候再点「继续」" }
    }
  }
  return { busy: false }
}

export function waitForNodeCondition(
  getNodes,
  nodeId,
  predicate,
  { timeoutMs = 120000, intervalMs = 400, missingError = "等待节点出现超时，请重试", signal } = {}
) {
  const deadline = Date.now() + timeoutMs
  return new Promise((resolve) => {
    const tick = () => {
      if (signal?.aborted) {
        resolve({ ok: false, error: "已停止" })
        return
      }
      const node = getNodes().find((n) => n.id === nodeId)
      if (!node) {
        if (Date.now() >= deadline) {
          resolve({ ok: false, error: missingError })
          return
        }
        window.setTimeout(tick, intervalMs)
        return
      }
      const result = predicate(node)
      if (result?.done) {
        resolve(result)
        return
      }
      if (Date.now() >= deadline) {
        resolve({ ok: false, error: result?.timeoutError || missingError })
        return
      }
      window.setTimeout(tick, intervalMs)
    }
    tick()
  })
}
