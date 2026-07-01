import { stripMediaTicket } from "../../utils/mediaTicket"

export const MAX_REFERENCE_IMAGES = 5

export function isBlobUrl(url) {
  return typeof url === "string" && url.startsWith("blob:")
}

import { getT } from "../../utils/locale"

function interruptedError() {
  return getT()("canvas.gen.interrupted")
}

function refImageLabel() {
  return getT()("canvas.prompt.refImage")
}

/** 过滤不可持久化的 blob: URL */
export function normalizePersistentImageUrl(url) {
  if (!url || typeof url !== "string") return null
  if (isBlobUrl(url)) return null
  return url
}

/** 画布加载/保存前剔除 blob:，避免刷新后图片失效 */
const STUCK_GENERATION_STATUSES = new Set(["pending", "generating", "queued"])

/**
 * 刷新/异常退出后：勿恢复「生成中」——否则会卡死 UI 或触发异常轮询。
 */
/** 重新提交前清空节点上的旧任务绑定，避免轮询僵尸 taskId */
export function buildClearGenerationTaskPatch(overrides = {}) {
  return {
    taskId: null,
    taskIds: null,
    error: null,
    progress: 0,
    pendingTrigger: null,
    ...overrides,
  }
}

export function resetStaleGenerationState(data, nodeType) {
  if (!data || typeof data !== "object") return data
  const next = { ...data }

  if (nodeType === "text-response") {
    next.outlineAutoPending = false
  }
  if (nodeType === "outline") {
    next.loading = false
    next.generatingShots = false
  }
  if (nodeType === "script-table") {
    next.loading = false
    next.generatingFromOutline = false
  }

  if (nodeType === "script-table" && Array.isArray(next.rows)) {
    next.rows = next.rows.map((row) => {
      const stuckRow = row?.status === "generating" || row?.status === "building"
      const keyframes = (row.keyframes || []).map((kf) => {
        if (kf?.status !== "generating" && kf?.status !== "building") return kf
        return {
          ...kf,
          status: "idle",
          error: kf.error || interruptedError(),
        }
      })
      if (!stuckRow && keyframes.every((kf, i) => kf === row.keyframes?.[i])) return row
      return {
        ...row,
        status: stuckRow ? "idle" : row.status,
        error: stuckRow ? row.error || interruptedError() : row.error,
        keyframes,
      }
    })
    return next
  }

  const stuck = STUCK_GENERATION_STATUSES.has(next.status)
  if (!stuck) return next

  if (nodeType === "video-gen" && next.videoUrl) {
    next.status = "completed"
    next.error = null
    next.pendingTrigger = null
    return next
  }

  next.status = nodeType === "image-gen" ? "failed" : "error"
  next.error = next.error || interruptedError()
  next.pendingTrigger = null
  next.taskId = null
  next.taskIds = null
  return next
}

