import { ensureMediaUrl, stripMediaTicket } from "../../utils/mediaTicket"
import { resolveCanvasR2MediaUrl } from "../../utils/r2MediaUrl"

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

/** 是否为可在 img src 中加载的媒体 URL */
export function isDisplayableMediaUrl(url) {
  if (!url || typeof url !== "string") return false
  const s = url.trim()
  if (!s || isBlobUrl(s)) return false
  if (s.startsWith("data:")) return true
  if (s.startsWith("http://") || s.startsWith("https://")) return true
  if (s.includes("/api/view") || s.includes("/api/uploads") || s.includes("/uploads/")) return true
  if (s.startsWith("/canvas/") || s.startsWith("canvas/")) return true
  const r2 = resolveCanvasR2MediaUrl(s)
  return Boolean(r2 && r2.startsWith("http"))
}

/** 过滤不可持久化的 blob: URL；R2 裸路径在已知 base 时补全为公网 URL */
export function normalizePersistentImageUrl(url) {
  if (!url || typeof url !== "string") return null
  if (isBlobUrl(url)) return null
  const resolved = resolveCanvasR2MediaUrl(url)
  return resolved || url
}

/** 画布加载/保存前剔除 blob:，避免刷新后图片失效 */
const STUCK_GENERATION_STATUSES = new Set(["pending", "generating", "queued"])

/** 节点数据上是否仍有可恢复的后端任务 ID */
function hasRecoverableTaskIds(data) {
  if (data?.taskId) return true
  return Array.isArray(data?.taskIds) && data.taskIds.length > 0
}

/**
 * 刷新/异常退出后：有 taskId 时恢复为 pending 交给轮询；无任务 ID 则标中断。
 */
