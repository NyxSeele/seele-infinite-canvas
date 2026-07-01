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