export function sanitizeNodeDataForPersist(data) {
  if (!data || typeof data !== "object") return data
  const next = { ...data }
  const scalarFields = [
    "uploadedImage",
    "imageUrl",
    "referenceImage",
    "referenceImageUrl",
    "videoUrl",
    "resultUrl",
  ]
  for (const key of scalarFields) {
    if (isBlobUrl(next[key])) {
      console.warn("[canvas] 清除无效 blob URL:", key, next[key])
      next[key] = null
    } else if (next[key]) {
      next[key] = stripMediaTicket(next[key])
    }
  }
  if (Array.isArray(next.results)) {
    next.results = next.results
      .map((u) => (isBlobUrl(u) ? null : u ? stripMediaTicket(u) : null))
      .filter(Boolean)
  }
  if (Array.isArray(next.referenceImages)) {
    next.referenceImages = next.referenceImages
      .map((r) => {
        if (!r?.imageUrl || isBlobUrl(r.imageUrl)) return null
        return r
      })
      .filter(Boolean)
  }
  if (next.referenceRef?.imageUrl && isBlobUrl(next.referenceRef.imageUrl)) {
    next.referenceRef = null
  }
  if (next.keyframes) {
    const kf = { ...next.keyframes }
    for (const slot of ["first", "last"]) {
      if (kf[slot]?.imageUrl && isBlobUrl(kf[slot].imageUrl)) kf[slot] = null
    }
    next.keyframes = kf
  }
  if (Array.isArray(next.freeRefs)) {
    next.freeRefs = next.freeRefs.filter((r) => r?.imageUrl && !isBlobUrl(r.imageUrl))
  }
  if (next.styleReference && typeof next.styleReference === "object") {
    const sr = { ...next.styleReference }
    if (sr.source_video_url) {
      sr.source_video_url = isBlobUrl(sr.source_video_url)
        ? null
        : stripMediaTicket(sr.source_video_url)
    }
    next.styleReference = sr
  }
  if (Array.isArray(next.rows)) {
    next.rows = next.rows.map((row) => {
      if (!row || typeof row !== "object") return row
      const r = { ...row }
      if (isBlobUrl(r.referenceImage)) {
        r.referenceImage = null
      } else if (r.referenceImage) {
        r.referenceImage = stripMediaTicket(r.referenceImage)
      }
      if (r.resultUrl) {
        r.resultUrl = isBlobUrl(r.resultUrl) ? null : stripMediaTicket(r.resultUrl)
      }
      if (Array.isArray(r.keyframes)) {
        r.keyframes = r.keyframes.map((kf) => {
          const k = { ...kf }
          if (isBlobUrl(k.referenceImage)) k.referenceImage = null
          else if (k.referenceImage) k.referenceImage = stripMediaTicket(k.referenceImage)
          if (k.resultUrl) {
            k.resultUrl = isBlobUrl(k.resultUrl) ? null : stripMediaTicket(k.resultUrl)
          }
          return k
        })
      }
      return r
    })
  }
  delete next.outlineAutoPending
  delete next.intentGated
  if (next.generatingShots) next.generatingShots = false
  if (next.generatingFromOutline) next.generatingFromOutline = false
  if (next.loading) next.loading = false
  return next
}

/** 从节点 data 读取参考图列表（兼容旧单图字段） */
export function getReferenceImagesList(data) {
  if (!data) return []
  if (Array.isArray(data.referenceImages) && data.referenceImages.length > 0) {
    return data.referenceImages
  }
  if (data.referenceRef?.imageUrl) {
    return [data.referenceRef]
  }
  const url = data.referenceImageUrl || data.referenceImage
  if (!url) return []
  return [
    buildRefItem({
      nodeId: data.referenceRef?.nodeId || "",
      imageIndex: data.referenceRef?.imageIndex ?? 0,
      imageUrl: url,
      imageId: data.referenceRef?.imageId,
      label: data.referenceRef?.label || refImageLabel(),
    }),
  ]
}

/** 为缺少 imageUrl 的参考项从画布节点补全 URL */
export function resolveReferenceImageUrl(refItem, getNode) {
  if (!refItem) return null
  const url = normalizePersistentImageUrl(refItem.imageUrl)
  if (url) return { ...refItem, imageUrl: url }
  if (!refItem.nodeId || typeof getNode !== "function") return refItem

  const node = getNode(refItem.nodeId)
  if (!node) return refItem

  const images = getImageNodeImages(node)
  if (!images.length) return refItem

  const idx = refItem.imageIndex ?? 0
  const match =
    images.find((r) => r.imageIndex === idx)
    || images[idx]
    || images[0]
  if (!match?.imageUrl) return refItem

  return {
    ...refItem,
    imageUrl: match.imageUrl,
    label: refItem.label || match.label || refImageLabel(),
    imageId: refItem.imageId || match.imageId,
  }
}

/** 解析并补全参考图列表，过滤无 URL 项 */
export function getResolvedReferenceImagesList(data, getNode) {
  return getReferenceImagesList(data)
    .map((ref) => resolveReferenceImageUrl(ref, getNode))
    .filter((ref) => ref?.imageUrl)
}

