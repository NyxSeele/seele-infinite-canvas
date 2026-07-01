import { stripMediaTicket } from "../mediaTicket"
import {
  getImageNodeImages,
  normalizePersistentImageUrl,
} from "../../components/canvas/videoReferenceHelpers"

const HISTORY_KEY = "ai_studio_gen_history_v2"
const LEGACY_KEY = "ai_studio_gen_history"
const MAX_STORED = 80

try {
  localStorage.removeItem(LEGACY_KEY)
} catch {
  /* ignore */
}

/** 统一时间戳：毫秒、秒级 Unix、ISO 字符串 */
export function normalizeTimestamp(raw) {
  if (raw == null || raw === "") return null
  if (typeof raw === "number" && Number.isFinite(raw)) {
    return raw < 1e12 ? Math.round(raw * 1000) : Math.round(raw)
  }
  const n = Number(raw)
  if (Number.isFinite(n) && n > 0) {
    return n < 1e12 ? Math.round(n * 1000) : Math.round(n)
  }
  const parsed = Date.parse(String(raw))
  return Number.isFinite(parsed) ? parsed : null
}

function stableUrl(url) {
  if (!url) return null
  return normalizePersistentImageUrl(stripMediaTicket(url))
}

function nodeLabel(d, fallback) {
  const t = d?.label && String(d.label).trim()
  return t || fallback
}

function normalizeHistoryItem(raw) {
  if (!raw?.id) return null
  const mediaUrl = stableUrl(raw.mediaUrl || raw.resultUrl)
  if (!mediaUrl) return null
  return {
    id: raw.id,
    kind: raw.kind === "video" ? "video" : "image",
    mediaUrl,
    title: (raw.title || raw.prompt || "").trim(),
    prompt: raw.prompt || "",
    nodeId: raw.nodeId || null,
    imageIndex: raw.imageIndex ?? null,
    ts: normalizeTimestamp(raw.ts ?? raw.created_at),
    canvasId: raw.canvasId || null,
    canvasName: (raw.canvasName || "").trim() || null,
    teamId: raw.teamId || raw.team_id || null,
    username: raw.username || null,
    source: raw.source || "local",
  }
}

function collectFromImageNode(node, meta) {
  const d = node.data || {}
  const completedAt = normalizeTimestamp(d.completedAt)
  const prompt = (d.prompt || "").trim()
  const teamId = meta.teamId || null

  return getImageNodeImages(node)
    .map((ref) => {
      const mediaUrl = stableUrl(ref.imageUrl)
      if (!mediaUrl) return null
      return {
        id: `img-${ref.nodeId}-${ref.imageIndex}-${mediaUrl.slice(-20)}`,
        kind: "image",
        mediaUrl,
        title: ref.label || nodeLabel(d, "Image"),
        prompt,
        nodeId: node.id,
        imageIndex: ref.imageIndex,
        ts: completedAt,
        canvasId: meta.canvasId || null,
        canvasName: meta.projectName || null,
        teamId,
        source: "canvas",
      }
    })
    .filter(Boolean)
}

function collectFromVideoNode(node, meta) {
  const d = node.data || {}
  const mediaUrl = stableUrl(d.videoUrl)
  if (!mediaUrl) return []
  return [
    {
      id: `vid-${node.id}`,
      kind: "video",
      mediaUrl,
      title: nodeLabel(d, "Video"),
      prompt: (d.prompt || d.displayPrompt || "").trim(),
      nodeId: node.id,
      ts: normalizeTimestamp(d.completedAt),
      canvasId: meta.canvasId || null,
      canvasName: meta.projectName || null,
      teamId: meta.teamId || null,
      source: "canvas",
    },
  ]
}

export function collectHistoryFromNodes(nodes = [], meta = {}) {
  const items = []
  for (const node of nodes) {
    if (node.type === "image-gen") items.push(...collectFromImageNode(node, meta))
    if (node.type === "video-gen") items.push(...collectFromVideoNode(node, meta))
  }
  return items
}

function readStored() {
  try {
    const list = JSON.parse(localStorage.getItem(HISTORY_KEY) || "[]")
    if (!Array.isArray(list)) return []
    return list.map(normalizeHistoryItem).filter(Boolean)
  } catch {
    return []
  }
}

function pickTimestamp(canvasItem, storedItem) {
  return (
    normalizeTimestamp(canvasItem?.ts)
    ?? normalizeTimestamp(storedItem?.ts)
    ?? null
  )
}

function pickCanvasName(canvasItem, storedItem, meta) {
  if (storedItem?.canvasName) return storedItem.canvasName
  if (canvasItem?.canvasName) return canvasItem.canvasName
  if (meta?.projectName) return meta.projectName
  return "未命名画布"
}

