import { NODE_WIDTHS_MAP } from "./nodeHelpers"

const LABEL_OFFSET_TYPES = new Set(["image-gen", "video-gen", "text-note"])
const PIN_SIZE = 44
export const CARD_CORNER_RADIUS = 16

/** gn2 / tn：标签行 + wrapper gap 后才是卡片本体顶边 */
const GN2_WRAPPER_GAP = 10
const GN2_LABEL_ROW_HEIGHT = 24
export const GN2_CARD_TOP_OFFSET = GN2_WRAPPER_GAP + GN2_LABEL_ROW_HEIGHT + GN2_WRAPPER_GAP

/** tn-label-row 无 bottom padding，顶边略靠上 */
const TN_CARD_TOP_OFFSET = GN2_WRAPPER_GAP + 18 + GN2_WRAPPER_GAP

/**
 * 各节点类型评论角标锚点：固定视觉宽度 + 卡片本体顶边 Y 偏移。
 * 避免 React Flow measured.width 含加号热区导致角标漂到卡片外。
 */
const CARD_PIN_SPECS = {
  "image-gen": { width: NODE_WIDTHS_MAP["image-gen"], topOffset: GN2_CARD_TOP_OFFSET },
  "video-gen": { width: NODE_WIDTHS_MAP["video-gen"], topOffset: GN2_CARD_TOP_OFFSET },
  "text-note": { width: NODE_WIDTHS_MAP["text-note"], topOffset: TN_CARD_TOP_OFFSET },
  "text-response": { width: 480, topOffset: 0 },
  "script-table": { width: NODE_WIDTHS_MAP["script-table"], topOffset: 0 },
  "shot-script": { width: NODE_WIDTHS_MAP["shot-script"], topOffset: 0 },
  outline: { width: NODE_WIDTHS_MAP.outline, topOffset: 0 },
  "script-beat-card": { width: NODE_WIDTHS_MAP["script-beat-card"], cornerRadius: 12, topOffset: 0 },
}

function resolveVisualWidth(node) {
  const spec = CARD_PIN_SPECS[node.type]
  if (spec?.width) return Number(spec.width)
  const styleW = node.style?.width
  if (styleW != null && styleW !== "") return Number(styleW)
  if (node.width != null) return Number(node.width)
  return 320
}

function resolveTopOffset(node) {
  const spec = CARD_PIN_SPECS[node.type]
  if (spec && spec.topOffset != null) return spec.topOffset
  if (LABEL_OFFSET_TYPES.has(node.type)) return GN2_CARD_TOP_OFFSET
  return 0
}

/** 评论角标圆心对准卡片本体右上顶点（半圆压在圆角弧上） */
export function getCommentPinPosition(node) {
  if (!node) return null
  const w = resolveVisualWidth(node)
  const topOffset = resolveTopOffset(node)
  const cornerX = node.position.x + w
  const cornerY = node.position.y + topOffset
  return {
    left: cornerX - PIN_SIZE / 2,
    top: cornerY - PIN_SIZE / 2,
    size: PIN_SIZE,
  }
}

/** 评论面板锚点矩形（flow 坐标，与 pin 共用 CARD_PIN_SPECS） */
export function getCommentAnchorRect(node) {
  if (!node) return null
  const w = resolveVisualWidth(node)
  const topOffset = resolveTopOffset(node)
  const height = (node.height ?? node.measured?.height ?? node.style?.height ?? 200)
  return {
    x: node.position.x,
    y: node.position.y + topOffset,
    width: w,
    height: Number(height) || 200,
  }
}

export { PIN_SIZE, GN2_WRAPPER_GAP, GN2_LABEL_ROW_HEIGHT }