/** 追加参考图（去重、上限） */
export function appendReferenceImage(list, refItem, max = MAX_REFERENCE_IMAGES) {
  if (!refItem?.imageUrl) return list
  if (list.length >= max) return list
  const id = refItem.imageId || `${refItem.nodeId}_${refItem.imageIndex ?? 0}`
  if (list.some((r) => (r.imageId || `${r.nodeId}_${r.imageIndex ?? 0}`) === id)) {
    return list
  }
  return [...list, refItem]
}

/** 构建带索引的参考项 */
export function buildRefItem({ nodeId, imageIndex, imageUrl, imageId, label }) {
  const idx = imageIndex ?? 0
  return {
    nodeId,
    imageIndex: idx,
    imageUrl,
    imageId: imageId ?? `${nodeId}_${idx}`,
    label: label && String(label).trim() ? String(label).trim() : "Image",
  }
}

/** 从 image-gen 节点构建参考项 */
export function refFromImageNode(node) {
  return getImageNodeOutgoingRef(node)
}

/** 列出 image-gen 节点上的全部可引用图片（含多宫格） */
export function getImageNodeImages(node) {
  if (!node) return []
  const d = node.data || {}
  const label = d.label && String(d.label).trim() ? String(d.label).trim() : "Image"
  let rawResults = Array.isArray(d.results) ? d.results.filter(Boolean) : []
  if (rawResults.length === 0 && d.resultUrl) {
    rawResults = [d.resultUrl]
  }

  if (rawResults.length > 0) {
    const multi = rawResults.length > 1
    return rawResults
      .map((url, index) => {
        const safe = normalizePersistentImageUrl(url)
        return safe ? buildRefItem({
          nodeId: node.id,
          imageIndex: index,
          imageUrl: safe,
          label: multi ? `${label} #${index + 1}` : label,
        }) : null
      })
      .filter(Boolean)
  }

  const imageUrl = normalizePersistentImageUrl(d.uploadedImage || d.imageUrl || null)
  if (!imageUrl) return []
  return [buildRefItem({ nodeId: node.id, imageIndex: 0, imageUrl, label })]
}

/** 下游连线可自动获取的参考图（仅单图节点） */
export function getImageNodeOutgoingRef(node) {
  if (!node) return null
  const d = node.data || {}
  const rawResults = Array.isArray(d.results) ? d.results : []
  const label = d.label && String(d.label).trim() ? String(d.label).trim() : "Image"

  if (rawResults.length > 1) {
    return null
  }

  if (rawResults.length === 1 && rawResults[0]) {
    const safe = normalizePersistentImageUrl(rawResults[0])
    if (!safe) return null
    return buildRefItem({
      nodeId: node.id,
      imageIndex: 0,
      imageUrl: safe,
      label,
    })
  }

  const imageUrl = normalizePersistentImageUrl(d.uploadedImage || d.imageUrl || null)
  if (!imageUrl) return null
  return buildRefItem({
    nodeId: node.id,
    imageIndex: 0,
    imageUrl,
    label,
  })
}

/** 从画布边查询：图片节点 → 已连接的视频节点 */
export function getConnectedVideoNodesFromEdges(edges, nodeInternals, imageNodeId) {
  const list = []
  edges.forEach((e) => {
    if (e.source !== imageNodeId) return
    const target = nodeInternals.get(e.target)
    if (target?.type !== "video-gen") return
    const vlabel =
      target.data?.label && String(target.data.label).trim()
        ? String(target.data.label).trim()
        : "Video"
    list.push({ id: target.id, label: vlabel })
  })
  return list
}

export const DEFAULT_KEYFRAMES = { first: null, last: null }

export function truncateLabel(text, maxLen = 4) {
  const s = String(text || "")
  if (s.length <= maxLen) return s
  return `${s.slice(0, maxLen)}…`
}