function pickCanvasId(canvasItem, storedItem, meta) {
  if (storedItem?.canvasId) return storedItem.canvasId
  if (canvasItem?.canvasId) return canvasItem.canvasId
  if (meta?.canvasId) return meta.canvasId
  return null
}

function pickTeamId(canvasItem, storedItem) {
  if (storedItem?.teamId) return storedItem.teamId
  if (canvasItem?.teamId) return canvasItem.teamId
  return null
}

function sortByTimestamp(list) {
  return [...list].sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0))
}

function mergeHistory(nodes, meta = {}) {
  const map = new Map()
  for (const item of readStored()) map.set(item.id, item)
  for (const canvasItem of collectHistoryFromNodes(nodes, meta)) {
    const stored = map.get(canvasItem.id)
    map.set(canvasItem.id, {
      ...canvasItem,
      title: canvasItem.title || stored?.title || "",
      prompt: canvasItem.prompt || stored?.prompt || "",
      ts: pickTimestamp(canvasItem, stored),
      canvasName: pickCanvasName(canvasItem, stored, meta),
      canvasId: pickCanvasId(canvasItem, stored, meta),
      teamId: pickTeamId(canvasItem, stored),
      username: stored?.username || canvasItem.username || null,
      source: stored?.source || canvasItem.source || "local",
    })
  }
  return sortByTimestamp([...map.values()].filter((item) => item.mediaUrl))
}

export function readGenHistory(nodes = [], meta = {}) {
  const before = readStored()
  const merged = mergeHistory(nodes, meta)
  const backfilled = merged.some((item) => {
    const prev = before.find((b) => b.id === item.id)
    return prev && !prev.canvasName && item.canvasName
  })
  if (backfilled || merged.length !== before.length) {
    try {
      localStorage.setItem(HISTORY_KEY, JSON.stringify(merged.slice(0, MAX_STORED)))
      if (backfilled) {
        window.dispatchEvent(new CustomEvent("gen-history-updated"))
      }
    } catch {
      /* ignore */
    }
  }
  return merged
}

/** 个人 scope：无 teamId 的本地记录 */
export function filterPersonalHistory(list) {
  return list.filter((item) => !item.teamId)
}

export function filterGenHistory(list, tab) {
  if (tab === "video") return list.filter((h) => h.kind === "video")
  if (tab === "image") return list.filter((h) => h.kind === "image")
  return list
}

/** 将 API 任务记录转为历史网格项（仅 completed image/video 且有 result） */
export function mapTaskRecordsToHistory(records = []) {
  return sortByTimestamp(
    records
      .filter((r) => {
        if (r.status !== "completed") return false
        if (!r.result) return false
        return r.task_type === "image" || r.task_type === "video"
      })
      .map((r) =>
        normalizeHistoryItem({
          id: `task-${r.id}`,
          kind: r.task_type === "video" ? "video" : "image",
          mediaUrl: r.result,
          title: (r.prompt_text || "").trim() || (r.task_type === "video" ? "Video" : "Image"),
          prompt: r.prompt_text || "",
          nodeId: r.node_id || null,
          ts: r.created_at,
          teamId: r.team_id || null,
          username: r.username || null,
          canvasName: r.team_name || null,
          source: "server",
        })
      )
      .filter(Boolean)
  )
}

export function pushGenHistory(entry) {
  const mediaUrl = stableUrl(entry.mediaUrl || entry.resultUrl)
  if (!mediaUrl) return null

  const kind = entry.kind || (entry.type === "video-gen" ? "video" : "image")
  const ts = normalizeTimestamp(entry.ts) ?? Date.now()
  const item = normalizeHistoryItem({
    id:
      entry.id
      || `${kind}-${entry.nodeId || "x"}-${entry.imageIndex ?? 0}-${mediaUrl.slice(-16)}`,
    kind,
    mediaUrl,
    title: (entry.title || entry.prompt || "").trim() || (kind === "video" ? "Video" : "Image"),
    prompt: entry.prompt || "",
    nodeId: entry.nodeId || null,
    imageIndex: entry.imageIndex ?? null,
    ts,
    canvasId: entry.canvasId || null,
    canvasName: (entry.canvasName || "").trim() || null,
    teamId: entry.teamId || null,
    source: "local",
  })

  const merged = [
    item,
    ...readStored().filter((h) => h.id !== item.id),
  ].slice(0, MAX_STORED)
  localStorage.setItem(HISTORY_KEY, JSON.stringify(merged))
  window.dispatchEvent(new CustomEvent("gen-history-updated"))
  return item
}

export function formatHistoryTime(ts) {
  const ms = normalizeTimestamp(ts)
  if (!ms) return ""
  return new Date(ms).toLocaleString("zh-CN", {
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  })
}