/** 重新提交前清空节点上的旧任务绑定，避免轮询僵尸 taskId */
export function buildClearGenerationTaskPatch(overrides = {}) {
  return {
    taskId: null,
    taskIds: null,
    error: null,
    progress: 0,
    pendingTrigger: null,
    completedAt: null,
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
      const stuckDirect = row?.directStatus === "generating"
      const keyframes = (row.keyframes || []).map((kf) => {
        if (kf?.status !== "generating" && kf?.status !== "building") return kf
        return {
          ...kf,
          status: "idle",
          error: kf.error || interruptedError(),
        }
      })
      if (!stuckRow && !stuckDirect && keyframes.every((kf, i) => kf === row.keyframes?.[i])) return row
      return {
        ...row,
        status: stuckRow ? "idle" : row.status,
        error: stuckRow ? row.error || interruptedError() : row.error,
        directStatus: stuckDirect ? "idle" : row.directStatus,
        directResultUrl: stuckDirect ? null : row.directResultUrl,
        keyframes,
      }
    })
    return next
  }

  const stuck = STUCK_GENERATION_STATUSES.has(next.status)
  if (!stuck) return next

  const recoverable = hasRecoverableTaskIds(next)

  if (recoverable) {
    next.status = "pending"
    next.pendingTrigger = null
    next.error = null
    return next
  }

  if (nodeType === "video-gen" && next.videoUrl) {
    next.status = "error"
    next.error = next.error || interruptedError()
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

function resolveReferenceImageUrlFromNode(refItem, getNode) {
  if (!refItem?.nodeId || typeof getNode !== "function") return null
  const node = getNode(refItem.nodeId)
  if (!node) return null

  const images = getImageNodeImages(node)
  if (!images.length) return null

  const idx = refItem.imageIndex ?? 0
  const match =
    images.find((r) => r.imageIndex === idx)
    || images[idx]
    || images[0]
  if (!match?.imageUrl) return null

  return {
    ...refItem,
    imageUrl: match.imageUrl,
    label: refItem.label || match.label || refImageLabel(),
    imageId: refItem.imageId || match.imageId,
  }
}

/** 为缺少 imageUrl 的参考项从画布节点补全 URL */
export function resolveReferenceImageUrl(refItem, getNode) {
  if (!refItem) return null

  const stored = normalizePersistentImageUrl(refItem.imageUrl)
  if (stored && isDisplayableMediaUrl(stored)) {
    return { ...refItem, imageUrl: stored }
  }

  const fromNode = resolveReferenceImageUrlFromNode(refItem, getNode)
  if (fromNode?.imageUrl && isDisplayableMediaUrl(fromNode.imageUrl)) {
    return fromNode
  }

  if (stored) return { ...refItem, imageUrl: stored }
  return fromNode || refItem
}

/** 展示用 URL：解析参考项并附加媒体 ticket */
export function resolveRefDisplayUrl(ref, getNode) {
  if (!ref) return null
  const resolved = resolveReferenceImageUrl(ref, getNode)
  if (!resolved?.imageUrl || isBlobUrl(resolved.imageUrl)) return null
  const display = ensureMediaUrl(resolved.imageUrl)
  if (!display || isBlobUrl(display)) return null
  return display
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
  const rawResults = Array.isArray(d.results) ? d.results : []
  const filledCount = rawResults.filter(Boolean).length

  if (filledCount > 0) {
    const multi = filledCount > 1
    return rawResults
      .map((url, index) => {
        const safe = normalizePersistentImageUrl(url)
        return safe
          ? buildRefItem({
            nodeId: node.id,
            imageIndex: index,
            imageUrl: safe,
            label: multi ? `${label} #${index + 1}` : label,
          })
          : null
      })
      .filter(Boolean)
  }

  const imageUrl = normalizePersistentImageUrl(
    d.resultUrl || d.uploadedImage || d.imageUrl || d.generatedImage || null,
  )
  if (!imageUrl) return []
  return [buildRefItem({ nodeId: node.id, imageIndex: 0, imageUrl, label })]
}

/** 下游连线可自动获取的参考图（多结果时取首张） */
export function getImageNodeOutgoingRef(node) {
  if (!node) return null
  const d = node.data || {}
  const rawResults = Array.isArray(d.results) ? d.results : []
  const label = d.label && String(d.label).trim() ? String(d.label).trim() : "Image"

  const firstResultIndex = rawResults.findIndex(Boolean)
  if (firstResultIndex >= 0) {
    const safe = normalizePersistentImageUrl(rawResults[firstResultIndex])
    if (!safe || !isDisplayableMediaUrl(safe)) return null
    return buildRefItem({
      nodeId: node.id,
      imageIndex: firstResultIndex,
      imageUrl: safe,
      label,
    })
  }

  const imageUrl = normalizePersistentImageUrl(
    d.resultUrl || d.uploadedImage || d.imageUrl || d.generatedImage || null,
  )
  if (!imageUrl || !isDisplayableMediaUrl(imageUrl)) return null
  return buildRefItem({
    nodeId: node.id,
    imageIndex: 0,
    imageUrl,
    label,
  })
}

/** 删除来自指定源节点的参考图 / 首尾帧 / linkedSource 关联 */
export function removeRefsSourcedFromNode(data, sourceNodeId) {
  if (!data || !sourceNodeId) return null

  const patch = {}
  const keyframes = data.keyframes || DEFAULT_KEYFRAMES
  const nextKeyframes = { ...keyframes }
  let keyframesChanged = false

  if (nextKeyframes.first?.nodeId === sourceNodeId) {
    nextKeyframes.first = null
    keyframesChanged = true
  }
  if (nextKeyframes.last?.nodeId === sourceNodeId) {
    nextKeyframes.last = null
    keyframesChanged = true
  }
  if (keyframesChanged) {
    patch.keyframes = nextKeyframes
  }

  const freeRefs = Array.isArray(data.freeRefs) ? data.freeRefs : []
  const nextFreeRefs = freeRefs.filter((r) => r.nodeId !== sourceNodeId)
  if (nextFreeRefs.length !== freeRefs.length) {
    patch.freeRefs = nextFreeRefs
  }

  const refList = getReferenceImagesList(data)
  if (refList.some((r) => r.nodeId === sourceNodeId)) {
    const nextRefs = refList.filter((r) => r.nodeId !== sourceNodeId)
    patch.referenceImages = nextRefs
    const first = nextRefs[0]
    patch.referenceImage = first?.imageUrl ?? null
    patch.referenceImageUrl = first?.imageUrl ?? null
    patch.referenceRef = first ?? null
  }

  if (
    !keyframesChanged
    && !patch.freeRefs
    && !patch.referenceImages
    && data.linkedSourceId !== sourceNodeId
  ) {
    return null
  }

  return patch
}

/** 文本节点连线时可下传的提示词 */
export function getTextNodeOutgoingPrompt(node) {
  if (!node) return null
  const d = node.data || {}
  if (node.type === "text-note" || node.type === "text-response") {
    const text = String(d.prompt || d.content || d.displayPrompt || "").trim()
    return text || null
  }
  return null
}

/**
 * 连线进入目标卡片时写入的数据补丁（参考图 / 首帧 / 提示词 / linkedSource）。
 * 用于 onConnect、拖线创建节点等所有入边路径。
 */
export function buildIncomingEdgeDataPatch(sourceNode, targetType, targetData = {}) {
  if (!sourceNode?.id || !targetType) return {}

  const patch = {
    linkedSourceId: sourceNode.id,
    linkedSourceType: sourceNode.type || null,
  }

  const imageRefRaw = getImageNodeOutgoingRef(sourceNode)
  const imageRef = imageRefRaw?.imageUrl
    ? {
        ...imageRefRaw,
        imageUrl: ensureMediaUrl(imageRefRaw.imageUrl) || imageRefRaw.imageUrl,
      }
    : imageRefRaw

  if (targetType === "image-gen" && imageRef) {
    const existing = getReferenceImagesList(targetData)
    if (existing.length === 0) {
      patch.referenceImages = [imageRef]
      patch.referenceImage = imageRef.imageUrl
      patch.referenceImageUrl = imageRef.imageUrl
      patch.referenceRef = imageRef
    }
  }

  if (targetType === "video-gen" && imageRef) {
    const mode = targetData.referenceMode || "keyframe"
    const keyframes = targetData.keyframes || DEFAULT_KEYFRAMES
    const freeRefs = targetData.freeRefs || []
    if (mode === "keyframe") {
      if (!keyframes.first) {
        patch.keyframes = { ...keyframes, first: imageRef }
        patch.referenceMode = "keyframe"
      } else if (!keyframes.last) {
        patch.keyframes = { ...keyframes, last: imageRef }
        patch.referenceMode = "keyframe"
      }
    } else if (
      !freeRefs.some((r) => r.imageId === imageRef.imageId)
      && freeRefs.length < MAX_REFERENCE_IMAGES
    ) {
      patch.freeRefs = [...freeRefs, imageRef]
      patch.referenceMode = "freeref"
    }
  }

  if (targetType === "image-gen" || targetType === "video-gen") {
    const textPrompt = getTextNodeOutgoingPrompt(sourceNode)
    if (textPrompt && !String(targetData.prompt || "").trim() && !String(targetData.displayPrompt || "").trim()) {
      patch.prompt = textPrompt
      patch.displayPrompt = textPrompt
    }
  }

  return patch
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
