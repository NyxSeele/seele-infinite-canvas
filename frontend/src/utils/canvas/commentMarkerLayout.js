const LABEL_OFFSET_TYPES = new Set(["image-gen", "video-gen"])
const PIN_SIZE = 44
/** 与画布卡片常见 border-radius 一致（约 12px） */
const CARD_CORNER_RADIUS = 12
/** 圆角弧 45° 中点相对直角顶点的内缩（R·(1−1/√2)） */
const ARC_CENTER_OFFSET = CARD_CORNER_RADIUS * (1 - Math.SQRT1_2)

/** 评论角标中心对准卡片右上圆角弧中点。 */
export function getCommentPinPosition(node) {
  if (!node) return null
  const w = node.width ?? node.measured?.width ?? node.style?.width ?? 320
  const labelOffset = LABEL_OFFSET_TYPES.has(node.type) ? 28 : 0
  const cornerX = node.position.x + Number(w) - ARC_CENTER_OFFSET
  const cornerY = node.position.y + labelOffset + ARC_CENTER_OFFSET
  return {
    left: cornerX - PIN_SIZE / 2,
    top: cornerY - PIN_SIZE / 2,
    size: PIN_SIZE,
  }
}
