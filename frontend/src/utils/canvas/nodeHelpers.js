import { segmentsToScriptPayload } from "./scriptTableSegments"

export const DEFAULT_NODE_WIDTHS = { "image-gen": 280, "video-gen": 400, "script-table": 1100 }
export const SCRIPT_TABLE_WIDTH = 1100
export const BEAT_CARD_WIDTH = 920
export const SCREENPLAY_NODE_OFFSET_X = 520
export const SHOT_SCRIPT_NODE_OFFSET_X = 560
export const SHOT_SCRIPT_TO_TABLE_Y_OFFSET = 480
export const SCRIPT_TABLE_TO_IMAGE_GAP = 48
export const SCRIPT_TABLE_ROW_Y_OFFSET = 210
/** 分镜表顶部统计/设定/工具栏占用高度，用于对齐镜头行与节拍卡 */
export const SCRIPT_TABLE_CHROME_Y = 300
export const SCRIPT_KEYFRAME_Y_STEP = 120
export const DEFAULT_NODE_HEIGHT = 260
export const TEXT_NOTE_WIDTH = 320
export const TEXT_RESPONSE_WIDTH = 480

export const NODE_WIDTHS_MAP = {
  "image-gen": 280,
  "video-gen": 400,
  "text-note": TEXT_NOTE_WIDTH,
  "script-table": SCRIPT_TABLE_WIDTH,
  "script-beat-card": 920,
  outline: 540,
  "shot-script": 840,
}

/** text-note：chat=仅 AI 回复；screenplay=回复后自动走剧本大纲 */
export const TEXT_MODES = {
  CHAT: "chat",
  SCREENPLAY: "screenplay",
}

let _nodeIdSeq = 1

export function makeId(type) {
  return `${type}-${_nodeIdSeq++}`
}

export function sortScriptRows(rows) {
  return [...(rows || [])].sort(
    (a, b) => (a.shotNumber ?? 0) - (b.shotNumber ?? 0)
  )
}

export { scriptRowText } from "./scriptTableKeyframes"

export function segmentsToScriptRows(segments) {
  const { rows } = segmentsToScriptPayload(segments)
  return rows
}

export { segmentsToScriptPayload } from "./scriptTableSegments"

export function computeScriptTableGenX(scriptNode) {
  return (scriptNode?.position?.x || 0) + SCRIPT_TABLE_WIDTH + SCRIPT_TABLE_TO_IMAGE_GAP
}

export function computeScriptTableShotY(scriptNode, rowIndex = 0) {
  return (scriptNode?.position?.y || 0) + SCRIPT_TABLE_CHROME_Y + rowIndex * SCRIPT_TABLE_ROW_Y_OFFSET
}

export function computeBeatCardPosition(scriptNode, rowIndex = 0) {
  return {
    x: computeScriptTableGenX(scriptNode),
    y: computeScriptTableShotY(scriptNode, rowIndex),
  }
}

export function computeScriptTableGenPosition(scriptNode, rowIndex = 0, yExtra = 0) {
  return {
    x: computeScriptTableGenX(scriptNode),
    y: computeScriptTableShotY(scriptNode, rowIndex) + yExtra,
  }
}

/** 新建节点落点：有选中节点时在其右侧；否则避开同位置已有节点 */
export function resolveCreateNodePosition(flowPos, type, existingNodes, options = {}) {
  const { anchorNode } = options
  if (anchorNode) {
    const anchorW =
      NODE_WIDTHS_MAP[anchorNode.type]
      || DEFAULT_NODE_WIDTHS[anchorNode.type]
      || 280
    return {
      x: (anchorNode.position?.x ?? 0) + anchorW + 80,
      y: anchorNode.position?.y ?? 0,
    }
  }

  const base = {
    x: flowPos.x - 140,
    y: flowPos.y - 160,
  }
  const tol = 20
  let candidate = { ...base }
  for (let i = 0; i < 24; i += 1) {
    const hit = (existingNodes || []).some((n) => {
      if (Math.abs((n.position?.x ?? 0) - candidate.x) >= tol) return false
      return Math.abs((n.position?.y ?? 0) - candidate.y) < tol
    })
    if (!hit) return candidate
    candidate = {
      x: base.x + 48 * (i + 1),
      y: base.y + 36 * (i + 1),
    }
  }
  return candidate
}

/** 选中 image-gen 是否适合直接写入上传图（而非再新建一张卡） */
export function isEmptyImageGenNode(node) {
  if (!node || node.type !== "image-gen") return false
  const d = node.data || {}
  if (d.uploadedImage || d.imageUrl) return false
  if (Array.isArray(d.results) && d.results.some(Boolean)) return false
  const st = d.status
  if (st === "pending" || st === "generating" || st === "queued") return false
  return true
}
